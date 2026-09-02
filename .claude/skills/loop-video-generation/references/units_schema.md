# unit 队列格式（units_queue.json）

`loop-video-generation` 的执行单元是一个 S/A 级镜头（或已按
`stability_playbook.md` 拆分的一个分段）。字段在
`short-drama-video-gen/references/video_jobs_schema.md` 的 JSON 版本基础
上加了几个本 skill 专属字段，用来支撑 Generator/Reviewer 两个 subagent
的多轮循环记录状态。

**这份队列描述"生成到哪一步了"，不描述"要生成什么"**——后者的源头是镜头卡
`shot_cards.json`（`short-drama-video-gen/references/shot_card_schema.md`）。
`prompt` 在这里是从卡装配出来的派生字段，改提示词回卡上改。

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 同 `video_jobs_schema.md`，`ep{集号:02d}_镜{镜号:02d}`，分段加后缀 `_seg1`/`_seg2`。 |
| `shot_no` / `scene` / `first_frame` / `last_frame` / `dialogue` | 同 `video_jobs_schema.md`。`dialogue` 仍然只是参考信息，不进 prompt。 |
| `ref_images` | 否，当前无效 | 沿用 `video_jobs_schema.md` 字段名，但 `ltx_ssh_submit.py` 从不读取/上传它，填了对自建 LTX-2.5 通道没有任何效果（详见该文件的字段说明和 `ltx_pipeline_gotchas.md`）。可以留着做人工记录，不要指望它影响生成结果，也不要让 Reviewer 把"一致性差"的 `fix_instruction` 落在"加一张参考图"上。 |
| `scene_plate` | 建议 | 这一单元首帧用的机位底板 id。Reviewer 判「视角不对」时靠它溯源；连续几个 unit 的 `scene_plate` 都一样，说明整场戏一个视角演完，那是分镜层的问题，**不计入这一镜的 3 轮重试**（见 `reviewer_agent.md`）。 |
| `shot_card_id` | 是 | 指向 `shot_cards.json` 里对应的镜头卡。**改提示词一律改那张卡的字段，然后重跑 `build_prompt.py`**，不要手改下面的 `prompt`。 |
| `prompt` | 是，但是**派生字段** | 当前这一轮实际提交的完整**正向**提示词，由 `short-drama-video-gen/scripts/build_prompt.py` 从 `shot_card_id` 指向的镜头卡装配出来。上一轮 `fail` 时，orchestrator 按 Reviewer 的 `fix_instruction` 改**卡上的字段**（比如 `beats[1].motion_en`）再重跑装配脚本，把新结果同步到这里；**不要直接手改这个字符串**——下次装配会冲掉它，而且 `validate_video_jobs.py` 会拦"prompt 和镜头卡装配结果不一致"。**这是本 pipeline 唯一真正影响生成结果的文本字段**，理由见下面 `negative_prompt` 的说明。 |
| `negative_prompt` | 否，仅存档 | `ltx_ssh_submit.py` 已经用 `--help` 实测确认 `ltx_pipelines.distilled`/`dfr_pipeline` **都没有 `--negative-prompt` 这个 CLI 参数**（脚本源码里明确写了"不传给这个 pipeline 的 CLI"）——这个字段改了对生成结果**没有任何实际影响**，只是留着给人读、给以后换到支持这个字段的 pipeline 时用。Reviewer 的 `fix_instruction` **不允许**只落在"加强负面提示词"上，必须落在下面 `prompt`/`seed`/动作幅度/分段这几个真正生效的杠杆上，见 `references/reviewer_agent.md`。 |
| `seed` | 是（每轮都要显式填） | `ltx_pipeline_gotchas.md` 实测确认 `--seed` 默认值固定是 `10`、不传就每次复现同一个结果，**不是随机**。round 0 用镜头卡上的 `seed`（卡的校验会拒绝 `10`——留成默认值等于没指定，会让"换种子"这条杠杆失效）；如果某一轮 `fail` 且原因看起来是"这次随机采样运气差"而不是系统性的提示词/参数问题，这一轮必须换一个新的 `seed` 值，否则用同样的 prompt+同样的默认 seed 重跑，会拿到几乎一样的结果，等于白烧一次显卡时间。 |
| `duration_sec_test` / `resolution_test` | 是 | 按 `stability_playbook.md` 第 5 条，循环的每一轮都先用测试档（短时长+低分辨率）生成，省显卡时间。 |
| `duration_sec_final` / `resolution_final` | 是 | 测试档通过（`status` 变 `passed` 前的最后一步）之后，用来提交一次正式档确认的参数。 |
| `platform_recommend` | 是 | 沿用 `video_jobs_schema.md`，这里固定是自建 LTX-2.5，可以留作记录用途。 |
| `script_ref` | 是 | Reviewer 判断"情节对不对"唯一的依据原文。优先摘用户提供的完整剧本/对白全文对应段落；没有就摘 `short-drama-scout` 该集分集大纲原文（开场3秒/核心冲突/结尾钩子里跟这一镜相关的部分）+ 出场角色的人物小传设定。**不能**填 `ep0X.md` 分镜表"画面描述"列原文——那是生成阶段已经用过的输入。 |
| `round_count` | 是，初始 `0` | 只统计"拿到视频/帧、Reviewer 给出了内容判断"的轮次。达到 `3` 就必须放行，不管有没有 `pass`。**基础设施性错误**（SSH/CUDA 崩溃、VAE 解码报错、HF 权限 401/403 等，见 `references/generator_agent.md`"技术性障碍"一节）不产出帧、Reviewer 根本没机会判断，不计入这个数字，按技术故障单独处理。 |
| `status` | 是，初始 `pending` | `pending` / `active`（当前在跑，同一时刻整个队列只应该有 1 条是这个状态，见 `loop_protocol.md` 的顺序执行规则）/ `passed` / `capped` / `capped_by_split`（这一条被判定成"结构上就不该一次生成"，已经拆成若干 `_u1`/`_u2` 子单元另起条目，本条不再重试，也不产出 `selected_file`——最终成片用子单元的产物；《出狱后》ep01 的 `ep01_镜06`/`ep01_镜20_seg2` 就是这个状态）/ `blocked`（遇到基础设施性错误，等人处理，不算创作重试用完）。 |
| `history` | 是，初始 `[]` | 每轮追加一条 `{round, seed, video_file, frames_dir, verdict, reason, fix_instruction, defect_window}`。`defect_window`（`{start, end}`，单位秒，可为空）是 Reviewer 判断"问题只集中在这一小段、其余画面正常"时给出的时间窗口，orchestrator 据此决定下一轮是走 `ltx_pipelines.retake` 局部重绘还是整段重来，见 `loop_protocol.md`。`capped` 状态下从这里挑 Reviewer 在第 3 轮给出的 `best_of_all` 及"是否建议降级为本地推拉摇移兜底"的意见。 |
| `final_confirmed` | 是，初始 `false` | 测试档 `pass` 之后按正式 `duration_sec_final`/`resolution_final` 重新提交一次的结果是否也确认无误；这一步如果出问题按 `loop_protocol.md` 的规则计入轮次。 |
| `selected_file` | 否 | `passed` 且 `final_confirmed: true` 时填正式档视频文件绝对路径；`capped` 时填 `best_of_all` 选出的文件路径。 |

## 示例

```json
[
  {
    "id": "ep01_镜03",
    "shot_no": 3,
    "scene": "SC01_出租屋_日间",
    "shot_card_id": "ep01_镜03",
    "first_frame": "output/千金归位/keyframes/ep01/ep01_镜03_00.png",
    "last_frame": null,
    "ref_images": ["output/千金归位/assets/苏晚_落魄期_三视图/苏晚_落魄期_三视图_00.png"],
    "_ref_images_note": "仅存档，ltx_ssh_submit.py 不会读取/上传这个字段，对自建 LTX-2.5 通道无效",
    "dialogue": "婶，我真的无处可去了……",
    "prompt": "人物眼眶先泛红，睫毛颤动，随后泪水滑落脸颊，嘴角下撇，动作轻微克制，镜头固定不动……（只写变化量，人物外观/服装/背景陈设已经由 first_frame 提供，不在文字里重复描述，避免跟图像条件打架）",
    "negative_prompt": "避免：人物面部变形、五官错位、多余肢体、背景突变、镜头剧烈抖动（仅存档参考，distilled/dfr pipeline 不接受这个 CLI 参数，不会真正生效）",
    "seed": 3307,
    "duration_sec_test": 2,
    "resolution_test": "720p",
    "duration_sec_final": 4,
    "resolution_final": "1080p",
    "platform_recommend": ["自建 LTX-2.5"],
    "script_ref": "（分集大纲·第1集·核心冲突）苏晚被养家亲戚当街赶出门，众目睽睽之下遭受羞辱却无处可去，这是全剧建立她'落魄'处境的第一个关键情绪点，要让观众对她产生同情而不是觉得她软弱认命。",
    "round_count": 0,
    "status": "pending",
    "history": [],
    "final_confirmed": false,
    "selected_file": null
  }
]
```
