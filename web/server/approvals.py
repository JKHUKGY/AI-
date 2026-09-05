"""图片执行前保存不可变预览；确认仅能执行这份已展示的请求一次。"""
from pathlib import Path
import time
import uuid

import state


def path(pdir):
    return str(Path(pdir) / '_web_state/approvals.json')


def preview(pdir, payload, username):
    entry = {'id': uuid.uuid4().hex, 'type': 'image', 'status': 'pending',
             'payload': payload, 'requested_by': username, 'created_at': time.time()}
    target = path(pdir)
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    state._mutate(target, lambda data: data.setdefault('approvals', []).append(entry))
    return entry


def execute(pdir, approval_id, username, submit):
    target = path(pdir)
    with state._lock_for(target):
        data = state.load(target)
        entry = next((e for e in data.get('approvals', []) if e['id'] == approval_id), None)
        if not entry:
            raise ValueError('需要先预览本次图片任务，再明确审批')
        if entry['status'] == 'running':
            return entry['result']
        if entry['status'] != 'pending' or time.time() - entry['created_at'] > 86400:
            raise ValueError('该审批已经使用或过期，请重新预览')
        entry.update(status='submitting', approved_by=username, approved_at=time.time())
        state.save(target, data)
        try:
            result = submit(entry['payload'])
        except Exception:
            entry['status'] = 'failed'
            state.save(target, data)
            raise
        entry.update(status='running', result=result)
        state.save(target, data)
        return result
