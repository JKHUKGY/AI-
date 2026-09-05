"""Arrange v3 once; preserve old paths, then refresh human reading views."""
from pathlib import Path
import hashlib
import html
import json
import os
import re
from urllib.parse import quote
from markdown_it import MarkdownIt

ROOT = Path('/workspaces/AI-')
PROJECT = ROOT/'output/出狱后我成为了非洲矿王_v3'
HUMAN = PROJECT/'给人看'
MACHINE = PROJECT/'机器文件'
PROCESS = MACHINE/'制作过程'
assert PROJECT.resolve().is_relative_to(ROOT)
for p in [HUMAN, PROCESS]: p.mkdir(parents=True, exist_ok=True)

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def alias(dst, src):
    assert dst.parent.resolve().is_relative_to(ROOT)
    assert src.resolve().is_relative_to(ROOT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        if dst.resolve() == src.resolve(): return
        if dst.is_relative_to(HUMAN): dst.unlink()
        else: raise RuntimeError(f'Existing alias conflict: {dst}')
    if dst.exists(): raise RuntimeError(f'Existing file conflict: {dst}')
    dst.symlink_to(os.path.relpath(src, dst.parent))

audit = []
for name in ['storyboard', 'assets', 'keyframes', 'videos']:
    old = PROJECT/name
    if not old.exists() or old.is_symlink(): continue
    dest = PROCESS/name
    if dest.exists(): raise RuntimeError(f'Move collision: {dest}')
    hashes, links = {}, []
    for parent, dirs, files in os.walk(old, followlinks=False):
        for n in dirs + files:
            f = Path(parent)/n
            if f.is_symlink(): links.append((f.relative_to(old), f.resolve(strict=True)))
        for n in files:
            f = Path(parent)/n
            if not f.is_symlink(): hashes[f.relative_to(old)] = digest(f)
    old.rename(dest)
    alias(old, dest)
    # Relative links to inherited v2 assets must keep pointing at the same images.
    for rel, target in links:
        link = dest/rel
        link.unlink()
        link.symlink_to(os.path.relpath(target, link.parent))
        assert link.resolve(strict=True) == target.resolve(strict=True)
    for rel, h in hashes.items(): assert digest(old/rel) == h, str(rel)
    audit.append({'old':str(old.relative_to(PROJECT)), 'new':str(dest.relative_to(PROJECT)),
                  'verified_original_files':len(hashes),'preserved_symlinks':len(links)})

original_readme = MACHINE/'项目说明_原始.md'
if not original_readme.exists(): original_readme.write_bytes((PROJECT/'README.md').read_bytes())
progress_source = MACHINE/'制作进度源.md'
if not (PROJECT/'PROGRESS.md').is_symlink():
    assert not progress_source.exists()
    (PROJECT/'PROGRESS.md').rename(progress_source)
    alias(PROJECT/'PROGRESS.md', progress_source)

manifest_path = MACHINE/'目录迁移记录.json'
previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
manifest_path.write_text(json.dumps(previous + audit,ensure_ascii=False,indent=2)+'\n')

md = MarkdownIt('commonmark', {'html':False}).enable('table')
def relative_url(path, base=HUMAN): return quote(os.path.relpath(path, base), safe='/')
def write_view(rel, content):
    dst = HUMAN/rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content)
    return dst

def copy_document(source, dest, *, replace_status=None):
    src = PROJECT/source
    body = src.read_text()
    if replace_status:
        body = re.sub(r'^状态：.*$', replace_status, body, count=1, flags=re.M)
    dst = HUMAN/dest
    # The readable copies have a different directory, so relocate real Markdown links.
    def relocate(m):
        target = m.group(2)
        if '://' in target or target.startswith(('#','mailto:')): return m.group(0)
        path, sep, anchor = target.partition('#')
        p = Path(path) if path.startswith('/') else src.parent/path
        return '['+m.group(1)+']('+relative_url(p,dst.parent)+(('#'+anchor) if sep else '')+')'
    body = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', relocate, body)
    write_view(dest, body)
    return body

status_path=PROJECT/'keyframes/ep01/generation_status.json'
status=json.loads(status_path.read_text())
assets=json.loads((PROJECT/'assets/selected_registry.json').read_text())
masters=json.loads((PROJECT/'keyframes/ep01/master_generation.json').read_text())
shots_path=PROJECT/'keyframes/ep01/keyframe_generation.json'
shots=json.loads(shots_path.read_text()) if shots_path.exists() else []
chosen=[x for x in assets if x['status']=='selected']
chosen_masters=[x for x in masters if x['status']=='selected']
labels={'ep01_p2':'监狱饮水前主帧','ep01_p3':'监狱饮水后主帧','ep01_v1':'别墅主帧','ep01_r2':'客房主帧'}
todo=status.get('blocked_after_3_rounds',[])+status.get('needs_retry_round3',[])
todo_text='、'.join(labels.get(x,x) for x in todo) or '暂无记录中的待处理主帧'
video_count=len(list((PROJECT/'videos').rglob('*.mp4')))
shot_count=status['keyframes_completed']
progress_text=f'场次主帧已选{len(chosen_masters)}/6张；逐镜关键帧{shot_count}/38张；现有视频文件{video_count}个。'

story=copy_document('storyboard/ep01.md','01_分镜表/第01集.md',replace_status=
    f'状态：38镜分镜文本已完成；场次主帧已选{len(chosen_masters)}/6张，逐镜关键帧{status["keyframes_completed"]}/38张。')
documents=[('storyboard/style_bible.md','04_设定/画风与风格.md'),
           ('storyboard/characters.md','04_设定/人物档案.md'),
           ('storyboard/scenes.md','04_设定/场景设定.md'),
           ('storyboard/ep01_review.md','05_审阅与验收/第01集_台词核对.md'),
           ('keyframes/ep01/keyframe_prompts_ep01.md','05_审阅与验收/第01集_关键帧提示词.md'),
           ('keyframes/ep01/master_prompts_ep01.md','05_审阅与验收/第01集_主帧提示词.md'),
           ('keyframes/ep01/master_review.md','05_审阅与验收/第01集_图片验收记录.md')]
for src, dst in documents: copy_document(src,dst)

images=[]
for x in chosen:
    category='人物' if '三视图' in x['id'] else '场景'
    source=ROOT/x['path'];dest=HUMAN/'02_已选图片'/category/(x['id']+source.suffix)
    alias(dest,source)
    images.append({'title':x['id'],'path':dest,'group':category,'note':x.get('evidence',''),'status':'已选'})
for x in masters:
    source=ROOT/x['path']
    picked=x['status']=='selected'
    category='场次主帧' if picked else '待处理'
    label='备选' if x['status']=='alternate' else ('已选' if picked else ('待审查' if x['status']=='pending_review' else '未通过'))
    dest=HUMAN/('02_已选图片/第01集_场次主帧' if picked else '03_待处理图片/第01集')/source.name
    alias(dest,source)
    images.append({'title':x['id']+f' · 候选{x["candidate"]:02d}', 'path':dest,'group':category,
                   'note':x.get('review_zh',''),'status':label})

for x in shots:
    source=ROOT/x['path']; picked=x['status']=='selected'
    category='逐镜关键帧' if picked else '待处理'
    label='已选' if picked else ('待审查' if x['status']=='pending_review' else '未通过')
    dest=HUMAN/('02_已选图片/第01集_关键帧' if picked else '03_待处理图片/第01集_关键帧')/source.name
    alias(dest,source)
    images.append({'title':x['id']+f' · 候选{x["candidate"]:02d}', 'path':dest,'group':category,'note':x.get('review_zh',''),'status':label})
if (PROJECT/'keyframes/ep01/keyframes.md').exists():
    copy_document('keyframes/ep01/keyframes.md','05_审阅与验收/第01集_关键帧登记.md')

write_view('03_待处理图片/说明.md','''# 待处理图片

这里只收录未通过和备选候选，不属于已选素材。图片对应的具体问题可在阅读首页的“待处理图片”筛选中查看。
三轮到限不代表通过；这些图片不会混进“已选图片”。
''')
write_view('进度.md',f'''# 当前制作进度

- 第1集：38镜分镜文本已完成，预计253秒。
- 场次主帧：已选 {len(chosen_masters)}/6 张。
- 逐镜关键帧：{shot_count}/38 张；现有视频文件{video_count}个。
- 关键帧候选：{status.get('keyframe_image_count', len(shots))} 张；到限未通过 {status.get('keyframe_unit_counts', {}).get('capped', 0)} 镜；依赖主帧阻塞 {status.get('keyframe_unit_counts', {}).get('blocked_dependency', 0)} 镜。
- 主帧待处理：{todo_text}。具体问题见验收记录。
- 下一步：{status.get('next_step', '以关键帧登记为准')}。

[查看关键帧登记](05_审阅与验收/第01集_关键帧登记.md) · [查看主帧验收记录](05_审阅与验收/第01集_图片验收记录.md)。历史已选资产与本轮新生成主帧分开统计。
''')

navigation='''# 《出狱后我成为了非洲矿王》v3 · 阅读入口

**先打开 [阅读首页.html](阅读首页.html)**：可以直接看第1集分镜、筛选人物／场景／主帧图片，并查看待处理图片的问题。

| 你想看什么 | 打开这里 |
|---|---|
| 第1集分镜表 | [第01集](01_分镜表/第01集.md) |
| 已选图片 | [人物](02_已选图片/人物/) · [场景](02_已选图片/场景/) · [第1集场次主帧](02_已选图片/第01集_场次主帧/) · [第1集关键帧](02_已选图片/第01集_关键帧/) |
| 尚未通过的图片 | [待处理图片](03_待处理图片/) |
| 画风、人物和场景设定 | [设定](04_设定/) |
| 提示词审阅、台词核对、图片验收 | [审阅与验收](05_审阅与验收/) |
| 做到哪一步 | [当前进度](进度.md) |

逐镜关键帧尚未生成，现有的“场次主帧”不能当作38镜已经完成。
'''
if (HUMAN/'子代理进度.md').exists(): navigation += '\n[查看子代理实际进度](子代理进度.md)\n'
write_view('README.md',navigation.replace('逐镜关键帧尚未生成，现有的“场次主帧”不能当作38镜已经完成。',progress_text+' 场次主帧与逐镜关键帧分别统计。'))
cards=[]
for x in images:
    src=relative_url(x['path']);title=html.escape(x['title']);note=html.escape(x['note']);group=html.escape(x['group'])
    cards.append(f'<article class="card" data-group="{group}" data-search="{title}"><a href="{src}" target="_blank" rel="noopener"><img loading="lazy" src="{src}" alt="{title}"></a><div><span class="badge">{html.escape(x["status"])} · {group}</span><h3>{title}</h3><p>{note}</p></div></article>')

page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>非洲矿王 v3 · 分镜与图片</title><style>
:root{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;color:#262d2c;background:#f4f3ef}body{margin:0}header,main{max-width:1380px;margin:auto;padding:28px}h1{font-size:clamp(25px,4vw,42px);margin:8px 0}h2{margin-top:0}p{line-height:1.7}.sub{color:#64706a}nav,.tools{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}a{color:#276150}button,.link{padding:10px 16px;border:1px solid #d5d9d4;border-radius:8px;background:white;color:#264c40;text-decoration:none;font:inherit;cursor:pointer}button.active{background:#264c40;color:#fff}.stats{display:flex;flex-wrap:wrap;gap:15px}.stats div{background:#fff;border-radius:12px;padding:18px 24px;min-width:170px}.stats strong{font-size:27px;display:block}.notice{border-left:4px solid #a7763b;background:#fff6e6;padding:12px 18px;margin:20px 0}section{margin:20px 0 45px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:18px}.card{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px #00000009}.card img{width:100%;height:320px;object-fit:contain;background:#e8e7e2}.card>div{padding:16px}.card h3{font-size:16px;overflow-wrap:anywhere}.card p{font-size:13px;color:#66706a}.badge{font-size:12px;color:#55725e}input{padding:10px 12px;border:1px solid #cbd2ca;border-radius:8px;min-width:240px;font:inherit}.sheet{overflow:auto;background:white;border-radius:12px;padding:22px}.sheet table{border-collapse:collapse;min-width:950px;font-size:14px}.sheet td,.sheet th{border:1px solid #dfe3dc;padding:11px;vertical-align:top;min-width:90px}.sheet th{background:#e8eee8;position:sticky;top:0}.sheet table:last-of-type td:nth-child(6){min-width:280px}.sheet table:last-of-type td:nth-child(10){min-width:200px}.sheet td:nth-child(n+11),.sheet th:nth-child(n+11){display:none}.sheet.full td,.sheet.full th{display:table-cell}.sheet code{white-space:normal}.empty{padding:24px;color:#66706a}[hidden]{display:none!important}footer{padding:24px;color:#64706a}
</style><header><div class="sub">制作阅读页 · 第1集</div><h1>出狱后我成为了非洲矿王 <small>v3</small></h1><p class="sub">分镜、图片和当前进度集中在这里。点击图片可打开原尺寸文件。</p>
<div class="stats"><div><strong>38 镜</strong>分镜文本完成 · 预计253秒</div><div><strong>MASTER_COUNT / 6</strong>场次主帧已选</div><div><strong>SHOT_COUNT / 38</strong>逐镜关键帧已通过审查</div></div>
<nav><a class="link" href="#story">看分镜</a><a class="link" href="#pictures">看图片</a><a class="link" href="04_%E8%AE%BE%E5%AE%9A/">看设定</a><a class="link" href="05_%E5%AE%A1%E9%98%85%E4%B8%8E%E9%AA%8C%E6%94%B6/">审阅与验收</a><a class="link" href="%E8%BF%9B%E5%BA%A6.md">当前进度</a></nav>
<div class="notice">主帧还剩3项待处理：监狱饮水前／后水瓶持握、别墅提包手。未通过图片单列；当前没有完成的逐镜关键帧或视频。</div></header><main>
<section id="pictures"><h2>图片</h2><div class="tools" id="filters"><button class="active" data-filter="已选">全部已选</button><button data-filter="人物">人物</button><button data-filter="场景">场景</button><button data-filter="场次主帧">第1集主帧</button><button data-filter="逐镜关键帧">第1集关键帧</button><button data-filter="待处理">待处理图片</button><input id="search" type="search" placeholder="查找角色、场景或镜号" aria-label="查找图片"></div><p id="count" class="sub" aria-live="polite"></p><div class="grid">CARDS</div></section>
<section id="story"><h2>第1集 · 分镜表</h2><p>默认展示主要阅读列，可横向滚动。<button id="columns">显示全部18列</button> <a href="01_%E5%88%86%E9%95%9C%E8%A1%A8/%E7%AC%AC01%E9%9B%86.md">打开完整 Markdown 分镜表</a></p><div class="sheet">STORY</div></section>
<footer>已选图片保留历史／本轮验收依据。场次主帧与逐镜关键帧分别统计。</footer></main><script>
let filter='已选';const cards=[...document.querySelectorAll('.card')];function update(){const q=document.querySelector('#search').value.toLowerCase();let n=0;for(const c of cards){const ok=(filter==='已选'?c.dataset.group!=='待处理':c.dataset.group===filter)&&c.dataset.search.toLowerCase().includes(q);c.hidden=!ok;if(ok)n++}document.querySelector('#count').textContent=`当前显示 ${n} 张图片`;}document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));update()}));document.querySelector('#search').addEventListener('input',update);document.querySelector('#columns').addEventListener('click',e=>{const full=document.querySelector('.sheet').classList.toggle('full');e.target.textContent=full?'收起技术列':'显示全部18列'});update();
</script></html>'''
page=page.replace('主帧还剩3项待处理：监狱饮水前／后水瓶持握、别墅提包手。未通过图片单列；当前没有完成的逐镜关键帧或视频。',html.escape('待处理：'+todo_text+'。未通过图片单列。'+progress_text))
page=page.replace('MASTER_COUNT',str(len(chosen_masters))).replace('SHOT_COUNT',str(shot_count)).replace('CARDS',''.join(cards)).replace('STORY',md.render(story))
if (HUMAN/'子代理进度.md').exists(): page=page.replace('</nav>', '<a class="link" href="'+relative_url(HUMAN/'子代理进度.md')+'">子代理进度</a></nav>', 1)
write_view('阅读首页.html',page)

(PROJECT/'README.md').write_text('''# 《出狱后我成为了非洲矿王》v3

## 给人看

**[打开阅读首页：直接看分镜和图片](给人看/阅读首页.html)**

也可以打开 [阅读目录](给人看/README.md)，按分镜表、已选图片、待处理图片、设定、审阅和进度查找。

## 机器文件

[机器文件](机器文件/) 保存原始制作数据、JSON任务、卡片、生成日志与全部候选原档。
旧 storyboard、assets、keyframes 路径是兼容入口，原脚本和图片引用继续有效。
''')
(MACHINE/'README.md').write_text('''# 机器工作目录

- 制作过程/storyboard：分镜源稿、原文提取和编辑数据。
- 制作过程/assets：素材源文件、选图登记、任务JSON与生成日志。
- 制作过程/keyframes：主帧／逐镜卡片、派生任务、审批、审查和全部候选。
- 制作进度源.md、项目说明_原始.md：机器读取的进度与原项目说明。
- 目录迁移记录.json：移动记录及原文件校验数量。

旧路径由项目根目录的兼容链接保留；更新源文件后运行本目录的刷新阅读入口.py，刷新给人看的文档与图库。
给人看中的Markdown和HTML是阅读副本；图片引用同一原图，不复制大图片，不把失败候选列为已选。
''')
build_record=MACHINE/'阅读入口构建记录.json'
old_build=json.loads(build_record.read_text()) if build_record.exists() else {}
managed_aliases=[str(x['path'].relative_to(HUMAN)) for x in images]
for stale in set(old_build.get('managed_aliases',[]))-set(managed_aliases):
    f=HUMAN/stale
    if f.is_symlink(): f.unlink()
summary={'selected_assets':len(chosen),'selected_masters':len(chosen_masters),'other_master_candidates':len(masters)-len(chosen_masters),'gallery_images':len(images),'migrations':audit,'managed_aliases':managed_aliases}
(MACHINE/'阅读入口构建记录.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='managed_aliases'},ensure_ascii=False,indent=2))
