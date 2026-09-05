#!/usr/bin/env python3
"""通过 SSH 调用远程显卡上已部署好的 LTX-2.5（Lightricks LTX-2 仓库）批量
提交图生视频任务：上传首帧 -> 远程跑推理 -> 下载生成的视频。

前提（脚本不会帮你做，也不会瞎猜）：
- 远程机器已经装好 `Lightricks/LTX-2` 仓库、下载好模型权重，能跑通官方
  README 的最小示例。
- 本机能用 ssh/scp 连上远程机器（密码需提前配好免密登录，或用 --config
  里的 ssh_key 指定私钥）。
- config 里的 pipeline_module / pipeline_extra_args（尤其是模型权重路径）
  必须是用户在远程机器上确认过的真实值，不是本脚本编出来的默认值。

详细接口说明和已知的不确定项见
`.claude/skills/short-drama-ltx-generate/references/ltx_pipeline_gotchas.md`
——尤其是 --image 的三段式参数格式、--num-frames 必须 8k+1、
--negative-prompt 不是所有 pipeline 都有这几点，第一次用某个 pipeline
之前务必先在远程跑一遍 `python -m <pipeline_module> --help` 核实。

用法（正常提交生成）:
  python3 ltx_ssh_submit.py --config ltx_remote_config.json \\
      --jobs output/<故事名>/videos/ep0X/video_jobs.json \\
      --out-dir output/<故事名>/videos/ep0X \\
      [--only 11 12] [--dry-run]

用法（局部重绘，只重跑已有视频里一段时间窗口，其余画面不动，走
ltx_pipelines.retake——官方文档记载但本仓库尚未用 --help 实测确认参数名，
第一次用先看 ltx_pipeline_gotchas.md 的提醒，`--jobs`/`--only` 仍然要传，
用来定位是哪个镜头、拿它当前的 prompt/seed）:
  python3 ltx_ssh_submit.py --config ltx_remote_config.json \\
      --jobs output/<故事名>/videos/ep0X/video_jobs.json \\
      --out-dir output/<故事名>/videos/ep0X \\
      --only 11 --retake 2.0 3.0 [--dry-run]
  （要求 --out-dir 下已经有一份 <id>.mp4，即上一轮生成的结果，retake 会把
  它上传上去当输入；产物落在 <id>_retake.mp4，不覆盖原文件）

video_jobs.json 是 short-drama-video-gen/references/video_jobs_schema.md
里 JSON 版本的结构，额外需要 width/height（像素，需能被 64 整除），可选
num_frames（不填按 duration_sec * 24fps 估算，再吸附到最近的合法 8k+1
值），可选 seed，可选 first_frame_strength（首帧锁定强度，默认 1.0=完全锁死；
调低能让背景松动但首帧保真度下降，未实测，见 model_capability_ledger.md D4）。**`ref_images` 字段目前是死代码**——本脚本从未读取/上传
过这个字段，只处理 `first_frame`/`last_frame`，写了这个字段不会有任何
效果，官方真正的多参考图机制是 IC-LoRA Ingredients/Multi-Subject
Reference LoRA，需要额外权重和不同调用方式，本脚本还没接。

用法（跑完这一批就自动把显卡关掉，别继续烧钱）:
  python3 ltx_ssh_submit.py --config ltx_remote_config.json \\
      --jobs .../video_jobs.json --out-dir ... --auto-stop
  `--auto-stop` 会在这一批任务**全部跑完、结果已经下载到本地之后**（包括
  中途报错、Ctrl-C 中断这两种情况，走 finally，不会因为异常就漏掉关机）调用
  `gpu_teardown.py` 停掉实例并轮询确认真的停了。要求 config 里有 `platform`
  和 `instance_id` 两个字段，**这个检查放在提交任务之前**——宁可现在就报错，
  也不要等两小时批量任务跑完了才发现关不掉。默认 `--auto-stop-mode auto`：
  RunPod 上是 terminate（Network Volume 上的模型权重不受影响，且顺带省掉
  停止 Pod 仍在收的磁盘费），vast.ai/AutoDL 上是停机（那两家销毁会连模型
  权重一起删）。细节见 gpu_teardown.py 的头部说明。

ltx_remote_config.json 模板见 references/ltx_pipeline_gotchas.md 和
SKILL.md；retake 模式如果需要跟主 pipeline 不同的模块名/额外参数，可以在
config 里加 `retake_pipeline_module`（默认 `ltx_pipelines.retake`）和
`retake_extra_args`（默认空），不会跟 `pipeline_module`/`pipeline_extra_args`
混用。`platform`/`instance_id`（RunPod 填 pod_id）这两个字段本脚本自己不用，
只有 `--auto-stop` 用来知道该去关哪个平台的哪台机器。
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def ssh_base(cfg):
    cmd = ["ssh"]
    if cfg.get("ssh_port"):
        cmd += ["-p", str(cfg["ssh_port"])]
    if cfg.get("ssh_key"):
        cmd += ["-i", os.path.expanduser(cfg["ssh_key"])]
    cmd.append(cfg["ssh_host"])
    return cmd


def scp_base(cfg):
    cmd = ["scp"]
    if cfg.get("ssh_port"):
        cmd += ["-P", str(cfg["ssh_port"])]
    if cfg.get("ssh_key"):
        cmd += ["-i", os.path.expanduser(cfg["ssh_key"])]
    return cmd


def remote_mkdir(cfg, remote_dir):
    subprocess.run(ssh_base(cfg) + [f"mkdir -p {shlex.quote(remote_dir)}"], check=True)


def upload(cfg, local_path, remote_path):
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"本地文件不存在，检查 job 里的路径: {local_path}")
    remote_mkdir(cfg, os.path.dirname(remote_path))
    subprocess.run(
        scp_base(cfg) + [local_path, f"{cfg['ssh_host']}:{remote_path}"], check=True
    )


def download(cfg, remote_path, local_path):
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    subprocess.run(
        scp_base(cfg) + [f"{cfg['ssh_host']}:{remote_path}", local_path], check=True
    )


def _nearest_8k_plus_1(n):
    """LTX 要求 num_frames = 8*k + 1（k 非负整数），把估算值吸附到最近的合法值。"""
    k = round((n - 1) / 8)
    k = max(k, 0)
    return 8 * k + 1


def build_remote_cmd(cfg, job, remote_image, remote_last_image, remote_output):
    fps = job.get("fps", 24)
    num_frames = job.get("num_frames") or round(job["duration_sec"] * fps)
    num_frames = _nearest_8k_plus_1(num_frames)

    # python_bin 支持像 "uv run python" 这种带空格的多词前缀，按空格拆分
    # 成独立参数，不要整串塞进一个 list 元素（会被 shlex.quote 成一个不存在
    # 的程序名，比如 'uv run python'）。
    cmd = cfg.get("python_bin", "python").split() + ["-m", cfg["pipeline_module"]]
    cmd += cfg.get("pipeline_extra_args", [])
    cmd += ["--prompt", job["prompt"]]
    # 经 `--help` 实测确认：ltx_pipelines.distilled 没有 --negative-prompt
    # 这个参数（它根本不存在），负面提示词只留在 job 数据里给人看/给未来
    # 支持这个字段的 pipeline 用，不传给这个 pipeline 的 CLI。
    # --image 的实际格式是 `PATH FRAME_IDX STRENGTH [CRF]`（经 --help 确认），
    # 不是一个裸路径。首帧用 FRAME_IDX=0；STRENGTH 默认 1.0（完全锁定首帧），
    # 但可以由 job 的 `first_frame_strength` 覆盖。
    #
    # 为什么要留这个口子：strength=1.0 把首帧焊死，直接后果是生成出来的视频
    # **背景像素级不动**，只有人物的手和脸在变（实测证据见
    # short-drama-video-gen/references/model_capability_ledger.md A6）。
    # 调低理论上能让画面松动、允许视差和真实运镜，代价是首帧保真度下降
    # （人脸/服装漂移）。**这个权衡本仓库还没实测**，A/B 方案见 ledger D4——
    # 所以默认值保持 1.0 不变，不改现有行为，只是让那个实验做得了。
    first_frame_strength = job.get("first_frame_strength", 1.0)
    cmd += ["--image", remote_image, "0", str(first_frame_strength)]
    if remote_last_image:
        # 尾帧同样走 --image，FRAME_IDX 用最后一帧的索引（num_frames-1）。
        cmd += ["--image", remote_last_image, str(num_frames - 1), "1.0"]
    cmd += ["--num-frames", str(num_frames)]
    if job.get("width") and job.get("height"):
        cmd += ["--width", str(job["width"]), "--height", str(job["height"])]
    if job.get("seed") is not None:
        cmd += ["--seed", str(job["seed"])]
    cmd += ["--output-path", remote_output]

    # 非交互式 ssh 命令不会加载 .bashrc/.profile，PATH 里不带 ~/.local/bin
    # （uv 等工具常装在这里），显式导出一次，不依赖远程 shell 的登录配置。
    return (
        "export PATH=$HOME/.local/bin:$PATH && "
        f"cd {shlex.quote(cfg['remote_repo_dir'])} && "
        + " ".join(shlex.quote(c) for c in cmd)
    )


def build_retake_cmd(cfg, remote_video, remote_output, start_sec, end_sec, prompt, seed):
    # ltx_pipelines.retake：官方文档记载"只重新生成视频里一段时间窗口，
    # 其余画面保持不动"，本仓库尚未用 --help 实测确认参数名，第一次用
    # 之前务必先在远程跑一遍 `python -m ltx_pipelines.retake --help` 核对，
    # 下面这几个参数名是按官方文档 best-effort 拼的，不保证跟当前版本 CLI
    # 完全一致——如果报参数错误，对照 --help 输出改这个函数，不要瞎猜重试。
    cmd = cfg.get("python_bin", "python").split() + [
        "-m",
        cfg.get("retake_pipeline_module", "ltx_pipelines.retake"),
    ]
    cmd += cfg.get("retake_extra_args", [])
    cmd += ["--video-path", remote_video]
    cmd += ["--start-time", str(start_sec), "--end-time", str(end_sec)]
    cmd += ["--prompt", prompt]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    cmd += ["--output-path", remote_output]

    return (
        "export PATH=$HOME/.local/bin:$PATH && "
        f"cd {shlex.quote(cfg['remote_repo_dir'])} && "
        + " ".join(shlex.quote(c) for c in cmd)
    )


def run_retake(cfg, job, local_video, out_dir, start_sec, end_sec, dry_run=False):
    job_id = job["id"]
    remote_work = cfg["remote_work_dir"].rstrip("/")
    remote_video = f"{remote_work}/{job_id}_retake_in.mp4"
    remote_output = f"{remote_work}/{job_id}_retake_out.mp4"

    remote_cmd = build_retake_cmd(
        cfg, remote_video, remote_output, start_sec, end_sec, job["prompt"], job.get("seed")
    )

    print(f"\n=== {job_id} (retake {start_sec}s-{end_sec}s) ===")
    print("远程命令:", remote_cmd)

    if dry_run:
        return {"id": job_id, "status": "dry_run", "cmd": remote_cmd}

    if not os.path.exists(local_video):
        raise FileNotFoundError(
            f"--retake 需要先有一份本地已生成的视频作为输入（上一轮的产出），找不到: {local_video}"
        )

    upload(cfg, local_video, remote_video)
    result = subprocess.run(ssh_base(cfg) + [remote_cmd], capture_output=True, text=True)
    if result.stdout:
        print(result.stdout[-2000:])
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        return {"id": job_id, "status": "failed", "stderr": result.stderr[-4000:]}

    local_out = os.path.join(out_dir, f"{job_id}_retake.mp4")
    download(cfg, remote_output, local_out)
    print(f"已下载: {local_out}")
    return {"id": job_id, "status": "done", "output": local_out}


def run_job(cfg, job, out_dir, dry_run=False):
    job_id = job["id"]
    remote_work = cfg["remote_work_dir"].rstrip("/")
    remote_image = f"{remote_work}/{job_id}_first.png"
    remote_last_image = f"{remote_work}/{job_id}_last.png" if job.get("last_frame") else None
    remote_output = f"{remote_work}/{job_id}.mp4"

    remote_cmd = build_remote_cmd(cfg, job, remote_image, remote_last_image, remote_output)

    print(f"\n=== {job_id} ===")
    print("远程命令:", remote_cmd)

    if dry_run:
        return {"id": job_id, "status": "dry_run", "cmd": remote_cmd}

    upload(cfg, job["first_frame"], remote_image)
    if job.get("last_frame"):
        upload(cfg, job["last_frame"], remote_last_image)

    result = subprocess.run(ssh_base(cfg) + [remote_cmd], capture_output=True, text=True)
    if result.stdout:
        print(result.stdout[-2000:])
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        return {"id": job_id, "status": "failed", "stderr": result.stderr[-4000:]}

    local_out = os.path.join(out_dir, f"{job_id}.mp4")
    download(cfg, remote_output, local_out)
    print(f"已下载: {local_out}")
    return {"id": job_id, "status": "done", "output": local_out}


def auto_stop(cfg, config_path, mode):
    """这一批任务收工，立刻把显卡关掉。

    实际动作全部交给 gpu_teardown.py（它负责挑对每个平台该用 stop 还是
    terminate、调完接口轮询确认真的停了、顺带杀掉本机的闲置看门狗），这里
    只负责"批量任务一结束就把它叫起来"这个时机。故意不吞掉它的退出码——
    关机没确认成功是必须让人看见的事，不能被"生成成功"的日志盖过去。
    """
    script = str(Path(__file__).resolve().parent / "gpu_teardown.py")
    cmd = ["python3", script, "--platform", cfg["platform"],
           "--instance-id", str(cfg["instance_id"]), "--mode", mode]
    if config_path:
        cmd += ["--config", config_path]
    print("\n=== 自动关闭显卡 ===")
    print(" ".join(cmd))
    # 子进程直接写继承来的 stdout，父进程这边被重定向到文件/管道时是块缓冲，
    # 不 flush 的话日志顺序会错乱（关机日志跑到生成日志前面），排查时很误导。
    sys.stdout.flush()
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(
            "\n⚠️ 自动关机没能确认成功，实例可能还在计费，去平台控制台手动确认"
            f"（实例 {cfg['instance_id']}，平台 {cfg['platform']}）",
            file=sys.stderr,
        )
    return result.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="ltx_remote_config.json 路径")
    ap.add_argument("--jobs", required=True, help="video_jobs.json 路径")
    ap.add_argument("--out-dir", required=True, help="生成视频下载到本地的目录")
    ap.add_argument(
        "--only", nargs="*", help="只跑指定的 shot_no 或 id，不传则跑 jobs 文件里的全部"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="只打印将要执行的远程命令和上传/下载路径，不实际连接"
    )
    ap.add_argument(
        "--auto-stop",
        action="store_true",
        help=(
            "这一批任务跑完（含中途报错/中断）后自动调用 gpu_teardown.py 停掉显卡实例"
            "并确认停成功了，别让实例空转烧钱。要求 config 里有 platform/instance_id，"
            "缺了会在提交任务之前就报错退出。--dry-run 时不会真的关机。"
        ),
    )
    ap.add_argument(
        "--auto-stop-mode",
        choices=["auto", "stop", "terminate"],
        default="auto",
        help="透传给 gpu_teardown.py 的 --mode，默认 auto（RunPod terminate / 其余停机）",
    )
    ap.add_argument(
        "--retake",
        nargs=2,
        metavar=("START_SEC", "END_SEC"),
        help=(
            "局部重绘模式：只重新生成 --only 指定的这一个镜头里 "
            "[START_SEC, END_SEC] 这段时间窗口，其余画面不动（ltx_pipelines.retake，"
            "官方文档记载但本仓库未实测，见脚本头部说明）。要求 --only 精确匹配到"
            "唯一一个镜头，且 --out-dir 下已有该镜头上一轮生成的 <id>.mp4。"
        ),
    )
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(args.jobs, encoding="utf-8") as f:
        jobs = json.load(f)

    missing = [k for k in ("ssh_host", "remote_repo_dir", "remote_work_dir", "pipeline_module") if k not in cfg]
    if missing:
        sys.exit(f"config 缺少必填字段: {', '.join(missing)}")

    # --auto-stop 需要的字段在**提交任何任务之前**就校验掉：等批量任务跑完
    # 几小时才发现关不掉机器，等于白交一轮学费。
    if args.auto_stop and not args.dry_run:
        missing_stop = [k for k in ("platform", "instance_id") if not cfg.get(k)]
        if missing_stop:
            sys.exit(
                f"--auto-stop 需要 config 里有 {', '.join(missing_stop)} 字段"
                "（platform 取值 vast/autodl/runpod，instance_id 在 RunPod 上是 pod_id）；"
                "补上再跑，不要先跑生成再想怎么关机。"
            )

    if args.only:
        wanted = {str(x) for x in args.only}
        jobs = [j for j in jobs if str(j.get("shot_no")) in wanted or j["id"] in wanted]
        if not jobs:
            sys.exit(f"--only {args.only} 在 jobs 文件里没有匹配到任何镜头")

    os.makedirs(args.out_dir, exist_ok=True)

    # --retake 的入参校验放在 try 之前：这类"命令敲错了、一个任务都还没提交"
    # 的退出不该触发 --auto-stop 去关机（用户大概率是要改个参数马上重跑）。
    if args.retake and len(jobs) != 1:
        sys.exit(
            f"--retake 模式要求 --only 精确匹配到唯一一个镜头，当前匹配到 {len(jobs)} 个"
        )

    # 从这里往下只要真的动过显卡，无论正常收工、抛异常还是 Ctrl-C，finally 里
    # 的 --auto-stop 都会执行——"任务崩了没人管、实例挂着通宵计费"是最贵的
    # 一种失败方式，比任何一次生成失败都贵。
    try:
        if args.retake:
            start_sec, end_sec = float(args.retake[0]), float(args.retake[1])
            job = jobs[0]
            local_video = os.path.join(args.out_dir, f"{job['id']}.mp4")
            try:
                result = run_retake(cfg, job, local_video, args.out_dir, start_sec, end_sec, dry_run=args.dry_run)
            except Exception as e:
                print(f"镜头 {job.get('id')} retake 出错: {e}", file=sys.stderr)
                result = {"id": job.get("id"), "status": "error", "error": str(e)}
            summary_path = os.path.join(args.out_dir, "ltx_submit_results.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump([result], f, ensure_ascii=False, indent=2)
            print(f"\n结果写入 {summary_path}")
            if result["status"] not in ("done", "dry_run"):
                print(f"\nretake 未成功，检查上面的报错或 {summary_path}", file=sys.stderr)
            return

        results = []
        for job in jobs:
            try:
                results.append(run_job(cfg, job, args.out_dir, dry_run=args.dry_run))
            except Exception as e:
                print(f"镜头 {job.get('id')} 出错: {e}", file=sys.stderr)
                results.append({"id": job.get("id"), "status": "error", "error": str(e)})

        summary_path = os.path.join(args.out_dir, "ltx_submit_results.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果汇总写入 {summary_path}")

        failed = [r for r in results if r["status"] not in ("done", "dry_run")]
        if failed:
            print(f"\n{len(failed)} 个镜头未成功，检查上面的报错或 {summary_path}", file=sys.stderr)
    finally:
        if args.auto_stop and not args.dry_run:
            auto_stop(cfg, args.config, args.auto_stop_mode)


if __name__ == "__main__":
    main()
