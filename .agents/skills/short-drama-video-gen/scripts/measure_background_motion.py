#!/usr/bin/env python3
"""量一段视频"背景到底动没动"——把 ledger A6 从形容词变成一个可比的数字。

## 为什么需要它

A6（单镜内背景像素级冻住）到 2026-09 为止的证据是"抽两帧肉眼看，逐像素相同"。
这个判据没法做 A/B：两组都"看起来不太动"的时候，说不出哪组更松。而 A6 的成因
归属已经被推翻过两次（先怪 `first_frame_strength`，D4 扫描证伪；再怀疑提示词
自己在命令背景别动），**再靠肉眼比下去不会有结论**。

这个脚本给三个数：

- `mean_abs_diff`：每一帧和**首帧**的平均绝对像素差（0-255）。背景真的冻住时
  它会贴近 0 并且几乎不随时间增长。
- `frozen_ratio`：和首帧差值小于 `--eps` 的像素占比。**这是最直接的"冻住"指标**
  ——0.98 意味着 98% 的画面逐像素没变过。
- `edge_band_diff`：只统计画面**四周边框**那一圈（默认外侧 12%）的差值。
  人物通常在画面中央，边框基本只有背景，所以这一条比整帧更能反映"背景动没动"。

判读：**看 `frozen_ratio` 和 `edge_band_diff` 的组合。**
`frozen_ratio` 高 + `edge_band_diff` 贴近 0 = 背景是死的；
`edge_band_diff` 明显大于 0 而人脸没崩 = 松动成功。

## 用法

```bash
# 单个文件
python3 measure_background_motion.py a.mp4

# 一组 A/B 对比（同首帧同 seed，只改提示词）
python3 measure_background_motion.py \
    videos/ep01/ep01_镜14_a_baseline.mp4 \
    videos/ep01/ep01_镜14_b_norig.mp4 \
    videos/ep01/ep01_镜14_c_loose.mp4 --frames 6
```

依赖只有 ffmpeg（用 rawvideo gray 管道读帧，不需要 numpy/PIL）。
"""

import argparse
import json
import os
import subprocess
import sys

DEFAULT_FRAMES = 6
DEFAULT_EPS = 2          # 灰度差 ≤ 这个值就算"没变"
DEFAULT_BAND = 0.12      # 边框带宽占短边的比例
SAMPLE_W = 160           # 统一缩到这个宽度再比，省内存也抹掉编码噪点


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_read_packets",
         "-count_packets", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    return int(st["width"]), int(st["height"]), int(st.get("nb_read_packets") or 0)


def read_gray_frames(path, n, w, h):
    """均匀取 n 帧，缩成 SAMPLE_W 宽的灰度图，返回 [bytes]。"""
    sh = max(1, round(SAMPLE_W * h / w))
    # fps 过滤不好定位，直接全解码再按步长取——短片（4-8 秒）代价可以接受
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path,
         "-vf", f"scale={SAMPLE_W}:{sh}", "-pix_fmt", "gray",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    fsize = SAMPLE_W * sh
    total = len(raw) // fsize
    if total == 0:
        raise SystemExit(f"{path}: 一帧都没解出来")
    idx = [round(i * (total - 1) / max(1, n - 1)) for i in range(min(n, total))]
    return [raw[i * fsize:(i + 1) * fsize] for i in idx], SAMPLE_W, sh


def band_mask(w, h, band):
    """四周边框那一圈的像素下标集合（用集合太慢，返回逐行的列区间判断函数）。"""
    bx = max(1, int(w * band))
    by = max(1, int(h * band))
    return bx, by


def measure(path, n_frames, eps, band):
    w, h, _ = probe(path)
    frames, sw, sh = read_gray_frames(path, n_frames, w, h)
    base = frames[0]
    bx, by = band_mask(sw, sh, band)

    rows = []
    for k, f in enumerate(frames[1:], 1):
        tot = same = 0
        acc = 0
        bacc = bcnt = 0
        for y in range(sh):
            row = y * sw
            in_band_row = (y < by or y >= sh - by)
            for x in range(sw):
                i = row + x
                d = base[i] - f[i]
                if d < 0:
                    d = -d
                acc += d
                tot += 1
                if d <= eps:
                    same += 1
                if in_band_row or x < bx or x >= sw - bx:
                    bacc += d
                    bcnt += 1
        rows.append({
            "frame": k,
            "mean_abs_diff": round(acc / tot, 3),
            "frozen_ratio": round(same / tot, 4),
            "edge_band_diff": round(bacc / max(1, bcnt), 3),
        })
    return {
        "file": os.path.basename(path),
        "size": f"{w}x{h}",
        "frames_sampled": len(frames),
        "per_frame": rows,
        "last": rows[-1] if rows else None,
    }


def main():
    ap = argparse.ArgumentParser(description="量视频背景动没动（ledger A6 的判据）")
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--frames", type=int, default=DEFAULT_FRAMES,
                    help=f"均匀取几帧和首帧比，默认 {DEFAULT_FRAMES}")
    ap.add_argument("--eps", type=int, default=DEFAULT_EPS,
                    help=f"灰度差≤多少算没变，默认 {DEFAULT_EPS}")
    ap.add_argument("--band", type=float, default=DEFAULT_BAND,
                    help=f"边框带宽占比，默认 {DEFAULT_BAND}")
    ap.add_argument("--json", metavar="PATH", help="把完整结果写成 JSON")
    args = ap.parse_args()

    results = []
    print(f"{'文件':<34} {'尾帧均差':>9} {'冻结占比':>9} {'边框差':>9}")
    print("-" * 66)
    for v in args.videos:
        if not os.path.exists(v):
            print(f"{os.path.basename(v):<34} {'(文件不存在)':>29}")
            continue
        r = measure(v, args.frames, args.eps, args.band)
        results.append(r)
        last = r["last"] or {}
        print(f"{r['file']:<34} {last.get('mean_abs_diff', 0):>9} "
              f"{last.get('frozen_ratio', 0):>9} {last.get('edge_band_diff', 0):>9}")

    print()
    print("判读：`冻结占比` 高（>0.95）且 `边框差` 贴近 0 = 背景是死的（A6 症状）。")
    print("     A/B 里 `边框差` 明显更大、而人脸没崩的那一组，就是松动成功的写法。")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n已写出 → {args.json}")


if __name__ == "__main__":
    main()
