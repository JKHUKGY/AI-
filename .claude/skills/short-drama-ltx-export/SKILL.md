---
name: short-drama-ltx-export
description: 面向自建 LTX-2.5（Lightricks LTX-2）图生视频通道的提交前关卡：short-drama-video-gen 的 build_prompt.py 已经从镜头卡（shot_cards.json）直接装配出 video_jobs.json，所以这个 skill 不做"从 Markdown 表格转录"的工作，而是**提交前的最后一道校验关卡**——跑 validate_video_jobs.py 逐条查路径存在性、64 整除、8k+1、台词语言声明、seed 有效性、prompt token 预算、正向提示词里的否定句残留、first_frame_strength 是否偏离实测确认的 1.0、以及 prompt 是否还和镜头卡装配结果一致（防止有人手改 JSON 绕过镜头卡），核对拆段单元的首帧是否已经落地，检查/生成 ltx_remote_config.json，最后跑一次 ltx_ssh_submit.py --dry-run。老项目只有 video_jobs.md 没有镜头卡时，退回"引导补齐镜头卡"而不是自己抠字段。当用户说"把这些整理成能交给LTX的文件""校验video_jobs.json""打包提交给LTX2.5""这一集的提示词整理成能跑的文件"时使用。**这一批要用 MiniMax-H3 就去 minimax-h3-export，不要用这个**——H3 的提示词是完全不同的六段结构化格式，校验规则也不一样。
---

# AI 短剧 LTX-2.5 提交文件打包助手 (short-drama-ltx-export)

承接 `short-drama-video-gen` 之后的**提交前最后一道关卡**。

**2026-09 变更**：`short-drama-video-gen` 现在维护结构化的镜头卡
（`shot_cards.json`），并用 `scripts/build_prompt.py` 直接装配出
`video_jobs.json` —— 连 LTX 专属字段（`width`/`height`/`num_frames`/`seed`）
一起装配好。所以本 skill **不再做"从 Markdown 散文表格里逐字段抠出来、
补齐缺的字段"这件事**（那一步已经不存在了），职责收窄成三件：

1. **校验** `video_jobs.json` 能不能被 `ltx_ssh_submit.py` 直接消费，
   并且还和镜头卡对得上。
2. **检查/生成** `ltx_remote_config.json`。
3. **`--dry-run`** 验证一遍。

这个 skill **只负责校验文件**，不负责真正发起 SSH 生成——那是
`short-drama-ltx-generate` 拿到本 skill 的产出后去掉 `--dry-run` 真跑的事。

## 0. 先确认这一批用的是 LTX-2.5

**本 skill 只管 LTX-2.5。** 用户说要用 MiniMax-H3，或者
`shot_cards.json` 同目录已经有 `h3_remote_config.json`，
**转去 `minimax-h3-export`**，别在这里硬凑——两个模型的提示词格式、
校验规则、提交方式完全不同。

替用户判断的几条：

- **这一集已经有跑通的 LTX 成片、只是补几镜** → 继续 LTX。两个模型的质感、
  人脸、镜头语言都不一样，同一集混用会穿帮。
- **需要台词真的出声** → 只能 H3。LTX 这条链是无声的，配音要另做。
- **单元短于 4 秒** → H3 生不出来（帧数只能取 17n+5），这几镜只能走 LTX。
- **想省显卡钱** → 反而是 H3 便宜：SGLang 有 1×RTX 4090 24GB 的实测配方
  （$0.34/hr），LTX 我们实测要 80GB（$1.19–1.59/hr）。

选定之后把结果写进 `ltx_remote_config.json` 的 `model` 字段（`"ltx-2.5"`），
下游 `short-drama-ltx-generate` 读它确认没走错通道。

## 1. 先确认这次针对哪一集/哪几镜

不要一次性把全剧都打包，按用户指定的集数（`epNN`）处理；如果用户说"这几镜"，
只处理指定镜号，其余镜头保留在已有的 `video_jobs.json`（增量更新，不要覆盖
掉别的镜头已经校验过的记录）。

## 2. 确认输入齐不齐

- `output/<故事名>/videos/ep0X/shot_cards.json` + 由它装配出来的
  `video_jobs.json`——`short-drama-video-gen` 的产出，本 skill 的主要数据源。
  **两个都要有**：只有 JSON 没有卡的话，"prompt 是否还和卡一致"这条校验
  查不了，等于给手改 JSON 开了后门。
- **老项目只有 `video_jobs.md`、没有 `shot_cards.json` 时**：不要自己从
  Markdown 里抠字段拼 JSON（那正是被这次改动废掉的流程，也是历史上漏写
  语言声明、漏填 seed 的来源）。回 `short-drama-video-gen` 把镜头卡补出来
  再回来。存量已经跑通并确认过的镜头例外——那些不用回填，直接留着，只是
  别再拿它们当新镜头的模板。
- `output/<故事名>/keyframes/ep0X/keyframes.md`——核对首帧路径确实是选中的
  关键帧文件，两边对不上时以 `keyframes.md` 为准并提醒用户。
- `output/<故事名>/assets/selected.md`——核对一致性参考图路径。
- 如果 `output/<故事名>/videos/ep0X/ltx_remote_config.json` 已存在，读出来
  确认 `pipeline_module`/权重路径没有变化；不存在则见第 5 步问用户要，
  **不要瞎猜**。

## 3. 确认这批 job 的范围和档位

`video_jobs.json` 已经是装配好的，这一步只做三件核对，**不改内容**：

1. **范围**：这次要提交哪几条。不承载新台词/新情节的 C 级复用镜头、以及
   因反复生成失败降级为本地 `ken_burns.py` 兜底的镜头不进本次提交；
   **B 级镜头跟 S/A 级一样正常提交**，不要看到"B 级"就当跳过项。如果发现
   某条 C 级被标了跳过、但 `ep0X.md` 这一镜的台词/旁白列有新内容，先提醒
   用户这一镜分级可能标错了。
2. **档位**：这批是测试档还是正式档。测试/正式两档的 `width`/`height`
   （和可选的更短 `num_frames`）不同，来自镜头卡上填的值——**先问用户要
   哪一档**，要两档就让 `short-drama-video-gen` 分别装配两份，不要自己在
   这里改 JSON 的分辨率。可用尺寸表见 `references/resolution_presets.md`。
   第一次跑通某镜之前优先测试档。
3. **拆段单元的首帧是否已经落地**：卡上写 `first_frame_from` 的单元
   （比如 `ep01_镜06_u2` 的首帧来自 `ep01_镜06_u1:last`），必须先把上一段
   生成出来、用 `short-drama-video-gen/scripts/extract_frames.py` 抽出尾帧、
   把真实路径填回卡的 `first_frame` 并重跑装配，才能提交。第 3 步的校验
   会因为"`first_frame` 缺失"直接报错——这是**设计如此**，不是 bug。

**发现内容层面的问题（提示词写得不对、时长不够、动作描述笼统），回
`short-drama-video-gen` 改镜头卡再重跑 `build_prompt.py`，不要在这里手改
`video_jobs.json`。** 手改会让 `prompt` 和卡脱钩，第 3 步的一致性校验会拦
下来，而且下次装配就把手改的内容冲掉了。

## 4. 校验（本 skill 的核心）

跑校验脚本，不要跳过这一步：

```bash
python3 .claude/skills/short-drama-ltx-export/scripts/validate_video_jobs.py \
  output/<故事名>/videos/ep0X/video_jobs.json
```

脚本检查（详见脚本头部注释，规则不在这里重复）：

- 必填字段齐全；`first_frame`/`last_frame`/`ref_images` 引用的文件本地真实存在
- `width`/`height` 被 64 整除；`aspect_ratio` 跟实际比例吻合（防止漏填分辨率
  悄悄退回 pipeline 默认横屏 `1536×1024`）；`num_frames` 满足 `8k+1`
- `prompt`/`negative_prompt` 里没有残留占位符
- **有台词的镜头，`prompt` 里有显式语言声明**（`Mandarin Chinese`/中文/普通话）
- **`seed` 填了、而且不是 LTX 的默认值 10**
- **`prompt` 的 token 估算没超工作预算**（Gemma 上限 1024，**超了静默截尾**）
- **`prompt` 里没有残留否定句**（distilled pipeline 没有 `--negative-prompt`
  参数，否定句只会注入不想要的概念）
- **`prompt` 还和镜头卡的装配结果一致**（同目录有 `shot_cards.json` 且 job 带
  `shot_card_id` 时才查）。探针/对照组要故意偏离时，在 job 上加
  `prompt_variant` 写明理由，这条就降成 WARN
- **有运镜的镜头，`rig` 里不许再写 `locked off`**（`build_prompt.py` 在装配层
  就 ERROR 拦）。历史上 v2 ep01 的 40 张卡 40/40 都写着 `locked off`，其中 5 张
  同时要求 push-in，装配出一句锁死机位、下一句要推镜的互斥提示词——见 ledger A6
- 台词字数和 `duration_sec` 是否匹配

后面这几条每一条都对着一个**已经付过代价**的实测故障，依据全部集中在
`short-drama-video-gen/references/model_capability_ledger.md`。拿存量项目
跑一遍能看到它们确实抓得住：`output/出狱后我成为了非洲矿王/videos/ep01/`
会报出 18 条缺语言声明、9 条 seed 问题（7 条缺 + 2 条留成 10）、4 条正向
提示词里残留否定句、22 条无效的 `negative_prompt`。

**校验报错就回 `short-drama-video-gen` 改镜头卡再重跑装配**，不要手动改
JSON 把报错糊过去（比如路径不存在就编一个假路径让脚本通过）——这种"通过
校验"没有意义，SSH 提交时一样会失败。

存量项目（已经跑通并确认过的镜头）报出来的问题**只汇报、不回填**，避免动到
已确认通过的产物；把清单给用户看，由用户决定要不要返工。

## 5. 检查/生成 `ltx_remote_config.json`

- 已存在：读出来给用户看一眼当前的 `ssh_host`/`pipeline_module`/权重路径，
  确认没有变化（比如换了台显卡机器）。
- 不存在：按 `short-drama-ltx-generate/references/runpod_gpu_ops.md` 和
  `ltx_pipeline_gotchas.md` 的模板问用户要：SSH 地址/端口/密钥、远程仓库
  路径 `remote_repo_dir`、远程工作目录 `remote_work_dir`、这次用哪个
  `pipeline_module`（比如 `ltx_pipelines.distilled`）、权重路径
  `pipeline_extra_args`。这些都是用户环境相关的真实值，**不要用占位符/
  猜测值直接写文件**，宁可停下来问。
  `pipeline_extra_args` 里**不要主动加 `--enhance_prompt`**——见
  `ltx_pipeline_gotchas.md`"官方文档 + 社区实测交叉验证的共识"一节，
  本 skill 导出的提示词都是上游手写好的完整详细提示词，不适用这个"自动
  增强简略提示词"的功能，多篇第三方实测也反馈它不稳定。
- **`model` 字段填 `"ltx-2.5"`**，下游据此确认没走错通道。
- **`platform` + `instance_id` 这两个字段要一起写上**（`platform` 现在只有
  `runpod` 一个取值——AutoDL 和 vast.ai 两条通道 2026-09-04 已经删掉，理由是
  那两家没有 Network Volume 那种"卷和实例解耦"的东西，每次都要重下 67GB
  权重；`instance_id` 填 pod_id，还要带上 `network_volume_id`）。提交脚本本身不用
  它们，但"用完就关"那套收尾机制要靠它们才知道该去关哪个平台的哪台机器
  （`short-drama-ltx-generate/scripts/gpu_teardown.py`、
  `ltx_ssh_submit.py --auto-stop`）。租显卡那一步能拿到这些值，别漏填——
  漏了就只能事后手敲实例 ID，最容易演变成"忘了关，显卡通宵计费"。

## 6. Dry-run 验证能不能被脚本消费

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py \
  --config output/<故事名>/videos/ep0X/ltx_remote_config.json \
  --jobs output/<故事名>/videos/ep0X/video_jobs.json \
  --out-dir output/<故事名>/videos/ep0X \
  --dry-run
```

这一步不实际连接远程机器，只确认脚本能正常解析 config+jobs、
拼出远程命令不报 Python 异常（比如 KeyError）。逐条看打印出来的"远程命令"，对照
`short-drama-ltx-generate/references/ltx_pipeline_gotchas.md` 里标注的
已知参数陷阱（`--image` 的三段式格式、`--num-frames` 必须 8k+1、
`--negative-prompt` 是否通用）提醒用户：这一步只保证文件能被脚本消费，
**不保证远程 pipeline 真的认得这些参数**，第一次真跑之前用户还是要自己在
远程机器上跑一遍对应 pipeline 的 `--help` 核实。

`--dry-run` 报错（比如 KeyError、路径解析异常）说明 `video_jobs.json`
结构本身有问题，回第 2-4 步修，不是 `ltx_ssh_submit.py` 的 bug（那个脚本
已经在别的地方验证过）。

## 7. 汇报

结束时说清楚：本次打包了几镜（哪些集/哪些镜号）、跳过了几镜（不承载新
台词/新情节的 C 级复用镜、本地兜底降级镜、或素材缺失）、校验阶段发现并
修正了什么问题（尤其是台词时长不够、C 级误跳过这两类）、`ltx_remote_config.json` 是
新建的还是复用已有的、dry-run 是否通过。明确告诉用户：文件已经就位，
真正生成交给 `short-drama-ltx-generate` 这个 skill 去掉 `--dry-run` 执行
（或者先用 `--only` 只跑 1-2 个镜头验证效果），本 skill 不会替用户主动
执行生成。

## 与其他 skill 的衔接

- 上游：`short-drama-video-gen`（`shot_cards.json` 镜头卡 + 装配出的
  `video_jobs.json`）+
  `short-drama-keyframe-gen`（`keyframes.md` 关键帧路径）+
  `short-drama-image-gen`（`selected.md` 一致性参考图）。
- 下游：`short-drama-ltx-generate` 拿本 skill 产出的 `video_jobs.json` +
  `ltx_remote_config.json`，去掉 `--dry-run` 实际执行
  `ltx_ssh_submit.py` 提交生成、抽帧+听审验收，验收结果回填进
  `video_jobs.md`（人读版）和 `video_jobs.json`（`notes`/后续增量导出
  时的"状态"）。
