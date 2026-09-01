---
name: short-drama-ltx-export
description: 面向自建 LTX-2.5（Lightricks LTX-2）图生视频通道的打包助手：把 short-drama-video-gen 产出的逐镜提示词清单（video_jobs.md）、short-drama-keyframe-gen 的关键帧文件路径、人物/场景一致性参考图，汇总校验后导出成严格符合 video_jobs_schema.md 结构、并补齐 LTX 专属字段（width/height/num_frames/seed）的 video_jobs.json，同时检查/生成 ltx_remote_config.json，最后跑一次 ltx_ssh_submit.py --dry-run 验证能不能被脚本直接消费。产出"可以直接交给 LTX-2.5 提交"的文件，不需要用户手动从 Markdown 表格里转录。当用户说"把这些整理成能交给LTX的文件""导出video_jobs.json""打包提交给LTX2.5""这一集的提示词整理成能跑的文件"时使用。
---

# AI 短剧 LTX-2.5 提交文件打包助手 (short-drama-ltx-export)

承接 `short-drama-video-gen` 之后的最后一道装配环节：那个 skill 产出的
`video_jobs.md` 是**给人看的** Markdown（表格 + 逐镜提示词散文），
`ltx_ssh_submit.py` 需要的是**严格结构化**的 `video_jobs.json`
（见 `short-drama-video-gen/references/video_jobs_schema.md`）外加 LTX
专属字段（`width`/`height`/`num_frames`/`seed`）。这中间"从散文表格里
逐字段抠出来、补齐缺的字段、检查路径真实存在"这一步容易出错也容易漏做，
所以单独拆成这个 skill，别指望用户自己手动转录。

这个 skill **只负责产出/校验文件**，不负责真正发起 SSH 生成——那是
`short-drama-ltx-generate` 这个 skill 拿到本 skill 的产出后去掉
`--dry-run` 真跑的事，本 skill 最多跑到 `--dry-run` 这一步为止。

## 0. 先确认这次针对哪一集/哪几镜

不要一次性把全剧都打包，按用户指定的集数（`epNN`）处理；如果用户说"这几镜"，
只处理指定镜号，其余镜头保留在已有的 `video_jobs.json`（增量更新，不要覆盖
掉别的镜头已经校验过的记录）。

## 1. 确认输入齐不齐

- `output/<故事名>/videos/ep0X/video_jobs.md`——`short-drama-video-gen` 的
  产出，包含"提交清单"表格（镜号/场景/首帧/尾帧/一致性参考图/台词/建议
  时长/状态）和"逐镜完整提示词"章节（每镜的正向/负面提示词）。这是本 skill
  的主要数据源，缺了就先回 `short-drama-video-gen` 把这一步做完，不要凑合
  着从分镜表原文直接编提示词。
- `output/<故事名>/keyframes/ep0X/keyframes.md`——核对首帧路径确实是选中的
  关键帧文件，不要相信 `video_jobs.md` 里可能手误写错的路径，两边对不上时
  以 `keyframes.md` 为准并提醒用户。
- `output/<故事名>/assets/selected.md`——核对一致性参考图路径。
- 如果 `output/<故事名>/videos/ep0X/ltx_remote_config.json` 已存在，读出来
  确认 `pipeline_module`/权重路径没有变化；不存在则见第 5 步问用户要，
  **不要瞎猜**。

## 2. 逐镜抽取字段，按 schema 转换

对"提交清单"表格里状态不是"跳过"的每一行（B/C 级已跳过的镜头，或者原表
"B 级镜头（跳过）"章节里的镜头，都不进本次导出），从 `video_jobs.md` 里
把对应字段抠出来，拼成一条 JSON 记录，字段和含义完全按
`short-drama-video-gen/references/video_jobs_schema.md` 的 JSON 版本：

- `id`：`ep{集号:02d}_镜{镜号:02d}`，和 `keyframes.md`/`jobs.json` 命名一致；
  分段镜头加 `_seg1`/`_seg2` 后缀。
- `shot_no`：镜号（整数）。
- `scene`：场景编号+简称，从表格"场景"列取。
- `first_frame`/`last_frame`：文件路径原样照抄，`last_frame` 没有就是
  `null`，不要因为"看起来应该有"就编一个。
- `ref_images`：一致性参考图，表格里如果写"同上"要展开成实际路径，不要把
  "同上"两个字直接塞进 JSON。
- `dialogue`：台词/旁白列原样照抄，没有就是 `null`；这只是给配音/剪辑参考，
  绝对不进 `prompt`/`negative_prompt`。
- `prompt`/`negative_prompt`：去对应"逐镜完整提示词"章节找这一镜的完整
  正向/负面提示词整段抄过来，不要截断、不要自己精简，也不要因为提示词长
  就省略"备注"里对生成效果有实际影响的限制条件（比如"不出现第二张脸"）。
  抄的时候顺手扫一眼：如果这一镜有 `first_frame`，提示词却大段在复述
  首帧图里已经有的静态内容（人物穿着、发型、背景陈设）而几乎没写动作/
  镜头运动的变化量，这是 LTX 图生视频的已知常见坑（见
  `short-drama-ltx-generate/references/ltx_pipeline_gotchas.md`），容易
  跟首帧图像条件冲突导致生成结果跑偏——**照抄导出，但提醒用户回
  `short-drama-video-gen` 检查这一镜提示词**，不要自己在导出阶段改写
  提示词内容。
- `duration_sec`：表格"建议时长(s)"列。
- `aspect_ratio`：短剧默认 `"9:16"`，除非用户明确说这镜要横屏。
- `platform_recommend`：固定写 `["LTX-2.5 (self-hosted)"]`，不要照抄
  `video_platform_comparison.md` 里 SaaS 平台的推荐，那是给别的通道用的。
- `notes`：原表格备注/分段说明，加上第 3 步补的分辨率测试策略说明。

## 3. 补齐 LTX 专属字段

`video_jobs_schema.md` 的通用 JSON 里没有的字段，LTX 提交必须有：

- `num_frames`：默认不填，让 `ltx_ssh_submit.py` 按
  `duration_sec × 24fps` 自动估算；如果这一镜需要更精确控制（比如卡住某个
  动作节拍），显式算好填进去并在 `notes` 写明为什么覆盖默认估算。
  第一次验证某镜动作方向时，参照
  `references/resolution_presets.md`"时长也要走同样的先测试再放大阶梯"
  一节，优先出一份 `num_frames` 较小（比如 73/97）的测试档 job，跟分辨率
  测试档同一批产出，不要一上来就按最终时长导出。
- `width`/`height`：像素值必须能被 64 整除（见
  `short-drama-ltx-generate/references/ltx_pipeline_gotchas.md`）。竖屏
  9:16 常见可用组合比如 `704×1280`、`768×1344`——**先问用户这次要测试档
  还是正式档**，两档分辨率不同就分别产出两份 job（或用 `notes` 区分），
  不要自己拍板只出一档。第一次跑通某个镜头之前，优先建议测试档，跑通了再
  升正式档——竖屏输出已经实测验证过没问题，但每次换新显卡架构/新 pipeline
  仍建议先测试档确认再上正式档。
- `seed`：**不填不等于随机**——`ltx_pipeline_gotchas.md` 已用 `--help`
  实测确认 `ltx_pipelines.distilled`/`dfr_pipeline` 的 `--seed` 默认值是
  固定的 `10`，不传就每次复现同一个结果，不是随机。如果这一镜要多轮测试
  不同的生成走向（比如同一 prompt 反复出现同类问题，怀疑是这个种子运气差
  而不是提示词系统性写错），必须显式传一个新的 `seed` 值才能拿到不同结果；
  只有确认已经选中某个 seed 的效果、要在正式分辨率下复现同一个动作走向时，
  才固定填那个具体数值，不要自己编一个数字。

具体 64 整除的可用尺寸表和测试/正式档搭配建议放在
`references/resolution_presets.md`，直接查表用，不要每次重新算。

## 4. 校验

写完 `video_jobs.json` 后跑校验脚本，不要跳过这一步：

```bash
python3 .claude/skills/short-drama-ltx-export/scripts/validate_video_jobs.py \
  output/<故事名>/videos/ep0X/video_jobs.json
```

脚本检查（详见脚本内注释，规则不在这里重复）：必填字段是否齐全、
`first_frame`/`last_frame`/`ref_images` 引用的文件是否在本地磁盘真实存在、
`width`/`height` 是否能被 64 整除、`aspect_ratio` 字段是否跟实际
`width`/`height` 比例吻合（防止漏填/传错分辨率悄悄退回默认横屏）、
`num_frames`（如果手填了）是否满足 8k+1、`prompt`/`negative_prompt` 是否
有明显占位符（比如残留的"TODO"/"（完整正向提示词）"这类没展开的字样）。

校验报错就回 `video_jobs.md` 或对应素材目录核实修正，不要手动改 JSON 把
报错糊过去（比如路径不存在就编一个假路径让脚本通过）——这种"通过校验"没有
意义，SSH 提交时一样会因为本地文件不存在而失败。

## 5. 检查/生成 `ltx_remote_config.json`

- 已存在：读出来给用户看一眼当前的 `ssh_host`/`pipeline_module`/权重路径，
  确认没有变化（比如换了台显卡机器）。
- 不存在：按 `short-drama-ltx-generate/references/gpu_rental_ops.md` 和
  `ltx_pipeline_gotchas.md` 的模板问用户要：SSH 地址/端口/密钥、远程仓库
  路径 `remote_repo_dir`、远程工作目录 `remote_work_dir`、这次用哪个
  `pipeline_module`（比如 `ltx_pipelines.distilled`）、权重路径
  `pipeline_extra_args`。这些都是用户环境相关的真实值，**不要用占位符/
  猜测值直接写文件**，宁可停下来问。
  `pipeline_extra_args` 里**不要主动加 `--enhance_prompt`**——见
  `ltx_pipeline_gotchas.md`"官方文档 + 社区实测交叉验证的共识"一节，
  本 skill 导出的提示词都是上游手写好的完整详细提示词，不适用这个"自动
  增强简略提示词"的功能，多篇第三方实测也反馈它不稳定。

## 6. Dry-run 验证能不能被脚本消费

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py \
  --config output/<故事名>/videos/ep0X/ltx_remote_config.json \
  --jobs output/<故事名>/videos/ep0X/video_jobs.json \
  --out-dir output/<故事名>/videos/ep0X \
  --dry-run
```

这一步不实际连接远程机器，只确认脚本能正常解析 config+jobs、拼出远程命令
不报 Python 异常（比如 KeyError）。逐条看打印出来的"远程命令"，对照
`short-drama-ltx-generate/references/ltx_pipeline_gotchas.md` 里标注的
已知参数陷阱（`--image` 的三段式格式、`--num-frames` 必须 8k+1、
`--negative-prompt` 是否通用）提醒用户：这一步只保证文件能被脚本消费，
**不保证远程 pipeline 真的认得这些参数**，第一次真跑之前用户还是要自己在
远程机器上跑一遍对应 pipeline 的 `--help` 核实。

`--dry-run` 报错（比如 KeyError、路径解析异常）说明 `video_jobs.json`
结构本身有问题，回第 2-4 步修，不是 `ltx_ssh_submit.py` 的 bug（那个脚本
已经在别的地方验证过）。

## 7. 汇报

结束时说清楚：本次打包了几镜（哪些集/哪些镜号）、跳过了几镜（B/C 级或
素材缺失）、校验阶段发现并修正了什么问题、`ltx_remote_config.json` 是
新建的还是复用已有的、dry-run 是否通过。明确告诉用户：文件已经就位，
真正生成交给 `short-drama-ltx-generate` 这个 skill 去掉 `--dry-run` 执行
（或者先用 `--only` 只跑 1-2 个镜头验证效果），本 skill 不会替用户主动
执行生成。

## 与其他 skill 的衔接

- 上游：`short-drama-video-gen`（`video_jobs.md` 逐镜提示词）+
  `short-drama-keyframe-gen`（`keyframes.md` 关键帧路径）+
  `short-drama-image-gen`（`selected.md` 一致性参考图）。
- 下游：`short-drama-ltx-generate` 拿本 skill 产出的 `video_jobs.json` +
  `ltx_remote_config.json`，去掉 `--dry-run` 实际执行
  `ltx_ssh_submit.py` 提交生成、抽帧+听审验收，验收结果回填进
  `video_jobs.md`（人读版）和 `video_jobs.json`（`notes`/后续增量导出
  时的"状态"）。
