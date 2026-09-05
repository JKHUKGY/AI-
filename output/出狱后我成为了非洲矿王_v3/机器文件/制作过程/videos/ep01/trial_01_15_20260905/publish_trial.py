"""Build a local review page for available trial videos; join only when all units exist."""
import html,json,subprocess
from pathlib import Path
OUT=Path(__file__).resolve().parent
PROJECT=OUT.parents[4]
HUMAN=PROJECT/'给人看/07_视频试片';HUMAN.mkdir(exist_ok=True)
results=json.loads((OUT/'generation_results.json').read_text()) if (OUT/'generation_results.json').exists() else []
reviews=json.loads((OUT/'visual_reviews.json').read_text()) if (OUT/'visual_reviews.json').exists() else {}
cards=json.loads((OUT/'shot_cards.json').read_text());byid={c['id']:c for c in cards}
relative='../../videos/ep01/trial_01_15_20260905'
esc=html.escape
blocks=[]
for r in results:
    ident=r['id'];c=byid[ident];review=reviews.get(ident,{})
    lines=' / '.join(b['dialogue']['text_zh'] for b in c['beats'] if b.get('dialogue')) or '本单元无台词'
    blocks.append(f'<section><h2>{esc(ident)} · {c["duration_sec"]:.2f} 秒</h2><video controls preload="metadata" poster="{relative}/review_frames/{esc(ident)}/contact.jpg" src="{relative}/clips/{esc(ident)}.mp4"></video><p>{esc(c["intent_zh"])}</p><p>原台词：{esc(lines)}</p><p>画面抽帧审阅：{esc(review.get("verdict_zh","待审阅"))}。{esc(review.get("notes_zh",""))}</p><p>声音：已检查音轨是否存在及响度；语句准确性、音色和精确口型仍需播放确认。</p><details><summary>查看5张抽帧</summary><img loading="lazy" src="{relative}/review_frames/{esc(ident)}/contact.jpg"></details><a download href="{relative}/clips/{esc(ident)}.mp4">下载本单元</a></section>')
preview=OUT/'第01集_镜01-15_试片串联.mp4'
if len(results)==20 and not preview.exists():
    concat=OUT/'concat.txt'
    concat.write_text(''.join("file '"+str(OUT/'clips'/(c['id']+'.mp4')).replace("'","'\\''")+"'\n" for c in cards))
    r=subprocess.run(['ffmpeg','-v','warning','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(preview)],capture_output=True,text=True)
    (OUT/'concat.log').write_text(r.stderr)
    if r.returncode:raise RuntimeError(r.stderr)
top='<h1>第1集 · 镜01—15试片</h1><p>RunPod / LTX-2.5 distilled · 576×1024 · 24 fps。15镜拆20个生成单元；下方展示当前已下载结果，均为单轮试片。</p>'
if preview.exists(): top+=f'<p><a href="{relative}/{preview.name}">播放或下载整段试片（按镜号串联）</a></p><video controls preload="metadata" src="{relative}/{preview.name}"></video>'
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>镜01—15视频试片</title><style>body{font:16px/1.65 system-ui,sans-serif;margin:auto;max-width:1000px;padding:24px;background:#f2f2ee;color:#252b30}section{padding:20px;margin:20px 0;background:white;border-radius:12px}video{display:block;max-height:640px;max-width:100%;background:#111}img{width:100%;height:auto}a{color:#176b91}details{margin:14px 0}h1{font-size:28px}h2{font-size:21px}</style>'''+top+''.join(blocks)+'</html>'
(HUMAN/'第01集_镜01-15_试片.html').write_text(page)
md=f'# 第1集镜01—15试片\n\n已下载 {len(results)}/20 单元。LTX-2.5 distilled，576×1024 测试档，24fps。\n\n[打开逐段播放器](第01集_镜01-15_试片.html)\n\n'
if preview.exists():md+=f'[按镜号串联试片]({relative}/{preview.name})\n\n'
md+='|单元|画面抽帧审阅|发现的问题|\n|---|---|---|\n'
for r in results:
    ident=r['id'];v=reviews.get(ident,{})
    md+=f'|[{ident}]({relative}/clips/{ident}.mp4)|{v.get("verdict_zh","待审阅")}|{v.get("notes_zh","")}|\n'
md+='\n抽帧只能检查采样时刻；音轨存在和响度不代表台词说对，台词内容、音色和精确同步需播放确认。已知首帧差异与本轮视频新问题分别记录。\n'
(HUMAN/'第01集_镜01-15_试片说明.md').write_text(md)
print({'downloaded':len(results),'visually_reviewed':len(reviews),'preview_exists':preview.exists(),'page':str(HUMAN/'第01集_镜01-15_试片.html')})
