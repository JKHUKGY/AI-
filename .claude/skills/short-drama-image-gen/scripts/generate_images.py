#!/usr/bin/env python3
"""批量调用 Codex CLI（ChatGPT 登录，内置 image_gen 工具）生成图片。

用法：
    codex login --device-auth   # 先登录一次（ChatGPT Plus/Pro/Team 账号）
    python3 generate_images.py jobs.json --out-dir output/<故事名>/assets
    python3 generate_images.py jobs.json --out-dir output/<故事名>/assets --parallel 3

jobs.json 格式见 ../references/jobs_schema.md。不依赖任何 API key/计费账号，
走的是 `codex` CLI 自带的 image_gen 工具，用你登录的 ChatGPT 账号额度。

`--parallel N`（默认 1，等价于原来的顺序执行）会把这一批 job 里所有要生成
的图片（job x count 展开成一个任务队列）放进一个线程池，最多同时跑 N 个
`codex exec` 子进程——即多个 codex CLI 真正并发运行，而不是一张一张排队。
并行数怎么选、什么情况不适合并行见 ../references/parallel_mode.md。
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_TIMEOUT = 240


def check_login():
    result = subprocess.run(["codex", "login", "status"], capture_output=True, text=True)
    return result.returncode == 0


def run_one(prompt, ref_images, job_dir, target, model, timeout):
    full_prompt = (
        f"{prompt}\n\n"
        f"请生成这张图片，并把最终图片文件保存到这个精确的绝对路径："
        f"{target}\n"
        f"只需要保存这一个 PNG 文件到这个路径，不需要额外说明或展示其它内容。"
    )
    cmd = [
        "codex", "exec",
        "--skip-git-repo-check",
        "--sandbox", "workspace-write",
        "-C", str(job_dir),
    ]
    for ref in ref_images:
        cmd += ["-i", str(Path(ref).resolve())]
    if model:
        cmd += ["-m", model]
    # codex exec 的 -i/--image 是 clap 的多值选项（<FILE>...），如果直接把
    # prompt 追加在 -i 之后，prompt 文本会被当成又一个图片路径吞掉，导致
    # PROMPT 位置参数落空、codex 转而尝试从 stdin 读取（进而报错退出）。
    # 用 "--" 显式终止选项解析，强制其后的内容作为位置参数（即 PROMPT）。
    cmd += ["--", full_prompt]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  [警告] 超时（{timeout}s），跳过", file=sys.stderr)
        return False, ""

    if result.returncode != 0:
        print(f"  [警告] codex 退出码 {result.returncode}", file=sys.stderr)
        print(result.stderr[-1500:], file=sys.stderr)
        return target.exists(), result.stdout

    return target.exists(), result.stdout


def build_tasks(jobs, out_dir):
    """把 job x count 展开成独立的生成任务列表，每个任务对应一次 codex exec 调用。"""
    tasks = []
    for job in jobs:
        job_id = job["id"]
        prompt = job["prompt"]
        count = int(job.get("count", 3))
        ref_images = job.get("ref_images") or []
        job_dir = out_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(job_dir.glob(f"{job_id}_*.png"))
        start_idx = len(existing)

        for i in range(count):
            idx = start_idx + i
            fname = f"{job_id}_{idx:02d}.png"
            target = (job_dir / fname).resolve()
            tasks.append(
                {
                    "job_id": job_id,
                    "prompt": prompt,
                    "ref_images": ref_images,
                    "job_dir": job_dir,
                    "target": target,
                }
            )
    return tasks


def run_task(task, model, timeout):
    job_id = task["job_id"]
    target = task["target"]
    print(f"[{job_id}] 生成 -> {target.name} ...")

    ok, stdout = run_one(task["prompt"], task["ref_images"], task["job_dir"], target, model, timeout)
    if not ok:
        print(f"  [警告][{job_id}] 未生成 {target.name}，重试一次...", file=sys.stderr)
        ok, stdout = run_one(task["prompt"], task["ref_images"], task["job_dir"], target, model, timeout)

    if ok:
        print(f"  已保存 [{job_id}] {target.name}")
        return {
            "file": str(target),
            "job_id": job_id,
            "prompt": task["prompt"],
            "ref_images": task["ref_images"],
            "backend": "codex-cli",
            "model": model or "default",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    print(f"  [失败][{job_id}] {target.name} 仍未生成，放弃这一张。codex 最后输出：", file=sys.stderr)
    print(stdout[-1000:], file=sys.stderr)
    return None


def main():
    ap = argparse.ArgumentParser(description="批量调用 Codex CLI image_gen 工具（AI 短剧角色/场景出图）")
    ap.add_argument("jobs_file", help="jobs JSON 文件路径，格式见 references/jobs_schema.md")
    ap.add_argument("--out-dir", default="output/assets", help="输出根目录，每个 job 一个子目录")
    ap.add_argument("--model", default=None, help="传给 codex exec -m 的模型名，默认用 codex 配置里的默认模型")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单张图片生成超时秒数")
    ap.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="最多同时跑几个 codex exec 子进程（默认 1=顺序执行）。见 references/parallel_mode.md。",
    )
    args = ap.parse_args()

    if not check_login():
        print(
            "错误：codex 未登录。请先运行 `codex login --device-auth`，"
            "用 ChatGPT 账号完成登录后再运行本脚本。",
            file=sys.stderr,
        )
        sys.exit(1)

    jobs = json.loads(Path(args.jobs_file).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = build_tasks(jobs, out_dir)
    manifest_path = out_dir / "manifest.append.jsonl"
    manifest_lock = threading.Lock()
    all_manifest = []

    def worker(task):
        entry = run_task(task, args.model, args.timeout)
        if entry:
            with manifest_lock:
                with manifest_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    parallel = max(1, args.parallel)
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        for entry in executor.map(worker, tasks):
            if entry:
                all_manifest.append(entry)

    print(f"\n完成，本次共生成 {len(all_manifest)} 张图片，记录已追加到 {manifest_path}")


if __name__ == "__main__":
    main()
