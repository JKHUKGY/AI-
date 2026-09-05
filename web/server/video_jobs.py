"""持久 H3 视频提交：报价审批、积分冻结、SSH 隧道、恢复轮询和下载结算。

只读取项目已装配的 h3_jobs.json，不从浏览器接受任意服务器地址或文件路径。
提交结果不明时绝不重新 POST；释放实例后才解除其占用及退还积分。
"""
import base64
from contextlib import contextmanager
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from urllib.request import Request, urlopen
import uuid

import auth
import control_store as store
import projects
import runpod_service as gpu
from router import ApiError

_workers = set()
_guard = threading.Lock()
LIVE = ('reserved', 'running', 'unknown')


def get(identifier):
    with store.db() as c:
        row = c.execute("SELECT * FROM usage WHERE id=? AND kind='video'", (identifier,)).fetchone()
    if not row:
        raise ApiError(404, '视频任务不存在')
    return {**dict(row), 'detail': json.loads(row['detail'])}


def update(identifier, **fields):
    with store.db() as c:
        row = c.execute('SELECT detail FROM usage WHERE id=?', (identifier,)).fetchone()
        detail = json.loads(row['detail']); detail.update(fields)
        c.execute('UPDATE usage SET detail=? WHERE id=?', (json.dumps(detail,ensure_ascii=False),identifier))


def public(row):
    return {**{k:v for k,v in row.items() if k != 'detail'},
            'detail':{k:v for k,v in row['detail'].items() if k in
                      ('rental_id','job_id','episode','output','error','phase','prompt')}}


def manifest(project, episode):
    root = Path(projects.project_dir(project))
    path = root / 'videos' / f'ep{episode:02d}' / 'h3_jobs.json'
    if not path.resolve().is_relative_to(root.resolve()):
        raise ApiError(400, '任务文件路径不合法')
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text())
        if not isinstance(items, list) or any(not isinstance(j,dict) for j in items):
            raise ValueError()
        return items
    except (ValueError, OSError):
        raise ApiError(400, '视频任务清单格式不正确，请重新装配') from None


def condition_path(project, raw):
    root = Path(projects.project_dir(project)).resolve()
    if not isinstance(raw,str):
        raise ApiError(400, '视频参考素材必须是当前项目中的本地文件')
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path(projects.REPO_ROOT) / candidate if raw.startswith('output/') else root / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file() or candidate.stat().st_size > 30*1024*1024:
        raise ApiError(400, '视频参考文件不存在、超出当前项目或超过 30 MB')
    return candidate


def snapshot(project, job):
    if job.get('task') not in ('ref2va','fl2va','t2va'):
        raise ApiError(400, '不支持的 H3 视频任务类型')
    prompt = job.get('prompt'); target = job.get('target')
    if not isinstance(prompt,str) or not 1 <= len(prompt) <= 30000 or not isinstance(target,dict):
        raise ApiError(400,'视频提示词或目标参数不合法')
    duration = target.get('duration_seconds')
    edge = target.get('short_edge',768)
    if type(duration) not in (float,int) or not 4 <= duration <= 15 or type(edge) is not int or not 256 <= edge <= 2048 or edge % 32:
        raise ApiError(400,'视频需为 4–15 秒；分辨率为 256–2048 之间的 32 倍数')
    if target.get('aspect_ratio') not in ('auto','21:9','16:9','4:3','1:1','3:4','9:16'):
        raise ApiError(400,'视频画幅不合法')
    conditions = job.get('conditions',[])
    if not isinstance(conditions,list) or len(conditions) > 12:
        raise ApiError(400,'参考素材数量不合法')
    saved=[]; size=0
    for item in conditions:
        if not isinstance(item,dict) or item.get('type') not in ('image','video','audio','video_audio'):
            raise ApiError(400,'参考素材类型不合法')
        path = condition_path(project,item.get('path'))
        size += path.stat().st_size
        if size > 45*1024*1024:
            raise ApiError(400,'参考素材合计不能超过 45 MB')
        saved.append({**{k:v for k,v in item.items() if k in ('type','role','frame_index','start_time_seconds')},
                      'path':str(path.relative_to(Path(projects.project_dir(project)).resolve())),
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    seed = job.get('seed',0)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ApiError(400,'视频随机种子不合法')
    return {'task':job['task'],'prompt':prompt,'target':target,'seed':seed,'conditions':saved}


def preview(username, project, episode, body):
    store.require_feature(username,'video')
    if not auth.can_access_project(username,project): raise ApiError(403,'没有项目权限')
    if store.settings().get('h3_paused'): raise ApiError(503,'视频生成通道已暂时停用')
    if not store.settings().get('video_ready'): raise ApiError(503,'管理员尚未配置视频运行环境')
    job = next((j for j in manifest(project,episode) if j.get('id') == body.get('job_id')),None)
    if not job: raise ApiError(400,'请先准备该集的视频任务清单')
    rental = gpu.get(body.get('rental_id',''))
    if rental['username'] != username or rental['project'] != project or rental['status'] != 'running' or not rental['detail'].get('video_ready'):
        raise ApiError(403,'请选择本人在当前项目已启动的视频显卡')
    payload=snapshot(project,job)
    identifier='video:'+uuid.uuid4().hex
    detail={'rental_id':rental['id'],'job_id':job['id'],'episode':episode,'payload':payload,'prompt':payload['prompt'],'phase':'preview'}
    with store.db() as c:
        c.execute('INSERT INTO usage(id,username,project,kind,quantity,unit_cost,status,detail,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                  (identifier,username,project,'video',1,store.PRICES['video'],'preview',json.dumps(detail,ensure_ascii=False),time.time()))
    return {**public(get(identifier)),'credits':store.PRICES['video'],'target':payload['target']}


def start(username, identifier, approved):
    if approved is not True: raise ApiError(400,'请确认点数及显卡费用后再开始')
    row=get(identifier)
    if row['username'] != username: raise ApiError(403,'只能提交本人预览的视频任务')
    with store.user_lock(username), gpu.lock(row['detail']['rental_id']):
        store.require_feature(username,'video')
        if not auth.can_access_project(username,row['project']): raise ApiError(403,'项目权限已撤销')
        row=get(identifier)
        if row['status'] != 'preview': return public(row)
        if time.time()-row['created_at'] > 300: raise ApiError(409,'预览已过期，请重新预览')
        rental=gpu.get(row['detail']['rental_id'])
        if rental['status'] != 'running' or rental['expires_at'] <= time.time(): raise ApiError(409,'显卡未运行或已到期')
        if store.settings().get('h3_paused'): raise ApiError(403,'视频生成通道已暂时停用')
        if not store.settings().get('video_ready'): raise ApiError(403,'视频生成已关闭')
        payload(row)  # 冻结点数前验证预览时的素材摘要仍一致。
        with store.db() as c:
            pending=c.execute("SELECT id FROM usage WHERE kind='video' AND status IN ('reserved','running','unknown') AND project=?",(row['project'],)).fetchall()
            for item in pending:
                other=c.execute('SELECT detail FROM usage WHERE id=?',(item['id'],)).fetchone()
                if json.loads(other['detail']).get('rental_id') == rental['id']:
                    raise ApiError(409,'这台显卡已有视频任务，请等完成后再提交')
            user=store._account(c,username)
            if user['balance'] < row['unit_cost']: raise ApiError(402,'积分不足，请联系管理员分配')
            c.execute('UPDATE accounts SET balance=balance-? WHERE username=?',(row['unit_cost'],username))
            c.execute("UPDATE usage SET status='reserved' WHERE id=?",(identifier,))
            c.execute('INSERT INTO ledger VALUES (?,?,?,?,?,?)',('hold:'+identifier,username,-row['unit_cost'],'冻结视频积分',username,time.time()))
        gpu.task_activity(rental['id'])
    kick(identifier)
    return public(get(identifier))


@contextmanager
def tunnel(rental):
    detail=rental['detail']; host=detail.get('ssh_host'); port=detail.get('ssh_port')
    if not host or not port or not re.fullmatch(r'[a-zA-Z0-9.:-]+',str(host)) or not str(port).isdigit():
        raise ApiError(503,'显卡 SSH 尚未就绪，请等待实例启动')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); local=sock.getsockname()[1]
    key=Path(auth.DATA_DIR)/'gpu_ed25519'
    proc=subprocess.Popen(['ssh','-N','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new',
        '-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=3',
        '-i',str(key),'-p',str(port),'-L',f'127.0.0.1:{local}:127.0.0.1:30011','root@'+host],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if proc.poll() is not None: raise ApiError(503,'无法连接显卡 SSH，请检查运行镜像及公钥')
            try:
                with socket.create_connection(('127.0.0.1',local),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise ApiError(503,'显卡连接超时')
        yield f'http://127.0.0.1:{local}'
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()


def http(endpoint,path,body=None):
    request=Request(endpoint+path,data=json.dumps(body).encode() if body is not None else None,
                    headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=30) as response:
        return json.load(response)


def payload(row):
    result=dict(row['detail']['payload']); conditions=[]
    for item in result['conditions']:
        path=condition_path(row['project'],item['path']); blob=path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != item['sha256']: raise ApiError(409,'参考素材已变化，请重新预览')
        conditions.append({**{k:v for k,v in item.items() if k not in ('path','sha256')},
                           'uri':f'data:{mimetypes.guess_type(path)[0] or "application/octet-stream"};base64,'+base64.b64encode(blob).decode()})
    result['conditions']=conditions
    result.update(model='MiniMaxAI/MiniMax-H3',num_outputs_per_prompt=1)
    return result


def download(endpoint, remote, destination):
    temp=destination.with_suffix('.part')
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        with urlopen(endpoint+'/v1/videos/'+remote+'/content',timeout=60) as response, temp.open('wb') as handle:
            size=0
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                if size > 512*1024*1024: raise ValueError('视频文件过大')
                handle.write(chunk)
        with temp.open('rb') as handle:
            if b'ftyp' not in handle.read(32): raise ValueError('返回内容不是 MP4 视频')
        os.replace(temp,destination)
    finally:
        temp.unlink(missing_ok=True)


def worker(identifier):
    try:
        row=get(identifier); rental=gpu.get(row['detail']['rental_id'])
        with tunnel(rental) as endpoint:
            row=get(identifier)
            if row['status']=='reserved':
                body=payload(row)
                # 持久标记在 POST 之前。进程此时中断，不会重新 POST 产生重复任务。
                with gpu.lock(rental['id']):
                    if gpu.get(rental['id'])['status'] != 'running': return
                    update(identifier,phase='submitting')
                    store.started(identifier)
                    remote=http(endpoint,'/v1/videos',body).get('id','')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',remote): raise ValueError('缺少视频编号')
                    update(identifier,phase='polling',remote_id=remote)
            row=get(identifier); remote=row['detail'].get('remote_id')
            if not remote:
                update(identifier,error='提交结果待核实；请关闭此显卡以结束任务并退还积分，系统不会重复提交')
                return
            status=str(http(endpoint,'/v1/videos/'+remote).get('status','')).lower()
            if status in ('failed','error','cancelled','canceled'):
                with gpu.lock(rental['id']):
                    store.settle(identifier,'failed'); gpu.task_activity(rental['id'])
                    update(identifier,error='视频生成失败，积分已退还')
            elif status in ('completed','succeeded','success','done'):
                root=Path(projects.project_dir(row['project']))
                filename='web_'+identifier.split(':')[1]+'.mp4'
                dest=root/'videos'/f"ep{row['detail']['episode']:02d}"/filename
                download(endpoint,remote,dest)
                with gpu.lock(rental['id']):
                    if get(identifier)['status'] not in LIVE:
                        dest.unlink(missing_ok=True); return
                    update(identifier,phase='done',output=str(dest.relative_to(Path(projects.OUTPUT_DIR))),error=None)
                    store.settle(identifier,'done',1); gpu.task_activity(rental['id'])
    except Exception:
        row=get(identifier)
        if row['status']=='reserved':
            store.settle(identifier,'failed')
            update(identifier,error='连接或素材校验失败，未提交视频，积分已退还')
        elif row['status'] in LIVE:
            update(identifier,error='视频状态暂无法核实，后台将重试；也可手动关闭显卡结束任务')
    finally:
        with _guard: _workers.discard(identifier)


def kick(identifier):
    with _guard:
        if identifier in _workers: return
        _workers.add(identifier)
    threading.Thread(target=worker,args=(identifier,),daemon=True).start()


def tick():
    with store.db() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM usage WHERE kind='video' AND status IN ('reserved','running','unknown')")]
    for row in rows:
        detail=json.loads(row['detail'])
        # 无编号且已经发出 POST 的不明任务不重发，10 分钟后主动释放，避免长期占卡。
        if row['status'] != 'reserved' and not detail.get('remote_id') and time.time()-row['created_at'] >= 600:
            gpu.stop(detail['rental_id'])
        else: kick(row['id'])


def rental_stopped(identifier):
    with store.db() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM usage WHERE kind='video' AND status IN ('reserved','running','unknown')")]
    for row in rows:
        if json.loads(row['detail']).get('rental_id') == identifier:
            store.settle(row['id'],'cancelled')
            update(row['id'],error='显卡已关闭，未完成的视频积分已退还')


def register(router):
    @router.get(r'/api/projects/(?P<name>[^/]+)/videos/(?P<ep>\d+)/generation')
    def listing(ctx,params):
        items=manifest(params['name'],int(params['ep']))
        rows=store.usage(None if auth.is_admin(ctx.username) else ctx.username)
        return {'jobs':[{'id':j.get('id'),'prompt':j.get('prompt'),'target':j.get('target')} for j in items],
                'tasks':[public(r) for r in rows if r['project']==params['name'] and r['kind']=='video' and r['detail'].get('episode')==int(params['ep']) and r['status']!='preview'],
                'credits':store.PRICES['video'],'paused':bool(store.settings().get('h3_paused')),
                'ready':bool(store.settings().get('video_ready')) and not store.settings().get('h3_paused',False)}

    @router.post(r'/api/projects/(?P<name>[^/]+)/videos/(?P<ep>\d+)/generation/preview')
    def prepare(ctx,params):
        return {'task':preview(ctx.username,params['name'],int(params['ep']),ctx.json())}

    @router.post(r'/api/video/(?P<identifier>video:[a-f0-9]+)/start')
    def submit(ctx,params):
        return {'task':start(ctx.username,params['identifier'],ctx.json().get('approved'))}
