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
`.claude/skills/short-drama-video-gen/references/ltx2_self_hosted.md`——
尤其是首尾帧组合用法、--negative-prompt 是否通用这两点，第一次用某个
pipeline 之前务必先在远程跑一遍 `python -m <pipeline_module> --help` 核实。

用法:
  python3 ltx_ssh_submit.py --config ltx_remote_config.json \\
      --jobs output/<故事名>/videos/ep0X/video_jobs.json \\
      --out-dir output/<故事名>/videos/ep0X \\
      [--only 11 12] [--dry-run]

video_jobs.json 是 references/video_jobs_schema.md 里 JSON 版本的结构，
额外需要 width/height（像素，需能被 64 整除），可选 num_frames（不填按
duration_sec * 24fps 估算）、可选 seed。

ltx_remote_config.json 模板见 references/ltx2_self_hosted.md。
"""

import argparse
import json
import os
import shlex
import subprocess
import sys


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
    # 不是一个裸路径。首帧固定用 FRAME_IDX=0、STRENGTH=1.0（完全锁定首帧）。
    cmd += ["--image", remote_image, "0", "1.0"]
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
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(args.jobs, encoding="utf-8") as f:
        jobs = json.load(f)

    missing = [k for k in ("ssh_host", "remote_repo_dir", "remote_work_dir", "pipeline_module") if k not in cfg]
    if missing:
        sys.exit(f"config 缺少必填字段: {', '.join(missing)}")

    if args.only:
        wanted = {str(x) for x in args.only}
        jobs = [j for j in jobs if str(j.get("shot_no")) in wanted or j["id"] in wanted]
        if not jobs:
            sys.exit(f"--only {args.only} 在 jobs 文件里没有匹配到任何镜头")

    os.makedirs(args.out_dir, exist_ok=True)
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


if __name__ == "__main__":
    main()
