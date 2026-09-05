"""Sequential RunPod trial: skill-built argv, one model load, reviewed tail dependencies, finally teardown."""
import hashlib, importlib.util, json, os, shlex, subprocess, sys, time, traceback
from pathlib import Path

ROOT=Path('/workspaces/AI-'); OUT=Path(__file__).resolve().parent
os.chdir(ROOT);os.environ['PATH']=str(OUT/'bin')+':'+os.environ['PATH']
CFG=json.loads((OUT/'ltx_remote_config.json').read_text()); REMOTE=CFG['remote_work_dir']
def module(name,path):
    s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
submit=module('submit','.agents/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py')
builder=module('builder','.agents/skills/short-drama-video-gen/scripts/build_prompt.py')
clips=OUT/'clips';clips.mkdir(exist_ok=True)
frames=OUT/'review_frames';frames.mkdir(exist_ok=True)
tails=OUT/'tail_frames';tails.mkdir(exist_ok=True)
(OUT/'results').mkdir(exist_ok=True)
(OUT/'tail_reviews').mkdir(exist_ok=True)
start=time.time(); results=json.loads((OUT/'generation_results.json').read_text()) if (OUT/'generation_results.json').exists() else []
state={'status':'running','started_at':start,'total_units':20,'completed':0,'pod_id':CFG['instance_id']}
def save(**kw):
    state.update(kw);state['updated_at']=time.time()
    p=OUT/'status.tmp';p.write_text(json.dumps(state,ensure_ascii=False,indent=2));p.replace(OUT/'status.json')
def run(args,timeout=120):
    r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if r.returncode:raise RuntimeError((r.stderr or r.stdout)[-2500:])
    return r.stdout
def ssh(command,timeout=60):return run(submit.ssh_base(CFG)+[command],timeout)
def read_result(ident):
    cmd='python3 -c '+shlex.quote("from pathlib import Path; p=Path("+repr(REMOTE+'/results/'+ident+'.json')+"); print(p.read_text() if p.exists() else '{}')")
    try:return json.loads(ssh(cmd))
    except Exception as e:
        save(connection_warning=str(e));return {}
def until_result(ident):
    while True:
        if time.time()-start>7200:raise TimeoutError('Trial exceeded two-hour controller limit')
        r=read_result(ident)
        if r:return r
        save(current_unit=ident,phase='remote_generation')
        time.sleep(15)
def wait_review(path,phase):
    began=time.time()
    while not path.exists():
        if time.time()-began>900:raise TimeoutError('Review gate waited 900 seconds: '+str(path))
        save(phase=phase,review_gate=str(path));time.sleep(5)
    return json.loads(path.read_text())

try:
    cards=json.loads((OUT/'shot_cards.json').read_text())
    for idx,c in enumerate(cards):
        ident=c['id']
        if any(r['id']==ident for r in results):
            continue
        save(current_unit=ident,phase='preparing',completed=len(results))
        if c.get('first_frame_from'):
            prev=c['first_frame_from'].removesuffix(':last'); tail=tails/(prev+'.png')
            assert tail.exists()
            gate=wait_review(OUT/'tail_reviews'/(ident+'.json'),'waiting_tail_review')
            assert gate['approved'] is True and gate.get('state_zh')
            c['first_frame']=str(tail);c['first_frame_state_zh']=gate['state_zh']
            c['first_frame_state_basis']='observed_generated_tail'
            c['readiness']['status']='tail_reviewed_for_trial'
            c['notes']+=' 已实际查看前段最后一帧后续接；尾帧审阅记录见 tail_reviews。'
            (OUT/'shot_cards.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2)+'\n')
            proc=subprocess.run(['python3',str(ROOT/'.agents/skills/short-drama-video-gen/scripts/build_prompt.py'),str(OUT/'shot_cards.json'),'-o',str(OUT/'video_jobs.json')],capture_output=True,text=True)
            (OUT/f'build_after_{ident}.log').write_text(proc.stdout+proc.stderr)
            if proc.returncode:raise RuntimeError('Card build failed after tail adoption')
            submit.upload(CFG,str(tail),REMOTE+'/'+ident+'_first.png')
        jobs=json.loads((OUT/'video_jobs.json').read_text());job=next(j for j in jobs if j['id']==ident)
        assert job['prompt']==builder.build_prompt(c)
        (OUT/'active_job.json').write_text(json.dumps([job],ensure_ascii=False,indent=2))
        validation=subprocess.run(['python3',str(ROOT/'.agents/skills/short-drama-ltx-export/scripts/validate_video_jobs.py'),str(OUT/'active_job.json')],capture_output=True,text=True)
        (OUT/f'validate_{ident}.log').write_text(validation.stdout+validation.stderr)
        if validation.returncode:raise RuntimeError('Export validation failed: '+ident)
        if idx>0:
            cmd=submit.build_remote_cmd(CFG,job,REMOTE+'/'+ident+'_first.png',None,REMOTE+'/'+ident+'.mp4')
            args=shlex.split(cmd.split(' && ')[-1]);args=args[args.index(CFG['pipeline_module'])+1:]
            request=OUT/'request.json';request.write_text(json.dumps({'id':ident,'argv':args},ensure_ascii=False))
            remote_tmp=REMOTE+f'/requests/{idx+1:03}.tmp'
            submit.upload(CFG,str(request),remote_tmp)
            ssh('mv '+shlex.quote(remote_tmp)+' '+shlex.quote(remote_tmp.removesuffix('.tmp')+'.json'))
        remote_result=until_result(ident)
        (OUT/'results'/(ident+'.json')).write_text(json.dumps(remote_result,ensure_ascii=False,indent=2))
        if remote_result['status']!='done':raise RuntimeError('Remote generation failed: '+json.dumps(remote_result))
        local=clips/(ident+'.mp4');submit.download(CFG,REMOTE+'/'+ident+'.mp4',str(local))
        probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(local)]))
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        assert (video['width'],video['height'])==(job['width'],job['height'])
        assert int(video['nb_frames'])==job['num_frames'],(ident,video['nb_frames'],job['num_frames'])
        folder=frames/ident
        run(['python3',str(ROOT/'.agents/skills/short-drama-video-gen/scripts/extract_frames.py'),str(local),'--out-dir',str(folder),'--count','5'])
        tail=tails/(ident+'.png')
        run(['ffmpeg','-v','error','-y','-i',str(local),'-vf',f"select=eq(n\\,{job['num_frames']-1})",'-frames:v','1',str(tail)])
        aud=subprocess.run(['ffmpeg','-hide_banner','-i',str(local),'-vn','-af','volumedetect','-f','null','-'],capture_output=True,text=True)
        (folder/'audio_levels.txt').write_text(aud.stderr)
        (folder/'probe.json').write_text(json.dumps(probe,indent=2))
        # Contact sheet is a review aid made from decoded video frames, not a replacement keyframe.
        from PIL import Image,ImageOps,ImageDraw
        imgs=sorted(folder.glob('*_frame*.png'));sheet=Image.new('RGB',(288*5,544),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for k,p in enumerate(imgs):
            im=Image.open(p).convert('RGB');im.thumbnail((288,512));sheet.paste(im,(288*k,24));draw.text((288*k+8,5),f'{ident} frame {k}',fill='black')
        sheet.save(folder/'contact.jpg',quality=92)
        record={**remote_result,'local_video':str(local),'sha256':hashlib.sha256(local.read_bytes()).hexdigest(),
            'video_frames':int(video['nb_frames']),'resolution':[video['width'],video['height']],
            'audio_stream_present':any(s['codec_type']=='audio' for s in probe['streams']),
            'contact_sheet':str(folder/'contact.jpg'),'visual_review':'pending','speech_content_review':'pending'}
        results.append(record);(OUT/'generation_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        save(completed=len(results),last_completed=ident,phase='downloaded_and_extracted')
        print('DOWNLOADED '+ident+' '+str(len(results))+'/20',flush=True)
        if idx==0:
            gate=wait_review(OUT/'pilot_review.json','waiting_first_clip_review')
            assert gate['continue_trial'] is True
    ssh('touch '+shlex.quote(REMOTE+'/STOP'))
    save(status='generated',phase='all_downloaded')
except BaseException as e:
    save(status='error',phase='stopping',error=str(e));traceback.print_exc()
finally:
    # Download the full remote execution log before closing our own Pod.
    try:submit.download(CFG,REMOTE+'/worker.log',str(OUT/'worker.log'))
    except Exception:pass
    result=subprocess.run(['python3',str(ROOT/'.agents/skills/short-drama-ltx-generate/scripts/gpu_teardown.py'),'--config',str(OUT/'ltx_remote_config.json'),'--platform-config',str(ROOT/'.claude/skills/short-drama-ltx-generate/runpod_config.json')],capture_output=True,text=True)
    (OUT/'teardown.log').write_text(result.stdout+result.stderr)
    save(gpu_teardown_exit_code=result.returncode,finished_at=time.time())
    print(result.stdout+result.stderr,flush=True)
