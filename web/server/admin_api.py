"""管理员入口；敏感配置只返回是否已设置。"""
import json
from pathlib import Path
import re
import threading
import time
import auth
import control_store as store
import notifications
import projects
import project_setup
import prompt_tasks
import jobs
import state
import runpod_service as runpod
import video_estimates
import gpu_monitor
import help_history
from router import ApiError

SECRET_FIELDS = {'runpod_api_key','smtp_password'}
SETTINGS_FIELDS = SECRET_FIELDS | {'mail_to','mail_from','smtp_host','smtp_port','smtp_user','smtp_security',
    'gpu_enabled','gpu_image','gpu_public_key','gpu_max_minutes','gpu_max_usd','video_ready'}


def require_admin(username):
    store.ensure_enabled(username)
    if not auth.is_admin(username):
        raise ApiError(403, '仅管理员可操作')


def safe_settings():
    config = store.settings()
    return {**{k:v for k,v in config.items() if k not in SECRET_FIELDS},
            **{k+'_configured':bool(config.get(k)) for k in SECRET_FIELDS}}


def users():
    result = []
    all_projects = projects.list_projects()
    for username, entry in auth.load_users().items():
        result.append({'username':username,'display_name':entry.get('display_name',username),
                       'admin':auth.is_admin(username), 'projects':[p['name'] for p in all_projects if auth.can_access_project(username,p['name'])],
                       **store.account(username)})
    return result


def stop_user(username, project=None):
    for item in projects.list_projects():
        if project and item['name'] != project:
            continue
        pdir = projects.project_dir(item['name'])
        setup = project_setup.status(pdir)
        if setup and setup.get('status') == 'running' and setup.get('started_by') == username:
            project_setup.cancel(pdir)
        for task in prompt_tasks.list_tasks(pdir):
            if task.get('author') == username and task['status'] == 'running':
                prompt_tasks.cancel(pdir, task['id'])
        for task in state.list_regen_jobs(projects.web_state_path(item['name'])):
            if task.get('author') == username and task.get('kind') == 'image' and task.get('token'):
                jobs.cancel(task['token'])
    for rental in runpod.list_rentals(username):
        if (not project or rental['project'] == project) and rental['status'] in runpod.ACTIVE:
            runpod.stop(rental['id'])


def register(router):
    @router.get(r'/api/admin/help-conversations')
    def help_conversations(ctx, params):
        require_admin(ctx.username)
        return help_history.listing(ctx.query_one('username',''),ctx.query_one('conversation_id',''),ctx.query_one('before'))

    @router.get(r'/api/admin/overview')
    def overview(ctx, params):
        require_admin(ctx.username)
        with store.db() as c:
            totals = [dict(row) for row in c.execute('SELECT username,kind,COUNT(*) tasks,SUM(charged) charged,SUM(CASE WHEN status IN (\'running\',\'reserved\',\'unknown\') THEN 1 ELSE 0 END) running FROM usage GROUP BY username,kind')]
            ledger = [dict(row) for row in c.execute('SELECT * FROM ledger ORDER BY created_at DESC LIMIT 200')]
        return {'users':users(), 'projects':[p['name'] for p in projects.list_projects()], 'usage':store.usage(),
                'totals':totals, 'ledger':ledger, 'settings':safe_settings(), 'mail':notifications.status(),
                'rentals':[runpod.public(r) for r in runpod.list_rentals()], 'prices':store.PRICES, 'features':store.FEATURES}

    @router.post(r'/api/admin/users')
    def create_user(ctx, params):
        require_admin(ctx.username)
        body = ctx.json(); username=body.get('username'); password=body.get('password')
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_\-\u4e00-\u9fff]{1,40}', username):
            raise ApiError(400,'账号限 1–40 位中文、字母、数字、横线或下划线')
        if not isinstance(password,str) or not 12 <= len(password) <= 200:
            raise ApiError(400,'密码需为 12–200 位')
        with store.user_lock('_accounts'):
            if username in auth.load_users():
                raise ApiError(409,'账号已存在')
            auth.add_user(username,password,username)
            auth.set_projects(username,[])
        return {'ok':True}

    @router.post(r'/api/admin/users/(?P<username>[^/]+)/(?P<action>access|credits|enabled|password)')
    def change_user(ctx, params):
        require_admin(ctx.username)
        username,action=params['username'],params['action']; body=ctx.json()
        if username not in auth.load_users():
            raise ApiError(404,'账号不存在')
        with store.user_lock(username), store.user_lock('_accounts'):
            if action=='credits':
                return {'account':store.allocate(username,body.get('delta'),ctx.username,body.get('request_id'))}
            if action=='enabled':
                enabled=body.get('enabled')
                if type(enabled) is not bool: raise ApiError(400,'enabled 必须为布尔值')
                if username==ctx.username and not enabled: raise ApiError(400,'不能停用当前管理员账号')
                store.set_enabled(username,enabled)
                if not enabled:
                    threading.Thread(target=stop_user,args=(username,),daemon=True).start()
            elif action=='password':
                password=body.get('password')
                if not isinstance(password,str) or not 12<=len(password)<=200: raise ApiError(400,'密码需为 12–200 位')
                auth.add_user(username,password,auth.display_name(username))
                store.set_enabled(username,bool(store.account(username)['enabled']))
            else:
                names=body.get('projects'); gpu=body.get('gpu_allowed'); flags=body.get('features',store.account(username)['features'])
                if not isinstance(names,list) or any(not isinstance(p,str) or not projects.project_dir(p) for p in names) or type(gpu) is not bool:
                    raise ApiError(400,'项目列表或租卡权限不合法')
                if auth.is_admin(username):
                    raise ApiError(400,'管理员保留全部项目权限；此处只分配普通账号')
                store.set_features(username,flags)
                previous={p['name'] for p in projects.list_projects() if auth.can_access_project(username,p['name'])}
                auth.set_projects(username,names)
                with store.db() as c:
                    store._account(c,username)
                    c.execute('UPDATE accounts SET gpu_allowed=? WHERE username=?',(int(gpu),username))
                for removed in previous-set(names):
                    threading.Thread(target=stop_user,args=(username,removed),daemon=True).start()
                if not gpu:
                    for row in runpod.list_rentals(username):
                        if row['status'] in runpod.ACTIVE:
                            threading.Thread(target=runpod.stop,args=(row['id'],),daemon=True).start()
        return {'ok':True,'account':store.account(username)}

    @router.post(r'/api/admin/settings')
    def update_settings(ctx, params):
        require_admin(ctx.username); body=ctx.json()
        if not isinstance(body,dict) or set(body)-SETTINGS_FIELDS: raise ApiError(400,'不支持的配置字段')
        if body.get('video_ready') is True and store.settings().get('h3_paused'):
            raise ApiError(409,'视频生成通道已暂时停用，恢复通道后才可启用')
        clean={}
        for key,value in body.items():
            if key in SECRET_FIELDS and value=='': continue
            if key in ('gpu_enabled','video_ready'):
                if type(value) is not bool: raise ApiError(400,'开关配置需为布尔值')
            elif key in ('smtp_port','gpu_max_minutes'):
                limit=65535 if key=='smtp_port' else 240
                if type(value) is not int or not 1<=value<=limit: raise ApiError(400,'端口或时长不合法')
            elif key=='gpu_max_usd':
                if type(value) not in (float,int) or not 0<value<=100: raise ApiError(400,'租卡预算上限需为 0–100 美元')
            elif not isinstance(value,str) or len(value)>4000 or '\r' in value or '\n' in value:
                raise ApiError(400,'配置格式不合法')
            if key in ('mail_to','mail_from') and value and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value): raise ApiError(400,'邮箱地址不合法')
            if key=='smtp_security' and value not in ('ssl','starttls'): raise ApiError(400,'发信必须使用 SSL 或 STARTTLS')
            if key=='gpu_public_key' and value and not value.startswith(('ssh-ed25519 ','ssh-rsa ')): raise ApiError(400,'请填写 SSH 公钥，不是私钥')
            clean[key]=value
        store.save_settings(clean)
        return {'settings':safe_settings()}

    @router.post(r'/api/admin/mail/test')
    def test_mail(ctx, params):
        require_admin(ctx.username)
        if not notifications.configured(): raise ApiError(400,'请先填写完整发信配置')
        store.audit(ctx.username,'mail_test')
        return {'ok':True,'message':'测试邮件已进入发送队列，请查看邮件状态'}

    @router.get(r'/api/usage')
    def personal_usage(ctx, params):
        return {'account':store.account(ctx.username),'usage':store.usage(ctx.username),'prices':store.PRICES}

    @router.get(r'/api/gpu')
    def gpu_list(ctx, params):
        config=store.settings()
        return {'rentals':[runpod.public(r) for r in runpod.list_rentals(None if auth.is_admin(ctx.username) else ctx.username)],
                'h3_paused':bool(config.get('h3_paused')), 'video_ready':bool(config.get('video_ready')) and not config.get('h3_paused',False), 'video_allowed':auth.is_admin(ctx.username) or store.account(ctx.username)['features']['video'],
                'mail_configured':notifications.configured(), 'notification_email':notifications.GPU_RECIPIENT, 'idle_seconds':runpod.IDLE_SECONDS,
                'enabled':bool(config.get('gpu_enabled')), 'allowed':auth.is_admin(ctx.username) or bool(store.account(ctx.username)['gpu_allowed']),
                'max_minutes':config.get('gpu_max_minutes',60),'max_usd':config.get('gpu_max_usd',10)}

    @router.get(r'/api/gpu/monitor')
    def gpu_monitor_report(ctx, params):
        return gpu_monitor.report(ctx.username)

    @router.get(r'/api/gpu/catalog')
    def gpu_catalog(ctx, params):
        if not auth.is_admin(ctx.username) and not store.account(ctx.username)['gpu_allowed']: raise ApiError(403,'没有租卡权限')
        rows=runpod.catalog()
        for row in rows:
            row['estimates']={str(steps):video_estimates.generation(row['name'],steps) for steps in (20,50)}
        return {'gpus':rows, 'queried_at':time.time(), 'cloud':'SECURE', 'gpu_count':1,
                'methodology':video_estimates.methodology()}

    @router.post(r'/api/projects/(?P<name>[^/]+)/gpu/preview')
    def gpu_preview(ctx, params):
        return {'rental':runpod.preview(ctx.username,params['name'],ctx.json())}

    @router.post(r'/api/gpu/(?P<identifier>[a-f0-9]+)/(?P<action>start|stop)')
    def gpu_action(ctx, params):
        row=runpod.get(params['identifier'])
        if row['username']!=ctx.username and not auth.is_admin(ctx.username): raise ApiError(403,'无权操作此实例')
        if params['action']=='start': return {'rental':runpod.start(ctx.username,params['identifier'],ctx.json().get('approved'))}
        if ctx.json().get('confirmed') is not True: raise ApiError(400,'释放显卡会清除容器盘，请明确确认')
        return {'rental':runpod.stop(params['identifier'])}
