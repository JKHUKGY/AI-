import importlib.util,json,subprocess,time,os,sys
from pathlib import Path
R=Path('/workspaces/AI-'); T=Path(__file__).resolve().parent; D=T/'loop_runtime';D.mkdir(exist_ok=True)
s=importlib.util.spec_from_file_location('ops',R/'.agents/skills/short-drama-ltx-generate/scripts/runpod_ops.py');ops=importlib.util.module_from_spec(s);s.loader.exec_module(ops)
token=ops.load_token(R/'.claude/skills/short-drama-ltx-generate/runpod_config.json')
body={'name':'ltx25-v3-ep01-finish-loop','imageName':'runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04','gpuTypeIds':['NVIDIA A100 80GB PCIe'],'cloudType':'SECURE','containerDiskInGb':50,'ports':['22/tcp'],'env':{'PUBLIC_KEY':Path('/home/codespace/.ssh/id_ed25519.pub').read_text().strip()},'networkVolumeId':'vr1dk0uvnx','volumeMountPath':'/workspace'}
pod=None;watch=None;started=time.time()
try:
 for attempt in range(20):
  body['gpuTypeIds']=[['NVIDIA A100 80GB PCIe','NVIDIA A100-SXM4-80GB'][attempt%2]]
  try: pod=ops.rest_call(token,'POST','/pods',body)
  except Exception as e:
   print('API transient',repr(e),flush=True);time.sleep(15);continue
  if 'error' not in pod: break
  print('capacity retry',attempt+1,json.dumps(pod),flush=True);pod=None;time.sleep(20)
 if not pod: raise RuntimeError('No A100 available')
 pod['local_created_at']=time.time();(D/'pod.json').write_text(json.dumps(pod,indent=2));pid=pod['id'];print('CREATED',pid,pod.get('costPerHr'),flush=True)
 cfg=json.loads((T/'ltx_remote_config.json').read_text());cfg.update(instance_id=pid,cost_per_hr_usd=pod.get('costPerHr'))
 (D/'ltx_remote_config.json').write_text(json.dumps(cfg,indent=2))
 for n in range(80):
  st=ops.rest_call(token,'GET','/pods/'+pid)
  port=(st.get('portMappings') or {}).get('22')
  if st.get('publicIp') and port:
   cfg.update(ssh_host='root@'+st['publicIp'],ssh_port=port);(D/'ltx_remote_config.json').write_text(json.dumps(cfg,indent=2));break
  time.sleep(10)
 else: raise RuntimeError('No SSH port')
 env=dict(os.environ);env['PATH']=str(T/'bin')+':'+env['PATH']
 args=['python3','-u',str(R/'.agents/skills/short-drama-ltx-generate/scripts/idle_shutdown_watchdog.py'),'--instance-id',pid,'--ssh-host',cfg['ssh_host'],'--ssh-port',str(cfg['ssh_port']),'--platform','runpod','--runpod-config',str(R/'.claude/skills/short-drama-ltx-generate/runpod_config.json'),'--ltx-config',str(D/'ltx_remote_config.json'),'--stop-mode','terminate','--idle-seconds','900','--check-interval','20']
 watch=subprocess.Popen(args,env=env,stdout=open(D/'watchdog.log','w'),stderr=subprocess.STDOUT)
 print('READY',cfg['ssh_host'],cfg['ssh_port'],flush=True);(D/'ready.json').write_text(json.dumps(cfg))
 while not (D/'DONE').exists():
  if time.time()-started>3600:raise TimeoutError('One-hour lease deadline')
  if watch.poll() is not None:raise RuntimeError('Watchdog exited, closing lease')
  time.sleep(5)
finally:
 if watch and watch.poll() is None:watch.terminate()
 if pod and pod.get('id'):
  r=subprocess.run(['python3',str(R/'.agents/skills/short-drama-ltx-generate/scripts/gpu_teardown.py'),'--config',str(D/'ltx_remote_config.json'),'--platform-config',str(R/'.claude/skills/short-drama-ltx-generate/runpod_config.json')],capture_output=True,text=True)
  (D/'teardown.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr,flush=True)
  (D/'closed.json').write_text(json.dumps({'exit_code':r.returncode,'closed_at':time.time(),'pod_id':pod['id']}))
