import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import content_editor as editor
import md_tables
import projects
from router import ApiError


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'项目'; (self.root/'storyboard').mkdir(parents=True)
        self.patch=patch.object(projects,'OUTPUT_DIR',self.tmp.name); self.patch.start(); self.addCleanup(self.patch.stop)
        self.characters=self.root/'storyboard/characters.md'
        self.characters.write_text('# 人物\n\n## 1. 小雨\n\n旧角色档案\n\n## 2. 店主\n\n店主档案\n',encoding='utf-8')
        (self.root/'storyboard/scenes.md').write_text('# 场景\n\n## SC01 书店\n\n柜台与书架\n',encoding='utf-8')
        self.episode=self.root/'storyboard/ep01.md'
        self.episode.write_text('# 第一集\n\n| 镜号 | 场景编号 | 画面描述 | 分级 |\n|---|---|---|---|\n| 1 | SC01 | 小雨进店 | B |\n| 2 | SC01 | 店主取信 | A |\n\n原有尾注\n',encoding='utf-8')

    def remove(self,body):
        preview=editor.preview(self.root,body)
        editor.remove(self.root,{'preview_id':preview['id'],'confirmed':True},'owner')
        return preview

    def test_character_delete_preview_restore_preserves_assets_and_other_text(self):
        assets=self.root/'assets/小雨_三视图'; assets.mkdir(parents=True); (assets/'小雨_01.png').write_bytes(b'keep')
        preview=editor.preview(self.root,{'kind':'character','title':'1. 小雨'})
        self.assertIn('ep01 · 镜1',preview['references'])
        self.assertIn('小雨',self.characters.read_text())
        editor.remove(self.root,{'preview_id':preview['id'],'confirmed':True},'owner')
        self.assertNotIn('小雨',self.characters.read_text())
        self.assertIn('店主档案',self.characters.read_text())
        self.assertTrue((assets/'小雨_01.png').exists())
        self.assertTrue(editor.disabled(self.root,'小雨_三视图','asset',None))
        editor.restore(self.root,preview['id'],'owner')
        self.assertIn('旧角色档案',self.characters.read_text())
        self.assertFalse(editor.disabled(self.root,'小雨_三视图','asset',None))
        self.assertEqual(editor.trash(self.root),[])

    def test_stale_or_unconfirmed_delete_is_rejected(self):
        p=editor.preview(self.root,{'kind':'character','title':'1. 小雨'})
        with self.assertRaises(ApiError): editor.remove(self.root,{'preview_id':p['id']},'owner')
        self.characters.write_text(self.characters.read_text()+'新修改\n')
        with self.assertRaises(ApiError) as result: editor.remove(self.root,{'preview_id':p['id'],'confirmed':True},'owner')
        self.assertEqual(result.exception.status,409)
        self.assertIn('小雨',self.characters.read_text())

    def test_add_and_insert_shots_keep_ids_and_tail_and_escape_pipes(self):
        result=editor.add(self.root,{'kind':'shot','episode':1,'after':'1','row':{'画面描述':'新动作 | 特写','分级':'A'}},'owner')
        self.assertEqual(result['shot'],'3')
        table=md_tables.parse_table(self.episode.read_text())
        self.assertEqual([r['镜号'] for r in table['rows']],['1','3','2'])
        self.assertEqual(table['rows'][1]['画面描述'],'新动作 | 特写')
        self.assertTrue(self.episode.read_text().endswith('原有尾注\n'))
        preview=self.remove({'kind':'shot','episode':1,'shot':'3'})
        result=editor.add(self.root,{'kind':'shot','episode':1,'row':{'画面描述':'另一镜'}},'owner')
        self.assertEqual(result['shot'],'4')
        editor.restore(self.root,preview['id'],'owner')
        self.assertEqual([r['镜号'] for r in md_tables.parse_table(self.episode.read_text())['rows']],['1','3','2','4'])

    def test_episode_add_delete_restore_and_shot_parent_guard(self):
        result=editor.add(self.root,{'kind':'episode','name':'新的一集'},'owner')
        self.assertEqual(result['episode'],2)
        self.assertEqual(md_tables.parse_table((self.root/'storyboard/ep02.md').read_text())['rows'],[])
        shot=self.remove({'kind':'shot','episode':1,'shot':'1'})
        self.assertTrue(editor.disabled(self.root,'ep01_镜01','keyframe',1))
        episode=self.remove({'kind':'episode','episode':1})
        with self.assertRaises(ApiError): editor.restore(self.root,shot['id'],'owner')
        editor.restore(self.root,episode['id'],'owner')
        editor.restore(self.root,shot['id'],'owner')
        self.assertIn('小雨进店',self.episode.read_text())

    def test_names_and_scene_ids_are_not_reused(self):
        self.remove({'kind':'character','title':'1. 小雨'})
        with self.assertRaises(ApiError): editor.add(self.root,{'kind':'character','name':'小雨','text':'新人'},'owner')
        result=editor.add(self.root,{'kind':'character','name':'小风','text':'新角色'},'owner')
        self.assertEqual(result['title'],'3. 小风')
        (self.root/'assets/SC09_旧素材').mkdir(parents=True)
        result=editor.add(self.root,{'kind':'scene','name':'街道','text':'街景'},'owner')
        self.assertEqual(result['title'],'SC10 街道')

    def test_scope_and_generation_guard(self):
        for body in ({'kind':'bad'},{'kind':'shot','episode':'../x'},{'kind':'character','name':'../x','text':'内容'}):
            with self.assertRaises(ApiError): editor.add(self.root,body,'owner')
        (self.root/'_web_state').mkdir(exist_ok=True)
        (self.root/'_web_state/setup.json').write_text(json.dumps({'status':'running'}))
        with self.assertRaises(ApiError) as error: editor.add(self.root,{'kind':'character','name':'新角色','text':'内容'},'owner')
        self.assertEqual(error.exception.status,409)

    def test_restore_does_not_overwrite_reused_identity(self):
        preview=self.remove({'kind':'character','title':'1. 小雨'})
        self.characters.write_text(self.characters.read_text()+'\n## 9. 小雨\n新内容\n')
        with self.assertRaises(ApiError): editor.restore(self.root,preview['id'],'owner')
        self.assertIn('新内容',self.characters.read_text())
