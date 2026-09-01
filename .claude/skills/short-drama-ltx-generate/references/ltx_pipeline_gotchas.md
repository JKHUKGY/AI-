# LTX-2.5（Lightricks LTX-2 仓库）CLI 参数实测记录

> 持续更新。官方仓库还在迭代，这里记的是**用 `--help` 和源码实测确认过**的
> 结论，不是抄文档——文档和实际 CLI 有出入的地方已经在下面标注。新开一集
> /新参数之前，先跑一遍对应 pipeline 的 `--help` 现场核实，不要直接照抄这
> 份文档里的参数名当成永久事实。

## 推理入口

官方仓库是 `Lightricks/LTX-2`（monorepo：`ltx-core`/`ltx-pipelines`/
`ltx-trainer`），推理通过 `python -m ltx_pipelines.<pipeline名>` 调用。
**LTX-2.5 是官方当前推荐模型**。常用 pipeline：

- `ltx_pipelines.distilled` —— 最快，图生视频/文生视频的默认起点（本仓库
  实际在用的）
- `ltx_pipelines.dfr_pipeline` —— 生产质量，更慢更吃显存
- `ltx_pipelines.keyframe_interpolation` —— 首尾帧插值
- `ltx_pipelines.dubit` —— 配音（保持说话人音色，见下方"角色配音一致性"）
- `ltx_pipelines.a2vid_two_stage` —— 音频驱动视频生成

## 官方文档 + 社区实测交叉验证的共识（2026-08 调研，供判断"哪些是真限制/
哪些是产品层面限制"）

查了 LTX-2.5 官方 Hugging Face README、官方 ComfyUI 工作流仓库，以及多篇
第三方实测教程（fal.ai、earngenix 等）后交叉核对出的结论，凡是跟本仓库自己
`--help`/实测冲突的地方，**以本仓库自己的实测为准**，下面只记差异点和互相
印证的地方：

- **distilled 是固定 8 步、CFG=1**（官方 Diffusers README 原文："Fixed
  8-step schedule, CFG=1"），跟本仓库 CLI 不暴露 steps/CFG 参数这件事互相
  印证——**不是遗漏，是这个 pipeline 设计上就不需要调**。网上教程讨论"把
  CFG 调到 3.0-3.5"说的是 dev/full 完整模型，跟我们用的 distilled 无关，
  不要照抄过来给 `pipeline_extra_args` 加 CFG 相关参数。
- **`--num-frames` 必须 8k+1**：官方 Diffusers 文档表述为
  `num_frames % 8 == 1`，跟本仓库实测的"8*k+1"是同一件事，互相印证，
  可信度高。
- **宽高整除**：官方 Diffusers 文档要求"能被 32 整除"，本仓库
  `references/resolution_presets.md` 按更保守的 64 整除（64 的整数一定
  也是 32 的整数，不冲突）——继续用 64 整除的预设表，不要因为看到官方写
  "32"就去用只满足 32 不满足 64 的尺寸，没有必要冒这个险。
- **单次生成时长不是卡在几秒**：fal.ai 等**托管 API 产品**把单镜时长限制
  在 6-20 秒档位可选，那是**产品 UI 层面的限制**，不是模型/pipeline 本身
  的硬上限——本仓库在自建通道上已经用 `ltx_pipelines.dfr_pipeline` 实测
  跑通 15 秒（361 帧）无质量衰减（见下方"DFR pipeline"一节），**不要被
  托管平台的档位选项误导，以为自建通道也必须把镜头切得很短**，镜头该多长
  按叙事需求和分段拼接策略（`short-drama-video-gen/references/
  stability_playbook.md`）决定，不是被这个数字限制住。
- **`--enhance_prompt`（官方"提示词自动增强"选项）不要用**：这是官方
  CLI 提供的可选功能，用于把简略提示词自动扩写；但多篇第三方实测反馈这个
  功能表现不稳定，容易改写偏离原意。本仓库的提示词在
  `short-drama-video-gen` 阶段就已经手写成完整详细的正向/负面提示词（见
  `video_prompt_guide.md`），属于"已经写得很详细"的场景，跟"提示词太
  简略需要自动扩写"的适用场景不符——**不要给 `pipeline_extra_args` 加
  `--enhance_prompt`**，除非用户明确要单独测试这个功能本身。
- **帧率维持默认 24fps，不要跟风调高**：模型能力上支持到 50fps，但多篇
  第三方实测的共同经验是**含台词/对白的镜头维持 24-25fps 表演质感更自然**，
  帧率拉到 50fps 会让画面偏向"电子游戏录屏感"，对短剧这种强调表演/台词的
  内容是减分。本仓库脚本（`ltx_ssh_submit.py`）目前 `fps` 只用来把
  `duration_sec` 估算成 `num_frames`，并没有单独的 `--fps` 参数传给
  pipeline；如果未来某个 pipeline 版本加了这个参数，短剧对白镜头默认还是
  留 24，不要因为"模型能到 50"就顺手调高。
- **图生视频（`--image` 条件生成）常见的提示词坑**：多篇第三方实测都提到
  同一个问题——提示词里如果把首帧图里已经有的静态内容（人物穿着、发型、
  背景陈设）又用文字重新描述一遍，容易跟"图像条件"打架或被模型忽略，
  导致生成结果偏离首帧。**提示词应该只写变化量**（动作、表情变化、镜头
  运动、光影变化），静态内容已经由首帧图本身提供，不需要在文字里重复。
  这条本质是 `short-drama-video-gen` 的提示词撰写方法论，但在
  `short-drama-ltx-export` 校验阶段如果看到某镜提示词大段在复述画面已有
  的静态内容而几乎没写动作变化，应该提醒用户回头检查，不要照抄硬导出。

## 生成质量丢分的三大常见诱因（验收不通过时先对照这三条排查）

多个独立来源（官方文档的"已知限制"章节 + 第三方实测教程）反复提到同样
几类"最容易翻车"的原因，验收环节（`SKILL.md` 第 5 步）生成结果不对时，
先看是不是踩了这三条，再去查显卡/环境问题：

1. **宽高比/分辨率传错**：`video_jobs.json` 里某镜漏填了 `width`/`height`，
   导致这一镜实际用了 pipeline 的默认值（`1536×1024`，横屏），短剧要的
   竖屏结果直接变形/构图错乱。`short-drama-ltx-export/scripts/
   validate_video_jobs.py` 已经会自动核对 `aspect_ratio` 字段和实际
   `width`/`height` 比例是否吻合，正常走完校验流程理论上不会漏这个；如果
   还是出现了，说明校验之后又有人手动改过 JSON 没有重新校验，先确认
   校验脚本是不是被跳过了。
2. **CFG 相关的参数**（仅当以后换用 dev/full 完整模型时才适用）：CFG
   调过高会让画面过度锐化、色彩失真；distilled 目前没有暴露这个开关，
   这条现阶段用不上，但换 pipeline 时要留意，不要凭经验瞎调。
3. **提示词堆砌/自相矛盾**：同一条提示词里塞太多互相冲突的描述（比如
   正文写"镜头缓慢推进"，备注又要求"固定机位不能动"），模型会在两者间
   取一个不可预测的折中结果。这条需要回 `short-drama-video-gen` 阶段
   精简/消歧提示词，不是本 skill 能在导出/生成阶段修的。

## 实测确认的参数陷阱（`ltx_pipelines.distilled`，2026-08）

- **`--negative-prompt` 这个参数根本不存在**（`--help` 实测确认），不是
  "部分 pipeline 不支持"，是这个 pipeline 压根没有这个字段。负面提示词
  只能留在 job 数据里给人看，传给 CLI 会直接报参数错误。
- **`--image` 的真实格式是 `PATH FRAME_IDX STRENGTH [CRF]`**（三个必填
  位置参数，`--help` 原文：`Image conditioning input: PATH FRAME_IDX
  STRENGTH [CRF]`），不是裸路径。首帧锁定用 `PATH 0 1.0`；尾帧用
  `PATH <num_frames-1> 1.0`，可以传多次 `--image` 同时给首尾帧。
- **`--num-frames` 必须是 `8*k+1`**（k 为非负整数，比如 73/97/121/145），
  传其他值行为不可预测。按目标秒数估算后要吸附到最近的合法值——
  `ltx_ssh_submit.py` 已经内置了这个吸附逻辑（`_nearest_8k_plus_1`），
  自己写脚本调用时不要漏掉这一步。
- **`--seed` 默认值是 10**，不传就复现同一个种子，不是真随机；要不同结果
  需要显式传不同的 `--seed`。
- **`--width`/`--height` 默认 1536×1024（横屏）**，需能被 64 整除。竖屏
  9:16（比如测试档 704×1280）**实测确认真的输出竖屏**，没有被模型内部
  裁成横屏——这条之前没人验证过，现在有真实生成结果为证。
- **显存不够时**：`--quantization fp8-cast --offload {cpu,disk}` 能降低
  占用但会变慢；96GB 显存跑测试分辨率完全用不上这些参数。

## 环境搭建踩坑

- **非交互式 SSH 命令不会加载 `~/.bashrc`**，`uv` 装在 `~/.local/bin/`
  时 PATH 里找不到，必须在远程命令前显式
  `export PATH=$HOME/.local/bin:$PATH &&`。`ltx_ssh_submit.py` 已经在
  拼接远程命令时自动加了这一段，自己手动 SSH 调试时别忘了也加。
- **Hugging Face 权限**：LTX-2.5 是 gated repo，下载前要在网页上 accept
  模型条款，再用 `hf auth login --token <TOKEN>`（Read 权限即可）登录，
  否则 `hf download` 会 401/403。
- **模型权重约 66GiB**，5 个文件（transformer/text_encoder/video_vae/
  audio_vae/spatial_upsampler），官方 CLI 下载命令走 `hf download
  Lightricks/LTX-2.5 <文件路径...> --local-dir models/ltx-2.5`，实测在
  高带宽机器上只要 1-2 分钟。

## VAE 后端显卡兼容性（新架构显卡尤其要注意）

- **diffusion VAE 解码器**（`ltx-2.5-video-vae-bf16.safetensors`，natten
  神经网络注意力后端）在 **Blackwell 架构显卡**（compute_cap 12.0，比如
  RTX PRO 6000 Blackwell WS）上实测触发
  `CUBLAS_STATUS_INTERNAL_ERROR` / `illegal memory access`，发生在最后的
  视频解码阶段（扩散采样本身是通的，问题在解码 kernel 的显卡兼容性，不是
  显存不够）。
- **换成卷积版 VAE**（`ltx-2.5-video-vae-conv-bf16.safetensors`，官方标注
  "轻量、不需要额外依赖"）后同样的 job 直接跑通，成片质量（人脸一致性、
  情绪弧线、竖屏构图）实测良好。
- **建议**：在新架构/小众显卡（尤其是 Blackwell 系列消费卡/工作站卡）上，
  第一次跑就直接用卷积版 VAE，不要先试 natten 版再踩坑排查——两者效果
  差异在实测中不明显，但兼容性风险差很多。

## DFR pipeline（生产质量档）实测记录（2026-08）

- `--detailing-lora PATH [STRENGTH ...]` 是**必填项**（`--help` 里没有
  被方括号包住），需要单独下载
  `Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler` 仓库的权重
  文件——**这是一个独立于主仓库的 gated repo**，用户需要在这个仓库自己的
  HuggingFace 页面上单独点一次"同意条款"，跟主仓库 `Lightricks/LTX-2.5`
  的授权是两回事，同一个 token 但要两次网页确认，不要以为主仓库同意过就
  自动覆盖这个。
- 除了 `--detailing-lora`，其余参数（`--image` 三段式、无
  `--negative-prompt`、`--num-frames` 需 8k+1）和 `ltx_pipelines.distilled`
  一致。
- **实测跑通 15 秒（361 帧）、1600×896 分辨率的纯文生视频**（无 `--image`
  条件），在 RTX PRO 6000 Blackwell（96GB 显存）上用卷积版 VAE 顺利生成，
  耗时明显比 121 帧的短镜头长，但没有出现 VRAM 溢出或随时长明显崩坏/漂移
  的问题，人物身份、光影连续性全程保持良好。之前担心的"长镜头质量是否
  会随时间衰减"这个顾虑，在这次实测里没有出现。
- 日志里会出现一条 `keyframe-anchored decoding needs a diffusion VAE.
  Decoding without them.` 的提示——这是因为用了卷积版 VAE（不支持
  DFR 的"关键帧锚定解码"特性），**只是信息提示，不是报错**，视频照常
  正常生成，成片质量在这次实测里没有看出明显影响。

## 官方文档记载、本仓库尚未验证/尚未完全接入的能力（2026-09 调研）

查官方 GitHub 仓库（`README.md` + `packages/ltx-pipelines/docs/pipelines.md`
+ `docs/installation.md`，一手源码仓库、可信度高）和 HuggingFace/官方博客
的二手摘要（`ltx.io/blog/*` 直接抓取遇到 `Header overflow`，只能靠搜索引擎
摘要，措辞不保证跟原文完全一致，第一次要用之前建议换工具重新抓一次原文核
对准确措辞）后，梳理出的 pipeline 家族比本仓库目前用到的更全，记下来避免
以后重新调研一遍：

- **`ltx_pipelines.retake`（局部重绘，本仓库 2026-09 已接入
  `ltx_ssh_submit.py --retake`）**：只重新生成一段已有视频里指定的时间
  窗口 `[--start-time, --end-time]`，其余部分保持不动，据称可独立控制
  `regenerate_video`/`regenerate_audio`。这条命中 `loop-video-generation`
  最大的浪费点——之前 Reviewer 发现"只有某几秒有问题"也要整段重来。**参数
  名尚未用 `--help` 实测确认**，`ltx_ssh_submit.py` 里的 `build_retake_cmd`
  是按文档 best-effort 拼的，第一次用先跑
  `python -m ltx_pipelines.retake --help` 核对，报参数错误就照 `--help`
  输出改这个函数，别猜。
- **`ltx_pipelines.keyframe_interpolation` 支持任意数量关键帧**，不只是
  首尾两张——`short-drama-video-gen` 的"起始姿态→过程关键点→结束姿态"三段
  式目前"过程关键点"只有文字描述，没有对应的图像锚点。如果以后想让这个
  中间关键点也有真实图像约束，需要 `short-drama-keyframe-gen` 先出一张
  "过程关键点"关键帧图，再换用这个 pipeline，而不是现在这样只给首尾帧、
  中间纯靠文字描述赌运气。**目前没有接入，是一个需要额外改
  keyframe-gen 产出物的更大改动，先记录不急着做。**
- **IC-LoRA 家族（相机控制 Canny/Depth/Pose、`Camera-Control-Static`、
  Ingredients 单图参考表、Multi-Subject Reference LoRA 最多5张独立参考图、
  Motion-Track-Control 轨迹样条）**：官方给的结构性一致性/运镜控制机制，
  跟本仓库现在"全靠文字描述赌运气"的做法是两条完全不同的路。需要额外下载
  对应 LoRA 权重、改 `ltx_remote_config.json` 结构支持 `--lora` 参数、换成
  `ltx_pipelines.ic_lora` 调用方式，工程量不小，**目前没有接入**，值得
  以后单独评估要不要投入，不建议顺手绑进现有 skill 流程里。
- **`ti2vid_two_stages`/`_hq`**：这两个 pipeline 才有 CFG/STG guidance，
  能承载负面提示词式的对抗引导——本仓库在用的 `distilled`/`dfr_pipeline`
  **没有**这个机制，之前写"这个 pipeline 没有负面提示词"是准确的，但容易
  被误读成"整个 LTX-2.5 都不支持"，这里澄清一下：只是我们选的这两个
  pipeline 没有，不是模型整体没有。如果某类瑕疵在 distilled/dfr 上反复
  出现同一种问题，`ti2vid_two_stages` 系列可以作为升级选项评估，**目前
  没有接入**。
- **DFR 的 `--temporal-upscalings{0,1,2}`/`--spatial-upscalings{1,2}`**：
  理论上可以对已经验证过的测试档结果做时间/空间维度放大，比
  `loop-video-generation` 现在"正式档确认"整段重新生成一次更省钱，**目前
  `ltx_ssh_submit.py` 没有接这两个参数**，先记录，等以后有精力接的时候
  参考这条。
- **`ref_images` 字段是死代码**：`video_jobs_schema.md`/各 skill 文档里
  写的"额外一致性参考图"这个字段，`ltx_ssh_submit.py` 从来没有读取或上传
  过它，只处理 `first_frame`/`last_frame`。已经在脚本和相关文档里补了
  提醒；真正的多参考图机制就是上面 IC-LoRA Ingredients/Multi-Subject
  Reference LoRA，接入前不要假装这个字段有效果。

## 角色配音一致性（2026-08 查文档+源码，尚未实测）

LTX-2.5 会根据提示词自动生成同步音频（见
`short-drama-video-gen/references/video_prompt_guide.md` 的"关于台词/
对白"一节），但**每次生成是独立过程，不保证跨镜头音色一致**。官方提供
两条解决路径（已用源码 argparse 定义交叉确认，参数名可信，但效果本身
没有在本仓库实测过，用前先小范围验证）：

1. **`ltx_pipelines.dubit`（DubItPipeline）**：给一段 `--reference-video`
   （必填，视频+音频文件，音色身份和帧数/帧率都从这个文件来），配上新的
   `--prompt` 台词，重新生成对口型视频，同时保持参考视频里的说话人音色。
   还需要 `--reference-strength`（默认1.0）、`--spatial-upsampler-path`
   （必填）、`--lora <Dub-It专用IC-LoRA路径>`（必填，需单独下载
   `Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler` 仓库或对应
   Dub-It LoRA）。**适合场景**：已经生成过一段该角色说话效果好的镜头，
   想让同一角色在其他镜头里保持相同音色。
2. **`ltx_pipelines.a2vid_two_stage`（A2VidPipelineTwoStage）**：
   `--audio-path`（必填）传入你自己准备好的固定音频文件（比如用专门的
   中文 TTS/声音克隆工具提前配好台词）。源码确认**输出视频的音频轨道是
   原始输入波形，模型不会重新生成音频**，所以音色 100% 由外部音频决定，
   不存在"是否一致"的问题，代价是需要额外的配音工具生成输入音频。

选择建议：已经有一段效果不错的角色语音镜头 → 用 DubIt 复用音色；没有
现成素材、想要完全掌控音色/使用真人配音 → 用 A2Vid 外挂音频。两条路都
**没有中文台词的实测验证**，第一次使用建议先对 1 个镜头测试，确认效果
可用再批量套用到其他镜头。

## 说话类镜头会把复杂/负面情绪收敛成通用笑容（2026-09 实测，多镜头交叉确认）

`ltx_pipelines.distilled` 生成带台词的镜头时，如果目标情绪不是简单的
"平静/生气"这类单一情绪，而是**混合或克制型情绪**（苦笑带泪、阴阳怪气的
冷笑、强忍酸楚的笑），模型有明显倾向把结尾表情收敛成一个**通用的、真心
开怀的大笑/露齿笑**，即使正向提示词已经写清楚具体的目标表情、负面提示词
也明确排除"大笑/露齿笑/开心表情"。

**已确认的案例**（《出狱后我成为了非洲矿王》ep01）：
- 镜14（苏慧"含泪强忍的酸楚笑"）：3轮不同措辞都没能达成，模型稳定给出
  "开心大笑"。
- 镜18（刘兰"嘴角轻蔑上扬的冷笑，眼皮不抬阴阳怪气"）：3轮里最后一轮
  把负面提示词加强到"嘴唇基本闭合、不露牙齿、任何形式的笑容都不要"这么
  具体，依然收敛成开怀露齿笑。

**建议**：这类"目标表情是克制/负面但台词内容本身语气偏日常"的镜头，跑满
`stability_playbook.md`"最多3轮"上限仍未解决时，不要继续加大负面提示词
力度硬扛（已验证无效），可选替代方案：
1. 接受这个替代效果，情绪精度让位给动作/音频的正确性，如实记录差距。
2. 换用非台词驱动的静态表情（把这一镜降级处理，不生成说话音频，只做
   表情/微动作，配音在剪辑阶段单独叠加），绕开"台词驱动"这个触发条件。
3. 换 pipeline（比如 `ltx_pipelines.dfr_pipeline` 生产质量档）测试是否
   有同样倾向——本仓库目前只在 distilled pipeline 上验证过这个问题，
   没有跨pipeline对比数据。
