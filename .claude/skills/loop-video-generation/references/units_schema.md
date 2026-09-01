# unit 队列格式（units_queue.json）

`loop-video-generation` 的执行单元是一个 S/A 级镜头（或已按
`stability_playbook.md` 拆分的一个分段）。字段在
`short-drama-video-gen/references/video_jobs_schema.md` 的 JSON 版本基础
上加了几个本 skill 专属字段，用来支撑 Generator/Reviewer 两个 subagent
的多轮循环记录状态。

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 同 `video_jobs_schema.md`，`ep{集号:02d}_镜{镜号:02d}`，分段加后缀 `_seg1`/`_seg2`。 |
| `shot_no` / `scene` / `first_frame` / `last_frame` / `dialogue` | 同 `video_jobs_schema.md`。`dialogue` 仍然只是参考信息，不进 prompt。 |
| `ref_images` | 否，当前无效 | 沿用 `video_jobs_schema.md` 字段名，但 `ltx_ssh_submit.py` 从不读取/上传它，填了对自建 LTX-2.5 通道没有任何效果（详见该文件的字段说明和 `ltx_pipeline_gotchas.md`）。可以留着做人工记录，不要指望它影响生成结果，也不要让 Reviewer 把"一致性差"的 `fix_instruction` 落在"加一张参考图"上。 |
| `prompt` | 是 | 当前这一轮要用的完整**正向**提示词。round 0 是 `short-drama-video-gen` 展开的原始版本；后续每轮如果上一轮 `fail`，这里要按 Reviewer 的 `fix_instruction` 更新——由 orchestrator 更新，Generator agent 不自己改。**这是本 pipeline 唯一真正影响生成结果的文本字段**，理由见下面 `negative_prompt` 的说明。 |
| `negative_prompt` | 否，仅存档 | `ltx_ssh_submit.py` 已经用 `--help` 实测确认 `ltx_pipelines.distilled`/`dfr_pipeline` **都没有 `--negative-prompt` 这个 CLI 参数**（脚本源码里明确写了"不传给这个 pipeline 的 CLI"）——这个字段改了对生成结果**没有任何实际影响**，只是留着给人读、给以后换到支持这个字段的 pipeline 时用。Reviewer 的 `fix_instruction` **不允许**只落在"加强负面提示词"上，必须落在下面 `prompt`/`seed`/动作幅度/分段这几个真正生效的杠杆上，见 `references/reviewer_agent.md`。 |
| `seed` | 是（每轮都要显式填） | `ltx_pipeline_gotchas.md` 实测确认 `--seed` 默认值固定是 `10`、不传就每次复现同一个结果，**不是随机**。round 0 用一个固定初始值（比如 `10`）；如果某一轮 `fail` 且原因看起来是"这次随机采样运气差"而不是系统性的提示词/参数问题，这一轮必须换一个新的 `seed` 值，否则用同样的 prompt+同样的默认 seed 重跑，会拿到几乎一样的结果，等于白烧一次显卡时间。 |
| `duration_sec_test` / `resolution_test` | 是 | 按 `stability_playbook.md` 第 5 条，循环的每一轮都先用测试档（短时长+低分辨率）生成，省显卡时间。 |
| `duration_sec_final` / `resolution_final` | 是 | 测试档通过（`status` 变 `passed` 前的最后一步）之后，用来提交一次正式档确认的参数。 |
| `platform_recommend` | 是 | 沿用 `video_jobs_schema.md`，这里固定是自建 LTX-2.5，可以留作记录用途。 |
| `script_ref` | 是 | Reviewer 判断"情节对不对"唯一的依据原文。优先摘用户提供的完整剧本/对白全文对应段落；没有就摘 `short-drama-scout` 该集分集大纲原文（开场3秒/核心冲突/结尾钩子里跟这一镜相关的部分）+ 出场角色的人物小传设定。**不能**填 `ep0X.md` 分镜表"画面描述"列原文——那是生成阶段已经用过的输入。 |
| `round_count` | 是，初始 `0` | 只统计"拿到视频/帧、Reviewer 给出了内容判断"的轮次。达到 `3` 就必须放行，不管有没有 `pass`。**基础设施性错误**（SSH/CUDA 崩溃、VAE 解码报错、HF 权限 401/403 等，见 `references/generator_agent.md`"技术性障碍"一节）不产出帧、Reviewer 根本没机会判断，不计入这个数字，按技术故障单独处理。 |
| `status` | 是，初始 `pending` | `pending` / `active`（当前在跑，同一时刻整个队列只应该有 1 条是这个状态，见 `loop_protocol.md` 的顺序执行规则）/ `passed` / `capped` / `blocked`（遇到基础设施性错误，等人处理，不算创作重试用完）。 |
| `history` | 是，初始 `[]` | 每轮追加一条 `{round, seed, video_file, frames_dir, verdict, reason, fix_instruction, defect_window}`。`defect_window`（`{start, end}`，单位秒，可为空）是 Reviewer 判断"问题只集中在这一小段、其余画面正常"时给出的时间窗口，orchestrator 据此决定下一轮是走 `ltx_pipelines.retake` 局部重绘还是整段重来，见 `loop_protocol.md`。`capped` 状态下从这里挑 Reviewer 在第 3 轮给出的 `best_of_all` 及"是否建议降级成 B 级"的意见。 |
| `final_confirmed` | 是，初始 `false` | 测试档 `pass` 之后按正式 `duration_sec_final`/`resolution_final` 重新提交一次的结果是否也确认无误；这一步如果出问题按 `loop_protocol.md` 的规则计入轮次。 |
| `selected_file` | 否 | `passed` 且 `final_confirmed: true` 时填正式档视频文件绝对路径；`capped` 时填 `best_of_all` 选出的文件路径。 |

## 示例

```json
[
  {
    "id": "ep01_镜03",
    "shot_no": 3,
    "scene": "SC01_出租屋_日间",
    "first_frame": "output/千金归位/keyframes/ep01/ep01_镜03_00.png",
    "last_frame": null,
    "ref_images": ["output/千金归位/assets/苏晚_落魄期_三视图/苏晚_落魄期_三视图_00.png"],
    "_ref_images_note": "仅存档，ltx_ssh_submit.py 不会读取/上传这个字段，对自建 LTX-2.5 通道无效",
    "dialogue": "婶，我真的无处可去了……",
    "prompt": "人物眼眶先泛红，睫毛颤动，随后泪水滑落脸颊，嘴角下撇，动作轻微克制，镜头固定不动……（只写变化量，人物外观/服装/背景陈设已经由 first_frame 提供，不在文字里重复描述，避免跟图像条件打架）",
    "negative_prompt": "避免：人物面部变形、五官错位、多余肢体、背景突变、镜头剧烈抖动（仅存档参考，distilled/dfr pipeline 不接受这个 CLI 参数，不会真正生效）",
    "seed": 10,
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
