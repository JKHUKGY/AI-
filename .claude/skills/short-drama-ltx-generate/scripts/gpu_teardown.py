#!/usr/bin/env python3
"""用完就关：一条命令把这次生成用的显卡实例真正停掉计费，并**确认停成功了**。

跟 `idle_shutdown_watchdog.py` 的分工（两个都要用，不是二选一）：
- 看门狗是"我忘了关"的兜底：连续 N 秒检测不到活动才动手，属于被动保险。
- 本脚本是"我现在确认用完了"的主动收尾：立刻停，并且轮询平台接口确认状态
  真的变了。批量生成跑完后应该跑这一步，不要指望看门狗慢慢等超时——
  等待的那几分钟也是真金白银，而且看门狗只在当前会话存活期间有效。

**为什么必须"确认"而不是调一下停止接口就完事**：本仓库踩过的坑是
"以为停了其实没停"——接口返回 200 不等于实例真的进了 stopped/exited 状态
（vast.ai 上排队/异常状态的实例尤其会这样）。所以这里调完停止接口会轮询
状态直到确认，确认不了就用非 0 退出码 + 大字警告收场，让人去控制台补一刀，
而不是打印一句"已停止"就让用户以为安全了。

## 用法

最省事的一种（平台/实例 ID 直接从 ltx_remote_config.json 的
`platform`/`instance_id` 字段读）：
```bash
python3 gpu_teardown.py --config output/<故事名>/videos/ep0X/ltx_remote_config.json
```

手动指定：
```bash
python3 gpu_teardown.py --platform runpod   --instance-id <pod_id>      [--mode stop|terminate]
python3 gpu_teardown.py --platform vast     --instance-id <实例ID>
python3 gpu_teardown.py --platform autodl   --instance-id <实例UUID>
```
加 `--dry-run` 只打印将要执行的动作，不真的调接口。

## `--mode auto`（默认）在各平台上的选择，以及为什么

- **RunPod → `terminate`**。RunPod 的 `stop` 只停 GPU 计费，Pod 本体还在，
  **磁盘（容器盘）按官方计费口径仍然在收费**（本仓库没有逐条核对过账单
  数字，但"停止的 Pod 仍收存储费"这一点是官方计费说明写明的），而且容器盘
  在 `stop`→`start` 之间本来就不持久（实测：`uv` 会没了），留着它没什么
  好处。真正要保住的是 Network Volume 上的 67GB 模型权重，而**实测确认
  `terminate` Pod 完全不影响 Network Volume**（见
  `references/runpod_gpu_ops.md` 第 6 条），下次挂同一个
  `network_volume_id` 建新 Pod，权重还在。所以 RunPod 上"用完就关"的正确
  动作是 terminate，这也是这个渠道相比另外两家的核心优势。
  **例外**：config 里没有 `network_volume_id`（说明权重下在容器盘/本地盘
  上，一 terminate 就白下载了）时，auto 会降级成 `stop` 并打印警告，
  不会替用户把 67GB 权重删掉。
- **vast.ai → `stop`**、**AutoDL → `power_off`**。这两家的销毁动作
  （`vastai destroy instance` / AutoDL `release`）会连盘上的数据一起删，
  模型权重就在那块盘上，所以"用完就关"在这两家只能是停机，不能是销毁。
  真要销毁得用户明确说"这台不要了"，本脚本**不提供**销毁入口
  （`volume_delete`/`release`/`destroy` 都不在这里，故意的）。

顺带做的一件事：停成功后会 `pkill` 掉本机盯着这个实例的
`idle_shutdown_watchdog.py` 进程——实例都没了，留着看门狗只会每 15 秒
SSH 超时刷日志。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def run(cmd, timeout=120):
    """跑一条命令，返回 (ok, stdout, stderr)。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"命令超时: {' '.join(str(c) for c in cmd)}"
    except FileNotFoundError as e:
        return False, "", str(e)


def _json_or_none(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------- RunPod


def runpod_ops(config, *sub):
    return ["python3", str(SCRIPT_DIR / "runpod_ops.py"), "--config", str(config), *sub]


def runpod_stop(instance_id, config, mode):
    verb = "terminate" if mode == "terminate" else "stop"
    ok, out, err = run(runpod_ops(config, verb, "--pod-id", instance_id))
    print(f"[teardown] runpod {verb} 返回: {out.strip() or err.strip()}")
    return ok


def runpod_check_stopped(instance_id, config, mode):
    """RunPod：terminate 成功后 GET pod 会 404；stop 成功后 desiredStatus=EXITED。"""
    ok, out, _ = run(runpod_ops(config, "status", "--pod-id", instance_id))
    if not ok:
        return False, "status 查询失败"
    data = _json_or_none(out) or {}
    if mode == "terminate":
        http_status = data.get("http_status")
        gone = http_status == 404 or "not found" in json.dumps(data).lower()
        return gone, f"http_status={http_status}"
    status = data.get("desiredStatus")
    return status in ("EXITED", "STOPPED", "TERMINATED"), f"desiredStatus={status}"


# ---------------------------------------------------------------- vast.ai


def vast_stop(instance_id, api_key, mode):
    if mode == "terminate":
        print(
            "[teardown] 拒绝在 vast.ai 上执行 terminate：vast.ai 的销毁会连盘上的"
            "模型权重一起删，本脚本只做停机。真要销毁请用户自己确认后手动跑 "
            f"`vastai destroy instance {instance_id} -y`。",
            file=sys.stderr,
        )
        return False
    cmd = ["vastai", "stop", "instance", str(instance_id), "--raw"]
    if api_key:
        cmd += ["--api-key", api_key]
    ok, out, err = run(cmd)
    print(f"[teardown] vast stop 返回: {out.strip() or err.strip()}")
    return ok


def vast_check_stopped(instance_id, api_key, mode):
    """vast.ai：轮询 `show instance` 直到 actual_status/cur_state 确认停了。

    两个实测过的输出形状都要认：`--raw` 有时直接给实例本身的字段，有时包一层
    `{"instances": ...}`（查不到的实例返回 `{"instances": null}`，**退出码
    仍然是 0**）。查不到时故意**不**当成"已停止"——"实例已被销毁"和"实例ID
    写错了/API 抽风"这两种情况在输出上分不开，后者要是被当成停成功了，那台
    真正在跑的实例就会一直计费到有人发现，正是这个脚本要防的事。
    """
    cmd = ["vastai", "show", "instance", str(instance_id), "--raw"]
    if api_key:
        cmd += ["--api-key", api_key]
    ok, out, _ = run(cmd)
    if not ok:
        return False, "show instance 查询失败"
    data = _json_or_none(out)
    if not isinstance(data, dict):
        return False, f"show instance 输出不是预期的 JSON 对象: {out.strip()[:200]}"

    inst = data if "actual_status" in data or "cur_state" in data else data.get("instances")
    if isinstance(inst, list):
        inst = inst[0] if inst else None
    if not isinstance(inst, dict):
        return False, (
            f"vast.ai 查不到实例 {instance_id}（可能已被销毁，也可能实例ID写错/"
            f"接口抽风，这里分不出来）——请人工到控制台确认，不当成已停止"
        )

    actual = inst.get("actual_status")
    cur = inst.get("cur_state")
    stopped = actual in ("exited", "stopped") or cur in ("stopped", "exited")
    return stopped, f"actual_status={actual} cur_state={cur}"


# ---------------------------------------------------------------- AutoDL


def autodl_ops(config, *sub):
    return ["python3", str(SCRIPT_DIR / "autodl_ops.py"), "--config", str(config), *sub]


def autodl_stop(instance_id, config, mode):
    if mode == "terminate":
        print(
            "[teardown] 拒绝在 AutoDL 上执行 release（销毁）：会连盘上的模型权重"
            "一起删，本脚本只做 power_off。真要销毁请用户明确确认后手动跑 "
            f"`autodl_ops.py release --instance-uuid {instance_id}`。",
            file=sys.stderr,
        )
        return False
    ok, out, err = run(autodl_ops(config, "power_off", "--instance-uuid", instance_id))
    print(f"[teardown] autodl power_off 返回: {out.strip() or err.strip()}")
    return ok


def autodl_check_stopped(instance_id, config, mode):
    """AutoDL：status 里出现 shutdown/stopped 才算停了。

    这里是在整个响应体上做子串匹配，不是读某个确定字段——AutoDL 开放平台的
    status 响应结构本仓库还没完整摸清（见 references/autodl_gpu_ops.md），
    等哪次真的在 AutoDL 上用这个脚本关过机、拿到真实响应，再改成读准确字段。
    宁可偏保守：匹配不上就是"确认不了"，会走报警分支让人去控制台看一眼。
    """
    ok, out, _ = run(autodl_ops(config, "status", "--instance-uuid", instance_id))
    if not ok:
        return False, "status 查询失败"
    blob = json.dumps(_json_or_none(out) or out).lower()
    return ("shutdown" in blob or "stopped" in blob), out.strip()[:200]


# ---------------------------------------------------------------- 通用流程


def resolve_mode(platform, mode, cfg):
    """把 --mode auto 展开成这个平台上真正该用的动作。"""
    if mode != "auto":
        return mode, f"用户显式指定 --mode {mode}"
    if platform == "runpod":
        if cfg.get("network_volume_id"):
            return "terminate", (
                f"RunPod + 有 Network Volume（{cfg['network_volume_id']}），terminate "
                "不影响卷上的模型权重，且能连磁盘费一起省掉"
            )
        return "stop", (
            "RunPod 但 config 里没有 network_volume_id——模型权重可能在容器盘上，"
            "terminate 会白删 67GB 权重，降级为 stop（注意停止的 Pod 仍按磁盘计费）"
        )
    return "stop", f"{platform} 的销毁动作会连模型权重一起删，只做停机"


def _ancestor_pids():
    """本进程 + 所有祖先进程的 pid。

    看门狗超时后是**由它自己**调起本脚本的，而它的命令行里就带着这个
    instance_id——早期版本直接 `pkill -f` 会把调用方（看门狗自己，甚至整条
    进程链）连带杀掉，结果关机确认的日志还没打完进程就没了，看上去像"关机
    脚本崩了"。所以杀之前先把自己的祖先排除掉。
    """
    pids, pid = set(), os.getpid()
    for _ in range(20):
        pids.add(pid)
        try:
            # /proc/<pid>/stat 的第 4 个字段是 ppid，但进程名字段可能带空格和
            # 括号，所以从最后一个 ')' 之后开始切。
            stat = Path(f"/proc/{pid}/stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            break
        if ppid <= 1:
            break
        pid = ppid
    return pids


def kill_local_watchdog(instance_id):
    pattern = f"idle_shutdown_watchdog.py.*{instance_id}"
    ok, out, _ = run(["pgrep", "-f", pattern], timeout=20)
    if not ok:
        return
    skip = _ancestor_pids()
    targets = [t for t in out.split() if t.isdigit() and int(t) not in skip]
    if not targets:
        return
    run(["kill"] + targets, timeout=20)
    print(f"[teardown] 已顺带杀掉本机盯着 {instance_id} 的闲置看门狗进程: {', '.join(targets)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None,
                    help="ltx_remote_config.json 路径，从里面的 platform/instance_id/"
                         "network_volume_id 字段自动读，省得手敲")
    ap.add_argument("--platform", choices=["vast", "autodl", "runpod"], default=None,
                    help="不传就从 --config 的 platform 字段读")
    ap.add_argument("--instance-id", default=None,
                    help="vast 的实例ID / AutoDL 的实例UUID / RunPod 的 pod_id；"
                         "不传就从 --config 的 instance_id 字段读")
    ap.add_argument("--mode", choices=["auto", "stop", "terminate"], default="auto",
                    help="auto（默认）= RunPod 上 terminate（Network Volume 保住权重、"
                         "顺带省掉停止 Pod 的磁盘费），vast/AutoDL 上停机；"
                         "terminate 在 vast/AutoDL 上会被拒绝，那两家销毁会丢模型权重")
    ap.add_argument("--platform-config", default=None,
                    help="runpod_config.json / autodl_config.json 路径，"
                         "默认用 skill 目录下的同名文件")
    ap.add_argument("--api-key", default=None, help="vast.ai API key，不传就用本机 vastai CLI 存的")
    ap.add_argument("--verify-timeout", type=int, default=180,
                    help="调完停止接口后，最多轮询多少秒确认状态真的变了，默认180")
    ap.add_argument("--verify-interval", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true", help="只打印将要做什么，不调接口")
    args = ap.parse_args()

    cfg = {}
    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))

    platform = args.platform or cfg.get("platform")
    instance_id = args.instance_id or cfg.get("instance_id")
    if not platform:
        sys.exit("要么传 --platform，要么让 --config 指向带 platform 字段的 ltx_remote_config.json")
    if not instance_id:
        sys.exit("要么传 --instance-id，要么让 --config 指向带 instance_id 字段的 ltx_remote_config.json")

    platform_config = args.platform_config or (
        SKILL_DIR / "runpod_config.json" if platform == "runpod" else
        SKILL_DIR / "autodl_config.json" if platform == "autodl" else None
    )

    mode, why = resolve_mode(platform, args.mode, cfg)
    print(f"[teardown] 平台={platform} 实例={instance_id} 动作={mode}")
    print(f"[teardown] 理由: {why}")

    if args.dry_run:
        print("[teardown] --dry-run，不实际调用停止接口")
        return

    if platform == "runpod":
        stop_ok = runpod_stop(instance_id, platform_config, mode)
        check = lambda: runpod_check_stopped(instance_id, platform_config, mode)
    elif platform == "autodl":
        stop_ok = autodl_stop(instance_id, platform_config, mode)
        check = lambda: autodl_check_stopped(instance_id, platform_config, mode)
    else:
        stop_ok = vast_stop(instance_id, args.api_key, mode)
        check = lambda: vast_check_stopped(instance_id, args.api_key, mode)

    # 停止接口返回失败不代表实例还在跑（常见情况：本来就已经是 stopped，
    # 平台直接报错），所以不管返回什么都往下走确认状态，用状态说话。
    if not stop_ok:
        print("[teardown] 停止接口返回非成功，继续查状态确认实例到底停了没有", file=sys.stderr)

    deadline = time.time() + args.verify_timeout
    confirmed, detail = check()
    while not confirmed and time.time() < deadline:
        print(f"[teardown] 还没确认停止（{detail}），{args.verify_interval}s 后重查")
        time.sleep(args.verify_interval)
        confirmed, detail = check()

    if confirmed:
        print(f"[teardown] ✅ 已确认停止计费（{detail}）")
        kill_local_watchdog(instance_id)
        if platform == "runpod" and mode == "stop":
            print("[teardown] 提醒：RunPod 上 stop 只停 GPU，Pod 的磁盘按官方计费口径"
                  "仍在收费；如果模型权重在 Network Volume 上，用 --mode terminate "
                  "才是真的不烧钱。")
        if platform == "runpod" and mode == "terminate" and cfg.get("network_volume_id"):
            print(f"[teardown] Network Volume {cfg['network_volume_id']} 未被触碰，"
                  "下次挂同一个卷建新 Pod 即可，不用重新下载权重。")
        return

    print(
        f"\n[teardown] ⚠️⚠️ 没能确认实例已停止（最后状态: {detail}）。"
        f"\n[teardown] 这意味着可能**还在计费**，不要当成已经关掉了。"
        f"\n[teardown] 请立刻去 {platform} 控制台手动确认实例 {instance_id} 的状态。",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
