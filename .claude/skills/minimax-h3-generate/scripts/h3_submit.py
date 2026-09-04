#!/usr/bin/env python3
"""把 h3_jobs.json 提交给远端的 MiniMax-H3（SGLang）服务，轮询、下载结果。

**跟 ltx_ssh_submit.py 的根本区别**：LTX 是"每镜 ssh 过去跑一次 CLI，每次重新
装 67GB 权重"；H3 是"先把服务起起来常驻，然后走 HTTP 一条条提交"。所以 H3 这边
权重只装一次，第 2 条往后没有装载开销——这是 H3 相对 LTX 在批量上的结构性优势。

服务端接口（官方 scripts/readme/reproducible-768p-*.sh 里的真实请求）：
    POST /v1/videos                  提交，返回 {"id": ...}
    GET  /v1/videos/{id}             查状态，返回 {"status": ...}
    GET  /v1/videos/{id}/content     下载 mp4

conditions 里的图片官方用 uri（公网 URL 或 data URL）。我们的关键帧在本地，
所以这里把本地 PNG 读成 base64 data URL 直接塞进请求体——省掉"先传到图床"
这一步，代价是请求体会大几 MB，局域网/SSH 隧道里无所谓。

用法:
    # 起隧道（把远端 30011 映射到本地）后
    python3 h3_submit.py --jobs h3_jobs.json --out-dir output/.../videos/ep01 \\
        --endpoint http://127.0.0.1:30011

    # 直连远端公网 IP
    python3 h3_submit.py --jobs ... --out-dir ... --endpoint http://<ip>:30011

    # 跑完自动关显卡（跟 ltx_ssh_submit.py 一样的收尾语义）
    python3 h3_submit.py --jobs ... --out-dir ... --endpoint ... \\
        --config ltx_remote_config.json --auto-stop

⚠️ 后台跑一定要 setsid 隔离进程组，理由见 SKILL.md「六条硬教训」第 ⑤ 条。
"""
import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

POLL_INTERVAL = 10
POLL_TIMEOUT = 1800          # 单条最多等 30 分钟
DONE_STATES = {"completed", "succeeded", "success", "done"}
FAIL_STATES = {"failed", "error", "cancelled", "canceled"}


def http_json(url, method="GET", body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw else {}


def http_bytes(url, timeout=600):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def to_data_url(path):
    """本地图片 → base64 data URL，直接进请求体，不需要图床。"""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def build_request(job, root):
    """把 h3_jobs.json 里的一条转成官方请求体。"""
    conditions = []
    for c in job.get("conditions") or []:
        p = c.get("path")
        if p:
            abs_p = p if os.path.isabs(p) else os.path.join(root, p)
            if not os.path.exists(abs_p):
                raise FileNotFoundError(f"条件文件不存在: {abs_p}")
            item = {"type": c["type"], "uri": to_data_url(abs_p), "role": c.get("role", "reference")}
        else:
            item = {"type": c["type"], "uri": c["uri"], "role": c.get("role", "reference")}
        if "frame_index" in c:
            item["frame_index"] = c["frame_index"]
        conditions.append(item)

    return {
        "task": job["task"],
        "prompt": job["prompt"],
        "conditions": conditions,
        "target": job["target"],
        "seed": int(job.get("seed") or 0),
    }


def run_job(job, endpoint, out_dir, root, dry_run=False):
    jid = job["id"]
    out_path = os.path.join(out_dir, f"{jid}.mp4")
    print(f"\n=== {jid} ===", flush=True)

    payload = build_request(job, root)
    if dry_run:
        preview = dict(payload)
        preview["conditions"] = [
            {**c, "uri": f"<data url, {len(c['uri'])} chars>"} for c in payload["conditions"]]
        print(json.dumps(preview, ensure_ascii=False, indent=2)[:2000], flush=True)
        return {"id": jid, "status": "dry_run"}

    created = http_json(f"{endpoint}/v1/videos", "POST", payload)
    vid = created.get("id")
    if not vid:
        return {"id": jid, "status": "error", "error": f"提交没拿到 id: {created}"}
    print(f"  已提交，服务端 id={vid}，轮询中…", flush=True)

    t0 = time.time()
    while True:
        if time.time() - t0 > POLL_TIMEOUT:
            return {"id": jid, "status": "error", "error": f"轮询超时（{POLL_TIMEOUT}s）", "video_id": vid}
        try:
            st = http_json(f"{endpoint}/v1/videos/{vid}").get("status", "")
        except urllib.error.URLError as e:
            return {"id": jid, "status": "error", "error": f"查状态失败: {e}", "video_id": vid}
        low = str(st).lower()
        if low in DONE_STATES:
            break
        if low in FAIL_STATES:
            return {"id": jid, "status": "error", "error": f"服务端返回 {st}", "video_id": vid}
        print(f"  … {st} ({int(time.time() - t0)}s)", flush=True)
        time.sleep(POLL_INTERVAL)

    blob = http_bytes(f"{endpoint}/v1/videos/{vid}/content")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(blob)
    print(f"  已下载 → {out_path}（{len(blob) / 1e6:.1f} MB，用时 {int(time.time() - t0)}s）", flush=True)
    return {"id": jid, "status": "done", "output": out_path, "video_id": vid}


def auto_stop(config_path, mode):
    """跟 ltx_ssh_submit.py 完全一样的收尾语义，直接复用 gpu_teardown.py。"""
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    script = str(Path(__file__).resolve().parent / "gpu_teardown.py")
    cmd = ["python3", script, "--platform", cfg["platform"],
           "--instance-id", str(cfg["instance_id"]), "--mode", mode,
           "--config", config_path]
    print("\n=== 自动关闭显卡 ===", flush=True)
    print(" ".join(cmd), flush=True)
    sys.stdout.flush()
    subprocess.run(cmd)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", required=True, help="h3_jobs.json 路径")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--endpoint", required=True, help="SGLang 服务地址，如 http://127.0.0.1:30011")
    ap.add_argument("--root", default=os.getcwd(), help="仓库根目录（条件文件路径相对它解析）")
    ap.add_argument("--only", nargs="+", metavar="ID")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", help="ltx_remote_config.json，--auto-stop 时必需")
    ap.add_argument("--auto-stop", action="store_true",
                    help="这一批跑完（含报错/中断）自动关显卡")
    ap.add_argument("--auto-stop-mode", choices=["auto", "stop", "terminate"], default="auto")
    args = ap.parse_args()

    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    if args.only:
        want = set(args.only)
        jobs = [j for j in jobs if j["id"] in want or str(j.get("shot_no")) in want]
        if not jobs:
            sys.exit(f"--only {args.only} 没匹配到任何镜头")

    # --auto-stop 需要的字段在提交任何任务之前就校验掉，理由同 ltx_ssh_submit.py：
    # 别等批量任务跑完了才发现关不掉。
    if args.auto_stop and not args.dry_run:
        if not args.config:
            sys.exit("--auto-stop 需要 --config 指向 ltx_remote_config.json")
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        missing = [k for k in ("platform", "instance_id") if not cfg.get(k)]
        if missing:
            sys.exit(f"--auto-stop 需要 config 里有 {', '.join(missing)} 字段")

    os.makedirs(args.out_dir, exist_ok=True)
    results = []
    try:
        for job in jobs:
            try:
                results.append(run_job(job, args.endpoint.rstrip("/"),
                                       args.out_dir, args.root, args.dry_run))
            except Exception as e:
                print(f"镜头 {job.get('id')} 出错: {e}", file=sys.stderr, flush=True)
                results.append({"id": job.get("id"), "status": "error", "error": str(e)})

        summary = os.path.join(args.out_dir, "h3_submit_results.json")
        with open(summary, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果汇总写入 {summary}")
        failed = [r for r in results if r["status"] not in ("done", "dry_run")]
        if failed:
            print(f"\n{len(failed)} 个镜头未成功，检查上面的报错或 {summary}", file=sys.stderr)
    finally:
        if args.auto_stop and not args.dry_run:
            auto_stop(args.config, args.auto_stop_mode)


if __name__ == "__main__":
    main()
