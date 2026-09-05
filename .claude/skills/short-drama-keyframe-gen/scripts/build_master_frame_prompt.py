#!/usr/bin/env python3
"""场次节拍 → 场次主帧的出图提示词 / jobs.json（提示词是派生产物，不手写）。

## 这一步存在的理由

在它之前，每一张关键帧都是从 **空场景底板 + 角色三视图** 合成的——也就是说
**每一镜都在重新把人搬进空房间一次**。于是：

- 一场戏九镜，画面里那张沙发出现了五次，其中三次是空的，因为那三张卡没写
  沙发上坐着人（《出狱后》v2 ep01 `镜25` 实拍）。
- 同一只行李箱在镜30 变成了棕色旧皮箱，因为那张卡没重抄一遍它的外观。
- 同一批"虚焦的两个女性身影"出成了一男一女，因为那句话写在 `props_zh` 里，
  是一句没有任何约束的散文。

主帧把这一层补上：**每个「场次 × 叙事节拍」先出一张图，把这个房间此刻的
真实状态一次性定死**——在场的每个人站在哪、穿什么、手里拿着什么、光从哪来、
东西摆在哪。然后这一场的每一镜都以这张主帧为参考图1，而不是回到空房间。

## 为什么这不是「拿上一镜当下一镜的种子」

`研究.md` §2.7 引的那条业界纪律（never let one shot seed the next）禁的是
**链式**：A 生 B、B 生 C，三镜之后就是另一个人，漂移会累积。

主帧是**星形**：一场戏所有镜头都回到同一张主帧，和"所有镜头都回到同一份
三视图"是完全相同的拓扑，漂移不累积。三视图锁的是"这个人长什么样"，
主帧锁的是"此刻这个房间是什么样"——**后者正是现在唯一缺的那一层锚点**。

## 用法

```bash
# 校验 + 打印装配结果
python3 build_master_frame_prompt.py \
    output/<故事名>/keyframes/ep0X/keyframe_cards.json --lint

# 写出 jobs（喂给 short-drama-image-gen 的 generate_images.py）
python3 build_master_frame_prompt.py \
    output/<故事名>/keyframes/ep0X/keyframe_cards.json \
    -o output/<故事名>/keyframes/ep0X/jobs_master_ep0X.json
```

出完图之后，把选中的那张回填进对应节拍的 `master_frame` 字段，再跑
`build_keyframe_prompt.py`——它会自动改用主帧当参考图1。**回填之前
`build_keyframe_prompt.py` 会因为 `master_frame` 指向的文件不存在而报错，
这是故意的**（和镜头卡回填 `first_frame_state_zh` 是同一道闸门）。

约定从仓库根目录运行。退出码非 0 表示有必须处理的 ERROR。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_keyframe_prompt import (  # noqa: E402
    AVOID_FIXED, AVOID_WITH_PEOPLE, BODY_DIR, CAMERA_RELATION, COMPAT,
    DEFAULT_COUNT, DEPTH, FACE_TURNED, GAZE_FIXED, POS_X, QUALITY_SPELL_WORDS,
    REF_COUNT_HARD_MAX, gaze_label, negation_hits_blocking, resolve,
)

# 主帧是"这个房间此刻的总览"，天然是全景/定场，所以它不吃景别那一套校验。
# 但它必须看得见每一个在场的人——这是它唯一的硬要求。
MASTER_REQUIRED = ["id", "scene", "present", "master_plate_id",
                   "master_plate_image", "master_plate_read_zh",
                   "style_anchor_zh", "camera_zh", "blocking"]
BLOCKING_REQUIRED = ["name", "ref_images", "pos_x", "depth", "body_dir",
                     "camera_relation", "posture_zh"]

# 主帧的参考图会比单镜多（在场的人全都要给基准图），所以软上限放宽到接口上限
REF_COUNT_SOFT_MAX_MASTER = 9


def render_blocking(p, names):
    parts = [
        f"位于{POS_X.get(p.get('pos_x'), p.get('pos_x'))}、"
        f"{DEPTH.get(p.get('depth'), p.get('depth'))}",
        f"{BODY_DIR.get(p.get('body_dir'), p.get('body_dir'))}，"
        f"{CAMERA_RELATION.get(p.get('camera_relation'), p.get('camera_relation'))}",
    ]
    if p.get("gaze_at"):
        parts.append(gaze_label(p.get("gaze_at"), names))
    for key in ("posture_zh", "holding_zh", "contact_zh"):
        v = (p.get(key) or "").strip()
        if v:
            parts.append(v.rstrip("。"))
    return f"{p.get('name')}：" + "；".join(parts) + "。"


def ref_images_of_beat(beat):
    refs = [beat.get("master_plate_image")] if beat.get("master_plate_image") else []
    for p in beat.get("blocking") or []:
        refs += list(p.get("ref_images") or [])
    return refs


def build_master_prompt(beat):
    """场次节拍 → 主帧提示词。纯函数。

    块序：画风 → 参考图 → 房间状态 → 全员走位 → 光线 → 合成要求 → 避免。
    没有【景别与裁切】那一块——主帧固定是这个机位的完整取景（全景/定场），
    它的职责是"把这个房间此刻的全貌一次拍全"，裁切是下游每一镜自己的事。
    """
    blocking = beat.get("blocking") or []
    names = {p.get("name") for p in blocking}
    blocks = []

    style = (beat.get("style_anchor_zh") or "").strip().rstrip("。")
    if style:
        blocks.append(style + "。")

    decl = []
    idx = 1
    if beat.get("master_plate_image"):
        cam = (beat.get("camera_zh") or "").strip().rstrip("。")
        decl.append(f"参考图{idx}是这个房间的空场景底板"
                    f"（{beat.get('master_plate_id')}"
                    + (f"：{cam}" if cam else "") + "）")
        idx += 1
    for p in blocking:
        refs = list(p.get("ref_images") or [])
        if not refs:
            continue
        note = (p.get("ref_note_zh") or "").strip() or "三视图基准图"
        span = f"参考图{idx}" if len(refs) == 1 else f"参考图{idx}到{idx + len(refs) - 1}"
        decl.append(f"{span}是人物{p.get('name')}的{note}")
        idx += len(refs)
    if decl:
        blocks.append("【参考图】" + "；".join(decl) + "。")

    state = [s.strip().rstrip("。") for s in (beat.get("state_zh") or []) if s.strip()]
    if state:
        blocks.append("【这一刻房间的状态】" + "；".join(state) + "。")

    if blocking:
        blocks.append(
            "【全员走位】这个房间里此刻在场的人，一个都不能少，各自的位置是："
            + " ".join(render_blocking(p, names) for p in blocking))

    light = (beat.get("light_zh") or "").strip()
    if light:
        blocks.append("【光线】" + light.rstrip("。") + "。")

    compose = [
        "把上述所有人按【全员走位】放进参考图1的房间里，"
        "保持每个人的五官、发型、服装、体型比例、配色与其对应的人物参考图完全一致",
        "保持房间的陈设、材质、光影和相机视角与参考图1完全一致"
        "（同一个房间、同一个机位，不要重新设计房间、不要换角度）",
        "保留参考图1的完整取景范围，这一张是这一场的总览基准帧，"
        "不要裁切、不要推近——下游每一镜会各自从它里面取需要的那一块",
    ]
    blocks.append("【合成要求】" + "；".join(compose) + "。")

    avoid = list(AVOID_FIXED)
    avoid.insert(5, AVOID_WITH_PEOPLE)
    avoid += [s.strip() for s in (beat.get("avoid_extra_zh") or []) if s.strip()]
    blocks.append("避免：" + "、".join(avoid))

    return "\n".join(blocks)


def check_beat(beat, index, root):
    errors, warnings = [], []
    label = beat.get("id") or f"index_{index}"

    def err(m):
        errors.append(f"[{label}] {m}")

    def warn(m):
        warnings.append(f"[{label}] {m}")

    # present 显式填 [] = 这一节拍是空镜，房间里没有人 → 不需要主帧
    if beat.get("present") == []:
        return [], [f"[{label}] present 是空的（空镜节拍），不需要主帧，已跳过"], None
    # 显式豁免：只有一两镜、或只有一个人的节拍，主帧带不来信息量。
    # **必须写理由**——和 `plate_tier_waiver_zh` 同一条纪律：豁免要留下判断依据。
    if (beat.get("no_master_reason_zh") or "").strip():
        return [], [f"[{label}] 已声明不出主帧：{beat['no_master_reason_zh']}"], None
    for f in MASTER_REQUIRED:
        if beat.get(f) in (None, "", []):
            err(f"缺必填字段 {f}")

    plate = beat.get("master_plate_image")
    if plate and not os.path.exists(resolve(plate, root)):
        err(f"master_plate_image 指向的文件不存在: {plate}")
    if beat.get("master_plate_read_zh") and len(beat["master_plate_read_zh"]) < 20:
        err("master_plate_read_zh 太短，看起来没真的打开底板图看过——"
            "人能站哪由底板已经拍成什么样决定，不由想象决定")

    blocking = beat.get("blocking") or []
    names = [p.get("name") for p in blocking]
    present = list(beat.get("present") or [])

    # 主帧的唯一硬要求：在场的每一个人都必须在这张图里有位置
    missing = [n for n in present if n not in names]
    if missing:
        err(f"present 里的 {missing} 在 blocking 里没有走位。"
            f"**主帧的全部意义就是「这个房间此刻谁在哪」**，"
            f"漏一个人这张主帧就不成立")
    extra = [n for n in names if n not in present]
    if extra:
        err(f"blocking 里的 {extra} 不在 present 名单里")

    for i, p in enumerate(blocking):
        who = p.get("name") or f"blocking[{i}]"
        for f in BLOCKING_REQUIRED:
            if not p.get(f):
                err(f"{who} 缺必填字段 {f}")
        for f, table in (("pos_x", POS_X), ("depth", DEPTH),
                         ("body_dir", BODY_DIR),
                         ("camera_relation", CAMERA_RELATION)):
            if p.get(f) and p[f] not in table:
                err(f"{who}.{f} 取值 {p[f]!r} 不在词表里，允许的是 {sorted(table)}")
        bd, cr = p.get("body_dir"), p.get("camera_relation")
        if bd in COMPAT and cr in CAMERA_RELATION and cr not in COMPAT[bd]:
            err(f"{who} 的 body_dir={bd} 和 camera_relation={cr} 自相矛盾，"
                f"这个 body_dir 只能配 {sorted(COMPAT[bd])}")
        gz = p.get("gaze_at")
        if gz and gz not in GAZE_FIXED and not str(gz).startswith("prop:") \
                and gz not in names:
            err(f"{who}.gaze_at={gz!r} 既不是本场人物名，也不是 "
                f"{sorted(GAZE_FIXED)} 或 prop:<道具名>")
        for ref in p.get("ref_images") or []:
            if not os.path.exists(resolve(ref, root)):
                err(f"{who} 的参考图不存在: {ref}")
        for f in ("posture_zh", "holding_zh", "contact_zh"):
            if negation_hits_blocking(p.get(f) or ""):
                err(f"{who}.{f} 里用否定句写了走位，改成正向陈述")

    if len(blocking) >= 2:
        if len({p.get("depth") for p in blocking}) < 2:
            err("两人以上的主帧必须至少有两个不同的 depth——"
                "同层横排会把房间拍平成列队")
        if len({p.get("pos_x") for p in blocking}) < 2:
            err("两人以上的 pos_x 不许全部相同")
        fronts = [p.get("name") for p in blocking
                  if p.get("camera_relation") == "front"]
        if len(fronts) > 1:
            err(f"一张图里 camera_relation=front 最多 1 人，现在有 {fronts}")
        if not any(p.get("camera_relation") in FACE_TURNED for p in blocking):
            warn("主帧里没有任何人是侧面/过肩/背对——总览帧比单镜宽松一点，"
                 "但全员朝镜头依然是「合影」，看一眼是不是真的都该朝镜头")

    # seating：谁坐在哪件家具上。下游用它核对"画面里有那件家具，人却说在画外"
    seats = beat.get("seating") or {}
    for n in seats:
        if n not in present:
            err(f"seating 里的 {n} 不在 present 名单里")

    for f in ("style_anchor_zh", "camera_zh", "light_zh"):
        hit = [w for w in QUALITY_SPELL_WORDS if w in (beat.get(f) or "")]
        if hit:
            warn(f"{f} 里有质量咒/赞美词 {hit}——不产生质量只占位置")

    n_refs = len(ref_images_of_beat(beat))
    if n_refs > REF_COUNT_HARD_MAX:
        err(f"参考图 {n_refs} 张，超过接口上限 {REF_COUNT_HARD_MAX} 张。"
            f"在场人太多时，把最次要的那几个改成不给参考图、"
            f"在 posture_zh 里写清外观并放到虚焦的纵深远端")
    elif n_refs > REF_COUNT_SOFT_MAX_MASTER:
        warn(f"参考图 {n_refs} 张，主帧的软上限是 {REF_COUNT_SOFT_MAX_MASTER} 张")

    if beat.get("master_frame"):
        if os.path.exists(resolve(beat["master_frame"], root)):
            warn(f"这一节拍已经有主帧了（{beat['master_frame']}），"
                 f"重出会让已经按旧主帧出过的关键帧对不上——"
                 f"确认是要整场重做再跑")
        else:
            warn(f"master_frame 字段已经填了 {beat['master_frame']}，"
                 f"但那个文件还不存在。出完图记得把**实际选中**的那张路径填回去")

    return errors, warnings, build_master_prompt(beat)


def beat_to_job(beat, prompt):
    return {
        "id": f"master_{beat.get('id')}",
        "prompt": prompt,
        "count": int(beat.get("count") or DEFAULT_COUNT),
        "ref_images": ref_images_of_beat(beat),
        "beat_id": beat.get("id"),
        "scene": beat.get("scene"),
        "master_plate_id": beat.get("master_plate_id"),
        "present": beat.get("present"),
        "notes": beat.get("notes"),
    }


def main():
    ap = argparse.ArgumentParser(
        description="场次节拍 → 场次主帧提示词 / jobs.json（提示词不手写）")
    ap.add_argument("cards", help="keyframe_cards.json 路径（新版含 scene_beats）")
    ap.add_argument("-o", "--out", help="写出主帧 jobs.json 的路径")
    ap.add_argument("--lint", action="store_true", help="只校验并打印，不写文件")
    ap.add_argument("--only", nargs="+", metavar="BEAT_ID", help="只处理这些节拍")
    ap.add_argument("--root", default=os.getcwd(), help="解析相对路径的根目录")
    args = ap.parse_args()

    with open(args.cards, encoding="utf-8") as f:
        doc = json.load(f)
    if isinstance(doc, list):
        sys.exit("这份卡文件是旧版格式（顶层是卡的数组），里面没有 scene_beats。"
                 "先迁移成 {\"scene_beats\": [...], \"cards\": [...]}——"
                 "字段定义见 references/keyframe_card_schema.md")
    beats = doc.get("scene_beats") or []
    if not beats:
        sys.exit("scene_beats 是空的，没有主帧可以装配")

    selected = [b for b in beats if not args.only or b.get("id") in args.only]
    if args.only and not selected:
        sys.exit(f"--only 指定的 id 找不到: {args.only}")

    all_err, all_warn, jobs = [], [], []
    for i, beat in enumerate(selected):
        e, w, prompt = check_beat(beat, i, args.root)
        all_err += e
        all_warn += w
        if prompt is None:      # 空镜节拍，没有主帧要出
            continue
        jobs.append(beat_to_job(beat, prompt))
        if args.lint:
            print(f"\n{'=' * 70}\nmaster_{beat.get('id')}  "
                  f"（{len(beat.get('blocking') or [])} 人在场, "
                  f"{len(prompt)} 字）\n{'=' * 70}")
            print(prompt)

    print(f"\n共处理 {len(selected)} 个场次节拍")
    if all_warn:
        print(f"\n{len(all_warn)} 条提示:")
        for m in all_warn:
            print(f"  WARN: {m}")
    if all_err:
        print(f"\n{len(all_err)} 条错误（必须处理）:")
        for m in all_err:
            print(f"  ERROR: {m}")
        print("\n有 ERROR，没有写出 jobs.json —— 先改 scene_beats。")
        sys.exit(1)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"\n已写出 {len(jobs)} 条主帧 job → {args.out}")
        print("出完图之后：逐张打开看 → 把选中的那张路径回填进对应节拍的 "
              "`master_frame` → 再跑 build_keyframe_prompt.py")


if __name__ == "__main__":
    main()
