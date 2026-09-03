---
name: loop-picture-generation
description: 面向 AI 短剧从文字版分镜到图像版分镜/人物形象这一步的双 agent 循环出图助手：不再是同一个 Claude 自己出图又自己验收，而是拆成两个独立 subagent 互相制衡——出图 agent（Generator）只负责调用 Codex CLI 实际生成图片，并且对审查 agent 给出的修改意见无条件照做，不自行辩解、不打折扣执行；审查 agent（Reviewer）只做一件事，拿到 Generator 刚生成的图，逐张对照文字版分镜表/角色档案原文判断是否合格，合格就通过，不合格就给出具体、能直接拼进下一轮提示词的修改意见退回 Generator 重来，单个镜头/角色/场景最多循环三轮（三次出图）不管有没有通过都要放行进入下一个分镜，不能在一个镜头上无限重试卡住整体进度。同时为了提速，不是一个分镜一个分镜顺序处理，而是维护最多 4 个并发槎位，同时对 4 个不同分镜/角色/场景各起一组 Generator+Reviewer 并行生成，一个槎位跑完（通过或到三轮上限）立刻补下一个待处理分镜进来，让 Codex CLI 始终有多个进程同时在跑。可以接在 short-drama-image-gen（角色/场景基准图）和 short-drama-keyframe-gen（逐镜关键帧）已经组装好的 jobs 之后，作为它们"验收+重试"这一步的替代执行引擎。当用户要求"用两个 agent 互相审查出图""出图别自己审自己""这批镜头/角色一起并行出图，最多4个同时跑""让审查 agent 强制打回重做""每镜最多出3次图就跳到下一镜""加快出图速度"时使用。
---

# 双 agent 循环出图助手 (loop-picture-generation)

这个 skill 不重新定义"提示词怎么写、参考图去哪找"——那部分规则已经在
`short-drama-image-gen`（角色/场景基准图）和 `short-drama-keyframe-gen`
（逐镜关键帧）里写好了，直接复用。这个 skill 要解决的是那两个 skill 里
"生成 → 自查 → 不合格就自己改自己重生成"这一段的两个问题：

1. 同一个 agent 既出图又给自己打分，容易"差不多就过"；拆成两个各司其职
   的 subagent，互相不妥协，质量控制更硬。
2. 原来的流程是一个分镜/角色/场景顺序处理完再处理下一个；这里换成最多
   4 路并发，几个分镜同时在跑 Codex CLI，明显更快。

## 0. 先确认输入和前置条件

- 走这个 skill 之前，先确认已经有（或先跑出）：
  - 角色/场景：`short-drama-image-gen` 产出的 `characters.md` / `scenes.md`。
  - 关键帧：`short-drama-keyframe-gen` **阶段一已经跑完并经用户确认**的
    `jobs_ep0X.json`（连同 `keyframe_cards.json` 和那份
    `keyframe_prompts_ep0X.md` 审阅表）。这个 skill 只替代它的阶段二
    （出图+验收），**不许绕过阶段一那道人工闸门直接开始出图**——走位/朝向/
    景别在出图之前必须由人看过一遍，理由见
    `short-drama-keyframe-gen/references/blocking_guide.md`。
    Reviewer 的 `storyboard_ref` 用卡上的 `script_ref_zh`，
    `fix_instruction` 要落到卡的具体字段上（比如
    `people[1].camera_relation` 改成 `three_quarter_back`），
    改完由 orchestrator 重跑 `build_keyframe_prompt.py` 拿新 prompt，
    不要手改 prompt 字符串。
  - 这些文件怎么产出、占位符怎么替换，不在这里重复，缺了就先引导用户/自己
    跑对应的上游 skill。
- 检查 Codex CLI 登录状态（同 `short-drama-image-gen/references/api_setup.md`），
  没登录先引导用户完成 `codex login --device-auth`。
- 问清楚这一次要处理**哪个范围**（比如"这一集全部镜头""这 5 个角色的
  三视图"），不要默认把整部剧所有分镜一次性塞进队列——范围越大，中途
  发现问题需要推倒重来的代价越高。

## 1. 组装 unit 队列

把这一批要处理的对象（每个角色三视图 job / 每个场景 job / 每一镜关键帧
job）整理成"unit"列表，字段在 `short-drama-image-gen` 的 `jobs_schema.md`
基础上多了几个本 skill 专属字段，用来支撑多轮循环记录状态。字段定义、
`storyboard_ref` 怎么摘录（角色档案原文 / 场景描述原文 / 分镜表该镜那一行
原文）见 `references/units_schema.md`，写成
`output/<故事名>/.../units_queue.json`。

`storyboard_ref` 必须是原文摘录，不要转述改写——这是 Reviewer agent 判断
"合不合格"唯一的依据，转述过程中丢的细节会让审查标准跑偏。

## 2. 两个 subagent 的分工（核心设计）

- **Generator（出图 agent）**：每一轮只做"照当前 prompt 调用
  `generate_images.py` 把图吐出来"这一件事。Reviewer 给的修改意见
  （`fix_instruction`）在进入下一轮之前已经由你（orchestrator）拼进了
  unit 的 `prompt` 字段，Generator 拿到就是最终版本，不需要也不允许自己
  再评判这条意见对不对、要不要打折扣执行——完整 prompt 模板见
  `references/generator_agent.md`。唯一允许它停下来报错而不是硬跑的情况
  是遇到技术性障碍（引用文件不存在、codex 未登录/连续报错），这不算"对
  审查意见有异议"。
- **Reviewer（审查 agent）**：拿到 Generator 这一轮新生成的图片文件路径，
  用 Read 工具逐张实际打开，只对照这个 unit 的 `storyboard_ref` 原文 +
  对应验收清单判断，不脱离原文自己加戏挑毛病。合格给
  `verdict: pass` + 选中文件；不合格给 `verdict: fail` +
  具体到能直接拼进下一轮 prompt 的 `fix_instruction`（不能是"再改进一下"
  这种没法执行的话）。完整模板和判断标准见 `references/reviewer_agent.md`。

这两个 subagent 都是**每轮现起一个新的**，不复用上一轮的 agent 实例——
所有需要延续的状态（当前 prompt、已经生成到第几张、历史 verdict）都记在
`units_queue.json` 里由你维护，agent 本身不需要"记得"之前发生了什么。

## 3. 最多 4 槎位并行批处理循环

调度算法（怎么补槎位、Generator/Reviewer 批次怎么在同一条消息里并发发出、
状态怎么更新、3 轮上限怎么强制放行）见 `references/batch_loop.md`，里面
有一个 6-unit 的例子说明为什么要"随时补槎位"而不是等一批 4 个全跑完才开
下一批。核心规则只有两条，必须严格执行：

1. 任意时刻同时处于"进行中"的 unit 不超过 4 个。
2. 单个 unit 累计跑满 3 轮（3 次生成+审查）不管有没有 `pass`，都必须把它
   标记结束（`passed` 或 `capped`）、腾出槎位处理下一个，不允许为了"再试
   一次说不定就过了"破例。

如果 Generator 报出疑似限流的错误（`short-drama-image-gen/references/api_setup.md`
描述的那类连续非零退出/超时），把并发槎位数从 4 调小到 2 甚至 1，不要在
明显限流的情况下硬撑并发。

## 4. 汇总落地

跑完这一批 unit 之后：

- 按 `short-drama-image-gen` 的 `selected.md` / `short-drama-keyframe-gen`
  的 `keyframes.md` 表格格式登记最终结果，多加两列：**用了几轮**、
  **结果（通过/到三轮上限放行）**。
- 给用户的汇报要点名：这一批共 N 个 unit，M 个一轮就过，K 个 2-3 轮后过，
  P 个跑满 3 轮仍未通过（逐个列出，附 `best_of_all` 选出的最接近图和
  差在哪），本轮总共触发了多少次 codex 生成调用。
- 3 轮仍未通过的 unit 不要自己private决定"将就用"或"放弃"，明确交给用户
  决定是调整角色/场景设定、换措辞重来，还是接受当前最接近的一张。

## 与其他 skill 的衔接

- 上游：`short-drama-image-gen`（角色/场景基准图 + `generate_images.py`
  脚本，本 skill 直接复用不重新实现）、`short-drama-keyframe-gen`（分镜表
  解析、关键帧提示词展开规则）。这个 skill 不替代它们的第 0-1 步（提示词
  组装），只替代它们各自的"生成+验收+重试"这几步，换成双 agent 循环 + 4
  路并行的执行方式。
- 下游：产出的 `selected.md` / `keyframes.md` 跟原来两个 skill 格式一致，
  可以直接被 `short-drama-video-gen` / `short-drama-ltx-export` 等后续
  skill 引用，不需要额外转换。
