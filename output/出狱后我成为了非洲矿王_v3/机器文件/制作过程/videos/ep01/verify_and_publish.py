"""Read-only checks on cards/images; write local preparation reports, never submit jobs."""
import hashlib, html, importlib.util, json, re
from collections import Counter
from pathlib import Path

ROOT=Path('/workspaces/AI-')
PROJECT=ROOT/'output/出狱后我成为了非洲矿王_v3'
OUT=PROJECT/'videos/ep01'
HUMAN=PROJECT/'给人看/06_视频提示词'
spec=importlib.util.spec_from_file_location('builder',ROOT/'.agents/skills/short-drama-video-gen/scripts/build_prompt.py')
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
cards=json.loads((OUT/'shot_cards.json').read_text())
blocked=json.loads((OUT/'blocked_shot_cards.json').read_text())
jobs=json.loads((OUT/'video_jobs.json').read_text())
rows=json.loads((OUT/'storyboard_snapshot.json').read_text())
allcards=sorted(cards+blocked,key=lambda c:(c['shot_no'],c.get('unit_index',c.get('planned_unit_index',[1]))[0]))
byid={c['id']:c for c in cards}
assert len(byid)==len(cards)
assert set(c['shot_no'] for c in allcards)==set(range(1,39))
source=(PROJECT/'storyboard/script_source.txt').read_text().split('第 1 集 远渡重洋',1)[1].split('第 2 集',1)[0]
original_lines=re.findall(r'^(?:陈野|江砚(?: OS)?|苏慧|刘兰|顾瑶)(?:（.*?）)?：(.+)$',source,re.M)
assert len(original_lines)==21,len(original_lines)
dialogue_coverage=[]
for n,row in enumerate(rows,1):
    expected=row['台词/旁白'].split('：',1)[1] if row['台词/旁白']!='无' else ''
    actual=''.join(b['dialogue']['text_zh'] for c in allcards if c['shot_no']==n for b in c['beats'] if b.get('dialogue'))
    assert expected==actual,(n,expected,actual)
    dialogue_coverage.append({'shot_no':n,'exact_match':True,'text_zh':actual})
assert ''.join(original_lines)==''.join(x['text_zh'] for x in dialogue_coverage),'Original script dialogue mismatch'
assert [j['id'] for j in jobs]==[c['id'] for c in cards]
groups={}
for c in cards:
    if c.get('unit_of'): groups.setdefault(c['unit_of'],[]).append(c)
errors=[]; warnings=[]; token_counts=[]; observed=[]; dependencies=[]; speech=[]
for i,(c,j) in enumerate(zip(cards,jobs)):
    err,warn,prompt,tokens=builder.check_card(c,i,'en',None,groups,str(OUT.resolve()))
    errors.extend(err); warnings.extend(warn); token_counts.append(tokens)
    assert j==builder.card_to_job(c,prompt,'en'),c['id']
    assert (OUT/'prompts'/f"{c['id']}.txt").read_text()==prompt+'\n'
    assert 4<=c['duration_sec']<=8.05
    assert c['num_frames']%8==1 and c['width']%64==c['height']%64==0
    assert abs(c['duration_sec']-c['num_frames']/24)<.000001
    if c.get('first_frame'):
        p=Path(c['first_frame']); assert p.is_file(),p
        assert c['first_frame_state_basis']=='observed_selected_image'
        observed.append({'shot_no':c['shot_no'],'path':str(p.relative_to(ROOT)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'viewed_during_preparation':True})
    if c.get('first_frame_from'):
        prev=c['first_frame_from'].removesuffix(':last'); assert prev in byid
        assert byid[prev]['shot_no']==c['shot_no']
        assert byid[prev]['unit_index'][0]+1==c['unit_index'][0]
        dependencies.append({'unit':c['id'],'previous_unit':prev,'status':'not_generated'})
    for b in c['beats']:
        if b.get('dialogue'):
            minimum,count=builder.dialogue_min_duration(b['dialogue']['text_zh'],b['dialogue']['pace'])
            span=b['t'][1]-b['t'][0]; assert span+.000001>=minimum
            speech.append({'unit':c['id'],'text':b['dialogue']['text_zh'],'characters':count,'pace':b['dialogue']['pace'],'minimum_sec':round(minimum,3),'allocated_sec':round(span,3),'onscreen':b['dialogue']['onscreen']})
assert not errors,errors
assert len(observed)==38 and len(dependencies)==11
assert len(warnings)==11 and all('首帧还没落地' in w for w in warnings)
assert len(blocked)==1 and blocked[0]['id']=='ep01_镜16_u2'
# A conditional preview is mechanically rendered, but deliberately not validated or added to video_jobs.json.
draftdir=OUT/'blocked_prompts'; draftdir.mkdir(exist_ok=True)
for c in blocked: (draftdir/f"{c['id']}.txt").write_text(builder.build_prompt(c)+'\n')

summary={'episode':'ep01','scope':'prompt_preparation_only','original_shots':38,
    'compiled_units':len(cards),'conditional_draft_units':len(blocked),'planned_total_units':len(allcards),
    'selected_first_frames_viewed_and_existing':len(observed),'unmaterialized_tail_dependencies':len(dependencies),
    'original_script_dialogue_lines':len(original_lines),'original_dialogue_exact_match':True,
    'source_duration_sec':sum(float(r['时长(秒)']) for r in rows),
    'planned_generation_duration_sec':round(sum(c['duration_sec'] for c in allcards),3),
    'compiled_generation_duration_sec':round(sum(c['duration_sec'] for c in cards),3),
    'lint_errors':len(errors),'lint_warnings':len(warnings),'max_estimated_prompt_tokens':max(token_counts),
    'tokenizer_check':'heuristic_only_no_local_Gemma_tokenizer',
    'all_jobs_identical_to_card_builder':True,'video_generation_started':False,'gpu_requested':False,
    'production_batch_ready':False,'resolution':[576,1024],'fps':24}
audit={'summary':summary,'warnings':warnings,'dialogue_by_shot':dialogue_coverage,'speech_timing':speech,
    'first_frame_manifest':observed,'tail_dependencies':dependencies}
(OUT/'preparation_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
manifest={'scope':'preparation_only','production_batch_ready':False,
    'blocking_reasons':['ep01_镜16_u2 缺副驾补机位首帧；未进入 video_jobs.json。','11 个续段须先生成前段、看尾帧、回填镜头卡再装配。','命中 A1 的混合表情台词镜须先通过替代管线预检和小样；本包未验证 DFR 效果。'],
    'units':[{'id':c['id'],'shot_no':c['shot_no'],'duration_sec':c['duration_sec'],
        'readiness':c['readiness'],'first_frame_from':c.get('first_frame_from'),'included_in_video_jobs':c in cards} for c in allcards]}
(OUT/'execution_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

intro=f'''# 第1集图生视频提示词准备

第1集 **38 镜全部纳入，规划 50 个生成单元**：49 个镜头卡已通过装配校验，另 1 个为待补首帧的条件草案。38 张已选图已逐张看过；原剧本 21 条对白/旁白按分镜拆开再拼接，逐字一致。

当前只有提示词，没有生成视频。沿用 LTX-2.5，先列 576×1024 测试档、24 fps、首帧强度 1.0；不是正式分辨率成片。本页卡片状态与 [执行条件清单](../../videos/ep01/execution_manifest.json) 一起交给后续环节。

原分镜预计 253 秒；本次完整生成单元预算约 **{summary['planned_generation_duration_sec']:.2f} 秒**（约 4 分 35 秒），包含拆段停顿及动作余量，最终剪辑可裁掉多余停留。每单元 {min(c['duration_sec'] for c in allcards):.2f}–{max(c['duration_sec'] for c in allcards):.2f} 秒。

- **镜16上车片段缺首帧**：已选图只露车身边缘，不能当成副驾车门与座椅已经可见。u1 写到盖瓶、走到车旁；u2 保留开门、坐下后说“去顾家接我妈走。”的完整草案，放在 blocked 文件，未混入可装配任务。
- **11 个续段等待上一段尾帧**：这些是计划依赖，不是假装已存在的图片；生成后看尾帧、回填卡片，再装配下一段。
- **混合情绪台词镜保留原演法**：强笑仍是强笑，忍让仍是忍让。根据仓库旧管线 A1 记录，相关卡暂停 distilled 批量提交，交接方案为 DFR 预检后先试镜24；DFR 是否改善尚未实测。本次没有切管线或启动测试。
- **已选图中的连戏差异仍明示**：镜08持瓶手序，25→26→32拿包手，33→34→35拉箱手遮挡。后续可用切点遮开或补画面，提示词不宣称这些问题已修复；不翻转已选图。

## 文件与校验

- [镜头卡：维护入口](../../videos/ep01/shot_cards.json)
- [49个装配任务](../../videos/ep01/video_jobs.json)
- [镜16待补草案卡](../../videos/ep01/blocked_shot_cards.json)
- [校验记录](../../videos/ep01/preparation_audit.json)：0错误，11条续段依赖提示；最大提示词估算 {summary['max_estimated_prompt_tokens']} token，尚未使用 Gemma tokenizer 精确计数。
- [逐单元英文提示词](../../videos/ep01/prompts/)；正文英文，台词保持中文。

维护规则：只改镜头卡，运行 skill 的 build_prompt.py 重新装配，不能单独手改 video_jobs.json 的 prompt。条件草案未计入“校验通过”。

## 连戏与声音交接

监狱01–16：已打开的门继续出狱→单次拍肩→水瓶转入江砚左手→05只局部旋盖后停住→09开盖、喝一口、吞咽后说话→15只拍腿一次→16盖瓶走向车旁，副驾动作另补首帧。13/14同角度近景以停顿与摇头衔接。瓶盖从09起保持分离，16才重新盖上。

机场17–25：以“一个月前”闪回，17已在门外不重复出门，18只走完最后一小步，20不再走近；成年江砚的回望旁白与年轻江砚当时的心疼区分。22安排纸收入袋、暂放箱杆、背包交接，母亲左手拿包、儿子右手箱杆；24从手已擦到眼角继续，不再抬手。25沿首帧纵深方向离开。纸入袋是道具转移方案，原剧本没有该独立动作。

客厅26–34：母子站、主人坐的高低关系贯穿；27检查指甲，29吹一次，31扫视嗤笑一次，32不重复；33从松搭的右指渐次攥紧。34母亲手已贴背，继续引导到楼梯旁过道，不上楼。原分镜重复动作及25离场方向调整已登记在卡片 notes。

客房35–38：保持白天；35关门后放包、停箱、入座，接36已关门、母亲双手叠腹、儿子坐姿的状态。桌/床脚部分处于画外，先检查动作空间，受阻则补宽镜。37闭嘴听劝，38点头后答话，只推到肩上特写便停止。

五个角色的声音描述各自统一，但 LTX 跨单元音色一致性尚无本批证据。画外音标记已填写，人物反应镜闭嘴；32里的顾瑶是背景人物，需避免背景可读嘴型与画外声错位。对话先保清晰度，低配器 BGM 后期添加，避免每段独立生成配乐导致切点断裂。机场风/车流、监狱干风、室内底噪在镜头卡中分别声明；“一个月前”字卡在剪辑层添加。

## 后续执行顺序

先解决镜16补机位；A1镜先做替代管线预检，再以24强笑、09喝水、22交包、33攥箱杆作为小样关注点。通过后才扩展同类，续段必须按依赖顺序。完成提示词审阅后由 short-drama-ltx-export 做实际路径与配置校验，再交 short-drama-ltx-generate 执行与验收。本次未调用任何提交或显卡脚本。

## 逐镜索引

|镜号|单元|原分镜秒数|生成预算秒数|叙事目标|
|---|---|---:|---:|---|
'''
for n,row in enumerate(rows,1):
    group=[c for c in allcards if c['shot_no']==n]
    intro+=f"|{n:02}|{'、'.join(c['id'].replace('ep01_镜','') for c in group)}|{row['时长(秒)']}|{sum(c['duration_sec'] for c in group):.2f}|{group[0]['intent_zh']}|\n"
md=intro+'\n## 完整提示词与首帧状态\n'
for c in allcards:
    isblocked=c in blocked
    p=builder.build_prompt(c)
    group='blocked_prompts' if isblocked else 'prompts'
    md+=f"\n### {c['id']} · {c['duration_sec']:.2f}秒"+(' · 待补首帧条件草案' if isblocked else '')+'\n\n'
    md+=f"目标：{c['intent_zh']}\n\n起点：{c['first_frame_state_zh']}\n\n"
    if c.get('first_frame'): md+=f"[已选首帧](../02_已选图片/第01集_关键帧/{Path(c['first_frame']).name})\n\n"
    if c.get('first_frame_from'): md+=f"首帧依赖：`{c['first_frame_from']}`。\n\n"
    md+=f"[英文提示词文件](../../videos/ep01/{group}/{c['id']}.txt)\n\n```text\n{p}\n```\n\n交接：{c['notes']}\n"
(HUMAN/'第01集_视频提示词.md').write_text(md)
# Standalone local browser view with one selected image per original shot and searchable unit cards.
esc=html.escape
sections=[]
for n,row in enumerate(rows,1):
    group=[c for c in allcards if c['shot_no']==n]
    img=group[0].get('first_frame')
    pic=f'<img loading="lazy" src="../02_已选图片/第01集_关键帧/{esc(Path(img).name)}" alt="镜{n:02}已选首帧">' if img else ''
    body=f'<section><h2>镜 {n:02} · {esc(group[0]["intent_zh"])}</h2>{pic}'
    for c in group:
        status='待补副驾首帧 · 条件草案' if c in blocked else '等待上一段尾帧' if c.get('first_frame_from') else '首帧已存在'
        if c['readiness'].get('pipeline_gate'): status+=' · 需 A1 管线预检'
        body+=f'<article><h3>{esc(c["id"])} · {c["duration_sec"]:.2f}秒</h3><p class="status">{status}</p><p>{esc(c["first_frame_state_zh"])}</p><details><summary>查看英文提示词（中文原台词）</summary><pre>{esc(builder.build_prompt(c))}</pre></details><p class="note">{esc(c["notes"])}</p></article>'
    sections.append(body+'</section>')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>第01集视频提示词</title><style>body{font:16px/1.65 system-ui,sans-serif;margin:auto;padding:24px;max-width:1100px;background:#f5f4ef;color:#232b31}h1{font-size:28px}section{background:white;border-radius:12px;margin:22px 0;padding:22px;display:flow-root}img{width:180px;float:left;margin:0 22px 20px 0}article{overflow:hidden;border-bottom:1px solid #ddd;padding:8px 0 16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eff2f4;padding:16px}summary{cursor:pointer;color:#175d83}.status{color:#94620e}.note{font-size:14px;color:#555}input{box-sizing:border-box;width:100%;padding:12px;font:inherit;position:sticky;top:8px}a{color:#175d83}@media(max-width:600px){body{padding:12px}section{padding:14px}img{float:none;width:130px}h2{font-size:20px}}</style><h1>第1集 · 视频提示词</h1><p>38镜 / 50个规划单元；49个通过文本装配，镜16上车片段待补首帧。11个续段等待尾帧。仅准备提示词，尚未生成视频。</p><p><a href="第01集_视频提示词.md">完整制作交接与校验说明</a></p><input id="q" placeholder="搜索镜号、人物、台词或动作" aria-label="搜索镜头">'''+''.join(sections)+'''<script>document.getElementById('q').addEventListener('input',e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('section').forEach(s=>s.hidden=!s.textContent.toLowerCase().includes(q))})</script></html>'''
(HUMAN/'第01集_视频提示词.html').write_text(page)
readme='''# ep01 视频提示词产物

本目录仅为准备阶段。shot_cards.json 是当前维护入口；authoring/initial_cards.py 仅保存初次手工编排过程，后续已修改卡片，不要重跑覆盖。

49 张卡和 video_jobs.json 一一对应；镜16第二段在 blocked_shot_cards.json / blocked_prompts，不是可提交任务。完整制作方案共38镜、50单元。执行前必须读 execution_manifest.json 和给人看/06_视频提示词/第01集_视频提示词.md。

重装配（在仓库根目录）：

```bash
python3 .agents/skills/short-drama-video-gen/scripts/build_prompt.py output/出狱后我成为了非洲矿王_v3/videos/ep01/shot_cards.json --lint
python3 .agents/skills/short-drama-video-gen/scripts/build_prompt.py output/出狱后我成为了非洲矿王_v3/videos/ep01/shot_cards.json -o output/出狱后我成为了非洲矿王_v3/videos/ep01/video_jobs.json --emit-prompts output/出狱后我成为了非洲矿王_v3/videos/ep01/prompts
python3 output/出狱后我成为了非洲矿王_v3/videos/ep01/verify_and_publish.py
```

verify_and_publish.py 是本次38镜/50单元方案的本地复核与阅读页生成器；后续改变拆段方案时需相应更新计数断言。它只检查卡片/路径/台词和重建阅读页，不生成视频、不上传网站或云盘。
'''
(OUT/'README.md').write_text(readme)
print(json.dumps(summary,ensure_ascii=False,indent=2))
