#!/usr/bin/env python3
"""AutoDL 容器实例 Pro API 的轻量封装：创建/查状态/查连接信息/开机(GPU)/关机/释放。

跟 vast.ai 那边用 `vastai` CLI 不一样，AutoDL 开放平台没有官方 CLI，这里直接
包一层 HTTP 调用。踩过的坑、GPU 选型建议见 references/autodl_gpu_ops.md。

**无卡模式（省钱模式，¥0.1/小时）目前只能在网页控制台手动开机，开放平台 API
明确不支持**（power_on 的 payload 官方文档只认 "gpu" 一个值：
"gpu：有卡开机, 暂不支持API以无卡模式开机"，本脚本因此不提供无卡开机）。
`power_on` 子命令只能开有卡（GPU）模式。

Token 从 autodl_config.json 读（同目录，已加入 .gitignore），可以用
`--config` 指定别的路径。instance_uuid 大多数子命令需要显式传
`--instance-uuid`（一个账号下可能同时有 CPU 用途和 GPU 用途的多台实例，
不假设只有一台）。

用法：
  python3 autodl_ops.py create --gpu-spec pro6000-p --image base-image-mbr2n4urrc \\
      --cuda-v-from 113 --region beijingDC2 --name ltx-gpu [--disk-gb 0]
  python3 autodl_ops.py list
  python3 autodl_ops.py status --instance-uuid pro-xxxx
  python3 autodl_ops.py snapshot --instance-uuid pro-xxxx   # 打印价格+SSH信息
  python3 autodl_ops.py power_on --instance-uuid pro-xxxx   # 只支持有卡(GPU)模式
  python3 autodl_ops.py power_off --instance-uuid pro-xxxx
  python3 autodl_ops.py release --instance-uuid pro-xxxx    # 先确认已关机，不可逆
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "autodl_config.json"


def load_token(config_path):
    return json.loads(Path(config_path).read_text())["api_token"]


def call(token, method, path, params=None, body=None):
    url = f"https://api.autodl.com{path}"
    if method == "GET" and params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": token, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def cmd_create(token, args):
    body = {
        "req_gpu_amount": 1,
        "gpu_spec_uuid": args.gpu_spec,
        "image_uuid": args.image,
        "cuda_v_from": args.cuda_v_from,
        "expand_system_disk_by_gb": args.disk_gb,
        "data_center_list": [args.region],
        "instance_name": args.name,
    }
    print(json.dumps(call(token, "POST", "/api/v1/dev/instance/pro/create", body=body), ensure_ascii=False))


def cmd_list(token, args):
    body = {"page_index": 1, "page_size": 50}
    print(json.dumps(call(token, "POST", "/api/v1/dev/instance/pro/list", body=body), ensure_ascii=False))


def cmd_status(token, args):
    print(json.dumps(call(token, "GET", "/api/v1/dev/instance/pro/status", {"instance_uuid": args.instance_uuid}), ensure_ascii=False))


def cmd_snapshot(token, args):
    r = call(token, "GET", "/api/v1/dev/instance/pro/snapshot", {"instance_uuid": args.instance_uuid})
    data = r.get("data") or {}
    print(json.dumps({
        "ssh_command": data.get("ssh_command"),
        "proxy_host": data.get("proxy_host"),
        "ssh_port": data.get("ssh_port"),
        "root_password": data.get("root_password"),
        "gpu": data.get("snapshot_gpu_alias_name"),
        "region": data.get("region_sign"),
        # 价格字段单位是"厘"（0.001元），除以1000才是元/小时
        "price_yuan_per_hour": (data.get("payg_price") or 0) / 1000,
        "origin_price_yuan_per_hour": (data.get("origin_pay_price") or 0) / 1000,
    }, ensure_ascii=False, indent=2))


def cmd_power_on(token, args):
    body = {"instance_uuid": args.instance_uuid, "payload": "gpu"}
    print(json.dumps(call(token, "POST", "/api/v1/dev/instance/pro/power_on", body=body), ensure_ascii=False))


def cmd_power_off(token, args):
    print(json.dumps(call(token, "POST", "/api/v1/dev/instance/pro/power_off", body={"instance_uuid": args.instance_uuid}), ensure_ascii=False))


def cmd_release(token, args):
    print(json.dumps(call(token, "POST", "/api/v1/dev/instance/pro/release", body={"instance_uuid": args.instance_uuid}), ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create")
    p.add_argument("--gpu-spec", required=True, help="例如 pro6000-p / h800 / v-48g / 4090D")
    p.add_argument("--image", required=True, help="镜像UUID，例如 base-image-mbr2n4urrc")
    p.add_argument("--cuda-v-from", required=True, type=int, help="例如 102 表示 cuda>=10.2，113 表示 cuda>=11.3")
    p.add_argument("--region", default="beijingDC2")
    p.add_argument("--name", default="ltx-gpu")
    p.add_argument("--disk-gb", type=int, default=0)
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("list")
    p.set_defaults(func=cmd_list)

    for name, fn in [("status", cmd_status), ("snapshot", cmd_snapshot),
                      ("power_on", cmd_power_on), ("power_off", cmd_power_off),
                      ("release", cmd_release)]:
        p = sub.add_parser(name)
        p.add_argument("--instance-uuid", required=True)
        p.set_defaults(func=fn)

    args = ap.parse_args()
    token = load_token(args.config)
    args.func(token, args)


if __name__ == "__main__":
    main()
