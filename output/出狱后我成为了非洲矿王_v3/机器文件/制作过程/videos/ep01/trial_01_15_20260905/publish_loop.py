"""Publish independently selected test results; retain failed drafts and honest audio scope."""
import html,json,os,subprocess
from pathlib import Path
T=Path(__file__).resolve().parent;P=T.parents[4];H=P/'给人看/07_视频试片';H.mkdir(exist_ok=True)
units=json.loads((T/'units_queue.json').read_text());cards={c['id']:c for c in json.loads((T/'shot_cards.json').read_text())};esc=html.escape
selected=[];blocks=[];rows=[]
def link(path):return os.path.relpath(path,H)
for u in units:
 ident=u['id'];hist=u.get('history',[]);chosen=u.get('selected_test_file');display=chosen or (hist[-1]['video_file'] if hist else None)
 if not display or not Path(display).exists():continue
 if chosen:selected.append((ident,chosen))
 state='视觉抽帧通过' if chosen and u['status']!='capped' else '未通过，保留问题样片'
 rounds=u.get('round_count',0);c=cards[ident];dialogue=' / '.join(b['dialogue']['text_zh'] for b in c['beats'] if b.get('dialogue')) or '无台词'
 last=hist[-1] if hist else {};reasons=last.get('reason',[]);reasons=[reasons] if isinstance(reasons,str) else reasons
 details='；'.join(str(r) for r in reasons);src=link(display)
 poster=Path(last.get('frames_dir',str(Path(display).parent.parent/'review_frames'/ident)))/'contact.jpg'
 block=f'<section><h2>{esc(ident)} · {rounds}轮 · {state}</h2><video controls preload="metadata" src="{esc(src)}"></video><p>{esc(c["intent_zh"])}</p><p>原台词：{esc(dialogue)}</p><p>{esc(details)}</p>'
 if poster.exists():block+=f'<details><summary>查看本轮抽帧</summary><img loading="lazy" src="{esc(link(poster))}"></details>'
 block+='<details><summary>历轮结果</summary><ul>'
 for item in hist:block+=f'<li>第{item["round"]}轮 · {esc(item.get("verdict","pending"))} · <a href="{esc(link(item["video_file"]))}">播放样片</a></li>'
 block+='</ul></details></section>';blocks.append(block);rows.append(f'|[{ident}]({src})|{rounds}|{state}|{details.replace("|","/")}|')
preview=T/'第01集_镜01-15_循环筛选试片.mp4'
if len(selected)==20:
 concat=T/'concat_selected.txt';concat.write_text(''.join("file '"+str(p).replace("'","'\\''")+"'\n" for _,p in selected))
 r=subprocess.run(['ffmpeg','-v','warning','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(preview)],capture_output=True,text=True);(T/'concat_selected.log').write_text(r.stderr)
 if r.returncode:raise RuntimeError(r.stderr)
count=sum(u.get('generation_count',0) for u in units);passed=len(selected);capped=[u['id'] for u in units if u['status'].startswith('capped')]
intro=f'<h1>第1集 · 镜01—15循环试片</h1><p>15镜 / 20单元，累计生成{count}条视频；{passed}/20单元视觉抽帧通过。RunPod · LTX-2.5 · 576×1024 · 24fps。</p><p>这是测试档。对白内容、音色、语气和精确声画同步尚未听审；视觉通过不代表完整视听验收通过。</p>'
if preview.exists():intro+=f'<p><a href="{esc(link(preview))}">播放或下载筛选后串联试片</a></p><video controls preload="metadata" src="{esc(link(preview))}"></video>'
if capped:intro+='<p>达到上限仍有问题：'+esc('、'.join(capped))+'。问题样片不自动选为交付。</p>'
page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>镜01—15循环试片</title><style>body{font:16px/1.65 system-ui;margin:auto;max-width:1000px;padding:24px;background:#f2f2ee;color:#252b30}section{padding:20px;margin:20px 0;background:white;border-radius:12px}video{display:block;max-height:640px;max-width:100%;background:#111}img{width:100%}a{color:#176b91}h1{font-size:28px}h2{font-size:21px}</style>'+intro+''.join(blocks)+'</html>'
(H/'第01集_镜01-15_试片.html').write_text(page)
md=f'# 第1集镜01—15循环试片\n\n15镜拆20个单元；累计{count}次真实视频生成，{passed}/20单元视觉抽帧通过。576×1024测试档，24fps。\n\n[逐段播放和历轮对比](第01集_镜01-15_试片.html)\n\n'
if preview.exists():md+=f'[筛选后串联试片]({link(preview)})\n\n'
md+='|单元|生成轮数|视觉结论|证据/限制|\n|---|---|---|---|\n'+'\n'.join(rows)+'\n\n对白内容、音色、语气与精确声画同步尚未听审。抽帧通过范围仅为采样画面；原关键帧已有的手别等连戏差异仍列于审查记录。\n'
(H/'第01集_镜01-15_试片说明.md').write_text(md)
(T/'loop_summary.json').write_text(json.dumps({'units':20,'shots':15,'generation_count':count,'visual_passed':passed,'capped':capped,'test_resolution':[576,1024],'audio_review':'not_listened','selected':selected,'preview':str(preview) if preview.exists() else None},ensure_ascii=False,indent=2))
print({'generated':count,'visual_passed':passed,'capped':capped,'preview':preview.exists()})
