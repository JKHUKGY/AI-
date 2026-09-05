## 3. 出图 / 出视频要用的外部账号

| 用途 | 怎么接入 | 在哪配 |
|---|---|---|
| 人物图/场景图/关键帧图 | Codex CLI（ChatGPT 账号登录，无需 API key、不额外计费） | 本机 `codex login --device-auth`，登录态在本机 `~/.codex/`；服务器上要单独登录一次，否则网站的"重新生成"按钮不可用 |
| 图生视频（LTX-2.5 / MiniMax-H3） | 租显卡自建，**渠道只剩 RunPod**（AutoDL 和 vast.ai 2026-09-04 已删除：销毁实例会连权重一起删）。用哪个模型看 config 里的 `model` 字段 | 各剧的 `output/<剧名>/videos/ep0X/ltx_remote_config.json`（连接信息 + `model` + `platform`/`instance_id`/`network_volume_id`）；平台 key 在 `.claude/skills/short-drama-ltx-generate/runpod_config.json`（**已 gitignore，仓库里没有**） |

显卡**用完必须关**：`.claude/skills/short-drama-ltx-generate/scripts/gpu_teardown.py`
一条命令关实例并轮询确认停止计费；批量任务用 `ltx_ssh_submit.py --auto-stop`。
