#!/usr/bin/env python3
"""校验 video_jobs.json 是不是能被 ltx_ssh_submit.py 直接消费。

只做本地静态检查，不连接远程机器、不调用任何生成 API：
- 必填字段是否齐全（id/shot_no/scene/first_frame/prompt/negative_prompt/
  duration_sec/aspect_ratio/platform_recommend/width/height）。
- first_frame/last_frame/ref_images 引用的文件是否在本地磁盘真实存在
  （相对路径按运行时的当前工作目录解析，约定从仓库根目录运行）。
- width/height 是否能被 64 整除（LTX-2.5 的已知限制，见
  short-drama-ltx-generate/references/ltx_pipeline_gotchas.md）。
- aspect_ratio 字段跟实际 width/height 的比例是否吻合（防止漏填/传错
  分辨率导致悄悄退回 pipeline 默认横屏 1536×1024，见
  short-drama-ltx-generate/references/ltx_pipeline_gotchas.md
  "生成质量丢分的三大常见诱因"第 1 条）。
- num_frames 如果手动填了，是否满足 8*k+1；不满足的话
  ltx_ssh_submit.py 会静默吸附成最近的合法值，跟手填的原意可能不一致。
- prompt/negative_prompt 里是否残留常见占位符文本，提示尚未真正展开。
- dialogue 非空时，prompt 里有没有显式的语言声明（`Mandarin Chinese`/中文/
  普通话）。不声明语言时实测出现过角色说英文或语种混杂，即使台词本身是中文；
  历史上《出狱后》ep01 有台词的 15 镜里"中文"出现 0 次，规则确立后从未回填，
  也没有任何校验——这一条就是补上那个缺口，见
  short-drama-video-gen/references/model_capability_ledger.md B4。
- seed 是否填了、以及是不是留成了 LTX `--seed` 的默认值 10。留成默认值等于
  没指定，不改提示词重跑会原地复现，"换种子再试一次"这条杠杆完全失效
  （历史上 ep01 缺 9/22、ep02 缺 19/19），见 ledger B3。
- prompt 的 token 估算有没有超过工作预算。Gemma 文本编码器上限 1024 token，
  **超了静默截尾**，丢掉的正是排在最后的内容，见 ledger B2。
- prompt 里有没有残留否定句（`避免/禁止/不要`、`no/not/without/avoid`…）。
  distilled pipeline **没有 --negative-prompt 参数**，否定句只会把不想要的
  概念注入文本编码器，见 ledger B1。
- prompt 是不是还和镜头卡装配结果一致（同目录有 shot_cards.json 且 job 带
  shot_card_id 时才查）。防止有人手改了 video_jobs.json 绕过镜头卡——手改的
  内容下次装配就会被冲掉。
- dialogue 非空时，duration_sec 是否够台词按合理语速念完（人工审查
  2026-09 实测确认的真实故障：时长不够时 LTX-2.5 会自己总结/压缩台词）。
  按台词字数（只数引号内正文，排除说话人标注）估算：低于"最快语速(6字/秒)
  也不够"的下限报 ERROR，低于"正常语速(4字/秒)"下限报 WARN，公式细节见
  short-drama-video-gen/references/video_prompt_guide.md"台词时长计算"。
  这是启发式估算，语气很快/很慢的台词可能需要人工判断是否是误报。

用法:
  python3 validate_video_jobs.py <video_jobs.json>

退出码非 0 表示存在需要人工处理的问题，退出码 0 但仍可能有 WARN 级提示。
"""

import json
import os
import re
import sys

# 复用 short-drama-video-gen 的装配/校验实现，不在这里重复一套阈值和词表——
# token 估算系数、否定词表、装配模板只应该有一个来源。
_BUILD_PROMPT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "short-drama-video-gen", "scripts",
)
sys.path.insert(0, os.path.normpath(_BUILD_PROMPT_DIR))
try:
    import build_prompt as bp
except ImportError:  # pragma: no cover
    sys.exit(
        "找不到 short-drama-video-gen/scripts/build_prompt.py。这个校验脚本"
        "依赖它提供 token 估算、否定词表和提示词装配逻辑，请确认两个 skill "
        f"目录都在（找过: {os.path.normpath(_BUILD_PROMPT_DIR)}）"
    )

REQUIRED_FIELDS = [
    "id",
    "shot_no",
    "scene",
    "first_frame",
    "prompt",
    "negative_prompt",
    "duration_sec",
    "aspect_ratio",
    "platform_recommend",
    "width",
    "height",
]

PLACEHOLDER_MARKERS = [
    "TODO",
    "(完整正向提示词)",
    "（完整正向提示词）",
    "(完整负面提示词)",
    "（完整负面提示词）",
    "占位",
    "待补充",
]

# 跟 ltx_ssh_submit.py 的 _nearest_8k_plus_1 保持同一个吸附算法，方便在
# 校验阶段就提前告诉用户手填的 num_frames 最终会被吸附成什么值。
def _nearest_8k_plus_1(n):
    k = max(round((n - 1) / 8), 0)
    return 8 * k + 1


_CJK_RE = re.compile(r"[一-鿿]")
_QUOTED_RE = re.compile(r"[“”\"]([^“”\"]+)[“”\"]")


def _dialogue_char_count(dialogue_text):
    """粗略估算台词正文字数：只数引号内的内容（排除说话人姓名/舞台提示，
    比如"苏慧（拉衣角，使眼色）："这部分不算），且只数中文字符，不算标点。
    多段台词（同一镜多人对话）字数相加。找不到引号就退化为整段估算。"""
    if not dialogue_text:
        return 0
    quoted = _QUOTED_RE.findall(dialogue_text)
    spans = quoted if quoted else [dialogue_text]
    return sum(len(_CJK_RE.findall(span)) for span in spans)


def _min_duration_for_dialogue(char_count):
    """按字数估算最低时长：(最快语速6字/秒下限, 正常语速4字/秒下限)。
    公式和缓冲量跟 video_prompt_guide.md「台词时长计算」保持一致。"""
    if char_count <= 0:
        return 0.0, 0.0
    fastest = char_count / 6.0 + 0.6
    normal = char_count / 4.0 + 0.8
    return fastest, normal


def _parse_aspect_ratio(aspect_ratio):
    """把 "9:16" 这种字符串解析成 width/height 比例；解析不了返回 None。"""
    try:
        w_str, h_str = str(aspect_ratio).split(":")
        w, h = float(w_str), float(h_str)
        if h == 0:
            return None
        return w / h
    except (ValueError, AttributeError):
        return None


_LANG_DECLARATIONS = ("mandarin chinese", "中文", "普通话")


def _load_shot_cards(jobs_path):
    """同目录下有 shot_cards.json 就读进来，按 id 建索引，用于"prompt 是不是
    还和镜头卡对得上"这条检查。没有就返回空 dict（老项目没有卡，跳过这条）。"""
    cards_path = os.path.join(os.path.dirname(os.path.abspath(jobs_path)), "shot_cards.json")
    if not os.path.exists(cards_path):
        return {}
    try:
        with open(cards_path, encoding="utf-8") as f:
            cards = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(cards, list):
        return {}
    return {c["id"]: c for c in cards if isinstance(c, dict) and c.get("id")}


def check_job(job, index, cards=None):
    errors = []
    warnings = []
    label = job.get("id", f"index_{index}")
    cards = cards or {}

    for field in REQUIRED_FIELDS:
        if job.get(field) in (None, ""):
            errors.append(f"[{label}] 缺少必填字段 `{field}`")

    for path_field in ("first_frame", "last_frame"):
        path = job.get(path_field)
        if path and not os.path.exists(path):
            errors.append(f"[{label}] `{path_field}` 指向的文件不存在: {path}")

    for i, ref in enumerate(job.get("ref_images") or []):
        if not os.path.exists(ref):
            errors.append(f"[{label}] `ref_images[{i}]` 指向的文件不存在: {ref}")

    width, height = job.get("width"), job.get("height")
    if isinstance(width, int) and width % 64 != 0:
        errors.append(f"[{label}] width={width} 不能被 64 整除")
    if isinstance(height, int) and height % 64 != 0:
        errors.append(f"[{label}] height={height} 不能被 64 整除")

    if isinstance(width, int) and isinstance(height, int) and height:
        expected_ratio = _parse_aspect_ratio(job.get("aspect_ratio"))
        if expected_ratio:
            actual_ratio = width / height
            # 容忍度放宽到 15%：现有测试档/正式档预设里最接近 9:16 的
            # 704x1280（0.55）跟精确 0.5625 差约 2%，留足空间不误报；但
            # 横屏 1536x1024（1.5）跟 9:16 目标（0.5625）差 167%，稳稳落在
            # 阈值外，正是要拦的那种"漏填/退回默认值"场景。
            if abs(actual_ratio - expected_ratio) / expected_ratio > 0.15:
                errors.append(
                    f"[{label}] width×height={width}×{height}（实际比例"
                    f"{actual_ratio:.3f}）跟 aspect_ratio={job.get('aspect_ratio')}"
                    f"（目标比例 {expected_ratio:.3f}）明显不符，很可能是漏填/"
                    "传错了分辨率（比如悄悄退回了 pipeline 默认横屏 1536×1024）"
                )

    for text_field in ("prompt", "negative_prompt"):
        text = job.get(text_field) or ""
        for marker in PLACEHOLDER_MARKERS:
            if marker in text:
                errors.append(
                    f"[{label}] `{text_field}` 里残留占位符文本 `{marker}`，看起来没有真正展开"
                )

    num_frames = job.get("num_frames")
    if num_frames is None:
        fps = job.get("fps", 24)
        est = round(job.get("duration_sec", 0) * fps) if job.get("duration_sec") else None
        warnings.append(
            f"[{label}] 未显式指定 num_frames，ltx_ssh_submit.py 会按 duration_sec×{fps}fps"
            f"（≈{est} 帧）自动估算，确认这符合预期"
        )
    elif isinstance(num_frames, int) and (num_frames - 1) % 8 != 0:
        snapped = _nearest_8k_plus_1(num_frames)
        warnings.append(
            f"[{label}] num_frames={num_frames} 不满足 LTX 要求的 8k+1，"
            f"ltx_ssh_submit.py 提交时会静默吸附成 {snapped}——如果这一镜是靠精确"
            "num_frames 卡某个动作节拍，确认吸附后的值还符合预期，或者直接在这里"
            f"改成 {snapped} 避免歧义"
        )

    if job.get("dialogue"):
        for text_field in ("prompt", "negative_prompt"):
            if job["dialogue"] in (job.get(text_field) or ""):
                warnings.append(
                    f"[{label}] `dialogue` 的文本原样出现在 `{text_field}` 里，"
                    "确认不是把台词误塞进了提示词（dialogue 只应是参考信息）"
                )

        char_count = _dialogue_char_count(job["dialogue"])
        duration = job.get("duration_sec")
        if char_count > 0 and isinstance(duration, (int, float)):
            min_fastest, min_normal = _min_duration_for_dialogue(char_count)
            if duration < min_fastest:
                errors.append(
                    f"[{label}] 台词约 {char_count} 字，duration_sec={duration}s 明显"
                    f"不够（即使按最快语速 6字/秒估算也至少需要 {min_fastest:.1f}s）——"
                    "人工审查实测确认时长不够时 LTX-2.5 会自己总结/压缩台词，需要加长"
                    "duration_sec 或按 stability_playbook.md 拆成分段生成，见"
                    "video_prompt_guide.md「台词时长计算」"
                )
            elif duration < min_normal:
                warnings.append(
                    f"[{label}] 台词约 {char_count} 字，duration_sec={duration}s 按"
                    f"正常语速(4字/秒)估算偏短（建议≥{min_normal:.1f}s），除非这段台词"
                    "本来就是急促/快速语气，否则确认是否需要加长"
                )

    # --- 台词语言声明（ledger B4） ---
    prompt_text = job.get("prompt") or ""
    if job.get("dialogue"):
        lowered = prompt_text.lower()
        if not any(d in lowered for d in _LANG_DECLARATIONS):
            errors.append(
                f"[{label}] 这一镜有台词，但 `prompt` 里没有任何语言声明"
                "（`Mandarin Chinese` / 中文 / 普通话）。实测确认：不显式声明"
                "目标语言时模型会吐出非目标语种或语种混杂的语音，即使引号里的"
                "台词本身就是中文——见 model_capability_ledger.md B4"
            )

    # --- seed（ledger B3） ---
    if job.get("seed") is None:
        errors.append(
            f"[{label}] 缺 `seed`。LTX `--seed` 的默认值是固定的 10，不指定"
            "等于每次都跑同一个结果，不改提示词重跑会原地复现，"
            "『换种子再试一次』这条杠杆完全失效——见 ledger B3"
        )
    elif job.get("seed") == 10:
        errors.append(
            f"[{label}] `seed`=10 正好是 LTX `--seed` 的默认值，留着等于没指定，"
            "换一个别的值"
        )

    # --- token 预算（ledger B2） ---
    if prompt_text:
        n_tokens = bp.estimate_tokens(prompt_text)
        if n_tokens > bp.TOKEN_BUDGET:
            errors.append(
                f"[{label}] `prompt` 估算 {n_tokens} token，超过工作预算 "
                f"{bp.TOKEN_BUDGET}（Gemma 文本编码器硬上限 "
                f"{bp.TOKEN_HARD_LIMIT}，**超了静默截尾**，会悄悄丢掉排在最后"
                "的内容）——精简节拍描述或把这一镜拆段"
            )
        elif n_tokens > bp.TOKEN_BUDGET * 0.85:
            warnings.append(
                f"[{label}] `prompt` 估算 {n_tokens} token，已接近预算 "
                f"{bp.TOKEN_BUDGET}"
            )

    # --- prompt 里的否定句（ledger B1） ---
    negations = bp.find_negations(prompt_text)
    if negations:
        errors.append(
            f"[{label}] `prompt` 里含否定词 {sorted(set(negations))}。"
            "ltx_pipelines.distilled 没有 --negative-prompt 参数，写进正向"
            "提示词的否定句只会把不想要的概念注入文本编码器——按 "
            "video_prompt_guide.md「否定→正向改写表」改写成正向陈述，"
            "改写不了的直接删掉"
        )

    # --- negative_prompt 是死字段（ledger B1） ---
    neg = job.get("negative_prompt") or ""
    if neg and "没有 --negative-prompt 参数" not in neg:
        warnings.append(
            f"[{label}] `negative_prompt` 写了实际内容，但这个参数在 "
            "ltx_pipelines.distilled 上**根本不存在**，字符串永远不会被发送"
            "（历史上为它白烧过 3 轮 GPU）。想排除的东西要改写成正向陈述写进"
            "`prompt`，这个字段只留存档说明"
        )

    # --- prompt 是不是还和镜头卡对得上 ---
    card = cards.get(job.get("shot_card_id"))
    if card is not None:
        try:
            expected = bp.build_prompt(card, job.get("prompt_lang") or "en")
        except (KeyError, TypeError):
            expected = None
        if expected is not None and expected.strip() != prompt_text.strip():
            errors.append(
                f"[{label}] `prompt` 和镜头卡 `{job['shot_card_id']}` 的装配结果"
                "不一致——说明有人手改了 video_jobs.json。改提示词要回去改卡的"
                "字段再重跑 build_prompt.py，手改的内容下次装配会被冲掉"
            )

    return errors, warnings


def main():
    if len(sys.argv) != 2:
        sys.exit(f"用法: python3 {sys.argv[0]} <video_jobs.json>")

    jobs_path = sys.argv[1]
    with open(jobs_path, encoding="utf-8") as f:
        jobs = json.load(f)

    if not isinstance(jobs, list):
        sys.exit("video_jobs.json 顶层必须是一个数组")

    cards = _load_shot_cards(jobs_path)
    if cards:
        print(f"（同目录找到 shot_cards.json，{len(cards)} 张卡，会核对 prompt 是否一致）")

    all_errors = []
    all_warnings = []
    for i, job in enumerate(jobs):
        errors, warnings = check_job(job, i, cards)
        all_errors += errors
        all_warnings += warnings

    print(f"共校验 {len(jobs)} 条 job")

    if all_warnings:
        print(f"\n{len(all_warnings)} 条提示（不阻塞，建议人工确认）:")
        for w in all_warnings:
            print(f"  WARN: {w}")

    if all_errors:
        print(f"\n{len(all_errors)} 条错误（必须处理才能提交）:")
        for e in all_errors:
            print(f"  ERROR: {e}")
        sys.exit(1)

    print("\n未发现阻塞性问题，可以进入 ltx_ssh_submit.py --dry-run 验证。")


if __name__ == "__main__":
    main()
