"""RunPod 有界租卡：不可变报价、单次创建、状态核实、到期释放。"""
import json
import math
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
import fcntl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import auth
import control_store as store
import notifications
from router import ApiError

ACTIVE = ('creating', 'unknown', 'running', 'stopping')
IDLE_SECONDS = 600
_locks = {}
_guard = threading.Lock()


@contextmanager
def lock(identifier, blocking=True):
    with _guard:
        local = _locks.setdefault(identifier, threading.RLock())
    if not local.acquire(blocking=blocking):
        yield False
        return
    try:
        directory = Path(auth.DATA_DIR) / 'gpu_locks'
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / (identifier + '.lock')).open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        local.release()


def request(method, path, body=None, graphql=False):
    key = store.settings().get('runpod_api_key')
    if not key:
        raise ApiError(503, '管理员尚未配置 RunPod API Key')
    url = 'https://api.runpod.io/graphql' if graphql else 'https://rest.runpod.io/v1' + path
    req = Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json', 'User-Agent':'Scriptwriter-Web/1.0'})
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read()
            result = json.loads(raw) if raw else {}
            if isinstance(result, dict) and result.get('errors'):
                raise ApiError(502, 'RunPod 查询失败，请检查 API 权限或稍后重试')
            return result
    except HTTPError as exc:
        if exc.code == 404:
            raise ApiError(404, 'RunPod 实例不存在') from None
        raise ApiError(502, f'RunPod 请求被拒绝（HTTP {exc.code}），请检查配置、余额及库存') from None
    except (URLError, TimeoutError, ValueError):
        raise ApiError(502, 'RunPod 暂时无法响应，正在核实状态，请勿重复创建') from None


def catalog():
    result = request('POST', '', {'query': '''query { gpuTypes { id displayName memoryInGb secureCloud
      lowestPrice(input:{gpuCount:1,secureCloud:true,minDisk:50}) {
        uninterruptablePrice stockStatus availableGpuCounts } } }'''}, graphql=True)
    if not isinstance(result.get('data', {}).get('gpuTypes'), list):
        raise ApiError(502, 'RunPod 未返回有效机型目录，请刷新重试')
    rows = []
    for gpu in result.get('data', {}).get('gpuTypes', []):
        quote = gpu.get('lowestPrice') or {}
        price = quote.get('uninterruptablePrice')
        valid_price = type(price) in (float, int) and math.isfinite(price) and price > 0
        stock = str(quote.get('stockStatus') or 'unknown').lower()
        counts = quote.get('availableGpuCounts')
        # Production API can return null here even with stockStatus=High.
        # The price query already specifies gpuCount=1; use its status when
        # counts is omitted, but honour an explicit list excluding one card.
        single_available = counts is None or (isinstance(counts, list) and 1 in counts)
        if gpu.get('secureCloud'):
            rows.append({'id':gpu['id'], 'name':gpu['displayName'], 'memory_gb':gpu['memoryInGb'],
                         'hourly_usd':price if valid_price else None, 'stock':stock,
                         'available':valid_price and stock in ('high','medium','low') and single_available,
                         'available_gpu_counts':counts})
    return sorted(rows, key=lambda g:(not g['available'], g['hourly_usd'] or float('inf')))


def get(identifier):
    with store.db() as c:
        row = c.execute('SELECT * FROM rentals WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ApiError(404, '找不到这条租卡记录')
        return {**dict(row), 'detail':json.loads(row['detail'])}


def save(identifier, **fields):
    allowed = {'status','pod_id','detail','expires_at'}
    if set(fields)-allowed:
        raise ValueError('Invalid rental update')
    if 'detail' in fields:
        fields['detail'] = json.dumps(fields['detail'], ensure_ascii=False)
    fields['updated_at'] = time.time()
    with store.db() as c:
        c.execute('UPDATE rentals SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', (*fields.values(), identifier))


def public(row):
    result = {k:v for k,v in row.items() if k != 'detail'}
    detail = row['detail']
    for key in ('gpu','hourly_usd','max_usd','minutes','estimated_usd','runtime','error','last_checked','cost_estimate_usd','stop_requested','ssh_host','ssh_port','video_ready','idle_since','stop_reason'):
        if key in detail:
            result[key] = detail[key]
    result['elapsed_seconds'] = max(0, (detail.get('ended_at') or time.time())-row['created_at']) if row['status'] != 'preview' else 0
    result['idle_seconds'] = IDLE_SECONDS
    result['idle_deadline'] = detail.get('idle_since',row['created_at']) + IDLE_SECONDS
    result['notification_email'] = notifications.GPU_RECIPIENT
    return result


def list_rentals(username=None):
    with store.db() as c:
        rows = c.execute('SELECT * FROM rentals'+(' WHERE username=?' if username else '')+' ORDER BY created_at DESC LIMIT 300', (username,) if username else ()).fetchall()
        return [{**dict(r),'detail':json.loads(r['detail'])} for r in rows]


def preview(username, project, body):
    store.ensure_enabled(username)
    if not auth.can_access_project(username, project):
        raise ApiError(403, '没有权限访问这个项目')
    config = store.settings()
    if not auth.is_admin(username) and not store.account(username)['gpu_allowed']:
        raise ApiError(403, '管理员尚未授予租卡权限')
    if not config.get('gpu_enabled') or not config.get('gpu_image') or not config.get('gpu_public_key'):
        raise ApiError(503, '管理员尚未启用租卡并配置运行镜像与 SSH 公钥')
    minutes = body.get('minutes')
    maximum = body.get('max_usd')
    if type(minutes) is not int or not 5 <= minutes <= config.get('gpu_max_minutes', 60):
        raise ApiError(400, '租用时长超出管理员允许范围')
    if type(maximum) not in (int, float) or not math.isfinite(maximum) or not 0 < maximum <= config.get('gpu_max_usd', 10):
        raise ApiError(400, '预算超出管理员允许范围')
    gpu = next((g for g in catalog() if g['id'] == body.get('gpu_id')), None)
    if not gpu:
        raise ApiError(400, '机型不存在或当前无报价，请重新选择')
    if not gpu.get('available'):
        raise ApiError(409, '该机型当前没有可确认的单卡库存，请刷新实时机型后重新选择')
    # 容器盘采用明确展示的保守费用预算；实际账单由 RunPod 计费。
    rate = gpu['hourly_usd'] + 50 * .1 / 720
    estimate = rate * minutes / 60
    if estimate > maximum:
        raise ApiError(400, '预算不足以覆盖所选时长，请缩短时长或增加预算')
    identifier = uuid.uuid4().hex
    payload = {'name':'sw-'+identifier, 'imageName':config['gpu_image'], 'gpuTypeIds':[gpu['id']], 'gpuCount':1,
               'cloudType':'SECURE', 'containerDiskInGb':50, 'volumeInGb':0, 'ports':['22/tcp'],
               'env':{'PUBLIC_KEY':config['gpu_public_key']}, 'interruptible':False}
    # H3 只经 SSH 隧道访问，不向公网开放无鉴权的视频接口。
    detail = {'gpu':gpu, 'hourly_usd':rate, 'estimated_usd':round(estimate,4), 'max_usd':maximum,
              'minutes':minutes, 'body':payload, 'video_ready':bool(config.get('video_ready'))}
    now = time.time()
    with store.db() as c:
        c.execute('INSERT INTO rentals VALUES (?,?,?,?,?,?,?,?,?)',
                  (identifier, username, project, 'preview', None, json.dumps(detail), now, now+300, now))
    return public(get(identifier))


def start(username, identifier, approved):
    if approved is not True:
        raise ApiError(400, '请检查租卡方案并明确批准')
    with store.user_lock(username), lock(identifier):
        row = get(identifier)
        if row['username'] != username:
            raise ApiError(403, '只能执行本人提交的租卡方案')
        store.ensure_enabled(username)
        if not auth.can_access_project(username, row['project']):
            raise ApiError(403, '项目权限已被撤销')
        if not store.settings().get('gpu_enabled') or (not auth.is_admin(username) and not store.account(username)['gpu_allowed']):
            raise ApiError(403, '租卡权限已被撤销')
        if row['status'] != 'preview':
            return public(row)
        if row['expires_at'] < time.time():
            raise ApiError(409, '报价已过期，请重新预览')
        if not notifications.configured():
            raise ApiError(503, '请管理员先配置发件服务；每次启动显卡必须发送邮件通知')
        with store.db() as c:
            active = c.execute("SELECT id FROM rentals WHERE username=? AND status IN ('creating','unknown','running','stopping')", (username,)).fetchone()
            if active:
                raise ApiError(409, '该账号已有租卡任务，请先释放当前显卡')
            c.execute("UPDATE rentals SET status='creating',expires_at=?,created_at=? WHERE id=?", (time.time()+row['detail']['minutes']*60, time.time(), identifier))
        detail = row['detail']; detail['idle_since'] = time.time()
        save(identifier, detail=detail)
        store.reserve(username, row['project'], 'gpu', identifier=identifier, detail={'gpu':row['detail']['gpu']['name']})
        store.started(identifier, identifier)
        threading.Thread(target=_create, args=(identifier,), daemon=True).start()
        return public(get(identifier))


def _create(identifier):
    with lock(identifier):
        row = get(identifier)
        try:
            result = request('POST', '/pods', row['detail']['body'])
            if not re.fullmatch(r'[a-zA-Z0-9_-]+', str(result.get('id',''))):
                raise ApiError(502, 'RunPod 未返回有效实例编号，正在核实')
            save(identifier, pod_id=result['id'], status='running')
            store.gpu_notification(identifier)
            _sync(identifier)
        except Exception:
            latest = get(identifier)
            detail = latest['detail']; detail['error'] = '创建结果待核实，系统不会重复创建；请查看 RunPod 控制台或等待核实'
            save(identifier, status='unknown' if not latest['pod_id'] else 'stopping', detail=detail)


def stop(identifier):
    with lock(identifier):
        row = get(identifier)
        if row['status'] in ('terminated','failed','preview'):
            return public(row)
        detail = row['detail']; detail['stop_requested'] = True
        save(identifier, status='stopping', detail=detail)
        if row['pod_id']:
            try:
                request('DELETE', '/pods/'+row['pod_id'])
            except ApiError as exc:
                if exc.status != 404:
                    detail['error'] = '释放未确认，可能仍在计费；后台将重试，请在 RunPod 控制台核实'
                    save(identifier, detail=detail)
                    return public(get(identifier))
            # DELETE 成功仍查询确认，不将请求已发出当作已停止计费。
            _sync(identifier)
        return public(get(identifier))


def _sync(identifier):
    row = get(identifier); detail = row['detail']
    if not row['pod_id']:
        pods = request('GET', '/pods')
        match = next((p for p in pods if p.get('name') == detail['body']['name']), None)
        if not match:
            detail['error'] = '未发现实例；创建结果仍待核实，可在管理员页面检查 RunPod 控制台'
            save(identifier, detail=detail)
            return
        save(identifier, pod_id=match['id']); row = get(identifier)
    store.gpu_notification(identifier)
    try:
        pod = request('GET', '/pods/'+row['pod_id'])
    except ApiError as exc:
        if exc.status != 404:
            raise
        detail.update(ended_at=time.time(), error=None, last_checked=time.time())
        save(identifier, status='terminated', detail=detail)
        store.settle(identifier, 'done')
        import video_jobs
        video_jobs.rental_stopped(identifier)
        return
    rate = float(pod.get('adjustedCostPerHr') or pod.get('costPerHr') or detail['hourly_usd'])
    detail.update(hourly_usd=rate, last_checked=time.time(), cost_estimate_usd=round(rate*(time.time()-row['created_at'])/3600,4),
                  ssh_host=pod.get('publicIp'), ssh_port=(pod.get('portMappings') or {}).get('22'))
    busy = has_tasks(identifier)
    if busy:
        detail['idle_since'] = time.time()
    idle = time.time() - detail.get('idle_since',row['created_at']) >= IDLE_SECONDS
    if idle and not busy:
        detail['stop_reason'] = '连续 10 分钟没有待处理或运行中的任务'
    must_stop = (detail.get('stop_requested') or (idle and not busy) or time.time() >= row['expires_at'] or not store.account(row['username'])['enabled']
                 or rate * detail['minutes']/60 > detail['max_usd'] or not auth.can_access_project(row['username'], row['project']))
    detail['error'] = None
    save(identifier, detail=detail, status='stopping' if must_stop else 'running')
    if must_stop:
        request('DELETE', '/pods/'+row['pod_id'])
        return  # 下一轮 GET 确认实例已删除。
    try:
        result = request('POST', '', {'query':'query($id:String!){pod(input:{podId:$id}){runtime{uptimeInSeconds gpus{id gpuUtilPercent memoryUtilPercent}}}}', 'variables':{'id':row['pod_id']}}, graphql=True)
        detail['runtime'] = ((result.get('data') or {}).get('pod') or {}).get('runtime')
        save(identifier, detail=detail)
    except ApiError:
        pass


def tick():
    with store.db() as c:
        active_ids = [r['id'] for r in c.execute("SELECT id FROM rentals WHERE status IN ('creating','unknown','running','stopping')")]
    for identifier in active_ids:
        row = get(identifier)
        with lock(row['id'], blocking=False) as acquired:
            if not acquired:
                continue
            try:
                _sync(row['id'])
            except Exception:
                latest = get(row['id']); detail = latest['detail']
                detail['error'] = 'RunPod 状态暂时无法核实，后台将重试；可能仍在计费'
                save(row['id'], detail=detail)


def has_tasks(identifier):
    with store.db() as c:
        rows = c.execute("SELECT detail FROM usage WHERE kind='video' AND status IN ('reserved','running','unknown')")
        return any(json.loads(r['detail']).get('rental_id') == identifier for r in rows)


def task_activity(identifier):
    """只供服务端接受/完成任务调用，浏览器轮询不能延长租期。调用者持 rental 锁。"""
    row = get(identifier)
    detail = row['detail']; detail['idle_since'] = time.time()
    save(identifier, detail=detail)
