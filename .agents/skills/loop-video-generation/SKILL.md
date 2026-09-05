---
name: loop-video-generation
description: 面向自建图生视频（LTX-2.5 / MiniMax-H3）生成这一步的双 agent 循环执行助手：接管 short-drama-ltx-generate
  里"提交生成+验收+重试"这几步，拆成出片 agent（Generator）和审查 agent（Reviewer）。Generator 按镜头卡装配好的提示词实际提交生成、下载结果、抽帧，并落实审查意见（改正向提示词、换
  seed、缩小动作幅度、拆段、局部重绘——已确认当前 pipeline 没有独立负面提示词参数，不会拿"加负面提示词"当手段）；Reviewer 刻意不拿分镜表"画面描述"那句话当唯一标准（那是这一轮生成用过的输入，拿它验收等于自己出题自己判卷），而是对照原剧本判断情节讲对没有，同时查视频特有问题：背景跑偏/闪烁、人物崩坏、镜头视角不符。**Reviewer
  有三种结论**：pass / retry_l1（视频层能修：时长、节拍、seed、拆段、局部重绘）/ **escalate_l2（首帧本身就不适合这一镜，重试视频是浪费钱——回关键帧层改走位/朝向/机位/景别/在场人物，重出图再回来）**。这条升级路径是为了解决"首帧被
  --image 焊死、图不对就永远修不好"这个结构性缺陷（最硬的例子是 ledger A9 人物自己转向镜头，三档 strength 全部失败）；判定路由表见
  keyframe_escalation_guide.md，执行链由 rekey_shot.py 包住，其中回填 first_frame_state_zh 是硬闸门。预算：单镜最多
  3 轮 L1 + 1 次 L2，L3（改分镜）永远停下来交给用户。默认**不做多镜头并行**——所有任务跑在同一台租来的显卡上，抢显存没意义，严格按镜头顺序执行。当用户要求"视频生成也用两个
  agent 互相审查""审查视频别按分镜表字面对答案""检查视频背景/人物动作/镜头视角有没有问题""视频生成加个打回重做的循环""首帧不对要能回去重出图""生成的视频跟分镜对不上怎么办"时使用。
---

## Codex 运行适配（迁移新增，以下原始正文保持不变）

- 在本项目根目录运行；此 skill 的 Codex 入口为 `.agents/skills/loop-video-generation/SKILL.md`，用 `$loop-video-generation` 调用。
- 原文中的 Read：文本用文件读取工具，图片用图片查看工具；Bash 用 shell，Write/Edit 用文件编辑工具，Glob/Grep 用文件搜索工具；WebFetch/WebSearch 用可用的网页检索工具。
- 原文提到其他 skill 时，读取同级 `../<skill-name>/SKILL.md`。Task/subagent/Generator/Reviewer 对应 Codex 的独立子代理能力；保留原来的职责隔离、轮次和预算，实际并发受宿主上限限制。能力缺失时报告限制，不声称已经执行。
- 原文相对于 skill 的 references/、scripts/ 路径仍相对于本目录。原文命令里的 `.claude/skills/` 脚本及文档路径在 Codex 执行时映射到 `.agents/skills/`；项目素材、输出和私有配置文件的路径保持原意。脚本内部实现及默认配置保持原样，源目录与目标目录共存。
- 原文的确认节点、输入要求和业务规则保持不变。本文只适配执行宿主，不自动执行生成、租卡或 API 调用。

<!-- ORIGINAL-BODY-START -->

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
  `prompt`/`seed`/`segments` 等字段（`prompt` 是从镜头卡装配出来的派生字段，
  orchestrator 改卡后重跑 `build_prompt.py` 再同步进队列），Generator 拿到
  就是照最新版本提交，不用自己重新设计方案。**`negative_prompt` 字段不是有效杠杆**——已确认
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

### Reviewer 的第三种结论：升级到关键帧层（L2）

**这是 2026-09-04 加的，起因是一个结构性缺陷**：以前的循环只会拿**同一张
首帧**反复重生成视频。但首帧是 `--image PATH 0 1.0` **焊死**的，如果那张图
本身就不适合这一镜——人物朝向不对、这个机位根本看不到该看的东西、上一镜
在场的人这张图里没有——那么重试多少轮都改不出来。**问题在上游，重试在
下游，永远修不好。**

最硬的证据是 ledger **A9「人物自己转向镜头」**：首帧是 3/4 侧面，成片里人
第 1 秒就转成正面；我们在 `preserve_en` 里加了显式朝向锁定句，
**1.0 / 0.95 / 0.85 三档 strength 全部照样失败**。这条在视频层已经没有已知
修法，唯一出路是回关键帧层换思路。

所以 Reviewer 的结论从两种变成三种：

| verdict | 意思 | 下一步 |
|---|---|---|
| `pass` | 过 | 进下一个 unit |
| `retry_l1` | 视频层能修 | 改镜头卡字段/seed/拆段/局部重绘，重新生成 |
| **`escalate_l2`** | **首帧本身不对，重试视频是浪费钱** | 走 `rekey_shot.py` 回关键帧层重出图 |

**怎么判**：完整的路由表在
`short-drama-video-gen/references/keyframe_escalation_guide.md`，按"看到什么
现象 → 归哪一层 → 改哪个字段"组织。几条最常见的：

- 台词没说完、动作糊、只有镜头动 → **L1**（时长/节拍/seed）
- 人物转向镜头、上一镜的人这镜没了、机位看不到该看的、景别不对、朝向跟
  对话逻辑矛盾、长相服装跟前镜对不上 → **L2**
- 这一镜本身信息量撑不住时长、连续三镜同一底板、台词长到拆段也塞不下
  → **L3（分镜层）**，**停下来交给用户，Reviewer 不许自己动 `ep0X.md`**

**`escalate_l2` 必须给出可执行的补丁**，光说"首帧不对"没用：

```json
{
  "verdict": "escalate_l2",
  "why": "镜24 首帧里顾瑶是端坐的，分镜要求半躺+小腿架扶手；视频层改不了姿势",
  "keyframe_card_patch": {
    "people[顾瑶].posture_zh": "整个人半躺着陷在转角沙发靠南那一段里……一条小腿架在沙发扶手上"
  },
  "recheck": "重出图后逐张看：小腿是不是真的架在扶手上、两人是不是都没抬头"
}
```

**Generator 收到 `escalate_l2` 之后**跑
`short-drama-video-gen/scripts/rekey_shot.py`，它把整条链包起来了：
改卡 → 重装配关键帧提示词 → 重出图 → **人工逐张看** → 回填 `first_frame`
**和 `first_frame_state_zh`** → 重装配视频 job。

⚠️ **回填时重写 `first_frame_state_zh` 是硬闸门，不是提醒**。新图姿态跟旧图
不一样，节拍必须从**新图**已有的状态继续；漏了就直接掉进 ledger A3
（人物不动、只有镜头在动）。这个坑我们已经栽过 17 次，所以 `rekey_shot.py`
在 `--adopt` 时不给 `--state` 会**直接拒绝执行**。

**L2 也要封顶**：单镜最多升级 **1 次** L2；L1 的三轮上限**不因升级而重置**。
一镜的总预算是「最多 3 轮 L1 + 最多 1 次 L2」，用完还不行就标 `capped_l2`
放行，交给人工决定要不要上 L3。理由跟三轮上限一样：视频比图片贵得多，
而 L2 比 L1 更贵（要重新出图 **再** 重新跑视频）。

**局部重绘（利用 `ltx_pipelines.retake`）**：如果某一轮的问题只出现在
视频的一小段时间窗口、其余画面完全正常，不要整段重来——Reviewer 会给出
`defect_window`，下一轮改用 `ltx_ssh_submit.py --retake <start> <end>`
只重新生成这一段，省下重跑整段（尤其是升到正式分辨率/时长后）的显卡
时间。这条能力是 2026-09 查完 LTX-2.5 官方文档后新加的，官方文档记载但
参数名还没在这个仓库里用 `--help` 实测确认，第一次用先看
`short-drama-ltx-generate/references/ltx_pipeline_gotchas.md` 里对应的
提醒。另外要注意：**`ref_images`/`negative_prompt` 这两个字段在自建
LTX-2.5 通道上都不生效**（`ltx_ssh_submit.py` 从不读取/传递），`fix_instruction`
不能落在这两个字段上，只能落在镜头卡字段（`beats[i].motion_en`/
`beats[i].t`/`camera_en.rig`）/`seed`/分段/局部重绘这几项
真正有效的杠杆上，见 `references/reviewer_agent.md`。

## 4. 汇总落地

跑完这一批 unit 之后：

- **第一件事：把显卡关掉**。循环跑完（所有 unit 都 pass 或到轮次上限
  放行）之后，登记表格、写汇报、给用户看抽帧截图这些全是本地工作，
  显卡挂着不干活就是纯烧钱。所以先跑
  ```bash
  python3 .claude/skills/short-drama-ltx-generate/scripts/gpu_teardown.py \
    --config output/<故事名>/videos/ep0X/ltx_remote_config.json
  ```
  确认输出里有 `✅ 已确认停止计费` 再继续往下写汇报（RunPod 上它默认
  terminate Pod，Network Volume 上的模型权重不受影响，下次挂同一个卷
  重建即可）。这一步不用问用户"要不要关"，用完就关是默认行为；只有用户
  明确说接下来还要继续跑、或者还有 unit 等着补跑时才留着。细节和各平台
  差别见 `short-drama-ltx-generate/SKILL.md`「用完就关」一节。
  **注意**：这个循环里 Generator 是一个 unit 一个 unit 提交的，所以
  **不要**给循环内的 `ltx_ssh_submit.py` 加 `--auto-stop`（那会在第一个
  unit 跑完就把显卡关了，后面的 unit 全部失败）——`--auto-stop` 只适合
  "一次性批量提交完就不再用显卡"的场景。
- 按 `video_jobs.md` 的表格格式登记结果，多加两列：**用了几轮**、
  **结果（通过/到三轮上限放行，附具体卡在哪一帧/哪个环节）**。
- 给用户的汇报要点名：这一批共 N 个镜头，M 个一轮就过，K 个 2-3 轮后过，
  P 个跑满 3 轮仍未通过（逐个列出问题和抽帧截图路径），本轮总共提交了
  多少次生成任务（视频比图片贵，这个数字比出图流程更值得强调）。
- 3 轮仍未通过的镜头不要自己决定"将就用"，按
  `video_review_checklist.md`"何时可以判定这个镜头没必要用图生视频"一节
  的思路，把"降级为本地推拉摇移（`ken_burns.py`）兜底处理，不再走图生视频"
  作为一个选项列给用户，交用户决定。

## 与其他 skill 的衔接

- 上游：`short-drama-ltx-export`（`video_jobs.json` + 校验通过的
  `ltx_remote_config.json`）、`short-drama-ltx-generate` 第 1-3 步（已经
  租好显卡、搭好环境、核实过 pipeline 参数）、`short-drama-scout`（分集
  大纲/人物小传，作为 `script_ref` 的来源）。
- 平行：`short-drama-video-gen` 负责提示词撰写方法论和 `extract_frames.py`
  抽帧工具，`short-drama-ltx-generate` 负责 GPU 租赁/环境/pipeline 参数
  的实测踩坑记录，本 skill 都直接复用，不重新实现。
- 下游：产出的视频文件路径和登记表跟原来 `short-drama-ltx-generate` 第 5-7
  步一致，可以直接接续那份 skill 的收尾流程（`gpu_teardown.py` 关显卡、
  补踩坑记录）。
