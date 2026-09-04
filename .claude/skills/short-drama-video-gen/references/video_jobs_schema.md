# video_jobs.json / video_jobs.md 格式说明

自建 LTX-2.5 通道（本仓库的主路线）里，`video_jobs.json` 是
`ltx_ssh_submit.py` 直接消费的输入，也是这一层的**主产物**。

**它由 `scripts/build_prompt.py` 从镜头卡装配出来，不手写。**

```
shot_cards.json  ──build_prompt.py──▶  video_jobs.json  ──▶  ltx_ssh_submit.py
（人维护这个）                          （派生，别手改）
```

镜头卡字段见 `shot_card_schema.md`，装配规则见 `video_prompt_guide.md`。

Markdown 版本（`video_jobs.md`）现在只是**给人看的汇总视图**，不再是提示词的
落脚处——需要时从 `video_jobs.json` 生成一份即可，用来贴进 PR/汇报或者手动
提交到 SaaS 平台。

---

## JSON 结构（`output/<故事名>/videos/ep0X/video_jobs.json`）

```json
[
  {
    "id": "xueshan_shot01_u1",
    "shot_no": 1,
    "scene": "雪山之巅_生死决斗",
    "shot_card_id": "xueshan_shot01_u1",
    "scene_plate": "无场景资产库：手工首帧的一次性镜头，机位=男主第一人称正面轴线",
    "first_frame_strength": 1.0,
    "prompt_lang": "en",
    "first_frame": "output/雪山决斗/refs/雪山决斗_女主_首帧_1600x896.png",
    "first_frame_from": null,
    "last_frame": null,
    "ref_images": [],
    "dialogue": "女主：\"为什么……骗我的是你……为什么？为什么！\"",
    "prompt": "shot from the male lead's first-person position, standing directly in front of her on the snowfield at her eye level, the same spot for the whole take. locked-off camera, ...",
    "negative_prompt": "(ltx_pipelines.distilled 没有 --negative-prompt 参数，此字段不会被发送，仅为兼容旧 schema 保留。...)",
    "duration_sec": 5.7083,
    "fps": 24,
    "num_frames": 137,
    "aspect_ratio": "16:9",
    "width": 1600,
    "height": 896,
    "seed": 42,
    "platform_recommend": ["LTX-2.5 (self-hosted)"],
    "notes": "137 帧。..."
  }
]
```

| 字段 | 来源 | 说明 |
|---|---|---|
| `id` | 卡 | 生成单元 id。拆段的用 `_u1`/`_u2` 后缀 |
| `shot_no` | 卡 | 对应分镜表镜号 |
| `scene` | 卡 | 场景编号 |
| `shot_card_id` | 卡 | **回指镜头卡**。改提示词回这张卡改，不要改本文件 |
| `scene_plate` | 卡 | 这一单元首帧用的**机位底板 id**（如 `SC04_顾家别墅餐厅_B反打`）。溯源用：验收说"这一镜视角不对"时先查底板对不对，改提示词没用 |
| `first_frame_strength` | 卡 | 首帧锁定强度，**保持 `1.0`**。2026-09-04 实测 1.0/0.95/0.85 三档无可观察差异，调低不换来任何松动（`model_capability_ledger.md` D4 已结案） |
| `prompt_lang` | 装配参数 | `en`（英文正文 + 中文台词）/ `zh`（全中文，旧行为） |
| `first_frame` | 卡 | 首帧图路径。**拆段的后续段在上一段跑完抽帧之后才能填上** |
| `first_frame_from` | 卡 | 如 `xueshan_shot01_u1:last`，说明这一段的首帧该从哪来 |
| `last_frame` | 卡 | 一般 `null`。只有确实要用首尾帧控制、且已经有"结束状态"关键帧时才填 |
| `ref_images` | 恒为 `[]` | **死字段**。`ltx_ssh_submit.py` 从不读取它，填了对自建通道没有任何效果（见 `model_capability_ledger.md` A4） |
| `dialogue` | 卡 | 各拍台词的中文汇总，**只是给人和配音/剪辑环节对照用**。真正驱动语音的是 `prompt` 里嵌好的台词 |
| `prompt` | **派生** | 装配产物。手改这里会让它和镜头卡脱钩，导出校验会拦 |
| `prompt_variant` | 只有探针文件才有 | **故意偏离镜头卡的理由**。探针/对照组（比如 A6 的提示词冻结 A/B）必须故意改提示词，声明了这个字段，导出校验就把"prompt 和卡对不上"从 ERROR 降成 WARN。**正式提交的 job 不许带它** |
| `negative_prompt` | 固定文案 | distilled pipeline 没有这个参数，**不会被发送**。仅为兼容旧 schema 保留 |
| `duration_sec` | 派生 | = `num_frames / fps`，已经是合法值 |
| `fps` | 卡 | 固定 24。LTX 没有 `--fps` 参数，这个值只用来推 `num_frames` |
| `num_frames` | 派生 | `8k+1` 合法值 |
| `aspect_ratio` | 派生 | 由 `width`/`height` 推出并吸附到常见比例。导出校验会拿它反查分辨率有没有漏填 |
| `width` / `height` | 卡 | 必须被 64 整除。漏填会悄悄退回 pipeline 默认的横屏 `1536×1024` |
| `seed` | 卡 | **必填，且不能是 10**（LTX `--seed` 的默认值就是 10，留着等于没指定） |
| `platform_recommend` | 固定 | `["LTX-2.5 (self-hosted)"]` |
| `notes` | 卡 | 原样带过来 |

---

## 关于台词：LTX-2.5 和 SaaS 平台的规则是相反的

- **SaaS 平台**（可灵/即梦/Vidu/Veo…）：多数没有可靠的对口型/角色语音能力，
  台词只能作为参考信息放在 `dialogue` 字段，**不要塞进提示词**。
- **自建 LTX-2.5（本仓库主路线）**：自带音频 VAE，**必须**把台词按格式嵌进
  正向提示词，否则生成出来只有环境音、没有台词。这是"视频没有台词"这类问题
  最常见的直接原因。

镜头卡的 `beats[].dialogue` 就是这个格式的结构化形式，装配器负责嵌入，
校验器负责确认语言声明和时长够不够。详见 `model_capability_ledger.md` C1/B4。

---

## 状态跟踪

生成进度不记在这份 JSON 里，记在 `loop-video-generation` 的
`units_queue.json`（`status` / `round_count` / `history[]` / `selected_file`）。
这份 JSON 只描述"要生成什么"，不描述"生成到哪一步了"。

需要给人看的进度视图时，`video_jobs.md` 可以带一列
`待生成 / 已提交测试档 / 测试档已核对 / 已确认 / 不合格待调整`。
