#!/usr/bin/env python3
"""批量调用 Codex CLI（ChatGPT 登录，内置 image_gen 工具）生成图片。

用法：
    codex login --device-auth   # 先登录一次（ChatGPT Plus/Pro/Team 账号）
    python3 generate_images.py jobs.json --out-dir output/<故事名>/assets

jobs.json 格式见 ../references/jobs_schema.md。不依赖任何 API key/计费账号，
走的是 `codex` CLI 自带的 image_gen 工具，用你登录的 ChatGPT 账号额度。
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_TIMEOUT = 240


def check_login():
    result = subprocess.run(["codex", "login", "status"], capture_output=True, text=True)
    return result.returncode == 0


def run_one(job_id, prompt, ref_images, job_dir, target, model, timeout):
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


def run_job(job, out_dir, model, timeout):
    job_id = job["id"]
    prompt = job["prompt"]
    count = int(job.get("count", 3))
    ref_images = job.get("ref_images") or []
    job_dir = out_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(job_dir.glob(f"{job_id}_*.png"))
    start_idx = len(existing)

    manifest_entries = []
    for i in range(count):
        idx = start_idx + i
        fname = f"{job_id}_{idx:02d}.png"
        target = (job_dir / fname).resolve()
        print(f"[{job_id}] 生成第 {idx + 1} 张 -> {target.name} ...")

        ok, stdout = run_one(job_id, prompt, ref_images, job_dir, target, model, timeout)
        if not ok:
            print(f"  [警告] 未生成 {target}，重试一次...", file=sys.stderr)
            ok, stdout = run_one(job_id, prompt, ref_images, job_dir, target, model, timeout)

        if ok:
            print(f"  已保存 {target}")
            manifest_entries.append(
                {
                    "file": str(target),
                    "job_id": job_id,
                    "prompt": prompt,
                    "ref_images": ref_images,
                    "backend": "codex-cli",
                    "model": model or "default",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
        else:
            print(f"  [失败] {target} 仍未生成，放弃这一张。codex 最后输出：", file=sys.stderr)
            print(stdout[-1000:], file=sys.stderr)
    return manifest_entries


def main():
    ap = argparse.ArgumentParser(description="批量调用 Codex CLI image_gen 工具（AI 短剧角色/场景出图）")
    ap.add_argument("jobs_file", help="jobs JSON 文件路径，格式见 references/jobs_schema.md")
    ap.add_argument("--out-dir", default="output/assets", help="输出根目录，每个 job 一个子目录")
    ap.add_argument("--model", default=None, help="传给 codex exec -m 的模型名，默认用 codex 配置里的默认模型")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单张图片生成超时秒数")
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

    all_manifest = []
    for job in jobs:
        all_manifest.extend(run_job(job, out_dir, args.model, args.timeout))

    manifest_path = out_dir / "manifest.append.jsonl"
    with manifest_path.open("a", encoding="utf-8") as f:
        for entry in all_manifest:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n完成，本次共生成 {len(all_manifest)} 张图片，记录已追加到 {manifest_path}")


if __name__ == "__main__":
    main()
