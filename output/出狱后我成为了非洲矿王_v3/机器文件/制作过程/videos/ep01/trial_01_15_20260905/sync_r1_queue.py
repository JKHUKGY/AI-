import json
from pathlib import Path
T=Path(__file__).resolve().parent;q=json.loads((T/'units_queue.json').read_text());results={r['id']:r for r in json.loads((T/'generation_results.json').read_text())};reviews={r['id']:r for r in json.loads((T/'review_loop_r1_12_15.json').read_text())['reviews']};cards={c['id']:c for c in json.loads((T/'shot_cards.json').read_text())}
for u in q:
 ident=u['id']
 if ident not in results or u.get('round_count',0)>1:continue
 u['round_count']=u['generation_count']=1
 if ident not in reviews:continue
 r=reviews[ident];u['status']='test_visual_reviewed' if r['verdict']=='pass' else 'pending_retry';u['selected_test_file']=results[ident]['local_video'] if r['verdict']=='pass' else None
 u['history']=[{'round':1,'seed':cards[ident]['seed'],'video_file':results[ident]['local_video'],'frames_dir':str(T/'review_frames'/ident),'verdict':r['verdict'],'action_class':'retain_visual_result' if r['verdict']=='pass' else 'mandatory_retry','reason':[r['reason_zh']],'fix_instruction':r.get('fix_instruction'),'defect_window':r.get('defect_window'),'review_file':str(T/'review_loop_r1_12_15.json')}]
(T/'units_queue.json').write_text(json.dumps(q,ensure_ascii=False,indent=2))
print([(u['id'],u['round_count'],u['status']) for u in q[-7:]])
