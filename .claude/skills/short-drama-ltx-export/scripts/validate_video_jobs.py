#!/usr/bin/env python3
"""校验 video_jobs.json 是不是能被 ltx_ssh_submit.py 直接消费。

只做本地静态检查，不连接远程机器、不调用任何生成 API：
- 必填字段是否齐全（id/shot_no/scene/first_frame/prompt/negative_prompt/
  duration_sec/aspect_ratio/platform_recommend/width/height）。
- first_frame/last_frame/ref_images 引用的文件是否在本地磁盘真实存在
  （相对路径按运行时的当前工作目录解析，约定从仓库根目录运行）。
- width/height 是否能被 64 整除（LTX-2.5 的已知限制，见
  short-drama-video-gen/references/ltx2_self_hosted.md 第 5 点）。
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

    for text_field in ("prompt", "negative_prompt"):
        text = job.get(text_field) or ""
        for marker in PLACEHOLDER_MARKERS:
            if marker in text:
                errors.append(
                    f"[{label}] `{text_field}` 里残留占位符文本 `{marker}`，看起来没有真正展开"
                )

    if job.get("num_frames") is None:
        fps = job.get("fps", 24)
        est = round(job.get("duration_sec", 0) * fps) if job.get("duration_sec") else None
        warnings.append(
            f"[{label}] 未显式指定 num_frames，ltx_ssh_submit.py 会按 duration_sec×{fps}fps"
            f"（≈{est} 帧）自动估算，确认这符合预期"
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
