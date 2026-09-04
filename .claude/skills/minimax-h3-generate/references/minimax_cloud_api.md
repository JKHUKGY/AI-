# MiniMax 官方云 API（H3）——第三条通道

自建 SGLang 之外的另一条路：**不租显卡，直接打 MiniMax 官方 API**。
跑的是同一个 H3，吃的是**同一份 `h3_jobs.json`**，但接口和参数完全不同，
所以单独一个脚本：`scripts/h3_cloud_submit.py`。

跟另外两条的分工：

| | 自建 SGLang | 官方云 API | MiniMax Design |
|---|---|---|---|
| 脚本 | `h3_submit.py` | **`h3_cloud_submit.py`** | 没有，人在客户端点 |
| 要不要租卡 | 要 | 不要 | 不要 |
| seed 可控 | ✅ | ❌ | ❌ |
| 最高分辨率 | 768p（开源权重原生） | **2K** | 2K |
| 批量 | 脚本跑 | 脚本跑 | 手动，不适合整集 |

## 接口事实（2026-09 文档）

```
POST https://api.minimax.io/v2/video_generation          # 海外
POST https://api.minimaxi.com/v2/video_generation        # 国内
GET  /v2/query/video_generation/{task_id}                # 早期示例是 ?task_id=，脚本两种都试
Authorization: Bearer <api_key>                          # 不需要 GroupId
```

请求体：

```json
{
  "model": "MiniMax-H3",
  "content": [
    {"type": "text", "text": "<六段 ref2va 提示词，≤7000 字符>"},
    {"type": "image_url", "image_url": {"url": "..."}, "role": "reference_image"}
  ],
  "resolution": "2K",
  "duration": 6,
  "ratio": "9:16"
}
```

- `url` 三种写法都行：公网 URL、`mm_file://{file_id}`、**`data:image/png;base64,...`**。
  我们的关键帧在本地，脚本默认走 data URI，省掉图床——单张 2.1 MB 的 PNG
  内联后请求体 2.84 MB，离 64 MB 的体积上限很远。
- `role`：`first_frame` / `last_frame` / `reference_image`（视频 `reference_video`、
  音频 `reference_audio`、重生成 `base_video`）。**带 first/last frame 的任务官方规定
  `ratio` 恒为 `adaptive`**，脚本会自动改并提示。
- 素材上限：图 ≤9、视频 ≤3（每段 2-15s、合计 ≤15s）、音频 ≤3（不能作为唯一输入）、
  总数 ≤12。图片 JPG/JPEG/PNG/WEBP/HEIC/HEIF、≤30 MB、边长 256-5760、宽高比 0.4-2.5。
- `duration`：**整数秒**，H3 是 4-15，H3-Max 是 5-15。
- `resolution`：H3 `768P`/`2K`，H3-Max `480P`/`768P`。
- `ratio`：`adaptive` `21:9` `16:9` `4:3` `1:1` `3:4` `9:16`。
- 返回 `{"task_id": ...}`；轮询到 `task.status == "succeeded"` 后
  `task.content.url` 直接就是 mp4 地址，不用再换 file_id。官方建议 10 秒一轮。
- **没有 `seed` 字段**。文档里 `watermark` / `prompt_optimizer` 这些也都没有。

## 从自建那份 jobs 搬过来要注意的四处落差

1. **时长要取整。** 自建走 `num_frames`（17n+5、24fps），时长是 5.875 / 8.708 这种小数；
   云端只吃整数秒。脚本默认 `--duration-policy ceil`——**宁可片尾多留一点静止，
   也不要把最后一拍切掉**，因为六段提示词里的逐拍时间戳是按原时长写的。
   换成 `nearest` 会在 ep01 的 8 个镜头上削掉末拍（镜22/镜25 各削 0.458s，
   占它们全长的 10%）。`ceil` 下 ep01 全集 217 秒，`nearest` 202 秒。
2. **分辨率别沿用 768。** 自建锁 768 短边是开源权重原生只有 768p 的限制，
   云端支持 2K，白拿的收益。
3. **seed 全部作废。** 卡里那些 seed 在这条路上不可用，复现只能靠多抽几条挑。
4. **画幅从 `target.aspect_ratio` 走，不是 `short_edge`。** 云端不接受
   704×1280 这种自定义尺寸，只有比例档。

## 用法

API key 三处任取其一，**都不进仓库**（跟 `runpod_config.json` 同一个规矩，
`minimax_config.json` 已加进 `.gitignore`）：`--api-key` / 环境变量
`MINIMAX_API_KEY` / `.claude/skills/minimax-h3-generate/minimax_config.json`。

```bash
J="output/出狱后我成为了非洲矿王_v2/videos/ep01"

# ① 看请求体，不花钱、不需要 key
python3 .claude/skills/minimax-h3-generate/scripts/h3_cloud_submit.py \
    --jobs $J/h3_jobs.json --out-dir $J --only ep01_镜01+1 --dry-run

# ② 落一套可审阅、可进 git 的 payload（图片写成 file:// 占位）
python3 .claude/skills/minimax-h3-generate/scripts/h3_cloud_submit.py \
    --jobs $J/h3_jobs.json --out-dir $J --emit-payloads $J/cloud_payloads

# ③ 落完全自包含、能直接 curl 的 payload（每个几 MB，别进 git）
python3 .claude/skills/minimax-h3-generate/scripts/h3_cloud_submit.py \
    --jobs $J/h3_jobs.json --out-dir $J --only ep01_镜01+1 \
    --emit-payloads /tmp/payloads --inline-base64
curl -s https://api.minimax.io/v2/video_generation \
    -H "Authorization: Bearer $MINIMAX_API_KEY" -H "Content-Type: application/json" \
    -d @/tmp/payloads/ep01_镜01+1.json

# ④ 真提交（提交→轮询→下载 <id>_cloud.mp4→写 h3_cloud_results.json）
python3 .claude/skills/minimax-h3-generate/scripts/h3_cloud_submit.py \
    --jobs $J/h3_jobs.json --out-dir $J --resolution 2K --region global
```

`--region cn` 走 api.minimaxi.com。这条路**没有关机动作**——按秒计费，
跑完就结束，不用 `gpu_teardown.py`。

## 来源

- <https://platform.minimax.io/docs/guides/video-generation> / <https://platform.minimaxi.com/docs/guides/video-generation>
- <https://platform.minimax.io/docs/api-reference/video-generation-v2-create>
- <https://huggingface.co/MiniMaxAI/MiniMax-H3>（六段 ref2va 提示词格式、base64 Data URL 用法）
