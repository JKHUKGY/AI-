#!/usr/bin/env python3
"""把 h3_jobs.json 提交给 **MiniMax 官方云 API**（不是自建 SGLang）。

跟同目录 h3_submit.py 的关系：两个脚本吃的是**同一份 h3_jobs.json**，
但打的是完全不同的接口，请求体格式也完全不同。

               h3_submit.py（自建）              h3_cloud_submit.py（官方云）
  ----------   ------------------------------   ------------------------------
  接口         POST {endpoint}/v1/videos        POST https://api.minimax.io/v2/video_generation
  鉴权         无（隧道里的本机服务）             Authorization: Bearer <api_key>
  图片         conditions[].uri = data URL      content[].image_url.url = data URI / 公网 URL / mm_file://
  时长         num_frames（17n+5，任意小数）      duration 整数秒，4-15
  分辨率       target.short_edge 任意（32 倍数）   resolution 只有 "768P" / "2K"
  seed         支持，可复现                       **官方 API 不暴露 seed，复现只能靠多抽**
  成本         租卡按小时                         按秒计费，跑完不用关机

官方接口约定（2026-09 文档）：
    POST /v2/video_generation                  提交，返回 {"task_id": ...}
    GET  /v2/query/video_generation/{task_id}  查状态（旧文档是 ?task_id=，本脚本两种都试）
    task.status == "succeeded" → task.content.url 直接就是 mp4 下载地址

API key 从下面任一处读，**不写进仓库**（跟 runpod_config.json 同一个规矩）：
    1. --api-key
    2. 环境变量 MINIMAX_API_KEY
    3. .claude/skills/minimax-h3-generate/minimax_config.json 里的 {"api_key": "..."}（已 gitignore）

用法:
    # ① 先看请求体，不花钱（图片位置只打摘要，不打整段 base64）
    python3 h3_cloud_submit.py --jobs .../h3_jobs.json --out-dir .../videos/ep01 \
        --only ep01_镜01+1 --dry-run

    # ② 落一套可审阅/可提交的 payload 文件（图片写成 file:// 占位，人能看）
    python3 h3_cloud_submit.py --jobs ... --out-dir ... --emit-payloads .../cloud_payloads

    # ③ 落完全自包含、能直接 curl -d @file 的 payload（每个几 MB，别进 git）
    python3 h3_cloud_submit.py --jobs ... --out-dir ... \
        --emit-payloads /tmp/payloads --inline-base64

    # ④ 真提交（2K、时长向上取整）
    python3 h3_cloud_submit.py --jobs ... --out-dir ... --resolution 2K
"""
import argparse
import base64
import json
import math
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URLS = {"global": "https://api.minimax.io", "cn": "https://api.minimaxi.com"}
MODELS = {"MiniMax-H3", "MiniMax-H3-Max"}
# 官方硬规则（platform 文档 + api-reference）
RESOLUTIONS = {"MiniMax-H3": {"768P", "2K"}, "MiniMax-H3-Max": {"480P", "768P"}}
DURATION_RANGE = {"MiniMax-H3": (4, 15), "MiniMax-H3-Max": (5, 15)}
RATIOS = {"adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
PROMPT_MAX_CHARS = 7000
IMG_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
IMG_MAX_BYTES = 30 * 1024 * 1024
IMG_DIM_RANGE = (256, 5760)
IMG_RATIO_RANGE = (0.4, 2.5)          # width/height
MAX_IMAGES, MAX_VIDEOS, MAX_AUDIOS, MAX_FILES = 9, 3, 3, 12
BODY_MAX_BYTES = 64 * 1024 * 1024
ROLE_MAP = {"reference": "reference_image", "reference_image": "reference_image",
            "first_frame": "first_frame", "last_frame": "last_frame"}

POLL_INTERVAL = 10
POLL_TIMEOUT = 1800
DONE_STATES = {"succeeded", "success", "completed", "done"}
FAIL_STATES = {"failed", "error", "cancelled", "canceled"}


class JobError(Exception):
    pass


# ------------------------------------------------------------------ HTTP
def http_json(url, api_key, method="GET", body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:800]
        raise JobError(f"HTTP {e.code} {url}\n{detail}") from None
    return json.loads(raw) if raw else {}


def http_bytes(url, timeout=900):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


# ------------------------------------------------------------------ 装配
def to_data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def snap_duration(seconds, policy, lo, hi, jid, issues):
    """自建那条走 num_frames（17n+5，小数时长）；官方 API 只吃整数秒。

    默认 ceil：宁可片尾多留一点静止，也不要把最后一拍切掉——提示词里逐拍
    时间戳是按原时长写的，floor/nearest 往下取整会削掉末拍动作。
    """
    if policy == "ceil":
        d = math.ceil(seconds - 1e-9)
    elif policy == "floor":
        d = math.floor(seconds + 1e-9)
    else:
        d = round(seconds)
    if d < lo:
        issues.append(f"{jid}: 时长 {seconds:.3f}s 取整成 {d}s，低于官方下限 {lo}s，已抬到 {lo}s")
        d = lo
    if d > hi:
        issues.append(f"{jid}: 时长 {seconds:.3f}s 超过官方上限 {hi}s，已压到 {hi}s")
        d = hi
    if d < seconds - 1e-9:
        issues.append(f"{jid}: 时长 {seconds:.3f}s → {d}s，**末尾 {seconds - d:.3f}s 的动作会被切掉**")
    return d


def check_image(abs_p, jid, issues):
    ext = Path(abs_p).suffix.lower()
    if ext not in IMG_FORMATS:
        issues.append(f"{jid}: {Path(abs_p).name} 格式 {ext} 不在官方支持列表 {sorted(IMG_FORMATS)}")
    size = os.path.getsize(abs_p)
    if size > IMG_MAX_BYTES:
        issues.append(f"{jid}: {Path(abs_p).name} {size / 1e6:.1f} MB 超过单图 30 MB 上限")
    try:
        from PIL import Image
        with Image.open(abs_p) as im:
            w, h = im.size
    except Exception:
        issues.append(f"{jid}: 装不了 PIL，{Path(abs_p).name} 的尺寸/画幅没校验（官方要求边长 256-5760、宽高比 0.4-2.5）")
        return
    lo, hi = IMG_DIM_RANGE
    if not (lo <= w <= hi and lo <= h <= hi):
        issues.append(f"{jid}: {Path(abs_p).name} {w}×{h} 越出边长 {lo}-{hi} 的范围")
    r = w / h
    if not (IMG_RATIO_RANGE[0] <= r <= IMG_RATIO_RANGE[1]):
        issues.append(f"{jid}: {Path(abs_p).name} 宽高比 {r:.3f} 越出 0.4-2.5")


def build_payload(job, root, args, issues, inline=True):
    """h3_jobs.json 的一条 → 官方 /v2/video_generation 请求体。"""
    jid = job["id"]
    if job.get("task") not in (None, "ref2va", "fl2va", "t2va"):
        issues.append(f"{jid}: task={job['task']} 不认识")

    prompt = job["prompt"]
    if len(prompt) > PROMPT_MAX_CHARS:
        issues.append(f"{jid}: 提示词 {len(prompt)} 字符超过官方 {PROMPT_MAX_CHARS} 上限")
    content = [{"type": "text", "text": prompt}]

    n = {"image": 0, "video": 0, "audio": 0}
    has_frame_role = False
    for c in job.get("conditions") or []:
        kind = c.get("type", "image")
        if kind not in n:
            issues.append(f"{jid}: conditions 里出现了不认识的 type={kind}")
            continue
        n[kind] += 1
        role = ROLE_MAP.get(c.get("role", "reference"))
        if role is None:
            issues.append(f"{jid}: role={c.get('role')} 官方不认，按 reference_image 处理")
            role = "reference_image"
        if role in ("first_frame", "last_frame"):
            has_frame_role = True

        p = c.get("path")
        if p:
            abs_p = p if os.path.isabs(p) else os.path.join(root, p)
            if not os.path.exists(abs_p):
                raise JobError(f"{jid}: 参考文件不存在: {abs_p}")
            if kind == "image":
                check_image(abs_p, jid, issues)
            url = to_data_uri(abs_p) if inline else "file://" + p
        else:
            url = c.get("uri") or c.get("url")
            if not url:
                raise JobError(f"{jid}: conditions 里这一项既没有 path 也没有 uri")
        content.append({"type": f"{kind}_url", f"{kind}_url": {"url": url}, "role": role})

    if n["image"] > MAX_IMAGES:
        issues.append(f"{jid}: 参考图 {n['image']} 张超过 {MAX_IMAGES} 张上限")
    if n["video"] > MAX_VIDEOS:
        issues.append(f"{jid}: 参考视频 {n['video']} 段超过 {MAX_VIDEOS} 段上限")
    if n["audio"] > MAX_AUDIOS:
        issues.append(f"{jid}: 参考音频 {n['audio']} 段超过 {MAX_AUDIOS} 段上限")
    if sum(n.values()) > MAX_FILES:
        issues.append(f"{jid}: 参考素材共 {sum(n.values())} 个超过总数 {MAX_FILES} 上限")
    if n["audio"] and not (n["image"] or n["video"]):
        issues.append(f"{jid}: 官方要求音频不能作为唯一输入，必须和图或视频一起给")

    lo, hi = DURATION_RANGE[args.model]
    target = job.get("target") or {}
    duration = snap_duration(float(target.get("duration_seconds") or 0), args.duration_policy,
                             lo, hi, jid, issues)

    # 画幅：带 first_frame/last_frame 的任务官方规定 ratio 恒为 adaptive
    ratio = args.ratio or target.get("aspect_ratio") or "adaptive"
    if has_frame_role and ratio != "adaptive":
        issues.append(f"{jid}: 有 first_frame/last_frame，官方规定 ratio 恒为 adaptive，已改")
        ratio = "adaptive"
    if ratio not in RATIOS:
        issues.append(f"{jid}: ratio={ratio} 不在官方列表 {sorted(RATIOS)}，已改成 adaptive")
        ratio = "adaptive"

    if job.get("seed"):
        issues.append(f"{jid}: 卡里的 seed={job['seed']} **官方 API 不接受，已丢弃**，这条不可复现")

    payload = {"model": args.model, "content": content,
               "resolution": args.resolution, "duration": duration, "ratio": ratio}
    if args.callback_url:
        payload["callback_url"] = args.callback_url

    if inline:
        nbytes = len(json.dumps(payload).encode())
        if nbytes > BODY_MAX_BYTES:
            issues.append(f"{jid}: 请求体 {nbytes / 1e6:.1f} MB 超过官方 64 MB 上限，"
                          f"把参考图传成公网 URL 或 mm_file:// 再来")
    return payload, duration


def preview(payload):
    """把 data URI 折叠成摘要，方便肉眼看请求体。"""
    p = json.loads(json.dumps(payload))
    for item in p["content"]:
        for k in ("image_url", "video_url", "audio_url"):
            if k in item:
                u = item[k]["url"]
                if u.startswith("data:"):
                    item[k]["url"] = f"<{u[:u.find(';')]}; base64 {len(u)} 字符>"
    t = p["content"][0]["text"]
    if len(t) > 600:
        p["content"][0]["text"] = t[:600] + f"…（共 {len(t)} 字符）"
    return p


# ------------------------------------------------------------------ 提交
def query_task(base, api_key, task_id):
    """两种查询形态都试：新文档是路径参数，早期示例是 ?task_id=。"""
    try:
        return http_json(f"{base}/v2/query/video_generation/{task_id}", api_key)
    except JobError as e:
        if "HTTP 404" not in str(e):
            raise
    q = urllib.parse.urlencode({"task_id": task_id})
    return http_json(f"{base}/v2/query/video_generation?{q}", api_key)


def run_job(job, args, root, api_key, base):
    jid = job["id"]
    print(f"\n=== {jid} ===", flush=True)
    issues = []
    payload, duration = build_payload(job, root, args, issues, inline=not args.dry_run)
    for msg in issues:
        print(f"  ⚠️  {msg}", flush=True)

    if args.dry_run:
        print(json.dumps(preview(payload), ensure_ascii=False, indent=2), flush=True)
        return {"id": jid, "status": "dry_run", "duration": duration, "issues": issues}

    created = http_json(f"{base}/v2/video_generation", api_key, "POST", payload)
    task_id = created.get("task_id")
    if not task_id:
        return {"id": jid, "status": "error", "error": f"提交没拿到 task_id: {created}", "issues": issues}
    print(f"  已提交 task_id={task_id}（{duration}s / {args.resolution}），轮询中…", flush=True)

    t0 = time.time()
    while True:
        if time.time() - t0 > POLL_TIMEOUT:
            return {"id": jid, "status": "error", "error": f"轮询超时（{POLL_TIMEOUT}s）",
                    "task_id": task_id, "issues": issues}
        task = (query_task(base, api_key, task_id) or {}).get("task") or {}
        st = str(task.get("status", "")).lower()
        if st in DONE_STATES:
            url = ((task.get("content") or {}).get("url"))
            if not url:
                return {"id": jid, "status": "error", "error": f"成功但没给下载地址: {task}",
                        "task_id": task_id, "issues": issues}
            break
        if st in FAIL_STATES:
            return {"id": jid, "status": "error", "error": f"服务端返回 {st}: {task.get('error')}",
                    "task_id": task_id, "issues": issues}
        print(f"  … {st or '(无状态)'} ({int(time.time() - t0)}s)", flush=True)
        time.sleep(POLL_INTERVAL)

    blob = http_bytes(url)
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{jid}_cloud.mp4")
    with open(out_path, "wb") as f:
        f.write(blob)
    print(f"  已下载 → {out_path}（{len(blob) / 1e6:.1f} MB，用时 {int(time.time() - t0)}s）", flush=True)
    return {"id": jid, "status": "done", "output": out_path, "task_id": task_id,
            "duration": duration, "issues": issues}


def resolve_api_key(args):
    if args.api_key:
        return args.api_key
    if os.environ.get("MINIMAX_API_KEY"):
        return os.environ["MINIMAX_API_KEY"]
    cfg = Path(__file__).resolve().parent.parent / "minimax_config.json"
    if cfg.exists():
        k = json.loads(cfg.read_text(encoding="utf-8")).get("api_key")
        if k:
            return k
    sys.exit("找不到 API key：给 --api-key，或设 MINIMAX_API_KEY，或在 "
             f"{cfg} 里写 {{\"api_key\": \"...\"}}（该文件已 gitignore）")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", required=True, help="h3_jobs.json 路径（跟自建那条同一份）")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--root", default=os.getcwd(), help="仓库根目录，参考图路径相对它解析")
    ap.add_argument("--only", nargs="+", metavar="ID")
    ap.add_argument("--api-key")
    ap.add_argument("--region", choices=list(BASE_URLS), default="global",
                    help="global=api.minimax.io（海外）/ cn=api.minimaxi.com（国内）")
    ap.add_argument("--model", choices=sorted(MODELS), default="MiniMax-H3")
    ap.add_argument("--resolution", default="2K",
                    help="H3: 768P/2K；H3-Max: 480P/768P。自建那条锁 768 是开源权重的限制，云端别沿用")
    ap.add_argument("--ratio", help=f"默认取 target.aspect_ratio。可选 {sorted(RATIOS)}")
    ap.add_argument("--duration-policy", choices=["ceil", "nearest", "floor"], default="ceil")
    ap.add_argument("--callback-url")
    ap.add_argument("--dry-run", action="store_true", help="只打请求体，不提交、不花钱")
    ap.add_argument("--emit-payloads", metavar="DIR",
                    help="把每条请求体单独落成 <id>.json")
    ap.add_argument("--inline-base64", action="store_true",
                    help="--emit-payloads 时把图片内联成 data URI（文件几 MB，能直接 curl -d @file，别进 git）")
    args = ap.parse_args()

    if args.resolution not in RESOLUTIONS[args.model]:
        sys.exit(f"{args.model} 的 resolution 只能是 {sorted(RESOLUTIONS[args.model])}")

    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    if args.only:
        want = set(args.only)
        jobs = [j for j in jobs if j["id"] in want or str(j.get("shot_no")) in want]
        if not jobs:
            sys.exit(f"--only {args.only} 没匹配到任何镜头")

    # ---- 只落 payload 文件，不提交
    if args.emit_payloads:
        out = Path(args.emit_payloads)
        out.mkdir(parents=True, exist_ok=True)
        all_issues, total = [], 0
        for job in jobs:
            issues = []
            payload, duration = build_payload(job, args.root, args, issues,
                                              inline=args.inline_base64)
            total += duration
            (out / f"{job['id']}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            all_issues += issues
        # seed 那条每镜都会报一次，26 行一模一样的没意义，折成一行
        dropped = [m for m in all_issues if "官方 API 不接受" in m]
        for msg in all_issues:
            if msg not in dropped:
                print(f"⚠️  {msg}")
        if dropped:
            print(f"⚠️  {len(dropped)} 条卡里的 seed 全部丢弃（官方 API 不暴露 seed），这批不可复现")
        print(f"\n{len(jobs)} 条请求体 → {out}"
              f"（{'含内联 base64，可直接 curl -d @file' if args.inline_base64 else 'file:// 占位，提交前由本脚本内联'}）")
        print(f"计费时长合计 {total} 秒 @ {args.resolution}")
        return

    # --dry-run 不打网络，不该被没配 key 卡住
    api_key = None if args.dry_run else resolve_api_key(args)
    base = BASE_URLS[args.region]
    os.makedirs(args.out_dir, exist_ok=True)
    results = []
    for job in jobs:
        try:
            results.append(run_job(job, args, args.root, api_key, base))
        except Exception as e:
            print(f"镜头 {job.get('id')} 出错: {e}", file=sys.stderr, flush=True)
            results.append({"id": job.get("id"), "status": "error", "error": str(e)})

    summary = os.path.join(args.out_dir, "h3_cloud_results.json")
    with open(summary, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果汇总写入 {summary}")
    failed = [r for r in results if r["status"] not in ("done", "dry_run")]
    if failed:
        print(f"\n{len(failed)} 条未成功，检查上面的报错或 {summary}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
