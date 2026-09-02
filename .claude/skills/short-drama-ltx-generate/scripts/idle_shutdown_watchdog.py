#!/usr/bin/env python3
"""闲置显卡自动停止看门狗：连续 N 秒检测不到生成活动，就调用
`gpu_teardown.py` 停掉实例、停止计费（各平台该 stop 还是 terminate、
以及"停完要确认真的停了"这套逻辑都在那个脚本里，这里不重复实现）。

**它跟"用完就关"是两个不同的东西，两个都要有**：本脚本是被动兜底
（"人忘了关"时超时自救），跑完一批任务后主动收工应该直接跑
`gpu_teardown.py`，或者干脆给 `ltx_ssh_submit.py` 加 `--auto-stop`
让它批量任务一结束就自己关——那样不用干等看门狗的超时时间。

判断"有没有活动"看三件事（任一为真就算活动，重置计时）：
- 远程 GPU 利用率 > 0（`nvidia-smi --query-gpu=utilization.gpu`）
- 远程有生成/环境搭建相关进程在跑（`ltx_pipelines`/`uv sync`/`hf download`/
  `git clone`/`pip install` 等，见 `ACTIVE_PROC_PATTERN`）
- 系统 1 分钟负载明显不是空闲（`/proc/loadavg` 兜底，覆盖上面关键字列表
  没穷举到的情况，比如 natten 的 C++/CUDA 编译进程）

**2026-08 实测教训**：早期版本只看 GPU 利用率 + `ltx_pipelines` 进程，
结果在环境搭建阶段（`uv sync` 装依赖）把正在正经干活的实例误判成闲置、
直接停掉了，白白浪费了已经跑了一半的安装进度。现在的三重判断就是为了
堵上这个漏洞，新增判断条件时优先往「宁可错放过一次真正的闲置，也不要
错杀正在干活的实例」这个方向偏。

用法（vast.ai，默认）:
  python3 idle_shutdown_watchdog.py \\
      --instance-id 49395065 \\
      --ssh-host root@ssh2.vast.ai --ssh-port 35064 \\
      --idle-seconds 120 --check-interval 15

用法（AutoDL，GPU/有卡模式的实例）:
  python3 idle_shutdown_watchdog.py \\
      --instance-id pro-788241abd595 \\
      --ssh-host root@connect.bjb2.seetacloud.com --ssh-port 53213 \\
      --platform autodl --autodl-config .claude/skills/short-drama-ltx-generate/autodl_config.json \\
      --idle-seconds 120 --check-interval 15

用法（RunPod，Pod ID 用 --instance-id 传）:
  python3 idle_shutdown_watchdog.py \\
      --instance-id <pod_id> \\
      --ssh-host root@<公网IP> --ssh-port <映射端口> \\
      --platform runpod --runpod-config .claude/skills/short-drama-ltx-generate/runpod_config.json \\
      --stop-mode terminate \\
      --idle-seconds 120 --check-interval 15
  （权重在 Network Volume 上时推荐带 `--stop-mode terminate`，见下面局限一节）

局限（必须让用户知道，不要含糊过去）：
- 这个看门狗是本地（Claude Code 会话里的一个后台进程）在轮询，**只在当前
  会话/任务存活期间生效**。如果会话被关掉、这个后台任务被杀掉，看门狗
  也会跟着消失，不会再保护后续的计费。不是"设置一次永久生效"的平台级
  开关——vast.ai 本身没有找到原生的"闲置自动停止"功能，所以只能用这种
  外部轮询的方式实现，效果上等同于"只要这个会话还在，就有人盯着"。
- SSH 连不上（实例已经挂了/网络问题）时，直接判定为"检测不到活动"计入
  闲置计时，而不是报错退出——这样即使实例本身已经故障，也能尽快调用停止
  接口，避免继续计费。
- 停止接口调用失败（比如实例本来就已经是 stopped 状态）不算脚本故障，
  `gpu_teardown.py` 会继续查状态、用状态说话；只有连状态都确认不了才会
  用非 0 退出码报警。
- 默认 `--stop-mode stop` 只停机，最保守。**RunPod 上"停机"并不等于
  "不烧钱"**：停止的 Pod 磁盘按官方计费口径仍在收费，而且容器盘本来就
  不跨 stop/start 持久（实测 `uv` 会没了）。模型权重在 Network Volume 上
  时，加 `--stop-mode terminate`（或 `auto` + `--ltx-config`）更省，
  下次挂同一个卷建新 Pod，权重还在。
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def ssh_cmd(ssh_host, ssh_port, remote_cmd, timeout=15):
    cmd = ["ssh", "-p", str(ssh_port), "-o", "ConnectTimeout=8",
           "-o", "StrictHostKeyChecking=accept-new", ssh_host, remote_cmd]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout
    except subprocess.TimeoutExpired:
        return False, ""


# 不只是"生成中"算活动——环境搭建阶段（装依赖、下模型权重、编译 natten
# 等）没有 GPU 占用、也没有 ltx_pipelines 进程，但同样是正经在干活，绝对
# 不能被当成闲置停掉。这里覆盖所有已知的搭建期/生成期进程关键字。
ACTIVE_PROC_PATTERN = (
    "ltx_pipelines|uv sync|uv run|uv pip|hf download|hf auth|"
    "git clone|git-lfs|pip install|pip3 install|apt-get install|"
    "curl.*astral|tar -x"
)


def check_activity(ssh_host, ssh_port):
    """返回 True 表示检测到活动（GPU 在用、有生成/搭建进程、或系统负载明显
    不是空闲），False 表示真的闲置或连不上。"""
    ok, out = ssh_cmd(
        ssh_host, ssh_port,
        "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits; "
        f"echo ---PROC---; ps aux | grep -E '{ACTIVE_PROC_PATTERN}' | grep -v grep; "
        "echo ---LOAD---; cat /proc/loadavg",
    )
    if not ok:
        return False  # 连不上，当作没有活动处理（大概率实例已经挂了）

    gpu_part, _, rest = out.partition("---PROC---")
    proc_part, _, load_part = rest.partition("---LOAD---")

    gpu_util_lines = [l.strip() for l in gpu_part.splitlines() if l.strip()]
    has_gpu_util = any(int(l) > 0 for l in gpu_util_lines if l.isdigit())
    has_proc = proc_part.strip() != ""

    load1 = 0.0
    try:
        load1 = float(load_part.strip().split()[0])
    except (ValueError, IndexError):
        pass
    # 1 分钟负载明显不是空闲机器（阈值放宽，避免 SSH 本身的开销误判），
    # 用来兜底覆盖上面两个关键字列表没覆盖到的搭建期活动（比如 natten 的
    # C++/CUDA 编译，进程名可能是 cc1plus/ninja 这类不好穷举关键字的）。
    has_load = load1 > 0.5

    return has_gpu_util or has_proc or has_load


def stop_instance(args):
    """闲置超时的实际停机动作：全部委托给 gpu_teardown.py。

    这里故意不自己拼各平台的停止命令——`gpu_teardown.py` 已经把"哪个平台该
    用 stop 还是 terminate""调完接口要轮询确认真的停了""确认不了要报警"
    这几件事做完了，看门狗再写一份就会出现两套行为不一致的关机逻辑（尤其是
    RunPod 上 stop 只停 GPU、磁盘还在收费这个差别），那才是真正会漏钱的地方。
    """
    script = str(Path(__file__).resolve().parent / "gpu_teardown.py")
    cmd = ["python3", script, "--platform", args.platform,
           "--instance-id", str(args.instance_id), "--mode", args.stop_mode]
    if args.ltx_config:
        cmd += ["--config", args.ltx_config]
    if args.platform == "autodl" and args.autodl_config:
        cmd += ["--platform-config", args.autodl_config]
    if args.platform == "runpod" and args.runpod_config:
        cmd += ["--platform-config", args.runpod_config]
    if args.platform == "vast" and args.api_key:
        cmd += ["--api-key", args.api_key]
    print(f"[watchdog] 闲置超时，调用 gpu_teardown.py 停止 {args.platform} 实例 {args.instance_id}",
          file=sys.stderr)
    sys.stderr.flush()
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[watchdog] ⚠️ 关机没能确认成功，实例可能还在计费，去平台控制台手动确认",
              file=sys.stderr)
    return result.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--ssh-host", required=True, help="例如 root@ssh2.vast.ai")
    ap.add_argument("--ssh-port", required=True, type=int)
    ap.add_argument("--idle-seconds", type=int, default=120, help="连续闲置多少秒后停止实例，默认120")
    ap.add_argument("--check-interval", type=int, default=15, help="每隔多少秒检查一次，默认15")
    ap.add_argument(
        "--api-key", default=None,
        help="vast.ai API key，透传给 stop 命令；不传就用本机 vastai CLI 已经"
             "存好的 key（~/.config/vastai/vast_api_key）",
    )
    ap.add_argument(
        "--platform", choices=["vast", "autodl", "runpod"], default="vast",
        help="实例所在平台，决定闲置超时后调用哪个停止接口，默认 vast",
    )
    ap.add_argument(
        "--autodl-config", default=None,
        help="platform=autodl 时必填，autodl_config.json 路径（存 api_token）",
    )
    ap.add_argument(
        "--stop-mode", choices=["auto", "stop", "terminate"], default="stop",
        help="闲置超时后做什么，透传给 gpu_teardown.py 的 --mode。默认 stop"
             "（只停机，最保守）。RunPod 上停止的 Pod 磁盘仍在计费、容器盘本来"
             "也不跨 stop/start 持久，如果模型权重在 Network Volume 上，用 "
             "`--stop-mode terminate`（或 auto）才是真的不烧钱，下次挂同一个卷"
             "建新 Pod 权重还在",
    )
    ap.add_argument(
        "--ltx-config", default=None,
        help="可选，ltx_remote_config.json 路径，透传给 gpu_teardown.py 让它能读到"
             "network_volume_id（--stop-mode auto 判断 RunPod 能不能安全 terminate 要用）",
    )
    ap.add_argument(
        "--runpod-config", default=None,
        help="platform=runpod 时必填，runpod_config.json 路径（存 api_key）；"
             "--instance-id 传 pod_id。RunPod 的 stop 只影响 Pod 计费，"
             "挂载的 Network Volume 不受影响，见 references/runpod_gpu_ops.md",
    )
    args = ap.parse_args()
    if args.platform == "autodl" and not args.autodl_config:
        ap.error("--platform autodl 需要同时传 --autodl-config")
    if args.platform == "runpod" and not args.runpod_config:
        ap.error("--platform runpod 需要同时传 --runpod-config")

    last_active = time.time()
    print(
        f"[watchdog] 开始监控 {args.ssh_host}:{args.ssh_port}（实例 {args.instance_id}），"
        f"闲置阈值 {args.idle_seconds}s，检查间隔 {args.check_interval}s",
        file=sys.stderr,
    )

    while True:
        time.sleep(args.check_interval)
        active = check_activity(args.ssh_host, args.ssh_port)
        now = time.time()
        if active:
            last_active = now
            print(f"[watchdog] {time.strftime('%H:%M:%S')} 检测到活动，重置计时", file=sys.stderr)
        else:
            idle_for = now - last_active
            print(
                f"[watchdog] {time.strftime('%H:%M:%S')} 无活动，已闲置 {idle_for:.0f}s",
                file=sys.stderr,
            )
            if idle_for >= args.idle_seconds:
                stop_instance(args)
                print("[watchdog] 停机流程已执行完（结果见上面 gpu_teardown 的输出），看门狗退出",
                      file=sys.stderr)
                return


if __name__ == "__main__":
    main()
