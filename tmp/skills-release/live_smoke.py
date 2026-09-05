import sys,json,time,urllib.request,urllib.error,concurrent.futures
from pathlib import Path
sys.path.insert(0,'/home/deploy/AI-/web/server')
import auth,project_setup
URL='https://scriptwriter-jia.northcentralus.cloudapp.azure.com'
USER='junzhenj'; NAME='Skills调用测试_20260905'
root=Path('/home/deploy/AI-/output')/NAME
if not root.exists():
 project_setup.create({'name':NAME,'script':'小雨推开旧书店的门，向店主索取父亲留下的信封。信封里是一张旧矿场地图。','episodes':3,'duration':30},USER)
COOKIE=auth.SESSION_COOKIE_NAME+'='+auth.make_session_cookie_value(USER,ttl=3600)
def req(path,body=None):
 data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
 request=urllib.request.Request(URL+path,data=data,headers={'Cookie':COOKIE,'Content-Type':'application/json','Origin':URL})
 with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
from urllib.parse import quote
base='/api/projects/'+quote(NAME)+'/skills'
report={'website':URL,'project':NAME,'probes':[]}
report_path=Path('/home/deploy/AI-/tmp/skills-live-report.json')
def save():report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
def wait(task):
 deadline=time.time()+2100
 while time.time()<deadline:
  tasks=req(base+'/tasks')['tasks']
  found=next((t for t in tasks if t['id']==task['id']),None)
  if found and found['status']!='running':return found
  time.sleep(2)
 raise RuntimeError('task polling timed out')
def probe(skill):
 try:
  t=wait(req(base+'/'+skill['id']+'/probe',{})['task'])
  out={'skill':skill['id'],'status':t['status'],'task_id':t['id'],'version':skill['version'],'result':t.get('result'),'error':t.get('error')}
 except Exception as e:out={'skill':skill['id'],'status':'http_error','error':str(e)}
 print(json.dumps({'skill':out['skill'],'status':out['status']},ensure_ascii=False),flush=True)
 return out
catalog=req('/api/skills');report['catalog_count']=len(catalog['skills']);assert report['catalog_count']==14
print('catalog 14; starting real model loading probes',flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for result in pool.map(probe,catalog['skills']):report['probes'].append(result);save()
preview=wait(req(base+'/short-drama-scout/preview',{'request':'仅依据项目中的书店、信封和矿场地图，原创一份三集中文故事大纲，保存为 output/'+NAME+'/story-outline.md。不要联网检索，不生成图片或视频，不操作其他项目。每集含开场钩子、冲突、悬念。','mode':'user_choice'})['task'])
report['preview']=preview;save();print('preview '+preview['status'],flush=True)
if preview['status']=='done':
 proposal=preview['result']['proposal']; submitted=req(base+'/execute',{'proposal':proposal,'approved':True})['task']
 duplicate=req(base+'/execute',{'proposal':proposal,'approved':True})['task'];assert duplicate['id']==submitted['id']
 report['duplicate_execution_same_task']=True
 execution=wait(submitted);report['execution']=execution;save()
 print('execution '+execution['status'],flush=True)
 if execution['status']=='done':
  artifacts=execution['result'].get('artifacts',[]);report['artifact_count']=len(artifacts)
  report['artifact_checks']=[{'path':p,'exists':(Path('/home/deploy/AI-/output')/p).is_file()} for p in artifacts]
  print('artifacts '+str(len(artifacts)),flush=True)
save()
