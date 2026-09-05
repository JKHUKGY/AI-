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
- `people` 为空但描述里有手/背影等身体部位 —— 那个局部属于谁？属于已建立角色就必须
  进 people[] 带参考图，否则模型会按场景语境重新发明它（2026-09-03 实测）。

2026-09-04 新增的**连戏层**（这一层以前完全不存在，跨卡校验原来只查 id 重复、
连续同底板、正反打越轴，没有一条跟"人还在不在"有关）：

- **在场必须表态**：`scene_beats[].present` 列出这一节拍在这个房间里的所有人，
  每一镜的 `people` + `background_people` + `present_off_frame` 三个名单加起来
  必须正好覆盖它。漏一个人就是 ERROR。证据：《出狱后》v2 ep01 场次 1-3，
  四个人全程在客厅，九镜里五镜的画面中有那张沙发、卡上却一个字没写沙发上的
  两个人，出来的图沙发是空的（`ep01_镜25`）。
- **画外声明不能和取景打架**：某人被声明成 `present_off_frame`，而这一镜的
  `plate_crop_zh` 又明写着取了他坐的那件家具 → ERROR。
- **背景人物是一等公民**：`background_people[]` 走和主体完全一样的走位枚举 +
  参考图（或必填的 `appearance_zh`）。以前这件事是写在 `props_zh` 里的一句
  散文，没有任何约束——`ep01_镜27` 的"两个女性虚焦身影"第一轮出成了一男一女。
- **焦段**：近景/特写要的是紧底板（`..._紧`）。宽景定场底板里没有那些像素，
  硬裁的结果是模型重新合成一个相机，一旦重新合成相机"保持场景与参考图一致"
  就整体失效了——这是 `ep01_镜24` 标着 A主机位却出成全新机位的成因。
  没有紧底板时可以改用场次主帧；两样都没有又非要跑，在卡上写
  `plate_tier_waiver_zh` 说明理由才降级成 WARN。
- **场次主帧**（`scene_beats[].master_frame`）：有主帧时它取代底板当参考图1。
  底板锁的是"空房间长什么样"，主帧锁的是"此刻这个房间是什么样、谁站在哪、
  手里拿着什么"。这是星形拓扑（所有镜头都回到同一张主帧），不是链式，
  不违反「never let one shot seed the next」。

用法:
  # 校验 + 打印装配结果，什么都不写出
  python3 build_keyframe_prompt.py <keyframe_cards.json> --lint

  # 校验通过后写出给人审阅的表 + 给 generate_images.py 的 jobs
  python3 build_keyframe_prompt.py <keyframe_cards.json> \
      --review-sheet output/<故事名>/keyframes/ep0X/keyframe_prompts_ep0X.md \
      -o output/<故事名>/keyframes/ep0X/jobs_ep0X.json

卡文件的顶层有两种格式：
  旧版  [ {卡}, {卡}, ... ]
  新版  { "scene_beats": [ {节拍} ], "cards": [ {卡} ] }
旧版照跑，但连戏那几条只能报 WARN（没有 present 名单就没有判据）。

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

# 底板 id 的焦段后缀。宽底板（无后缀）是定场/全景用的；紧底板是近景/特写用的。
TIGHT_PLATE_SUFFIX = "_紧"

# 背景人物的虚焦档位 → 提示词短语
FOCUS = {
    "defocused": "处在虚焦里（轮廓、发色、衣着颜色能辨认，五官不清晰）",
    "sharp": "和主体一样实焦",
}

# 一轮出几张。**默认 1**：第一张就能用的比例很高（v2 ep01 实测 35 镜 31 镜
# 一次过），一上来就出 3 张等于给绝大多数镜头白烧两张。要多出是**返工时**
# 的手段，按 1→2→3 逐轮加（阶梯见 loop-picture-generation）。
DEFAULT_COUNT = 1

SAME_PLATE_RUN_WARN = 3          # 连续多少镜同一底板开始报警
PROMPT_CHARS_WARN = 2000         # 提示词长度提醒
FRAC_HARD_MARGIN = 0.15          # 超出景别区间多少算 ERROR 而不是 WARN

NEGATION_WORDS = [
    "避免", "禁止", "不要", "不得", "不能", "不许", "切勿", "不应",
    "不是", "没有", "无任何", "不再", "而不是",
    # 拿否定去定义朝向/视线的常见写法。**"不抬头"不会让模型把头低下去**，
    # 它只是又把"抬头"这个概念注入了一遍——要低头就正面写"下巴收在胸口"。
    "不抬", "不看", "没抬", "不朝", "不面向", "不转",
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


def needed_plate_tier(shot_size):
    """这个景别需要哪一档焦段的底板。

    近景/特写没法从宽景定场底板里"裁"出来——底板里根本没有那些像素。硬裁的
    结果是模型重新合成一个相机，一旦它重新合成相机，"保持场景与参考图一致"
    就整体失效了：房间里还有谁、背后是什么、光从哪来，全部重新发明一遍。
    这就是 ep01 镜24 标着 `A主机位` 却出成一个全新机位的成因。

    注意匹配顺序：「中近景」里含「近景」两个字，必须先判掉。
    """
    s = shot_size or ""
    if "中近景" in s or "中景" in s:
        return "wide"
    if any(n in s for n in ("大特写", "特写", "近景")):
        return "tight"
    return "wide"


# `D细节` 按词表定义就是"道具/手部/俯仰角度"的细节机位——它**本身就是紧档**，
# 不存在也不需要 `D细节_紧`。（2026-09-05：原来的规则会对每一个挂 D细节 的
# 特写镜报缺，那是把机位词表和焦段维度搞混了。）
INHERENTLY_TIGHT = ("D细节",)


def is_tight_plate(plate_id):
    pid = plate_id or ""
    return (TIGHT_PLATE_SUFFIX in pid
            or any(k in pid for k in INHERENTLY_TIGHT))


def _cam_of(plate_id):
    """底板 id → 相机位置（去掉焦段后缀）。宽底板和紧底板是同一个机位。"""
    if not plate_id:
        return None
    return plate_id.replace(TIGHT_PLATE_SUFFIX, "")


# 家具词：用来核对"这一镜画面里有那张沙发，沙发上的人写了吗"
FURNITURE_WORDS = ["沙发", "餐桌", "长桌", "茶几", "床", "办公桌",
                   "书桌", "吧台", "扶手椅", "软凳", "长凳"]
# 这些复合词里出现的家具词指的是别的东西（床头台灯不等于画面里有那张床）
FURNITURE_FALSE_FRIENDS = {
    "床": ["床头灯", "床头台灯", "床头柜", "床头", "起床", "床边小几"],
    "茶几": [],
    "沙发": [],
}
# 跨镜连戏核对的邻域半径（镜号差在这个范围内算"同一段戏"）
CONTINUITY_RADIUS = 2


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

def anchor_of(card, beat):
    """这一镜的空间锚点图：有场次主帧就用主帧，没有就退回机位底板。

    主帧（`scene_beats[].master_frame`）锁的是"此刻这个房间是什么样、谁站在
    哪、手里拿着什么、光是什么样"；底板只锁"这个空房间长什么样"。**现在每一
    镜都是从空房间重新把人搬进去一次，这就是沙发上的人会凭空消失的根**。

    这不违反「never let one shot seed the next」：那条禁的是链式（A 生 B、
    B 生 C，漂移累积）。主帧是星形——一场戏所有镜头都回到同一张主帧，
    和"所有镜头都回到同一份三视图"是完全相同的拓扑。
    """
    tier = needed_plate_tier((card.get("framing") or {}).get("shot_size"))
    master = (beat or {}).get("master_frame")
    plate = card.get("plate_image")

    # 同一个机位的中景/全景：主帧本身就是"这个机位 + 这一刻的人"，一张全包
    same_cam = (_cam_of(card.get("plate_id"))
                == _cam_of((beat or {}).get("master_plate_id")))
    if master and tier != "tight" and same_cam:
        return master, None, "master_only"

    # 其它情况：底板给**机位几何和左右关系**，主帧给**谁在场、穿什么、拿什么**。
    # 这两件事必须分开——主帧是从 A 主机位拍的，本镜可能是 B 反打，
    # 左右是相反的；拿主帧当唯一参考会把越轴关系带反。
    # 近景/特写一律走紧底板：主帧也是一张宽图，从主帧里裁特写和从底板里裁
    # 特写是同一个像素问题，主帧顶替不了紧底板。
    if plate and master:
        return plate, master, "plate_plus_master"
    if plate:
        return plate, None, "plate"
    if master:
        return master, None, "master_only"
    return None, None, None


def ref_images_of(card, beat=None):
    """参考图顺序：锚点图（主帧或底板）永远是参考图1，然后是 people，
    最后是带了基准图的 background_people。"""
    a1, a2, _ = anchor_of(card, beat)
    refs = [x for x in (a1, a2) if x]
    for p in card.get("people") or []:
        refs += list(p.get("ref_images") or [])
    for p in card.get("background_people") or []:
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


def render_background_person(p, names):
    """背景人物：走和主体一样的走位字段，外加虚焦档位和外观兜底描述。

    ep01_镜27 第一轮把"左侧虚焦的两个女性身影"出成了一男一女——因为那句话
    当时写在 `props_zh` 里，是一句没有任何约束的散文。现在它走这条路径：
    同一套 pos_x/depth/body_dir/camera_relation 枚举 + 参考图（或必填的
    `appearance_zh`），和主体受同样的校验。
    """
    parts = [
        f"位于{POS_X.get(p.get('pos_x'), p.get('pos_x'))}、{DEPTH.get(p.get('depth'), p.get('depth'))}",
        FOCUS.get(p.get("focus") or "defocused", FOCUS["defocused"]),
        f"{BODY_DIR.get(p.get('body_dir'), p.get('body_dir'))}，"
        f"{CAMERA_RELATION.get(p.get('camera_relation'), p.get('camera_relation'))}",
    ]
    if p.get("gaze_at"):
        parts.append(gaze_label(p.get("gaze_at"), names))
    for key in ("appearance_zh", "posture_zh", "action_zh", "contact_zh"):
        v = (p.get(key) or "").strip()
        if v:
            parts.append(v.rstrip("。"))
    return f"{p.get('name')}：" + "；".join(parts) + "。"


def build_prompt(card, beat=None):
    """关键帧卡（+ 所属场次节拍）→ 出图提示词。纯函数：同样的输入永远得到
    同一段字符串。

    块的顺序是固定的，而且顺序本身是在修一个实拍故障：
      1. 画风锚点
      2. 参考图声明（锚点图——主帧或底板——永远是参考图1）
      3. **场次状态** —— 这个房间此刻的既成事实（谁在场、东西摆在哪）
      4. **景别与裁切** —— 排在走位之前，不再当尾巴（ep03 那批放尾部，漂了）
      5. 人物走位（逐人，位置/纵深/朝向/视线/姿态/动作）
      6. **背景人物** —— 在画面里但不是这一镜主体的人
      7. 人物关系 / 道具 / 光线
      8. 合成要求 —— 措辞按锚点是主帧还是底板、底板是宽是紧分四种
      9. 避免尾块
    """
    people = card.get("people") or []
    bg = card.get("background_people") or []
    names = {p.get("name") for p in people} | {p.get("name") for p in bg}
    fr = card.get("framing") or {}
    blocks = []

    style = (card.get("style_anchor_zh") or "").strip().rstrip("。")
    if style:
        blocks.append(style + "。")

    a1, a2, anchor_kind = anchor_of(card, beat)

    # 参考图声明
    decl = []
    idx = 1
    cam = (card.get("camera_zh") or "").strip().rstrip("。")
    if anchor_kind == "master_only":
        decl.append(
            f"参考图{idx}是本场次的**主帧**——它同时给两样东西："
            f"这个机位的房间几何与左右关系，以及这一刻在场的人各自站在哪、"
            f"穿什么、手里拿着什么、光从哪来")
        idx += 1
    elif anchor_kind == "plate_plus_master":
        decl.append(
            f"参考图{idx}是本镜的场景底板（{card.get('plate_id')}"
            + (f"：{cam}" if cam else "")
            + f"）——**本镜的机位、房间几何和左右关系以它为准**")
        idx += 1
        decl.append(
            f"参考图{idx}是本场次的**主帧**——**只取"
            f"「这一刻谁在场、各自穿什么、手里拿着什么、光是什么颜色什么方向」**；"
            f"主帧是从另一个机位拍的，**它的左右关系不适用于本镜**，"
            f"本镜的左右一律按参考图1 和【人物走位】")
        idx += 1
    elif anchor_kind == "plate":
        decl.append(
            f"参考图{idx}是本镜的场景底板（{card.get('plate_id')}"
            + (f"：{cam}" if cam else "") + "）")
        idx += 1
    for p in people:
        refs = list(p.get("ref_images") or [])
        if not refs:
            continue
        note = (p.get("ref_note_zh") or "").strip() or "基准图"
        span = f"参考图{idx}" if len(refs) == 1 else f"参考图{idx}到{idx + len(refs) - 1}"
        decl.append(f"{span}是人物{p.get('name')}的{note}")
        idx += len(refs)
    for p in bg:
        refs = list(p.get("ref_images") or [])
        if not refs:
            continue
        note = (p.get("ref_note_zh") or "").strip() or "基准图"
        span = f"参考图{idx}" if len(refs) == 1 else f"参考图{idx}到{idx + len(refs) - 1}"
        decl.append(f"{span}是背景人物{p.get('name')}的{note}")
        idx += len(refs)
    if decl:
        blocks.append("【参考图】" + "；".join(decl) + "。")

    # 场次状态：这一场戏此刻的既成事实。跨镜复用的道具/家具占用写在这里，
    # 每一镜都重复一遍——模型不跨镜记忆（ep01 镜30 的行李箱变成棕色旧皮箱
    # 就是这么来的）。
    state = [s.strip().rstrip("。") for s in ((beat or {}).get("state_zh") or [])
             if s.strip()]
    if state:
        blocks.append("【本场此刻的状态】" + "；".join(state) + "。")

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
    if bg:
        blocks.append(
            "【背景人物】这一镜的画面里除了上述主体，还必须看得见以下这些人"
            "（他们不是这一镜的表演主体，但他们就在这个房间里，画面里不能空着）："
            + " ".join(render_background_person(p, names) for p in bg)
        )
    rel = (card.get("relation_zh") or "").strip()
    if rel:
        blocks.append("【人物关系】" + rel.rstrip("。") + "。")
    props = [s.strip().rstrip("。") for s in (card.get("props_zh") or []) if s.strip()]
    if props:
        blocks.append("【道具】" + "；".join(props) + "。")
    light = ((card.get("light_zh") or "").strip()
             or ((beat or {}).get("light_zh") or "").strip())
    if light:
        blocks.append("【光线】" + light.rstrip("。") + "。")

    # 合成要求
    compose = []
    if people or bg:
        # 逐项点名，不写笼统的"保持一致"——OpenAI 官方 preservation 措辞要求
        # 列举具体项（same face, same tunic, same proportions, same palette）
        compose.append(
            "把上述人物按【人物走位】"
            + ("和【背景人物】" if bg else "")
            + "放进参考图1的场景里，"
            "保持每个人的五官、发型、服装、体型比例、配色与其对应的人物参考图完全一致"
        )
    if anchor_kind == "master_only":
        compose.append(
            "保持房间的陈设、材质、光影方向、相机视角、以及参考图1里已经在场的"
            "每个人的位置、服装和手里的东西与参考图1完全一致"
            "（同一个房间、同一个机位、同一场戏的同一刻，"
            "不要重新设计房间、不要改变谁在哪）"
        )
    elif anchor_kind == "plate_plus_master":
        compose.append(
            "房间的陈设、材质、相机视角、左右位置关系全部按参考图1；"
            "每个人的服装、手里拿的东西、以及光的颜色和方向按参考图2"
            "（同一个房间、同一场戏的同一刻，不要重新设计房间、不要换角度）"
        )
    else:
        compose.append(
            "保持场景的陈设、材质、光影和相机视角与参考图1完全一致"
            "（同一个房间、同一个机位，不要重新设计房间、不要换角度）"
        )
    # 取景那一句：紧底板/主帧已经是本镜的取景基准，不能再叫模型"推近"，
    # 一叫推近它就重新合成一个相机。
    if anchor_kind in ("plate", "plate_plus_master") \
            and is_tight_plate(card.get("plate_id")):
        compose.append(
            "参考图1已经是本镜的取景基准（紧底板），保持它的取景范围和相机距离，"
            "只按【景别与裁切】做微调，不要拉远、不要重新构图"
        )
    elif anchor_kind == "master_only":
        compose.append(
            "取景范围按【景别与裁切】从参考图1里取那一块，"
            "取到的那一块里有什么就画什么、画面里原本就有的人一个都不要拿掉"
        )
    else:
        compose.append(
            "取景范围按【景别与裁切】重新裁切，参考图1里多出来的空间"
            "（尤其画面下缘的空地面）可以裁掉，不需要保留底板的完整取景范围"
        )
    blocks.append("【合成要求】" + "；".join(compose) + "。")

    avoid = list(AVOID_FIXED)
    if people or bg:
        avoid.insert(5, AVOID_WITH_PEOPLE)
    avoid += [s.strip() for s in (card.get("avoid_extra_zh") or []) if s.strip()]
    blocks.append("避免：" + "、".join(avoid))

    return "\n".join(blocks)


def card_to_job(card, prompt, root, beat=None):
    return {
        "id": card.get("id"),
        "prompt": prompt,
        "count": int(card.get("count") or DEFAULT_COUNT),
        "ref_images": ref_images_of(card, beat),
        # 溯源字段，jobs.json 被 generate_images.py 忽略，但人和下游要用
        "keyframe_card_id": card.get("id"),
        "shot_no": card.get("shot_no"),
        "scene": card.get("scene"),
        "plate_id": card.get("plate_id"),
        "beat_id": card.get("beat_id"),
        "master_frame": (beat or {}).get("master_frame"),
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


def check_card(card, index, root, beat=None, has_beats=False):
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

    # 场次节拍：有 scene_beats 就必须挂上去，主帧路径要真的在
    if has_beats:
        if not card.get("beat_id"):
            err("这份卡文件带了 scene_beats，本卡缺 beat_id——"
                "每一镜必须归属到一个场次节拍，连戏校验才有依据")
        elif beat is None:
            err(f"beat_id={card.get('beat_id')!r} 在 scene_beats 里找不到")
        elif beat.get("scene") and card.get("scene") and \
                beat["scene"] != card["scene"]:
            err(f"beat_id={card['beat_id']} 属于场景 {beat['scene']}，"
                f"本卡的 scene 是 {card['scene']}，对不上")
    mf = (beat or {}).get("master_frame")
    if mf and not os.path.exists(resolve(mf, root)):
        err(f"场次主帧不存在: {mf}（主帧还没出图就先别挂上去，"
            f"否则装配出的提示词引用了一张不存在的参考图）")
    if mf and len(((beat or {}).get("master_frame_read_zh") or "")) < 40:
        err(f"节拍 {(beat or {}).get('id')} 挂了主帧却没写 master_frame_read_zh"
            f"（或写得太短）。和 plate_read_zh / first_frame_state_zh 是同一道闸门："
            f"**主帧出来长什么样由图决定，不由当初的设计稿决定**——"
            f"模型经常把人摆到和 blocking 不完全一样的位置，"
            f"下游每一镜的走位要按实际那张图写")

    # 焦段：近景/特写要不到宽景底板里去裁——那些像素不存在
    fr_probe = card.get("framing") or {}
    if plate:
        want = needed_plate_tier(fr_probe.get("shot_size"))
        waiver = (card.get("plate_tier_waiver_zh") or "").strip()
        if want == "tight" and not is_tight_plate(card.get("plate_id")) and waiver:
            warn(f"景别「{fr_probe.get('shot_size')}」用宽底板，已声明豁免："
                 f"{waiver}。**豁免不改变物理**——这一镜的背景仍然是模型重新"
                 f"合成的，跨镜一致性只能靠人验收")
        elif want == "tight" and not is_tight_plate(card.get("plate_id")):
            err(f"景别「{fr_probe.get('shot_size')}」要的是**紧底板**，"
                f"现在挂的 `{card.get('plate_id')}` 是宽景底板。"
                f"从宽景底板里推近 2 倍去裁近景/特写，模型只能重新合成一个相机，"
                f"一旦重新合成相机「保持场景与参考图一致」就整体失效了"
                f"（ep01_镜24 标 A主机位、出成全新机位就是这么来的）。"
                f"补出 `{card.get('plate_id')}{TIGHT_PLATE_SUFFIX}` 这张紧底板。"
                f"**场次主帧顶替不了**——主帧也是一张宽图，从主帧里裁特写"
                f"是同一个像素问题。确实要用宽底板顶一次的，"
                f"在卡上写 `plate_tier_waiver_zh` 说清为什么——"
                f"**写了理由才降级成 WARN，不写就是硬拦**")
        if want == "wide" and is_tight_plate(card.get("plate_id")) \
                and not any(k in (card.get("plate_id") or "")
                            for k in INHERENTLY_TIGHT):
            warn(f"景别「{fr_probe.get('shot_size')}」用的是紧底板 "
                 f"`{card.get('plate_id')}`，紧底板拉不出中景/全景的空间，"
                 f"确认一下是不是挂错了")

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
    bg_people = card.get("background_people") or []
    names = [p.get("name") for p in people] + [p.get("name") for p in bg_people]

    if not people and not bg_people:
        if not (card.get("props_zh") or []):
            err("people 为空的镜头必须填 props_zh，否则这一镜没有任何主体")
        # people 为空但描述里出现身体部位 → 这个局部大概率属于某个已建立的角色
        body_words = ["手", "掌", "指", "手臂", "小臂", "背影", "肩", "脚", "腿"]
        blob = " ".join((card.get("props_zh") or []) + [card.get("beat_zh") or ""])
        hit = [w for w in body_words if w in blob]
        if hit:
            err(f"people 为空，但描述里出现了身体部位 {hit}。**这个局部属于谁？**"
                f"属于已建立三视图的角色就必须把他放进 people[] 并给 ref_images，"
                f"在 action_zh 里注明'只有手从画面下方入画、看不到脸'。"
                f"没传参考图的身体部位，模型会按场景语境重新发明它"
                f"——ep03_镜19 的手就这样出成了深肤色（2026-09-03 实测）")
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

    # 背景人物：走和主体一样的枚举校验，但不参与"合影"和纵深那几条规则
    # （他们本来就该是虚焦的背景，不是这一镜的构图主体）
    for i, p in enumerate(bg_people):
        who = p.get("name") or f"background_people[{i}]"
        for f in ("name", "pos_x", "depth", "body_dir", "camera_relation"):
            if not p.get(f):
                err(f"背景人物 {who} 缺必填字段 {f}——"
                    f"背景人物走和主体一样的走位字段，不是一句散文")
        for f, table in (("pos_x", POS_X), ("depth", DEPTH),
                         ("body_dir", BODY_DIR),
                         ("camera_relation", CAMERA_RELATION)):
            if p.get(f) and p[f] not in table:
                err(f"背景人物 {who}.{f} 取值 {p[f]!r} 不在词表里，"
                    f"允许的是 {sorted(table)}")
        bd, cr = p.get("body_dir"), p.get("camera_relation")
        if bd in COMPAT and cr in CAMERA_RELATION and cr not in COMPAT[bd]:
            err(f"背景人物 {who} 的 body_dir={bd} 和 camera_relation={cr} 自相矛盾，"
                f"这个 body_dir 只能配 {sorted(COMPAT[bd])}")
        if p.get("focus") and p["focus"] not in FOCUS:
            err(f"背景人物 {who}.focus 取值 {p['focus']!r} 不在词表里，"
                f"允许的是 {sorted(FOCUS)}")
        refs = list(p.get("ref_images") or [])
        for ref in refs:
            if not os.path.exists(resolve(ref, root)):
                err(f"背景人物 {who} 的参考图不存在: {ref}")
        if not refs and not (p.get("appearance_zh") or "").strip():
            err(f"背景人物 {who} 既没给 ref_images 也没写 appearance_zh。"
                f"没有参考图、也没有外观描述的背景人物，模型会按场景语境重新发明——"
                f"ep01_镜27 的「两个女性虚焦身影」第一轮就出成了一男一女")
        gz = p.get("gaze_at")
        if gz and gz not in GAZE_FIXED and not str(gz).startswith("prop:") \
                and gz not in names:
            err(f"背景人物 {who}.gaze_at={gz!r} 既不是本镜里的人物名，"
                f"也不是 {sorted(GAZE_FIXED)} 或 prop:<道具名>")
        for f in ("appearance_zh", "posture_zh", "action_zh", "contact_zh"):
            if negation_hits_blocking(p.get(f) or ""):
                err(f"背景人物 {who}.{f} 里用否定句写了走位/景别，"
                    f"改成正向陈述（朝向用 camera_relation，视线用 gaze_at）")

    dup = {n for n in [p.get("name") for p in people]
           if n in {q.get("name") for q in bg_people}}
    if dup:
        err(f"{sorted(dup)} 同时出现在 people 和 background_people 里——"
            f"一个人在一镜里只能是主体或背景之一")

    # 场次在场名单：卡上三个名单加起来必须正好覆盖这一节拍在场的所有人
    if beat and beat.get("present") is not None:
        present = list(beat["present"])
        off = list(card.get("present_off_frame") or [])
        accounted = set(names) | set(off)
        missing = [n for n in present if n not in accounted]
        extra = [n for n in accounted if n not in present]
        if missing:
            err(f"场次 {beat.get('id')} 此刻在场的 {missing} 在这张卡上没有交代。"
                f"每一镜都必须对在场的每个人表态：在画面里演（people）、"
                f"在画面里但不是主体（background_people）、"
                f"还是确实在画外（present_off_frame）。"
                f"**不表态就是 ep01_镜25 那种「沙发上的人凭空消失」**")
        if extra:
            err(f"{extra} 出现在这张卡上，但不在场次 {beat.get('id')} 的 present 名单里。"
                f"要么改 scene_beats 的 present，要么这个人不该在这一镜")
        # 画外声明和画内取景打架：人坐在沙发上，而这一镜的取景又明说取了沙发
        crop_blob = " ".join([
            (card.get("framing") or {}).get("plate_crop_zh") or "",
            (card.get("framing") or {}).get("crop_zh") or "",
        ])
        seats = (beat.get("seating") or {})
        for n in off:
            fur = seats.get(n)
            if fur and fur in crop_blob:
                err(f"{n} 被声明成 present_off_frame（画外），但 scene_beats 记着"
                    f"他此刻在「{fur}」上，而这一镜的取景说明里又明写着取了"
                    f"「{fur}」那一块——画面里有那件家具，家具上的人就不可能在画外。"
                    f"把他挪进 background_people")

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
    n_refs = len(ref_images_of(card, beat))
    if n_refs > REF_COUNT_HARD_MAX:
        err(f"参考图 {n_refs} 张，超过接口上限 {REF_COUNT_HARD_MAX} 张")
    elif n_refs > REF_COUNT_SOFT_MAX:
        warn(f"参考图 {n_refs} 张，超过 {REF_COUNT_SOFT_MAX} 张的最优区间。"
             f"实践共识是 3-5 张精选好过一堆输入——多人镜里次要角色改用文字描述"
             f"+ 虚焦处理，不要每个人都给参考图，更不要一个人给两张视图")

    cnt = card.get("count", DEFAULT_COUNT)
    try:
        if not 1 <= int(cnt) <= 6:
            warn(f"count={cnt} 不太合理（允许 1-6）")
        elif int(cnt) > DEFAULT_COUNT:
            warn(f"count={cnt} 高于默认的 {DEFAULT_COUNT}。"
                 f"**首轮只出 1 张**——第一张就能用的比例很高"
                 f"（《出狱后》v2 ep01 实测 35 镜里 31 镜一次过），"
                 f"首轮多出等于给那 31 镜各白烧 {int(cnt) - DEFAULT_COUNT} 张。"
                 f"多出是**返工时**的手段，按轮次 1→2→3 加，"
                 f"见 loop-picture-generation 的「加量阶梯」。"
                 f"（这一条是返工轮、或用户明确要求多出几版供他挑，就忽略）")
    except (TypeError, ValueError):
        err(f"count 不是整数: {cnt!r}")

    prompt = build_prompt(card, beat)
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


def all_named(card):
    """这张卡对哪些人表过态：画面主体 + 背景人物 + 明确声明在画外的。"""
    return ({p.get("name") for p in (card.get("people") or [])}
            | {p.get("name") for p in (card.get("background_people") or [])}
            | set(card.get("present_off_frame") or []))


def in_frame_names(card):
    return ({p.get("name") for p in (card.get("people") or [])}
            | {p.get("name") for p in (card.get("background_people") or [])})


def furniture_in(text):
    """文本里真的点到了哪些家具。会把「床头台灯」这类复合词先抹掉再匹配，
    否则一盏床头灯会被当成"画面里有那张床"。"""
    t = text or ""
    hits = []
    for w in FURNITURE_WORDS:
        probe = t
        for ff in FURNITURE_FALSE_FRIENDS.get(w, []):
            probe = probe.replace(ff, "")
        if w in probe:
            hits.append(w)
    return hits


def check_scene_continuity(cards, has_beats):
    """跨镜连戏：人不能凭空消失，画面里的家具上不能坐着"没写的人"。

    这一层以前**完全不存在**。跨卡校验原来只查三件事：id 重复、连续同底板、
    正反打越轴——没有一条跟"人还在不在"有关。结果就是《出狱后》v2 ep01
    场次 1-3：四个人全程在客厅，九镜里有五镜的画面中明明有那张沙发，
    卡上却一个字都没写沙发上的两个人，出来的图沙发是空的。
    """
    errors, warnings = [], []
    by_scene = {}
    for c in cards:
        by_scene.setdefault(c.get("scene"), []).append(c)

    for scene, group in by_scene.items():
        group = sorted(group, key=lambda c: (c.get("shot_no") or 0))

        # 规则 A（没有 scene_beats 时的兜底）：夹心检查。
        # 某人在镜 N 和镜 N+k 都在画面里，中间那几镜却对他只字未提 → 他去哪了？
        if not has_beats:
            appear = {}
            for idx, c in enumerate(group):
                for n in in_frame_names(c):
                    appear.setdefault(n, []).append(idx)
            for name, idxs in appear.items():
                if len(idxs) < 2:
                    continue
                for lo, hi in zip(idxs, idxs[1:]):
                    if hi - lo < 2:
                        continue
                    for mid in range(lo + 1, hi):
                        c = group[mid]
                        if name in all_named(c):
                            continue
                        warnings.append(
                            f"[{c.get('id')}] 连戏没交代：{name} 在 "
                            f"{group[lo].get('id')} 和 {group[hi].get('id')} 的画面里，"
                            f"中间这一镜对他只字未提。他要么还在画面里"
                            f"（写进 background_people），要么确实走开了"
                            f"（写进 present_off_frame 表个态）。"
                            f"**这份卡文件还没有 scene_beats，所以只能报 WARN**——"
                            f"迁移成 {{\"scene_beats\":[...],\"cards\":[...]}} 之后"
                            f"这一条会变成硬拦")

        # 规则 B：画面里有那件家具，家具上的人写了吗
        for i, c in enumerate(group):
            crop_blob = " ".join([
                (c.get("framing") or {}).get("plate_crop_zh") or "",
                (c.get("framing") or {}).get("crop_zh") or "",
            ])
            here = furniture_in(crop_blob)
            if not here:
                continue
            named = all_named(c)
            for j, other in enumerate(group):
                if j == i:
                    continue
                if abs((other.get("shot_no") or 0) - (c.get("shot_no") or 0)) \
                        > CONTINUITY_RADIUS:
                    continue
                for p in (other.get("people") or []):
                    if p.get("name") in named:
                        continue
                    seat_blob = " ".join([p.get("contact_zh") or "",
                                          p.get("posture_zh") or ""])
                    shared = [w for w in furniture_in(seat_blob) if w in here]
                    if shared:
                        msg = (f"[{c.get('id')}] 画面里有「{shared[0]}」"
                               f"（取景说明里写着），而 {other.get('id')} 里 "
                               f"{p.get('name')} 就在那件「{shared[0]}」上。"
                               f"这一镜对他没有任何交代 → 出来就是一件空家具"
                               f"（ep01_镜25 的空沙发就是这么来的）。"
                               f"把他写进 background_people，或者在 scene_beats 里"
                               f"说明他这时已经离开")
                        (errors if has_beats else warnings).append(msg)
    return errors, warnings


def check_all(cards, has_beats=False):
    errors, warnings = [], []

    seen = {}
    for i, c in enumerate(cards):
        cid = c.get("id")
        if cid in seen:
            errors.append(f"[{cid}] id 重复（另一处在 index {seen[cid]}）")
        seen[cid] = i

    ce, cw = check_scene_continuity(cards, has_beats)
    errors += ce
    warnings += cw

    # 连续同一机位（宽/紧两档焦段算同一个机位——机位是相机站在哪，不是焦段）
    run_id, run_n, run_start = None, 0, 0
    for i, c in enumerate(cards + [{}]):
        pid = (c.get("plate_id") or "").replace(TIGHT_PLATE_SUFFIX, "") or None
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


def review_sheet(cards, results, cards_path, beats_by_id=None):
    beats_by_id = beats_by_id or {}
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
    L.append("4. **连戏**：下面那张「在场核对表」——这一场此刻在场的每个人，"
             "每一镜是不是都表了态？被判成「画外」的那些，真的看不见吗？")
    L.append("")

    if beats_by_id:
        L.append("## 在场核对表（连戏这一层）")
        L.append("")
        L.append("> 一场戏里在场的人，每一镜必须落在三栏之一。**空着就是"
                 "「上一镜有的人下一镜消失了」**。")
        L.append("")
        for bid, b in beats_by_id.items():
            mine = [c for c in cards if c.get("beat_id") == bid]
            if not mine:
                continue
            L.append(f"### {bid}（{b.get('scene')}"
                     + (f" · {b.get('title_zh')}" if b.get("title_zh") else "")
                     + f"）　在场：{'、'.join(b.get('present') or []) or '（无）'}")
            L.append("")
            if b.get("master_frame"):
                L.append(f"- 场次主帧：`{b['master_frame']}`")
                if b.get("master_frame_read_zh"):
                    L.append(f"- 主帧实际长什么样（看图后填）：{b['master_frame_read_zh']}")
            for s in (b.get("state_zh") or []):
                L.append(f"- 状态：{s}")
            L.append("")
            L.append("| 镜号 | 画面主体 | 画面里的背景人物 | 声明在画外 |")
            L.append("|---|---|---|---|")
            for c in sorted(mine, key=lambda x: x.get("shot_no") or 0):
                L.append(
                    f"| {c.get('shot_no')} | "
                    f"{'、'.join(p.get('name') for p in (c.get('people') or [])) or '—'} | "
                    f"{'、'.join(p.get('name') for p in (c.get('background_people') or [])) or '—'} | "
                    f"{'、'.join(c.get('present_off_frame') or []) or '—'} |")
            L.append("")

    L.append("## 汇总")
    L.append("")
    L.append("| 镜号 | id | 分级 | 机位底板 | 焦段 | 景别 | 主体占幅 | 人物（位置/纵深/朝向） | 背景人物 | 校验 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for c in cards:
        fr = c.get("framing") or {}
        e, w, _ = results[c.get("id")]
        who = "；".join(
            f"{p.get('name')}({POS_X.get(p.get('pos_x'), '?')}/{p.get('depth')}/"
            f"{p.get('camera_relation')})" for p in (c.get("people") or [])
        ) or "（无人物）"
        bgwho = "、".join(p.get("name") for p in (c.get("background_people") or [])) or "—"
        beat = beats_by_id.get(c.get("beat_id")) or {}
        tier = ("主帧" if beat.get("master_frame")
                else ("紧" if is_tight_plate(c.get("plate_id")) else "宽"))
        flag = "OK" if not e and not w else (f"{len(e)}E/{len(w)}W")
        L.append(f"| {c.get('shot_no')} | `{c.get('id')}` | {c.get('tier') or ''} | "
                 f"`{c.get('plate_id')}` | {tier} | {fr.get('shot_size')} | "
                 f"{fr.get('subject_frac')} | {who} | {bgwho} | {flag} |")
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
        if c.get("background_people"):
            L.append("**背景人物**（在画面里，但不是这一镜的表演主体）")
            L.append("")
            L.append("| 人物 | 画面位置 | 纵深 | 虚焦 | 身体朝向 | 相对镜头 | 参考图/外观 |")
            L.append("|---|---|---|---|---|---|---|")
            for p in c["background_people"]:
                src = ("参考图" if p.get("ref_images")
                       else (p.get("appearance_zh") or "—"))
                L.append(
                    f"| {p.get('name')} | {POS_X.get(p.get('pos_x'), p.get('pos_x'))} | "
                    f"{p.get('depth')} | {p.get('focus') or 'defocused'} | "
                    f"{BODY_DIR.get(p.get('body_dir'), p.get('body_dir'))} | "
                    f"{CAMERA_RELATION.get(p.get('camera_relation'), p.get('camera_relation'))} | "
                    f"{src} |")
            L.append("")
        if c.get("present_off_frame"):
            L.append(f"**声明在画外（在场但这一镜看不见）**："
                     f"{'、'.join(c['present_off_frame'])}")
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
        for i, r in enumerate(ref_images_of(c, beats_by_id.get(c.get("beat_id"))), 1):
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
        doc = json.load(f)
    # 两种顶层格式：
    #   旧版：直接是卡的数组
    #   新版：{"scene_beats": [...], "cards": [...]} —— scene_beats 承载
    #        「这一场此刻谁在场、房间是什么状态、主帧是哪张」
    if isinstance(doc, list):
        cards, beats = doc, []
    elif isinstance(doc, dict) and isinstance(doc.get("cards"), list):
        cards = doc["cards"]
        beats = doc.get("scene_beats") or []
    else:
        sys.exit("keyframe_cards.json 顶层必须是卡的数组，"
                 "或 {\"scene_beats\": [...], \"cards\": [...]}")
    beats_by_id = {b.get("id"): b for b in beats}
    has_beats = bool(beats)

    selected = [c for c in cards if not args.only or c.get("id") in args.only]
    if args.only and not selected:
        sys.exit(f"--only 指定的 id 在文件里都找不到: {args.only}")

    beat_errs = []
    seen_beat = set()
    for b in beats:
        if not b.get("id"):
            beat_errs.append("scene_beats 里有一条缺 id")
        elif b["id"] in seen_beat:
            beat_errs.append(f"scene_beats id 重复: {b['id']}")
        seen_beat.add(b.get("id"))
        if b.get("present") is None:
            beat_errs.append(f"[{b.get('id')}] scene_beats 必须填 present"
                             f"（这一节拍在这个房间里的所有人）——"
                             f"没有它就没有连戏校验的依据")

    results, jobs = {}, []
    for i, card in enumerate(selected):
        beat = beats_by_id.get(card.get("beat_id"))
        errors, warnings, prompt = check_card(card, i, args.root, beat, has_beats)
        results[card.get("id")] = (errors, warnings, prompt)
        jobs.append(card_to_job(card, prompt, args.root, beat))
        if args.lint:
            print(f"\n{'=' * 70}\n{card.get('id')}  "
                  f"（{(card.get('framing') or {}).get('shot_size')}, "
                  f"{len(card.get('people') or [])} 人, {len(prompt)} 字）\n{'=' * 70}")
            print(prompt)

    cross_err, cross_warn = check_all(selected, has_beats)
    all_err = ([m for r in results.values() for m in r[0]]
               + cross_err + beat_errs)
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
            f.write(review_sheet(selected, results, args.cards, beats_by_id) + "\n")
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
