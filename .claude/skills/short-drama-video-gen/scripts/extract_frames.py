#!/usr/bin/env python3
"""从生成的图生视频片段里抽出几张均匀分布的帧，供 Claude 用 Read 工具查看验收。

Read 工具能看图片、看不了视频文件本身，这一步是视频验收流程的必需前置
步骤，见 references/video_review_checklist.md。

用法：
    ffmpeg -version   # 先确认已安装
    python3 extract_frames.py <视频文件路径> --out-dir <帧输出目录> --count 5

默认抽 5 帧：开头(0%)、25%、50%(中间)、75%、结尾(接近100%，留一点余量避免
seek 到最后一帧失败)。
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def check_ffmpeg():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_duration(video_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[警告] ffprobe 读取时长失败：{result.stderr.strip()}", file=sys.stderr)
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def extract_one(video_path, timestamp, out_path):
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{timestamp:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and out_path.exists()


def main():
    ap = argparse.ArgumentParser(description="从视频里抽取均匀分布的帧用于人工验收")
    ap.add_argument("video", help="视频文件路径")
    ap.add_argument("--out-dir", default="output/videos/review_frames", help="帧图片输出目录")
    ap.add_argument("--count", type=int, default=5, help="抽帧数量，默认 5")
    args = ap.parse_args()

    if not check_ffmpeg():
        print(
            "错误：未检测到 ffmpeg/ffprobe。请先安装（Debian/Ubuntu: apt-get "
            "install -y ffmpeg；macOS: brew install ffmpeg）后再运行本脚本。",
            file=sys.stderr,
        )
        sys.exit(1)

    video_path = Path(args.video).resolve()
    if not video_path.exists():
        print(f"错误：找不到视频文件 {video_path}", file=sys.stderr)
        sys.exit(1)

    duration = get_duration(video_path)
    if not duration or duration <= 0:
        print("错误：无法读取视频时长，无法计算抽帧时间点。", file=sys.stderr)
        sys.exit(1)

    count = max(args.count, 2)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem

    # 结尾留 2% 余量，避免 seek 到刚好等于总时长时因为编码原因抽不出帧。
    margin = duration * 0.02
    timestamps = [
        margin + (duration - 2 * margin) * i / (count - 1)
        for i in range(count)
    ]

    saved = []
    for i, ts in enumerate(timestamps):
        out_path = out_dir / f"{stem}_frame{i:02d}.png"
        if extract_one(video_path, ts, out_path):
            print(f"已保存 {out_path} (t={ts:.2f}s)")
            saved.append(str(out_path))
        else:
            print(f"[警告] 抽取 t={ts:.2f}s 的帧失败", file=sys.stderr)

    print(f"\n完成，共抽取 {len(saved)}/{count} 帧到 {out_dir}")
    print("接下来用 Read 工具逐张打开这些帧图片，按 video_review_checklist.md 核对。")


if __name__ == "__main__":
    main()
