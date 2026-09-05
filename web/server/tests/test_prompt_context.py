import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import jobs
import projects
from router import ApiError, Ctx


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / '测试剧'
        self.assets = self.project / 'assets'
        self.assets.mkdir(parents=True)
        (self.project / 'storyboard').mkdir()
        (self.project / 'storyboard/characters.md').write_text(
            '## 画风锚点\n写实暖光\n\n## 1. 江砚（男主）\n### 提示词正文\n```\n25岁男性，短发，竖屏\n```\n\n## 2. 苏慧\n母亲\n', encoding='utf-8')
        for jid in ['江砚_正面', '江砚_侧面', '苏慧_正面']:
            d = self.assets / jid
            d.mkdir()
            (d / (jid + '_01.png')).write_bytes(b'image')
        self.output_patch = patch.object(projects, 'OUTPUT_DIR', str(self.root))
        self.output_patch.start()
        self.addCleanup(self.output_patch.stop)

    def manifest(self, entries):
        (self.assets / 'manifest.append.jsonl').write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in entries), encoding='utf-8')

    def context(self):
        return app._prompt_context(Ctx({}, b'', {}), {'name': '测试剧'}, '江砚_正面', 'asset', None)

    def test_empty_selection_record_cannot_erase_prompt(self):
        self.manifest([
            {'job_id': '江砚_正面', 'prompt': '完整原文', 'ref_images': ['a']},
            {'job_id': '江砚_正面', 'prompt': '后来修改', 'ref_images': ['b']},
            {'job_id': '江砚_正面', 'file': 'image.png'},
            {'job_id': '江砚_正面', 'prompt': ''},
        ])
        result = jobs.find_job_context(self.assets, '江砚_正面')
        self.assertEqual(result['prompt'], '后来修改')
        self.assertEqual(result['original_prompt'], '完整原文')
        self.assertEqual(result['ref_images'], ['b'])

    def test_missing_manifest_prompt_falls_back_to_exact_job(self):
        self.manifest([{'job_id': '江砚_正面', 'file': 'image.png'}])
        (self.assets / 'jobs_round1.json').write_text(json.dumps([
            {'id': '苏慧_正面', 'prompt': '其他人'}, {'id': '江砚_正面', 'prompt': '原始任务提示词'}]), encoding='utf-8')
        result = self.context()
        self.assertEqual(result['prompt'], '原始任务提示词')
        self.assertEqual(result['prompt_source'], 'jobs_round1.json')

    def test_reference_options_are_from_same_character_section(self):
        result = self.context()
        self.assertEqual({o['job_id'] for o in result['reference_options']}, {'江砚_正面', '江砚_侧面'})
        self.assertIn('25岁男性', result['prompt'])
        self.assertIn('写实暖光', result['prompt'])
        self.assertIn('storyboard/characters.md', result['prompt_source'])

    def test_remaps_old_development_machine_reference_path(self):
        rel = '测试剧/assets/江砚_侧面/江砚_侧面_01.png'
        self.manifest([{'job_id': '江砚_正面', 'prompt': '原文', 'ref_images': ['/workspaces/AI-/output/' + rel]}])
        result = self.context()
        self.assertEqual(result['ref_images'], [rel])
        self.assertTrue(result['reference_options'][0]['previous'])

    def test_explicit_reference_choices_reach_generator_and_empty_stays_empty(self):
        rel = '测试剧/assets/江砚_侧面/江砚_侧面_01.png'
        self.manifest([{'job_id': '江砚_正面', 'prompt': '原文', 'ref_images': ['output/' + rel]}])
        with patch.object(app.jobs, 'start_regenerate', return_value='test') as generate, patch.object(app.state, 'add_regen_job'):
            for refs in ([rel], []):
                body = {'job_id': '江砚_正面', 'prompt': '最终编辑文本', 'ref_images': refs}
                ctx = Ctx({}, json.dumps(body).encode(), {})
                ctx.username = 'tester'
                approval = app.api_regenerate_preview(ctx, {'name': '测试剧'})['approval']
                ctx = Ctx({}, json.dumps({'approval_id': approval['id'], 'approved': True}).encode(), {})
                ctx.username = 'tester'
                response = app.api_regenerate(ctx, {'name': '测试剧'})
                self.assertEqual(response['used_ref_images'], refs)
                self.assertEqual(generate.call_args.args[2], '最终编辑文本')
                self.assertEqual(generate.call_args.args[4], [str(self.root / p) for p in refs])

    def test_rejects_foreign_project_traversal_and_nonimages(self):
        for refs in (['别的剧/assets/x.png'], ['测试剧/../file.png'], 'not-a-list', [None], ['测试剧/storyboard/characters.md']):
            with self.assertRaises(ApiError):
                app._reference_paths('测试剧', refs)


if __name__ == '__main__':
    unittest.main()
