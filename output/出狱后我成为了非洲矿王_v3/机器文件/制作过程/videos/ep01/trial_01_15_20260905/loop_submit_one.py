"""Single-unit submission through audited skill-built argv and warm official pipeline adapter."""
import hashlib,importlib.util,json,os,shlex,subprocess,sys,time
from pathlib import Path
R=Path('/workspaces/AI-');T=Path(__file__).resolve().parent;os.chdir(R);os.environ['PATH']=str(T/'bin')+':'+os.environ['PATH']
D=Path(sys.argv[1]).resolve();ident=sys.argv[2];rnd=int(sys.argv[3]);CF=T/'loop_runtime/ltx_remote_config.json';cfg=json.loads(CF.read_text());cfg['remote_work_dir']='/workspace/ltx_jobs/v3_ep01_loop_20260905';remote=cfg['remote_work_dir']
s=importlib.util.spec_from_file_location('submit',R/'.agents/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def run(a,t=120):
 r=subprocess.run(a,capture_output=True,text=True,timeout=t)
 if r.returncode:raise RuntimeError((r.stderr+r.stdout)[-3500:])
 return r.stdout
def ssh(c,t=120):return run(m.ssh_base(cfg)+[c],t)
for f in ['clips','results','review_frames','tail_frames']: (D/f).mkdir(exist_ok=True)
job=next(j for j in json.loads((D/'video_jobs.json').read_text()) if j['id']==ident)
card=next(c for c in json.loads((D/'shot_cards.json').read_text()) if c['id']==ident)
active=D/('active_'+ident+'.json');active.write_text(json.dumps([job],ensure_ascii=False,indent=2))
(D/('validate_'+ident+'.log')).write_text(run(['python3',str(R/'.agents/skills/short-drama-ltx-export/scripts/validate_video_jobs.py'),str(active)]))
(D/('dry_run_'+ident+'.log')).write_text(run(['python3',str(R/'.agents/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py'),'--config',str(CF),'--jobs',str(active),'--out-dir',str(D/'clips'),'--only',ident,'--dry-run']))
remoteid=ident+'_r'+str(rnd);imagepath=remote+'/'+remoteid+'_first.png';output=remote+'/'+remoteid+'.mp4'
ssh('mkdir -p '+remote+'/{requests,claimed,results}')
m.upload(cfg,job['first_frame'],imagepath)
cmd=m.build_remote_cmd(cfg,job,imagepath,None,output);args=shlex.split(cmd.split(' && ')[-1]);args=args[args.index(cfg['pipeline_module'])+1:]
req={'id':remoteid,'argv':args};request=D/('request_'+remoteid+'.json');request.write_text(json.dumps(req,ensure_ascii=False))
# Lease owns shutdown. Starting a worker here is serialized across agents.
exists=ssh("pgrep -af '[l]tx_batch_worker.py /workspace/ltx_jobs/v3_ep01_loop_20260905' || true").strip()
if not exists:
 m.upload(cfg,str(request),remote+'/initial_request.json');m.upload(cfg,str(T/'ltx_batch_worker.py'),remote+'/ltx_batch_worker.py')
 ssh('rm -f '+remote+'/STOP; cd /workspace/LTX-2 && setsid nohup .venv/bin/python -u '+remote+'/ltx_batch_worker.py '+remote+' > '+remote+'/worker.log 2>&1 < /dev/null &',30)
# Atomic queueing, resume existing result if interrupted.
resultpath=remote+'/results/'+remoteid+'.json';read='python3 -c '+shlex.quote('from pathlib import Path;p=Path('+repr(resultpath)+');print(p.read_text() if p.exists() else "{}")')
result=json.loads(ssh(read))
if not result:
 remotequeue=remote+'/requests/'+remoteid+'.json';m.upload(cfg,str(request),remotequeue+'.tmp');ssh('mv '+shlex.quote(remotequeue+'.tmp')+' '+shlex.quote(remotequeue))
start=time.time()
while not result:
 if time.time()-start>1500:raise TimeoutError(remoteid)
 time.sleep(10);result=json.loads(ssh(read));print('WAIT',remoteid,round(time.time()-start),flush=True)
if result['status']!='done':raise RuntimeError(json.dumps(result))
local=D/'clips'/(ident+'.mp4');m.download(cfg,output,str(local))
probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(local)]));v=next(s for s in probe['streams'] if s['codec_type']=='video');assert(v['width'],v['height'],int(v['nb_frames']))==(job['width'],job['height'],job['num_frames'])
folder=D/'review_frames'/ident;run(['python3',str(R/'.agents/skills/short-drama-video-gen/scripts/extract_frames.py'),str(local),'--out-dir',str(folder),'--count','5'])
run(['ffmpeg','-v','error','-y','-i',str(local),'-vf',f"select=eq(n\\,{job['num_frames']-1})",'-frames:v','1',str(D/'tail_frames'/(ident+'.png'))])
(folder/'probe.json').write_text(json.dumps(probe,indent=2))
from PIL import Image,ImageDraw
sheet=Image.new('RGB',(1440,544),'#eeeeee');draw=ImageDraw.Draw(sheet)
for k,p in enumerate(sorted(folder.glob('*_frame*.png'))):
 im=Image.open(p).convert('RGB');im.thumbnail((288,512));sheet.paste(im,(288*k,24));draw.text((288*k+8,5),f'{ident} R{rnd} frame{k}',fill='black')
sheet.save(folder/'contact.jpg',quality=92)
record={**result,'remote_id':remoteid,'id':ident,'round':rnd,'local_video':str(local),'sha256':hashlib.sha256(local.read_bytes()).hexdigest(),'video_frames':int(v['nb_frames']),'resolution':[v['width'],v['height']],'audio_stream_present':any(s['codec_type']=='audio' for s in probe['streams']),'contact_sheet':str(folder/'contact.jpg'),'visual_review':'pending','speech_content_review':'not_listened'}
(D/'results'/(ident+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2));rp=D/'generation_results.json';records=json.loads(rp.read_text()) if rp.exists() else [];records=[r for r in records if r['id']!=ident]+[record];rp.write_text(json.dumps(records,ensure_ascii=False,indent=2));print('DONE',str(local),flush=True)
