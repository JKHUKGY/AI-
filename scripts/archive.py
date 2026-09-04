#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短剧素材冷归档 / 取回工具。

把暂时用不上的项目里的二进制素材（png/mp4/...）打包上传到 Google Drive，
本地只留一份清单（.archived.json），需要时再原样取回。

剧本、镜头表、jobs.json 这类文本永远留在仓库里，不参与归档。

用法:
    scripts/archive.py status                     # 空间报告：哪些在本地、哪些在云端
    scripts/archive.py list                       # 列出云端已归档的项目
    scripts/archive.py stash 千金归位 暗局          # 打包上传，然后删本地二进制
    scripts/archive.py stash --all-except 出狱后我成为了非洲矿王_v2
    scripts/archive.py restore 千金归位            # 全部取回
    scripts/archive.py restore 千金归位 -v keyframes  # 只取回 keyframes 分卷
    scripts/archive.py verify 千金归位             # 只校验，不下载全部
    scripts/archive.py export 千金归位 -o /path   # 导出 tar.zst 到本地路径（不传云）

加 --dry-run 可以先看它打算做什么，不实际动文件。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
MANIFEST_NAME = ".archived.json"
CONFIG_PATH = REPO_ROOT / "scripts" / "archive_config.json"

# 这些后缀算“素材”，会被打包归档。其余（.md/.json/.txt/.jsonl/.log）一律留在仓库。
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff",
    ".mp4", ".mov", ".mkv", ".webm", ".avi",
    ".wav", ".mp3", ".aac", ".flac", ".m4a",
    ".psd", ".zip", ".tar", ".zst",
}

DEFAULT_CONFIG = {
    "remote": "gdrive",
    "remote_base": "AI-短剧归档",
    "zstd_level": 1,
}


# --------------------------------------------------------------------------- 基础工具

class Fail(Exception):
    """预期内的错误，打印后干净退出，不摔栈。"""


def log(msg: str) -> None:
    print(msg, flush=True)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise Fail(f"{CONFIG_PATH} 不是合法 JSON: {exc}") from exc
    return cfg


def rclone_bin() -> str:
    exe = shutil.which("rclone") or str(Path.home() / ".local/bin/rclone")
    if not Path(exe).exists():
        raise Fail(
            "找不到 rclone。安装:\n"
            "  curl -sL -o /tmp/rclone.zip https://downloads.rclone.org/rclone-current-linux-amd64.zip\n"
            "  cd /tmp && unzip -oq rclone.zip && mv rclone-*-linux-amd64/rclone ~/.local/bin/"
        )
    return exe


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def dwidth(text: str) -> int:
    """字符串在终端里占几格 —— 中文和全角标点算两格。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def dpad(text: str, width: int) -> str:
    return text + " " * max(0, width - dwidth(text))


def human(n: int) -> str:
    v = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if v < 1024 or unit == "T":
            return f"{v:.0f}{unit}" if unit == "B" else f"{v:.1f}{unit}"
        v /= 1024
    return f"{v:.1f}T"


def sha256_of(path: Path, _buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_buf):
            h.update(chunk)
    return h.hexdigest()


def check_remote(cfg: dict) -> None:
    """确认 rclone remote 已经配好，否则给出可操作的指引。"""
    remote = cfg["remote"]
    out = subprocess.run(
        [rclone_bin(), "listremotes"], capture_output=True, text=True
    ).stdout
    if f"{remote}:" not in out.split():
        raise Fail(
            f"rclone 里还没有名为 '{remote}' 的 remote。\n"
            f"在终端里跑一次（前面加 ! 让它在会话里执行）:\n"
            f"    ! rclone config\n"
            f"  n) 新建 → 名字填 {remote} → 类型选 drive → client_id/secret 直接回车\n"
            f"  scope 选 1 (完全访问) → 剩下的回车 → 浏览器授权\n"
            f"配好后再跑一次本命令。"
        )


def remote_path(cfg: dict, *parts: str) -> str:
    """
    拼出 rclone 目标，形如 'gdrive:AI-短剧归档/千金归位'。
    Drive 上 remote_base 是相对的文件夹名；本地盘 remote 可能给绝对路径，
    所以开头的斜杠必须留着，否则 rclone 会按当前目录解析、把包写进仓库里。
    """
    base = cfg["remote_base"].rstrip("/")
    segs = [p.strip("/") for p in parts if p.strip("/")]
    joined = "/".join([base, *segs]) if base else "/".join(segs)
    return f"{cfg['remote']}:{joined}"


# --------------------------------------------------------------------------- 扫描

def project_dir(name: str) -> Path:
    d = OUTPUT_DIR / name
    if not d.is_dir():
        raise Fail(f"项目目录不存在: {d}")
    return d


def all_projects() -> list[str]:
    if not OUTPUT_DIR.is_dir():
        return []
    return sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())


def scan_volumes(proj: Path) -> dict[str, list[Path]]:
    """
    把项目里的二进制按顶层子目录分卷。直接躺在项目根下的二进制归到 _root。
    返回 {分卷名: [相对项目目录的路径, ...]}，只含非空分卷。
    """
    vols: dict[str, list[Path]] = {}
    for path in sorted(proj.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in BINARY_EXTS:
            continue
        rel = path.relative_to(proj)
        vol = rel.parts[0] if len(rel.parts) > 1 else "_root"
        vols.setdefault(vol, []).append(rel)
    return vols


def read_manifest(proj: Path) -> dict | None:
    mf = proj / MANIFEST_NAME
    if not mf.exists():
        return None
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Fail(f"清单损坏 {mf}: {exc}") from exc


# --------------------------------------------------------------------------- stash

def cmd_stash(args, cfg: dict) -> int:
    targets = resolve_targets(args)
    if not targets:
        raise Fail("没有指定要归档的项目。用 --all-except <要保留的项目> 或直接列项目名。")

    if not args.dry_run:
        check_remote(cfg)

    log(f"准备归档 {len(targets)} 个项目: {', '.join(targets)}\n")
    total_freed = 0

    for name in targets:
        proj = project_dir(name)
        vols = scan_volumes(proj)
        if not vols:
            log(f"[跳过] {name}: 没有可归档的二进制素材")
            continue

        existing = read_manifest(proj) or {}
        manifest = {
            "project": name,
            "archived_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "remote": remote_path(cfg, name),
            "volumes": dict(existing.get("volumes", {})),
        }

        proj_bytes = 0
        for vol, rels in vols.items():
            size = sum((proj / r).stat().st_size for r in rels)
            log(f"[{name}/{vol}] {len(rels)} 个文件, {human(size)}")
            if args.dry_run:
                proj_bytes += size
                continue
            entry = stash_volume(cfg, proj, name, vol, rels)
            manifest["volumes"][vol] = entry
            proj_bytes += size

        if args.dry_run:
            log(f"[dry-run] {name} 归档后可释放 {human(proj_bytes)}\n")
            total_freed += proj_bytes
            continue

        # 上传全部校验通过后才写清单、删本地文件。
        (proj / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for rels in vols.values():
            for rel in rels:
                (proj / rel).unlink()
        prune_empty_dirs(proj)
        log(f"[完成] {name} 已归档，释放 {human(proj_bytes)}\n")
        total_freed += proj_bytes

    tag = "[dry-run] 预计" if args.dry_run else "累计"
    log(f"{tag}释放空间: {human(total_freed)}")
    if args.dry_run:
        log("这是 dry-run，什么都没动。去掉 --dry-run 才会真的执行。")
    else:
        log("清单文件 .archived.json 记得提交进 git，取回时要靠它。")
    return 0


def stash_volume(cfg: dict, proj: Path, name: str, vol: str, rels: list[Path]) -> dict:
    """打一个分卷 → 上传 → 校验远端。任一步失败都抛异常，本地文件保持原样。"""
    files = [
        {
            "path": str(rel),
            "size": (proj / rel).stat().st_size,
            "sha256": sha256_of(proj / rel),
        }
        for rel in rels
    ]

    archive_name = f"{name}__{vol}.tar.zst"
    with tempfile.TemporaryDirectory(prefix="archive-") as tmp:
        local_archive = Path(tmp) / archive_name

        # 用 -T - 从 stdin 读文件列表，避免超长命令行和中文名转义问题。
        listing = "\n".join(str(r) for r in rels) + "\n"
        log(f"  打包 {archive_name} ...")
        proc = subprocess.run(
            ["tar", "-C", str(proj), "-I", f"zstd -{cfg['zstd_level']} -T0",
             "-cf", str(local_archive), "-T", "-"],
            input=listing, text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise Fail(f"打包失败 {archive_name}:\n{proc.stderr.strip()}")

        arc_size = local_archive.stat().st_size
        arc_sha = sha256_of(local_archive)
        raw = sum(f["size"] for f in files)
        ratio = f"{arc_size / raw:.0%}" if raw else "-"
        log(f"  压缩后 {human(arc_size)} ({ratio} of {human(raw)})，上传中 ...")

        dest = remote_path(cfg, name)
        run([rclone_bin(), "copyto", str(local_archive), f"{dest}/{archive_name}",
             "--progress", "--drive-chunk-size", "64M"])

        # 回读远端大小确认上传完整，之后才允许删本地。
        out = subprocess.run(
            [rclone_bin(), "lsjson", f"{dest}/{archive_name}"],
            capture_output=True, text=True,
        )
        if out.returncode != 0:
            raise Fail(f"上传后无法在远端找到 {archive_name}:\n{out.stderr.strip()}")
        remote_size = json.loads(out.stdout)[0]["Size"]
        if remote_size != arc_size:
            raise Fail(
                f"{archive_name} 远端大小 {remote_size} != 本地 {arc_size}，"
                "上传不完整，本地文件已保留。"
            )
        log(f"  远端校验通过 ✓")

    return {
        "archive": archive_name,
        "archive_size": arc_size,
        "archive_sha256": arc_sha,
        "raw_size": raw,
        "file_count": len(files),
        "files": files,
    }


def prune_empty_dirs(root: Path) -> None:
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        try:
            next(d.iterdir())
        except StopIteration:
            d.rmdir()


# --------------------------------------------------------------------------- restore

def cmd_restore(args, cfg: dict) -> int:
    check_remote(cfg)
    name = args.project
    proj = project_dir(name)
    manifest = read_manifest(proj)
    if not manifest:
        raise Fail(f"{name} 没有 {MANIFEST_NAME}，说明它没被归档过（或清单丢了）。")

    vols = manifest.get("volumes", {})
    wanted = args.volume or list(vols)
    unknown = [v for v in wanted if v not in vols]
    if unknown:
        raise Fail(f"清单里没有分卷 {unknown}。可用: {list(vols)}")

    dest = manifest.get("remote") or remote_path(cfg, name)
    for vol in wanted:
        entry = vols[vol]
        log(f"[{name}/{vol}] 取回 {entry['file_count']} 个文件 "
            f"({human(entry['archive_size'])} 压缩包)")
        if args.dry_run:
            continue
        restore_volume(cfg, proj, dest, entry)

    if args.dry_run:
        log("这是 dry-run，什么都没下载。")
        return 0

    # 分卷全取回后清单就没用了；只取回一部分则保留剩下的记录。
    remaining = {v: e for v, e in vols.items() if v not in wanted}
    mf = proj / MANIFEST_NAME
    if remaining:
        manifest["volumes"] = remaining
        mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
        log(f"\n已取回 {wanted}；仍在云端: {list(remaining)}")
    else:
        mf.unlink()
        log(f"\n{name} 已完整取回，清单已移除。")
    return 0


def restore_volume(cfg: dict, proj: Path, dest: str, entry: dict) -> None:
    archive_name = entry["archive"]
    with tempfile.TemporaryDirectory(prefix="restore-") as tmp:
        local_archive = Path(tmp) / archive_name
        log(f"  下载 {archive_name} ...")
        run([rclone_bin(), "copyto", f"{dest}/{archive_name}", str(local_archive),
             "--progress"])

        got = sha256_of(local_archive)
        if got != entry["archive_sha256"]:
            raise Fail(
                f"{archive_name} sha256 不匹配，下载损坏。\n"
                f"  期望 {entry['archive_sha256']}\n  实际 {got}"
            )
        log("  压缩包校验通过 ✓，解包中 ...")
        run(["tar", "-C", str(proj), "-I", "zstd -d", "-xf", str(local_archive)])

    bad = []
    for f in entry["files"]:
        target = proj / f["path"]
        if not target.exists():
            bad.append(f"缺失 {f['path']}")
        elif sha256_of(target) != f["sha256"]:
            bad.append(f"损坏 {f['path']}")
    if bad:
        raise Fail("解包后校验失败:\n  " + "\n  ".join(bad[:20]))
    log(f"  {entry['file_count']} 个文件逐一校验通过 ✓")


# --------------------------------------------------------------------------- verify / list / status / export

def cmd_verify(args, cfg: dict) -> int:
    check_remote(cfg)
    name = args.project
    manifest = read_manifest(project_dir(name))
    if not manifest:
        raise Fail(f"{name} 没有归档清单。")
    dest = manifest.get("remote") or remote_path(cfg, name)
    ok = True
    for vol, entry in manifest["volumes"].items():
        out = subprocess.run(
            [rclone_bin(), "lsjson", f"{dest}/{entry['archive']}"],
            capture_output=True, text=True,
        )
        if out.returncode != 0:
            log(f"  ✗ {vol}: 远端找不到 {entry['archive']}")
            ok = False
            continue
        size = json.loads(out.stdout)[0]["Size"]
        if size != entry["archive_size"]:
            log(f"  ✗ {vol}: 大小不符 远端 {human(size)} vs 清单 {human(entry['archive_size'])}")
            ok = False
        else:
            log(f"  ✓ {vol}: {entry['archive']} {human(size)}, {entry['file_count']} 个文件")
    log("\n全部分卷在云端可用。" if ok else "\n有分卷异常，先别删本地素材。")
    return 0 if ok else 1


def cmd_list(args, cfg: dict) -> int:
    log(f"云端归档 ({remote_path(cfg)}):\n")
    found = False
    for name in all_projects():
        manifest = read_manifest(OUTPUT_DIR / name)
        if not manifest:
            continue
        found = True
        vols = manifest["volumes"]
        arc = sum(e["archive_size"] for e in vols.values())
        raw = sum(e.get("raw_size", 0) for e in vols.values())
        cnt = sum(e["file_count"] for e in vols.values())
        log(f"  {name}")
        log(f"    归档于 {manifest['archived_at']}")
        log(f"    {cnt} 个文件, 原始 {human(raw)} → 云端 {human(arc)}")
        detail = ", ".join(f"{v}({e['file_count']})" for v, e in vols.items())
        log(f"    分卷: {detail}")
        log(f"    取回: scripts/archive.py restore {name}")
    if not found:
        log("  (还没有归档过任何项目)")
    return 0


def cmd_status(args, cfg: dict) -> int:
    log("项目占用一览:\n")
    rows = []
    for name in all_projects():
        proj = OUTPUT_DIR / name
        manifest = read_manifest(proj)
        local = sum(
            p.stat().st_size for p in proj.rglob("*")
            if p.is_file() and not p.is_symlink()
        )
        if manifest:
            vols = manifest["volumes"]
            state = f"已归档 ({len(vols)} 分卷)"
            cloud = sum(e.get("raw_size", 0) for e in vols.values())
        else:
            state = "本地"
            cloud = 0
        rows.append((name, local, cloud, state))

    w = max((dwidth(n) for n, *_ in rows), default=10)
    log(f"  {dpad('项目', w)}  {'本地':>8}  {'云端':>8}  状态")
    log(f"  {'-' * w}  {'-' * 8}  {'-' * 8}  ----")
    for name, local, cloud, state in sorted(rows, key=lambda r: -r[1]):
        log(f"  {dpad(name, w)}  {human(local):>8}  "
            f"{(human(cloud) if cloud else '-'):>8}  {state}")

    log(f"\n  {dpad('合计', w)}  {human(sum(r[1] for r in rows)):>8}  "
        f"{human(sum(r[2] for r in rows)):>8}")

    du = shutil.disk_usage(REPO_ROOT)
    log(f"\n磁盘: 共 {human(du.total)}, 已用 {human(du.used)} "
        f"({du.used / du.total:.0%}), 剩余 {human(du.free)}")
    git_dir = REPO_ROOT / ".git"
    if git_dir.exists():
        gsize = sum(p.stat().st_size for p in git_dir.rglob("*") if p.is_file())
        log(f".git: {human(gsize)}  (归档不会缩小这部分，它是提交历史里的旧素材)")
    return 0


def cmd_export(args, cfg: dict) -> int:
    """把项目打成 tar.zst 放到本地路径，不碰云端 —— 给移动硬盘/别的网盘用。"""
    name = args.project
    proj = project_dir(name)
    outdir = Path(args.out).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    vols = scan_volumes(proj)
    if not vols:
        raise Fail(f"{name} 没有可导出的二进制素材。")
    for vol, rels in vols.items():
        target = outdir / f"{name}__{vol}.tar.zst"
        size = sum((proj / r).stat().st_size for r in rels)
        log(f"[{name}/{vol}] {len(rels)} 个文件 {human(size)} → {target}")
        if args.dry_run:
            continue
        listing = "\n".join(str(r) for r in rels) + "\n"
        proc = subprocess.run(
            ["tar", "-C", str(proj), "-I", f"zstd -{cfg['zstd_level']} -T0",
             "-cf", str(target), "-T", "-"],
            input=listing, text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise Fail(f"打包失败:\n{proc.stderr.strip()}")
        log(f"  完成 {human(target.stat().st_size)}")
    log("\n导出的包不删本地素材。确认拷走后自己删，或改用 stash 走云端。")
    return 0


# --------------------------------------------------------------------------- CLI

def resolve_targets(args) -> list[str]:
    if args.all_except:
        keep = set(args.all_except)
        missing = keep - set(all_projects())
        if missing:
            raise Fail(f"--all-except 里的项目不存在: {sorted(missing)}")
        return [
            n for n in all_projects()
            if n not in keep and not read_manifest(OUTPUT_DIR / n)
        ]
    return args.projects


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="短剧素材冷归档 / 取回",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("stash", help="打包上传并删除本地二进制")
    p.add_argument("projects", nargs="*", help="项目名（output/ 下的目录名）")
    p.add_argument("--all-except", nargs="+", metavar="项目",
                   help="归档除这些之外的全部项目")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_stash)

    p = sub.add_parser("restore", help="从云端取回")
    p.add_argument("project")
    p.add_argument("-v", "--volume", action="append", help="只取回指定分卷，可重复")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("verify", help="校验云端归档还在、大小对得上")
    p.add_argument("project")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("list", help="列出已归档项目")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="空间报告")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("export", help="导出 tar.zst 到本地路径，不传云")
    p.add_argument("project")
    p.add_argument("-o", "--out", required=True, help="输出目录")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_export)

    args = ap.parse_args(argv)
    cfg = load_config()
    try:
        return args.func(args, cfg)
    except Fail as exc:
        print(f"\n错误: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"\n外部命令失败: {' '.join(map(str, exc.cmd))}", file=sys.stderr)
        return exc.returncode or 1
    except KeyboardInterrupt:
        print("\n已中断。本地素材没有被删除。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
