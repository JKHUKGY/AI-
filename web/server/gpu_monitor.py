"""Read-only live telemetry. Polling never starts/stops Pods or resets idle time."""
import time
import json
import auth
import control_store as store
import runpod_service as runpod
from router import ApiError


def report(username):
    store.ensure_enabled(username)
    admin = auth.is_admin(username)
    with store.db() as c:
        rows = c.execute("SELECT * FROM rentals WHERE status IN ('creating','unknown','running','stopping')"
                         + ('' if admin else ' AND username=?') + ' ORDER BY created_at DESC',
                         () if admin else (username,)).fetchall()
        rentals = [{**dict(r), 'detail':json.loads(r['detail'])} for r in rows]
        counts = {}
        for task in c.execute("SELECT detail FROM usage WHERE kind='video' AND status IN ('reserved','running','unknown')"):
            identifier = json.loads(task['detail']).get('rental_id')
            counts[identifier] = counts.get(identifier, 0) + 1
    items = []
    for row in rentals:
        item = runpod.public(row)
        # Cached runtime must never be presented as a fresh sample on failure.
        item.update(runtime=None, monitor_state='pending', monitor_error=None,
                    queried_at=None, provider_status=None, active_tasks=counts.get(row['id'], 0))
        items.append(item)
    query_items = [item for item in items if item['pod_id']]
    for offset in range(0, len(query_items), 20):
        batch = query_items[offset:offset+20]
        variables = {'id'+str(i):item['pod_id'] for i,item in enumerate(batch)}
        declaration = ','.join('$'+name+':String!' for name in variables)
        fields = ' '.join('p'+str(i)+':pod(input:{podId:$id'+str(i)+'}){desiredStatus runtime{uptimeInSeconds gpus{id gpuUtilPercent memoryUtilPercent} container{cpuPercent memoryPercent}}}' for i in range(len(batch)))
        try:
            response = runpod.request('POST','',{'query':'query('+declaration+'){'+fields+'}', 'variables':variables},graphql=True)
            data = response.get('data')
            if not isinstance(data, dict):
                raise ApiError(502, 'RunPod 未返回有效监控数据')
            now = time.time()
            for i,item in enumerate(batch):
                key = 'p'+str(i)
                if key not in data:
                    item.update(monitor_state='error', monitor_error='RunPod 未返回此实例的查询结果')
                    continue
                pod = data[key]
                item['queried_at'] = now
                if not pod:
                    item.update(monitor_state='missing', monitor_error='RunPod 未找到实例，关闭状态由后台继续核实')
                    continue
                item['provider_status'] = pod.get('desiredStatus')
                item['runtime'] = pod.get('runtime')
                item['monitor_state'] = 'live' if item['runtime'] else 'pending'
        except ApiError:
            for item in batch:
                item.update(monitor_state='error', monitor_error='RunPod 实时查询失败，请刷新重试；没有将旧数值作为当前数据')
    return {'rentals':items, 'refreshed_at':time.time(), 'refresh_seconds':15, 'is_admin':admin}
