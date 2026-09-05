"""持久化文字任务；浏览器关闭或换页不影响执行，完成结果可重新读取。"""
from pathlib import Path
import threading
import time
import uuid

import ai_prompt
import state

_slots = threading.BoundedSemaphore(2)


def path(pdir):
    return str(Path(pdir) / '_web_state/prompt_tasks.json')


def list_tasks(pdir):
    return state.load(path(pdir)).get('tasks', [])


def start(pdir, target, username, run):
    filename = path(pdir)
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    with state._lock_for(filename):
        data = state.load(filename)
        tasks = data.setdefault('tasks', [])
        existing = next((t for t in tasks if t['target'] == target and t['status'] == 'running'), None)
        if existing:
            return dict(existing)
        if not _slots.acquire(blocking=False):
            raise ai_prompt.BusyError('已有两个文字任务正在运行，请稍后重试')
        task = {'id': uuid.uuid4().hex, 'kind': 'prompt', 'target': target, 'author': username,
                'status': 'running', 'created_at': time.time()}
        tasks.append(task)
        try:
            state.save(filename, data)
        except Exception:
            _slots.release()
            raise
    def work():
        try:
            result = run()
            update = {'status': 'done', 'result': result}
        except Exception as exc:
            update = {'status': 'failed', 'error': str(exc) if isinstance(exc, (ValueError, RuntimeError)) or hasattr(exc, 'status') else '文字任务失败，请重试'}
        try:
            def finish(data):
                entry = next(t for t in data['tasks'] if t['id'] == task['id'])
                entry.update(update, finished_at=time.time())
            state._mutate(filename, finish)
        finally:
            _slots.release()
    threading.Thread(target=work, daemon=True).start()
    return dict(task)


def recover(output_dir):
    for filename in Path(output_dir).glob('*/_web_state/prompt_tasks.json'):
        def mark(data):
            for task in data.get('tasks', []):
                if task['status'] == 'running':
                    task.update(status='interrupted', error='服务重启中断了文字任务，原任务记录已保留，请重新提交')
        state._mutate(str(filename), mark)
