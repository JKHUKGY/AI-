"""Trial adapter of skill ltx_batch.py: same pipeline, one model load, audited job inbox."""
import gc, json, logging, os, sys, time, traceback
from pathlib import Path

import torch
from ltx_core.model.video_vae import AUTO_TILING, get_video_chunks_number
from ltx_pipelines.distilled import DistilledPipeline
from ltx_pipelines.utils.args import add_generated_keyframes_arg, default_2_stage_distilled_arg_parser, resolve_cli_params
from ltx_pipelines.utils.media_io import encode_video, resolve_hdr_color_space, vae_dtype_for_hdr

work=Path(sys.argv[1]); initial=json.loads((work/'initial_request.json').read_text())
sys.argv=[sys.argv[0]]+initial['argv']
logging.basicConfig(level=logging.INFO)
params=resolve_cli_params(distilled=True)
parser=add_generated_keyframes_arg(default_2_stage_distilled_arg_parser(params=params,supports_auto_duration=True))
a0=parser.parse_args(initial['argv'])
print('[worker] loading pipeline once',flush=True)
pipeline=DistilledPipeline(model_paths=a0.model_paths,spatial_upsampler_path=a0.spatial_upsampler_path,
    loras=tuple(a0.lora) if getattr(a0,'lora',None) else (),quantization=a0.quantization,
    compilation_config=a0.compile,offload_mode=a0.offload_mode,prompt_enhancer_gemma_root=a0.prompt_enhancer_gemma_root,
    diffvae_optimization=a0.diffvae_optimization)
(work/'pipeline_ready').write_text(str(time.time()))
print('[worker] pipeline ready',flush=True)
idle=time.monotonic()
while True:
    if (work/'STOP').exists(): break
    reqs=sorted((work/'requests').glob('*.json'))
    if not reqs:
        if time.monotonic()-idle>600:
            print('[worker] inbox idle for 600s, exiting',flush=True);break
        time.sleep(2);continue
    p=reqs[0];job=json.loads(p.read_text());p.rename(work/'claimed'/p.name)
    args=parser.parse_args(job['argv']);start=time.time()
    result_info={'id':job['id'],'started_at':start}
    print('[worker] START '+job['id'],flush=True)
    try:
        with torch.inference_mode():
            hdr=resolve_hdr_color_space(images=args.images,hdr=args.hdr)
            result=pipeline(prompt=args.prompt,seed=args.seed,height=args.height,width=args.width,
                num_frames=args.num_frames,frame_rate=args.frame_rate,images=args.images,
                vae_dtype=vae_dtype_for_hdr(hdr,torch.bfloat16),color_space=hdr,
                enhance_prompt=args.enhance_prompt,enhance_static_cache=args.enhance_static_cache,
                tiling_config=AUTO_TILING,generated_keyframes=args.num_generated_keyframes)
            encode_video(video=result.video,fps=args.frame_rate,audio=result.audio,output_path=args.output_path,
                video_chunks_number=get_video_chunks_number(result.num_frames,result.tiling_config),color_space=hdr)
            del result
        result_info.update(status='done',output=args.output_path,seconds=round(time.time()-start,2))
    except Exception as e:
        traceback.print_exc();result_info.update(status='failed',error=str(e),seconds=round(time.time()-start,2))
    gc.collect();torch.cuda.empty_cache()
    temp=work/'results'/f"{job['id']}.tmp"
    temp.write_text(json.dumps(result_info));temp.replace(temp.with_suffix('.json'))
    print('[worker] '+json.dumps(result_info),flush=True)
    idle=time.monotonic()
print('[worker] finished',flush=True)
