#!/usr/bin/env python3
"""镜头卡（shot_cards.json）→ LTX-2.5 正向提示词 + video_jobs.json。

这个脚本是"提示词不再手写"这条规则的执行者：提示词是**派生产物**，由
镜头卡的字段按固定模板机械装配。同一张卡永远装配出同一段字符串，改提示词
只能改卡上的某个字段再重跑本脚本。

镜头卡字段定义见
`.claude/skills/short-drama-video-gen/references/shot_card_schema.md`，
装配规则和每条校验背后的实测依据见同目录
`references/video_prompt_guide.md` 与 `references/model_capability_ledger.md`。

只做本地纯文本处理：不联网、不读模型权重、不调 GPU。

用法:
  # 只校验 + 把装配结果打到终端，不写任何文件
  python3 build_prompt.py <shot_cards.json> --lint

  # 校验通过后装配并写出 video_jobs.json（供 ltx_ssh_submit.py 消费）
  python3 build_prompt.py <shot_cards.json> -o <video_jobs.json>

  # 把每张卡的提示词单独存成 txt（方便和历史版本 diff）
  python3 build_prompt.py <shot_cards.json> --emit-prompts <dir>

  # 只处理其中几张卡
  python3 build_prompt.py <shot_cards.json> --lint --only ep01_镜06_u1

  # 正文语言：en（默认，英文正文+中文台词）/ zh（全中文正文，旧行为）
  python3 build_prompt.py <shot_cards.json> --lint --lang zh

  # 用真实 Gemma tokenizer 精确数 token（需要本地有 transformers + 分词器）
  python3 build_prompt.py <shot_cards.json> --lint --tokenizer <path-or-repo-id>

退出码非 0 表示有 ERROR 级问题（拒绝写出 video_jobs.json）；退出码 0 时
仍可能有 WARN 级提示，需要人工确认。
"""

import argparse
import json
import math
import os
import re
import sys

# ---------------------------------------------------------------------------
# 常量：全部来自本仓库已实测确认的模型行为，改动前先看 model_capability_ledger.md
# ---------------------------------------------------------------------------

# Gemma-4-12B text encoder 的上下文上限是 1024 token，**超了静默截尾**
# （雪山决斗 shot01 实测：~1030 个中文字 ≈ 874 token）。留 ~17% 余量当
# 工作预算，因为 token 估算本身是启发式的，不能贴着硬上限走。
TOKEN_HARD_LIMIT = 1024
TOKEN_BUDGET = 850

# 启发式 token 估算系数。用雪山决斗那条（~1030 CJK 字 → 874 token，
# 约 0.85 token/字）反标定后取保守值 0.9；非 CJK 按 ~3.3 字符/token 取 0.3。
TOKENS_PER_CJK_CHAR = 0.9
TOKENS_PER_ASCII_CHAR = 0.3

# 一个节拍至少要占多少秒，否则动作点挤太密、模型会把动作压缩变形。
# 按分级区分：A/B/C 级是对话/反应/空镜，节拍就该是"小幅度、慢"，2.5s 起；
# S 级是打斗/反转瞬间，起手式 1.2s、刺剑 0.7s 这种短促节拍恰恰是它的正确
# 写法，用 2.5s 卡它会逼人把动作合并成一个笼统的大动作——那正是
# model_capability_ledger.md 里"欠描述导致姿态焊死"的成因。
SECONDS_PER_BEAT_BY_TIER = {"S": 0.8, "A": 2.5, "B": 2.5, "C": 2.5}
SECONDS_PER_BEAT_DEFAULT = 2.5
MAX_BEATS = 6

# 台词语速（中文字/秒），三档，见 video_prompt_guide.md「台词时长计算」。
SPEECH_RATES = {"fast": 5.5, "normal": 4.0, "slow": 3.0}
SPEECH_BUFFER_SEC = 0.8

# distilled / dfr pipeline 都没有 --negative-prompt 参数（已用 --help 实测
# 确认），negative_prompt 字段纯存档，装配时写死这句，不再逐镜手写。
NEGATIVE_PROMPT_ARCHIVAL = (
    "(ltx_pipelines.distilled 没有 --negative-prompt 参数，此字段不会被发送，"
    "仅为兼容旧 schema 保留。想排除的东西请在镜头卡里改写成正向陈述，"
    "见 video_prompt_guide.md「否定→正向改写表」)"
)

FPS_DEFAULT = 24

# ---------------------------------------------------------------------------
# 词表
# ---------------------------------------------------------------------------

# 否定词：写进正向提示词等于把不想要的概念直接注入文本编码器。
# 拆成英文（词边界匹配）和中文（子串匹配）两套。
NEGATION_WORDS_EN = [
    "no", "not", "never", "none", "nothing", "without", "avoid", "avoids",
    "avoiding", "nor", "neither", "cannot", "dont", "doesnt", "isnt", "arent",
    "wont", "forbidden", "prohibited", "banned", "free of", "absent",
]
NEGATION_WORDS_ZH = ["避免", "禁止", "不要", "不得", "不能", "不许", "没有", "无任何", "切勿"]

_NEGATION_EN_RE = re.compile(
    r"\b(" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in NEGATION_WORDS_EN) + r")\b",
    re.IGNORECASE,
)

# 可见位移检验用的名词表：身体部位 + 常见服饰件。卡上的 props_en 会追加进来。
BODY_PART_WORDS = """
eye eyes eyelid eyelids eyelash eyelashes lash lashes brow brows eyebrow
eyebrows forehead temple nose nostril nostrils mouth lip lips teeth tooth
tongue jaw jawline chin cheek cheeks cheekbone ear ears neck throat nape
shoulder shoulders arm arms elbow elbows forearm wrist wrists hand hands
finger fingers fingertip knuckle knuckles thumb palm palms fist fists
chest ribcage torso waist hip hips spine leg legs thigh knee knees
shin calf ankle foot feet heel heels toe toes head skull hair strand strands
fringe bangs ponytail braid gaze eyeline breath breaths
scarf sleeve sleeves cuff collar hem lapel coat robe skirt dress shirt
jacket veil hood belt boot boots glove gloves
""".split()

# 运动动词表：motion_en 里出现这些词之一，说明写的是"会发生的变化"而不是
# 一个静态形容。和名词表是"或"的关系。
MOTION_VERB_WORDS = """
close closes closing tighten tightens tightening clench clenches clenching
open opens opening widen widens widening narrow narrows narrowing
lift lifts lifting raise raises raising drop drops dropping lower lowers
lowering fall falls falling sink sinks sinking rise rises rising
turn turns turning tilt tilts tilting twist twists twisting rotate rotates
step steps stepping walk walks walking stride strides run runs running
lean leans leaning bend bends bending straighten straightens straightening
push pushes pushing pull pulls pulling reach reaches reaching
shift shifts shifting slide slides sliding swing swings swinging
tremble trembles trembling shake shakes shaking shudder shudders quiver
quivers flicker flickers twitch twitches blink blinks swallow swallows
inhale inhales exhale exhales breathe breathes breathing part parts parting
press presses pressing draw draws drawing curl curls curling
flare flares flaring slump slumps slumping
drift drifts drifting stream streams streaming blow blows blowing
thrust thrusts thrusting strike strikes striking snap snaps snapping
""".split()

_BODY_OR_VERB = set(BODY_PART_WORDS) | set(MOTION_VERB_WORDS)

# 装配时自动补的正向子句（都刻意写成正向陈述，不含否定词）。
OFFSCREEN_VOICE_CLAUSE_EN = (
    "the voice comes from off-screen while the person visible in frame keeps "
    "their lips closed and still"
)
OFFSCREEN_VOICE_CLAUSE_ZH = "这是画外的声音，画面里可见的人物嘴唇保持闭合、静止"

BEAT_CONNECTORS_EN = ["First", "Then", "Next", "After that", "Meanwhile", "Finally"]
BEAT_CONNECTORS_ZH = ["先", "接着", "然后", "随后", "同时", "最后"]

# 超过这个时长的单元，节拍改用绝对时间前缀（"0.0-2.5s:"）而不是序数连接词。
TIMELINE_THRESHOLD_SEC = 6.0

_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def nearest_8k_plus_1(n):
    """LTX 要求 num_frames = 8k+1。跟 ltx_ssh_submit.py:_nearest_8k_plus_1
    保持同一个吸附算法，避免这里算出来的帧数和提交时用的不一致。"""
    k = max(round((n - 1) / 8), 0)
    return 8 * k + 1


def cjk_count(text):
    return len(_CJK_RE.findall(text or ""))


def estimate_tokens(text):
    """启发式 token 估算，系数见文件头常量。"""
    if not text:
        return 0
    cjk = cjk_count(text)
    other = len(text) - cjk
    return int(math.ceil(cjk * TOKENS_PER_CJK_CHAR + other * TOKENS_PER_ASCII_CHAR))


def exact_tokens(text, tokenizer):
    return len(tokenizer(text)["input_ids"])


def load_tokenizer(spec):
    try:
        from transformers import AutoTokenizer
    except ImportError:
        sys.exit(
            "--tokenizer 需要本地装有 transformers（pip install transformers）；"
            "不装也可以，去掉这个参数会退回启发式估算"
        )
    return AutoTokenizer.from_pretrained(spec)


def dialogue_min_duration(text_zh, pace):
    """台词最低时长：字数/语速 + 缓冲。只数 CJK 字，标点不算。
    公式和三档语速跟 video_prompt_guide.md「台词时长计算」一致。"""
    chars = cjk_count(text_zh)
    if chars == 0:
        return 0.0, 0
    rate = SPEECH_RATES.get(pace or "normal", SPEECH_RATES["normal"])
    return chars / rate + SPEECH_BUFFER_SEC, chars


# 常见目标比例。分辨率预设为了凑 64 整除往往不是精确比例（704×1280 是
# 0.550 而不是 9:16 的 0.5625），直接约分会得到 11:20 这种没人认的写法，
# 而下游 validate_video_jobs.py 又要拿 aspect_ratio 反查分辨率是否漏填，
# 所以先吸附到最近的常见比例（4% 以内），吸不上才退回精确约分。
COMMON_RATIOS = ["9:16", "16:9", "1:1", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2", "21:9"]


def aspect_ratio_str(width, height):
    if not width or not height:
        return None
    actual = int(width) / int(height)
    best, best_err = None, None
    for r in COMMON_RATIOS:
        a, b = r.split(":")
        err = abs(actual - int(a) / int(b)) / (int(a) / int(b))
        if best_err is None or err < best_err:
            best, best_err = r, err
    if best_err is not None and best_err <= 0.04:
        return best
    g = math.gcd(int(width), int(height))
    return f"{int(width) // g}:{int(height) // g}"


def find_negations(text):
    """返回文本里命中的否定词列表（英文按词边界，中文按子串）。"""
    hits = [m.group(0) for m in _NEGATION_EN_RE.finditer(text or "")]
    hits += [w for w in NEGATION_WORDS_ZH if w in (text or "")]
    return hits


def has_visible_motion(text, extra_nouns):
    """可见位移检验的机器可查部分：至少命中一个身体部位/道具名词或运动动词。"""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    vocab = _BODY_OR_VERB | {w.lower() for w in extra_nouns}
    return bool(words & vocab)


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

def _fmt_time(v):
    return f"{v:g}"


def render_beat(beat, index, total, timeline_mode, lang):
    """把一个节拍渲染成一句/一段文本。"""
    pieces = []

    if timeline_mode:
        t0, t1 = beat["t"]
        prefix = f"{_fmt_time(t0)}-{_fmt_time(t1)}s:"
    elif total > 1:
        connectors = BEAT_CONNECTORS_EN if lang == "en" else BEAT_CONNECTORS_ZH
        if index == total - 1:
            word = connectors[-1]
        else:
            word = connectors[min(index, len(connectors) - 2)]
        prefix = f"{word}," if lang == "en" else f"{word}，"
    else:
        prefix = ""

    framing = (beat.get("framing_en") if lang == "en" else beat.get("framing_zh")) or ""
    motion = (beat.get("motion_en") if lang == "en" else beat.get("motion_zh")) or ""
    motion = motion.strip()
    if framing.strip():
        # 景别放在动作之前：先告诉模型这一拍看到多大范围，再说范围里发生什么。
        if lang == "en" and motion:
            motion = motion[0].lower() + motion[1:]
        motion = framing.strip().rstrip(".。") + ("; " if lang == "en" else "；") + motion
    if prefix:
        # 序数连接词后面接小写更自然；时间前缀后面保持原样。
        if not timeline_mode and lang == "en" and motion:
            motion = motion[0].lower() + motion[1:]
        pieces.append(f"{prefix} {motion}".strip())
    else:
        pieces.append(motion)

    dlg = beat.get("dialogue")
    if dlg:
        delivery = (dlg.get("delivery_en") if lang == "en" else dlg.get("delivery_zh")) or ""
        delivery = delivery.strip().rstrip(":：,，.。")
        line = f'{delivery}: "{dlg["text_zh"]}"' if lang == "en" else f'{delivery}："{dlg["text_zh"]}"'
        pieces.append(line)
        if dlg.get("onscreen") is False:
            pieces.append(
                OFFSCREEN_VOICE_CLAUSE_EN if lang == "en" else OFFSCREEN_VOICE_CLAUSE_ZH
            )

    sfx = (beat.get("sfx_en") if lang == "en" else beat.get("sfx_zh")) or ""
    if sfx.strip():
        pieces.append(sfx.strip())

    if lang == "en":
        # 每个子句都是独立的一句话，句首大写，别出现 ". she speaks..." 这种。
        cleaned = []
        for piece in pieces:
            piece = piece.rstrip(".,")
            if piece:
                cleaned.append(piece[0].upper() + piece[1:])
        return ". ".join(cleaned) + "."
    body = "，".join(p.rstrip("。，,") for p in pieces if p)
    return body + "。"


def build_prompt(card, lang="en"):
    """镜头卡 → 正向提示词。纯函数：同一张卡永远得到同一段字符串。

    装配顺序是固定的，而且是 token 截尾的保险措施：
      1. 机位 / 景别 / 运镜（短，锁死视角）
      2. 主体锁定（一句，只为了别换人）
      3. 节拍（按时间顺序，最重要的内容）
      4. 风格尾块 —— 永远排最后，因为它是唯一被截掉也不致命的部分
    """
    cam = card.get("camera_en" if lang == "en" else "camera_zh") or {}
    head = []
    # position 排在最前：先告诉模型相机站在房间哪个位置往哪看，再说固定/手持和景别。
    for key in ("position", "rig", "framing_path", "move"):
        v = (cam.get(key) or "").strip()
        if v:
            head.append(v.rstrip(".。"))

    subject = (card.get("subject_lock_en" if lang == "en" else "subject_lock_zh") or "").strip()
    if subject:
        head.append(subject.rstrip(".。"))

    # 头块的几项（机位/景别/主体锁定）是彼此独立的陈述，中文用句号分隔更清楚，
    # 不要跟节拍内部那种"，"连读混在一起。
    sep = ". " if lang == "en" else "。"
    head_text = (sep.join(head) + ("." if lang == "en" else "。")) if head else ""

    beats = card.get("beats") or []
    timeline_mode = float(card.get("duration_sec") or 0) > TIMELINE_THRESHOLD_SEC
    beat_texts = [
        render_beat(b, i, len(beats), timeline_mode, lang) for i, b in enumerate(beats)
    ]

    tail = (card.get("style_tail_en" if lang == "en" else "style_tail_zh") or "").strip()
    if tail:
        tail = tail.rstrip(".。") + ("." if lang == "en" else "。")

    # 保持不变的东西：排在节拍之后、风格尾块之前。
    # 依据是 I2V 通用五要素的第 3 条"say what must stay unchanged"，以及
    # OpenAI 侧同样的 preservation 约束——两边都要求把"不变量"显式点名。
    preserve = (card.get("preserve_en" if lang == "en" else "preserve_zh") or "").strip()
    if preserve:
        prefix = "Throughout the shot, " if lang == "en" else "整段之内，"
        preserve = prefix + preserve.rstrip(".。") + ("." if lang == "en" else "。")

    blocks = ([head_text] + beat_texts
              + ([preserve] if preserve else [])
              + ([tail] if tail else []))
    return "\n\n".join(b for b in blocks if b)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def check_card(card, index, lang, tokenizer, cards_by_unit, cards_root):
    errors = []
    warnings = []
    label = card.get("id", f"index_{index}")

    def err(msg):
        errors.append(f"[{label}] {msg}")

    def warn(msg):
        warnings.append(f"[{label}] {msg}")

    # --- 1. 必填字段 -------------------------------------------------------
    for field in ("id", "shot_no", "scene", "duration_sec",
                  "width", "height", "seed", "script_ref"):
        if card.get(field) in (None, ""):
            err(f"缺少必填字段 `{field}`")

    # first_frame 和 first_frame_from 二选一必填。分段生成时后续段的首帧要等
    # 上一段真的跑出来才能抽帧，所以允许先用 first_frame_from 声明"来自哪一段
    # 的尾帧"，等生成时再落地成真实文件路径。
    if not card.get("first_frame") and not card.get("first_frame_from"):
        err("`first_frame` 和 `first_frame_from` 至少要填一个")
    if card.get("first_frame") and card.get("first_frame_from"):
        warn(
            "`first_frame` 和 `first_frame_from` 同时有值，提交时用的是 "
            "`first_frame`；确认它就是 `first_frame_from` 指的那一帧"
        )
    if not card.get("first_frame") and card.get("first_frame_from"):
        warn(
            f"首帧还没落地，声明来自 `{card['first_frame_from']}`——必须先把上一段"
            "生成出来、抽出尾帧、把路径填回 `first_frame`，才能提交这一段"
        )

    if not (card.get("first_frame_state_zh") or "").strip():
        err(
            "`first_frame_state_zh` 为空。这个字段必填，而且必须在**实际看过首帧图**"
            "之后如实描述图里的状态——首帧是用 `--image PATH 0 1.0` 焊死的，"
            "如果节拍 1 描述的是首帧之前的动作，模型会在'照首帧'和'照文字'之间"
            "摆烂，表现为人物姿态不动、只有镜头在动（见 model_capability_ledger.md）"
        )

    # 保持不变的东西：I2V 通用五要素里的第 3 条，缺了模型就可能在中途改人/改景
    if not (card.get("preserve_en" if lang == "en" else "preserve_zh") or "").strip():
        warn(
            f"`preserve_{lang}` 为空。图生视频的通用五要素里有一条是"
            "**显式说明这一段里什么必须保持不变**（身份/服装/背景/构图）。"
            "首帧只锁住第 0 帧，后面几秒会不会换人换景，靠的是这句话。"
            "写成正向陈述，例如：her face, hairstyle and grey knit dress stay "
            "exactly as in the first frame; the room behind her keeps the same "
            "furniture, wall colour and window light"
        )

    fp = card.get("first_frame")
    if fp:
        path = fp if os.path.isabs(fp) else os.path.join(cards_root, fp) if not os.path.exists(fp) else fp
        if not os.path.exists(fp) and not os.path.exists(path):
            err(f"`first_frame` 指向的文件不存在: {fp}")
    lf = card.get("last_frame")
    if lf and not os.path.exists(lf):
        err(f"`last_frame` 指向的文件不存在: {lf}")

    beats = card.get("beats") or []
    if not beats:
        err("`beats` 为空，至少要有一个节拍")

    # --- 2. 否定词（正向提示词里不许出现否定句） ---------------------------
    cam = card.get("camera_en") or {}
    negation_targets = [
        ("camera_en.position", cam.get("position")),
        ("camera_en.rig", cam.get("rig")),
        ("camera_en.framing_path", cam.get("framing_path")),
        ("camera_en.move", cam.get("move")),
        ("subject_lock_en", card.get("subject_lock_en")),
        ("preserve_en", card.get("preserve_en")),
        ("style_tail_en", card.get("style_tail_en")),
    ]
    for i, b in enumerate(beats):
        negation_targets.append((f"beats[{i}].motion_en", b.get("motion_en")))
        negation_targets.append((f"beats[{i}].framing_en", b.get("framing_en")))
        negation_targets.append((f"beats[{i}].sfx_en", b.get("sfx_en")))
        if b.get("dialogue"):
            negation_targets.append(
                (f"beats[{i}].dialogue.delivery_en", b["dialogue"].get("delivery_en"))
            )
    if lang == "zh":
        cam_zh = card.get("camera_zh") or {}
        negation_targets += [
            ("camera_zh.rig", cam_zh.get("rig")),
            ("subject_lock_zh", card.get("subject_lock_zh")),
            ("preserve_zh", card.get("preserve_zh")),
            ("style_tail_zh", card.get("style_tail_zh")),
        ]
        for i, b in enumerate(beats):
            negation_targets.append((f"beats[{i}].motion_zh", b.get("motion_zh")))
            negation_targets.append((f"beats[{i}].framing_zh", b.get("framing_zh")))

    for field, text in negation_targets:
        hits = find_negations(text)
        if hits:
            err(
                f"`{field}` 含否定词 {sorted(set(hits))}。distilled pipeline 没有"
                "负面提示词参数，否定句只会把不想要的概念注入文本编码器——"
                "按 video_prompt_guide.md「否定→正向改写表」改写成正向陈述，"
                "改写不了的直接删掉"
            )

    # --- 3. 可见位移检验 ---------------------------------------------------
    extra_nouns = list(card.get("props_en") or [])
    extra_nouns = [w for prop in extra_nouns for w in re.findall(r"[A-Za-z]+", prop)]
    for i, b in enumerate(beats):
        motion = b.get("motion_en") if lang == "en" else b.get("motion_zh")
        if not (motion or "").strip():
            err(f"`beats[{i}].motion_en` 为空")
            continue
        if lang == "en" and not has_visible_motion(motion, extra_nouns):
            warn(
                f"`beats[{i}].motion_en` 里没找到任何身体部位/道具名词或运动动词，"
                "很可能只写了情绪形容（'he is angry and holds back'）而没写出"
                "会改变位置或形状的东西——实测这类欠描述会导致人物姿态焊死在首帧。"
                "道具名词可以加到卡的 `props_en` 里让这条检验认识它"
            )

    # --- 4. 台词：语言声明 + onscreen ---------------------------------------
    for i, b in enumerate(beats):
        dlg = b.get("dialogue")
        if not dlg:
            continue
        if not (dlg.get("text_zh") or "").strip():
            err(f"`beats[{i}].dialogue.text_zh` 为空（不说话的节拍请把 dialogue 设为 null）")
            continue
        delivery = (dlg.get("delivery_en") if lang == "en" else dlg.get("delivery_zh")) or ""
        if lang == "en":
            if "mandarin chinese" not in delivery.lower():
                err(
                    f"`beats[{i}].dialogue.delivery_en` 里没有 `Mandarin Chinese`。"
                    "实测确认：不显式声明目标语言时，模型会吐出非目标语种或语种混杂"
                    "的语音，即使引号里的台词本身就是中文（见 model_capability_ledger.md）"
                )
        else:
            if "中文" not in delivery and "普通话" not in delivery:
                err(
                    f"`beats[{i}].dialogue.delivery_zh` 里没有『中文』或『普通话』，"
                    "必须显式声明目标语言"
                )
        if not delivery.strip():
            err(f"`beats[{i}].dialogue.delivery_en` 为空")

    # --- 5. 时长 / 节拍预算 -------------------------------------------------
    duration = card.get("duration_sec")
    fps = card.get("fps", FPS_DEFAULT)
    if isinstance(duration, (int, float)) and duration > 0:
        # 节拍数上限（按分级取每节拍时长下限）
        spb = SECONDS_PER_BEAT_BY_TIER.get(card.get("tier"), SECONDS_PER_BEAT_DEFAULT)
        max_beats = min(MAX_BEATS, max(1, round(duration / spb)))
        if len(beats) > max_beats:
            err(
                f"{duration}s 的单元写了 {len(beats)} 个节拍，超过上限 {max_beats}"
                f"（分级 {card.get('tier')} 下每节拍至少 {spb}s，全局上限 {MAX_BEATS}）——"
                "节拍挤太密模型会把动作压缩变形，要么减节拍要么加时长/拆段"
            )

        # 节拍时间轴必须连续且铺满整个时长
        for i, b in enumerate(beats):
            t = b.get("t")
            if not (isinstance(t, list) and len(t) == 2):
                err(f"`beats[{i}].t` 必须是 [起, 止] 两个秒数")
                continue
            if t[1] <= t[0]:
                err(f"`beats[{i}].t` = {t} 的止点不大于起点")
        if all(isinstance(b.get("t"), list) and len(b["t"]) == 2 for b in beats):
            if abs(beats[0]["t"][0]) > 1e-6:
                err(f"第一个节拍的起点是 {beats[0]['t'][0]}，必须是 0")
            for i in range(len(beats) - 1):
                if abs(beats[i]["t"][1] - beats[i + 1]["t"][0]) > 1e-6:
                    err(
                        f"`beats[{i}].t[1]`={beats[i]['t'][1]} 和 "
                        f"`beats[{i+1}].t[0]`={beats[i+1]['t'][0]} 不连续，"
                        "节拍必须首尾相接铺满整个时长（时间窗还要喂 --retake）"
                    )
            if abs(beats[-1]["t"][1] - duration) > 0.1:
                err(
                    f"最后一个节拍止于 {beats[-1]['t'][1]}s，和 duration_sec="
                    f"{duration}s 不一致"
                )

            # 逐节拍核对台词念得完念不完
            for i, b in enumerate(beats):
                dlg = b.get("dialogue")
                if not dlg or not dlg.get("text_zh"):
                    continue
                need, chars = dialogue_min_duration(dlg["text_zh"], dlg.get("pace"))
                span = b["t"][1] - b["t"][0]
                if span + 1e-6 < need:
                    err(
                        f"`beats[{i}]` 的台词约 {chars} 字（语速档 "
                        f"{dlg.get('pace') or 'normal'}），至少需要 {need:.2f}s，"
                        f"但这个节拍只有 {span:.2f}s——实测时长不够时 LTX-2.5 会自己"
                        "总结/压缩台词（改措辞无效），必须加长节拍或拆段"
                    )

        # num_frames 必须是 8k+1，且和 duration_sec 对得上
        derived = nearest_8k_plus_1(round(duration * fps))
        declared = card.get("num_frames")
        if declared is not None and declared != derived:
            err(
                f"`num_frames`={declared} 和 duration_sec={duration}×{fps}fps 吸附出的"
                f"合法值 {derived} 不一致。删掉这个字段让脚本算，或者把 duration_sec "
                f"改成 {derived / fps:.4g}s"
            )
        if abs(derived / fps - duration) > 0.05:
            warn(
                f"duration_sec={duration}s 不是 8k+1 帧能精确表示的时长，"
                f"实际会按 {derived} 帧 ≈ {derived / fps:.2f}s 生成——"
                f"想避免歧义就把 duration_sec 改成 {derived / fps:.4g}"
            )

    # --- 6. 分辨率 / seed --------------------------------------------------
    for field in ("width", "height"):
        v = card.get(field)
        if isinstance(v, int) and v % 64 != 0:
            err(f"{field}={v} 不能被 64 整除（LTX-2.5 已知限制）")

    seed = card.get("seed")
    if seed == 10:
        err(
            "`seed`=10 正好是 LTX `--seed` 的默认值。留着这个值等于没指定 seed，"
            "重跑会原地复现同一个结果，让 loop 的换种子这条杠杆失效——换一个别的值"
        )

    # --- 6.5 机位溯源 + 运镜是否撑得起 --------------------------------------
    if not (card.get("scene_plate") or "").strip():
        warn(
            "`scene_plate` 为空。这个字段记这一单元的首帧是在哪张机位底板上合成的"
            "（抄分镜表「机位」列，如 `SC04_顾家别墅餐厅_B反打`）。缺了它，验收发现"
            "'这一镜视角不对'时无法溯源是不是底板传错了——而首帧被 strength 1.0 焊死，"
            "底板错了改提示词是没用的。历史上场景资产只有一个机位、73/73 条 job 都用"
            "同一张底板，整场戏从一个视角演完（见 model_capability_ledger.md A7）"
        )

    if not (cam.get("position") or "").strip() and lang == "en":
        warn(
            "`camera_en.position` 为空。这一句是告诉模型相机站在场景的哪个位置往哪看"
            "（从 `scenes.md` 的「空间关系」块翻译），和 `camera_en.rig`（固定/手持、"
            "机高）分工不同，别混在一起写"
        )

    # 摇/移需要画外的像素，单张场景底板一般没有——这是物理限制不是风格问题
    move_text = (cam.get("move") or "") + " " + " ".join(
        (b.get("framing_en") or "") for b in beats
    )
    PAN_WORDS = ("pan", "pans", "panning", "track", "tracks", "tracking",
                 "dolly sideways", "truck", "trucks", "whip")
    hit = [w for w in PAN_WORDS if re.search(r"\b" + re.escape(w) + r"\b", move_text.lower())]
    if hit:
        warn(
            f"运镜里写了平移类动作 {sorted(set(hit))}。**摇/移本质是平移，需要画外的"
            "像素**，而单张场景底板一般没有——底板右边什么都没有时，'镜头向右摇露出门口'"
            "是注定失败的一镜（模型不会现编，它会保持不动）。确认这张底板那个方向真的"
            "有像素可以移进来，否则改成推/拉（缩放，单张底板撑得起），或者拆成两镜切机位。"
            "见 video_prompt_guide.md「哪些运镜是这张底板撑得起的」"
        )

    # 「锁死机位」和「运镜」是互斥指令，不能同时出现在同一段提示词里
    STATIC_RIG_WORDS = ("locked off", "locked-off", "static camera", "stationary",
                        "holds absolutely still", "holds still", "does not move",
                        "fixed camera", "固定机位", "锁死")
    static_text = " ".join(
        (cam.get(k) or "") for k in ("position", "rig", "framing_path")
    ).lower()
    move_declared = (cam.get("move") or "").strip()
    static_hit = [w for w in STATIC_RIG_WORDS if w in static_text]
    if static_hit and move_declared:
        err(
            f"`camera_en` 里同时写了锁死机位 {sorted(set(static_hit))} 和运镜 "
            f"`{move_declared[:50]}…`——这是两条互斥指令。装配出来的提示词会变成 "
            "'The camera is locked off at eye level. … a slow push-in …'，"
            "模型照哪条都不奇怪，实测表现就是运镜做不出来。有运镜的镜头，"
            "`rig` 只写机高和载具（`The camera rides a slow dolly at eye level, "
            "about 1.5 metres up`），'不动'这层意思交给 `move` 留空来表达，"
            "不要在 `rig` 里再写一遍"
        )

    # 运镜和「背景逐项保持不变」同样互斥：推镜必然改变背景的尺度和构图
    if move_declared:
        preserve_text = (
            card.get("preserve_en" if lang == "en" else "preserve_zh") or ""
        ).lower()
        FREEZE_WORDS = ("stay unchanged", "stays unchanged", "keeps the same",
                        "keep the same", "remains identical", "remain identical",
                        "保持不变", "完全一致")
        freeze_hit = [w for w in FREEZE_WORDS if w in preserve_text]
        if freeze_hit:
            warn(
                f"这一镜有运镜，而 `preserve_{lang}` 里写了 {sorted(set(freeze_hit))}。"
                "确认这些'不变'只管身份（脸/发型/服装）和'还是同一个地点'，"
                "**不要逐项点名背景元素要求它保持不变**——推镜必然改变背景的尺度和构图，"
                "两条指令打架。背景被逐项冻结是 A6『背景像素级冻住』的可疑成因之一，"
                "见 model_capability_ledger.md A6 / D4"
            )

    ffs = card.get("first_frame_strength")
    if ffs is not None:
        if not isinstance(ffs, (int, float)) or not (0 < ffs <= 1.0):
            err(f"`first_frame_strength`={ffs} 必须是 (0, 1.0] 区间的数")
        elif ffs < 1.0:
            warn(
                f"`first_frame_strength`={ffs} 低于默认值 1.0。这条路**本仓库还没实测**"
                "（见 model_capability_ledger.md D4）：预期能让背景松动、允许视差和真实"
                "运镜，代价是首帧保真度下降（人脸/服装漂移）。先小范围 A/B 确认，"
                "不要直接批量用；跑完把结论写回 ledger D4"
            )

    # --- 7. 已知做不到的项必须先做降级决定 ----------------------------------
    if card.get("known_limit") is not None:
        kl = card["known_limit"]
        if not isinstance(kl, dict) or not kl.get("decision"):
            err(
                "`known_limit` 有值但缺 `decision`。命中 model_capability_ledger.md 里"
                "『已验证做不到』的项时，必须先写降级决定（接受现状 / 降级成无台词"
                "表情镜 / 换 pipeline），不要让 loop 空烧 3 轮 GPU 去撞已知的墙"
            )

    # --- 8. 分段单元的接续关系 ---------------------------------------------
    unit_of = card.get("unit_of")
    if unit_of and card.get("unit_index"):
        idx = card["unit_index"]
        if not (isinstance(idx, list) and len(idx) == 2):
            err("`unit_index` 必须是 [第几段, 共几段]")
        else:
            n, total = idx
            siblings = cards_by_unit.get(unit_of, [])
            if len(siblings) != total:
                err(
                    f"`unit_index` 说这个分镜共 {total} 段，但本文件里 unit_of="
                    f"{unit_of} 的卡只有 {len(siblings)} 张"
                )
            if n > 1 and not (card.get("first_frame") or card.get("first_frame_from")):
                err("非第一段必须有 first_frame 或 first_frame_from（用上一段的尾帧）")
            if n > 1:
                prev = next(
                    (c for c in siblings if (c.get("unit_index") or [None])[0] == n - 1),
                    None,
                )
                if prev is None:
                    err(f"找不到第 {n - 1} 段的卡，分段序号不连续")

    # --- 9. 装配结果层面的检查 ---------------------------------------------
    prompt = build_prompt(card, lang)

    # 语言分工：CJK 只允许出现在台词引号内
    if lang == "en":
        stripped = prompt
        for b in beats:
            dlg = b.get("dialogue")
            if dlg and dlg.get("text_zh"):
                stripped = stripped.replace(dlg["text_zh"], "")
        leftover = sorted(set(_CJK_RE.findall(stripped)))
        if leftover:
            err(
                f"装配出的提示词里有台词之外的中文字符 {''.join(leftover[:20])}"
                f"{'…' if len(leftover) > 20 else ''}。`--lang en` 下正文必须全英文，"
                "中文只允许出现在 `dialogue.text_zh` 的引号里——检查是不是有 `*_en` "
                "字段被填了中文"
            )

    if tokenizer is not None:
        n_tokens = exact_tokens(prompt, tokenizer)
        how = "精确"
    else:
        n_tokens = estimate_tokens(prompt)
        how = "估算"

    if n_tokens > TOKEN_BUDGET:
        err(
            f"提示词 {how} {n_tokens} token，超过工作预算 {TOKEN_BUDGET}"
            f"（Gemma 文本编码器硬上限 {TOKEN_HARD_LIMIT}，**超了静默截尾**，"
            "会悄悄丢掉排在最后的内容）——精简节拍描述或拆段"
        )
    elif n_tokens > TOKEN_BUDGET * 0.85:
        warn(f"提示词 {how} {n_tokens} token，已经接近预算 {TOKEN_BUDGET}")

    return errors, warnings, prompt, n_tokens


# ---------------------------------------------------------------------------
# 产出
# ---------------------------------------------------------------------------

def card_to_job(card, prompt, lang):
    fps = card.get("fps", FPS_DEFAULT)
    num_frames = card.get("num_frames") or nearest_8k_plus_1(
        round(float(card["duration_sec"]) * fps)
    )
    lines = [
        f'{(b["dialogue"].get("speaker") or "").strip()}："{b["dialogue"]["text_zh"]}"'.lstrip("：")
        for b in (card.get("beats") or [])
        if b.get("dialogue") and b["dialogue"].get("text_zh")
    ]
    return {
        "id": card["id"],
        "shot_no": card["shot_no"],
        "scene": card["scene"],
        "shot_card_id": card["id"],
        "scene_plate": card.get("scene_plate"),
        "prompt_lang": lang,
        "first_frame": card.get("first_frame"),
        "first_frame_strength": card.get("first_frame_strength", 1.0),
        "first_frame_from": card.get("first_frame_from"),
        "last_frame": card.get("last_frame"),
        "ref_images": [],
        "dialogue": " / ".join(lines),
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT_ARCHIVAL,
        "duration_sec": round(num_frames / fps, 4),
        "fps": fps,
        "num_frames": num_frames,
        "aspect_ratio": aspect_ratio_str(card.get("width"), card.get("height")),
        "width": card.get("width"),
        "height": card.get("height"),
        "seed": card.get("seed"),
        "platform_recommend": ["LTX-2.5 (self-hosted)"],
        "notes": card.get("notes", ""),
    }


def main():
    ap = argparse.ArgumentParser(
        description="镜头卡 → LTX-2.5 提示词 / video_jobs.json（提示词是派生产物，不手写）"
    )
    ap.add_argument("cards", help="shot_cards.json 路径")
    ap.add_argument("-o", "--out", help="写出 video_jobs.json 的路径")
    ap.add_argument("--lint", action="store_true", help="只校验并打印装配结果，不写文件")
    ap.add_argument("--emit-prompts", metavar="DIR", help="把每张卡的提示词单独写成 txt")
    ap.add_argument("--only", nargs="+", metavar="ID", help="只处理这些卡 id")
    ap.add_argument("--lang", choices=["en", "zh"], default="en",
                    help="提示词正文语言，默认 en（英文正文 + 中文台词）")
    ap.add_argument("--tokenizer", help="Gemma tokenizer 路径或 repo id，用于精确数 token")
    args = ap.parse_args()

    with open(args.cards, encoding="utf-8") as f:
        cards = json.load(f)
    if not isinstance(cards, list):
        sys.exit("shot_cards.json 顶层必须是一个数组")

    cards_root = os.path.dirname(os.path.abspath(args.cards))
    tokenizer = load_tokenizer(args.tokenizer) if args.tokenizer else None

    cards_by_unit = {}
    for c in cards:
        if c.get("unit_of"):
            cards_by_unit.setdefault(c["unit_of"], []).append(c)

    selected = [c for c in cards if not args.only or c.get("id") in args.only]
    if args.only and not selected:
        sys.exit(f"--only 指定的 id 在文件里都找不到: {args.only}")

    all_errors, all_warnings, jobs = [], [], []
    for i, card in enumerate(selected):
        errors, warnings, prompt, n_tokens = check_card(
            card, i, args.lang, tokenizer, cards_by_unit, cards_root
        )
        all_errors += errors
        all_warnings += warnings
        jobs.append(card_to_job(card, prompt, args.lang))

        if args.lint or args.emit_prompts:
            print(f"\n{'=' * 70}\n{card.get('id', f'index_{i}')}  "
                  f"({card.get('duration_sec')}s, {len(card.get('beats') or [])} 拍, "
                  f"{'精确' if tokenizer else '估算'} {n_tokens} token)\n{'=' * 70}")
            print(prompt)

        if args.emit_prompts:
            os.makedirs(args.emit_prompts, exist_ok=True)
            out = os.path.join(args.emit_prompts, f"{card['id']}.txt")
            with open(out, "w", encoding="utf-8") as f:
                f.write(prompt + "\n")

    print(f"\n共处理 {len(selected)} 张镜头卡（正文语言 {args.lang}）")

    if all_warnings:
        print(f"\n{len(all_warnings)} 条提示（不阻塞，建议人工确认）:")
        for w in all_warnings:
            print(f"  WARN: {w}")

    if all_errors:
        print(f"\n{len(all_errors)} 条错误（必须处理）:")
        for e in all_errors:
            print(f"  ERROR: {e}")
        sys.exit(1)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"\n已写出 {len(jobs)} 条 job → {args.out}")
    elif not args.lint and not args.emit_prompts:
        print("\n（没指定 -o / --lint / --emit-prompts，什么都没写出）")

    if not all_errors:
        print("未发现阻塞性问题。")


if __name__ == "__main__":
    main()
