"""项目文字筹备、版本回溯和图片审批的隔离回归测试；不调用模型或出图。"""
import base64
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import approvals
import auth
import control_store
import project_setup as setup
import projects
import prompt_history
import prompt_tasks
from router import ApiError, Ctx

SCRIPT = '小雨推开旧书店的门。小雨说：“我来取父亲留下的信。”店主从柜台下取出一个信封。'
FOUNDATION = {
    'style_bible': '写实暖光，竖屏9:16；按原剧本叙事。', 'style_anchor': '写实暖光，竖屏9:16',
    'synopsis': '小雨到书店领取父亲的信。',
    'characters': [{'name': '小雨', 'profile': '来取信的女儿；服装为制作建议。', 'prompt': '小雨，三视图，朴素外套'}],
    'scenes': [{'id': 'SC01', 'name': '旧书店', 'description': '入口与柜台位置为规划。', 'prompt': '旧书店空景'}],
    'episodes': [{'number': 1, 'title': '来信', 'summary': '按原文取信'}],
}
SHOT = {key: '无' for key in setup.SHOT_FIELDS}
SHOT.update({'场景编号': 'SC01', '机位': 'A主机位（规划）', '分级': 'B', '时长(秒)': 15,
             '剧本原文锚点': '小雨推开旧书店的门。'})
BOARD = {'title': '来信', 'shots': [SHOT]}


def ctx(body=None, username='owner'):
    result = Ctx({}, json.dumps(body or {}).encode(), {})
    result.username = username
    return result


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        private = patch.object(auth, 'DATA_DIR', str(self.root / '_accounts'))
        private.start(); self.addCleanup(private.stop)
        control_store.allocate('owner',1000,'test','fixture-credits')
        for p in (patch.object(projects, 'OUTPUT_DIR', str(self.root)),
                  patch.object(setup, '_capacity', threading.BoundedSemaphore(2)),
                  patch.object(setup, '_active', set())):
            p.start()
            self.addCleanup(p.stop)
        self.name = setup.create({'name': '新剧', 'script': SCRIPT, 'duration': 15}, 'owner')
        self.pdir = self.root / self.name
        self.params = {'name': self.name}

    def run_worker(self, values):
        setup._capacity.acquire()
        with patch.object(setup, '_call', side_effect=values) as call:
            setup._worker(str(self.pdir))
        return call

    def test_text_only_bootstrap_integrates_with_existing_views(self):
        with patch.object(app.jobs, 'start_regenerate') as images:
            self.run_worker([FOUNDATION, BOARD])
            images.assert_not_called()
        progress = setup.status(self.pdir)
        self.assertEqual(progress['status'], 'done')
        self.assertEqual(progress['completed'], 2)
        self.assertTrue(all((self.pdir / f).is_file() for f in progress['files']))
        self.assertIn('storyboard/ep01.md', progress['files'])
        self.assertEqual(projects.list_episode_numbers(self.name), [1])
        self.assertEqual(list(self.pdir.rglob('*.png')), [])
        response = app.api_setup(ctx(), self.params)
        self.assertEqual(response['gpu']['status'], 'needs_plan')
        self.assertEqual(len(response['image_tasks']), 2)
        prompt = app._prompt_context(ctx(), self.params, '小雨_三视图', 'asset', None)
        self.assertIn('朴素外套', prompt['prompt'])
        self.assertEqual(prompt['ref_images'], [])
        self.assertTrue(prompt['history'])

    def test_resume_preserves_edits_and_skips_completed_stages(self):
        self.run_worker([FOUNDATION, RuntimeError('暂时中断')])
        self.assertEqual(setup.status(self.pdir)['status'], 'failed')
        edited = self.pdir / 'storyboard/characters.md'
        edited.write_text('用户已手动修订', encoding='utf-8')
        call = self.run_worker([BOARD])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(edited.read_text(encoding='utf-8'), '用户已手动修订')
        self.assertEqual(setup.status(self.pdir)['status'], 'done')
        self.assertEqual(self.run_worker([]).call_count, 0)

    def test_script_anchors_and_malformed_foundation_fail_cleanly(self):
        fields = setup._board_schema(FOUNDATION)['properties']['shots']['items']['properties']
        self.assertEqual(fields['场景编号']['enum'], ['SC01'])
        self.assertEqual(fields['分级']['enum'], ['S', 'A', 'B', 'C'])
        invalid = copy.deepcopy(BOARD)
        invalid['shots'][0]['剧本原文锚点'] = '原文不存在的剧情'
        self.run_worker([FOUNDATION, invalid])
        self.assertEqual(setup.status(self.pdir)['status'], 'failed')
        self.assertFalse((self.pdir / 'storyboard/ep01.md').exists())
        for field, value in [('episodes', [None]), ('scenes', [{'id': None}])]:
            invalid = {**FOUNDATION, field: value}
            with self.assertRaises(ValueError):
                setup._validate_foundation(invalid, 1)

    def test_owner_access_and_duplicate_name_protection(self):
        with patch.object(auth, 'allowed_projects', return_value=[]):
            self.assertTrue(auth.can_access_project('owner', self.name))
            self.assertFalse(auth.can_access_project('stranger', self.name))
            self.assertEqual(len(app.api_projects(ctx(), {})['projects']), 1)
            self.assertEqual(app.api_projects(ctx(username='stranger'), {})['projects'], [])
        with self.assertRaises(FileExistsError):
            setup.create({'name': self.name, 'script': SCRIPT}, 'stranger')
        self.assertEqual(projects.owner(self.name), 'owner')
        for name in ('../escape', '_hidden', 'folder/name', '..', ' padded '):
            with self.assertRaises(ValueError):
                setup.create({'name': name, 'script': SCRIPT}, 'owner')

    def test_docx_and_text_import_and_invalid_uploads(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + SCRIPT + '</w:t></w:r></w:p></w:body></w:document>')
        for name, raw in [('script.docx', buf.getvalue()), ('script.txt', SCRIPT.encode()), ('script.md', SCRIPT.encode('gb18030'))]:
            text, stored, original = setup.import_script({'upload': {'name': name, 'base64': base64.b64encode(raw).decode()}})
            self.assertEqual(text, SCRIPT)
            self.assertEqual(original, raw)
            self.assertTrue(stored.startswith('uploaded_script.'))
        for upload in ({'name': 'script.pdf', 'base64': ''}, {'name': 'script.docx', 'base64': 'bad'}):
            with self.assertRaises(ValueError):
                setup.import_script({'upload': upload})

    def test_interruption_recovery_and_file_scope(self):
        setup._update(self.pdir, status='running')
        setup.recover_interrupted()
        self.assertEqual(setup.status(self.pdir)['status'], 'interrupted')
        request = ctx()
        request.query = {'path': ['../project.json']}
        with self.assertRaises(ApiError):
            app.api_setup_file(request, self.params)

    def test_history_select_is_scoped_and_forwarded_to_codex(self):
        self.run_worker([FOUNDATION, BOARD])
        path, key = app._history_location(str(self.pdir), '小雨_三视图', 'asset', None)
        saved = prompt_history.save(path, key, '早期长发，暖光，竖屏', '手动保存', 'owner')
        prompt_history.save(path, key, saved['prompt'], '手动保存', 'owner')
        other = prompt_history.save(path, 'asset:0:别人', '另一个人的历史', '手动保存', 'owner')
        history = app._prompt_context(ctx(), self.params, '小雨_三视图', 'asset', None)['history']
        self.assertEqual(sum(v['id'] == saved['id'] for v in history), 1)
        self.assertNotIn(other['id'], [v['id'] for v in history])
        body = {'job_id': '小雨_三视图', 'instruction': '改成短发', 'current_prompt': saved['prompt'], 'prompt_version_id': saved['id']}
        with patch.object(app.ai_prompt, 'rewrite', return_value='短发，暖光，竖屏') as rewrite:
            result = app.api_ai_rewrite_prompt(ctx(body), self.params)
            rewrite.assert_called_once_with(saved['prompt'], '改成短发', original_prompt=saved['prompt'])
            self.assertEqual(result['version']['source'], 'Codex 改写')
            body['prompt_version_id'] = other['id']
            with self.assertRaises(ApiError):
                app.api_ai_rewrite_prompt(ctx(body), self.params)
            self.assertEqual(rewrite.call_count, 1)

    def test_preview_is_required_and_approval_executes_exact_snapshot_once(self):
        self.run_worker([FOUNDATION, BOARD])
        body = {'job_id': '小雨_三视图', 'prompt': '已经审阅的提示词', 'count': 1, 'ref_images': []}
        with patch.object(app.jobs, 'start_regenerate', return_value='token') as generate:
            with self.assertRaises(ApiError) as error:
                app.api_regenerate(ctx(body), self.params)
            self.assertEqual(error.exception.status, 403)
            entry = app.api_regenerate_preview(ctx(body), self.params)['approval']
            generate.assert_not_called()
            approved = {'approval_id': entry['id'], 'approved': True, 'prompt': '偷偷替换', 'count': 6}
            app.api_regenerate(ctx(approved), self.params)
            app.api_regenerate(ctx(approved), self.params)
            self.assertEqual(generate.call_count, 1)
            self.assertEqual(generate.call_args.args[2:5], ('已经审阅的提示词', 1, []))
            self.assertEqual(app.state.load(approvals.path(self.pdir))['approvals'][0]['approved_by'], 'owner')

    def test_foreign_expired_and_failed_approvals_cannot_execute(self):
        entry = approvals.preview(self.pdir, {'prompt': 'draft'}, 'owner')
        submit = Mock(return_value={'token': 'once'})
        with self.assertRaises(ValueError):
            approvals.execute(self.root, entry['id'], 'owner', submit)
        with patch.object(approvals.time, 'time', return_value=time.time() + 86401):
            with self.assertRaises(ValueError):
                approvals.execute(self.pdir, entry['id'], 'owner', submit)
        submit.assert_not_called()
        submit.side_effect = RuntimeError('启动失败')
        with self.assertRaises(RuntimeError):
            approvals.execute(self.pdir, entry['id'], 'owner', submit)
        with self.assertRaises(ValueError):
            approvals.execute(self.pdir, entry['id'], 'owner', submit)
        self.assertEqual(submit.call_count, 1)

    def test_fresh_mode_ignores_history_and_current_editor(self):
        self.run_worker([FOUNDATION, BOARD])
        body = {'job_id': '小雨_三视图', 'mode': 'fresh', 'instruction': '重新设计一个机器人',
                'current_prompt': '旧人物设定', 'prompt_version_id': '不存在的历史版本'}
        with patch.object(app.ai_prompt, 'fresh', return_value='全新机器人提示词') as fresh, patch.object(app.ai_prompt, 'rewrite') as edit:
            result = app.api_ai_rewrite_prompt(ctx(body), self.params)
            fresh.assert_called_once_with('重新设计一个机器人')
            edit.assert_not_called()
            self.assertIsNone(result['prompt_source'])
            self.assertEqual(result['version']['source'], 'Codex 全新生成')

    def test_prompt_task_survives_client_and_duplicate_start(self):
        entered, release = threading.Event(), threading.Event()
        def run():
            entered.set()
            release.wait(3)
            return {'prompt': '后台保存的结果'}
        target = {'type': 'asset', 'job_id': '角色', 'episode': None}
        task = prompt_tasks.start(self.pdir, target, 'owner', run)
        self.assertTrue(entered.wait(1))
        duplicate = prompt_tasks.start(self.pdir, target, 'owner', Mock())
        self.assertEqual(task['id'], duplicate['id'])
        self.assertEqual(prompt_tasks.list_tasks(self.pdir)[0]['status'], 'running')
        release.set()
        for _ in range(100):
            saved = prompt_tasks.list_tasks(self.pdir)[0]
            if saved['status'] != 'running':
                break
            time.sleep(.01)
        self.assertEqual(saved['result']['prompt'], '后台保存的结果')
        with patch.object(auth, 'allowed_projects', return_value=[]):
            self.assertEqual(app.api_tasks(ctx(), {})['tasks'][0]['id'], task['id'])
            self.assertEqual(app.api_tasks(ctx(username='stranger'), {})['tasks'], [])

    def test_task_listing_retains_image_results_and_checks_project(self):
        app.state.add_regen_job(app._state_path(self.name), {'type': 'asset', 'job_id': '小雨_三视图', 'episode': None}, status='running', token='token')
        live = {'status': 'done', 'job_id': '小雨_三视图', 'token': 'token', 'new_files': ['小雨_三视图_01.png']}
        with patch.object(auth, 'allowed_projects', return_value=[]), patch.object(app.jobs, 'get_status', return_value=live):
            self.assertEqual(app.api_tasks(ctx(), {})['tasks'][0]['new_files'], live['new_files'])
        with patch.object(auth, 'allowed_projects', return_value=[]), patch.object(app.jobs, 'get_status', return_value=None):
            self.assertEqual(app.api_tasks(ctx(), {})['tasks'][0]['status'], 'done')
        with self.assertRaises(ApiError):
            app.api_regenerate_status(ctx(), {'name': self.name, 'token': 'foreign'})


if __name__ == '__main__':
    unittest.main()
