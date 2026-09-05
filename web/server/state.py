"""output/<剧名>/_web_state/review.json 读写：剧本家反馈落地的唯一位置。

四类内容：
- comments：批注（对某镜/某张图/某个关键帧/某条视频任务的留言）
- selections：{job_id: 选中的文件名}，图片入选标记
- regen_jobs：重新生成的请求/任务记录（人物场景关键帧走真实子进程，
  视频走"仅登记待办"）
- edits：分镜表/视频清单文字字段被网页直接改写的审计记录

单个项目内的写操作靠一个进程内 Lock 串行化，避免并发请求互相覆盖；
落盘用"写临时文件再 os.replace"防止写到一半被读到坏 JSON。
"""
import json
import os
import threading
import time
import uuid

_locks = {}
_locks_guard = threading.Lock()


def _lock_for(path):
    with _locks_guard:
        lock = _locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _locks[path] = lock
        return lock


def new_id():
    return uuid.uuid4().hex[:12]


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def load(path):
    if path and os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = {}
    data.setdefault('comments', [])
    data.setdefault('selections', {})
    data.setdefault('regen_jobs', [])
    data.setdefault('edits', [])
    return data


def save(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def _mutate(path, fn):
    with _lock_for(path):
        data = load(path)
        result = fn(data)
        save(path, data)
        return result


def add_comment(path, target, text, author=None):
    def fn(data):
        entry = {
            'id': new_id(),
            'target': target,
            'text': text,
            'author': author or '剧本家',
            'created_at': _now(),
            'resolved': False,
        }
        data['comments'].append(entry)
        return entry
    return _mutate(path, fn)


def list_comments(path, resolved=None):
    comments = load(path)['comments']
    if resolved is not None:
        comments = [c for c in comments if bool(c.get('resolved')) == resolved]
    return comments


def resolve_comment(path, comment_id):
    def fn(data):
        for c in data['comments']:
            if c['id'] == comment_id:
                c['resolved'] = True
                c['resolved_at'] = _now()
                return c
        raise ValueError('comment not found')
    return _mutate(path, fn)


def set_selection(path, job_id, filename):
    def fn(data):
        data['selections'][job_id] = filename
        return dict(data['selections'])
    return _mutate(path, fn)


def get_selections(path):
    return load(path)['selections']


def add_edit(path, file_rel, field, old_value, new_value, row_key=None):
    def fn(data):
        entry = {
            'id': new_id(),
            'file': file_rel,
            'row_key': row_key,
            'field': field,
            'old': old_value,
            'new': new_value,
            'at': _now(),
        }
        data['edits'].append(entry)
        return entry
    return _mutate(path, fn)


def add_regen_job(path, target, note=None, status='pending', token=None, kind='image', author=None):
    def fn(data):
        entry = {
            'id': new_id(),
            'token': token,
            'kind': kind,
            'target': target,
            'note': note,
            'status': status,
            'requested_at': _now(),
            'author': author,
        }
        data['regen_jobs'].append(entry)
        return entry
    return _mutate(path, fn)


def update_regen_job(path, job_id, **fields):
    def fn(data):
        for j in data['regen_jobs']:
            if j['id'] == job_id or j.get('token') == job_id:
                if j.get('status') == 'cancelled':
                    return j  # 终止前发出的旧轮询响应不能重新激活任务。
                j.update(fields)
                j['updated_at'] = _now()
                return j
        raise ValueError('regen job not found')
    return _mutate(path, fn)


def list_regen_jobs(path):
    return load(path)['regen_jobs']
