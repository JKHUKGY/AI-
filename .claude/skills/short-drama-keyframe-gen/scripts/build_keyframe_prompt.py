#!/usr/bin/env python3
"""关键帧卡 → 出图提示词 / jobs.json / 人工审阅表（提示词是派生产物，不手写）。

这是 short-drama-keyframe-gen 的**第一阶段**（提示词阶段）唯一的出口：人只
维护 keyframe_cards.json，提示词由这个脚本按固定模板机械装配，同一张卡永远
装配出同一段字符串。要改提示词，只能改卡再重跑。

它同时是走位的校验关卡。拦的都是《出狱后》ep03 实拍出来的真实故障
（证据见 references/blocking_guide.md）：

- 多人镜全员正脸/全员 3/4 正面 —— `ep03_镜10` 三个人平脸横排像合影。
  `camera_relation` 是必填枚举，一镜最多 1 人 `front`，两人以上至少 1 人
  过肩或背对。（不设"全集正脸占比"这类配额——正脸该不该用按这一镜的实际
  需求判断，审阅表会把朝向分布列出来给人看，但不替人下结论。）
- 多人镜没有纵深层次 —— 同上那张图三人同层。两人以上至少两个不同 `depth`，
  且 `pos_x` 不许全同。
- 景别从「中景」漂成全景 —— `ep03_镜03`/`ep03_镜10` 标中景、出全身带脚。
  `subject_frac` 必填并按景别查区间，`crop_zh` 必填，非全景镜 `plate_crop_zh`
  必填（这一镜取底板的哪一块），装配时景别块排在走位之前、并附一句显式的
  "取景范围按景别重新裁切"化解和底板锁定句的冲突。
- 用否定句写走位 —— ep03 的避免尾块写了「顾万通正面朝镜头」「苏慧低头含胸」
  全都没拦住。`avoid_extra_zh` 里出现朝向/景别词直接报 ERROR。
- 视线/朝向自相矛盾、正反打不越轴 —— 按 pos_x 顺序核对 gaze 方向，
  对同场景 A主机位/B反打 两张卡核对每个人左右是否翻转。
- 底板/人物参考图路径不存在、`plate_read_zh` 没真的看图就填卡。
- 质量咒（`8k`/`高细节`/`大师作品`/`masterpiece`）—— OpenAI 官方把"用赞美
  代替视觉事实"列为反面写法，这类词不产生质量只占位置（WARN）。
- 参考图堆太多 —— 接口上限 16 张，但 3-5 张精选好过一堆输入（>5 报 WARN）。

用法:
  # 校验 + 打印装配结果，什么都不写出
  python3 build_keyframe_prompt.py <keyframe_cards.json> --lint

  # 校验通过后写出给人审阅的表 + 给 generate_images.py 的 jobs
  python3 build_keyframe_prompt.py <keyframe_cards.json> \
      --review-sheet output/<故事名>/keyframes/ep0X/keyframe_prompts_ep0X.md \
      -o output/<故事名>/keyframes/ep0X/jobs_ep0X.json

约定从**仓库根目录**运行（卡里的图片路径是仓库相对路径）；不是的话用 --root
指定根目录。退出码非 0 表示有必须处理的 ERROR。
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# 枚举与渲染词表：卡上的枚举 → 提示词里的固定中文短语
# ---------------------------------------------------------------------------

POS_X = {
    "far_left": "画面最左侧",
    "left": "画面左侧",
    "center": "画面中央",
    "right": "画面右侧",
    "far_right": "画面最右侧",
}
# 横向顺序，用来核对"视线目标在自己的左边还是右边"
POS_ORDER = ["far_left", "left", "center", "right", "far_right"]

DEPTH = {
    "near": "处在靠近镜头的近端（因此比其他人更大、更靠画面下缘）",
    "mid": "处在画面中段纵深",
    "far": "处在画面纵深远端（因此比其他人更小）",
}

BODY_DIR = {
    "screen_left": "身体朝画面左侧",
    "screen_right": "身体朝画面右侧",
    "to_camera": "身体朝镜头",
    "away": "身体朝画面纵深里侧、背离镜头",
}

CAMERA_RELATION = {
    "front": "正面对着镜头、整张脸朝镜头",
    "three_quarter_front": "以3/4侧面朝镜头，能看到大半张脸和一侧耳朵",
    "profile": "以完整侧面对镜头，只看得到一侧脸的轮廓线",
    "three_quarter_back": "以3/4背面对镜头（过肩视角，看得到后脑、一侧肩膀和一点脸颊轮廓）",
    "back": "完全背对镜头，只看得到后脑与后背",
}

# body_dir → 允许的 camera_relation
COMPAT = {
    "to_camera": {"front", "three_quarter_front"},
    "away": {"back", "three_quarter_back"},
    "screen_left": {"profile", "three_quarter_front", "three_quarter_back"},
    "screen_right": {"profile", "three_quarter_front", "three_quarter_back"},
}

GAZE_FIXED = {
    "lens": "视线直视镜头",
    "off_left": "视线投向画面左侧的画外",
    "off_right": "视线投向画面右侧的画外",
    "off_up": "视线抬向斜上方",
    "off_down": "视线垂向斜下方的地面",
}

# 露脸最多的两档算"朝镜头露脸"，单镜的"合影"检查基于它
FACE_OPEN = {"front", "three_quarter_front"}
FACE_TURNED = {"profile", "three_quarter_back", "back"}

# 景别 → subject_frac 合理区间。顺序有意义：中近景要排在近景/中景之前匹配
SHOT_SIZE_RANGES = [
    (("大特写", "特写"), 0.75, 1.0),
    (("中近景",), 0.45, 0.70),
    (("近景",), 0.50, 0.80),
    (("中景",), 0.30, 0.60),
    (("全景", "远景", "定场"), 0.10, 0.45),
]
# 这些景别不需要 plate_crop_zh（本来就是底板的原始取景范围）
WIDE_SIZES = ("全景", "远景", "定场")

SAME_PLATE_RUN_WARN = 3          # 连续多少镜同一底板开始报警
PROMPT_CHARS_WARN = 2000         # 提示词长度提醒
FRAC_HARD_MARGIN = 0.15          # 超出景别区间多少算 ERROR 而不是 WARN

NEGATION_WORDS = [
    "避免", "禁止", "不要", "不得", "不能", "不许", "切勿", "不应",
    "不是", "没有", "无任何", "不再", "而不是",
]
# 出现在否定句附近就是"拿否定句写走位/景别"，直接 ERROR
BLOCKING_KEYWORDS = [
    "朝镜头", "面对镜头", "看镜头", "正脸", "正面", "对视", "背对", "侧身",
    "景别", "特写", "近景", "中景", "全景", "裁", "站姿", "前倾", "含胸",
    "低头", "抬头", "左右", "位置",
]
NEG_NEAR_CHARS = 12

# 质量咒/赞美词：不产生质量，OpenAI 官方把"用赞美代替视觉事实"列为反面写法
QUALITY_SPELL_WORDS = [
    "8k", "8K", "4k", "4K", "高细节", "超高清", "大师作品", "大师级", "精美绝伦",
    "masterpiece", "best quality", "stunning", "epic", "ultra detailed",
    "hyper detailed",
]
# 参考图数量：接口上限 16，但 3-5 张精选优于一堆输入
REF_COUNT_SOFT_MAX = 5
REF_COUNT_HARD_MAX = 16

AVOID_FIXED = [
    "多余肢体", "手指数量错误", "五官崩坏", "水印文字", "画面内出现任何文字或字幕",
    "场景陈设与场景参考图不符", "多余人物",
]
# 只有有人物的镜头才补这一条（道具镜/空镜没有人物参考图）
AVOID_WITH_PEOPLE = "人物面部/发型/服装与人物参考图不符"

_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def resolve(path, root):
    return path if os.path.isabs(path) else os.path.join(root, path)


def find_negations(text):
    return [w for w in NEGATION_WORDS if w in (text or "")]


def negation_hits_blocking(text):
    """否定词和走位/景别词挨在一起 → 认定是拿否定句写走位。"""
    text = text or ""
    hits = []
    for nw in NEGATION_WORDS:
        for m in re.finditer(re.escape(nw), text):
            window = text[max(0, m.start() - NEG_NEAR_CHARS): m.end() + NEG_NEAR_CHARS]
            for kw in BLOCKING_KEYWORDS:
                if kw in window:
                    hits.append((nw, kw))
    return hits


def shot_size_range(shot_size):
    for names, lo, hi in SHOT_SIZE_RANGES:
        if any(n in (shot_size or "") for n in names):
            return names[0], lo, hi
    return None, None, None


def is_wide(shot_size):
    return any(n in (shot_size or "") for n in WIDE_SIZES)


def gaze_label(gaze, names):
    if gaze in GAZE_FIXED:
        return GAZE_FIXED[gaze]
    if isinstance(gaze, str) and gaze.startswith("prop:"):
        return f"视线落在{gaze[5:]}上"
    if gaze in names:
        return f"视线锁在{gaze}的脸上"
    return f"视线落点：{gaze}"


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

def ref_images_of(card):
    """参考图顺序：底板永远是参考图1，然后按 people 顺序排各人的基准图。"""
    refs = [card.get("plate_image")] if card.get("plate_image") else []
    for p in card.get("people") or []:
        refs += list(p.get("ref_images") or [])
    return refs


def render_person(p, names):
    parts = [
        f"位于{POS_X.get(p.get('pos_x'), p.get('pos_x'))}、{DEPTH.get(p.get('depth'), p.get('depth'))}",
        f"{BODY_DIR.get(p.get('body_dir'), p.get('body_dir'))}，"
        f"{CAMERA_RELATION.get(p.get('camera_relation'), p.get('camera_relation'))}",
        gaze_label(p.get("gaze_at"), names),
    ]
    for key in ("posture_zh", "action_zh", "contact_zh"):
        v = (p.get(key) or "").strip()
        if v:
            parts.append(v.rstrip("。"))
    return f"{p.get('name')}：" + "；".join(parts) + "。"


def build_prompt(card):
    """关键帧卡 → 出图提示词。纯函数：同一张卡永远得到同一段字符串。

    块的顺序是固定的，而且顺序本身是在修一个实拍故障：
      1. 画风锚点
      2. 参考图声明（底板永远是参考图1）
      3. **景别与裁切** —— 排在走位之前，不再当尾巴（ep03 那批放尾部，漂了）
      4. 人物走位（逐人，位置/纵深/朝向/视线/姿态/动作）
      5. 人物关系 / 道具 / 光线
      6. 合成要求 —— 含一句显式的"取景按景别重裁"，化解与底板锁定的冲突
      7. 避免尾块
    """
    people = card.get("people") or []
    names = {p.get("name") for p in people}
    fr = card.get("framing") or {}
    blocks = []

    anchor = (card.get("style_anchor_zh") or "").strip().rstrip("。")
    if anchor:
        blocks.append(anchor + "。")

    # 参考图声明
    decl = []
    idx = 1
    if card.get("plate_image"):
        cam = (card.get("camera_zh") or "").strip().rstrip("。")
        decl.append(
            f"参考图{idx}是本镜的场景底板（{card.get('plate_id')}"
            + (f"：{cam}" if cam else "") + "）"
        )
        idx += 1
    for p in people:
        refs = list(p.get("ref_images") or [])
        if not refs:
            continue
        note = (p.get("ref_note_zh") or "").strip() or "基准图"
        span = f"参考图{idx}" if len(refs) == 1 else f"参考图{idx}到{idx + len(refs) - 1}"
        decl.append(f"{span}是人物{p.get('name')}的{note}")
        idx += len(refs)
    if decl:
        blocks.append("【参考图】" + "；".join(decl) + "。")

    # 景别与裁切
    fparts = [f"{fr.get('shot_size')}"]
    if fr.get("subject_frac") is not None:
        fparts.append(
            f"画面里最靠前的主体从头顶到画面底边占画幅高度约"
            f"{round(float(fr['subject_frac']) * 100)}%"
        )
    for key in ("crop_zh", "plate_crop_zh"):
        v = (fr.get(key) or "").strip()
        if v:
            fparts.append(v.rstrip("。"))
    blocks.append("【景别与裁切】" + "；".join(fparts) + "。")

    # 走位
    if people:
        blocks.append("【人物走位】" + " ".join(render_person(p, names) for p in people))
    rel = (card.get("relation_zh") or "").strip()
    if rel:
        blocks.append("【人物关系】" + rel.rstrip("。") + "。")
    props = [s.strip().rstrip("。") for s in (card.get("props_zh") or []) if s.strip()]
    if props:
        blocks.append("【道具】" + "；".join(props) + "。")
    light = (card.get("light_zh") or "").strip()
    if light:
        blocks.append("【光线】" + light.rstrip("。") + "。")

    # 合成要求：三句缺一不可
    compose = []
    if people:
        # 逐项点名，不写笼统的"保持一致"——OpenAI 官方 preservation 措辞要求
        # 列举具体项（same face, same tunic, same proportions, same palette）
        compose.append(
            "把上述人物按【人物走位】放进参考图1的场景里，"
            "保持每个人的五官、发型、服装、体型比例、配色与其对应的人物参考图完全一致"
        )
    compose.append(
        "保持场景的陈设、材质、光影和相机视角与参考图1完全一致"
        "（同一个房间、同一个机位，不要重新设计房间、不要换角度）"
    )
    compose.append(
        "取景范围按【景别与裁切】重新裁切，参考图1里多出来的空间"
        "（尤其画面下缘的空地面）可以裁掉，不需要保留底板的完整取景范围"
    )
    blocks.append("【合成要求】" + "；".join(compose) + "。")

    avoid = list(AVOID_FIXED)
    if people:
        avoid.insert(5, AVOID_WITH_PEOPLE)
    avoid += [s.strip() for s in (card.get("avoid_extra_zh") or []) if s.strip()]
    blocks.append("避免：" + "、".join(avoid))

    return "\n".join(blocks)


def card_to_job(card, prompt, root):
    return {
        "id": card.get("id"),
        "prompt": prompt,
        "count": int(card.get("count") or 3),
        "ref_images": ref_images_of(card),
        # 溯源字段，jobs.json 被 generate_images.py 忽略，但人和下游要用
        "keyframe_card_id": card.get("id"),
        "shot_no": card.get("shot_no"),
        "scene": card.get("scene"),
        "plate_id": card.get("plate_id"),
        "tier": card.get("tier"),
        "notes": card.get("notes"),
    }


# ---------------------------------------------------------------------------
# 单卡校验
# ---------------------------------------------------------------------------

REQUIRED_TOP = ["id", "shot_no", "scene", "plate_id", "plate_image",
                "plate_read_zh", "script_ref_zh", "beat_zh",
                "style_anchor_zh", "camera_zh", "framing"]
REQUIRED_PERSON = ["name", "ref_images", "pos_x", "depth", "body_dir",
                   "camera_relation", "gaze_at", "posture_zh", "action_zh"]
POSITIVE_FIELDS = ["camera_zh", "light_zh", "relation_zh"]
POSITIVE_PERSON_FIELDS = ["posture_zh", "action_zh", "contact_zh"]


def check_card(card, index, root):
    errors, warnings = [], []
    label = card.get("id") or f"index_{index}"

    def err(m):
        errors.append(f"[{label}] {m}")

    def warn(m):
        warnings.append(f"[{label}] {m}")

    for f in REQUIRED_TOP:
        if not card.get(f):
            err(f"缺必填字段 {f}")

    # 底板：路径要真的在，plate_read_zh 要真的看过图才写得出来
    plate = card.get("plate_image")
    if plate and not os.path.exists(resolve(plate, root)):
        err(f"plate_image 指向的文件不存在: {plate}（机位底板缺就报缺，不要用别的机位顶替）")
    if card.get("plate_read_zh") and len(card["plate_read_zh"]) < 20:
        err("plate_read_zh 太短，看起来没真的打开底板图看过——"
            "人能站哪、画面能裁到哪由底板已经拍成什么样决定")

    # 景别
    fr = card.get("framing") or {}
    if not fr.get("shot_size"):
        err("framing.shot_size 必填（抄分镜表「景别」列）")
    if not (fr.get("crop_zh") or "").strip():
        err("framing.crop_zh 必填：画面上下边切在人身上哪里、地面留几分。"
            "只写「中景」模型不知道切哪，ep03 就是这样漂成全景的")
    frac = fr.get("subject_frac")
    if frac is None:
        err("framing.subject_frac 必填（主体占画幅高度的比例，0-1）")
    else:
        try:
            frac = float(frac)
        except (TypeError, ValueError):
            err(f"framing.subject_frac 不是数字: {frac!r}")
            frac = None
    if frac is not None:
        if not 0 < frac <= 1:
            err(f"framing.subject_frac 应在 0-1 之间，现在是 {frac}")
        else:
            name, lo, hi = shot_size_range(fr.get("shot_size"))
            if not (card.get("people") or []):
                # 区间是按人体标定的，道具镜/空镜的主体是别的东西，只查裁切说明
                pass
            elif name is None:
                warn(f"景别「{fr.get('shot_size')}」不在已知词表里，"
                     f"subject_frac 没法核对")
            elif not lo <= frac <= hi:
                gap = lo - frac if frac < lo else frac - hi
                msg = (f"景别「{fr.get('shot_size')}」的 subject_frac 合理区间是 "
                       f"{lo}-{hi}，现在填 {frac}")
                (err if gap > FRAC_HARD_MARGIN else warn)(msg)
    if not is_wide(fr.get("shot_size")) and not (fr.get("plate_crop_zh") or "").strip():
        err("非全景镜必须填 framing.plate_crop_zh：这一镜取底板的哪一块、"
            "放大多少、底板里哪些东西因此看不到。不写这句，"
            "「保持场景与参考图一致」会把取景范围也锁住")

    # 正向字段里的否定句
    for f in POSITIVE_FIELDS:
        text = card.get(f) or ""
        if negation_hits_blocking(text):
            err(f"{f} 里用否定句写了走位/景别：{negation_hits_blocking(text)[:3]}。"
                f"改成正向陈述（朝向用 camera_relation，景别用 framing.*）")
        elif find_negations(text):
            warn(f"{f} 里有否定词 {find_negations(text)}，尽量改成正向陈述")

    for item in card.get("avoid_extra_zh") or []:
        hit = [kw for kw in BLOCKING_KEYWORDS if kw in item]
        if hit:
            err(f"avoid_extra_zh 里的「{item}」在拿否定句写走位/景别（命中 {hit}）。"
                f"ep03 的尾块写过「顾万通正面朝镜头」「苏慧低头含胸」，一条都没拦住；"
                f"这些意图要写进 camera_relation / body_dir / framing.*")

    # 人物
    people = card.get("people")
    if people is None:
        err("people 必填（空镜/道具镜填 []）")
        people = []
    names = [p.get("name") for p in people]

    if not people:
        if not (card.get("props_zh") or []):
            err("people 为空的镜头必须填 props_zh，否则这一镜没有任何主体")
    for i, p in enumerate(people):
        who = p.get("name") or f"people[{i}]"
        for f in REQUIRED_PERSON:
            if not p.get(f):
                err(f"{who} 缺必填字段 {f}")
        for f, table in (("pos_x", POS_X), ("depth", DEPTH),
                         ("body_dir", BODY_DIR), ("camera_relation", CAMERA_RELATION)):
            if p.get(f) and p[f] not in table:
                err(f"{who}.{f} 取值 {p[f]!r} 不在词表里，允许的是 {sorted(table)}")
        bd, cr = p.get("body_dir"), p.get("camera_relation")
        if bd in COMPAT and cr in CAMERA_RELATION and cr not in COMPAT[bd]:
            err(f"{who} 的 body_dir={bd} 和 camera_relation={cr} 自相矛盾，"
                f"这个 body_dir 只能配 {sorted(COMPAT[bd])}")
        gaze = p.get("gaze_at")
        if gaze and gaze not in GAZE_FIXED and not str(gaze).startswith("prop:") \
                and gaze not in names:
            err(f"{who}.gaze_at={gaze!r} 既不是本镜里的人物名，也不是 "
                f"{sorted(GAZE_FIXED)} 或 prop:<道具名>")
        for ref in p.get("ref_images") or []:
            if not os.path.exists(resolve(ref, root)):
                err(f"{who} 的参考图不存在: {ref}（角色该造型/该视图缺就报缺，"
                    f"不要让模型凭文字猜这个人长什么样）")
        for f in POSITIVE_PERSON_FIELDS:
            text = p.get(f) or ""
            if negation_hits_blocking(text):
                err(f"{who}.{f} 里用否定句写了走位/景别，改成正向陈述")
            elif find_negations(text):
                warn(f"{who}.{f} 里有否定词 {find_negations(text)}")

    # 多人镜的三条硬规则
    if len(people) >= 2:
        fronts = [p.get("name") for p in people if p.get("camera_relation") == "front"]
        if len(fronts) > 1:
            err(f"一镜里 camera_relation=front 最多 1 人，现在有 {fronts}")
        if not any(p.get("camera_relation") in FACE_TURNED for p in people):
            err("两人以上的镜头至少要有 1 人是 profile / three_quarter_back / back。"
                "全员正面或 3/4 正面出来就是合影——ep03_镜10 就是这么变成三人合影的。"
                "默认让离镜头最近的那个人过肩")
        if len({p.get("depth") for p in people}) < 2:
            err(f"两人以上必须至少有两个不同的 depth，现在全是 "
                f"{people[0].get('depth')}——同层横排会把画面拍平成列队")
        if len({p.get("pos_x") for p in people}) < 2:
            err("两人以上的 pos_x 不许全部相同")

        # 视线方向和左右位置对不对
        order = {p.get("name"): POS_ORDER.index(p["pos_x"])
                 for p in people if p.get("pos_x") in POS_ORDER and p.get("name")}
        for p in people:
            tgt = p.get("gaze_at")
            if tgt not in order or p.get("name") not in order:
                continue
            me, other = order[p["name"]], order[tgt]
            if me == other:
                warn(f"{p.get('name')} 和 {tgt} 的 pos_x 相同，视线关系没法机械核对，"
                     f"请人工看一眼")
                continue
            want = "screen_right" if other > me else "screen_left"
            if p.get("body_dir") == want:
                continue
            msg = (f"{p.get('name')} 看的是 {tgt}（在他的画面"
                   f"{'右' if other > me else '左'}边），body_dir 应该是 {want}，"
                   f"现在是 {p.get('body_dir')}")
            if p.get("body_dir") in ("to_camera", "away"):
                warn(msg + "（如果是刻意的「看着他却不转身」，忽略这条）")
            else:
                err(msg)

        # 对视：两人互看时身体必须朝相反方向，否则是在朝同一边看
        by_name = {p.get("name"): p for p in people}
        for p in people:
            q = by_name.get(p.get("gaze_at"))
            if q is None or q.get("gaze_at") != p.get("name"):
                continue
            if p.get("body_dir") == q.get("body_dir") and p.get("body_dir") in (
                    "screen_left", "screen_right"):
                err(f"{p.get('name')} 和 {q.get('name')} 互相对视，但 body_dir 都是 "
                    f"{p.get('body_dir')}——真的对视要求两人朝向相反")

    # 质量咒：占位置不产生质量
    for f, text in [("style_anchor_zh", card.get("style_anchor_zh")),
                    ("camera_zh", card.get("camera_zh")),
                    ("light_zh", card.get("light_zh"))]:
        hit = [w for w in QUALITY_SPELL_WORDS if w in (text or "")]
        if hit:
            warn(f"{f} 里有质量咒/赞美词 {hit}——不产生质量，只占位置。"
                 f"要写实就写 photorealistic，要质感就点名具体材质和光源。"
                 f"注意：**已经出过一批图的在制项目不要中途改画风锚点**，"
                 f"跨镜一致性优先于这点微优化，留到下一部再改")

    # 参考图数量
    n_refs = len(ref_images_of(card))
    if n_refs > REF_COUNT_HARD_MAX:
        err(f"参考图 {n_refs} 张，超过接口上限 {REF_COUNT_HARD_MAX} 张")
    elif n_refs > REF_COUNT_SOFT_MAX:
        warn(f"参考图 {n_refs} 张，超过 {REF_COUNT_SOFT_MAX} 张的最优区间。"
             f"实践共识是 3-5 张精选好过一堆输入——多人镜里次要角色改用文字描述"
             f"+ 虚焦处理，不要每个人都给参考图，更不要一个人给两张视图")

    cnt = card.get("count", 3)
    try:
        if not 1 <= int(cnt) <= 6:
            warn(f"count={cnt} 不太合理，关键帧一轮出 2-3 张就够挑")
    except (TypeError, ValueError):
        err(f"count 不是整数: {cnt!r}")

    prompt = build_prompt(card)
    if len(prompt) > PROMPT_CHARS_WARN:
        warn(f"提示词 {len(prompt)} 字，偏长（>{PROMPT_CHARS_WARN}），"
             f"考虑把 posture_zh/action_zh 收紧成一句")
    return errors, warnings, prompt


# ---------------------------------------------------------------------------
# 跨卡校验
# ---------------------------------------------------------------------------

def _angle_of(plate_id):
    for tag in ("A主机位", "B反打", "C侧机位", "D细节"):
        if tag in (plate_id or ""):
            return tag
    return None


def check_all(cards):
    errors, warnings = [], []

    seen = {}
    for i, c in enumerate(cards):
        cid = c.get("id")
        if cid in seen:
            errors.append(f"[{cid}] id 重复（另一处在 index {seen[cid]}）")
        seen[cid] = i

    # 连续同一底板
    run_id, run_n, run_start = None, 0, 0
    for i, c in enumerate(cards + [{}]):
        pid = c.get("plate_id")
        if pid == run_id:
            run_n += 1
            continue
        if run_n >= SAME_PLATE_RUN_WARN:
            warnings.append(
                f"[{cards[run_start].get('id')}…{cards[run_start + run_n - 1].get('id')}] "
                f"连续 {run_n} 镜都用同一张底板 {run_id}，"
                f"这就是「整场戏一个视角演完」那个毛病")
        run_id, run_n, run_start = pid, 1, i

    # 正反打越轴：同场景、共享人物、A 与 B 机位，左右必须翻转
    for i, a in enumerate(cards):
        for b in cards[i + 1:]:
            if a.get("scene") != b.get("scene"):
                continue
            if {_angle_of(a.get("plate_id")), _angle_of(b.get("plate_id"))} != {
                    "A主机位", "B反打"}:
                continue
            pa = {p.get("name"): p.get("pos_x") for p in (a.get("people") or [])}
            pb = {p.get("name"): p.get("pos_x") for p in (b.get("people") or [])}
            shared = [n for n in pa if n in pb]
            if len(shared) < 2:
                continue
            for n in shared:
                xa, xb = pa[n], pb[n]
                if xa not in POS_ORDER or xb not in POS_ORDER:
                    continue
                sa = POS_ORDER.index(xa) - 2
                sb = POS_ORDER.index(xb) - 2
                if sa == 0 or sb == 0:
                    continue
                if (sa > 0) == (sb > 0):
                    errors.append(
                        f"[{a.get('id')} vs {b.get('id')}] 越轴：{n} 在 "
                        f"{a.get('id')}（{_angle_of(a.get('plate_id'))}）里在{POS_X[xa]}，"
                        f"在 {b.get('id')}（{_angle_of(b.get('plate_id'))}）里也在"
                        f"{POS_X[xb]}，是同一侧。反打必须左右翻转，"
                        f"依据 scenes.md「空间关系」块的四向速记")
    return errors, warnings


# ---------------------------------------------------------------------------
# 人工审阅表
# ---------------------------------------------------------------------------

def person_row(p):
    return (f"| {p.get('name')} | {POS_X.get(p.get('pos_x'), p.get('pos_x'))} | "
            f"{p.get('depth')} | {BODY_DIR.get(p.get('body_dir'), p.get('body_dir'))} | "
            f"{CAMERA_RELATION.get(p.get('camera_relation'), p.get('camera_relation'))} | "
            f"{p.get('gaze_at')} | {p.get('posture_zh')} / {p.get('action_zh')} |")


def review_sheet(cards, results, cards_path):
    total = sum(len(c.get("people") or []) for c in cards)
    fronts = sum(1 for c in cards for p in (c.get("people") or [])
                 if p.get("camera_relation") == "front")
    turned = sum(1 for c in cards for p in (c.get("people") or [])
                 if p.get("camera_relation") in FACE_TURNED)
    n_err = sum(len(r[0]) for r in results.values())
    n_warn = sum(len(r[1]) for r in results.values())

    L = []
    L.append("# 关键帧提示词审阅表（出图之前给人看的那一版）")
    L.append("")
    L.append(f"- 卡文件：`{cards_path}`（**提示词是这个文件装配出来的派生产物，"
             f"要改提示词请改卡再重跑脚本，不要手改本表或 jobs.json**）")
    L.append(f"- 共 {len(cards)} 镜，{total} 个人物主体")
    L.append(f"- 朝向分布：正面对镜头 {fronts} 人次"
             f"（{(fronts / total if total else 0):.0%}）、"
             f"侧面/过肩/背对 {turned} 人次")
    L.append(f"- 校验：{n_err} 条 ERROR、{n_warn} 条 WARN")
    L.append("")
    L.append("审阅的时候重点看三件事（这三样是这一步真实翻过车的地方，"
             "见 `references/blocking_guide.md`）：")
    L.append("")
    L.append("1. **朝向**：这一镜里该露脸的是谁？近端那个人是不是过肩/背对？"
             "有没有整镜人全是正脸？")
    L.append("2. **走位与纵深**：几个人是不是被摆成了同一层的横排？"
             "视线连起来是不是一条线？")
    L.append("3. **景别与裁切**：`subject_frac` + 裁切说明描述的画面，"
             "和分镜表要的景别是同一件事吗？")
    L.append("")
    L.append("## 汇总")
    L.append("")
    L.append("| 镜号 | id | 分级 | 机位底板 | 景别 | 主体占幅 | 人物（位置/纵深/朝向） | 校验 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for c in cards:
        fr = c.get("framing") or {}
        e, w, _ = results[c.get("id")]
        who = "；".join(
            f"{p.get('name')}({POS_X.get(p.get('pos_x'), '?')}/{p.get('depth')}/"
            f"{p.get('camera_relation')})" for p in (c.get("people") or [])
        ) or "（无人物）"
        flag = "OK" if not e and not w else (f"{len(e)}E/{len(w)}W")
        L.append(f"| {c.get('shot_no')} | `{c.get('id')}` | {c.get('tier') or ''} | "
                 f"`{c.get('plate_id')}` | {fr.get('shot_size')} | "
                 f"{fr.get('subject_frac')} | {who} | {flag} |")
    L.append("")
    L.append("---")
    L.append("")

    for c in cards:
        e, w, prompt = results[c.get("id")]
        fr = c.get("framing") or {}
        L.append(f"## {c.get('id')}（镜{c.get('shot_no')}，{c.get('tier') or '-'} 级，"
                 f"{c.get('scene')} / `{c.get('plate_id')}`）")
        L.append("")
        L.append(f"**剧本原文锚点（验收依据）**：{c.get('script_ref_zh')}")
        L.append("")
        L.append(f"**分镜表画面描述原文**：{c.get('beat_zh')}")
        L.append("")
        L.append(f"**底板实际长什么样（看图后填的）**：{c.get('plate_read_zh')}")
        L.append("")
        if c.get("people"):
            L.append("**走位设计**")
            L.append("")
            L.append("| 人物 | 画面位置 | 纵深 | 身体朝向 | 相对镜头 | 视线 | 姿态 / 这一瞬间的动作 |")
            L.append("|---|---|---|---|---|---|---|")
            for p in c["people"]:
                L.append(person_row(p))
            L.append("")
        if c.get("relation_zh"):
            L.append(f"**人物关系**：{c['relation_zh']}")
            L.append("")
        if c.get("props_zh"):
            L.append(f"**道具**：{'；'.join(c['props_zh'])}")
            L.append("")
        L.append(f"**景别与裁切**：{fr.get('shot_size')}，主体占画幅高度 "
                 f"{fr.get('subject_frac')}。{fr.get('crop_zh') or ''} "
                 f"{fr.get('plate_crop_zh') or ''}")
        L.append("")
        L.append("**参考图**（顺序就是提示词里「参考图N」的编号）")
        L.append("")
        for i, r in enumerate(ref_images_of(c), 1):
            L.append(f"{i}. `{r}`")
        L.append("")
        L.append("**装配出的提示词**")
        L.append("")
        L.append("```text")
        L.append(prompt)
        L.append("```")
        L.append("")
        if e or w:
            L.append("**校验**")
            L.append("")
            for m in e:
                L.append(f"- ERROR: {m}")
            for m in w:
                L.append(f"- WARN: {m}")
            L.append("")
        L.append("---")
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="关键帧卡 → 出图提示词 / jobs.json / 人工审阅表（提示词不手写）")
    ap.add_argument("cards", help="keyframe_cards.json 路径")
    ap.add_argument("-o", "--out", help="写出 jobs.json 的路径（给 generate_images.py 用）")
    ap.add_argument("--review-sheet", metavar="PATH",
                    help="写出给人审阅的 markdown 表")
    ap.add_argument("--lint", action="store_true", help="只校验并打印装配结果，不写文件")
    ap.add_argument("--only", nargs="+", metavar="ID", help="只处理这些卡 id")
    ap.add_argument("--root", default=os.getcwd(),
                    help="解析卡里图片相对路径的根目录，默认当前工作目录（约定为仓库根）")
    args = ap.parse_args()

    with open(args.cards, encoding="utf-8") as f:
        cards = json.load(f)
    if not isinstance(cards, list):
        sys.exit("keyframe_cards.json 顶层必须是一个数组")

    selected = [c for c in cards if not args.only or c.get("id") in args.only]
    if args.only and not selected:
        sys.exit(f"--only 指定的 id 在文件里都找不到: {args.only}")

    results, jobs = {}, []
    for i, card in enumerate(selected):
        errors, warnings, prompt = check_card(card, i, args.root)
        results[card.get("id")] = (errors, warnings, prompt)
        jobs.append(card_to_job(card, prompt, args.root))
        if args.lint:
            print(f"\n{'=' * 70}\n{card.get('id')}  "
                  f"（{(card.get('framing') or {}).get('shot_size')}, "
                  f"{len(card.get('people') or [])} 人, {len(prompt)} 字）\n{'=' * 70}")
            print(prompt)

    cross_err, cross_warn = check_all(selected)
    all_err = [m for r in results.values() for m in r[0]] + cross_err
    all_warn = [m for r in results.values() for m in r[1]] + cross_warn

    print(f"\n共处理 {len(selected)} 张关键帧卡")
    if all_warn:
        print(f"\n{len(all_warn)} 条提示（不阻塞，建议人工确认）:")
        for m in all_warn:
            print(f"  WARN: {m}")
    if all_err:
        print(f"\n{len(all_err)} 条错误（必须处理）:")
        for m in all_err:
            print(f"  ERROR: {m}")

    # 审阅表照写：有 ERROR 时人也需要看到问题清单
    if args.review_sheet:
        os.makedirs(os.path.dirname(os.path.abspath(args.review_sheet)), exist_ok=True)
        with open(args.review_sheet, "w", encoding="utf-8") as f:
            f.write(review_sheet(selected, results, args.cards) + "\n")
        print(f"\n已写出审阅表 → {args.review_sheet}")

    if all_err:
        print("\n有 ERROR，没有写出 jobs.json —— 先改卡。")
        sys.exit(1)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"\n已写出 {len(jobs)} 条 job → {args.out}")
    elif not args.lint and not args.review_sheet:
        print("\n（没指定 -o / --lint / --review-sheet，什么都没写出）")

    if not all_err:
        print("未发现阻塞性问题。**但 jobs.json 还不能直接拿去出图**："
              "先把审阅表交给人确认走位/朝向/景别，拿到确认再进第二阶段。")


if __name__ == "__main__":
    main()
