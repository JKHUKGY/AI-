"""不消耗额度的 Codex 适配器与路由回归测试。"""
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_prompt
import app
from router import ApiError, Ctx


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.slot_patch = patch.object(ai_prompt, '_slots', threading.BoundedSemaphore(2))
        self.slot_patch.start()
        self.addCleanup(self.slot_patch.stop)

    def test_result_comes_from_final_message_not_cli_diagnostics(self):
        def run(cmd, **kwargs):
            self.assertEqual(cmd[-1], '-')
            self.assertNotIn('长发人物', cmd)
            self.assertIn('长发人物', kwargs['input'])
            self.assertIn('短发', kwargs['input'])
            self.assertEqual(cmd[cmd.index('--sandbox') + 1], 'read-only')
            Path(cmd[cmd.index('--output-last-message') + 1]).write_text('短发人物，原有构图', encoding='utf-8')
            return subprocess.CompletedProcess(cmd, 0, 'diagnostic', '')
        with patch.object(ai_prompt.subprocess, 'run', side_effect=run):
            self.assertEqual(ai_prompt.rewrite('长发人物', '改为短发', original_prompt='长发人物'), '短发人物，原有构图')

    def test_timeout_and_missing_cli_release_capacity(self):
        for error in (subprocess.TimeoutExpired('codex', 120), FileNotFoundError()):
            with patch.object(ai_prompt.subprocess, 'run', side_effect=error):
                with self.assertRaises(RuntimeError):
                    ai_prompt.rewrite('原文', '修改')
            self.assertTrue(ai_prompt._slots.acquire(blocking=False))
            self.assertTrue(ai_prompt._slots.acquire(blocking=False))
            ai_prompt._slots.release()
            ai_prompt._slots.release()

    def test_empty_output_is_failure(self):
        with patch.object(ai_prompt.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'logs', '')):
            with self.assertRaisesRegex(RuntimeError, '没有返回'):
                ai_prompt.rewrite('', '画一个客厅')

    def test_structured_text_passes_schema_and_disables_execution_tools(self):
        schema = {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}
        def run(cmd, **kwargs):
            self.assertEqual(json.loads(Path(cmd[cmd.index('--output-schema') + 1]).read_text()), schema)
            self.assertEqual(kwargs['timeout'], 600)
            for feature in ('shell_tool', 'unified_exec', 'apps', 'plugins', 'multi_agent', 'image_generation'):
                self.assertIn(f'features.{feature}=false', cmd)
            Path(cmd[cmd.index('--output-last-message') + 1]).write_text('{"text":"草案"}', encoding='utf-8')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(ai_prompt.subprocess, 'run', side_effect=run):
            self.assertEqual(json.loads(ai_prompt.run_text('只写文字', timeout=600, schema=schema)), {'text': '草案'})

    def test_fresh_prompt_is_only_based_on_new_description(self):
        with patch.object(ai_prompt, 'run_text', return_value='机器人') as run:
            self.assertEqual(ai_prompt.fresh('设计一个机器人'), '机器人')
            self.assertIn('设计一个机器人', run.call_args.args[0])
            self.assertNotIn('<original_prompt>', run.call_args.args[0])

    def test_failure_does_not_expose_diagnostics(self):
        for stderr, expected in [('401 bearer PRIVATE', '登录'), ('429 PRIVATE', '额度'), ('PRIVATE', '调用失败')]:
            with patch.object(ai_prompt.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', stderr)):
                with self.assertRaisesRegex(RuntimeError, expected) as result:
                    ai_prompt.rewrite('原文', '修改')
                self.assertNotIn('PRIVATE', str(result.exception))

    def test_invalid_and_busy_requests_do_not_start_cli(self):
        with patch.object(ai_prompt.subprocess, 'run') as run:
            for args in [(None, 'x'), ('x', ''), ('x', 'y' * 4001), ('x' * 30001, 'y')]:
                with self.assertRaises(ValueError):
                    ai_prompt.rewrite(*args)
            ai_prompt._slots.acquire()
            ai_prompt._slots.acquire()
            with self.assertRaises(ai_prompt.BusyError):
                ai_prompt.rewrite('原文', '修改')
            run.assert_not_called()

    def request(self, body):
        ctx = Ctx({}, json.dumps(body).encode(), {})
        ctx.username = 'tester'
        return app.api_ai_rewrite_prompt(ctx, {'name': 'test'})

    def test_route_always_supplies_history_even_when_editor_has_text(self):
        context = {'prompt': '上次版本', 'original_prompt': '完整历史原文', 'prompt_source': 'manifest.append.jsonl'}
        with patch.object(app, '_project_or_404', return_value='/tmp/test'), patch.object(app, '_prompt_context', return_value=context), patch.object(app.prompt_history, 'save'), patch.object(app.ai_prompt, 'rewrite', return_value='新提示词') as rewrite:
            for current in ('', '编辑后的版本'):
                self.request({'job_id': '角色', 'instruction': '短发', 'current_prompt': current})
                rewrite.assert_called_with(current or '上次版本', '短发', original_prompt='完整历史原文')

    def test_route_does_not_silently_draft_when_history_missing(self):
        context = {'prompt': None, 'original_prompt': None, 'prompt_source': None}
        with patch.object(app, '_project_or_404', return_value='/tmp/test'), patch.object(app, '_prompt_context', return_value=context), patch.object(app.ai_prompt, 'rewrite') as rewrite:
            with self.assertRaises(ApiError) as result:
                self.request({'job_id': '角色', 'instruction': '短发'})
            self.assertEqual(result.exception.status, 400)
            rewrite.assert_not_called()

    def test_route_rejects_bad_input_and_maps_busy(self):
        with patch.object(app, '_project_or_404', return_value='/tmp/test'), patch.object(app.ai_prompt, 'rewrite', side_effect=ai_prompt.BusyError('忙')):
            for body in ([], {'job_id': '角色', 'instruction': []}, {'job_id': 2, 'instruction': 'x'}):
                with self.assertRaises(ApiError) as result:
                    self.request(body)
                self.assertEqual(result.exception.status, 400)
            with self.assertRaises(ApiError) as result:
                self.request({'job_id': '角色', 'instruction': '短发', 'current_prompt': '原文'})
            self.assertEqual(result.exception.status, 429)


if __name__ == '__main__':
    unittest.main()
