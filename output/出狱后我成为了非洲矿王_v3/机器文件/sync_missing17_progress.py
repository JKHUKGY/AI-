"""Refresh the missing-shot checkpoint and user-selection reading copy."""
from pathlib import Path
import json
import os
import sys
from datetime import datetime, timezone

P = Path(__file__).resolve().parent.parent
M = P / '机器文件/多代理续做'
ROOT = Path('/workspaces/AI-')

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)

active = ['ep01_镜' + x.zfill(2) for x in sys.argv[1:]]
queue = read(M / 'keyframe_units_queue.json')
for unit in queue:
    unit['generation_in_progress'] = unit['id'] in active
write(M / 'keyframe_units_queue.json', queue)
selected = [u for u in queue if u.get('selected_file')]
pending = [u['id'] for u in queue if not u.get('selected_file')]
passed = sum(u['status'] == 'passed' for u in selected)
total_images = len(list((P / 'keyframes/ep01/_shots').glob('*/*.png')))
status_file = P / 'keyframes/ep01/generation_status.json'
status = read(status_file)
status['active_generation'] = active
status['last_updated_at'] = datetime.now(timezone.utc).isoformat()
write(status_file, status)
next_step = ('继续补齐：' + '、'.join(pending)) if pending else '第1集38镜已各选一张；视频尚未开始。'
body = f'''用户要求补齐尚未加入的17镜；沿用原批准和到限候选择优选用要求。

- 场次主帧已选6/6。
- 逐镜关键帧已选{len(selected)}/38，其中独立审查通过{passed}镜、按用户要求择优选用{len(selected)-passed}镜。
- 尚待选入{len(pending)}镜；已有逐镜候选{total_images}张。原图、轮次及独立审查记录保留。
- 当前生成：{'、'.join(active) or '无'}。
- {next_step}
- 已选图库：给人看/02_已选图片/第01集_关键帧/；阅读首页：给人看/阅读首页.html。
- 持久选用清单：机器文件/多代理续做/user_selected_candidates_20260905.json；重新合并审查时保留选用，不把原fail改为pass。
'''
progress = P / 'PROGRESS.md'
old = progress.read_text()
prefix = old.split('## 当前节点')[0]
suffix = old.split('## 后续已知缺口', 1)[1]
progress.write_text(prefix + '## 当前节点（补齐缺镜）\n\n' + body + '\n## 后续已知缺口' + suffix)
(P / '机器文件/当前断点.md').write_text('# 当前执行断点\n\n' + body)
manifest = read(M / 'user_selected_candidates_20260905.json')
report = P / '给人看/05_审阅与验收/到限候选择优选用.md'
lines = ['# 到限候选择优选用', '', '按用户要求择优选用，包含到限任务及镜29工具拦截后保留的现有最佳图。原独立审查意见保留；“已选”不表示所有技术标准均通过。', '', '|任务|选图|选择依据|保留的问题|', '|---|---|---|---|']
for item in sorted(manifest['selections'], key=lambda x: (x['kind'], x['id'])):
    path = Path(item['path'])
    if not path.is_absolute():
        path = ROOT / path
    link = os.path.relpath(path, report.parent)
    clean = lambda s: str(s).replace('|', '／').replace('\n', ' ')
    lines.append(f"|{item['id']}|[查看原图]({link})|{clean(item['selection_reason'])}|{clean(item['known_issues'])}|")
report.write_text('\n'.join(lines) + '\n')
roster_file = M / 'roster_missing17_20260905.json'
roster = read(roster_file)
for agent in roster['agents']:
    agent['deliverables'] = []
    assigned = set()
    agent.pop('status', None)
    for f in list(M.glob('generator_missing17*.json')) + list(M.glob('review_keyframes_missing17*.json')):
        report_data = read(f)
        if report_data.get('agent_id') == agent['agent_id']:
            agent['deliverables'].append(f.name)
            assigned.update(item['id'] for item in report_data.get('records', report_data.get('images', [])))
    agent['assigned'] = sorted(assigned)
roster['status'] = 'complete' if not pending else 'in_progress'
roster['selected_keyframes'] = len(selected)
roster['remaining_keyframes'] = pending
write(roster_file, roster)
print(f'{len(selected)}/38 selected; {len(pending)} pending; active: {active}')
