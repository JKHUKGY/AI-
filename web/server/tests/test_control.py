"""账户/点数/付费资源边界。第三方完全替身，不租卡、不生成、不发邮件。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import time
import threading
from http.client import HTTPConnection
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import auth
import approvals
import control_store as store
import notifications
import projects
import runpod_service as gpu
import video_jobs as video
from router import ApiError, Ctx


class ControlTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); data=self.root/'data'; data.mkdir()
        for name,value in {'DATA_DIR':str(data),'USERS_PATH':str(data/'users.json'),
                           'PERMISSIONS_PATH':str(data/'permissions.json'),'SECRET_KEY_PATH':str(data/'secret_key')}.items():
            p=patch.object(auth,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(projects,'OUTPUT_DIR',str(self.root/'output'));p.start();self.addCleanup(p.stop)
        self.project=self.root/'output'/'demo';self.project.mkdir(parents=True)
        auth.add_user('admin','twelve-letters-password');auth.set_admin('admin',True)
        auth.add_user('writer','twelve-letters-password');auth.set_projects('writer',['demo'])
        store.allocate('writer',1000,'admin','initial-points')
        store.save_settings({'gpu_enabled':True,'gpu_image':'test-image','gpu_public_key':'ssh-ed25519 test',
                             'video_ready':True,'smtp_host':'smtp.test','smtp_user':'sender','smtp_password':'secret',
                             'mail_from':'sender@example.com'})
        with store.db() as c:c.execute('UPDATE accounts SET gpu_allowed=1 WHERE username=?',('writer',))

    def call(self,path,body=None,username='admin',method='POST'):
        handler,params=app.router.match(method,path)
        ctx=Ctx({},json.dumps(body or {}).encode(),{});ctx.username=username
        return handler(ctx,params)

    def rental(self,age=0):
        with patch.object(gpu,'catalog',return_value=[{'id':'test','name':'Test GPU','memory_gb':24,'hourly_usd':.5,'available':True}]):
            row=gpu.preview('writer','demo',{'gpu_id':'test','minutes':60,'max_usd':10})
        identifier=row['id']; detail=gpu.get(identifier)['detail'];detail['idle_since']=time.time()-age
        gpu.save(identifier,status='running',pod_id='pod123',detail=detail,expires_at=time.time()+3600)
        store.reserve('writer','demo','gpu',identifier=identifier);store.started(identifier,identifier)
        return identifier

    def job(self,rental):
        folder=self.project/'videos/ep01';folder.mkdir(parents=True,exist_ok=True)
        (self.project/'frame.png').write_bytes(b'image')
        job={'id':'shot01','task':'ref2va','prompt':'six-section prepared prompt','target':{'duration_seconds':5,'short_edge':768,'aspect_ratio':'9:16'},
             'seed':42,'conditions':[{'type':'image','role':'reference','path':'frame.png'}]}
        (folder/'h3_jobs.json').write_text(json.dumps([job]))
        return video.preview('writer','demo',1,{'job_id':'shot01','rental_id':rental})['id']

    def test_live_catalog_availability_and_secure_price_scope(self):
        def row(name, stock, counts, price=.5):
            return {'id':name,'displayName':name,'memoryInGb':24,'secureCloud':True,
                    'lowestPrice':{'stockStatus':stock,'availableGpuCounts':counts,'uninterruptablePrice':price}}
        payload={'data':{'gpuTypes':[row('in-stock','Low',[1,2]),row('multi-only','High',[2]),
            row('count-null','Medium',None),row('count-empty','High',[]),
            row('none','None',[1]),row('unknown',None,[1]),row('no-price','High',[1],None),
            row('nan-price','High',[1],float('nan'))]}}
        with patch.object(gpu,'request',return_value=payload) as request:
            result=gpu.catalog()
        self.assertEqual({r['id'] for r in result if r['available']},{'in-stock','count-null'})
        self.assertEqual(len(result),8)
        query=request.call_args.args[2]['query']
        self.assertIn('secureCloud:true',query)
        self.assertIn('minDisk:50',query)
        with patch.object(gpu,'request',return_value={'data':{}}):
            with self.assertRaises(ApiError):gpu.catalog()

    def test_unavailable_gpu_rejected_before_rental_preview(self):
        with patch.object(gpu,'catalog',return_value=[{'id':'sold-out','available':False}]):
            with self.assertRaises(ApiError) as error:
                gpu.preview('writer','demo',{'gpu_id':'sold-out','minutes':30,'max_usd':10})
        self.assertEqual(error.exception.status,409)
        self.assertEqual(gpu.list_rentals(),[])

    def test_all_timing_values_reset_to_pending(self):
        import video_estimates as estimates
        for name in ('RTX 4090','RTX 5090','RTX 2000 Ada','unknown'):
            for steps in (20,50):
                rows=estimates.generation(name,steps)
                self.assertEqual([r['video_seconds'] for r in rows],[5,10,15])
                self.assertTrue(all(r['status']=='pending' and r['min_minutes'] is None and r['max_minutes'] is None for r in rows))
        meta=estimates.methodology()
        self.assertIsNone(meta['cold_start']['cached_minutes'])
        self.assertIsNone(meta['cold_start']['first_download_minutes'])
        self.assertNotIn('source',meta)
        self.assertNotIn('MiniMax',json.dumps(meta))
        self.assertEqual(meta['recommendation']['gpu'],'A100')
        self.assertEqual(meta['recommendation']['generation_minutes'],[10,20])
        self.assertTrue(meta['recommendation']['excludes_cold_start'])
        self.assertIn('项目方',meta['recommendation']['basis'])

    def test_catalog_endpoint_reports_fresh_timestamp_and_estimates(self):
        with patch.object(gpu,'catalog',return_value=[{'name':'RTX 4090','id':'4090','available':True}]):
            before=time.time()
            response=self.call('/api/gpu/catalog',username='writer',method='GET')
        self.assertGreaterEqual(response['queried_at'],before)
        self.assertEqual(response['gpu_count'],1)
        self.assertEqual(len(response['gpus'][0]['estimates']['50']),3)
        with store.db() as c:c.execute("UPDATE accounts SET gpu_allowed=0 WHERE username='writer'")
        with self.assertRaises(ApiError):self.call('/api/gpu/catalog',username='writer',method='GET')

    def test_monitor_live_refresh_is_read_only_and_preserves_zero(self):
        identifier=self.rental(age=300)
        before=gpu.get(identifier)
        payload={'data':{'p0':{'desiredStatus':'RUNNING','runtime':{
            'uptimeInSeconds':123,'gpus':[{'id':'g','gpuUtilPercent':0,'memoryUtilPercent':70}],
            'container':{'cpuPercent':10,'memoryPercent':20}}}}}
        with patch.object(gpu,'request',return_value=payload) as request:
            result=self.call('/api/gpu/monitor',username='writer',method='GET')
        item=result['rentals'][0]
        self.assertEqual(item['monitor_state'],'live')
        self.assertEqual(item['runtime']['gpus'][0]['gpuUtilPercent'],0)
        self.assertIsNotNone(item['queried_at'])
        self.assertEqual(gpu.get(identifier),before)
        self.assertEqual(request.call_args.args[0],'POST')
        self.assertTrue(request.call_args.kwargs['graphql'])
        self.assertTrue(request.call_args.args[2]['query'].startswith('query('))
        self.assertNotIn('mutation',request.call_args.args[2]['query'])

    def test_monitor_scopes_provider_query_and_results_to_owner(self):
        own=self.rental();other=self.rental()
        with store.db() as c:c.execute("UPDATE rentals SET username='admin',pod_id='privatepod' WHERE id=?",(other,))
        with patch.object(gpu,'request',return_value={'data':{'p0':None}}) as request:
            result=self.call('/api/gpu/monitor',username='writer',method='GET')
        self.assertEqual([r['id'] for r in result['rentals']],[own])
        self.assertNotIn('privatepod',request.call_args.args[2]['variables'].values())
        with patch.object(gpu,'request',return_value={'data':{'p0':None,'p1':None}}):
            self.assertEqual(len(self.call('/api/gpu/monitor',method='GET')['rentals']),2)

    def test_monitor_failure_never_reports_cached_runtime_as_live(self):
        identifier=self.rental();row=gpu.get(identifier)
        row['detail']['runtime']={'gpus':[{'gpuUtilPercent':99}]}
        gpu.save(identifier,detail=row['detail'])
        with patch.object(gpu,'request',side_effect=ApiError(502,'unavailable')):
            item=self.call('/api/gpu/monitor',username='writer',method='GET')['rentals'][0]
        self.assertEqual(item['monitor_state'],'error')
        self.assertIsNone(item['runtime'])
        self.assertIsNone(item['queried_at'])
        self.assertEqual(gpu.get(identifier)['detail']['runtime']['gpus'][0]['gpuUtilPercent'],99)

    def test_monitor_no_instances_no_provider_call_and_pending_not_zero(self):
        with patch.object(gpu,'request') as request:
            self.assertEqual(self.call('/api/gpu/monitor',method='GET')['rentals'],[])
            request.assert_not_called()
        self.rental()
        with patch.object(gpu,'request',return_value={'data':{'p0':{'desiredStatus':'RUNNING','runtime':None}}}):
            item=self.call('/api/gpu/monitor',username='writer',method='GET')['rentals'][0]
        self.assertEqual(item['monitor_state'],'pending')
        self.assertIsNone(item['runtime'])

    def test_h3_pause_blocks_new_and_previously_prepared_jobs(self):
        rental=self.rental();identifier=self.job(rental)
        balance=store.account('writer')['balance']
        store.save_settings({'h3_paused':True,'video_ready':True})
        with self.assertRaises(ApiError):
            video.preview('writer','demo',1,{'job_id':'shot01','rental_id':rental})
        with patch.object(video.threading,'Thread') as thread:
            with self.assertRaises(ApiError):video.start('writer',identifier,True)
            thread.assert_not_called()
        self.assertEqual(store.account('writer')['balance'],balance)
        self.assertEqual(video.get(identifier)['status'],'preview')
        info=self.call('/api/gpu',username='writer',method='GET')
        self.assertTrue(info['h3_paused']);self.assertFalse(info['video_ready'])
        with self.assertRaises(ApiError):self.call('/api/admin/settings',{'video_ready':True})

    def test_help_answers_saved_durably_before_return(self):
        import help_chat, help_history
        from unittest.mock import patch
        cid='a'*32
        with patch.object(help_chat.ai_prompt,'run_text',return_value='真实回答'):
            result=help_chat.answer('writer',{'question':'怎么使用？','page':'production','conversation_id':cid,
                'history':[{'role':'assistant','content':'客户端伪造的回答'}]})
            help_chat.answer('writer',{'question':'接下来呢？','page':'guide','conversation_id':cid})
        rows=help_history.listing()['records']
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['answer']=='真实回答' and r['status']=='done' for r in rows))
        self.assertEqual(result['conversation_id'],cid)
        self.assertEqual(rows[0]['username'],'writer')
        self.assertEqual((Path(auth.DATA_DIR)/'help_conversations.sqlite3').stat().st_mode & 0o777,0o600)
        with help_history.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM exchanges').fetchone()[0],2)

    def test_help_history_admin_only_and_conversation_owner(self):
        import help_chat, help_history
        with patch.object(help_chat.ai_prompt,'run_text',return_value='answer'):
            help_chat.answer('writer',{'question':'hello','conversation_id':'b'*32})
            with self.assertRaises(ApiError):help_chat.answer('admin',{'question':'forged session','conversation_id':'b'*32})
        with self.assertRaises(ApiError):self.call('/api/admin/help-conversations',username='writer',method='GET')
        result=self.call('/api/admin/help-conversations',method='GET')
        self.assertEqual(len(result['records']),1)

    def test_help_failure_recorded_without_fabricated_answer(self):
        import help_chat, help_history
        with patch.object(help_chat.ai_prompt,'run_text',side_effect=RuntimeError('provider failed')):
            with self.assertRaises(ApiError):help_chat.answer('writer',{'question':'question'})
        row=help_history.listing()['records'][0]
        self.assertEqual(row['status'],'failed');self.assertIsNone(row['answer'])
        self.assertNotIn('writer',help_chat._active)

    def test_help_history_filters_and_paginates_without_dropping_records(self):
        import help_history
        with help_history.db() as c:
            for i in range(55):c.execute("INSERT INTO exchanges(conversation_id,username,page,question,model,status,created_at) VALUES(?,?,?,?,?,?,?)",('c'*32,'writer','home',str(i),'test','done',i))
        first=help_history.listing(username='writer');second=help_history.listing(username='writer',before=first['next_before'])
        self.assertEqual(len(first['records']),50);self.assertEqual(len(second['records']),5)
        self.assertFalse({r['id'] for r in first['records']} & {r['id'] for r in second['records']})
        self.assertEqual(help_history.listing(username='admin')['records'],[])
        self.assertEqual(help_history.listing(conversation_id='d'*32)['records'],[])
        with self.assertRaises(ApiError):help_history.listing(before='invalid')

    def test_disabled_session_never_revives(self):
        cookie=auth.make_session_cookie_value('writer')
        self.assertEqual(auth.verify_session_cookie_value(cookie),'writer')
        store.set_enabled('writer',False)
        self.assertIsNone(auth.verify_session_cookie_value(cookie))
        self.assertFalse(auth.verify_password('writer','twelve-letters-password'))
        store.set_enabled('writer',True)
        self.assertIsNone(auth.verify_session_cookie_value(cookie))

    def test_admin_only_and_secret_redaction(self):
        with self.assertRaises(ApiError) as error:self.call('/api/admin/overview',username='writer',method='GET')
        self.assertEqual(error.exception.status,403)
        info=self.call('/api/admin/overview',method='GET')
        self.assertNotIn('smtp_password',info['settings'])
        self.assertTrue(info['settings']['smtp_password_configured'])
        with self.assertRaises(ApiError):self.call('/api/admin/users/admin/enabled',{'enabled':False})

    def test_allocation_idempotent_and_concurrent_balance(self):
        store.allocate('writer',10,'admin','unique-credit')
        store.allocate('writer',10,'admin','unique-credit')
        self.assertEqual(store.account('writer')['balance'],1010)
        with self.assertRaises(ApiError):store.allocate('writer',20,'admin','unique-credit')
        def reserve(i):
            try:store.reserve('writer','demo','video',identifier='v'+str(i));return True
            except ApiError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:success=list(pool.map(reserve,range(8)))
        self.assertEqual(sum(success),3)
        self.assertEqual(store.account('writer')['balance'],110)

    def test_partial_refund_and_settlement_once(self):
        store.reserve('writer','demo','image',3,identifier='partial')
        store.started('partial');store.settle('partial','failed',1);store.settle('partial','done',3)
        self.assertEqual(store.account('writer')['balance'],990)
        self.assertEqual(store.account('writer')['held'],0)

    def test_feature_and_approval_owner(self):
        store.set_features('writer',{'image':False})
        with self.assertRaises(ApiError):store.reserve('writer','demo','image')
        approval=approvals.preview(self.project,{},'writer')
        submit=Mock()
        with self.assertRaises(ValueError):approvals.execute(self.project,approval['id'],'admin',submit)
        submit.assert_not_called()

    def test_idle_600_seconds_requests_stop_and_requires_confirmation(self):
        identifier=self.rental(601)
        def request(method,path,*args,**kwargs):
            if path=='/pods/pod123' and method=='GET':return {'costPerHr':.5}
            return {}
        with patch.object(gpu,'request',side_effect=request) as provider:
            gpu.tick()
            self.assertIn(('DELETE','/pods/pod123'),[c.args for c in provider.call_args_list])
        self.assertEqual(gpu.get(identifier)['status'],'stopping')
        with patch.object(gpu,'request',side_effect=ApiError(404,'gone')):gpu.tick()
        self.assertEqual(gpu.get(identifier)['status'],'terminated')

    def test_active_video_defers_idle_and_completion_resets_clock(self):
        identifier=self.rental(601);task=self.job(identifier)
        with patch.object(video,'kick'):video.start('writer',task,True)
        with patch.object(gpu,'request',return_value={'costPerHr':.5}) as provider:gpu.tick()
        self.assertFalse(any(c.args[0]=='DELETE' for c in provider.call_args_list))
        self.assertEqual(gpu.get(identifier)['status'],'running')

    def test_hard_expiry_stops_even_busy(self):
        identifier=self.rental();task=self.job(identifier)
        with patch.object(video,'kick'):video.start('writer',task,True)
        gpu.save(identifier,expires_at=time.time()-1)
        with patch.object(gpu,'request',return_value={'costPerHr':.5}) as provider:gpu.tick()
        self.assertTrue(any(c.args[0]=='DELETE' for c in provider.call_args_list))

    def test_video_duplicate_start_once_and_cancel_refund(self):
        identifier=self.rental();task=self.job(identifier)
        with patch.object(video,'kick') as start:
            video.start('writer',task,True);video.start('writer',task,True)
            start.assert_called_once()
        self.assertEqual(store.account('writer')['balance'],700)
        with patch.object(gpu,'request',side_effect=ApiError(404,'gone')):gpu.stop(identifier)
        self.assertEqual(store.account('writer')['balance'],1000)
        self.assertEqual(video.get(task)['status'],'cancelled')

    def test_changed_reference_rejected_before_charge(self):
        identifier=self.rental();task=self.job(identifier)
        (self.project/'frame.png').write_bytes(b'changed')
        with self.assertRaises(ApiError):video.start('writer',task,True)
        self.assertEqual(store.account('writer')['balance'],1000)

    def test_reference_escape_rejected(self):
        secret=self.root/'secret';secret.write_text('private')
        with self.assertRaises(ApiError):video.condition_path('demo',str(secret))
        with self.assertRaises(ApiError):video.condition_path('demo','https://example.com/frame')

    def test_notification_only_after_confirmed_gpu_and_recipient_fixed(self):
        identifier=self.rental()
        self.assertEqual(notifications.status()['counts'],{})
        store.gpu_notification(identifier);store.gpu_notification(identifier)
        store.save_settings({'mail_to':'other@example.com'})
        with patch.object(notifications,'send') as send:notifications.deliver_one()
        self.assertEqual(send.call_args.args[0]['To'],'j18210070075@gmail.com')
        self.assertIn('正在使用显卡',send.call_args.args[0]['Subject'])
        self.assertEqual(notifications.status()['counts'],{'sent':1})

    def test_mail_failure_persists_retry(self):
        identifier=self.rental();store.gpu_notification(identifier)
        with patch.object(notifications,'send',side_effect=OSError('secret must not leak')):notifications.deliver_one()
        result=notifications.status()
        self.assertEqual(result['counts'],{'failed':1})
        self.assertNotIn('secret',json.dumps(result))

    def test_start_requires_cost_confirmation_and_mail(self):
        with patch.object(gpu,'catalog',return_value=[{'id':'test','name':'Test','hourly_usd':.5,'available':True}]):
            row=gpu.preview('writer','demo',{'gpu_id':'test','minutes':60,'max_usd':10})
        with patch.object(gpu,'_create') as create:
            with self.assertRaises(ApiError):gpu.start('writer',row['id'],False)
            store.save_settings({'smtp_password':''})
            with self.assertRaises(ApiError):gpu.start('writer',row['id'],True)
            create.assert_not_called()

    def test_video_success_and_ambiguous_submit_not_repeated(self):
        identifier=self.rental();task=self.job(identifier)
        with patch.object(video,'kick'):video.start('writer',task,True)
        @contextmanager
        def tunnel(row):yield 'http://localhost'
        def download(endpoint,remote,dest):dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b'mp4')
        with patch.object(video,'tunnel',tunnel),patch.object(video,'http',side_effect=[{'id':'remote'},{'status':'completed'}]),patch.object(video,'download',side_effect=download):
            video.worker(task)
        self.assertEqual(video.get(task)['status'],'done')
        self.assertEqual(store.account('writer')['balance'],700)
        second=self.job(identifier)
        with patch.object(video,'kick'):video.start('writer',second,True)
        with patch.object(video,'tunnel',tunnel),patch.object(video,'http',side_effect=TimeoutError) as request:
            video.worker(second);video.worker(second)
            self.assertEqual(request.call_count,1)
        self.assertEqual(video.get(second)['status'],'running')

    def test_http_enforces_admin_feature_disable_and_cross_origin(self):
        server=app.Server(('127.0.0.1',0),app.Handler);server.secure_cookies=False
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        cookie=auth.make_session_cookie_value('writer')
        def request(method,path,body=None,origin=None):
            connection=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Cookie':auth.SESSION_COOKIE_NAME+'='+cookie,'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            connection.request(method,path,json.dumps(body or {}) if method=='POST' else None,headers)
            response=connection.getresponse();status=response.status;response.read();connection.close();return status
        try:
            with patch.object(app.Handler,'log_message'):
                self.assertEqual(request('GET','/api/admin/overview'),403)
                self.assertEqual(request('GET','/api/usage'),200)
                store.set_features('writer',{'create':False})
                self.assertEqual(request('POST','/api/projects',{}),403)
                self.assertEqual(request('POST','/api/projects',{},'https://other.example'),403)
                store.set_enabled('writer',False)
                self.assertEqual(request('GET','/api/usage'),401)
                self.assertEqual(request('GET','/media/demo/frame.png'),401)
                self.assertEqual(request('GET','/index.html'),302)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
