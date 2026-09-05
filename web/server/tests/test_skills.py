import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import skill_api
import skill_catalog
import state
from router import ApiError, Ctx


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'test-project'
        self.root.mkdir()
        self.patchers = [patch.object(skill_api.projects, 'OUTPUT_DIR', self.temp.name),
                         patch.object(skill_api.auth, 'is_admin', return_value=True),
                         patch.object(skill_api.control_store, 'require_feature')]
        for p in self.patchers:
            p.start(); self.addCleanup(p.stop)

    def call(self, route, body=None):
        ctx = Ctx({}, json.dumps(body or {}).encode(), {})
        ctx.username = 'tester'
        fn, params = app.router.match('POST', f'/api/projects/{self.root.name}/skills/{route}')
        self.assertIsNotNone(fn)
        return fn(ctx, params)

    def proposal(self):
        def immediate(root, target, username, run):
            return {'id': 'preview-task', 'result': run()}
        with patch.object(skill_api.ai_prompt, 'run_text', return_value='生成故事大纲，先核对人物'), \
                patch.object(skill_api.prompt_tasks, 'start', side_effect=immediate):
            return self.call('short-drama-scout/preview', {'request': '写一个书店故事'})['task']['result']['proposal']

    def test_all_skills_installed_and_latest_modes_included(self):
        self.assertEqual(len(skill_catalog.catalog()), 14)
        text = skill_catalog.instructions('short-drama-keyframe-gen')
        self.assertIn('user_choice', text)
        self.assertIn('managed', text)
        with self.assertRaises(ApiError): skill_catalog.get('../auth')

    def test_h3_probe_allowed_but_execution_planning_disabled(self):
        with self.assertRaises(ApiError) as error:
            self.call('minimax-h3-export/preview', {'request': '导出'})
        self.assertEqual(error.exception.status, 409)
        with patch.object(skill_api.prompt_tasks, 'start', return_value={'id': 'probe'}):
            self.assertEqual(self.call('minimax-h3-export/probe')['task']['id'], 'probe')

    def test_preview_never_executes_and_duplicate_approval_submits_once(self):
        with patch.object(skill_api, '_execute') as execute:
            identifier = self.proposal()
            execute.assert_not_called()
        with patch.object(skill_api.prompt_tasks, 'start', return_value={'id': 'one'}) as start:
            one = self.call('execute', {'proposal': identifier, 'approved': True})
            two = self.call('execute', {'proposal': identifier, 'approved': True})
        self.assertEqual(one, two)
        self.assertEqual(start.call_count, 1)

    def test_requires_admin_approval_owner_and_current_version(self):
        identifier = self.proposal()
        with patch.object(skill_api.auth, 'is_admin', return_value=False):
            with self.assertRaises(ApiError) as err: self.call('execute', {'proposal': identifier, 'approved': True})
            self.assertEqual(err.exception.status, 403)
        with self.assertRaises(ApiError): self.call('execute', {'proposal': identifier})
        filename = skill_api._store(self.root)
        data = state.load(filename); data['proposals'][identifier]['version'] = 'old'; state.save(filename, data)
        with self.assertRaises(ApiError) as err: self.call('execute', {'proposal': identifier, 'approved': True})
        self.assertEqual(err.exception.status, 409)
        data['proposals'][identifier]['author'] = 'someone-else'; state.save(filename, data)
        with self.assertRaises(ApiError) as err: self.call('execute', {'proposal': identifier, 'approved': True})
        self.assertEqual(err.exception.status, 404)

    def test_work_copy_keeps_source_and_omits_outside_links_and_configs(self):
        (self.root / 'assets').mkdir()
        source = self.root / 'assets/input.png'; source.write_bytes(b'image')
        text = self.root / 'assets/selected.md'; text.write_text('original')
        (self.root / 'assets/runpod_config.json').write_text('private')
        outside = Path(self.temp.name) / 'other.md'; outside.write_text('other project')
        (self.root / 'assets/outside.md').symlink_to(outside)
        work = self.root / '_web_state/work'; work.mkdir(parents=True)
        dest = skill_api._prepare(self.root, work)
        (dest / 'assets/selected.md').write_text('changed')
        self.assertEqual(text.read_text(), 'original')
        self.assertTrue((dest / 'assets/input.png').is_symlink())
        self.assertFalse((dest / 'assets/outside.md').exists())
        self.assertFalse((dest / 'assets/runpod_config.json').exists())
        self.assertTrue((work / '.agents/skills/short-drama-keyframe-gen/SKILL.md').is_file())


if __name__ == '__main__': unittest.main()
