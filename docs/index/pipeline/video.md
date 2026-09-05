# 视频镜头卡与装配

仅定位文件；实际操作读取对应 skill。路径相对当前宿主的 skills 根目录。
表中关键文件的省略前缀沿用最近的 `scripts/` 或 `references/`。

| 顺序 | Skill 目录 | 输入 → 输出 | 关键文件 |
|---|---|---|---|
| 5 | `short-drama-video-gen/` | 关键帧 + 运动描述 → **镜头卡 `shot_cards.json`**（4-8 秒生成单元，逐拍结构化）→ 按选定模型分别装配：`build_prompt.py`→`video_jobs.json`（LTX-2.5）/ `build_h3_prompt.py`→`h3_jobs.json`（MiniMax-H3）。**同一份卡喂两个模型，提示词是派生产物，不手写。** B 级跟 S/A 级一样走 LTX，`ken_burns.py` 只是反复生成失败时的兜底 | `scripts/build_prompt.py`（LTX 装配+校验）, **`build_h3_prompt.py`（MiniMax-H3 装配+校验）**, **`rekey_shot.py`（L2 升级管道：改关键帧卡→重出图→回填首帧→重装配）**, `extract_frames.py`, `ken_burns.py`, **`measure_background_motion.py`（把 ledger A6「背景动没动」变成三个可比的数）**, `references/shot_card_schema.md`, **`keyframe_escalation_guide.md`（故障→L1视频层/L2关键帧层/L3分镜层 的路由表）**, `model_capability_ledger.md`（模型能做/做不到清单，每条带证据）, `video_prompt_guide.md`, `stability_playbook.md`, `video_jobs_schema.md`, `video_review_checklist.md`, `video_platform_comparison.md` |
