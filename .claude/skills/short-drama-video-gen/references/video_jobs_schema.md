# video_jobs.md / video_jobs.json 格式说明

因为没有统一的免 API key 调用脚本（见 SKILL.md 第 0 步），这份清单的默认
形态是给用户看的 **Markdown 表格**，用户手动复制提示词到平台网页版提交。
只有用户明确说要接自己的 API 时，才额外导出对应字段的 JSON。

## Markdown 版本（默认产出，`output/<故事名>/videos/ep0X/video_jobs.md`）

| 镜号 | 场景 | 首帧文件路径 | 尾帧文件路径(可选) | 一致性参考图 | 台词/旁白 | 正向提示词 | 负面提示词 | 建议时长(秒) | 推荐平台 | 分段说明 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|

- **台词/旁白**列直接从 `ep0X.md` 分镜表的"台词/旁白"列原样搬过来，没有
  就写"无"。这一列**只是给配音/剪辑环节对照用的参考信息**，不代表要把
  这句话喂给图生视频模型生成语音——目前没有确认任何一个平台能可靠地按
  台词生成对应角色音色的同步语音/口型，所以提示词部分依然只描述动作和
  镜头，不要把台词硬塞进正向提示词里让模型自己编。
- **状态**列用来跟踪进度：`待生成` / `已提交测试版` / `测试版已核对，待正式版`
  / `已确认` / `不合格待调整`，方便多轮返工时不丢进度。
- **分段说明**：如果这个镜头被拆成了多段（见 `stability_playbook.md` 第 3
  条），在这里写清楚"第 1/2 段，结束帧衔接下一段"，并各自占一行。

## JSON 版本（仅用户要接自己 API 时导出）

```json
[
  {
    "id": "ep01_镜03",
    "shot_no": 3,
    "scene": "SC01_出租屋_日间",
    "first_frame": "output/千金归位/keyframes/ep01/ep01_镜03_00.png",
    "last_frame": null,
    "ref_images": [
      "output/千金归位/assets/苏晚_落魄期_正面/苏晚_落魄期_正面_00.png"
    ],
    "dialogue": "婶，我真的无处可去了……",
    "prompt": "起始画面为参考图中人物近景，人物眼眶先泛红...(完整正向提示词)",
    "negative_prompt": "避免：人物面部变形、五官错位、多余肢体...(完整负面提示词)",
    "duration_sec": 3,
    "aspect_ratio": "9:16",
    "resolution_test": "720p",
    "resolution_final": "1080p",
    "platform_recommend": ["可灵 Kling", "即梦 Jimeng"],
    "notes": "A级反应镜，先跑720p测试版确认动作方向再上1080p正式版"
  }
]
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 与 `keyframes.md`/`jobs.json` 一致的命名规则 `ep{集号:02d}_镜{镜号:02d}`，分段的话加后缀 `_seg1`/`_seg2`。 |
| `first_frame` | 是 | 来自 `keyframes.md` 的关键帧文件路径，不要凭空指定。 |
| `last_frame` | 否 | 只有确定用首尾帧控制、且已经有对应的"结束状态"关键帧时才填，没有就留 `null`，不要让视频模型的默认行为被误当成刻意设计的结束状态。 |
| `ref_images` | 否 | 额外的一致性参考图（人脸/道具特写），数量按目标平台上限来，见 `video_platform_comparison.md`。**自建 LTX-2.5 路线注意**：`short-drama-ltx-generate/scripts/ltx_ssh_submit.py` 目前从不读取/上传这个字段，只处理 `first_frame`/`last_frame`——填了这个字段对自建通道的生成结果没有任何效果（官方真正的多参考图机制是 IC-LoRA Ingredients/Multi-Subject Reference LoRA，需要额外权重和不同调用方式，见 `ltx_pipeline_gotchas.md`）。这个字段目前只对手动提交到 SaaS 平台（可灵/即梦/Vidu/Veo 等，它们的网页版/API 本身支持多参考图）有意义。 |
| `dialogue` | 否 | 从 `ep0X.md` 分镜表"台词/旁白"列原样搬过来，纯参考信息，给配音/剪辑环节对照用；没有台词就留 `null`。不要喂进 `prompt`/`negative_prompt` 让模型生成语音。 |
| `prompt` / `negative_prompt` | 是 | 完整文本，按 `video_prompt_guide.md` 展开，不要留占位符。 |
| `duration_sec` | 是 | 目标正式时长；测试轮次可以先用更短的值单独跑，不需要改这个字段，测试版本自己另开一条记录或在 `notes` 里注明。 |
| `platform_recommend` | 是 | 1-2 个推荐平台，参考 `video_platform_comparison.md` 的选型建议。 |
| `notes` | 否 | 分段/测试策略/特殊注意事项。 |

这份 JSON 不被任何脚本自动消费（B 级的 `ken_burns.py` 用的是单独的
`kenburns_jobs.json`，见该脚本头部说明），纯粹是给用户自己接 API 时省去
从 Markdown 表格再转录一遍的功夫。
