---
name: short-drama-keyframe-gen
description: 面向 AI 短剧的逐集分镜关键帧生成助手，**分两个阶段、中间有一道人工闸门**：阶段一只产出提示词不出图——读 short-drama-storyboard 的分集分镜表（ep0X.md）和 short-drama-image-gen 选定的人物/场景基准图，把这一集**每一镜**填成结构化的「关键帧卡」`keyframe_cards.json`（逐人写清在画面里的位置、纵深层、身体朝向、**相对镜头露多少脸**、视线落点、这一瞬间的动作，以及景别对应的裁切线），再用 `scripts/build_keyframe_prompt.py` 把卡机械装配成提示词 + 一份人能逐镜看的审阅表 `keyframe_prompts_ep0X.md`，装配时强制校验"一镜最多一人正脸/多人镜必须有人过肩背对/多人镜必须分纵深层/景别必须写成裁切/正反打必须越轴/参考图路径必须存在"；**停下来把审阅表交给用户确认**，用户改意见就改卡重跑脚本（提示词是派生产物，不手写、不手改）。阶段二拿到确认后才真正调 Codex CLI 出图、逐张验收、产出 keyframes.md。当用户要求"生成关键分镜图""按分镜出关键帧""把这集分镜全部做成图""先给我看提示词再出图""人物不要都正面对着镜头""设计好人物在场景里的位置和朝向"时使用。
---

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

直接复用 `short-drama-image-gen` 的生成脚本，不重复造轮子：

```bash
python3 .claude/skills/short-drama-image-gen/scripts/generate_images.py \
  output/<故事名>/keyframes/ep0X/jobs_ep0X.json \
  --out-dir output/<故事名>/keyframes/ep0X
```

Codex CLI 登录、速率限制注意事项见
`.claude/skills/short-drama-image-gen/references/api_setup.md`。

出图模型是 Codex CLI 内置 `image_gen` 底下的 **OpenAI GPT Image 2**
（**不用 Gemini**）。这条链路有两个结构性限制会影响这一步：
`quality`/`input_fidelity` 这些 API 旋钮**拿不到**，能控的只有提示词和参考图；
每次调用**无记忆**，所以画风锚点/角色描述/保留清单每镜都要传全。
参考图数量控制在 **3–5 张**（1 底板 + 1–3 人物），不要每个人都塞两张视图。

## 6. 验收，不合格就改卡重生成

用 Read 工具逐张实际查看，按 `references/keyframe_review_checklist.md`
核对：是否还原了 `script_ref_zh` 讲的那件事、**走位/朝向/纵深/景别是否
和审阅表上那份设计一致**、人物是否与基准图同一张脸同一套衣服、场景是否
和该机位底板一致、跨机位是否同一个房间、有没有越轴。

不合格时**改卡对应的字段再重跑装配脚本**（比如把某人的
`camera_relation` 从 `three_quarter_front` 改成 `three_quarter_back`、
把 `plate_crop_zh` 写得更狠），不要直接手改 prompt。单个镜头连续 3 轮
选不出可用图就停下来向用户汇报，不要无限重试。

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
- 镜头多、想用"生成 agent + 审查 agent 互相制衡"且最多 4 路并行提速时，
  **阶段一照跑不变**（闸门不能省），阶段二的第 5-6 步换成
  `loop-picture-generation`，把 `jobs_ep0X.json` 交给它。
