---
name: loop-video-generation
description: 面向自建 LTX-2.5（Lightricks LTX-2）图生视频生成这一步的双 agent 循环执行助手：接管 short-drama-ltx-generate 里"提交生成+验收+重试"这几步，拆成两个各司其职的 subagent——出片 agent（Generator）负责按分镜表展开好的提示词实际调用 ltx_ssh_submit.py 在已租好的显卡上提交生成、下载结果、抽帧，并且落实审查 agent 每一轮给出的具体修改意见（改正向提示词文字、换 seed、缩小动作幅度、拆段、换首尾帧等——已经确认 LTX-2.5 当前用的 pipeline 没有独立的负面提示词参数，不会拿"加负面提示词"当修改手段），不自己另起炉灶改方案；审查 agent（Reviewer）拿到 Generator 抽出来的帧后，刻意不拿分镜表"画面描述"那句话的字面意思当唯一标准（那句话本来就是这一轮生成时已经用过的输入，拿它验收等于自己出题自己判卷），而是回去对照原剧本/分集大纲描述的这一段实际场景和情节，判断视频有没有讲对这个情节，同时重点检查视频生成特有的技术问题：背景在过程中有没有跑偏/闪烁/变成别的场景，人物长相/服装/动作有没有崩坏或方向不对，镜头视角/景别有没有跟运镜设计不一致等。单个镜头最多循环三轮（三次提交生成），到了就放行进入下一个镜头，不允许在一个镜头上无限重试烧显卡时间；如果问题只出现在一小段时间窗口、其余画面正常，会用 LTX-2.5 官方文档记载的 `ltx_pipelines.retake` 局部重绘能力只重跑那一小段，不整段重来。跟 loop-picture-generation 不同的是**默认不做多镜头并行**——图生视频跑在同一台租来的显卡实例上，多个生成任务抢同一块显卡的显存/算力没有意义，所以这里是严格按镜头顺序执行的循环，不是并发批处理。当用户要求"视频生成也用两个 agent 互相审查""审查视频别按分镜表字面对答案，要看剧情对不对""检查视频背景/人物动作/镜头视角有没有问题""视频生成加个打回重做的循环"时使用。
---

# 双 agent 循环视频生成助手 (loop-video-generation)

这个 skill 不重新定义"提示词怎么展开、显卡怎么租、环境怎么搭"——那些规则
在 `short-drama-video-gen`（提示词方法论）和 `short-drama-ltx-generate`
（租显卡/环境/pipeline 参数）里已经写好，直接复用。这个 skill 要接管的是
`short-drama-ltx-generate` 第 4 步（提交生成）+ 第 5 步（验收），换成"出片
agent + 审查 agent 互相制衡、单镜最多三轮"的执行方式，同时纠正一个容易
被忽视的验收盲区：**不能拿分镜表那句话去验收用分镜表那句话生成出来的
视频**，那样任何看起来"字面对上了"的结果都会被放过，真正该看的是这段
视频有没有讲对原剧本里这一段的情节。

## 0. 先确认前置条件

- `short-drama-ltx-export` 已经产出并校验通过 `video_jobs.json` +
  `ltx_remote_config.json`；显卡实例已经按 `short-drama-ltx-generate`
  第 1-3 步租好、环境搭好、pipeline 参数核实过。这几步本 skill 不重复，
  没做完先回 `short-drama-ltx-generate`。
- 拿到这一集（或这几个镜头）对应的"原剧本"内容——见第 1 步怎么摘录，
  没有独立剧本文档也要有 `short-drama-scout` 产出的分集大纲原文，缺了就
  先问用户要，不要让 Reviewer agent 拿分镜表的"画面描述"列顶替。
- 问清楚这次要处理哪几个镜头，默认逐镜顺序处理（原因见第 3 步），不要
  一次性把一整集的 S/A 级镜头都塞进队列指望"反正是循环会自己跑完"——
  每一镜的三轮上限仍然会实际调用生成，批量排队只是省得每镜都重新确认
  一次范围。

## 1. 组装 unit 队列

把要处理的每个 S/A 级镜头（或已拆分的分段）整理成"unit"，字段在
`short-drama-video-gen` 的 `video_jobs_schema.md` 基础上多了几个本 skill
专属字段。最关键的是 `script_ref`：

- 优先摘用户提供的完整剧本/对白全文中对应这一段场景的原文。
- 没有独立剧本文档时，退而摘 `short-drama-scout` 产出的该集分集大纲原文
  （开场3秒/核心冲突/结尾钩子里跟这一镜相关的那句）+ 人物小传里出场角色
  的性格/关系设定。
- **明确不能用** `ep0X.md` 分镜表"画面描述"列的原文当 `script_ref`——那
  句话已经在展开 `prompt` 时用过了，重复拿来当验收依据等于自己出题自己
  判卷，会把"字面对上但没讲对情节"的结果放过去。

完整字段定义见 `references/units_schema.md`，写成
`output/<故事名>/videos/ep0X/units_queue.json`。

## 2. 两个 subagent 的分工（核心设计）

- **Generator（出片 agent）**：每一轮只做"用当前这一版 prompt/seed/参数
  实际调用 `ltx_ssh_submit.py` 提交生成、下载结果、抽帧"这一件事。Reviewer
  上一轮给的修改意见（改正向提示词文字、换 seed、缩小动作幅度、拆段、换
  一张首尾帧等）在进入下一轮之前已经由你（orchestrator）落实进 unit 的
  `prompt`/`seed`/`segments` 等字段，Generator 拿到就是照最新版本提交，
  不用自己重新设计方案。**`negative_prompt` 字段不是有效杠杆**——已确认
  当前用的 `ltx_pipelines.distilled`/`dfr_pipeline` 都没有对应 CLI 参数，
  改这个字段不会影响生成结果，细节和原因见 `references/units_schema.md`
  和 `references/generator_agent.md`。完整模板见
  `references/generator_agent.md`。
- **Reviewer（审查 agent）**：拿到 Generator 这一轮抽出来的帧，**刻意
  忽略分镜表画面描述的字面表述**，只对照 unit 的 `script_ref` 判断"这段
  视频有没有讲对原剧本这一段的情节/情绪"，再叠加视频生成特有的技术检查：
  背景是否在过程中跑偏/闪烁/变成别的场景、人物长相服装动作是否崩坏或方向
  不对、镜头视角景别是否跟运镜设计不一致，以及首尾帧衔接、结尾定格姿态
  等常规项。判断为 `fail` 时如果问题**只集中在一小段时间窗口、其余画面
  正常**，会额外给出 `defect_window`，让下一轮走局部重绘而不是整段重来
  （见第 3 步）。完整判断标准和模板见 `references/reviewer_agent.md`。

两个 subagent 都是**每轮现起一个新的**，不复用上一轮的 agent 实例，所有
需要延续的状态记在 `units_queue.json` 里由你维护。

## 3. 单镜顺序循环，最多三轮——为什么不像出图那样并行

`loop-picture-generation` 出图时开 4 路并行，是因为每路调的是各自独立的
Codex CLI（ChatGPT 账号额度），互不抢资源。这里不一样：所有生成任务都在
**同一台租来的显卡实例**上跑，显存和算力是唯一的，多个 `ltx_ssh_submit.py`
同时提交只会互相抢显存、大概率 OOM 或者被 CUDA 排队串行执行，跟顺序跑
没区别却更容易出故障——所以本 skill 默认严格按镜头顺序，一个 unit 的循环
彻底结束（`passed` 或到三轮上限 `capped`）才开始下一个。

调度算法（每轮怎么走 Generator→Reviewer、状态怎么更新、三轮上限怎么强制
放行）见 `references/loop_protocol.md`，核心规则：

1. 单个 unit 累计跑满 3 轮（3 次生成+审查）不管有没有 `pass`，都必须结束
   放行，不允许"再试一次说不定就过了"——视频比图片贵得多，见
   `short-drama-video-gen/references/stability_playbook.md`。
2. 如果用户明确租了多台互相独立的显卡实例（不是常见情况），可以给每台
   实例各配一组 Generator+Reviewer 循环处理不同镜头；默认单实例场景不要
   假设这个条件成立。

**局部重绘（利用 `ltx_pipelines.retake`）**：如果某一轮的问题只出现在
视频的一小段时间窗口、其余画面完全正常，不要整段重来——Reviewer 会给出
`defect_window`，下一轮改用 `ltx_ssh_submit.py --retake <start> <end>`
只重新生成这一段，省下重跑整段（尤其是升到正式分辨率/时长后）的显卡
时间。这条能力是 2026-09 查完 LTX-2.5 官方文档后新加的，官方文档记载但
参数名还没在这个仓库里用 `--help` 实测确认，第一次用先看
`short-drama-ltx-generate/references/ltx_pipeline_gotchas.md` 里对应的
提醒。另外要注意：**`ref_images`/`negative_prompt` 这两个字段在自建
LTX-2.5 通道上都不生效**（`ltx_ssh_submit.py` 从不读取/传递），`fix_instruction`
不能落在这两个字段上，只能落在 prompt 文字/`seed`/分段/局部重绘这几项
真正有效的杠杆上，见 `references/reviewer_agent.md`。

## 4. 汇总落地

跑完这一批 unit 之后：

- 按 `video_jobs.md` 的表格格式登记结果，多加两列：**用了几轮**、
  **结果（通过/到三轮上限放行，附具体卡在哪一帧/哪个环节）**。
- 给用户的汇报要点名：这一批共 N 个镜头，M 个一轮就过，K 个 2-3 轮后过，
  P 个跑满 3 轮仍未通过（逐个列出问题和抽帧截图路径），本轮总共提交了
  多少次生成任务（视频比图片贵，这个数字比出图流程更值得强调）。
- 3 轮仍未通过的镜头不要自己决定"将就用"，按
  `video_review_checklist.md`"何时可以判定这个镜头没必要用图生视频"一节
  的思路，把"降级成 B 级纯运镜处理"作为一个选项列给用户，交用户决定。

## 与其他 skill 的衔接

- 上游：`short-drama-ltx-export`（`video_jobs.json` + 校验通过的
  `ltx_remote_config.json`）、`short-drama-ltx-generate` 第 1-3 步（已经
  租好显卡、搭好环境、核实过 pipeline 参数）、`short-drama-scout`（分集
  大纲/人物小传，作为 `script_ref` 的来源）。
- 平行：`short-drama-video-gen` 负责提示词撰写方法论和 `extract_frames.py`
  抽帧工具，`short-drama-ltx-generate` 负责 GPU 租赁/环境/pipeline 参数
  的实测踩坑记录，本 skill 都直接复用，不重新实现。
- 下游：产出的视频文件路径和登记表跟原来 `short-drama-ltx-generate` 第 5-7
  步一致，可以直接接续那份 skill 的收尾流程（提醒用户停显卡、补踩坑记录）。
