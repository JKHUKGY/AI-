"""Verify gallery completion and missing-shot provenance without altering images."""
from pathlib import Path
import json, hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
P=Path(__file__).resolve().parent.parent
M=P/'机器文件/多代理续做'
ROOT=Path('/workspaces/AI-')
def read(p):return json.loads(p.read_text())
def absolute(p):
 p=Path(p);return p if p.is_absolute() else ROOT/p
def digest(p):return hashlib.sha256(absolute(p).read_bytes()).hexdigest()
queue=read(M/'keyframe_units_queue.json')
roster=read(M/'roster_missing17_20260905.json')
manifest=read(M/'user_selected_candidates_20260905.json')
errors=[]
def check(ok,msg):
 if not ok:errors.append(msg)
check(len(queue)==38 and len({u['id'] for u in queue})==38,'Queue must contain 38 unique shots')
for u in queue:
 check(bool(u.get('selected_file')),u['id']+' has no selection')
 if u.get('selected_file'):check(absolute(u['selected_file']).is_file(),u['id']+' selection missing')
 check(not u.get('generation_in_progress'),u['id']+' remains active')
for item in manifest['selections']:
 check(digest(item['path'])==item['sha256'],item['id']+' selection hash mismatch')
gallery=P/'给人看/02_已选图片'
for folder,count in [('第01集_关键帧',38),('第01集_场次主帧',6)]:
 files=list((gallery/folder).glob('*.png'))
 check(len(files)==count,folder+' count incorrect')
 check(all(f.is_file() for f in files),folder+' has broken links')
records=[];generators={};rounds=defaultdict(Counter)
for f in M.glob('generator_missing17*.json'):
 d=read(f)
 for r in d.get('records',[]):
  path=str(absolute(r['path']).resolve())
  records.append(r);generators[path]=d['agent_id'];rounds[r['id']][r['round']]+=1
  check(digest(r['path'])==r['sha256'],path+' generated hash mismatch')
paths=[str(absolute(r['path']).resolve()) for r in records]
check(len(paths)==len(set(paths)),'Duplicate generated-image records')
reviews=defaultdict(set)
for f in M.glob('review_keyframes_missing17*.json'):
 d=read(f)
 for r in d.get('images',[]):
  path=str(absolute(r['path']).resolve());reviews[path].add(d['agent_id'])
for path in paths:
 check(len(reviews[path])>=2,path+' lacks two independent reviews')
 check(generators[path] not in reviews[path],path+' generator reviewed own image')
for ident in roster['scope']:
 check(ident in rounds,ident+' missing generation')
 for rnd,n in rounds[ident].items():
  interrupted = ident=='ep01_镜29' and rnd==2 and n==1 and (M/'missing17_29_generation_stop.json').is_file()
  check(rnd in (1,2,3) and (n==rnd or interrupted),ident+' wrong round count')
 check(sum(rounds[ident].values())<=6,ident+' exceeds generation budget')
actual_agents=set(generators.values())|set().union(*(reviews[p] for p in paths))
check(len(actual_agents)>=4,'Fewer than four substantive subagents')
scene_audits=[]
for scene in ['SC05','SC01']:
 f=M/f'selected_scene_continuity_missing17_{scene}.json'
 check(f.is_file(),scene+' final scene audit missing')
 if f.is_file():
  d=read(f);scene_audits.append(f.name)
  check(d.get('status')=='complete',scene+' final audit incomplete')
  if 'new_generation_requested' in d:check(d['new_generation_requested'] is False,scene+' audit requests unresolved generation')
  else:check(d.get('actions_taken',{}).get('reopened_capped_units') is False and d.get('final_shot33_update',{}).get('required') is False,scene+' audit has unresolved work')
report={'checked_at':datetime.now(timezone.utc).isoformat(),'complete':not errors,'errors':errors,
 'scene_audits':scene_audits,
 'selected_keyframes':sum(bool(u.get('selected_file')) for u in queue),
 'technical_passed':sum(u['status']=='passed' for u in queue),
 'user_selected':sum(u['status']=='selected_by_user' for u in queue),
 'missing_shot_images_generated':len(records),'rounds':dict(rounds),
 'generation_exceptions':[read(M/'missing17_29_generation_stop.json')],
 'actual_subagents':sorted(actual_agents),'peak_running_subagents':roster['peak_running_subagents']}
(M/'missing17_completion_verification_20260905.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
