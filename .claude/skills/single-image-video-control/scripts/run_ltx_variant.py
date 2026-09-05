"""Run one A/B variant inside an already provisioned official LTX environment.

No rental, upload, or shutdown is performed here. The calling orchestrator owns
resource cleanup even if this process fails. This script defaults to dry-run;
--execute runs the model using the supplied checkpoint paths.
"""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil
import subprocess
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--jobs', type=Path, required=True)
    ap.add_argument('--job-id')
    ap.add_argument('--weights', type=Path, required=True)
    ap.add_argument('--first-frame', type=Path, required=True)
    ap.add_argument('--control-video', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--variant', choices=['A','B'], required=True)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    jobs = json.loads(args.jobs.read_text())
    if args.job_id:
        jobs = [j for j in jobs if j['id'] == args.job_id]
    if len(jobs) != 1:
        ap.error('Select exactly one job, using --job-id when needed')
    job = jobs[0]
    config = json.loads(args.weights.read_text())
    required = ['transformer_path','text_encoder_path','video_vae_path','audio_vae_path',
        'spatial_upsampler_path','union_lora_path']
    paths = {}
    for key in required:
        p = Path(config[key]).expanduser()
        if not p.is_absolute():
            p = args.weights.resolve().parent/p
        if not p.is_file():
            ap.error(f'Checkpoint does not exist: {key}: {p}')
        paths[key] = str(p)
    for p in [args.first_frame,args.control_video]:
        if not p.is_file():
            ap.error(f'Missing input: {p}')
    w,h,n,fps = [job[k] for k in ['width','height','num_frames','fps']]
    if w%64 or h%64 or n<9 or (n-1)%8 or fps<=0:
        ap.error('Require dimensions divisible by64, num_frames=8k+1, positivefps')
    from fractions import Fraction
    if shutil.which('ffprobe'):
        probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
            '-show_entries','stream=width,height,nb_frames,r_frame_rate','-of','json',str(args.control_video)],text=True))['streams'][0]
    else:
        # Official LTX environments already depend on PyAV; some images omit ffprobe.
        import av
        with av.open(str(args.control_video)) as container:
            stream = container.streams.video[0]
            probe = dict(width=stream.width,height=stream.height,
                nb_frames=stream.frames or sum(1 for _ in container.decode(video=0)),
                r_frame_rate=str(stream.average_rate))
    if (probe['width'],probe['height'],int(probe['nb_frames']),Fraction(probe['r_frame_rate'])) != (w,h,n,Fraction(fps)):
        ap.error('Control video metadata does not match the selected job')
    from PIL import Image
    if Image.open(args.first_frame).size != (w,h):
        ap.error('First frame dimensions do not match the selected job')
    args.out_dir.mkdir(parents=True,exist_ok=True)
    name = 'A_baseline' if args.variant=='A' else 'B_depth_control'
    target = args.out_dir/(name+'.mp4')
    record_path = args.out_dir/(name+'_runtime.json')
    record = {'variant':args.variant,'pipeline':'ltx_pipelines.ic_lora.ICLoraPipeline',
        'job_id':job['id'],'prompt':job['prompt'],'seed':job['seed'],'width':w,'height':h,
        'num_frames':n,'fps':fps,'first_frame_strength':job.get('first_frame_strength',1),
        'model_paths':paths,'declared_revisions':config.get('revisions',{}),
        'first_frame_sha256':hashlib.sha256(args.first_frame.read_bytes()).hexdigest(),
        'control_sha256':hashlib.sha256(args.control_video.read_bytes()).hexdigest(),
        'offload_mode':'cpu','enhance_prompt':False,'skip_stage_2':False,
        'union_and_depth_enabled':args.variant=='B','conditioning_attention_strength':1.0,
        'generation_calls':0,'status':'dry_run'}
    print(json.dumps(record,ensure_ascii=False,indent=2),flush=True)
    if not args.execute:
        return
    logging.basicConfig(level=logging.INFO)
    started = time.time()
    record['started_at_unix'] = started
    try:
        import torch
        from ltx_pipelines.ic_lora import ICLoraPipeline
        from ltx_pipelines.utils.types import OffloadMode
        from ltx_pipelines.utils.model_paths import ModelPaths
        from ltx_pipelines.utils.args import ImageConditioningInput,LoraPathStrengthAndSDOps,LTXV_LORA_COMFY_RENAMING_MAP
        from ltx_core.model.video_vae import AUTO_TILING,get_video_chunks_number
        from ltx_pipelines.utils.media_io import encode_video
        record['torch_version'] = torch.__version__
        record['gpu'] = torch.cuda.get_device_name(0)
        # Official CLI decorates main: include lazy decoding/encoding in this scope.
        with torch.inference_mode():
            record['inference_mode_enabled'] = torch.is_inference_mode_enabled()
            pipeline = ICLoraPipeline(
                model_paths=ModelPaths.from_split(**{k:paths[k] for k in required[:4]}),
                spatial_upsampler_path=paths['spatial_upsampler_path'],
                loras=[LoraPathStrengthAndSDOps(paths['union_lora_path'],1.,LTXV_LORA_COMFY_RENAMING_MAP)] if args.variant=='B' else [],
                offload_mode=OffloadMode.CPU)
            record['reference_downscale_factor'] = pipeline.reference_downscale_factor
            record['generation_calls'] = 1
            record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2))
            result = pipeline(prompt=job['prompt'],seed=job['seed'],height=h,width=w,
                num_frames=n,frame_rate=fps,
                images=[ImageConditioningInput(str(args.first_frame),0,job.get('first_frame_strength',1))],
                video_conditioning=[(str(args.control_video),1.)] if args.variant=='B' else [],
                enhance_prompt=False,vae_dtype=torch.bfloat16,tiling_config=AUTO_TILING,
                conditioning_attention_strength=1.,skip_stage_2=False)
            encode_video(video=result.video,fps=fps,audio=result.audio,output_path=str(target),
                video_chunks_number=get_video_chunks_number(result.num_frames,result.tiling_config))
        record['status']='success'
        record['output_bytes']=target.stat().st_size
    except BaseException as error:
        record['status']='error'
        record['error']=repr(error)
        raise
    finally:
        record['elapsed_seconds']=time.time()-started
        record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
