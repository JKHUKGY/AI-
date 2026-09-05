#!/usr/bin/env python3
"""一次加载模型、循环跑完多个生成任务（省掉每镜重复加载 67GB 权重的时间）。

结构严格镜像 ltx_pipelines/distilled.py 的 main()：唯一区别是
DistilledPipeline(...) 只构造一次，然后对每个 job 调用一次 pipeline(...) + encode_video(...)。

用法（在远程 /workspace/LTX-2 下）：
    .venv/bin/python ltx_batch.py batch_args.json
batch_args.json 格式：[{"id": "...", "argv": ["--transformer-path", "...", "--prompt", "...", ...]}, ...]
argv 就是原来单镜 CLI 里 `-m ltx_pipelines.distilled` 之后的全部参数。
"""
import json, logging, sys, time, traceback

import torch
from ltx_core.model.video_vae import AUTO_TILING, get_video_chunks_number
from ltx_pipelines.distilled import DistilledPipeline
from ltx_pipelines.utils.args import (
    add_generated_keyframes_arg,
    default_2_stage_distilled_arg_parser,
    resolve_cli_params,
)
from ltx_pipelines.utils.media_io import encode_video, resolve_hdr_color_space, vae_dtype_for_hdr


def main():
    logging.basicConfig(level=logging.INFO)
    jobs = json.load(open(sys.argv[1]))
    # resolve_cli_params() 会去读 sys.argv 判断是 monolith 还是 split checkpoint，
    # 所以必须先把任意一个 job 的 argv 放进 sys.argv，否则报
    # "Missing --distilled-checkpoint-path (monolith) or --transformer-path (split)"。
    sys.argv = [sys.argv[0]] + jobs[0]["argv"]
    params = resolve_cli_params(distilled=True)
    parser = add_generated_keyframes_arg(
        default_2_stage_distilled_arg_parser(params=params, supports_auto_duration=True)
    )
    parsed = [(j["id"], parser.parse_args(j["argv"])) for j in jobs]

    a0 = parsed[0][1]
    t0 = time.time()
    print(f"[batch] 构造 pipeline（只做一次）…", flush=True)
    pipeline = DistilledPipeline(
        model_paths=a0.model_paths,
        spatial_upsampler_path=a0.spatial_upsampler_path,
        loras=tuple(a0.lora) if getattr(a0, "lora", None) else (),
        quantization=a0.quantization,
        compilation_config=a0.compile,
        offload_mode=a0.offload_mode,
        prompt_enhancer_gemma_root=a0.prompt_enhancer_gemma_root,
        diffvae_optimization=a0.diffvae_optimization,
    )
    print(f"[batch] pipeline 就绪，用时 {time.time()-t0:.0f}s", flush=True)

    results = []
    for idx, (job_id, args) in enumerate(parsed, 1):
        s = time.time()
        try:
            hdr = resolve_hdr_color_space(images=args.images, hdr=args.hdr)
            vae_dtype = vae_dtype_for_hdr(hdr, torch.bfloat16)
            result = pipeline(
                prompt=args.prompt, seed=args.seed,
                height=args.height, width=args.width,
                num_frames=args.num_frames, frame_rate=args.frame_rate,
                images=args.images, vae_dtype=vae_dtype, color_space=hdr,
                enhance_prompt=args.enhance_prompt,
                enhance_static_cache=args.enhance_static_cache,
                tiling_config=AUTO_TILING,
                generated_keyframes=args.num_generated_keyframes,
            )
            encode_video(
                video=result.video, fps=args.frame_rate, audio=result.audio,
                output_path=args.output_path,
                video_chunks_number=get_video_chunks_number(result.num_frames, result.tiling_config),
                color_space=hdr,
            )
            dt = time.time() - s
            print(f"[batch] ({idx}/{len(parsed)}) DONE {job_id} -> {args.output_path} 用时 {dt:.0f}s", flush=True)
            results.append({"id": job_id, "status": "ok", "seconds": round(dt, 1),
                            "output": args.output_path})
            import gc
            del result
            gc.collect(); torch.cuda.empty_cache()
        except Exception as e:
            traceback.print_exc()
            # 失败后必须清显存，否则残留的分配会让**后续每一个** job 在加载权重阶段
            # 就 OOM（实测：镜14 生成失败后残留 77GB，镜25 连权重都没加载完就爆了）。
            try:
                import gc
                gc.collect(); torch.cuda.empty_cache()
            except Exception:
                pass
            print(f"[batch] ({idx}/{len(parsed)}) FAIL {job_id}: {e}", flush=True)
            results.append({"id": job_id, "status": "error", "error": str(e)})
    json.dump(results, open("batch_results.json", "w"), ensure_ascii=False, indent=2)
    print(f"[batch] 全部结束，总用时 {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
