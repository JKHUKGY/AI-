"""后台结算及通知不依赖用户打开浏览器。"""
import json
from pathlib import Path
import threading
import time
import control_store as store
import notifications
import runpod_service
import jobs
import projects
import project_setup
import prompt_tasks


def reconcile(recover=False):
    with store.db() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM usage WHERE status IN ('reserved','running','unknown')")]
    for row in rows:
        kind=row['kind']; root=projects.project_dir(row['project'])
        if kind=='image':
            live=jobs.get_status(row['ref']) if row['ref'] else None
            if live and live['status']!='running':
                store.settle(row['id'],live['status'],len(live['new_files']))
            elif recover and not live:
                detail=json.loads(row['detail']); count=0
                if root and detail.get('folder'):
                    folder=Path(root)/detail['folder']
                    if folder.resolve().is_relative_to(Path(root).resolve()):
                        count=len(jobs._existing_files(str(folder),detail['job_id'])-set(detail['before']))
                store.settle(row['id'],'interrupted',count)
        elif kind=='prompt':
            task=next((t for t in prompt_tasks.list_tasks(root) if t['id']==row['ref']),None) if root else None
            if task and task['status']!='running':
                store.settle(row['id'],task['status'])
            elif recover and not task:
                store.settle(row['id'],'interrupted')
        elif kind=='setup':
            status=project_setup.status(root) if root else None
            if status and status['status'] not in ('running','ready'):
                store.settle(row['id'],status['status'])
        elif recover and kind not in ('gpu','video'):
            store.settle(row['id'],'interrupted')


def start():
    reconcile(recover=True)
    def work():
        last_gpu=0
        while True:
            try:
                reconcile()
                notifications.deliver_one()
                if time.time()-last_gpu>=15:
                    runpod_service.tick(); last_gpu=time.time()
            except Exception:
                # 不输出第三方错误正文，避免邮件授权码/API Key 泄漏。
                pass
            time.sleep(2)
    threading.Thread(target=work,daemon=True).start()
