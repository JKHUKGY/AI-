# 路线与官方依据

核验日期：2026-09-05。能力和参数仍需执行时复核，表中成熟度是工程判断，不是成功率。

| 路线 | 输入→输出 | 有助于什么 | 没有解决什么 |
|---|---|---|---|
| Depth Anything V2 + 2.5D | 单图→相对深度→可见表面的点云 | 低成本小幅视差/运镜控制 | 被遮挡区域、真实尺度、角色动作 |
| SHARP | 单图→3D高斯 | 原机位附近视角合成 | 完整360度房间、带骨骼角色 |
| Marble | 图片等→生成的环境 | 更大空间和多机位可探索场景 | 生成的背面未必符合原设定，人物能力有限 |
| TRELLIS.2 / Hunyuan3D | 单图→3D物体/材质 | 道具、角色外形资产 | 自动场景拆分、拓扑整理、骨骼绑定与表演 |
| Blender简化场景 | 人工/脚本安排位置、替身和相机→渲染通道 | 走位、接触、遮挡、镜头复用 | 仍需美术参考与视频模型重建外观 |
| LTX Union Control | 首图+深度/轮廓/姿态序列→视频 | 有明确结构输入的条件生成 | 像素级绝对约束、必然首轮通过 |
| LTX Motion Control | 首图+稀疏轨迹→视频 | 轻量物体/区域运动指示 | 多关节动作与准确3D遮挡 |
| H3 Ref2VA | 多模态参考+结构提示→音视频 | 动作/运镜参考、分镜顺序和节奏 | 原生逐帧深度输入的保证 |
| Wan VACE | 参考图、控制片、掩膜→视频 | 另一条结构控制/编辑路径 | 自动优于当前LTX画质或性能的保证 |

## 官方入口：按所选路线读取

- [Depth Anything V2官方代码](https://github.com/DepthAnything/Depth-Anything-V2)：本示例用Small相对深度；[HF模型](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf)。Small与更大版本许可证可能不同，替换前核对。
- [Apple SHARP](https://github.com/apple/ml-sharp)：nearby views；可输出PLY高斯，其渲染依赖与普通彩色点云不同。
- [Marble图片输入](https://docs.worldlabs.ai/marble/create/prompt-guides/image-prompt)：明确指出人和动物支持有限；[Record](https://docs.worldlabs.ai/marble/create/studio-tools/record)介绍相机关键帧与视频导出。
- [TRELLIS.2](https://github.com/microsoft/TRELLIS.2)、[Hunyuan3D-2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)：物体和材质生成。
- [LTX Union Control](https://docs.ltx.io/open-source-model/feature-guides/structural-control/union-control)、[Motion Control](https://docs.ltx.io/open-source-model/feature-guides/structural-control/motion-control)、[IC-LoRA素材说明](https://docs.ltx.io/open-source-model/usage-guides/ic-lo-ra)。
- [LTX Python代码](https://github.com/Lightricks/LTX-2)：检索 `ic_lora.py`、`video-conditioning`、`reference_downscale_factor`、`images`。不要只看ComfyUI文档就推断旧CLI支持。
- [LTX官方ComfyUI工作流](https://github.com/Lightricks/ComfyUI-LTXVideo/tree/master/example_workflows/2.5)：默认Union工作流选一种annotation，不代表深度/pose/canny同时叠加已验证。
- [H3模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)、[Ref2VA指南](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)：区分参考模式和首尾帧模式。
- [VACE官方代码](https://github.com/ali-vilab/VACE)：已有depth和mask路径，可作备选实验。

## LTX控制接入容易漏掉的环节

2026-09-05核对的Python `ic_lora` 支持首图与控制视频共存。Union checkpoint的 `reference_downscale_factor=2` 需要按实际metadata处理；不要在外部先降采样一次、内部再错误降一次。

当时的示例参数名是 `--image PATH 0 1.0`、`--video-conditioning PATH STRENGTH`、`--lora PATH STRENGTH`，其余主模型、VAE、编码器和采样参数以目标checkout的 `--help` 为准。两阶段pipeline可能先用目标一半分辨率生成，再放大；记录实际控制编码大小，过低会丢失桌沿、手指等细节。

控制片无需再经过视频估深。灰度/深度数值只描述空间，RGB原图才提供主要外观锚点。几何辅助不能单独保证脸、服装、口型和细小道具的身份。

### 可复用推理入口

本包 `scripts/run_ltx_variant.py` 在已配置的官方LTX环境里运行一条A或B，默认只校验/打印计划，显式 `--execute` 才推理。它不租卡或关卡；调用方必须在finally中执行原有GPU收尾。不要在没有收尾执行器时丢到远程后台无人看管。

```bash
python SKILL_DIR/scripts/run_ltx_variant.py --jobs video_jobs.json --weights weights.json --first-frame first_frame.png --control-video depth_control.mp4 --out-dir results --variant B
```

`weights.json` 必填已存在的 `transformer_path`、`text_encoder_path`、`video_vae_path`、`audio_vae_path`、`spatial_upsampler_path`、`union_lora_path`；相对路径按该JSON所在目录解析。可附 `revisions` 记录checkpoint来源，脚本将其标为声明值，不假装已联网核验。路径配置不含账号或token。

推理环境需有Pillow及ffprobe或PyAV；预检优先ffprobe，缺失时用官方LTX环境已有的PyAV读视频元数据。运行时记录分别写入A/B runtime JSON；dry-run打印计划且generation_calls=0，不算生成成功。

本次接入发现的明确风险：官方main使用 `torch.inference_mode()`，直接调用公开API时也必须覆盖模型构建、调用和 `encode_video` 消费惰性结果的全过程；遗漏会出现推理张量反向保存错误，也可能影响内存。脚本已包含此上下文及CPU卸载，但实际峰值仍需以所选硬件、时长、VAE和分辨率测试，不能把“80GB”写成通用保证。
