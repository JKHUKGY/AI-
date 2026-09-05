"""Mechanically assemble same-shot edit jobs from source cards and review plans.

This script reads metadata and writes JSON only. Image editing is performed by
imagegen, never here. A candidate of another shot cannot be used as an edit target.
"""
import argparse,json,math
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[3]
P=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('plans');parser.add_argument('--ids',nargs='+',required=True)
parser.add_argument('--round',type=int,required=True);parser.add_argument('-o',required=True)
a=parser.parse_args()
if a.round not in (2,3):raise ValueError('Same-unit edits retain the second/third round budget')
d=json.loads((P/'keyframes/ep01/keyframe_cards.json').read_text());cards={c['id']:c for c in d['cards']};beats={b['id']:b for b in d['scene_beats']}
plans=json.loads(Path(a.plans).read_text());plans={p['id']:p for p in plans['plans']}
spec=importlib.util.spec_from_file_location('edit_job_validator',P/'机器文件/build_keyframe_jobs.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
out=[]
for ident in a.ids:
 c=cards[ident];p=plans[ident];target=Path(p['target_image']);target=target if target.is_absolute() else ROOT/target
 if not target.is_file() or not target.stem.startswith(ident+'_'):raise ValueError('Missing or cross-shot edit target')
 if not target.resolve().is_relative_to((P/'keyframes/ep01/_shots').resolve()):raise ValueError('Edit target outside same-shot candidate tree')
 errors,warnings,_=module.builder.check_card(c,0,str(ROOT),beats[c['beat_id']],True)
 if errors:raise ValueError(errors)
 if p['mode'] not in ('crop','local_reframe','directed_edit'):raise ValueError(f'{ident} has an unsupported edit mode')
 refs=[str(target.relative_to(ROOT))]
 for value in p.get('identity_references',[]):
  extra=Path(value);extra=extra if extra.is_absolute() else ROOT/extra
  if not extra.is_file() or not extra.resolve().is_relative_to((P/'assets').resolve()):raise ValueError('Identity reference must be an existing project asset')
  refs.append(str(extra.relative_to(ROOT)))
 if len(refs)>5:raise ValueError('Too many image references')
 parts=[f'编辑参考图1。这是镜头{ident}自己的现有候选，输出一张同一瞬间、同一人物、同一场景的竖屏9:16照片。']
 box=p.get('crop_box')
 if box:
  if len(box)!=4 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in box):raise ValueError('Invalid crop box')
  l,t,r,b=box
  if not (0<=l<r<=1 and 0<=t<b<=1):raise ValueError('Crop box out of bounds')
  parts.append(f'按原图归一化坐标裁切：左界{l:.3f}、上界{t:.3f}、右界{r:.3f}、下界{b:.3f}。将该区域等比例放大为新的竖屏9:16画幅；保持人脸与身体比例自然。')
 if p['mode']=='crop':parts.append('本次只收紧该原图的取景，不重新构造人物，不重新拍成完整身体；原图可见区域的身份、表情、衣物、光照和背景方向保持一致。')
 elif p['mode']=='directed_edit':parts.append('只修正下列计划明确指出的身份、姿态、持物或取景问题，其余内容按保留清单保持。')
 else:parts.append('只在收紧取景所需的局部范围调整前景肩缘，主要清晰人物的身份、表情、姿态及房间方向保持原图。')
 parts.extend(['【裁切修正】'+p['correction_zh'],'【必须保留】'+p['preserve_zh'], '【批准景别】'+c['framing']['shot_size']+'；'+c['framing']['crop_zh'],c['style_anchor_zh']])
 if p.get('prompt_variant')=='tight_reframe':
  edge={'left':'left','right':'right'}[p['foreground_edge']]
  subject=c['framing']['primary_subject']
  parts=[f'EDIT this photograph into a much tighter chest-up close-up of {subject}. Move the framing in strongly. The complete head from hair crown to chin fills HALF of the final image height. Place the hair crown only 5% below the TOP edge. Cut the BOTTOM edge across the UPPER CHEST. Keep the face proportions natural and preserve the exact facial expression and eye direction.',f'The blurred listener is almost entirely outside the {edge} edge: show only a thin sliver of hair and shoulder along the outermost 10-15% of that edge, including the bottom corner. The sharp face is dominant.',p['correction_zh'],p['preserve_zh'],'Keep the same photographic look, lighting and camera direction. Final image portrait 9:16.']
 if p.get('prompt_variant')=='edge_only':
  parts=['Make ONE localized edit to this photo. '+p['correction_zh'],'Preserve the sharp main person exactly: same face, expression, eye direction, hairstyle, clothes, scale and position. Preserve the current framing, lighting, and background camera direction. Keep 9:16.']
 if p.get('prompt_variant')=='composition_only':
  parts=['Edit this same photograph. '+p['correction_zh'],p['preserve_zh'],'Keep the same photographic style and lighting. Final portrait 9:16.']
 out.append({'id':ident,'prompt':'\n'.join(parts),'ref_images':refs,'count':a.round,'generation_round':a.round,'candidate_start':1 if a.round==2 else 3,'mode':'same_unit_edit','source_cards':str((P/'keyframes/ep01/keyframe_cards.json').relative_to(ROOT)),'source_edit_plan':str(Path(a.plans)),'script_ref_zh':c['script_ref_zh']})
Path(a.o).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'jobs':len(out),'images':sum(j['count'] for j in out),'round':a.round,'images_edited_by_script':0},ensure_ascii=False))
