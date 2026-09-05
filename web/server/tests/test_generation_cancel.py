"""隔离验证真正杀掉进程树、迟到结果丢弃、终止后的恢复及权限边界。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_prompt
import app
import content_editor
import generation_control as gc
import jobs
import project_setup as setup
import projects
import prompt_tasks
import state
from router import ApiError
from test_project_workflow import FOUNDATION, BOARD, SCRIPT, ctx


def wait_for(predicate):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for test worker')


class CancellationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patcher = patch.object(projects, 'OUTPUT_DIR', str(self.root))
        patcher.start(); self.addCleanup(patcher.stop)
        self.name = setup.create({'name': '取消测试', 'script': SCRIPT, 'duration': 15}, 'owner')
        self.pdir = self.root / self.name

    def test_prompt_cancel_discards_late_result_and_can_retry(self):
        ready = threading.Event()
        def run():
            control = gc.current(); ready.set()
            wait_for(lambda: control.cancelled)
            return {'prompt': '取消后才到达的文字'}
        commit = Mock()
        target = {'job_id': '小雨', 'type': 'asset'}
        task = prompt_tasks.start(self.pdir, target, 'owner', run, commit=commit)
        self.assertTrue(ready.wait(3))
        result = prompt_tasks.cancel(self.pdir, task['id'])
        self.assertEqual(result['status'], 'cancelled')
        self.assertNotIn('result', result)
        commit.assert_not_called()
        self.assertEqual(prompt_tasks.cancel(self.pdir, task['id']), result)
        retry = prompt_tasks.start(self.pdir, target, 'owner', lambda: {'prompt': '重试成功'})
        wait_for(lambda: prompt_tasks.list_tasks(self.pdir)[-1]['status'] == 'done')
        self.assertNotEqual(retry['id'], task['id'])
        self.assertEqual(prompt_tasks.cancel(self.pdir, retry['id'])['status'], 'done')

    def test_real_codex_process_cancel_saves_no_history(self):
        marker = self.root / 'started'
        script = self.root / 'fake_codex'
        script.write_text('#!' + sys.executable + '\nimport pathlib,time\n'
                          f'pathlib.Path({str(marker)!r}).write_text("started")\ntime.sleep(30)\n')
        script.chmod(0o700)
        context = {'prompt': '原有提示词', 'original_prompt': '原有提示词', 'prompt_source': 'test'}
        with patch.dict(os.environ, CODEX_BIN=str(script)), patch.object(app, '_prompt_context', return_value=context), \
                patch.object(app.prompt_history, 'save') as save:
            task = app.api_start_prompt_task(ctx({'job_id': '小雨', 'instruction': '改短发'}), {'name': self.name})['task']
            wait_for(marker.exists)
            control = prompt_tasks._controls[(prompt_tasks.path(self.pdir), task['id'])]
            proc = control.proc
            result = app.api_cancel_prompt_task(ctx(), {'name': self.name, 'identifier': task['id']})
            self.assertEqual(result['task']['status'], 'cancelled')
            self.assertIsNotNone(proc.poll())
            self.assertTrue(control.done.is_set())
            save.assert_not_called()

    def test_cancel_setup_retains_checkpoint_and_resumes(self):
        entered = threading.Event()
        def call(query, schema):
            if schema == setup.FOUNDATION:
                return FOUNDATION
            control = gc.current(); entered.set()
            wait_for(lambda: control.cancelled)
            return BOARD  # 模拟取消瞬间刚收到结果，仍不得落盘。
        with patch.object(setup, '_call', side_effect=call):
            setup.start(self.pdir)
            self.assertTrue(entered.wait(3))
            snapshot = (self.pdir / 'storyboard/characters.md').read_bytes()
            stopped = setup.cancel(self.pdir)
        self.assertEqual(stopped['status'], 'cancelled')
        self.assertEqual(stopped['completed'], 1)
        self.assertFalse((self.pdir / 'storyboard/ep01.md').exists())
        self.assertEqual((self.pdir / 'storyboard/characters.md').read_bytes(), snapshot)
        self.assertNotIn(str(self.pdir), setup._active)
        with patch.object(setup, '_call', return_value=BOARD) as call:
            setup.start(self.pdir)
            wait_for(lambda: str(self.pdir) not in setup._active)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(setup.status(self.pdir)['status'], 'done')

    def test_stop_failed_setup_allows_manual_structure_without_resurrection(self):
        setup._update(self.pdir, status='failed', error='失败')
        self.assertEqual(setup.cancel(self.pdir)['status'], 'cancelled')
        content_editor.add(self.pdir, {'kind': 'character', 'name': '手动角色', 'text': '手工设定'}, 'owner')
        self.assertFalse(setup.can_resume(self.pdir))
        setup.cancel(self.pdir)  # 重复取消不能重置结构版本限制。
        with self.assertRaisesRegex(ValueError, '手动'):
            setup.start(self.pdir)

    def test_image_cancel_kills_descendants_and_preserves_old_files(self):
        out = self.pdir / 'assets'; folder = out / 'test'; folder.mkdir(parents=True)
        old = folder / 'test_01.png'; old.write_bytes(b'previous image')
        marker = self.root / 'child.pid'
        late = folder / 'test_02.png'
        child = f'import time; from pathlib import Path; time.sleep(1); Path({str(late)!r}).write_bytes(b"late")'
        script = self.root / 'fake_images.py'
        script.write_text('import subprocess,sys,time\nfrom pathlib import Path\n'
                          f'p=subprocess.Popen([sys.executable,"-c",{child!r}])\n'
                          f'Path({str(marker)!r}).write_text(str(p.pid))\ntime.sleep(30)\n')
        with patch.object(jobs, 'GENERATE_SCRIPT', str(script)):
            token = jobs.start_regenerate(str(out), 'test', 'dummy', 1, [], str(self.root / 'logs'))
        self.addCleanup(lambda: jobs.cancel(token))
        wait_for(marker.exists)
        self.assertEqual(jobs.cancel(token)['status'], 'cancelled')
        self.assertEqual(jobs.cancel(token)['status'], 'cancelled')
        proc = jobs._registry[token]['proc']
        self.assertIsNotNone(proc.poll())
        self.assertTrue(jobs._registry[token]['log_file'].closed)
        childstat = Path('/proc') / marker.read_text() / 'stat'
        def child_stopped():
            try:
                return childstat.read_text().split()[2] == 'Z'
            except FileNotFoundError:
                return True
        wait_for(child_stopped)
        self.assertEqual(old.read_bytes(), b'previous image')
        self.assertFalse(late.exists())
        self.assertEqual(jobs.get_status(token)['new_files'], [])

    def test_cancel_token_is_project_scoped(self):
        with patch.object(jobs, 'cancel') as cancel:
            with self.assertRaises(ApiError) as exc:
                app.api_cancel_regenerate(ctx(), {'name': self.name, 'token': 'other-project-token'})
            self.assertEqual(exc.exception.status, 404)
            cancel.assert_not_called()
        self.assertIsNone(prompt_tasks.cancel(self.pdir, 'other-project-task'))

    def test_stale_image_poll_cannot_undo_cancellation(self):
        path = str(self.pdir / '_web_state/review.json')
        entry = state.add_regen_job(path, target={}, status='running', token='dummy', kind='image')
        state.update_regen_job(path, entry['id'], status='cancelled', new_files=[])
        state.update_regen_job(path, entry['id'], status='running', new_files=['late.png'])
        self.assertEqual(state.list_regen_jobs(path)[0]['status'], 'cancelled')
        self.assertEqual(state.list_regen_jobs(path)[0]['new_files'], [])

    def test_timeout_stops_process_and_releases_controller(self):
        control = gc.Control()
        with self.assertRaises(subprocess.TimeoutExpired):
            control.run([sys.executable, '-c', 'import time; time.sleep(30)'],
                        input='', timeout=.05, text=True)
        self.assertIsNone(control.proc)


if __name__ == '__main__':
    unittest.main()
