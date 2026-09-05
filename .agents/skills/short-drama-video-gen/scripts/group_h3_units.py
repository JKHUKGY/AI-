#!/usr/bin/env python3
"""镜头卡 → H3 生成单元（把短镜头合并成多镜头单元）。

**这是 H3 专属的一步，LTX 不需要。**

为什么要有这一步：我们的镜头卡是按 LTX 的粒度拆的——LTX 一次生成 = 一个镜头，
所以 2-3 秒的短镜头很常见。但 H3 的时长窗口是 **4-15 秒**，那些短单元
一条都提交不了。

H3 的解法不是"把短镜头拉长"，而是**一次生成里放多个镜头**——官方格式支持：

    [Shot 1] ...
    [Shot 2] At 00:03.042, the camera cuts to ...

这是 LTX 完全没有的能力（LTX 一次只能生成一个连续镜头）。所以把连续的短镜头
按剧情顺序打包成一个 4-15 秒的生成单元，既解决了时长下限，又**顺带让 H3 自己
处理剪辑点**——它是带音频的，切镜时的声音连续性由它自己保证。

同时这一步会把 LTX 时代的**拆段单元（u1/u2）合回去**：那种拆分是为了
迁就 LTX 的时长/稳定性，在 H3 这边没有必要，而且 u2 没有独立首帧
（`first_frame_from` 指向 u1 的尾帧），合并之后这个依赖直接消失。

用法:
    python3 group_h3_units.py <shot_cards.json> -o <h3_units.json>
    python3 group_h3_units.py <shot_cards.json> --plan     # 只打印分组方案

分组规则（保守，宁可少合不可乱合）：
  1. 同一镜头的 u1/u2/... 永远先合回一个镜头
  2. 只合并**相邻**镜头，不跨场景（`scene` 变了就断开）
  3. 累计时长 ≥ --min-duration 就收口，不再往里加
  4. 单个单元不超过 --max-duration
  5. 已经 ≥ 下限的镜头优先**单独成一个单元**，不为了凑数破坏原本合理的镜头
  6. 但**夹在长镜之间的孤立短镜**（比如 2 秒的手部特写夹在两个 6 秒对话镜中间）
     会被就近吸收进相邻单元——否则它永远凑不够 4 秒、只能被丢掉
"""
import argparse
import json
import re
import sys
from pathlib import Path

H3_FPS = 24
FRAME_BASE, FRAME_OFFSET = 17, 5


def snap(sec):
    want = int(round(sec * H3_FPS))
    n = max(0, -(-(want - FRAME_OFFSET) // FRAME_BASE))
    return (FRAME_BASE * n + FRAME_OFFSET) / H3_FPS


def base_id(sid):
    return re.sub(r"_u\d+$", "", sid)


def merge_split_units(cards):
    """把 u1/u2/... 合回一个镜头：拼接 beats，时长相加，首帧用 u1 的。"""
    out, buf = [], {}
    order = []
    for c in cards:
        b = base_id(c["id"])
        if b not in buf:
            buf[b] = []
            order.append(b)
        buf[b].append(c)
    for b in order:
        group = sorted(buf[b], key=lambda x: x["id"])
        if len(group) == 1:
            out.append(group[0])
            continue
        head = json.loads(json.dumps(group[0]))   # 深拷贝
        head["id"] = b
        head["duration_sec"] = round(sum(float(g["duration_sec"]) for g in group), 4)
        beats, t = [], 0.0
        for g in group:
            for bt in g.get("beats") or []:
                span = float(bt["t"][1]) - float(bt["t"][0])
                nb = json.loads(json.dumps(bt))
                nb["t"] = [round(t, 4), round(t + span, 4)]
                beats.append(nb)
                t += span
        head["beats"] = beats
        head["notes"] = ((head.get("notes") or "") +
                         f"（H3 单元：由 {'/'.join(g['id'] for g in group)} 合并，"
                         f"LTX 时代的拆段在 H3 上没必要）").strip()
        head.pop("first_frame_from", None)
        out.append(head)
    return out


def group_units(cards, min_dur, max_dur):
    units, cur = [], []

    def flush():
        if not cur:
            return
        tot = sum(float(c["duration_sec"]) for c in cur)
        head = cur[0]
        u = {
            "id": head["id"] if len(cur) == 1 else f"{head['id']}+{len(cur)-1}",
            "members": [c["id"] for c in cur],
            "scene": head.get("scene"),
            "duration_sec": round(tot, 4),
            "shots": cur[:],
        }
        # 把装配器要用的单元级字段从**第一个镜头**提上来。
        # 关键帧/风格/主体锁定/seed 都按第一镜走：多镜头单元里第一镜决定
        # 开场构图，后面的镜头由 [Shot N] 的切点描述接管。
        for k in ("first_frame", "first_frame_from", "style_tail_en",
                  "subject_lock_en", "summary_en", "references",
                  "seed", "width", "height", "aspect_ratio", "tier",
                  "scene_plate", "intent_zh", "notes"):
            if head.get(k) is not None:
                u[k] = head[k]
        units.append(u)
        cur.clear()

    for c in cards:
        dur = float(c["duration_sec"])
        if snap(dur) >= min_dur:
            flush()                 # 够长的自己单独成一个单元
            cur.append(c)
            flush()
            continue
        if cur and cur[0].get("scene") != c.get("scene"):
            flush()                 # 不跨场景合并
        cur.append(c)
        if snap(sum(float(x["duration_sec"]) for x in cur)) >= min_dur:
            flush()
    flush()

    # ---- 后处理：吸收孤儿短单元
    # 上面的贪心是"顺序累加"，所以夹在两个长镜之间的短镜会落单
    # （镜05 够长→单独成单元，镜06 只有 2 秒但后面的镜07 也够长→镜06 孤立）。
    # 这里把这种孤儿并进相邻单元：优先并前一个（保持剧情顺序读起来自然），
    # 前一个放不下或跨场景就试后一个。
    changed = True
    while changed:
        changed = False
        for i, u in enumerate(units):
            if snap(u["duration_sec"]) >= min_dur:
                continue
            for j in (i - 1, i + 1):          # 先前后
                if not (0 <= j < len(units)):
                    continue
                nb = units[j]
                if nb.get("scene") != u.get("scene"):
                    continue
                tot = u["duration_sec"] + nb["duration_sec"]
                if snap(tot) > max_dur:
                    continue
                merged_shots = (nb["shots"] + u["shots"]) if j < i else (u["shots"] + nb["shots"])
                nb["shots"] = merged_shots
                nb["members"] = [c["id"] for c in merged_shots]
                nb["duration_sec"] = round(tot, 4)
                nb["id"] = f"{merged_shots[0]['id']}+{len(merged_shots)-1}"
                for k in ("first_frame", "style_tail_en", "subject_lock_en",
                          "summary_en", "references", "seed", "width", "height",
                          "aspect_ratio", "tier", "scene_plate", "intent_zh"):
                    if merged_shots[0].get(k) is not None:
                        nb[k] = merged_shots[0][k]
                units.pop(i)
                changed = True
                break
            if changed:
                break
    return units


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cards")
    ap.add_argument("-o", "--out")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--min-duration", type=float, default=4.0)
    ap.add_argument("--max-duration", type=float, default=15.0)
    args = ap.parse_args()

    cards = json.loads(Path(args.cards).read_text(encoding="utf-8"))
    merged = merge_split_units(cards)
    units = group_units(merged, args.min_duration, args.max_duration)

    ok = [u for u in units if args.min_duration <= snap(u["duration_sec"]) <= args.max_duration]
    short = [u for u in units if snap(u["duration_sec"]) < args.min_duration]
    long_ = [u for u in units if snap(u["duration_sec"]) > args.max_duration]

    print(f"{len(cards)} 个 LTX 单元 → 合并拆段后 {len(merged)} 镜 → 打包成 {len(units)} 个 H3 单元")
    print(f"  合格 {len(ok)} | 仍太短 {len(short)} | 太长 {len(long_)}")
    if args.plan or short or long_:
        print()
        for u in units:
            sn = snap(u["duration_sec"])
            flag = "✅" if args.min_duration <= sn <= args.max_duration else "⚠️"
            multi = f"  ← {len(u['members'])} 镜合一" if len(u["members"]) > 1 else ""
            print(f"  {flag} {u['id']:<22} {u['duration_sec']:6.2f}s→{sn:6.3f}s  "
                  f"{u['scene']}  {'/'.join(u['members'])}{multi}")

    if args.out and not args.plan:
        Path(args.out).write_text(
            json.dumps(units, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写出 {len(units)} 个单元 → {args.out}")
    sys.exit(1 if (short or long_) else 0)


if __name__ == "__main__":
    main()
