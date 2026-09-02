---
name: short-drama-video-gen
description: 面向 AI 短剧的图生视频提示词与角色动画编排助手：承接 short-drama-keyframe-gen 产出的关键帧图库和 ep0X.md 分镜表里的"运动描述"列，把每个 S/A/B 级镜头（C 级复用不需要）拆成 4-8 秒的生成单元，填成结构化的**镜头卡** `shot_cards.json`（机位/主体锁定/逐拍动作/台词/风格尾块/seed/时长），再用 `scripts/build_prompt.py` 把镜头卡机械装配成提示词和 `video_jobs.json`——**提示词是派生产物，不手写**，装配时强制校验否定句、台词语言声明、台词时长、节拍预算、token 上限、seed 有效性。并给出稳定性方案（运动幅度控制、分段生成拼接、先测后上正式分辨率）防止人脸崩坏和动作失控。**只产出提示词/任务清单，不实际调用任何视频生成 API 或脚本**——自建 LTX-2.5 路径的实际打包/提交/生成/验收全部交给下游 `short-drama-ltx-export` + `short-drama-ltx-generate` 两个 skill；本地零成本的 ffmpeg 推拉摇移脚本（`ken_burns.py`）不再是 B 级镜头的默认路径，只在某镜反复生成失败时作为兜底方案使用。当用户说"把关键帧做成视频""生成图生视频提示词""这一镜怎么做动画""关键帧转视频""设计视频生成工作流""引导角色动作"时使用。
---

# AI 短剧图生视频与动画编排助手 (short-drama-video-gen)

承接 `short-drama-keyframe-gen`（关键帧图库）之后的下一步：把静态关键帧变成
"会动"的短剧素材。这一步的产出主要是**提示词和任务清单**，不是像出图那样
能一键跑通的免费自动化流程——先把这个现实情况和用户说清楚，再往下做。

## 0. 先说清楚一个现实：没有免 API key 的图生视频通道

`short-drama-image-gen`/`short-drama-keyframe-gen` 能用 Codex CLI（ChatGPT
登录）免费出图，是因为 `codex exec` 内置了 `image_gen` 工具。**视频生成没有
对应的免费路径**：OpenAI Sora 的网页版/App 已于 2026-04-26 下线，API 也计划
在 2026-09-24 停运，且 Codex CLI 本身不带任何视频生成工具。可灵、即梦、
Vidu、PixVerse、海螺、Runway、Veo 等主流图生视频平台都是订阅制或按秒计费的
独立产品，没有能白嫖的等价物。

所以本 skill 的产出是：**把每个镜头需要的完整提示词、参考图、时长、平台建议
整理成一份"提交清单"**，由用户手动粘贴到平台网页版生成（默认路径），或者
如果用户自己有某平台的 API key，可以照着清单里的字段自己接调用脚本（本
skill 不内置这类调用脚本，因为各家 SaaS 的 API 差异大、需要用户自己的
计费账号）。

**例外：用户自己租显卡、自己部署开源模型（比如 Lightricks LTX-2.5）**。
这种情况不是"平台订阅"，而是用户自己完全控制的推理环境，不存在"各家 API
不一样"的问题，但**这不代表本 skill 可以顺手就把生成也做了**：本 skill
只负责把镜头卡填好、用 `build_prompt.py` 装配出 `video_jobs.json`，**真正
打包提交、租显卡、跑生成、验收这几步一律交给下游的 `short-drama-ltx-export`
（打包校验）+ `short-drama-ltx-generate`（实际执行）两个 skill**，本 skill
不调用 `ltx_ssh_submit.py`，也不检查/操作显卡实例，见第 4.5 步的交接说明。

先跟用户确认属于哪种情况（SaaS 手动提交 / 自建模型 LTX-2.5 / 都不是），
避免走错流程；不管走哪种，本 skill 的最终产出永远只是**镜头卡
`shot_cards.json` + 装配出的 `video_jobs.json`**，不含任何实际生成的视频。

**2026-09 变更**：B 级镜头不再默认走本地 `ffmpeg` 零成本处理，跟 S/A 级
一样正常进图生视频/LTX 生成，只是动作幅度压到最低、时长压到最短。本地
`ffmpeg` 推拉摇移脚本（第 5 步）改为"某镜反复生成失败时的兜底方案"，不是
B 级镜头的默认路径。

## 1. 先确认输入齐不齐

- `short-drama-keyframe-gen` 产出的 `keyframes.md`（关键帧文件路径登记表）
  ——没有这个就没有稳定的起始帧，不要凭空猜一张图当首帧。
- 对应的 `ep0X.md` 分镜表，重点是"运动描述(S/A级需要)"列（简写的动效提示）、
  "运镜"列、"分级"列、"时长(秒)"列、"转场"列。
- `characters.md` / `scenes.md` 的画风锚点和角色档案（判断动作幅度是否会
  破坏角色关键特征，比如长发/裙摆的物理表现）。
- `short-drama-image-gen`/`short-drama-keyframe-gen` 的 `selected.md`（补充
  人物参考图，比如需要维持一致性的第二张角度图）。

同样问清楚这次处理哪几集/哪几个镜头，不建议一次性把全剧 S/A 级镜头都展开，
分批做方便中途核对提示词效果再调整。

## 2. 按分级路由，不是每个镜都要"生成视频"

- **C 级**：直接复用已有视频片段，跳过，不产出新 job——四档里唯一真正
  零成本、不进图生视频模型的档位。**但要先核实这一镜真的不承载新台词/新
  情节信息**：翻一下 `ep0X.md` 这一镜的"台词/旁白"列，如果分镜表标了
  C 级却写了新台词/新情节，说明分级标错了，按实际内容量级改成正常生成
  （多数是 A 级），不要因为表格写的是"C"就机械跳过——复用旧素材的口型/
  音频对不上新台词，观众看得出来，跳过会导致这段剧情实际上没讲出来。
- **S/A/B 级**：都进入第 3-4 步展开详细提示词，走图生视频/LTX 生成。区别
  只是动作幅度和时长预算：B 级镜头（空镜头/环境介绍/内心活动/时间流逝）
  按第 3 步的标准写成"近乎静止"的最小动作幅度、时长压到最短（比 A 级还
  保守），靠"几乎不动"而不是"不生成"控制成本，不要因为是 B 级就跳过
  展开提示词这一步。

## 3. 拆生成单元、看首帧图，然后填镜头卡

**这一层的第一条规则：提示词不手写。** 人维护镜头卡
（`shot_cards.json`），提示词由 `scripts/build_prompt.py` 按固定模板机械
装配。同一张卡永远装配出同一段字符串；要改提示词，只能改卡上的某个字段
再重跑脚本。字段定义见 `references/shot_card_schema.md`，装配规则见
`references/video_prompt_guide.md`。

### 3.1 先做跨镜头连贯性核对

按 `references/video_prompt_guide.md`「填卡之前的两道必做检查」第一道：
回头看上一镜的结束姿态/情绪/光影，确认这一镜的起始状态是它的自然延续，
再看一眼下一镜的起始需求。这是硬标准不是可选项——之前反复出现的"角色动作
与上下分镜不匹配"，根源都是逐镜孤立写提示词。如果分镜表本身就没接上，
停下来提醒用户回头补分镜，不要在提示词里悄悄圆过去。

### 3.2 拆生成单元

**默认把一镜拆成 4-8 秒的生成单元**，前段尾帧作后段首帧（卡上用
`first_frame_from` 声明）。拆段的好处是返工便宜（只重跑出问题那一段）、
定位精确。需要时可以做 10 秒以上的长单镜，361 帧 / 15 秒 @1600×896 实测
无画质衰减，不需要额外标记。

有台词的镜头，单元时长由台词字数决定（见 3.4），不是由分镜表"建议时长"
列决定。

### 3.3 用 Read 工具把每个单元的首帧图打开看一遍

**这一步不能跳过，也不能靠想象。** 首帧是用 `--image <path> 0 1.0` 焊死的，
如果节拍 1 描述的是首帧之前的动作，模型会在"照首帧"和"照文字"之间摆烂，
表现为人物姿态不动、只有镜头在动（实测案例见
`references/model_capability_ledger.md` A3）。

把图里真实的姿态/朝向/光线/道具位置写进卡的 `first_frame_state_zh`，然后
让节拍 1 从这个状态**继续**。雪山决斗那一镜就是靠这一步发现"首帧里剑已经
抬起指向镜头"，把原本的"从身体侧下方慢抬剑"改写成"维持持剑姿态 + 握力
加大 + 剑尖细微颤抖"。

### 3.4 填卡

逐字段填 `output/<故事名>/videos/ep0X/shot_cards.json`。要点：

1. **`script_ref` 必填，而且不能填分镜表"画面描述"列的原文**——那段文字是
   提示词的输入，拿它当验收标准等于自己出题自己判卷。要填的是"剧本原文
   摘录 + 角色小传 + 这一段的判断标准"，分镜表新增的「剧本原文锚点」列
   就是为了让这一步有源可抄。
2. **`beats[].motion_en` 必须过可见位移检验**：每一拍至少写出一个会改变
   位置或形状的身体部位或道具，情绪词只能挂在物理变化上。"她哭了"不合格，
   "眼眶泛红 → 睫毛颤动 → 一滴泪滑落 → 嘴角下撇 → 肩膀抽动一下"才合格。
   写细是对的，一拍内部写多细没有上限。
3. **所有 `*_en` 字段只许写英文，否定句一律改写成正向陈述**。distilled
   pipeline 没有 `--negative-prompt` 参数，否定句只会把不想要的概念注入
   文本编码器。改写方法见指南的「否定→正向改写表」。
4. **有台词的拍：`dialogue.delivery_en` 必须含 `Mandarin Chinese`**，且
   这一拍的时长必须 ≥ `台词CJK字数 / 语速 + 0.8`，语速按 `pace` 取
   `fast` 5.5 / `normal` 4.0 / `slow` 3.0 字每秒。哽咽/压抑/欲言又止一律
   走 `slow`——这类最容易被低估时长。时长不够时 LTX-2.5 会自己把台词压缩，
   **改措辞无效**。
5. **动作幅度按分级控制**：S 级（打斗/拥抱/痛哭/反转瞬间）才适合大幅度动作；
   A 级（对话/反应镜，全集主体）只做小幅度；B 级（空镜/环境/内心活动/
   时间流逝）压到接近静止（光影缓慢变化、衣角发丝细微飘动）。分级也决定
   节拍数上限（S 级每拍下限 0.8 秒，A/B/C 级 2.5 秒）。
6. **`seed` 必填且不能是 10**——10 就是 LTX `--seed` 的默认值，留着等于
   没指定，重跑会原地复现。
7. **过一遍能力清单**：`references/model_capability_ledger.md` 里标为
   "已验证做不到"的项，命中了就在卡的 `known_limit.decision` 里写清楚打算
   怎么办（接受 / 降级成无台词表情镜 / 换 pipeline），别让下游空烧 3 轮
   GPU 去撞已知的墙。最常撞的是 A1：带台词 + 混合克制型情绪 → 收敛成
   通用开怀笑。
8. **首尾帧策略**：动作有明确起止状态差异（比如从跪地到站起）时可以考虑
   用尾帧控制，但尾帧图如果关键帧库里没有，先判断要不要回
   `short-drama-keyframe-gen` 补一张，不要让模型自己瞎猜结束姿态。

## 4. 装配：跑脚本，不手写提示词

```bash
# 先只校验 + 看装配结果
python3 .claude/skills/short-drama-video-gen/scripts/build_prompt.py \
  output/<故事名>/videos/ep0X/shot_cards.json --lint

# 校验全绿后装配出 video_jobs.json
python3 .claude/skills/short-drama-video-gen/scripts/build_prompt.py \
  output/<故事名>/videos/ep0X/shot_cards.json \
  -o output/<故事名>/videos/ep0X/video_jobs.json \
  --emit-prompts output/<故事名>/videos/ep0X/prompts
```

脚本会硬拦这些（每条都对着一个已经付过代价的实测故障，依据见
`model_capability_ledger.md`）：否定句、缺 `Mandarin Chinese` 语言声明、
台词时长不够、节拍数超预算、节拍时间轴不连续、`seed` 是默认值 10、
token 超预算（Gemma 1024 上限**静默截尾**）、`*_en` 字段里混进中文、
`first_frame_state_zh` 空着、`width`/`height` 不被 64 整除。

**报错就回去改卡，不要手改 `video_jobs.json` 绕过校验**——手改会让 `prompt`
和镜头卡脱钩，下游 `short-drama-ltx-export` 的校验会拦。

装配完把 `video_jobs.json` 和 `prompts/*.txt` 交给用户过一眼。走 SaaS 手动
提交路径的话，额外参照 `references/video_platform_comparison.md` 给每镜推荐
1-2 个平台（注意：SaaS 路径下台词**不要**进提示词，那是 LTX-2.5 独有的能力，
见 `video_jobs_schema.md`「关于台词」）。

## 4.5 自建 LTX-2.5：写完提示词就停，交给下游 skill 打包执行

如果用户是自己租显卡、自己部署了 `Lightricks/LTX-2`（LTX-2.5）这类开源
模型，**本 skill 到第 4 步装配出 `video_jobs.json` 为止就算完成任务**——
不要调用或建议调用 `ltx_ssh_submit.py`、不要去租显卡或检查显卡实例状态，
这些都不是本 skill 该做的事，也不要在产出里写任何暗示已经实际跑过的状态值。

装配完之后，明确告诉用户接下来依次交给这两个 skill 接力完成：

1. **`short-drama-ltx-export`**：校验 `video_jobs.json` 能不能被
   `ltx_ssh_submit.py` 直接消费（路径存在性、64 整除、`8k+1`、台词语言
   声明、`seed` 有效性、token 预算、`prompt` 和镜头卡是否还一致），
   检查/生成 `ltx_remote_config.json`，跑一次 `--dry-run`。
   **LTX 专属字段（`width`/`height`/`num_frames`/`seed`）现在由镜头卡提供、
   `build_prompt.py` 装配，export 阶段不再需要补齐它们，只负责校验。**
2. **`short-drama-ltx-generate`**：真正去租显卡（或复用已有实例）、部署
   环境、跑 `ltx_ssh_submit.py` 提交生成、下载结果、抽帧+听审验收，
   并且沉淀了 GPU 租赁/pipeline 参数/角色配音一致性方面的实测踩坑记录。
   **验收/调整重试这些环节也属于 `short-drama-ltx-generate` 的工作范围**，
   但它要改的是**镜头卡的字段**（比如 `beats[1].motion_en` / `seed` /
   `duration_sec` / 拆段），改完重跑 `build_prompt.py`，**不要直接手改
   `video_jobs.json` 的 `prompt`**——那样会让提示词和卡脱钩，下次装配就把
   手改的内容冲掉了。

拆段单元的首帧还没落地（卡上是 `first_frame_from`）时，要提醒用户：必须先跑
第 1 段、抽出尾帧、把路径填回卡的 `first_frame`，才能提交下一段。
抽帧用 `scripts/extract_frames.py`。

本 skill 不重复实现打包/执行/验收逻辑，也不在自己的产出里描述"跑了几轮"
"选中了哪个版本"这类只有实际生成之后才知道的信息——那些内容属于
`short-drama-ltx-generate` 的产出，不是本 skill 该写的。

## 5. 本地兜底：某镜反复生成失败时的推拉摇移方案

**这不是 B 级镜头的默认路径**——B 级跟 S/A 级一样正常走第 3-4 步展开提示词、
交给下游生成。只有某一镜（不分级别）连续 3 轮生成都选不出可用片段（见第 6
步的重试上限），才用关键帧图跑本地 Ken Burns 效果顶上，避免在一个镜头上
无限烧钱：

```bash
ffmpeg -version   # 先确认已安装，没有就指导用户 apt-get/brew 装一下
python3 .claude/skills/short-drama-video-gen/scripts/ken_burns.py \
  output/<故事名>/videos/ep0X/kenburns_jobs.json \
  --out-dir output/<故事名>/videos/ep0X
```

`kenburns_jobs.json` 格式和用法见脚本头部注释：每条 job 指定关键帧图片、
运镜方向（推/拉/摇左/摇右/摇上/摇下）、时长、输出分辨率，脚本调用 ffmpeg
的 `zoompan` 滤镜合成 mp4，不消耗任何生成 API 额度。运镜方向要对应分镜表
"运镜"列，不要随手选一个和分镜意图不符的方向。用了这条兜底要在
镜头卡的 `notes` 和 `ep0X.md` 的备注里注明"原定 XX 级，因反复生成失败降级为
本地推拉摇移"，方便后续复盘别把这类镜头误当成正常生成的结果。

## 6. 验收：范围限定在本 skill 自己产出的视频（本地兜底 + SaaS 手动回填）

Read 工具能看图片，看不了视频。凡是本 skill 自己产出的视频文件（第 5 步
`ken_burns.py` 出的兜底片段），或者用户走 SaaS 路径自己在平台网页版生成、
下载后拿回来给你确认效果的视频，都要先抽帧再看：

```bash
python3 .claude/skills/short-drama-video-gen/scripts/extract_frames.py \
  <视频文件路径> --out-dir <帧输出目录> --count 5
```

用 Read 工具逐张查看抽出来的帧，按 `references/video_review_checklist.md`
核对：首帧是否还是原关键帧的样子（没有跑偏）、中间帧人脸/服装是否保持一致
没有变形换脸、动作方向和分镜表运动描述是否一致、结尾帧是否落在预期的定格
姿态。音画同步（口型/BGM 卡点）只能靠用户自己听，Claude 帮不了这部分，
提醒用户自己确认。

不合格就按 `references/stability_playbook.md` 的思路改**镜头卡**（缩小动作
幅度、把单元拆得更短、换 seed、加长台词那一拍的时长），重跑
`build_prompt.py` 再提交。**不要"加强负面提示词"**——distilled pipeline 没有
这个参数，那个字段从来没被发送过，历史上已经为它白烧过 3 轮 GPU
（见 `references/model_capability_ledger.md` B1）。单个镜头连续 3 轮选不出
可用片段就停下来向用户汇报具体卡在哪，不要无限建议重试烧钱——视频比图片
贵得多。

**自建 LTX-2.5 路径不适用本节**：那条路径下"生成→抽帧验收→调整提示词
重试"整个循环都在 `short-drama-ltx-generate` 里完成（它内部复用的正是
`extract_frames.py` 这个脚本），本 skill 不参与，也不需要用户把 LTX-2.5
生成的视频拿回来给本 skill 二次验收。

## 7. 汇报

结束时给一个小结：本集 S/A/B 级镜头共 N 个、拆成了 M 个生成单元，
镜头卡已填好、`build_prompt.py --lint` 是否全绿（有 WARN 就把 WARN 原文
告诉用户）、装配出了 M 条 job；如果有
镜头因反复生成失败触发了第 5 步的本地兜底，单独说明是哪几镜、原定什么级别。
**自建 LTX-2.5 路径下明确告诉用户：提示词清单已就绪，S/A/B 级镜头目前都
还没有变成视频文件，需要接下来跑 `short-drama-ltx-export` +
`short-drama-ltx-generate` 才能实际生成**，不要把"提示词写完了"说成
"这一镜做完了"。如果走的是 SaaS 路径且用户已经自己手动提交生成过、把视频
拿回来给你核对过，才汇报核对了几轮、最终确认了哪几个镜头的视频文件路径。
这些数字并入 `short-drama-storyboard` 输出模板的"成本与检查记录"。

## 与其他 skill 的衔接

- 上游：`short-drama-keyframe-gen`（关键帧图库 `keyframes.md`）+
  `short-drama-storyboard` 分镜表（`ep0X.md` 的"运动描述""运镜""分级"列）+
  `short-drama-image-gen` 的 `selected.md`（补充一致性参考图）。
- 下游：`shot_cards.json`（人维护的源）+ `video_jobs.json`（装配产物）。
  用户手动生成或接自己 API 拿到视频文件后，路径回填进
  `loop-video-generation` 的 `units_queue.json`，方便剪辑阶段按镜号找素材；
  `ken_burns.py` 兜底产出的视频文件可以直接进剪辑时间线，不需要额外处理；
  自建 LTX-2.5 的场景交给 `short-drama-ltx-export` → `short-drama-ltx-generate`
  接力完成打包和实际生成，视频下载到 `output/<故事名>/videos/ep0X/` 后
  路径回填进 `units_queue.json` 的 `selected_file`；如果想让"提交生成+验收"这一段换成
  出片 agent + 审查 agent 互相打回重做的循环（审查时对照原剧本情节而不是
  分镜表字面描述），`short-drama-ltx-generate` 那一段可以改用
  `loop-video-generation` 执行。
