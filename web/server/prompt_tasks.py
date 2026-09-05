"""持久化文字任务；浏览器关闭或换页不影响执行，完成结果可重新读取。"""
from pathlib import Path
import threading
import time
import uuid

import ai_prompt
import state
import generation_control

_slots = threading.BoundedSemaphore(2)
_controls = {}
_guard = threading.Lock()


def path(pdir):
    return str(Path(pdir) / '_web_state/prompt_tasks.json')


def list_tasks(pdir):
    return state.load(path(pdir)).get('tasks', [])


def start(pdir, target, username, run, commit=None):
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
        control = generation_control.Control()
        control.username = username
        with _guard:
            _controls[(filename, task['id'])] = control
    def finish(update):
        def mutate(data):
            entry = next(t for t in data['tasks'] if t['id'] == task['id'])
            if entry['status'] == 'running':
                entry.update(update, finished_at=time.time())
        state._mutate(filename, mutate)
    def work():
        try:
            with generation_control.activate(control):
                result = run()
                with generation_control.guard():
                    if commit:
                        result = commit(result)
                    finish({'status': 'done', 'result': result})
                    control.finished = True
        except generation_control.Cancelled:
            finish({'status':'cancelled'})
        except Exception as exc:
            with control.lock:
                if not control.cancelled:
                    finish({'status': 'failed', 'error': str(exc) if isinstance(exc, (ValueError, RuntimeError)) or hasattr(exc, 'status') else '文字任务失败，请重试'})
                    control.finished = True
        finally:
            _slots.release()
            with _guard:
                _controls.pop((filename, task['id']), None)
            control.done.set()
    threading.Thread(target=work, daemon=True).start()
    return dict(task)


def cancel(pdir, identifier):
    filename = path(pdir)
    with _guard:
        control = _controls.get((filename, identifier))
    if control:
        with control.lock:
            if control.cancel():
                def mark(data):
                    task = next(t for t in data['tasks'] if t['id'] == identifier)
                    task.update(status='cancelled', finished_at=time.time())
                    task.pop('result', None)
                    task.pop('error', None)
                state._mutate(filename, mark)
        control.done.wait(5)
    return next((t for t in list_tasks(pdir) if t['id'] == identifier), None)


def recover(output_dir):
    for filename in Path(output_dir).glob('*/_web_state/prompt_tasks.json'):
        def mark(data):
            for task in data.get('tasks', []):
                if task['status'] == 'running':
                    task.update(status='interrupted', error='服务重启中断了文字任务，原任务记录已保留，请重新提交')
        state._mutate(str(filename), mark)
