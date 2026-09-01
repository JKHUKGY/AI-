# unit 队列格式（units_queue.json）

`loop-picture-generation` 的执行单元叫 **unit**，一个 unit 对应"一个角色
三视图 job / 一个场景 job / 一集里的一镜关键帧 job"。字段在
`short-drama-image-gen` 的 `references/jobs_schema.md` 基础上加了几个本
skill 专属字段，用来让 Generator/Reviewer 两个 subagent 的多轮循环有地方
落地状态，不需要每轮都在对话里口头追踪"这个到第几轮了"。

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 同 `jobs_schema.md`，job/文件名前缀，全队列唯一。 |
| `type` | 是 | `character_turnaround` / `scene` / `keyframe`，决定 Reviewer 用哪份验收清单、要不要额外检查"三视图专属"标准。 |
| `prompt` | 是 | 当前这一轮要用的完整提示词。round 0 是原始提示词；后续每轮如果上一轮 `fail`，这里要替换成"原始 prompt + Reviewer 给的 `fix_instruction`"拼接后的最新版本——由 orchestrator（跑这个 skill 的你）在收到 Reviewer verdict 后更新，Generator agent 不自己改这个字段。 |
| `ref_images` | 否 | 同 `jobs_schema.md`，参考图文件路径数组。 |
| `count_per_round` | 否，默认按类型 | 每一轮要生成几张：角色三视图首轮固定 3，场景/关键帧首轮 2-4，追加轮建议调小到 2，避免陪跑成本。 |
| `storyboard_ref` | 是 | Reviewer 判断合格与否**唯一**的依据原文，逐字摘录，不要转述改写：`character_turnaround` 摘 `characters.md` 里这个角色的档案原文；`scene` 摘 `scenes.md` 场景描述原文；`keyframe` 摘 `ep0X.md` 该镜"画面描述+景别+出场人物"那一行原文。 |
| `round_count` | 是，初始 `0` | 已经完整跑过几轮（一轮 = 一次生成 + 一次审查）。达到 `3` 就必须放行，不管有没有 `pass`。 |
| `status` | 是，初始 `pending` | `pending`（排队中）/ `active`（占用槎位，正在跑）/ `passed`（通过）/ `capped`（跑满 3 轮仍不合格，被迫放行）。 |
| `history` | 是，初始 `[]` | 每轮追加一条 `{round, files: [...], verdict: "pass"/"fail", fix_instruction, reason}`。`capped` 状态下从这里挑 Reviewer 在第 3 轮给出的 `best_of_all` 作为最终交付。 |
| `selected_file` | 否 | `passed` 时填 Reviewer 选中的文件绝对路径；`capped` 时填 `best_of_all` 选出的文件绝对路径。 |

## 示例

```json
[
  {
    "id": "苏晚_落魄期_三视图",
    "type": "character_turnaround",
    "prompt": "现代都市短剧写实照片级质感……三个视角保持同一站姿同一表情同一套服装，纯色干净背景……避免：多余肢体、五官崩坏、三个视角不是同一个人",
    "ref_images": [],
    "count_per_round": 3,
    "storyboard_ref": "苏晚：24岁东亚女性，黑长直发前期略毛躁自然垂落，深棕色瞳孔，肤色偏白略显疲惫，身材纤瘦挺拔，落魄期穿着洗旧的浅色针织衫+牛仔裤，眼神隐忍。",
    "round_count": 0,
    "status": "pending",
    "history": [],
    "selected_file": null
  },
  {
    "id": "ep01_镜11",
    "type": "keyframe",
    "prompt": "……特写镜头，聚焦手部与散落衣物，苏晚跪地伸手去捡的动作瞬间……参考图1为SC01场景，参考图2为苏晚落魄期人物，保持人物面部与参考图2完全一致……",
    "ref_images": [
      "output/千金归位/assets/SC01_客厅_日间/SC01_客厅_日间_01.png",
      "output/千金归位/assets/苏晚_落魄期_三视图/苏晚_落魄期_三视图_00.png"
    ],
    "count_per_round": 2,
    "storyboard_ref": "镜11｜场景 SC01(日)｜出场人物 苏晚｜画面描述：苏晚跪地伸手去捡散落的文件，手指微颤｜景别：特写",
    "round_count": 0,
    "status": "pending",
    "history": [],
    "selected_file": null
  }
]
```

## 关于 `count_per_round` 和文件编号

Generator agent 每一轮都对同一个 `id` 调用一次
`short-drama-image-gen/scripts/generate_images.py`，脚本本身会按
`output/<...>/<id>/` 目录里已有的 `<id>_*.png` 数量接着往后编号（不会覆盖
之前几轮的图），所以不需要给每一轮起不同的 job id，`history` 里记的
`files` 字段直接对应这一轮新增的那几个文件名即可。
