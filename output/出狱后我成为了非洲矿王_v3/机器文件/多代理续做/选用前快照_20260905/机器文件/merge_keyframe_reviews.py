"""Rebuild keyframe registers from persisted candidates and independent reviews."""
from pathlib import Path
from collections import Counter, defaultdict
import json
import os
import re

ROOT = Path('/workspaces/AI-')
PROJECT = Path(__file__).resolve().parent.parent
MACHINE = PROJECT / '机器文件/多代理续做'
KF = PROJECT / 'keyframes/ep01'

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temp, path)

def key(path):
    p = Path(path)
    return str((p if p.is_absolute() else ROOT / p).resolve())

def rel(path):
    return str(Path(path).absolute().relative_to(ROOT))

def entries(value):
    if isinstance(value, list):
        for item in value:
            yield from entries(item)
    elif isinstance(value, dict):
        if value.get('path') and ('candidate' in value or 'verdict' in value):
            yield value
        for name in ('records', 'images', 'results', 'jobs', 'files'):
            if isinstance(value.get(name), (list, dict)):
                yield from entries(value[name])

old = {key(x['path']): x for x in read(KF / 'keyframe_generation.json')}
generators = defaultdict(list)
for report in sorted(MACHINE.glob('generator*.json')):
    data = read(report)
    if not isinstance(data, dict) or not data.get('agent_id'):
        continue
    for item in entries(data):
        if item.get('path') and item.get('source'):
            generators[key(item['path'])].append((data['agent_id'], rel(report), item))

reviews = defaultdict(dict)
recommendations = defaultdict(list)
for report in sorted(MACHINE.glob('review_keyframes_*.json')):
    data = read(report)
    agent = data.get('agent_id')
    if not agent:
        continue
    for item in data.get('capped_recommendation', []) + data.get('unit_summaries', []):
        if item.get('best_candidate'):
            recommendations[item['id']].append(dict(item, remaining_difference=item.get('remaining_difference', item.get('reason', '')), agent_id=agent, report=rel(report)))
    for ident, item in data.get('best_candidates', {}).items():
        if isinstance(item, dict) and item.get('path'):
            recommendations[ident].append(dict(item, id=ident, best_candidate=item['path'], agent_id=agent, report=rel(report)))
    for item in data.get('images', []):
        if item.get('path') and item.get('verdict') in ('pass', 'fail'):
            k = key(item['path'])
            # Preserve every independent verdict, including disagreements.
            reviews[k][(agent, rel(report))] = dict(item, agent_id=agent, report=rel(report))

candidates = []
for png in sorted((KF / '_shots').glob('*/*.png')):
    k = key(png)
    meta = png.with_suffix('.json')
    item = dict(old.get(k, {}))
    if meta.exists():
        item.update(read(meta))
    index = int(png.stem.rsplit('_', 1)[1])
    item.update(id=png.parent.name, path=rel(png), candidate=index,
                round=1 if index == 0 else 2 if index < 3 else 3)
    matches = generators[k]
    if matches:
        ids = {m[0] for m in matches}
        if len(ids) != 1:
            item['generator_provenance_conflict'] = sorted(ids)
        else:
            item['generator_agent_id'], item['generator_report'], record = matches[-1]
            item['source'] = record['source']
            item.pop('generator_provenance_conflict', None)
    independent = [r for r in reviews[k].values()
                   if r['agent_id'] != item.get('generator_agent_id')]
    item['independent_reviews'] = independent
    complete = len({r['agent_id'] for r in independent}) >= 2
    passed = complete and all(r['verdict'] == 'pass' for r in independent)
    item['status'] = 'approved_candidate' if passed else 'rejected' if complete else 'pending_review'
    item['review_zh'] = '；'.join(dict.fromkeys(r.get('reason', '') for r in independent))
    candidates.append(item)

queue = read(MACHINE / 'keyframe_units_queue.json')
by_id = defaultdict(list)
for item in candidates:
    by_id[item['id']].append(item)
for unit in queue:
    items = by_id[unit['id']]
    unit['candidates'] = [x['path'] for x in items]
    unit['generation_in_progress'] = False
    if unit.get('dependency') and not items:
        unit['status'] = 'blocked_dependency'
        continue
    passed = [x for x in items if x['status'] == 'approved_candidate']
    unit['selected_file'] = ''
    if passed:
        chosen = next((x for x in passed if old.get(key(x['path']), {}).get('status') == 'selected'), passed[0])
        chosen['status'] = 'selected'
        unit.update(status='passed', selected_file=chosen['path'])
        for x in passed:
            if x is not chosen:
                x['status'] = 'alternate'
    elif any(x['status'] == 'pending_review' for x in items):
        unit['status'] = 'pending_review'
    elif len(items) >= 6:
        unit['status'] = 'capped'
    else:
        unit['status'] = 'needs_retry'
    completed = 0
    for round_no, count in ((1, 1), (2, 2), (3, 3)):
        group = [x for x in items if x['round'] == round_no]
        if len(group) == count and all(x['status'] != 'pending_review' for x in group):
            completed = round_no
        else:
            break
    unit['completed_rounds'] = completed
    unit['active_round'] = max((x['round'] for x in items), default=0)
    unit['history'] = [dict(round=r, files=[x['path'] for x in items if x['round'] == r],
                            generator_agent_ids=sorted({x.get('generator_agent_id', 'unknown') for x in items if x['round'] == r}),
                            reviewer_agent_ids=sorted({v['agent_id'] for x in items if x['round'] == r for v in x['independent_reviews']}))
                       for r in range(1, unit['active_round'] + 1)]
    if unit['status'] == 'capped':
        suggested = [r for r in recommendations[unit['id']]
                     if key(r['best_candidate']) in {key(x['path']) for x in items}]
        if suggested:
            unit['best_candidate'] = suggested[-1]['best_candidate']
            unit['best_candidate_difference'] = suggested[-1].get('remaining_difference', '')
            unit['reviewer_best_candidate_recommendations'] = suggested
        elif not unit.get('best_candidate'):
            best = max(items, key=lambda x: (sum(r['verdict'] == 'pass' for r in x['independent_reviews']), x['round'], -x['candidate']))
            unit['best_candidate'] = best['path']
            unit['best_candidate_difference'] = best.get('review_zh', '')
        unit['best_candidate_usage'] = '仅供查看，未通过全部独立审查，禁止作为已选首帧'

write(KF / 'keyframe_generation.json', candidates)
write(MACHINE / 'keyframe_units_queue.json', queue)
status = read(KF / 'generation_status.json')
status.update(keyframes_completed=sum(x['status'] == 'passed' for x in queue),
              keyframe_image_count=len(candidates), keyframe_counts=dict(Counter(x['status'] for x in candidates)),
              keyframe_unit_counts=dict(Counter(x['status'] for x in queue)),
              total_image_count=len(candidates) + status['image_count'],
              next_step='继续有剩余轮次的独立镜头；已到限主帧及其依赖保持阻塞。')
write(KF / 'generation_status.json', status)
cards = {x['id']: x for x in read(KF / 'keyframe_cards.json')['cards']}
labels = {'passed': '新生成／已选', 'needs_retry': '未通过，待修正', 'pending_review': '待独立审查', 'capped': '到限未通过'}
lines = ['# 第01集关键帧登记', '', f"已批准38镜；当前已选{status['keyframes_completed']}镜，实际生成候选{len(candidates)}张。仅已选图片可作为视频首帧。", '',
         '|镜号|场景|机位底板|出场人物|对应剧情|选中文件|分级|来源／状态|', '|---|---|---|---|---|---|---|---|']
for unit in queue:
    card = cards[unit['id']]
    chosen = unit.get('selected_file')
    link = f"[查看原图](_shots/{unit['id']}/{Path(chosen).name})" if chosen else '—'
    label = labels.get(unit['status'], '等待主帧 ' + str(unit.get('dependency', '')))
    story = card.get('script_ref_zh', '').split('——')[-1].replace('|', '／')
    names = '、'.join(x['name'] for x in card.get('people', []) + card.get('background_people', []))
    lines.append(f"|{unit['id']}|{card['scene']}|{card['plate_id']}|{names}|{story}|{link}|{card['tier']}|{label}|")
(KF / 'keyframes.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({'images': len(candidates), 'units': status['keyframe_unit_counts']}, ensure_ascii=False))
