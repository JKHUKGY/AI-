#!/usr/bin/env python3
"""L2 升级的管道：改关键帧卡 → 重出图 → 回填首帧 → 重装配视频 job。

**这个脚本管的是"链"，不是"判断"。** 该不该升级、要改哪个字段，由
`references/keyframe_escalation_guide.md` 的路由表决定（人或 Reviewer agent
判断）；这个脚本只保证判断做出之后，那几步不会漏做、不会做错顺序。

它存在的唯一理由：**回填时重写 first_frame_state_zh 这一步太容易漏**。
漏了就是新首帧配旧节拍，节拍描述的动作在新图里已经发生完了，
成片表现为"人物不动、只有镜头在动"（ledger A3）。我们在这个坑里
已经栽过 17 次（第一批 16 镜栽 7 次、第二批 19 镜栽 10 次），
所以这一步被做成了**脚本会拦你的硬闸门**，不是提醒。

用法:
    # 1) 先看这一镜现在长什么样、会改动哪些文件（不写任何东西）
    python3 rekey_shot.py --shot ep01_镜24 \
      --keyframe-dir output/<剧>/keyframes/ep01 \
      --video-dir output/<剧>/videos/ep01 --plan

    # 2) 应用字段补丁并重新装配关键帧提示词（还不出图）
    python3 rekey_shot.py --shot ep01_镜24 ... \
      --patch 'people[顾瑶].posture_zh=整个人半躺着陷在沙发里，一条小腿架在扶手上' \
      --rebuild-keyframe-prompt

    # 3) 出图（真的调 Codex CLI）
    python3 rekey_shot.py --shot ep01_镜24 ... --generate

    # 4) 看完图、选定某一版之后回填，并重装配视频 job
    #    --state 是必填的：必须是你**实际打开新图看过之后**写的描述
    python3 rekey_shot.py --shot ep01_镜24 ... \
      --adopt output/<剧>/keyframes/ep01/ep01_镜24/ep01_镜24_02.png \
      --state '实际看图确认：顾瑶半躺、小腿架在扶手上，两人都没抬头…' \
      --model ltx-2.5

`--patch` 可以给多次。路径语法：
    framing.crop_zh=...              嵌套字段
    people[顾瑶].posture_zh=...      按 name 定位 people 数组里的某个人
    props_zh=["深色硬壳拉杆箱"]        值以 [ 或 { 开头时按 JSON 解析
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent.parent
BUILD_KEYFRAME = SKILLS / "short-drama-keyframe-gen" / "scripts" / "build_keyframe_prompt.py"
GENERATE_IMAGES = SKILLS / "short-drama-image-gen" / "scripts" / "generate_images.py"
BUILD_LTX = SKILLS / "short-drama-video-gen" / "scripts" / "build_prompt.py"
BUILD_H3 = SKILLS / "short-drama-video-gen" / "scripts" / "build_h3_prompt.py"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def find_card(cards, shot_id):
    for c in cards:
        if c.get("id") == shot_id:
            return c
    return None


def apply_patch(card, path, raw_value):
    """把 'people[顾瑶].posture_zh=新值' 这种补丁打进卡里。"""
    value = raw_value
    if raw_value[:1] in "[{":
        value = json.loads(raw_value)

    parts = path.split(".")
    node = card
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        m = re.match(r"^(\w+)\[([^\]]+)\]$", part)
        if m:                                   # people[顾瑶]
            key, who = m.group(1), m.group(2)
            arr = node.get(key)
            if not isinstance(arr, list):
                sys.exit(f"补丁路径 {path!r}: {key} 不是数组")
            hit = next((x for x in arr if x.get("name") == who), None)
            if hit is None:
                names = [x.get("name") for x in arr]
                sys.exit(f"补丁路径 {path!r}: {key} 里没有 name={who!r}，现有: {names}")
            node = hit
        elif last:
            if part not in node:
                print(f"  [注意] 字段 {path} 原来不存在，按新增处理")
            node[part] = value
            return
        else:
            node = node.setdefault(part, {})
    sys.exit(f"补丁路径 {path!r} 解析失败")


def run(cmd, why):
    print(f"\n>>> {why}\n    {' '.join(str(x) for x in cmd)}", flush=True)
    r = subprocess.run([str(x) for x in cmd])
    if r.returncode != 0:
        sys.exit(f"这一步失败了（退出码 {r.returncode}），链条停在这里，"
                 f"后面的步骤没有执行——先把这个错处理掉再继续")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shot", required=True, help="镜头 id，如 ep01_镜24")
    ap.add_argument("--keyframe-dir", required=True, help="keyframes/ep0X 目录")
    ap.add_argument("--video-dir", required=True, help="videos/ep0X 目录")
    ap.add_argument("--root", default=os.getcwd(), help="仓库根目录")
    ap.add_argument("--patch", action="append", default=[], metavar="路径=值",
                    help="改关键帧卡的字段，可给多次")
    ap.add_argument("--plan", action="store_true", help="只打印现状和将要动的文件")
    ap.add_argument("--rebuild-keyframe-prompt", action="store_true",
                    help="应用补丁并重跑 build_keyframe_prompt.py")
    ap.add_argument("--generate", action="store_true", help="真的调 Codex CLI 出图")
    ap.add_argument("--adopt", metavar="PNG", help="选定这一版新图，回填进 shot_cards.json")
    ap.add_argument("--state", metavar="中文描述",
                    help="新首帧的真实状态（--adopt 时必填，必须是实际看图之后写的）")
    ap.add_argument("--model", choices=["ltx-2.5", "minimax-h3"], default="ltx-2.5")
    args = ap.parse_args()

    kf_cards_p = Path(args.keyframe_dir) / "keyframe_cards.json"
    shot_cards_p = Path(args.video_dir) / "shot_cards.json"
    for p in (kf_cards_p, shot_cards_p):
        if not p.exists():
            sys.exit(f"找不到 {p}")

    kf_cards = load(kf_cards_p)
    shot_cards = load(shot_cards_p)

    # 镜头卡的 id 可能带拆段后缀（ep01_镜17_u1），关键帧卡是按镜号来的
    base_id = re.sub(r"_u\d+$", "", args.shot)
    kf = find_card(kf_cards, base_id)
    if kf is None:
        sys.exit(f"关键帧卡里没有 {base_id}")

    # --------------------------------------------------------- plan
    if args.plan:
        print(f"=== {args.shot}（关键帧卡 {base_id}）===")
        print(f"底板  : {kf.get('plate_id')}")
        fr = kf.get("framing") or {}
        print(f"景别  : {fr.get('shot_size')} | 裁切: {fr.get('crop_zh')}")
        for pp in kf.get("people") or []:
            print(f"人物  : {pp.get('name')} | x={pp.get('pos_x')} depth={pp.get('depth')} "
                  f"| {pp.get('body_dir')}/{pp.get('camera_relation')} | 视线 {pp.get('gaze_at')}")
        sc = find_card(shot_cards, args.shot)
        if sc:
            print(f"当前首帧: {sc.get('first_frame')}")
            print(f"首帧状态: {(sc.get('first_frame_state_zh') or '')[:120]}…")
        ep_name = Path(args.keyframe_dir).name
        print("\n升级会动这些文件:")
        for f in (kf_cards_p,
                  Path(args.keyframe_dir) / f"keyframe_prompts_{ep_name}.md",
                  shot_cards_p,
                  Path(args.video_dir) / ("video_jobs.json" if args.model == "ltx-2.5"
                                          else "h3_jobs.json")):
            print(f"  {f}")
        return

    ep = Path(args.keyframe_dir).name
    jobs_p = Path(args.keyframe_dir) / f"jobs_{ep}_rekey_{base_id}.json"

    # --------------------------------------------------------- 打补丁 + 重装配
    if args.patch or args.rebuild_keyframe_prompt:
        for pt in args.patch:
            if "=" not in pt:
                sys.exit(f"--patch 要写成 路径=值，收到: {pt!r}")
            path, val = pt.split("=", 1)
            print(f"  打补丁 {path}")
            apply_patch(kf, path, val)
        if args.patch:
            dump(kf_cards_p, kf_cards)
            print(f"关键帧卡已更新: {kf_cards_p}")

        run([sys.executable, BUILD_KEYFRAME, kf_cards_p, "--only", base_id,
             "-o", jobs_p, "--root", args.root],
            "重新装配关键帧提示词（提示词是派生产物，不手改）")

    # --------------------------------------------------------- 出图
    if args.generate:
        if not jobs_p.exists():
            sys.exit(f"没有 {jobs_p}，先跑 --rebuild-keyframe-prompt")
        run([sys.executable, GENERATE_IMAGES, jobs_p, "--out-dir", args.keyframe_dir],
            "调 Codex CLI 重出图")
        print("\n⚠️ 下一步**必须人工逐张打开看**，确认你改的那一点真的改过来了。"
              "\n   看完用 --adopt <选中的png> --state '<看图后写的真实状态>' 回填。")
        return

    # --------------------------------------------------------- 回填 + 重装配视频
    if args.adopt:
        if not args.state or len(args.state.strip()) < 20:
            sys.exit(
                "--adopt 必须同时给 --state，而且要写得具体。\n"
                "这不是形式要求：新图的姿态跟旧图不一样，节拍必须从**新图**已有的\n"
                "状态继续。漏了这一步就是 ledger A3「人物不动、只有镜头在动」，\n"
                "我们在这个坑里已经栽过 17 次。先把新图打开看了再来。")
        png = args.adopt
        if not (os.path.exists(os.path.join(args.root, png)) or os.path.exists(png)):
            sys.exit(f"图不存在: {png}")
        rel = os.path.relpath(os.path.abspath(png), args.root)

        # 同一个关键帧可能被多个拆段单元共用，但只有 u1 焊首帧
        targets = [c for c in shot_cards
                   if c.get("id") == args.shot or c.get("id") == base_id + "_u1"]
        if not targets:
            sys.exit(f"shot_cards.json 里没有 {args.shot}")
        for c in targets:
            c["first_frame"] = rel
            c["first_frame_state_zh"] = args.state.strip()
            print(f"  已回填 {c['id']} → {rel}")
        dump(shot_cards_p, shot_cards)

        builder = BUILD_LTX if args.model == "ltx-2.5" else BUILD_H3
        out = Path(args.video_dir) / ("video_jobs.json" if args.model == "ltx-2.5"
                                      else "h3_jobs.json")
        tmp = Path(args.video_dir) / f"_rekey_{args.shot}.json"
        run([sys.executable, builder, shot_cards_p, "--only", args.shot, "-o", tmp],
            f"重新装配 {args.model} 的 job（先出到临时文件，确认无误再并回 {out.name}）")
        print(f"\n✅ 链条走完。临时 job 在 {tmp.name}，"
              f"确认没问题后并进 {out.name} 再提交生成。")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
