#!/usr/bin/env python3
"""扫一遍仓库，打印"现在做到哪一步了"的实时快照。

索引文档（INDEX.md / references/resources.md）是人手写的，会过期；
这个脚本只从磁盘现状统计，不会过期。定位问题时先跑它，再去读文档。

用法：
    python3 .claude/skills/index/scripts/snapshot.py            # 全部
    python3 .claude/skills/index/scripts/snapshot.py --project 暗局
    python3 .claude/skills/index/scripts/snapshot.py --online   # 额外探测线上网站
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
OUTPUT = REPO / "output"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
AZURE_URL = "https://scriptwriter-jia.northcentralus.cloudapp.azure.com/login.html"


def count_files(root: Path, exts=None, suffix=None) -> int:
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "logs"}]
        for f in filenames:
            if exts and Path(f).suffix.lower() in exts:
                n += 1
            elif suffix and f.endswith(suffix):
                n += 1
    return n


def episodes(path: Path, pattern: str) -> list:
    if not path.is_dir():
        return []
    return sorted(p.name for p in path.iterdir() if re.fullmatch(pattern, p.name))


def project_report(proj: Path) -> str:
    lines = [f"## {proj.name}"]

    sb = proj / "storyboard"
    eps = episodes(sb, r"ep\d+\.md")
    have = [f for f in ("style_bible.md", "characters.md", "scenes.md") if (sb / f).exists()]
    if sb.is_dir():
        lines.append(f"  分镜表  : {len(eps)} 集 ({', '.join(eps) if eps else '无 ep0X.md'})"
                     f" | 设定档: {', '.join(have) if have else '无'}")
    else:
        lines.append("  分镜表  : 无 storyboard/ 目录（分镜可能在别处或还没做）")

    assets = proj / "assets"
    if assets.is_dir():
        dirs = [d.name for d in assets.iterdir() if d.is_dir()]
        scenes = [d for d in dirs if d.startswith("SC")]
        chars = [d for d in dirs if not d.startswith("SC")]
        sel = "有 selected.md" if (assets / "selected.md").exists() else "无 selected.md（未记录选片）"
        lines.append(f"  素材图  : 角色/表情目录 {len(chars)} 个, 场景目录 {len(scenes)} 个, "
                     f"图片 {count_files(assets, exts=IMG_EXT)} 张 | {sel}")

    kf = proj / "keyframes"
    for ep in episodes(kf, r"ep\d+"):
        d = kf / ep
        shots = len([x for x in d.iterdir() if x.is_dir()])
        cards = "有卡" if (d / "keyframe_cards.json").exists() else "无卡"
        done = "有 keyframes.md" if (d / "keyframes.md").exists() else "无 keyframes.md"
        lines.append(f"  关键帧  : {ep} → {shots} 镜目录, {count_files(d, exts=IMG_EXT)} 张, {cards}, {done}")

    vd = proj / "videos"
    for ep in sorted(p.name for p in vd.iterdir() if p.is_dir()) if vd.is_dir() else []:
        d = vd / ep
        mp4 = count_files(d, suffix=".mp4")
        jobs = "有 video_jobs.json" if (d / "video_jobs.json").exists() else "无 video_jobs.json"
        cards = "有镜头卡" if (d / "shot_cards.json").exists() else "无镜头卡"
        lines.append(f"  视频    : {ep} → {mp4} 个 mp4, {cards}, {jobs}")

    if len(lines) == 2 and not (proj / "assets").is_dir():
        # 不按标准结构组织的目录（试拍/实验），直接列它自己有什么
        loose = sorted(p.name for p in proj.iterdir())[:12]
        lines.append(f"  非标准结构，目录内容: {', '.join(loose)}")

    review = proj / "_web_state" / "review.json"
    if review.exists():
        try:
            data = json.loads(review.read_text(encoding="utf-8"))
            n = sum(len(v) for v in data.values() if isinstance(v, (list, dict)))
            lines.append(f"  剧本家反馈: {review.relative_to(REPO)}（{n} 条记录，读它看剧本家提了什么）")
        except Exception as e:  # 文件坏了也别让整份快照挂掉
            lines.append(f"  剧本家反馈: {review.relative_to(REPO)}（解析失败: {e}）")

    return "\n".join(lines)


def git_state() -> str:
    try:
        br = subprocess.run(["git", "branch", "--show-current"], cwd=REPO,
                            capture_output=True, text=True, timeout=15).stdout.strip()
        st = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                            capture_output=True, text=True, timeout=30).stdout.splitlines()
    except Exception as e:
        return f"git 状态读取失败: {e}"
    dirty = {}
    for line in st:
        top = line[3:].strip('"').split("/")[0]
        dirty[top] = dirty.get(top, 0) + 1
    top = ", ".join(f"{k}({v})" for k, v in sorted(dirty.items(), key=lambda x: -x[1])[:8])
    return f"分支 {br} | 未提交改动 {len(st)} 处: {top or '无'}"


def probe(url: str) -> str:
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return f"{r.status} 可访问"
    except Exception as e:
        return f"不可访问: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="只看某一部剧（目录名，可写前缀）")
    ap.add_argument("--online", action="store_true", help="额外探测线上协作网站是否活着")
    args = ap.parse_args()

    print(f"# 仓库快照  ({REPO})")
    print(git_state())
    print()

    if not OUTPUT.is_dir():
        print("没有 output/ 目录，还没有任何剧的产出。")
        return 0

    projs = sorted(p for p in OUTPUT.iterdir() if p.is_dir())
    if args.project:
        projs = [p for p in projs if p.name.startswith(args.project)] or projs
    for p in projs:
        print(project_report(p))
        print()

    if args.online:
        print("## 线上服务")
        print(f"  Azure 协作网站 {AZURE_URL} → {probe(AZURE_URL)}")
        print("  （VM 开关机状态用 `az vm list -d -o table` 查，见 references/resources.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
