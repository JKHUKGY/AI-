#!/usr/bin/env python3
"""RunPod REST API v1 + GraphQL 的轻量封装：建/查 Network Volume、建/查/开关/
删除 Pod、查 GPU 型号/价格/数据中心。

RunPod 跟 vast.ai / AutoDL 最大的不同：**存储和算力是分开计费、分开生命周期
的两个资源**。Network Volume 一旦建好，跟哪个 Pod 绑定、Pod 起了几次、换没换
GPU 型号都无关——只要新 Pod 创建时指定同一个 --network-volume-id，模型权重
就还在，不需要重新下载。这是本脚本存在的意义，见
references/runpod_gpu_ops.md（2026-09 已经用真实账号跑通一次完整流程：建
Volume → 建 Pod → SSH/SCP → terminate Pod → 用同一个 Volume 重建 Pod → 确认
数据还在，细节和踩过的坑见那份文档）。

认证：REST v1 和 GraphQL 都用 `Authorization: Bearer <token>`，实测确认有效。
**关键坑**：Python `urllib` 默认 User-Agent 会被 Cloudflare 拦截（返回
`error code: 1010`，跟账号/key 无关），必须伪装成浏览器 UA 才能通过——已经在
`BROWSER_UA` 里处理，这里只是记录原因，不要"优化"掉这个看起来多余的 header。

Token 从 runpod_config.json 读（同目录，需要自己创建，已加入 .gitignore），
可以用 --config 指定别的路径。

用法：
  python3 runpod_ops.py datacenters
  python3 runpod_ops.py gputypes --min-memory-gb 80
  python3 runpod_ops.py volume_create --name ltx2-weights --size-gb 120 --datacenter-id US-KS-2
  python3 runpod_ops.py volume_list
  python3 runpod_ops.py create --gpu-type-id "NVIDIA A100-SXM4-80GB" \\
      --network-volume-id <vol_id> --image runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04 \\
      --name ltx-gpu --public-key "$(cat ~/.ssh/id_ed25519.pub)"
  python3 runpod_ops.py status --pod-id <pod_id>
  python3 runpod_ops.py snapshot --pod-id <pod_id>   # 打印价格 + SSH 连接信息
  python3 runpod_ops.py stop --pod-id <pod_id>       # 停止计费
  python3 runpod_ops.py start --pod-id <pod_id>
  python3 runpod_ops.py terminate --pod-id <pod_id>  # 删除 Pod 本体，
                                                       # 实测确认 Network Volume 不受影响、
                                                       # 需要单独 volume_delete 才会丢数据
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "runpod_config.json"
REST_BASE = "https://rest.runpod.io/v1"
GRAPHQL_URL = "https://api.runpod.io/graphql"
# Cloudflare 会拦截 Python urllib 默认的 User-Agent（返回 1010 错误），必须伪装
# 成浏览器 UA 才能通过——2026-09 实测确认，curl 不受影响，只有 urllib 需要这个。
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def load_token(config_path):
    return json.loads(Path(config_path).read_text())["api_key"]


def rest_call(token, method, path, body=None):
    url = f"{REST_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": BROWSER_UA,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return {"error": json.loads(raw), "http_status": e.code}
        except json.JSONDecodeError:
            return {"error": raw, "http_status": e.code}


def graphql_call(token, query, variables=None):
    # 2026-09 实测确认：Bearer header 认证有效（`{query{myself{id}}}` 能拿到
    # 真实 user id），不需要 `?api_key=` 查询参数兜底。
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": BROWSER_UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return {"error": raw, "http_status": e.code}


def cmd_datacenters(token, args):
    r = graphql_call(token, "query { dataCenters { id name } }")
    print(json.dumps((r.get("data") or {}).get("dataCenters") or r, ensure_ascii=False, indent=2))


def cmd_gputypes(token, args):
    query = """
    query GpuTypes {
      gpuTypes {
        id
        displayName
        memoryInGb
        secureCloud
        communityCloud
        lowestPrice(input: {gpuCount: 1}) {
          uninterruptablePrice
          minimumBidPrice
          stockStatus
        }
      }
    }
    """
    r = graphql_call(token, query)
    types = (r.get("data") or {}).get("gpuTypes") or []
    filtered = [t for t in types if (t.get("memoryInGb") or 0) >= args.min_memory_gb]
    filtered.sort(key=lambda t: (t.get("lowestPrice") or {}).get("uninterruptablePrice") or 9999)
    print(json.dumps(filtered if filtered else r, ensure_ascii=False, indent=2))



def cmd_rent_cheapest(token, args):
    """按"满足最低显存就行、越便宜越好"的策略挑卡并直接建 Pod。

    2026-09-04 起这是**默认的租卡方式**。以前默认奔着 80GB 大卡去，
    实际上两个模型都有低显存配方（见 SKILL.md 第 1 节的显存门槛表），
    多花的钱纯属浪费：A100 80GB 约 $1.59/hr，RTX 5090 32GB 只要 $0.69/hr。

    挑卡逻辑：
      1. 拉全部型号，滤掉显存低于 --min-memory-gb 的
      2. 按价格从低到高排
      3. 从最便宜的开始挨个试着建 Pod，建成就返回

    为什么要"挨个试"而不是只试最便宜那个：`gputypes` 返回的 stockStatus 是
    **全局聚合值**，跟具体数据中心对不上（Network Volume 在哪，Pod 就必须在
    哪）。实测见过 stockStatus=Medium 的型号建不出来、而 Low 的反而成了，
    也见过一个数据中心四种 80GB+ 型号同时缺货、轮询 9 轮才抢到。所以
    --rounds 控制整轮重试次数，别试一次失败就放弃。
    """
    query = """
    query GpuTypes {
      gpuTypes {
        id
        memoryInGb
        lowestPrice(input: {gpuCount: 1}) {
          uninterruptablePrice
          stockStatus
        }
      }
    }
    """
    r = graphql_call(token, query)
    types = (r.get("data") or {}).get("gpuTypes") or []

    def price(t):
        return (t.get("lowestPrice") or {}).get("uninterruptablePrice")

    cands = [t for t in types
             if (t.get("memoryInGb") or 0) >= args.min_memory_gb and price(t) is not None]
    cands.sort(key=price)
    if args.max_price:
        cands = [t for t in cands if price(t) <= args.max_price]
    if not cands:
        sys.exit(f"没有满足 显存≥{args.min_memory_gb}GB"
                 + (f" 且 单价≤${args.max_price}/hr" if args.max_price else "")
                 + " 的型号")

    print(f"候选（按价格从低到高，共 {len(cands)} 个）:")
    for t in cands:
        lp = t.get("lowestPrice") or {}
        print(f"  ${price(t):<6} {t['memoryInGb']:>4}GB  {lp.get('stockStatus')}  {t['id']}")

    if args.dry_run:
        print("\n--dry-run，不实际创建")
        return

    for rnd in range(1, args.rounds + 1):
        for t in cands:
            body = _create_body(args, t["id"])
            resp = rest_call(token, "POST", "/pods", body)
            if "error" not in resp:
                print(f"\n✅ 建成: {resp.get('id')}  ${resp.get('costPerHr')}/hr  "
                      f"{(resp.get('machine') or {}).get('gpuTypeId')}")
                print(json.dumps(resp, ensure_ascii=False, indent=2))
                return
            err = json.dumps(resp.get("error"), ensure_ascii=False).lower()
            # 这几种措辞都是"这个型号在这个数据中心当下拿不到"，不是参数错。
            # 实测见过两种：
            #   "there are no instances currently available"
            #   "could not find any pods with required specifications"
            #      ← 这条通常意味着该型号在 Network Volume 所在的数据中心根本没有
            capacity = ("no instances currently available" in err
                        or "could not find any pods" in err
                        or "no pods available" in err)
            # ⚠️ GraphQL 的 gputypes 会列出 REST 建 Pod 时**不接受**的型号
            #（实测：MIG 切片如 "... MIG 1g.24gb" 不在 REST 的 gpuTypeIds 枚举里）。
            # 这不是参数写错，是这个型号本来就建不了 Pod——跳过继续试下一个。
            not_creatable = ("gputypeids" in err and "schema" in err)
            if not_creatable:
                print(f"  跳过 {t['id']}（REST 建 Pod 不接受这个型号，多半是 MIG 切片）")
                continue
            if not capacity:
                # 真错了（参数/额度/权限），别继续糟蹋下一个型号
                sys.exit(f"创建失败（不是容量问题）: {err}")
        print(f"第 {rnd} 轮所有候选都缺货，{args.retry_interval}s 后重试")
        if rnd < args.rounds:
            time.sleep(args.retry_interval)
    sys.exit(f"{args.rounds} 轮都没抢到。换个数据中心的 Volume，或抬高 --max-price")


def cmd_volume_create(token, args):
    body = {"name": args.name, "size": args.size_gb, "dataCenterId": args.datacenter_id}
    print(json.dumps(rest_call(token, "POST", "/networkvolumes", body=body), ensure_ascii=False, indent=2))


def cmd_volume_list(token, args):
    print(json.dumps(rest_call(token, "GET", "/networkvolumes"), ensure_ascii=False, indent=2))


def cmd_volume_delete(token, args):
    print(json.dumps(rest_call(token, "DELETE", f"/networkvolumes/{args.volume_id}"), ensure_ascii=False, indent=2))


def _create_body(args, gpu_type_id):
    """建 Pod 的请求体。cmd_create 和 cmd_rent_cheapest 共用，避免两处漂移。"""
    body = {
        "name": args.name,
        "imageName": args.image,
        "gpuTypeIds": [gpu_type_id],
        "cloudType": args.cloud_type,
        "containerDiskInGb": args.container_disk_gb,
        "ports": ["22/tcp"],
        "env": {"PUBLIC_KEY": args.public_key},
    }
    if getattr(args, "network_volume_id", None):
        body["networkVolumeId"] = args.network_volume_id
        body["volumeMountPath"] = args.volume_mount_path
    if args.cloud_type == "COMMUNITY":
        body["supportPublicIp"] = True
    return body


def cmd_create(token, args):
    body = _create_body(args, args.gpu_type_id)
    print(json.dumps(rest_call(token, "POST", "/pods", body=body), ensure_ascii=False, indent=2))


def cmd_status(token, args):
    print(json.dumps(rest_call(token, "GET", f"/pods/{args.pod_id}"), ensure_ascii=False, indent=2))


def cmd_snapshot(token, args):
    r = rest_call(token, "GET", f"/pods/{args.pod_id}")
    port_mappings = r.get("portMappings") or {}
    machine = r.get("machine") or {}
    print(json.dumps({
        "desired_status": r.get("desiredStatus"),
        "public_ip": r.get("publicIp"),
        "ssh_port": port_mappings.get("22"),
        "ssh_host": f"root@{r.get('publicIp')}" if r.get("publicIp") else None,
        "cost_per_hr_usd": r.get("costPerHr"),
        "gpu": machine.get("gpuTypeId"),
        "data_center_id": machine.get("dataCenterId"),
    }, ensure_ascii=False, indent=2))


def cmd_stop(token, args):
    print(json.dumps(rest_call(token, "POST", f"/pods/{args.pod_id}/stop"), ensure_ascii=False, indent=2))


def cmd_start(token, args):
    print(json.dumps(rest_call(token, "POST", f"/pods/{args.pod_id}/start"), ensure_ascii=False, indent=2))


def cmd_terminate(token, args):
    print(json.dumps(rest_call(token, "DELETE", f"/pods/{args.pod_id}"), ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("datacenters")
    p.set_defaults(func=cmd_datacenters)

    p = sub.add_parser("gputypes")
    p.add_argument("--min-memory-gb", type=int, default=80)
    p.set_defaults(func=cmd_gputypes)

    p = sub.add_parser("rent_cheapest",
                       help="满足最低显存的前提下挑最便宜的卡并建 Pod（推荐的默认租卡方式）")
    p.add_argument("--min-memory-gb", type=int, required=True,
                   help="这次任务的显存门槛。见 SKILL.md 的显存门槛表："
                        "H3 走 diffusers int8+offload 时 24；H3 不量化单卡时 80；"
                        "LTX-2.5 <217帧 时 80（低显存档未实测）")
    p.add_argument("--max-price", type=float, default=None, help="单价上限 $/hr，超过的不考虑")
    p.add_argument("--rounds", type=int, default=10, help="整轮重试次数，默认 10")
    p.add_argument("--retry-interval", type=int, default=30, help="每轮之间等待秒数，默认 30")
    p.add_argument("--network-volume-id", default=None)
    p.add_argument("--volume-mount-path", default="/workspace")
    p.add_argument("--image", required=True)
    p.add_argument("--name", default="ltx-gpu")
    p.add_argument("--container-disk-gb", type=int, default=50)
    p.add_argument("--cloud-type", choices=["SECURE", "COMMUNITY"], default="SECURE")
    p.add_argument("--public-key", required=True)
    p.add_argument("--dry-run", action="store_true", help="只打印候选列表，不建")
    p.set_defaults(func=cmd_rent_cheapest)

    p = sub.add_parser("volume_create")
    p.add_argument("--name", required=True)
    p.add_argument("--size-gb", type=int, required=True, help="LTX-2.5 权重约 66GB，建议至少给 100GB 留余量")
    p.add_argument("--datacenter-id", required=True, help="例如 EU-RO-1，具体可用值需在创建 Pod 时按报错/控制台核实")
    p.set_defaults(func=cmd_volume_create)

    p = sub.add_parser("volume_list")
    p.set_defaults(func=cmd_volume_list)

    p = sub.add_parser("volume_delete")
    p.add_argument("--volume-id", required=True)
    p.set_defaults(func=cmd_volume_delete)

    p = sub.add_parser("create")
    p.add_argument("--gpu-type-id", required=True, help="从 gputypes 子命令的输出里拿准确 id 字符串")
    p.add_argument("--network-volume-id", default=None, help="留空则不挂载，走纯容器盘（不持久）")
    p.add_argument("--volume-mount-path", default="/workspace")
    p.add_argument("--image", required=True)
    p.add_argument("--name", default="ltx-gpu")
    p.add_argument("--container-disk-gb", type=int, default=50)
    p.add_argument("--cloud-type", choices=["SECURE", "COMMUNITY"], default="SECURE",
                    help="SECURE 默认带公网IP；COMMUNITY 需要 supportPublicIp，本脚本已自动加上")
    p.add_argument("--public-key", required=True, help="SSH 公钥内容，注入 PUBLIC_KEY 环境变量供官方镜像启动脚本写入 authorized_keys")
    p.set_defaults(func=cmd_create)

    for name, fn in [("status", cmd_status), ("snapshot", cmd_snapshot),
                      ("stop", cmd_stop), ("start", cmd_start),
                      ("terminate", cmd_terminate)]:
        p = sub.add_parser(name)
        p.add_argument("--pod-id", required=True)
        p.set_defaults(func=fn)

    args = ap.parse_args()
    token = load_token(args.config)
    args.func(token, args)


if __name__ == "__main__":
    main()
