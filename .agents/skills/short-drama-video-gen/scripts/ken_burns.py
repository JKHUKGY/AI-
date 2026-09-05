#!/usr/bin/env python3
"""用 ffmpeg 的 zoompan 滤镜给静态关键帧做推拉摇移(Ken Burns)效果。

零成本、不调用任何生成 API，纯本地处理。**不是 B 级镜头的默认路径**——
B 级现在跟 S/A 级一样正常走图生视频/LTX 生成，本脚本只在某镜（不分级别）
连续多轮生成仍选不出可用片段时，作为本地兜底方案使用，见
`short-drama-video-gen/SKILL.md` 第 5 步。

用法：
    ffmpeg -version   # 先确认已安装，没有就 apt-get install ffmpeg / brew install ffmpeg
    python3 ken_burns.py kenburns_jobs.json --out-dir output/<故事名>/videos/ep0X

kenburns_jobs.json 格式（JSON 数组）：
[
  {
    "id": "ep01_镜05",
    "image": "output/千金归位/keyframes/ep01/ep01_镜05_00.png",
    "motion": "zoom_in",       // zoom_in | zoom_out | pan_left | pan_right | pan_up | pan_down | static
    "duration": 3.0,             // 秒，默认取 ep0X.md 该镜"时长(秒)"列的值
    "fps": 25,                    // 可选，默认 25
    "width": 1080,                 // 可选，默认 1080（竖屏 9:16）
    "height": 1920                  // 可选，默认 1920
  }
]

运镜方向要对应分镜表"运镜"列（推→zoom_in，拉→zoom_out，摇左/右/上/下→
pan_left/right/up/down，固定→static），不要随手选一个和分镜意图不符的方向。
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "static"}


def check_ffmpeg():
    return shutil.which("ffmpeg") is not None


def build_filter(motion, duration, fps, width, height):
    frames = max(int(round(duration * fps)), 1)
    # 内部先按目标分辨率的 2 倍上采样，给 zoompan 留出推拉摇移的余量，
    # 避免画面边缘出现黑边。
    upscale = f"scale={width * 2}:{height * 2}"

    if motion == "zoom_in":
        z = "min(zoom+0.0015,1.3)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out":
        z = "if(eq(on,0),1.3,max(zoom-0.0015,1.0))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pan_left":
        z = "1.15"
        x = f"(iw-iw/zoom)*(1-on/{frames - 1 if frames > 1 else 1})"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pan_right":
        z = "1.15"
        x = f"(iw-iw/zoom)*(on/{frames - 1 if frames > 1 else 1})"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pan_up":
        z = "1.15"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*(1-on/{frames - 1 if frames > 1 else 1})"
    elif motion == "pan_down":
        z = "1.15"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*(on/{frames - 1 if frames > 1 else 1})"
    else:  # static：轻微呼吸感缩放，避免画面完全死板
        z = "min(zoom+0.0004,1.05)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"

    zoompan = (
        f"zoompan=z='{z}':d=1:x='{x}':y='{y}':s={width}x{height}:fps={fps}"
    )
    return f"{upscale},{zoompan}"


def run_job(job, out_dir):
    job_id = job["id"]
    image = Path(job["image"]).resolve()
    motion = job.get("motion", "zoom_in")
    duration = float(job.get("duration", 3.0))
    fps = int(job.get("fps", 25))
    width = int(job.get("width", 1080))
    height = int(job.get("height", 1920))

    if motion not in MOTIONS:
        print(f"[{job_id}] 未知 motion '{motion}'，跳过。可选：{sorted(MOTIONS)}", file=sys.stderr)
        return None
    if not image.exists():
        print(f"[{job_id}] 找不到图片 {image}，跳过。", file=sys.stderr)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{job_id}.mp4"
    vf = build_filter(motion, duration, fps, width, height)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image),
        "-vf", vf,
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        str(target),
    ]
    print(f"[{job_id}] 生成 {motion} 效果，时长 {duration}s -> {target.name} ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not target.exists():
        print(f"  [失败] ffmpeg 退出码 {result.returncode}", file=sys.stderr)
        print(result.stderr[-1500:], file=sys.stderr)
        return None

    print(f"  已保存 {target}")
    return str(target)


def main():
    ap = argparse.ArgumentParser(description="用 ffmpeg zoompan 给 B 级关键帧做本地推拉摇移")
    ap.add_argument("jobs_file", help="kenburns_jobs.json 路径")
    ap.add_argument("--out-dir", default="output/videos", help="输出目录")
    args = ap.parse_args()

    if not check_ffmpeg():
        print(
            "错误：未检测到 ffmpeg。请先安装（Debian/Ubuntu: apt-get install "
            "-y ffmpeg；macOS: brew install ffmpeg）后再运行本脚本。",
            file=sys.stderr,
        )
        sys.exit(1)

    jobs = json.loads(Path(args.jobs_file).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir).resolve()

    done = 0
    for job in jobs:
        if run_job(job, out_dir):
            done += 1

    print(f"\n完成，本次共生成 {done}/{len(jobs)} 个 B 级运镜视频片段。")


if __name__ == "__main__":
    main()
