# 素材与关键帧

仅定位文件；实际操作读取对应 skill。路径相对当前宿主的 skills 根目录。
表中关键文件的省略前缀沿用最近的 `scripts/` 或 `references/`。

| 顺序 | Skill 目录 | 输入 → 输出 | 关键文件 |
|---|---|---|---|
| 3 | `short-drama-image-gen/` | 人物/场景提示词 → 三视图立绘 + 场景图（Codex CLI 出图） | `scripts/generate_images.py`, `references/jobs_schema.md`, `parallel_mode.md`, `review_checklist.md`, `api_setup.md` |
| 4 | `short-drama-keyframe-gen/` | **两阶段、中间一道人工闸门**。阶段一：分镜表 + 已选人物/场景图 → 先划**场次节拍 `scene_beats`**（这一段戏**谁在这个房间里** `present` / 房间此刻什么状态 `state_zh` / 谁坐在哪件家具上 `seating` / **场次主帧** `master_frame`）→ 再逐镜填**关键帧卡 `keyframe_cards.json`**（逐人写位置/纵深层/身体朝向/**相对镜头露多少脸**/视线/瞬间动作 + 景别对应的裁切线 + **`background_people` 画面里还看得见谁** / **`present_off_frame` 谁确实在画外**）→ `build_keyframe_prompt.py` 机械装配出提示词、审阅表 `keyframe_prompts_ep0X.md` 和 `jobs_ep0X.json`，**提示词是派生产物，不手写**；停下来等用户确认走位。阶段二：确认后才出图（全量每一镜），出完**一场戏的图要排开一起再看一遍**（连戏问题逐张看抓不到）| `scripts/build_keyframe_prompt.py`（装配+校验，含**连戏层**：在场必须表态／画外声明不能和取景打架／**近景特写必须挂紧底板**）, **`build_master_frame_prompt.py`（场次主帧装配器）**, `references/keyframe_card_schema.md`, `blocking_guide.md`（走位/朝向/景别规则，每条带实拍证据）, `keyframe_prompt_guide.md`（素材查找+分镜表列对应）, `shot_selection.md`, `keyframe_review_checklist.md`（含**场次级验收**）, `examples/ep03_keyframe_cards.json`(+`_v1_replica`) |
