#!/usr/bin/env python3
"""校验 video_jobs.json 是不是能被 ltx_ssh_submit.py 直接消费。

只做本地静态检查，不连接远程机器、不调用任何生成 API：
- 必填字段是否齐全（id/shot_no/scene/first_frame/prompt/negative_prompt/
  duration_sec/aspect_ratio/platform_recommend/width/height）。
- first_frame/last_frame/ref_images 引用的文件是否在本地磁盘真实存在
  （相对路径按运行时的当前工作目录解析，约定从仓库根目录运行）。
- width/height 是否能被 64 整除（LTX-2.5 的已知限制，见
  short-drama-ltx-generate/references/ltx_pipeline_gotchas.md）。
- aspect_ratio 字段跟实际 width/height 的比例是否吻合（防止漏填/传错
  分辨率导致悄悄退回 pipeline 默认横屏 1536×1024，见
  short-drama-ltx-generate/references/ltx_pipeline_gotchas.md
  "生成质量丢分的三大常见诱因"第 1 条）。
- num_frames 如果手动填了，是否满足 8*k+1；不满足的话
  ltx_ssh_submit.py 会静默吸附成最近的合法值，跟手填的原意可能不一致。
- prompt/negative_prompt 里是否残留常见占位符文本，提示尚未真正展开。

用法:
  python3 validate_video_jobs.py <video_jobs.json>

退出码非 0 表示存在需要人工处理的问题，退出码 0 但仍可能有 WARN 级提示。
"""

import json
import os
import sys

REQUIRED_FIELDS = [
    "id",
    "shot_no",
    "scene",
    "first_frame",
    "prompt",
    "negative_prompt",
    "duration_sec",
    "aspect_ratio",
    "platform_recommend",
    "width",
    "height",
]

PLACEHOLDER_MARKERS = [
    "TODO",
    "(完整正向提示词)",
    "（完整正向提示词）",
    "(完整负面提示词)",
    "（完整负面提示词）",
    "占位",
    "待补充",
]

# 跟 ltx_ssh_submit.py 的 _nearest_8k_plus_1 保持同一个吸附算法，方便在
# 校验阶段就提前告诉用户手填的 num_frames 最终会被吸附成什么值。
def _nearest_8k_plus_1(n):
    k = max(round((n - 1) / 8), 0)
    return 8 * k + 1


def _parse_aspect_ratio(aspect_ratio):
    """把 "9:16" 这种字符串解析成 width/height 比例；解析不了返回 None。"""
    try:
        w_str, h_str = str(aspect_ratio).split(":")
        w, h = float(w_str), float(h_str)
        if h == 0:
            return None
        return w / h
    except (ValueError, AttributeError):
        return None


def check_job(job, index):
    errors = []
    warnings = []
    label = job.get("id", f"index_{index}")

    for field in REQUIRED_FIELDS:
        if job.get(field) in (None, ""):
            errors.append(f"[{label}] 缺少必填字段 `{field}`")

    for path_field in ("first_frame", "last_frame"):
        path = job.get(path_field)
        if path and not os.path.exists(path):
            errors.append(f"[{label}] `{path_field}` 指向的文件不存在: {path}")

    for i, ref in enumerate(job.get("ref_images") or []):
        if not os.path.exists(ref):
            errors.append(f"[{label}] `ref_images[{i}]` 指向的文件不存在: {ref}")

    width, height = job.get("width"), job.get("height")
    if isinstance(width, int) and width % 64 != 0:
        errors.append(f"[{label}] width={width} 不能被 64 整除")
    if isinstance(height, int) and height % 64 != 0:
        errors.append(f"[{label}] height={height} 不能被 64 整除")

    if isinstance(width, int) and isinstance(height, int) and height:
        expected_ratio = _parse_aspect_ratio(job.get("aspect_ratio"))
        if expected_ratio:
            actual_ratio = width / height
            # 容忍度放宽到 15%：现有测试档/正式档预设里最接近 9:16 的
            # 704x1280（0.55）跟精确 0.5625 差约 2%，留足空间不误报；但
            # 横屏 1536x1024（1.5）跟 9:16 目标（0.5625）差 167%，稳稳落在
            # 阈值外，正是要拦的那种"漏填/退回默认值"场景。
            if abs(actual_ratio - expected_ratio) / expected_ratio > 0.15:
                errors.append(
                    f"[{label}] width×height={width}×{height}（实际比例"
                    f"{actual_ratio:.3f}）跟 aspect_ratio={job.get('aspect_ratio')}"
                    f"（目标比例 {expected_ratio:.3f}）明显不符，很可能是漏填/"
                    "传错了分辨率（比如悄悄退回了 pipeline 默认横屏 1536×1024）"
                )

    for text_field in ("prompt", "negative_prompt"):
        text = job.get(text_field) or ""
        for marker in PLACEHOLDER_MARKERS:
            if marker in text:
                errors.append(
                    f"[{label}] `{text_field}` 里残留占位符文本 `{marker}`，看起来没有真正展开"
                )

    num_frames = job.get("num_frames")
    if num_frames is None:
        fps = job.get("fps", 24)
        est = round(job.get("duration_sec", 0) * fps) if job.get("duration_sec") else None
        warnings.append(
            f"[{label}] 未显式指定 num_frames，ltx_ssh_submit.py 会按 duration_sec×{fps}fps"
            f"（≈{est} 帧）自动估算，确认这符合预期"
        )
    elif isinstance(num_frames, int) and (num_frames - 1) % 8 != 0:
        snapped = _nearest_8k_plus_1(num_frames)
        warnings.append(
            f"[{label}] num_frames={num_frames} 不满足 LTX 要求的 8k+1，"
            f"ltx_ssh_submit.py 提交时会静默吸附成 {snapped}——如果这一镜是靠精确"
            "num_frames 卡某个动作节拍，确认吸附后的值还符合预期，或者直接在这里"
            f"改成 {snapped} 避免歧义"
        )

    if job.get("dialogue"):
        for text_field in ("prompt", "negative_prompt"):
            if job["dialogue"] in (job.get(text_field) or ""):
                warnings.append(
                    f"[{label}] `dialogue` 的文本原样出现在 `{text_field}` 里，"
                    "确认不是把台词误塞进了提示词（dialogue 只应是参考信息）"
                )

    return errors, warnings


def main():
    if len(sys.argv) != 2:
        sys.exit(f"用法: python3 {sys.argv[0]} <video_jobs.json>")

    jobs_path = sys.argv[1]
    with open(jobs_path, encoding="utf-8") as f:
        jobs = json.load(f)

    if not isinstance(jobs, list):
        sys.exit("video_jobs.json 顶层必须是一个数组")

    all_errors = []
    all_warnings = []
    for i, job in enumerate(jobs):
        errors, warnings = check_job(job, i)
        all_errors += errors
        all_warnings += warnings

    print(f"共校验 {len(jobs)} 条 job")

    if all_warnings:
        print(f"\n{len(all_warnings)} 条提示（不阻塞，建议人工确认）:")
        for w in all_warnings:
            print(f"  WARN: {w}")

    if all_errors:
        print(f"\n{len(all_errors)} 条错误（必须处理才能提交）:")
        for e in all_errors:
            print(f"  ERROR: {e}")
        sys.exit(1)

    print("\n未发现阻塞性问题，可以进入 ltx_ssh_submit.py --dry-run 验证。")


if __name__ == "__main__":
    main()
