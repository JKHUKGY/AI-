#!/usr/bin/env python3
"""镜头卡 → MiniMax-H3 出片提示词 / h3_jobs.json（提示词是派生产物，不手写）。

这是 build_prompt.py 的 H3 版本：**同一份 shot_cards.json**，装配成 H3 要的格式。
两个模型共用一套镜头卡，换模型不用重写卡——这是这套流水线的核心不变量。

H3 的提示词跟 LTX 完全不是一回事，别拿 LTX 那套套：

  LTX（ltx_pipelines.distilled）      H3（ref2va）
  ------------------------------      ----------------------------------
  一段自由英文散文                     六段结构化字段
  首帧用 --image PATH 0 1.0 焊死       关键帧是 conditions[] 里的 reference，
                                       **不焊死**——这正是选 ref2va 的理由
  台词混在正文里                       台词必须包在 <d>[Language] ...</d>
  运镜随便写                           运镜必须用官方受控词表
  没有音频                             原生出 32kHz 立体声，声音要单独写字段
  任意时长                             5-15 秒，帧数吸附到 17n+5

**本仓库既定只用 `ref2va`**（2026-09-04 定，见
minimax-h3-generate/references/minimax_h3_ops.md 第 0 节）。`--task` 默认
就是它；fl2va/t2va 的三段格式保留在代码里，是为了将来想做首尾帧插值时不用重写。

ref2va 的映射方式：
  关键帧      → <Picture 1>，声明为 [Shot 1] 的首帧（ref guide §2.2 允许）
  角色三视图  → <Subject N>，卡上可选字段 references: [{name, image, note_zh}]
只用来定义人物长相的图**不单独立 <Picture N>**，官方要求写进对应 Subject 的定义里。

官方依据（都在 MiniMaxAI/MiniMax-H3 仓库里）：
  docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md   T2VA/I2VA/FL2VA/L2VA 三字段格式
  docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md    Ref2VA 六字段格式
  scripts/readme/reproducible-768p-*.sh        真实请求体

**为什么必须照着这个格式装配**：H3 官方系统里有一个叫 H3-Context-IR 的前置模块，
专门把人写的自由输入改写成上面这套结构化表示再喂给 H3-Base，README 原话是
"H3-Context-IR is critical to the quality of the final output"。这个模块**没有开源**，
官方给的替代方案就是"照着 Prompting Guidance 自己建一个"。这个脚本就是我们的
Context-IR：用镜头卡里已经填好的结构化字段，机械装配出官方要的结构化提示词。
所以**不要**把镜头卡的字段直接拼成一段散文丢给 H3，那等于把 Context-IR 这一步跳了。

用法:
    # 校验 + 打印装配结果
    python3 build_h3_prompt.py <shot_cards.json> --lint

    # 写出 h3_jobs.json（给 h3_submit.py 用）
    python3 build_h3_prompt.py <shot_cards.json> -o <h3_jobs.json>

    # 只处理部分镜头
    python3 build_h3_prompt.py <shot_cards.json> --only ep01_镜14 -o ...

约定从仓库根目录运行（卡里的图片路径是仓库相对路径），否则用 --root 指定。
退出码非 0 表示有必须处理的 ERROR。
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- 常量与词表

# H3 输出规格。
#
# ⚠️ 时长下限有两个官方口径，**取决于你走哪条路**，所以做成了 --min-duration：
#   README「System Overview」        4-15 秒  （原始 checkpoint / SGLang）
#   diffusers api/pipelines/minimax_h3  5-15 秒  （"the resulting duration has
#                                        to stay in that window"）
#
# 因为帧数必须是 17n+5、24fps，下限附近**可达时长只有离散的几个点**：
#     n=5   90 帧  3.750s
#     n=6  107 帧  4.458s   ← 4 秒下限和 5 秒下限之争，只差这一个档
#     n=7  124 帧  5.167s
# 也就是说两种口径的实际差别 = "4.458s 这一档能不能用"。
# 在《出狱后》v2 ep01 上这一档影响 3 个镜头（镜13/镜22/镜25，都是 4.04s）。
#
# 默认取 4.0：我们走的是 **SGLang serve**（h3_submit.py 打的就是它的 HTTP 接口），
# 而 SGLang 的 cookbook 白纸黑字写 "768-pixel short edge at 24 fps for 4-15 seconds"。
# 改走 diffusers 再传 --min-duration 5。两条都没实测过。
#
# ⚠️ 2026-09-04 更正：之前默认 5.0，理由是"便宜卡必须走 diffusers、那条路是 5 秒"。
# **这个理由是错的**——SGLang 自己就有实测验证过的 1×RTX 4090 24GB / 2×RTX 5090
# 配方，便宜卡根本不用换框架。详见 minimax_h3_ops.md 第 3 节。
H3_MIN_DURATION_DEFAULT = 4.0
H3_MAX_DURATION = 15.0
H3_FPS = 24
H3_DEFAULT_SHORT_EDGE = 768
# num_frames 会被吸附到下一个 17n+5（video VAE 能解码的粒度），
# 吸附之后的时长仍须落在 5-15 秒窗口内。
H3_FRAME_BASE = 17
H3_FRAME_OFFSET = 5
# 宽高必须是 32 的倍数（不是 LTX 的 64）
H3_DIM_MULTIPLE = 32

# 官方受控运镜词表（base guide 4.3）。key 是我们镜头卡里可能出现的说法，
# value 是官方词。**不在这张表里的运镜写法一律报 ERROR**——H3 对这套词表
# 的响应是训练出来的，自由发挥的运镜描述会退化成"镜头基本不动"。
CAMERA_MOVES = {
    "zoom in", "zoom out",
    "push in", "pull out",
    "pan left", "pan right",
    "truck left", "truck right",
    "tilt up", "tilt down",
    "pedestal up", "pedestal down",
    "arc shot", "tracking shot", "static shot",
    "shake slightly", "shake strongly",
    "pov",
    "roll clockwise", "roll counterclockwise",
}
CAMERA_AMPLITUDE = {"with small amplitude", "with large amplitude"}
CAMERA_SPEED = {"at slow speed", "at fast speed"}

# 台词语言标签：H3 稳定支持 11 种（README）。我们只会用到中文。
H3_LANGUAGES = {
    "Arabic", "Chinese", "English", "French", "German", "Italian",
    "Japanese", "Korean", "Portuguese", "Russian", "Spanish",
}

# 否定句检测——跟 build_prompt.py 同一个理由：CFG 蒸馏模型没有负面提示词通道，
# 正文里写"不要 X"只会把 X 注入编码器。
NEGATION_PATTERNS = [
    r"\bno\s+\w+", r"\bnot\s+\w+", r"\bwithout\s+\w+",
    r"\bavoid\b", r"\bnever\b", r"\bdon't\b", r"\bdoes not\b",
]

TASK_FL2VA = "fl2va"
TASK_T2VA = "t2va"
TASK_REF2VA = "ref2va"


class Issue:
    def __init__(self, level, card_id, msg):
        self.level, self.card_id, self.msg = level, card_id, msg

    def __str__(self):
        return f"{self.level}: [{self.card_id}] {self.msg}"


# ---------------------------------------------------------------- 小工具


def fmt_timestamp(sec):
    """H3 的镜头切点格式：MM:SS.mmm（base guide 4.2）。"""
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:06.3f}"


def fmt_two_decimals(sec):
    """首尾帧对齐指令里的秒数，官方要求恰好两位小数。"""
    return f"{sec:.2f}"


def find_negations(text):
    hits = []
    for pat in NEGATION_PATTERNS:
        hits += re.findall(pat, text, flags=re.I)
    return hits


# LTX 那边的运镜是自由散文（"a slow, restrained push-in that travels only far
# enough to…"），H3 要的是受控词表。这张表把 LTX 的说法映射成 H3 的三段式
# （动作 + 幅度 + 速度）。映射不到就报 ERROR 让人在卡上补 camera_en.h3_move。
LTX_TO_H3_MOVE = [
    # (在 LTX move 文本里找这些关键词, H3 的动作短语)
    (("push in", "push-in", "pushes in"), "pushes in"),
    (("pull out", "pull-out", "pulls out", "pulls back"), "pulls out"),
    (("zoom in",), "zooms in"),
    (("zoom out",), "zooms out"),
    (("pan left",), "pans left"),
    (("pan right",), "pans right"),
    (("truck left", "tracks left", "dolly left"), "trucks left"),
    (("truck right", "tracks right", "dolly right"), "trucks right"),
    (("tilt up",), "tilts up"),
    (("tilt down",), "tilts down"),
    (("pedestal up", "cranes up", "rises"), "pedestals up"),
    (("pedestal down", "cranes down", "lowers"), "pedestals down"),
    (("arc",), "makes an arc shot"),
    (("track", "follow"), "holds a tracking shot"),
    (("handheld", "shake"), "shakes slightly"),
    (("locked off", "static", "holds", "hold"), "holds a static shot"),
]

# 幅度/速度的线索词
AMPLITUDE_HINTS = [
    (("only far enough", "restrained", "slight", "small", "a hair", "subtle", "one step"),
     "with small amplitude"),
    (("large", "sweeping", "wide", "big"), "with large amplitude"),
]
SPEED_HINTS = [
    (("slow", "gradual", "gentle", "creep"), "at slow speed"),
    (("fast", "quick", "rapid", "snap"), "at fast speed"),
]


def to_h3_camera(card, card_id, issues):
    """把镜头卡上的运镜翻译成 H3 受控词表的三段式说法。

    优先用卡上手填的 camera_en.h3_move（人写死的最准）；没有就从 LTX 的
    move 文本里推。推不出来就报 ERROR——H3 对这套词表的响应是训练出来的，
    自由发挥的运镜描述会退化成"镜头基本不动"。
    """
    cam = card.get("camera_en") or {}
    explicit = (cam.get("h3_move") or "").strip()
    if explicit:
        low = explicit.lower()
        if not any(mv in low for mv in CAMERA_MOVES):
            issues.append(Issue(
                "ERROR", card_id,
                f"camera_en.h3_move={explicit!r} 里没有官方受控运镜词，"
                f"必须命中: {', '.join(sorted(CAMERA_MOVES))}"))
        return explicit

    # move 为空时退到 rig + framing_path 再推一次。
    # 理由：LTX 的卡对"镜头不动"的表达方式是 rig 写 "locked off"、framing_path
    # 写 "holds a ..."，而**根本不填 move**（不动就没什么可写的）。H3 要求显式
    # 声明运镜，但"locked off + holds"本来就等价于 static shot——让人给 35 张
    # 这样的卡手写一遍 h3_move 是纯粹的重复劳动，不是校验价值。
    raw = (cam.get("move") or "").strip()
    fallback_used = False
    if not raw:
        raw = " ".join(x for x in [(cam.get("rig") or ""),
                                   (cam.get("framing_path") or "")] if x).strip()
        fallback_used = True
    if not raw:
        issues.append(Issue(
            "ERROR", card_id,
            "camera_en 里 h3_move / move / rig / framing_path 全是空的——"
            "H3 必须显式声明运镜（不动就写 static shot）"))
        return "holds a static shot"

    low = raw.lower()
    action = None
    for keys, phrase in LTX_TO_H3_MOVE:
        if any(k in low for k in keys):
            action = phrase
            break
    if not action:
        issues.append(Issue(
            "ERROR", card_id,
            f"运镜翻不成 H3 受控词表。"
            f"{'（move 为空，已退到 rig+framing_path 推断）' if fallback_used else ''}"
            f"camera_en.move={raw!r}\n"
            f"    在卡上补一个 camera_en.h3_move，用这张表里的词: "
            f"{', '.join(sorted(CAMERA_MOVES))}"))
        return "holds a static shot"

    out = [action]
    for hints, phrase in AMPLITUDE_HINTS:
        if any(h in low for h in hints):
            out.append(phrase)
            break
    for hints, phrase in SPEED_HINTS:
        if any(h in low for h in hints):
            out.append(phrase)
            break
    return " ".join(out)


# ---------------------------------------------------------------- 说话人编号


def _all_beats(card):
    """多镜头单元时把所有镜头的 beats 串起来（说话人 ID 要跨镜保持一致）。"""
    out = []
    for sh in (card.get("shots") or [card]):
        out += sh.get("beats") or []
    return out


def assign_speaker_ids(card):
    """按台词在时间轴上的实际发声顺序分配 (S1)/(S2)…（base guide 4.4）。

    同一个人在同一镜里始终是同一个 ID；不发声的人不给 ID。
    """
    ids, order = {}, []
    for beat in _all_beats(card):
        dl = beat.get("dialogue")
        if not dl:
            continue
        spk = dl.get("speaker")
        if spk and spk not in ids:
            ids[spk] = f"S{len(ids) + 1}"
            order.append(spk)
    return ids, order


# ---------------------------------------------------------------- 装配正文


def build_dialogue_clause(dl, speaker_id, card_id, issues):
    """把一条台词装配成 H3 要的 <d>[Language] ...</d> 形式。

    官方硬规则（base guide 4.4）：
      - <d> 里面**只**放语言标签 + 用户给的原文，逐字保留、不翻译不改写
      - 说话人身份、动作、语气全部写在 <d> **外面**
      - 旁白必须用固定短语 says in an off-screen voiceover，
        而且紧跟其后要声明画面里那个人的嘴是闭着的
    """
    text = (dl.get("text_zh") or "").strip()
    if not text:
        return ""
    lang = dl.get("language") or "Chinese"
    if lang not in H3_LANGUAGES:
        issues.append(Issue("ERROR", card_id, f"台词语言 {lang!r} 不在 H3 稳定支持的 11 种里"))

    # LTX 的 delivery_en 里通常自带 "he says in Mandarin Chinese, quiet and settled"。
    # H3 把语言放进 <d> 标签，所以这里要把语言声明摘掉，只留语气/语速，
    # 否则会出现 "The speaker (S1) he says in Mandarin Chinese ... <d>[Chinese]"
    # 这种既重复又不合规的写法。
    delivery = (dl.get("delivery_en") or "").strip().rstrip(",.")
    delivery = re.sub(r"^(he|she|they|the \w+)\s+", "", delivery, flags=re.I)
    delivery = re.sub(r"\b(says?|narrates?|finishes|continues|replies)\s+in\s+"
                      r"(mandarin\s+)?\w+(\s+chinese)?\s*,?\s*", "", delivery, flags=re.I)
    delivery = delivery.strip().strip(",").strip()

    who = (dl.get("speaker_desc_en") or "The speaker").strip().rstrip(".")
    onscreen = dl.get("onscreen", True)

    if onscreen:
        lead = f"{who} ({speaker_id}) says"
        if delivery:
            lead += f", {delivery},"
        return f"{lead} <d>[{lang}] {text}</d>"
    # 旁白：官方固定短语 + 闭嘴声明，两者缺一不可（base guide 4.4）
    lead = f"{who} ({speaker_id}) says in an off-screen voiceover"
    if delivery:
        lead += f", {delivery},"
    return (f"{lead}: <d>[{lang}] {text}</d> "
            f"while their lips remain completely closed.")


# ---------------------------------------------------------------- ref2va 六段

def collect_references(card, root, cid, issues, keyframe_role="storyboard",
                       kf_cards=None):
    """整理这一镜的引用素材，分配 <Picture N> / <Subject N> 标签。

    **关键帧在 ref2va 里扮演什么角色是可选的**，三种模式的取舍见
    `minimax-h3-export/references/keyframe_or_not.md`：

      first_frame  关键帧当第 0 帧          最接近 LTX，构图最死，最可能复现 A9
      storyboard   关键帧当分镜参考（默认） 保住构图引导，又不制造"焊死 vs 先验"的矛盾
      none         不用关键帧               场景底板 + 角色三视图各当 <Subject N>，
                                            省掉整个 keyframe-gen 阶段，但丢掉人工审查闸门

    `none` 模式需要场景底板和角色三视图的**图片路径**。镜头卡上只有
    `scene_plate` 这个 id，真实路径在关键帧卡里（`plate_image` /
    `people[].ref_images`），所以传 kf_cards 进来复用——**不需要为了走这条路
    重新准备素材**，关键帧本来就是这两样的合成产物。
    """
    pics, subjects, conditions = [], [], []

    def add_subject(name, img, note, kind):
        idx = len(subjects) + 1
        if not img:
            return
        if not os.path.exists(os.path.join(root, img)):
            issues.append(Issue("ERROR", cid, f"参考图不存在: {img}"))
        if kind == "scene":
            d = (f"<Subject {idx}> is the location and camera setup shown in the "
                 f"supplied scene plate ({name}); its layout, furnishings, materials, "
                 f"lighting and the camera's position within it are followed.")
        else:
            d = (f"<Subject {idx}> is {name}, whose appearance, hair, clothing and "
                 f"proportions come from the supplied character reference sheet"
                 + (f" ({note})" if note else "") + ".")
        subjects.append({"label": f"<Subject {idx}>", "name": name,
                         "def_en": d, "path": img, "kind": kind})
        conditions.append({"type": "image", "path": img, "role": "reference"})

    kf = None
    if kf_cards:
        base = re.sub(r"_u\d+$", "", cid)
        kf = next((c for c in kf_cards if c.get("id") == base), None)

    ff = card.get("first_frame")
    if keyframe_role != "none" and ff:
        if not os.path.exists(os.path.join(root, ff)):
            issues.append(Issue("ERROR", cid, f"first_frame 不存在: {ff}"))
        if keyframe_role == "first_frame":
            d = ("<Picture 1> is the first frame of [Shot 1], establishing the "
                 "composition, subject placement, lighting and scene of the shot.")
            r = ("<Picture 1> ([Shot 1] first frame): fully_preserved - the "
                 "composition, subject placement, lighting and scene of the shot "
                 "are taken from it.")
            lead = "the shot begins from <Picture 1>"
            anchor = True
        else:   # storyboard
            d = ("<Picture 1> is a storyboard reference for [Shot 1], defining its "
                 "viewpoint, subject placement, framing and scene.")
            r = ("<Picture 1> ([Shot 1] storyboard reference): partially_preserved - "
                 "the viewpoint, subject placement and framing are followed, while "
                 "the shot develops in time away from that exact arrangement.")
            lead = "the shot follows the viewpoint and subject placement of <Picture 1>"
            anchor = False
        pics.append({"label": "<Picture 1>", "def_en": d, "ret_en": r,
                     "lead_en": lead, "path": ff, "is_frame_anchor": anchor})
        conditions.append({"type": "image", "path": ff, "role": "reference"})

    if keyframe_role == "none":
        # 场景底板当 <Subject>，人物三视图当 <Subject>
        if kf:
            add_subject(kf.get("plate_id") or card.get("scene_plate") or "the scene",
                        kf.get("plate_image"), None, "scene")
            for pp in kf.get("people") or []:
                imgs = pp.get("ref_images") or []
                add_subject(pp.get("name"), imgs[0] if imgs else None,
                            pp.get("ref_note_zh"), "person")
        else:
            issues.append(Issue(
                "ERROR", cid,
                "--keyframe-role none 需要关键帧卡提供场景底板和角色三视图的路径，"
                "但没找到对应的关键帧卡。用 --keyframe-cards 指定 keyframe_cards.json"))

    # 卡上手填的 references 永远生效（跟模式无关）
    for ref in card.get("references") or []:
        add_subject(ref.get("name") or "a subject", ref.get("image"),
                    ref.get("note_zh"), "person")

    n_img = sum(1 for c in conditions if c["type"] == "image")
    if n_img > 9:
        issues.append(Issue("ERROR", cid, f"参考图 {n_img} 张，超过 ref2va 的 9 张上限"))
    if len(conditions) > 12:
        issues.append(Issue("ERROR", cid, f"参考素材 {len(conditions)} 个，超过总数 12 的上限"))
    if not conditions:
        issues.append(Issue(
            "ERROR", cid,
            "这一镜一个参考素材都没有。ref2va 至少要有一个；"
            "纯文生请用 --task t2va"))
    return pics, subjects, conditions


def build_ref2va_prompt(card, speaker_ids, pics, subjects, issues):
    """装配 ref2va 的六段。顺序固定，一段都不能少（ref guide §1）。"""
    cid = card["id"]
    style = (card.get("style_tail_en") or "").strip().rstrip(".")

    # ---- ① subject_definitions
    defs = [p["def_en"] for p in pics] + [x["def_en"] for x in subjects]
    if not defs:
        issues.append(Issue(
            "ERROR", cid,
            "ref2va 至少要有一个引用素材。这一镜既没有 first_frame 也没有 references——"
            "纯文生请改用 t2va"))
        defs = ["<Subject 1> is the main subject described below."]

    # ---- ② summary：方括号任务类型前缀
    # 任务类型前缀（ref guide §3）：图当具体帧锚点才算 keyframe completion；
    # 当分镜/构图参考、或纯人物场景参考，都算 reference generation。
    kinds = []
    if any(p.get("is_frame_anchor") for p in pics):
        kinds.append("keyframe completion")
    if subjects or any(not p.get("is_frame_anchor") for p in pics):
        kinds.append("reference generation")
    prefix = " + ".join(kinds) or "reference generation"
    labels = ", ".join([p["label"] for p in pics] + [x["label"] for x in subjects])
    intent = (card.get("intent_zh") or "").strip()
    summary = (f"[{prefix}] The target video is a single shot built from {labels}. "
               f"{(card.get('summary_en') or '').strip()}").strip()
    if not (card.get("summary_en") or "").strip():
        issues.append(Issue(
            "WARN", cid,
            "卡上没有 summary_en，summary 段只能靠标签拼出来。"
            f"这一镜的意图是「{intent}」——把它翻成一句英文填进 summary_en 会明显更好"))

    # ---- ③ retention_analysis：每个标签一行
    # ⚠️ 官方明确：这一段里**不许出现 (Sx)**
    ret = []
    for p in pics:
        ret.append(p["ret_en"])
    for x in subjects:
        ret.append(f"{x['label']} (appears in [Shot 1]): fully_preserved - {x['name']}'s "
                   f"identity, hair, clothing and proportions are retained.")

    # ---- ④ detailed_description：风格句在 [Shot 1] 之前（ref guide §5.2）
    # **支持多镜头单元**：H3 一次生成可以包含多个镜头，用
    # `[Shot N] At MM:SS.mmm, the camera cuts to ...` 分隔（base guide 4.2）。
    # 这是 LTX 完全没有的能力，也是我们能把 2-3 秒短镜打包进 4-15 秒窗口的原因。
    shots = card.get("shots") or [card]
    body = [f"The target video is in a {style} style." if style else ""]

    t_cursor = 0.0
    for si, sh in enumerate(shots, start=1):
        if si == 1:
            body.append("[Shot 1]")
            lead = []
            for p in pics:
                lead.append(p["lead_en"])
            subj_txt = (card.get("subject_lock_en") or
                        sh.get("subject_lock_en") or "").strip().rstrip(".")
            for x in subjects:
                if x.get("kind") == "scene":
                    lead.append(f"the shot takes place in {x['label']}, keeping its layout, "
                                f"furnishings, materials and lighting")
                else:
                    lead.append(f"{x['label']} ({x['name']}) is present and keeps the "
                                f"appearance established in its reference")
            if not subjects and subj_txt:
                lead.append(f"the subject is {subj_txt}")
            body.append(("; ".join(lead) + ".") if lead else "")
        else:
            # 后续镜头：严格递增的切点 + 官方认可的切镜说法
            body.append(f"[Shot {si}] At {fmt_timestamp(t_cursor)}, the camera cuts to")
            fp = ((sh.get("camera_en") or {}).get("framing_path") or "").strip().rstrip(".")
            pos = ((sh.get("camera_en") or {}).get("position") or "").strip().rstrip(".")
            body.append((f"{fp}." if fp else "a new setup.") +
                        (f" {pos}." if pos else ""))

        body.append(f"The camera {to_h3_camera(sh, cid, issues)}.")

        for beat in sh.get("beats") or []:
            motion = (beat.get("motion_en") or "").strip()
            if motion:
                body.append(motion if motion.endswith((".", "!", "?")) else motion + ".")
            dl = beat.get("dialogue")
            if dl:
                sid = speaker_ids.get(dl.get("speaker"), "S1")
                clause = build_dialogue_clause(dl, sid, cid, issues)
                if clause:
                    body.append(clause)
            sfx = (beat.get("sfx_en") or "").strip()
            if sfx:
                body.append(sfx if sfx.endswith(".") else sfx + ".")

        t_cursor += float(sh.get("duration_sec") or 0)

    detailed = " ".join(x for x in body if x).replace("[Shot 1] .", "[Shot 1]")

    # 官方建议生成类任务 350-500 词；太短说明卡填得不够细
    words = len(re.findall(r"[A-Za-z']+", detailed))
    if words < 200:
        issues.append(Issue(
            "WARN", cid,
            f"detailed_description 只有约 {words} 个英文词，官方对生成类任务建议 350-500。"
            f"太短通常意味着镜头卡的逐拍动作写得太笼统——回去把 beats 写细，"
            f"不要在这里灌水凑字数"))

    return "\n\n".join([
        "subject_definitions:\n" + "\n".join(defs),
        "summary:\n" + summary,
        "retention_analysis:\n" + "\n".join(ret),
        "detailed_description:\n" + detailed,
        "overall_soundscape:\n" + build_soundscape(card),
        "non_diegetic_music:\n" + build_non_diegetic(card),
    ])


def build_shot_body(card, speaker_ids, issues):
    """装配 [Shot 1] 正文：首帧锚点 → 动作起点 → 连续发展 → 结果。

    这个顺序是 base guide 3.1 对 I2VA 的明确建议，不是我们自己编的。
    """
    cid = card["id"]
    parts = []

    style = (card.get("style_tail_en") or "").strip().rstrip(".")
    cam = card.get("camera_en") or {}
    framing = (cam.get("framing_path") or "").strip().rstrip(".")
    subject = (card.get("subject_lock_en") or "").strip().rstrip(".")

    # ① 首帧锚点：风格 + 构图 + 主体，明确说"沿用 <Picture 1> 里的样子"
    anchor = f"[Shot 1] {style}, {framing}" if framing else f"[Shot 1] {style}"
    anchor += (f". The subject is {subject}, preserving the appearance, clothing, "
               f"framing, and spatial relationships established in <Picture 1>")
    parts.append(anchor + ".")

    # ② 运镜：官方要求写成镜头内的自然英文动作，不是末尾贴标签
    parts.append(f"The camera {to_h3_camera(card, cid, issues)}.")

    # ③ 逐拍动作 + 台词
    for beat in card.get("beats") or []:
        motion = (beat.get("motion_en") or "").strip()
        if motion:
            parts.append(motion if motion.endswith((".", "!", "?")) else motion + ".")
        dl = beat.get("dialogue")
        if dl:
            spk = dl.get("speaker")
            sid = speaker_ids.get(spk, "S1")
            clause = build_dialogue_clause(dl, sid, cid, issues)
            if clause:
                parts.append(clause)
        sfx = (beat.get("sfx_en") or "").strip()
        if sfx:
            parts.append(sfx if sfx.endswith(".") else sfx + ".")

    return " ".join(parts)


def build_soundscape(card):
    """overall_soundscape：1-4 句，只写环境音/动作音/非语言人声。

    官方明确：台词、歌唱、画内音乐已经在正文里了，**不要在这里重复**。
    """
    bits = []
    for beat in _all_beats(card):
        s = (beat.get("sfx_en") or "").strip().rstrip(".")
        if s and s not in bits:
            bits.append(s)
    if not bits:
        return "N/A"
    # 去掉正文里已经出现过的重复感，压成一段
    return ". ".join(b[0].upper() + b[1:] for b in bits[:4]) + "."


def build_non_diegetic(card):
    """non_diegetic_music：只写观众听得到、角色听不到的配乐。

    官方明确：只写乐器/速度/节奏/强弱变化，**不要写抽象情绪词**，
    也不要解释配乐的情绪功能。没有配乐就写 N/A。
    """
    score = (card.get("score_en") or "").strip()
    return score if score else "N/A"


# ---------------------------------------------------------------- 单卡装配


def build_one(card, root, issues, args_task=None,
              min_duration=H3_MIN_DURATION_DEFAULT,
              keyframe_role="storyboard", kf_cards=None,
              short_edge_opt=None):
    cid = card["id"]

    # ---- 时长：先吸附到 17n+5，**再拿吸附后的值判窗口**。
    # 顺序很重要：吸附只向上取，所以 4.71s 会变成 5.167s——拿原始值判会把
    # 这种"本来合法"的单元误拦。官方原话也是 "the resulting duration has to
    # stay in that window"，判的就是 resulting。
    dur = float(card.get("duration_sec") or 0)
    want = int(round(dur * H3_FPS))
    n = max(0, -(-(want - H3_FRAME_OFFSET) // H3_FRAME_BASE))
    num_frames = H3_FRAME_BASE * n + H3_FRAME_OFFSET
    snapped = num_frames / H3_FPS

    if snapped < min_duration:
        issues.append(Issue(
            "ERROR", cid,
            f"duration_sec={dur:.2f}s 吸附到 {num_frames} 帧（{snapped:.3f}s）"
            f"仍低于 {min_duration} 秒下限。"
            f"（README 写 4 秒=SGLang 路径，diffusers 写 5 秒=便宜卡路径；"
            f"因为帧数只能取 17n+5，两者实际只差 4.458s 这一档。）"
            f"要么把这个拆段单元跟相邻单元合并，要么把节拍拉长——"
            f"LTX 那边可以照常用短单元，卡不用动"))
    if snapped > H3_MAX_DURATION:
        issues.append(Issue(
            "ERROR", cid,
            f"duration_sec={dur:.2f}s 吸附到 {num_frames} 帧（{snapped:.3f}s）"
            f"超过 15 秒上限"))

    # ---- task：本仓库既定只用 ref2va（2026-09-04 定），见 minimax_h3_ops.md 第 0 节
    task = args_task or TASK_REF2VA
    first_frame = card.get("first_frame")
    if not first_frame and card.get("first_frame_from"):
        issues.append(Issue(
            "WARN", cid,
            f"首帧还没落地，声明来自 {card['first_frame_from']}——"
            f"必须先把上一段生成出来、抽尾帧、把路径填回 first_frame 才能提交"))

    # ---- 说话人
    speaker_ids, _ = assign_speaker_ids(card)

    # ---- 按 task 装配
    ref_conditions = []
    if task == TASK_REF2VA:
        pics, subjects, ref_conditions = collect_references(
            card, root, cid, issues, keyframe_role, kf_cards)
        prompt = build_ref2va_prompt(card, speaker_ids, pics, subjects, issues)
        body = prompt
    else:
        # 三段格式（t2va / fl2va）。本仓库默认不走这条，保留是为了
        # 将来想拿 FL2VA 做首尾帧插值时不用重写。
        body = build_shot_body(card, speaker_ids, issues)
        soundscape = build_soundscape(card)
        music = build_non_diegetic(card)
        if task == TASK_FL2VA:
            head = ("For the target video, at 0.00 seconds into the target video, "
                    "<Picture 1> (from [Shot 1]) is fully referenced.")
            prompt = (f"{head}\n\n"
                      f"integrated_multimodal_description: {body}\n\n"
                      f"overall_soundscape: {soundscape}\n\n"
                      f"non_diegetic_music: {music}")
        else:
            prompt = (f"integrated_multimodal_description: {body}\n\n"
                      f"overall_soundscape: {soundscape}\n\n"
                      f"non_diegetic_music: {music}")

    # ---- 否定句检查（只查正文，<d> 里的台词原文豁免——那是人物真的在说的话）
    body_wo_dialogue = re.sub(r"<d>\[[^\]]+\][^<]*</d>", "", body)
    neg = find_negations(body_wo_dialogue)
    if neg:
        issues.append(Issue(
            "WARN", cid,
            f"正文里有否定句 {neg[:5]}——H3 跟 LTX 一样是 CFG 蒸馏、没有负面通道，"
            f"'不要 X' 只会把 X 注入编码器。改写成正向陈述"))

    # ---- 画幅：H3 用 short_edge + aspect_ratio，不是 width/height
    # ⚠️ **不要沿用镜头卡上的 width/height**——那是 LTX 的 64 整除约束凑出来的
    # 像素尺寸（704×1280）。H3 吃的是 `short_edge` + `aspect_ratio`，画布由它
    # 自己按比例算（官方：height/width default to MiniMax-H3's own canvas for
    # the aspect ratio）。所以短边固定用 768（开源只有这一档），
    # 卡上的像素尺寸只用来推比例。
    w, h = int(card.get("width") or 704), int(card.get("height") or 1280)
    short_edge = int(short_edge_opt or H3_DEFAULT_SHORT_EDGE)
    # H3 用 aspect_ratio 字符串，不是像素尺寸。我们的 704x1280 是 LTX 的
    # 64 整除约束凑出来的，化简会得到 11:20 这种 H3 不认的怪比例，
    # 所以要吸附到最近的常见比例（官方列了 21:9/16:9/4:3/1:1/3:4/9:16）。
    COMMON = {"21:9": 21 / 9, "16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1.0,
              "3:4": 3 / 4, "9:16": 9 / 16}
    ratio = w / h
    aspect = min(COMMON, key=lambda k: abs(COMMON[k] - ratio))
    if abs(COMMON[aspect] - ratio) > 0.02:
        issues.append(Issue(
            "WARN", cid,
            f"{w}x{h} 的比例 {ratio:.3f} 离最近的常见比例 {aspect} 有点远，"
            f"已吸附成 {aspect}；不想吸附就在卡上写 aspect_ratio 或用 'auto'"))
    aspect = card.get("aspect_ratio") or aspect

    job = {
        "id": cid,
        "shot_no": card.get("shot_no"),
        "scene": card.get("scene"),
        "shot_card_id": cid,
        "model": "minimax-h3",
        "task": task,
        "prompt": prompt,
        "conditions": [],
        "target": {
            "short_edge": short_edge,
            "aspect_ratio": aspect,
            "duration_seconds": round(snapped, 3),
        },
        "num_frames": num_frames,
        "seed": int(card.get("seed") or 0),
        "first_frame": first_frame,
        "first_frame_from": card.get("first_frame_from"),
        "fps": H3_FPS,
        "notes": card.get("notes"),
    }
    if task == TASK_REF2VA:
        # ref2va 的图都是 role=reference，**没有 frame_index**——
        # 它们是"参考"，不是被焊死的某一帧。这正是我们选 ref2va 的理由。
        job["conditions"] = ref_conditions
    elif first_frame:
        job["conditions"].append({
            "type": "image",
            "path": first_frame,       # 仓库相对路径，提交时由 h3_submit.py 转成 data URL
            "role": "keyframe",
            "frame_index": 0,
        })
    return job


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cards", help="shot_cards.json 路径")
    ap.add_argument("-o", "--out", help="写出 h3_jobs.json 的路径")
    ap.add_argument("--lint", action="store_true", help="只校验并打印装配结果，不写文件")
    ap.add_argument("--only", nargs="+", metavar="ID", help="只处理这些卡 id")
    ap.add_argument("--root", default=os.getcwd(), help="仓库根目录（卡里的路径相对它解析）")
    ap.add_argument("--short-edge", type=int, default=H3_DEFAULT_SHORT_EDGE,
                    help="输出短边，默认 768（H3 开源只有这一档；2K 要走没开源的 "
                         "H3-Regenerate-2K）。**不沿用镜头卡的 width/height**，"
                         "那是 LTX 的 64 整除约束凑出来的")
    ap.add_argument("--keyframe-role", choices=["storyboard", "first_frame", "none"],
                    default="storyboard",
                    help="关键帧在 ref2va 里扮演什么角色。默认 storyboard（当分镜参考，"
                         "保住构图引导又不制造'焊死 vs 先验'的矛盾）；first_frame 最接近 LTX、"
                         "构图最死；none 完全不用关键帧，改用场景底板+角色三视图各当 <Subject>。"
                         "三者取舍见 minimax-h3-export/references/keyframe_or_not.md")
    ap.add_argument("--keyframe-cards", metavar="PATH",
                    help="keyframe_cards.json 路径。--keyframe-role none 时必需"
                         "（要从里面取场景底板和角色三视图的真实路径）")
    ap.add_argument("--min-duration", type=float, default=H3_MIN_DURATION_DEFAULT,
                    metavar="秒",
                    help="时长下限。默认 4.0（SGLang cookbook 口径，我们走的就是 SGLang serve）；"
                         "改走 diffusers 传 5.0。两者实际只差 4.458s 这一档。"
                         "见 minimax-h3-generate/references/minimax_h3_ops.md 第 1 节")
    ap.add_argument("--task", choices=[TASK_REF2VA, TASK_FL2VA, TASK_T2VA], default=TASK_REF2VA,
                    help="装配成哪种任务。**默认 ref2va**——本仓库 2026-09-04 定的既定选择，"
                         "见 minimax-h3-generate/references/minimax_h3_ops.md 第 0 节。"
                         "fl2va/t2va 保留是为了将来想做首尾帧插值时不用重写")
    args = ap.parse_args()

    cards = json.loads(open(args.cards, encoding="utf-8").read())
    kf_cards = None
    if args.keyframe_cards:
        kf_cards = json.loads(open(args.keyframe_cards, encoding="utf-8").read())
    elif args.keyframe_role == "none":
        # 猜一下同项目的关键帧卡在哪：videos/ep0X → keyframes/ep0X
        guess = os.path.join(os.path.dirname(os.path.abspath(args.cards)),
                             "..", "..", "keyframes",
                             os.path.basename(os.path.dirname(os.path.abspath(args.cards))),
                             "keyframe_cards.json")
        guess = os.path.normpath(guess)
        if os.path.exists(guess):
            kf_cards = json.loads(open(guess, encoding="utf-8").read())
            print(f"（--keyframe-role none：自动找到关键帧卡 {guess}）")
    if args.only:
        want = set(args.only)
        cards = [c for c in cards if c["id"] in want or str(c.get("shot_no")) in want]
        if not cards:
            sys.exit(f"--only {args.only} 没匹配到任何卡")

    issues, jobs = [], []
    for card in cards:
        jobs.append(build_one(card, args.root, issues, args.task, args.min_duration,
                              args.keyframe_role, kf_cards, args.short_edge))

    if args.lint:
        for j in jobs:
            print("=" * 70)
            print(f"{j['id']}  task={j['task']}  {j['target']['duration_seconds']}s  "
                  f"{j['target']['short_edge']}p {j['target']['aspect_ratio']}")
            print("=" * 70)
            print(j["prompt"])
            print()

    print(f"共处理 {len(cards)} 张镜头卡（目标模型 minimax-h3）")

    warns = [i for i in issues if i.level == "WARN"]
    errs = [i for i in issues if i.level == "ERROR"]
    if warns:
        print(f"\n{len(warns)} 条提示（不阻塞，建议人工确认）:")
        for i in warns:
            print(f"  {i}")
    if errs:
        print(f"\n{len(errs)} 条错误（必须处理）:", file=sys.stderr)
        for i in errs:
            print(f"  {i}", file=sys.stderr)

    if not errs and args.out and not args.lint:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
        print(f"\n已写出 {len(jobs)} 条 job → {args.out}")

    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
