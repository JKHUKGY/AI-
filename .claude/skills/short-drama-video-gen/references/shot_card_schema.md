# 镜头卡 shot_cards.json 结构定义

镜头卡是**剧本/分镜表和提示词之间的中间层**。它存在的理由只有一个：提示词
不再手写。人只维护卡上的字段，提示词由
`scripts/build_prompt.py` 按固定模板机械装配——**同一张卡永远装配出同一段
字符串**。要改提示词，只能改卡上的某个字段再重跑脚本。

落盘位置：`output/<故事名>/videos/ep0X/shot_cards.json`（顶层是数组）。

**一张卡 = 一个 LTX 生成单元，不是一个分镜镜号。** 一个分镜镜号可以拆成
2-3 张卡（`unit_of` + `unit_index` 标明归属），默认每个单元 4-8 秒。

装配规则和每条校验背后的实测依据见 `video_prompt_guide.md` 和
`model_capability_ledger.md`。这里只定义字段。

---

## 字段总表

| 字段 | 必填 | 进提示词 | 说明 |
|---|---|---|---|
| `id` | ✅ | ✗ | 生成单元 id。拆段的用 `<镜号>_u1`/`_u2`，如 `ep01_镜06_u1` |
| `shot_no` | ✅ | ✗ | 对应分镜表镜号（整数） |
| `unit_of` | 拆段时 | ✗ | 父分镜 id，如 `ep01_镜06`。不拆段就省略 |
| `unit_index` | 拆段时 | ✗ | `[第几段, 共几段]`，如 `[2, 3]` |
| `scene` | ✅ | ✗ | 场景编号，抄分镜表 |
| `tier` | 建议 | ✗ | `S`/`A`/`B`/`C`，抄分镜表分级。**影响节拍数上限**（见下） |
| `intent_zh` | 建议 | ✗ | 一句话中文：这一段要讲成什么。给人快速回看用 |
| `script_ref` | ✅ | ✗ | 给 reviewer 的验收依据。见下方专门一节 |
| `scene_plate` | 建议 | ✗ | 这一单元首帧合成时用的**机位底板 id**，如 `SC04_顾家别墅餐厅_B反打`。抄分镜表「机位」列。见下方专门一节 |
| `first_frame` | 二选一 | ✗ | 首帧图路径。第一段必填 |
| `first_frame_strength` | ✗ | ✗ | 首帧锁定强度，默认 `1.0`（完全锁死）。见下方专门一节 |
| `first_frame_from` | 二选一 | ✗ | 如 `ep01_镜06_u1:last`，声明首帧来自上一段的尾帧（还没生成出来时用） |
| `first_frame_state_zh` | ✅ | ✗ | **看过图之后**如实描述首帧里的状态。见下方专门一节 |
| `last_frame` | ✗ | ✗ | 尾帧图路径，一般为 `null` |
| `props_en` | ✗ | ✗ | 道具名词列表，如 `["sword", "hilt"]`。只用来让"可见位移检验"认识这些词 |
| `camera_en.position` | 建议 | ✅ | 相机站在场景的哪个位置往哪看，一句英文。从 `scenes.md` 的「空间关系」块翻译过来 |
| `camera_en.rig` | ✅ | ✅ | 固定/手持、机高，**只收正向陈述** |
| `camera_en.framing_path` | ✅ | ✅ | 整段的景别走向 |
| `camera_en.move` | ✗ | ✅ | 运镜，固定机位填 `null` |
| `subject_lock_en` | 建议 | ✅ | **一句**，只为了别换人。不许堆外观形容词 |
| `beats[]` | ✅ | ✅ | 节拍数组，见下方专门一节 |
| `preserve_en` | 建议 | ✅ | **这一段里必须保持不变的东西**（身份/服装/背景/构图）。装配时排在节拍之后、风格尾块之前，前面自动加 `Throughout the shot, `。见下方专门一节 |
| `style_tail_en` | 建议 | ✅ | 风格尾块。装配时**永远排最后** |
| `duration_sec` | ✅ | ✗ | 单元时长。要能被 `8k+1` 帧精确表示 |
| `fps` | ✗ | ✗ | 默认 24。LTX 没有 `--fps` 参数，这个值只用来推 `num_frames` |
| `num_frames` | ✗ | ✗ | 一般省略让脚本算。填了就必须等于 `duration_sec × fps` 吸附出的 `8k+1` |
| `width` / `height` | ✅ | ✗ | 像素，**必须被 64 整除**。预设见 `short-drama-ltx-export/references/resolution_presets.md` |
| `seed` | ✅ | ✗ | **必填，且不能是 10**（10 是 LTX `--seed` 的默认值） |
| `known_limit` | 命中时 | ✗ | 命中"已验证做不到"的项时的降级决定。见下方专门一节 |
| `notes` | ✗ | ✗ | 自由备注，会原样带进 `video_jobs.json` |

`*_en` 字段是**真正发给模型的正文，必须全英文**；`*_zh` 字段是给人和
reviewer 看的，不进提示词。唯一的例外是台词原文 `dialogue.text_zh`——
那是中文，而且必须是中文（见 `video_prompt_guide.md`「语言分工」）。

`--lang zh` 模式下换用 `camera_zh` / `subject_lock_zh` / `style_tail_zh` /
`beats[].motion_zh` / `beats[].framing_zh` / `beats[].sfx_zh` /
`dialogue.delivery_zh` 这一套并行字段。这套只为回归对比旧的全中文提示词
保留，新项目不要用。

---

## `beats[]`：节拍

节拍是这一层最重要的结构。散文式提示词改一处只能整段重写，拆成节拍之后
可以只改其中一拍——`loop-video-generation` 的 `fix_instruction` 也就能精确
写成 `beats[1].motion_en`，而不是"重写那段话"。

```json
{
  "t": [3.4, 6.375],
  "framing_en": "the framing eases back out to the medium close-up, her sword hand and the blade readable again",
  "motion_en": "Her five fingers close back onto the hilt one knuckle at a time until the knuckles stand out, her forearm tenses, and the sunken blade lifts slowly back up until the tip is aimed at the lens again.",
  "dialogue": {
    "speaker": "江砚",
    "text_zh": "我猜到是他。",
    "delivery_en": "he says in Mandarin Chinese, quiet and flat, barely opening his mouth",
    "pace": "slow",
    "onscreen": true
  },
  "sfx_en": "howling wind and driven snow"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `t` | ✅ | `[起, 止]` 秒数。**所有节拍必须首尾相接、从 0 开始、铺满整个 `duration_sec`** |
| `framing_en` | ✗ | 这一拍的景别。同一轴线上的景别变化写在这里 |
| `motion_en` | ✅ | 这一拍发生的物理变化。**必须过可见位移检验** |
| `dialogue` | ✗ | 没有台词就填 `null` |
| `sfx_en` | ✗ | 环境音/音效 |

### `t` 为什么必填、必须连续

三个用途，缺一个都不行：

1. 逐拍核对台词念得完念不完（每一拍的时长必须 ≥ 那句台词的最低时长）。
2. 校验节拍数没有超过时长能承载的上限。
3. **喂 `--retake`**：验收发现问题出在某一拍，`t` 就是
   `ltx_ssh_submit.py --retake <start> <end>` 要的时间窗，不用再回头猜。

### 节拍数上限（跟分级挂钩）

上限 = `min(6, round(duration_sec / 每节拍下限))`，每节拍下限按 `tier` 取：

- **A / B / C 级**：2.5 秒。这些是对话镜/反应镜/空镜，节拍本来就该是"小幅度、
  慢"，动作点挤太密模型会把动作压缩变形。
- **S 级**：0.8 秒。打斗/反转瞬间，起手式 1.1 秒、刺剑 0.7 秒这种短促节拍
  恰恰是它的正确写法。用 2.5 秒卡 S 级会逼人把动作合并成一个笼统的大动作，
  而那正是`model_capability_ledger.md` 里"欠描述 → 姿态焊死在首帧"的成因。

### `motion_en` 的写法：可见位移检验

**每一拍必须至少写出一个会改变位置或形状的身体部位或道具。** 情绪词只能
挂在物理变化上，不能单独成句。

- ✗ `He is angry and holds back.` —— 模型不知道要动什么
- ✓ `His fingers close around the handle one knuckle at a time until the knuckles blanch; his forearm tenses.`

脚本会做这条检验的机器可查部分（查身体部位/道具名词和运动动词的词表），
查不到只报 WARN 让人确认，不硬拦——词表不可能穷尽。道具名词加到
`props_en` 里就能让它认识。

### `motion_en` 里不许出现否定句

`ltx_pipelines.distilled` **没有 `--negative-prompt` 参数**，否定句只会把
不想要的概念直接注入文本编码器。脚本会拦
`no/not/never/without/avoid/…` 和 `避免/禁止/不要/…`，改写方法见
`video_prompt_guide.md`「否定→正向改写表」。

### 一拍之内的渲染顺序是固定的

`framing_en` → `motion_en` → 台词 → `sfx_en`。所以"说完之后才发生的动作"
要么写成和台词同时发生（`as the last word leaves her, her lips press
shut`），要么放到下一拍去，不要指望它排在台词后面。

### `dialogue` 子字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `text_zh` | ✅ | 台词原文，**保持中文**。装配时原样放进引号 |
| `delivery_en` | ✅ | 声音质感/语气，**必须含 `Mandarin Chinese`**（脚本硬拦） |
| `pace` | ✗ | `fast`(5.5字/秒) / `normal`(4.0，默认) / `slow`(3.0)。决定最低时长 |
| `speaker` | ✗ | 说话人名字。只是元数据，**不进提示词** |
| `onscreen` | ✗ | 默认 `true`。画外音/旁白/电话对方声音填 `false` |

`onscreen: false` 时，装配器会自动补一句正向的
`the voice comes from off-screen while the person visible in frame keeps
their lips closed and still`——不用自己写，也不要写成否定句。

装配结果形如：

```
She speaks in Mandarin Chinese, low and forced out between her teeth: "为什么……骗我的是你……为什么？为什么！".
```

---

## `scene_plate` 和 `camera_en.position`：这一镜是从房间的哪个位置拍的

2026-09 新增。以前场景资产每个地点只有一张底板（只按日/夜拆），所以同一场戏里所有
镜头都是同一个摄影机位置，只有景别（裁切松紧）在变——整场戏从一个视角演完。
实拍证据见 `output/出狱后我成为了非洲矿王/videos/ep02/` 的 ep02_镜04.mp4 / ep02_镜07.mp4：
两镜是同一个餐厅的同一个机位，只是拉宽了（原抽帧目录已清理，用 ffmpeg 从 mp4 重抽即可复现）。

现在每个场景有一组机位底板（`A主机位`/`B反打`/`C侧机位`/`D细节`，词表见
`short-drama-storyboard/references/scene_prompt_template.md`），分镜表有「机位」列。

- `scene_plate` 抄分镜表「机位」列，记下这一单元的首帧是在哪张底板上合成的。
  它是**溯源字段**：验收发现"这一镜视角不对"时，先查是不是底板传错了，
  而不是去改提示词——首帧被 strength 1.0 焊死，底板错了改文字没用。
- `camera_en.position` 是这个机位的**英文一句话**，从 `scenes.md` 的「空间关系」块
  翻译过来，进提示词。和 `camera_en.rig` 分工：`position` 说相机**站在哪往哪看**，
  `rig` 说**固定还是手持、机高多少**。

**同一场戏的连续单元，`scene_plate` 应该有变化。** 连续 3-4 个单元都是同一个
`scene_plate`，就是"整场戏一个视角演完"那个毛病又回来了。

---

## `preserve_en`：这一段里什么必须保持不变

2026-09 新增。来源是图生视频提示词的通用五要素——一条合格的 I2V 提示词要回答
五件事：**一个主体动作 / 一个相机指令 / 什么必须保持不变 / 节奏 / 结束状态**。
我们原来只有前两项和第四、五项（节拍里带），**第三项一直是空的**。

**为什么它不能靠首帧代劳**：`--image PATH 0 <strength>` 只锁住**第 0 帧**。
后面 4-8 秒里人会不会换脸、衣服会不会变色、背景会不会漂成另一个房间，
靠的就是这句话。A6「背景冻住」是锁太死的一端，"中途换景"是另一端，
`preserve_en` 是唯一能在两端之间给出正向约束的字段。

写法要求：

- **正向陈述**，不许写否定句（脚本会拦）。写"她的脸、发型和灰色针织裙全程保持
  与首帧一致"，不要写"不要改变她的长相"。
- **逐项点名**，不要写笼统的 "keep everything consistent"。至少覆盖
  **人（脸/发型/服装）** 和 **景（陈设/墙面/光）** 两侧。
- 和 `subject_lock_en` 分工：`subject_lock_en` 是**一句话说清这是谁**
  （防止换人），`preserve_en` 是**说清哪些属性在这几秒里不许变**（防止漂移）。

真实例子（`output/雪山决斗/videos/shot01/shot_cards.json`，2026-09 从
`style_tail_en` 里拆出来的——它本来就混在风格尾块里，拆出来是为了让它
**排在风格尾块之前**，因为风格尾块是"被截掉也不致命"的那一段，
而保持不变的约束不是）：

```json
"preserve_en": "her face, hairstyle and red-and-black costume stay identical to the first frame, and the snowfield behind her keeps the same ridgeline, snow depth and grey-blue light"
```

装配结果：`Throughout the shot, her face, hairstyle and ... grey-blue light.`

---

## `first_frame_strength`：首帧锁多死

`ltx_ssh_submit.py` 用 `--image <path> <frame_idx> <strength>` 传首帧，以前把
strength **硬编码成 `1.0`**（完全锁死）。这是第二个"场景不变"的毛病：单个视频
内部背景**像素级不动**，只有人物的手和脸在变（`ep02_镜04` 的 frame00 和 frame04
背景完全一致）。

`--image` 的强度本来是可调的，**但本仓库从没试过 1.0 以外的值**。

- 默认保持 `1.0`，不改现有行为。
- **官方 I2V 工作流的第一阶段用的是 0.7**（原话："establishing the starting point
  while leaving room for natural motion"），第二阶段才用 1.0 重新注入保细节。
  也就是说全程 1.0 是我们自己的选择，不是官方默认。
- 调低（0.7~0.95）**预期**让画面松动、允许视差和真实运镜，代价是首帧保真度下降
  （人脸/服装漂移）。**这仍是未实测的推测**，扫描方案见
  `model_capability_ledger.md` D4，跑出结果再决定是否改默认值。

**这个字段治不了"场景单一"。** 画面的空间感来自**镜头之间切机位**（`scene_plate`
变化），不是靠一段视频自己摇出新空间——理由见 `video_prompt_guide.md`
「哪些运镜是这张底板撑得起的」。

---

## `first_frame_state_zh`：必填，而且必须真的看过图

首帧是用 `--image <path> 0 1.0` **焊死**的（strength 1.0）。如果节拍 1 描述的
是首帧之前的动作，模型就会在"照首帧"和"照文字"之间摆烂，表现为人物姿态
不动、只有镜头在动——这是本仓库实测过的具体故障
（`model_capability_ledger.md`）。

所以流程上强制一步：**填卡之前先用 Read 工具把首帧图打开看一遍**，把图里
真实的姿态/朝向/光线/道具位置写进这个字段，然后让节拍 1 从这个状态**继续**，
而不是重新摆一次姿势。

真实例子（雪山决斗 shot01）：

> 实际看图确认：16:9 横屏，女子在画面偏右，正面直视镜头。右手单手握剑、
> 手臂朝镜头方向伸出；剑身从画面左下向右上斜插进画，剑尖**已经抬起并指向
> 镜头方向**（不是从身体侧下方待抬的状态）。…… 所以第一拍只能写"维持这个
> 持剑姿态 + 握力加大 + 剑尖细微颤抖"，不能写"慢慢把剑抬起来"——那会和
> 焊死的首帧打架。

拆段单元（`first_frame_from`）填的是**上一段结束时应该是什么状态**，这个从
上一张卡的最后一拍就能推出来，不需要等图。

---

## `script_ref`：给 reviewer 的验收依据

**不能填分镜表"画面描述"列的原文。** 那段文字是提示词的输入，拿它当验收
标准等于自己出题自己判卷——任何"字面关键词都对上了"的结果都会被判通过，
哪怕实际情节/情绪完全没讲对（详见
`loop-video-generation/references/reviewer_agent.md`）。

要填的是三样：**剧本原文摘录 + 角色小传 + 这一段的判断标准**。中文，写给
人看。分镜表新增的「剧本原文锚点」列就是为了让这一步有源可抄。

---

## `known_limit`：撞已知的墙之前先做降级决定

`model_capability_ledger.md` 里标为**已验证做不到**的项（比如"混合/克制型
情绪会被收敛成通用笑容，加强负面提示词无效，实测 3 轮 ×2 镜"），命中了就
必须在卡上写清楚打算怎么办，脚本会检查 `decision` 非空：

```json
"known_limit": {
  "item": "混合/克制型情绪会被收敛成通用表情",
  "evidence": "出狱后 ep01 镜14/镜18，各 3 轮加强负面无效",
  "decision": "本段刻意设计成无台词（已确认触发条件是『带台词的镜头』），情绪全部挂在可见的物理变化上；3 轮拿不到就按 ledger 第 2 条降级，只保留剑尖下沉→抬回这一条动作线"
}
```

这条的目的是不让 `loop-video-generation` 空烧 3 轮 GPU 去撞一面已知的墙。

---

## 完整可跑的例子

`output/雪山决斗/videos/shot01/shot_cards.json` —— 3 个单元（5.71s / 6.375s /
5.71s），从手写的 `prompt_v1.txt` 逆向重建，lint 全绿。

同目录 `shot_cards_v1_replica.json` 是手写版的**原样**还原，**故意不修正**，
用来验证校验有效：

```bash
python3 .claude/skills/short-drama-video-gen/scripts/build_prompt.py \
  output/雪山决斗/videos/shot01/shot_cards_v1_replica.json --lint --lang zh
```

应当报出 3 条 ERROR：机位描述里的否定句（`禁止`/`没有`）、第 4 拍台词只给
1.2 秒但按 slow 语速至少需要 3.8 秒、提示词估算 922 token 超预算。这三条
都是手写版里真实存在的缺陷。
