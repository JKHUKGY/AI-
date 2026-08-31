# 自建 LTX-2.5（Lightricks LTX-2 仓库）远程调用说明

> 2026-08 调研，用前先在远程机器上跑一次 `--help` 核实，不要假设这里的参数
> 名字永远不变——官方仓库还在迭代。

## 和"平台订阅"的本质区别

`video_platform_comparison.md` 里列的可灵/即梦/Vidu/PixVerse/海螺/Runway/
Veo 都是别人家的 SaaS，本 skill 不内置调用脚本是因为各家 API 差异大、需要
用户自己的计费账号。**LTX-2.5 不一样**：用户自己租显卡（比如 vast.ai）、
自己部署开源仓库 `Lightricks/LTX-2`，SSH 是通用协议，不存在"各家 API 差异"
的问题，所以这种情况下本 skill 提供了实际的调用脚本
`scripts/ltx_ssh_submit.py`，直接完成"上传首帧 → 远程跑推理 → 下载视频"，
不需要用户手动操作网页。

## 官方接口现状（截至 2026-08 调研）

1. **推理入口**：官方仓库已从旧的 `Lightricks/LTX-Video`（0.9.x）迁移到新
   仓库 `Lightricks/LTX-2`（monorepo：`ltx-core`/`ltx-pipelines`/
   `ltx-trainer`）。**LTX-2.5 是官方当前推荐模型**。推理通过
   `python -m ltx_pipelines.<pipeline名>` 调用（例如
   `ltx_pipelines.ti2vid_two_stages`、`ltx_pipelines.distilled`、
   `ltx_pipelines.keyframe_interpolation`）。也支持 ComfyUI
   （`ComfyUI-LTXVideo` 插件），如果用户更习惯 ComfyUI，本脚本不适用，需要
   另外走 ComfyUI 的 workflow API。
2. **图生视频**：用 `--image` 传首帧路径。`KeyframeInterpolationPipeline`
   专门做首尾帧插值，`--num-generated-keyframes N` 控制中间关键帧数量
   （默认 0 = 关闭）。**官方文档没有给出 `--image` 和尾帧/多参考图组合使用
   的完整示例**，实际参数名（比如尾帧是不是叫 `--last-image`）需要
   `python -m ltx_pipelines.keyframe_interpolation --help` 现场确认，
   `ltx_ssh_submit.py` 里对应的参数是占位实现，跑之前必须核实。
3. **提示词**：正向 `--prompt` 是确定的。`--negative-prompt` 官方文档只在
   `T2AOneStagePipeline` 里明确出现，**没有确认所有图生视频 pipeline 是否
   都支持这个参数**，用错了 LTX 会直接报参数错误，脚本会把 stderr 打印
   出来，看到报错就去掉这个参数或查 `--help` 换正确写法。
4. **时长/帧率**：用 `--num-frames` 控制帧数（官方示例用过 121），没找到
   独立的 `--fps` 参数，帧率大概率固定在 24fps，脚本按
   `num_frames = duration_sec * 24` 估算，job 里可以直接写 `num_frames`
   覆盖这个估算。
5. **分辨率/竖屏**：用 `--width`/`--height` 传像素值，需能被 64 整除（部分
   模式要 128）。官方没有专门说"是否支持 9:16"，从示例数值看宽高可以任意
   搭配，理论上传竖屏尺寸（如 768×1360）就行，**但短剧是竖屏这件事本身没
   有被官方案例验证过，第一次跑一定要先用最小分辨率/最短帧数测试一遍，
   确认出来的视频真的是竖屏、没有被模型内部裁剪成横屏**。
6. **显存/性能**：模型权重合计约 66GiB（transformer + 文本编码器 + VAE +
   upscaler）。显存不够可以加 `--quantization fp8-cast --offload cpu`（或
   `disk`）降低占用，但会变慢，帮用户判断这台租来的显卡够不够用。

## 实测踩坑记录（2026-08，RTX PRO 6000 Blackwell WS 实测）

- **`--negative-prompt` 在 `ltx_pipelines.distilled` 里根本不存在**（实测
  `--help` 确认），负面提示词只能留在 job 数据里给人看，不要传给这个
  pipeline 的 CLI，传了会直接报参数错误。
- **`--image` 的真实格式是 `PATH FRAME_IDX STRENGTH [CRF]`**（三个必填位置
  参数），不是裸路径。首帧用 `PATH 0 1.0`；尾帧用
  `PATH <num_frames-1> 1.0`。
- **`--num-frames` 必须是 `8*k+1`**（比如 73/97/121/145），传其他值会被
  拒绝或行为不可预测；按目标秒数估算后要吸附到最近的合法值。
- **非交互式 SSH 命令不会加载 `~/.bashrc`**，`uv` 装在 `~/.local/bin/` 时
  PATH 里找不到，必须显式 `export PATH=$HOME/.local/bin:$PATH &&` 再执行。
- **diffusion VAE 解码器（`ltx-2.5-video-vae-bf16.safetensors`，natten
  后端）在 Blackwell 显卡（compute_cap 12.0，比如 RTX PRO 6000 Blackwell）
  上实测触发 `CUBLAS_STATUS_INTERNAL_ERROR` / `illegal memory access`**，
  发生在最后的视频解码阶段（说明扩散采样本身是通的，问题在解码 kernel 的
  显卡兼容性）。换成**卷积版 VAE**（`ltx-2.5-video-vae-conv-bf16.safetensors`，
  "轻量、不需要额外依赖"）后同样的 job 直接跑通，成片质量（人脸一致性、
  情绪弧线、竖屏构图）实测良好。**在新架构/小众显卡上，优先直接用卷积版
  VAE，不要先试 natten 版再踩坑**。
- 竖屏 9:16（测试档 704×1280）实测确认输出真的是竖屏，没有被模型内部裁成
  横屏——这条之前文档里标注"官方未验证"，现已用真实生成结果验证通过。

## 用法

1. 确认远程机器已经装好 `Lightricks/LTX-2` 仓库、下载好模型权重、能跑通
   官方 README 的最小示例。
2. 复制一份 `ltx_remote_config.json`（下方模板），根据远程机器实际情况填：
   ```json
   {
     "ssh_host": "root@<ip>",
     "ssh_port": 22,
     "ssh_key": "~/.ssh/id_ed25519",
     "remote_repo_dir": "/workspace/LTX-2",
     "remote_work_dir": "/workspace/jobs",
     "pipeline_module": "ltx_pipelines.distilled",
     "pipeline_extra_args": [
       "--transformer-path", "models/ltx-2.5/diffusion_models/xxx.safetensors",
       "--text-encoder-path", "models/ltx-2.5/text_encoders/xxx.safetensors",
       "--video-vae-path", "models/ltx-2.5/vae/xxx.safetensors"
     ],
     "python_bin": "python"
   }
   ```
   `pipeline_module` 和 `pipeline_extra_args`（模型权重路径）**必须由用户在
   远程机器上先确认过实际路径**，本 skill 不知道用户把权重下载到了哪里，
   不要瞎猜路径直接跑。
3. 按 `video_jobs_schema.md` 的 JSON 格式准备 `video_jobs.json`，额外补充
   LTX 需要的字段：`width`、`height`（像素，需 64 整除）、可选
   `num_frames`（不填就按秒数估算）、可选 `seed`（复现同一个结果时用）。
4. 先小范围测试：
   ```bash
   python3 .claude/skills/short-drama-video-gen/scripts/ltx_ssh_submit.py \
     --config ltx_remote_config.json \
     --jobs output/<故事名>/videos/ep0X/video_jobs.json \
     --out-dir output/<故事名>/videos/ep0X \
     --only 11 --dry-run
   ```
   `--dry-run` 只打印将要执行的远程命令，不实际连接，先确认命令拼得对不对
   （尤其是 `pipeline_extra_args` 里的权重路径），再去掉 `--dry-run` 真跑。
5. 每跑完一个镜头，按 `SKILL.md` 第 6 步用 `extract_frames.py` 抽帧验收，
   不合格按 `stability_playbook.md` 调整提示词/参数重新提交，不要连续
   失败还硬跑下一个镜头。
