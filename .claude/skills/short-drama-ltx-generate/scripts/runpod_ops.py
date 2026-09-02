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


def cmd_volume_create(token, args):
    body = {"name": args.name, "size": args.size_gb, "dataCenterId": args.datacenter_id}
    print(json.dumps(rest_call(token, "POST", "/networkvolumes", body=body), ensure_ascii=False, indent=2))


def cmd_volume_list(token, args):
    print(json.dumps(rest_call(token, "GET", "/networkvolumes"), ensure_ascii=False, indent=2))


def cmd_volume_delete(token, args):
    print(json.dumps(rest_call(token, "DELETE", f"/networkvolumes/{args.volume_id}"), ensure_ascii=False, indent=2))


def cmd_create(token, args):
    body = {
        "name": args.name,
        "imageName": args.image,
        "gpuTypeIds": [args.gpu_type_id],
        "cloudType": args.cloud_type,
        "containerDiskInGb": args.container_disk_gb,
        "ports": ["22/tcp"],
        "env": {"PUBLIC_KEY": args.public_key},
    }
    if args.network_volume_id:
        body["networkVolumeId"] = args.network_volume_id
        body["volumeMountPath"] = args.volume_mount_path
    if args.cloud_type == "COMMUNITY":
        body["supportPublicIp"] = True
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
