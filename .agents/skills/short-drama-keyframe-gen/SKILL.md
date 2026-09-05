---
name: short-drama-keyframe-gen
description: 短剧逐集关键帧工作流：先填卡并机械装配提示词，经用户确认后，由至少四个独立subagent生成和审查场次主帧、逐镜关键帧，输出keyframes.md；要求走位、景别、角色和道具连戏一致。
---

## Codex 运行适配（业务工作流已按用户要求更新）

- 在本项目根目录运行；此 skill 的 Codex 入口为 `.agents/skills/short-drama-keyframe-gen/SKILL.md`，用 `$short-drama-keyframe-gen` 调用。
- 原文中的 Read：文本用文件读取工具，图片用图片查看工具；Bash 用 shell，Write/Edit 用文件编辑工具，Glob/Grep 用文件搜索工具；WebFetch/WebSearch 用可用的网页检索工具。
- 原文提到其他 skill 时，读取同级 `../<skill-name>/SKILL.md`。Task/subagent/Generator/Reviewer 对应 Codex 的独立子代理能力；保留原来的职责隔离、轮次和预算，实际并发受宿主上限限制。能力缺失时报告限制，不声称已经执行。
- 原文相对于 skill 的 references/、scripts/ 路径仍相对于本目录。原文命令里的 `.claude/skills/` 脚本及文档路径在 Codex 执行时映射到 `.agents/skills/`；项目素材、输出和私有配置文件的路径保持原意。脚本内部实现及默认配置保持原样，源目录与目标目录共存。
- 原文的确认节点、输入要求和业务规则保持不变。本文只适配执行宿主，不自动执行生成、租卡或 API 调用。

<!-- ORIGINAL-BODY-START -->

# AI 短剧关键帧生成助手 (short-drama-keyframe-gen)

承接 `short-drama-storyboard`（分镜表）+ `short-drama-image-gen`（人物/场景
基准图）之后的下一步：把这一集分镜表里的**每一镜**都出图（不按 S/A/B/C
分级筛选），产出这一集完整的关键帧图库。

## 为什么拆成两个阶段

**关键帧的走位是不可返修的一次性决定。** 下游图生视频的首帧是用
`--image <path> 0 1.0` **焊死**的（见
`short-drama-video-gen/references/shot_card_schema.md` 的
`first_frame_strength` 一节）——首帧里人站错位置、朝错方向、景别不对，
到视频阶段改提示词**没有任何用**，模型只会在"照首帧"和"照文字"之间摆烂。
所以走位必须在**出图之前**由人看一遍，而不是出完图再回头返工。

《出狱后》ep03 就是没有这道闸门的样子（三张实拍证据和成因分析见
`references/blocking_guide.md`）：`ep03_镜10` 标的中景三人，出来是三个人
同一纵深横排、两人平脸朝镜头、画面下半 40% 空地板的"合影"；`ep03_镜03`
同样从中景漂成全身全景。那批 prompt 的走位描述并不短——**失败不是因为写得
少，是因为朝向没有相对镜头的字段、纵深没写、景别只是一句放在散文尾部的
`【景别】中景`，和"保持场景与参考图完全一致"直接打架**。

于是：

- **阶段一（提示词阶段，不出图、不花钱）**：每一镜填一张关键帧卡 → 脚本
  机械装配提示词 + 校验 + 生成审阅表 → **停下来等用户确认**。
- **阶段二（出图阶段）**：拿到确认才真正生成、验收、整理 `keyframes.md`。

和 `short-drama-video-gen` 的镜头卡是同一套纪律：**提示词是派生产物，不手写。**
要改提示词只能改卡再重跑脚本。

## 2026-09-04：又补了「连戏」和「焦段」两层

上面那套（走位/朝向/景别）救的全是**单镜内**的属性，实测有效。但《出狱后》
v2 ep01 整集剪出来之后暴露了另一类问题，它们全都是**镜与镜之间**的：

| 症状 | 根因 | 现在的对策 |
|---|---|---|
| **上一镜在场的人，下一镜不见了** | 卡上只有 `people[]`（这一镜要演谁），**没有字段承载"画面里还应该看得见谁"**。ep01 场次 1-3 四个人全程在客厅，九镜里五镜画面中有那张沙发、卡上一个字没写沙发上的两个人 → 出来的图沙发是空的（`ep01_镜25`） | `scene_beats[].present` 列出这一段戏在场的所有人；每一镜必须让 `people` / `background_people` / `present_off_frame` **三个名单加起来正好覆盖它**，漏人直接 ERROR |
| **场景/机位选的不对** | 一集 35 镜里 **22 镜是近景/特写**，却全挂在宽景定场底板上。底板里没有那个距离的像素，"推近 2.1 倍"只能让模型重新合成一个相机——一旦它重新合成相机，"保持场景与参考图一致"就整体失效（`ep01_镜24` 标 A主机位、出来是全新机位） | 底板分**宽/紧两档焦段**，近景/特写必须挂 `_紧` 底板，对不上直接 ERROR |
| **该有的场景状态变化没体现 / 道具变样** | 房间此刻是什么状态没有任何地方存，全靠每张卡手抄。ep01 第一轮：行李箱变棕皮箱、登山包跳到肩上、虚焦人影变成一男一女 | `scene_beats[].state_zh` 存这一场的既成事实，**每一镜的提示词都会重复一遍**；跨镜复用的道具外观写死在这里 |

同时新增**场次主帧**（`scene_beats[].master_frame`）：每个场次节拍先出一张
"这个房间此刻的全貌"，中景/全景镜以它为状态基准，不再从空房间重新把人搬进去。
细节见 `references/keyframe_card_schema.md`，装配器是
`scripts/build_master_frame_prompt.py`。

## 强制执行：至少四个独立 subagent

根据用户要求，本 skill 的实际出图与审查统一交给
[loop-picture-generation](../loop-picture-generation/SKILL.md)。每个获准执行的出图
批次至少四个不同的真实子代理，主代理不计入。默认两名生成者分担任务、两名审查者
分别逐张审图与核对连续性；仅一张任务时改为一名生成者和三名审查者，不额外出图。
生成者不能审自己的图；主代理负责卡片、调度和登记，不能代替生成或独立审查。
四个是累计参与数，实际同时运行数受宿主限制，可分批；记录真实 agent ID 及交付物，
不能把主代理、同一代理的角色切换或四个脚本进程算成四个 subagent。
本节替代下文旧的“主代理自己生成／自查”和“可选多代理”执行方式，其余素材、
提示词装配与验收要求沿用。调用脚本的示例交给 Generator 执行，逐张和场次验收交给
不同 Reviewer 执行。每轮1→2→3、每项最多三轮，继承已有次数；到限失败项停止并报告，
继续获准且不依赖失败项的任务。已有用户确认有效；修改skill不等于新增生成授权或重置轮次。

## 0. 先确认输入齐不齐

需要四样，缺哪样就先引导用户补上，不要凭空臆造：

- 分集分镜表 `ep0X.md`（含镜号/场景/**机位**/出场人物/画面描述/景别/分级/
  **剧本原文锚点**等列）。
- `short-drama-image-gen` 产出的 `selected.md`（人物/场景最终选中的基准图
  登记表）——没有它就没法保证关键帧里的人和场景与已有立绘是同一套。
- `characters.md` / `scenes.md`——`scenes.md` 的**「空间关系」块**是走位的
  依据（房间四向速记、各机位左右关系、人物默认站位）。
- `style_bible.md` 里的画风锚点原句。

同时问清楚**这次要处理哪几集**——默认不要一次把全剧跑一遍，逐集处理更方便
中途核对质量、控制成本。

---

# 阶段一：提示词（这一阶段不产生任何图片）

## 1. 确认镜头清单（全量，不按级别筛选）

按 `references/shot_selection.md`：**默认每一镜都要生成一张关键帧图**，
唯一例外是备注列明确写了"复用已有素材"且能在 `selected.md`/已有
`keyframes.md` 里查到文件路径的镜头。

先把清单过一遍给用户看一眼：要新生成的镜号列表 + 直接复用的镜号列表
（附文件路径），再往下走。

## 1.5 先划场次节拍 `scene_beats`（新增，做在填卡之前）

**一个节拍 = 一场戏里"房间状态没变"的一段。** 换场景要换节拍；房间发生了
不可逆的变化（有人离开/进来、门关上、东西被放下）也要换节拍。
ep01 一集 35 镜划成 7 个节拍。

每个节拍必须填 `present`（**这一段戏在这个房间里的所有人**，抄分镜表
「在场人物」列）和 `state_zh`（房间此刻的既成事实）。这两样是后面所有
连戏校验的判据，**填不出来就不要往下走**。

主场景（一场戏三镜以上、两人以上在场）还要填 `blocking` 和主帧提示词。
阶段一只装配主帧 jobs 与审阅表，**此时不生成主帧，也不填写虚构的 master_frame 路径**。
逐镜卡先依据已看过的空场景底板填写，将主帧方案与逐镜方案一起交给用户确认。

```bash
python3 .claude/skills/short-drama-keyframe-gen/scripts/build_master_frame_prompt.py \
  output/<故事名>/keyframes/ep0X/keyframe_cards.json --lint
python3 .claude/skills/short-drama-keyframe-gen/scripts/build_master_frame_prompt.py \
  output/<故事名>/keyframes/ep0X/keyframe_cards.json \
  -o output/<故事名>/keyframes/ep0X/jobs_master_ep0X.json
```

用户批准后，在阶段二先由四人工作流生成和独立审查主帧。通过后才回填真实
`master_frame` 与按图记录的 `master_frame_read_zh`，重跑逐镜装配和lint，再生成逐镜图。
只补已批准设计的参考路径无需重复确认；若实际主帧迫使走位等设计实质变化，先展示变更。

## 2. 逐镜填关键帧卡 `keyframe_cards.json`

字段定义见 `references/keyframe_card_schema.md`，走位怎么设计、朝向词表、
词表和硬规则见 `references/blocking_guide.md`。落盘到
`output/<故事名>/keyframes/ep0X/keyframe_cards.json`。

填卡的关键动作，一步都不能省：

1. **先用 Read 工具把这一镜要用的机位底板图真的打开看一遍**，把图里
   左/中/右/纵深各是什么、地面占多少如实写进 `plate_read_zh`。人能站哪、
   画面能裁到哪，由底板已经拍成什么样决定，不由想象决定。
2. **查素材路径，查不到就报缺。** 场景底板的查找键是「SC 编号 + 时段 +
   机位」三段；人物要对上造型阶段/视图。要的机位查不到就**停下来报缺**，
   不要用同场景别的机位顶替、更不要不传场景参考图靠文字现编背景。
   （历史违反：`ep02_镜11` 完全没传场景参考图现编了个厨房；ep01+ep02 的
   73 条 job 场景参考图 73/73 全是同一张 `_00.png`。）
3. **逐人填走位**：`pos_x`（画面左右）/ `depth`（纵深层）/ `body_dir`
   （身体朝画面哪边）/ `camera_relation`（**相对镜头露多少脸**）/
   `gaze_at`（视线落点）/ `posture_zh` + `action_zh`（**这一瞬间**在做什么）。
   `camera_relation` 是必填枚举，**不许因为省事一路填成 3/4 正面**——默认值
   就是失败的来源。近端那个人的默认答案是过肩（`three_quarter_back`）。
4. **景别写成裁切**：`shot_size` + `subject_frac`（主体占画幅高度的数）+
   `crop_zh`（上下边切在人身上哪里、地面留几分）+ `plate_crop_zh`
   （这一镜取底板的哪一块、哪些东西因此看不到）。四个一起才拦得住漂移。
5. `script_ref_zh` 抄分镜表「剧本原文锚点」列——这是阶段二验收的**唯一
   依据**，不要拿「画面描述」列当验收标准（那是提示词的输入，拿它判卷等于
   自己出题自己判卷）。
6. **对这一节拍在场的每个人表态**：在画面里演 → `people[]`；在画面里但不是
   主体 → `background_people[]`（走同一套走位枚举，**必须给参考图或
   `appearance_zh`**）；确实看不见 → `present_off_frame[]`。
   **三个名单加起来必须正好等于 `scene_beats[].present`。**
   判断"看不看得见"的依据是这一镜的取景，不是"这一镜讲的是谁"——
   画面里有那张沙发，沙发上的人就在画面里。
7. **按景别挂对焦段的底板**：近景/特写挂 `_紧`，中景/全景挂宽底板。
   要的紧底板不存在就**报缺**（跑一遍 `--lint`，它会点名缺哪张），
   参照 `short-drama-storyboard/references/scene_prompt_template.md`
   「焦段」一节把它派生出来。

运镜（推/拉/摇/移）和时长这一步一律不写，那是下一步（图生视频）的事。
机位不是运镜，它靠**选对底板**体现。

## 3. 装配提示词 + 校验 + 生成审阅表

```bash
# 先 lint，看装配结果和校验报告
python3 .claude/skills/short-drama-keyframe-gen/scripts/build_keyframe_prompt.py \
  output/<故事名>/keyframes/ep0X/keyframe_cards.json --lint

# 全绿之后写出审阅表和 jobs
python3 .claude/skills/short-drama-keyframe-gen/scripts/build_keyframe_prompt.py \
  output/<故事名>/keyframes/ep0X/keyframe_cards.json \
  --review-sheet output/<故事名>/keyframes/ep0X/keyframe_prompts_ep0X.md \
  -o output/<故事名>/keyframes/ep0X/jobs_ep0X.json
```

约定从仓库根目录运行（卡里的图片路径是仓库相对路径）。脚本会硬拦：

- 一镜里正脸（`front`）超过 1 人；两人以上的镜头全员正面/3⁄4 正面（"合影"）。
- 两人以上没有两个不同的 `depth`（同层横排）、`pos_x` 全相同。
- 视线目标和身体朝向对不上；两人互相对视但朝向同边。
- 同场景 `A主机位` 和 `B反打` 两镜里共享人物左右没有翻转（越轴）。
- 缺 `subject_frac` / `crop_zh`；非全景镜缺 `plate_crop_zh`；
  `subject_frac` 和景别对不上。
- `plate_read_zh` 太短（没真的看图）；底板/人物参考图路径不存在。
- 拿否定句写走位或景别（包括写在 `avoid_extra_zh` 尾块里）。
- **在场的人没有表态**（`scene_beats[].present` 里有、三个名单里都没有）。
- **画外声明和取景打架**：某人写进 `present_off_frame`，而 `seating` 记着他
  在沙发上、这一镜的取景说明又明写着取了沙发那一块。
- **近景/特写挂在宽景底板上**（除非写了 `plate_tier_waiver_zh` 说明理由）。
- 挂了 `master_frame` 却没按图写 `master_frame_read_zh`。

有 ERROR 时脚本**不写 jobs.json**，先改卡。WARN 需要人工判断，不阻塞。

## 4. 闸门：把审阅表交给用户，等确认（不许自己跳过）

把 `keyframe_prompts_ep0X.md` 的路径给用户，并在对话里点出需要他重点看的
地方：正脸/过肩的分布、几个人的纵深层次、景别对应的裁切、以及所有 WARN。
**明确说清这一步还没有出任何图。**

然后停下来。**没拿到用户明确的"可以出图"之前，不要进入阶段二。**

用户提修改意见时：**改卡，重跑脚本**。不要手改 `keyframe_prompts_ep0X.md`
或 `jobs_ep0X.json`——手改的内容下次装配就会被冲掉，而且审阅表和真正发给
模型的提示词会不一致，那道闸门就等于没有。

如果用户明确说"不用看了直接出图"，可以直接进阶段二，但先把 lint 的 WARN
念给他听一遍。

**老集数只有 `jobs_ep0X.json`、没有关键帧卡时**（2026-09 之前跑的），不要
为了补卡去重跑已经验收过的集数；只有当这一集要重出图时才补卡——补卡的成本
就是把那一集的走位重新设计一遍，而这正是重出图的目的。

---

# 阶段二：出图（拿到确认之后）

## 5. 调用脚本生成

先按第1.5节完成获准主帧的生成、独立审查、真实路径回填和逐镜任务重新装配，再生成逐镜图；主帧及逐镜图均强制采用至少四个subagent的工作流。

直接复用 `short-drama-image-gen` 的生成脚本，不重复造轮子：

```bash
python3 .claude/skills/short-drama-image-gen/scripts/generate_images.py \
  output/<故事名>/keyframes/ep0X/jobs_ep0X.json \
  --out-dir output/<故事名>/keyframes/ep0X
```

Codex CLI 登录、速率限制注意事项见
`.claude/skills/short-drama-image-gen/references/api_setup.md`。

出图模型是 Codex CLI 内置 `image_gen` 底下的 **OpenAI GPT Image 2**。这条链路有两个结构性限制会影响这一步：
`quality`/`input_fidelity` 这些 API 旋钮**拿不到**，能控的只有提示词和参考图；
每次调用**无记忆**，所以画风锚点/角色描述/保留清单每镜都要传全。
参考图数量控制在 **3–5 张**（1 底板 + 1–3 人物），不要每个人都塞两张视图。

## 5.5 一轮只出一张（2026-09-05 改）

卡上的 `count` **默认 1**，装配器就是按 1 写进 `jobs_ep0X.json` 的。
不要为了"保险"在首轮把它调大。

依据是这一集自己的数据：v2 ep01 **35 镜里 31 镜第一张就能用**，只有 4 镜
（镜21/24/27/30）需要返工。按老做法首轮每镜出 3 张，就是给那 31 镜各白烧
两张额度和时间——一集多烧近 70 张，结果一样。

**多出是返工时的手段，按轮次加：**

| 轮次 | `count` | 说明 |
|---|---|---|
| 第 1 轮 | **1** | 默认 |
| 第 2 轮 | 2 | 已经证明这一镜有难度，而且这一轮的卡里带着上一轮的具体修改 |
| 第 3 轮 | 3 | 最后一轮，从这 3 张里挑最好的 |

三轮之后停下来报给用户，不要无限重试。阶梯的自动执行见
`loop-picture-generation/references/units_schema.md`「加量阶梯」。

还有个副作用是好的：**首轮只有一张，验收时没得挑，只能对着标准判**。
一次给 3 张容易滑向"这三张里哪张最好"——那是选美不是验收，标准会被
现有候选悄悄拉低。

## 6. 验收，不合格就改卡重生成

由独立 Reviewer 用图片查看工具逐张实际查看，按 `references/keyframe_review_checklist.md`
核对：是否还原了 `script_ref_zh` 讲的那件事、**走位/朝向/纵深/景别是否
和审阅表上那份设计一致**、人物是否与基准图同一张脸同一套衣服、场景是否
和该机位底板一致、跨机位是否同一个房间、有没有越轴。

不合格时**改卡对应的字段再重跑装配脚本**（比如把某人的
`camera_relation` 从 `three_quarter_front` 改成 `three_quarter_back`、
把 `plate_crop_zh` 写得更狠），不要直接手改 prompt。单个镜头连续 3 轮
选不出可用图就停下来向用户汇报，不要无限重试。

## 6.5 一场戏的图出完之后，排开一起再看一遍（不许省）

**逐张验收抓不到连戏问题。** 一张图里沙发是空的，单看毫无毛病；只有和前一镜
并排放在一起，才看得出"上一镜那两个人去哪了"。ep01 场次 1-3 那九张图
**逐张都验收通过了**，剪在一起才发现问题。

所以一场戏的图全部出完之后，按镜号平铺一起看，逐条核对
`references/keyframe_review_checklist.md`「三点五、场次级验收」那五条：
人有没有凭空消失/出现、道具有没有变样、光有没有跳、跨机位还是不是同一个房间、
服装发型有没有变。有主帧的场次，**把主帧和这一场每一镜并排看**最省事——
主帧就是这一场的标准答案。

不通过时问题多半在 `scene_beats` 那一层（`present` 漏人、`state_zh` 没写死
道具外观），改那里再重出，不要一镜一镜打补丁。

## 7. 整理产出

把**每一镜**最终选中的一张（新生成的或复用的）整理进
`output/<故事名>/keyframes/ep0X/keyframes.md`，镜号与分镜表一一对应、不漏镜：

| 镜号 | 场景 | 机位底板 | 出场人物 | 对应画面描述 | 选中文件路径 | 分级 | 来源（新生成/复用） |
|---|---|---|---|---|---|---|---|

这份表就是"图生视频"环节要直接引用的起始帧素材清单。

## 8. 汇报

本集共 N 镜，全部已出图（M 镜新生成、K 镜复用，附镜号），本轮调用生成
多少次，以及阶段一审阅时用户改过哪些走位——最后这条要记进
`keyframes.md` 备注，下一集填卡时照着来，同一个毛病不要犯两次。

## 与其他 skill 的衔接

- 上游：`short-drama-storyboard`（分镜表 + `scenes.md` 的空间关系块）+
  `short-drama-image-gen`（基准图与 `generate_images.py`，本 skill 直接复用）。
- 下游：`keyframes.md` 里的路径会被 `short-drama-video-gen` 当作首帧引用；
  关键帧卡上的走位字段和镜头卡的 `first_frame_state_zh` 是同一件事的两端，
  填镜头卡时可以直接抄这边的 `posture_zh`/`action_zh`。
- **阶段一照跑不变**；阶段二（包含场次主帧）强制调用
  `loop-picture-generation`，把源卡、批准记录与 jobs 一起交给它，
  由至少四个不同的 subagent 完成生成和独立审查。

## 人读与机器产物分开

按 [阅读目录约定](../loop-picture-generation/references/output_layout.md) 整理产物；完成本轮生成与验收后刷新给人看的分镜、图片和进度入口。
