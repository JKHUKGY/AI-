# 视频提示词装配指南（LTX-2.5 自建通道）

**这一层的第一条规则：提示词不手写。**

人维护镜头卡（`shot_cards.json`，字段定义见 `shot_card_schema.md`），提示词
由 `scripts/build_prompt.py` 按固定模板机械装配。同一张卡永远装配出同一段
字符串；要改提示词，只能改卡上的某个字段再重跑脚本。

为什么要这样：这套流程以前是"看着分镜表当场写一段散文"，结果同一份指南在
不同时候写出的东西完全不是一个文体——历史产出的 41 条提示词长度从 90 字到
345 字，而手写的 `output/雪山决斗/videos/shot01/prompt_v1.txt` 是 1800 字的
时间轴结构。既不可复现，也没法只改一处。

```
storyboard/ep0X.md   ← 叙事决策：切几镜、景别、运镜、台词、分级、剧本原文锚点
   ↓  （本指南）
videos/ep0X/shot_cards.json     ← 结构化，逐字段可校验、可局部改
   ↓  build_prompt.py
videos/ep0X/video_jobs.json     ← prompt 字段是派生产物
```

---

## 装配顺序（固定，而且是 token 截尾的保险）

```
[camera_en.rig] . [camera_en.framing_path] . [camera_en.move] . [subject_lock_en] .

[beat 1: framing_en ; motion_en . 台词 . sfx_en]

[beat 2: …]

[style_tail_en]
```

**风格尾块永远排最后。** Gemma 文本编码器超过 1024 token 会**静默截尾**
（`model_capability_ledger.md` B2），排最后意味着万一真被截掉，丢的是风格
描述而不是高潮动作。

---

## 六条规则

### 规则 1：关键帧已经锁定外观，提示词只说"接下来发生什么"

首帧图已经定死了人物长相、服装、场景。堆外观形容词只会稀释动作指令的权重，
甚至让模型误以为要重新设计人物（Runway 官方图生视频指南：*"Effective image
to video prompts focus almost exclusively on motion"*）。

所以镜头卡在结构上就限死了：人物一致性只能靠 `subject_lock_en` **一句话**
（`the same young woman throughout, same face, same long black hair, same red
scarf over black robes`），没有第二个字段可以堆外观。

### 规则 2：可见位移检验

**每一拍的 `motion_en` 必须至少写出一个会改变位置或形状的身体部位或道具。**
情绪词只能挂在物理变化上，不能单独成句。

- ✗ `He is angry and holds back.`
- ✓ `His fingers close around the handle one knuckle at a time until the knuckles blanch; his forearm tenses; his shoulders draw a fraction tighter.`
- ✗ `她哭了`
- ✓ `Her eye rims redden, her lashes tremble, then a single tear slides down her cheek, one corner of her mouth pulls down, and her shoulder gives one small shake.`

这不是文风偏好，是实测：首帧被 `strength 1.0` 焊死，动作描述笼统时模型只会
移动镜头、人物姿态原地不动（《出狱后》ep01 镜1，"走出监狱大门"写成"镜头缓慢
推进"，抽 5 帧确认完全没有迈步；拆解成"双脚交替迈步 → 身体持续向镜头方向
平移 → 从阴影走到阳光下"才动起来，跨 seed 复现）。详见
`model_capability_ledger.md` A3。

**这条推翻了本指南的旧版本。** 旧版写"2-3 秒的短片段只写 1 个过程关键点"，
那正是这类欠描述的来源，已删除。节拍数的上限现在由时长和分级决定（规则 5），
但**每一拍内部要写多细，没有上限**——写细是对的。

脚本会做这条检验的机器可查部分（查身体部位/道具名词和运动动词词表），查不到
报 WARN 让人确认。道具名词加到卡的 `props_en` 里就能让它认识。

### 规则 3：否定 → 正向改写

`ltx_pipelines.distilled` **没有 `--negative-prompt` 参数，它根本不存在**
（`--help` 实测确认）。所以否定句只有两个去处：改写成正向陈述，或者删掉。
写进正向提示词等于把不想要的概念直接注入文本编码器。

| 想排除的 | ✗ 直接写否定 | ✓ 正向改写 |
|---|---|---|
| 侧面/斜拍/俯仰/绕行/越轴 | `禁止侧面、斜拍、俯拍、绕行、越轴` | `locked-off camera at eye level, facing her straight on; the axis stays fixed for the whole take` |
| 镜头乱动/抖动 | `避免镜头剧烈抖动` | `locked-off camera, the frame holds absolutely still` |
| 中途换脸 | `避免人物中途换脸` | `subject_lock_en`: `the same young woman throughout, same face, same long black hair` |
| 五官变形/模糊 | `避免面部变形、五官错位` | 无正向写法 → **删掉**（这是画质问题，靠分辨率档位和首帧质量解决，不是靠提示词） |
| 手指数量错误 | `避免手指数量错误` | 要么用 `framing_en` 把手排出画，要么把手的动作写清楚到每根指头 |
| 大笑/露齿笑 | `不要露齿笑` | 已验证无效（ledger A1）→ 走 `known_limit` 降级，不要硬扛 |
| 字幕/水印/屏幕文字 | `避免字幕、水印、屏幕文字` | 无正向写法 → **删掉**。写了只会把"字幕"这个概念注入编码器 |
| 画外音带偏嘴型 | `避免角色出现说话嘴型` | 卡上填 `dialogue.onscreen: false`，装配器自动补 `the voice comes from off-screen while the person visible in frame keeps their lips closed and still` |
| 多人穿模 | `避免人物之间重叠穿模` | 把两人的位置关系写成正向事实：`they stand three paces apart with clear space between them` |

`build_prompt.py` 会拦所有 `*_en` / `*_zh` 字段里的
`no / not / never / none / nothing / without / avoid / nor / neither /
cannot / forbidden / prohibited / …` 和
`避免 / 禁止 / 不要 / 不得 / 不能 / 不许 / 没有 / 无任何 / 切勿`。

`video_jobs.json` 的 `negative_prompt` 字段由脚本写成固定的存档说明，
**不再逐镜手写**——历史上 41/41 条 job 都写了它，其中一条还为它跑了 3 轮
GPU（ledger B1）。

### 规则 4：语言分工——英文正文 + 中文台词

- `*_en` 字段全英文，是真正发给模型的正文（LTX 官方示例全英文，文本编码器
  是 Gemma-4-12B）。
- **引号内台词保持中文原文。**
- `dialogue.delivery_en` **必须显式含 `Mandarin Chinese`**。不声明语言时实测
  出现过角色说英文或语种混杂，即使引号里本身就是中文（ledger B4）。
- 校验：**装配出的提示词里，CJK 字符只允许出现在台词引号内**。这条 lint 把
  语言分工变成机器可查的事实——`*_en` 字段被填了中文会直接报错。

装配结果形如：

> She speaks in Mandarin Chinese, low and forced out between her teeth, breaking off with a heavy breath before the volume climbs into a demand: "为什么……骗我的是你……为什么？为什么！".

⚠️ **英文正文 + 中文台词这个组合本仓库还没有实测数据**（现有 12 个中文台词
成功样本全部是全中文提示词）。批量套用之前先按 ledger D1 的方案跑一次 A/B。
`--lang zh` 保留了全中文的旧行为，用卡上的 `*_zh` 并行字段。

### 规则 5：节拍与时长预算

**默认把一段戏拆成 4-8 秒的生成单元**（前段尾帧作后段首帧，卡上用
`first_frame_from` 声明），需要时可以做 10 秒以上的长单镜——361 帧 / 15 秒
@1600×896 实测无画质衰减（ledger C2），不需要额外标记。拆段的好处是返工便宜
（只重跑出问题那一段）和定位精确。

**节拍数上限** = `min(6, round(duration_sec / 每节拍下限))`：

| 分级 | 每节拍下限 | 理由 |
|---|---|---|
| A / B / C | 2.5 秒 | 对话镜/反应镜/空镜，节拍本来就该是"小幅度、慢"，挤太密动作会压缩变形 |
| S | 0.8 秒 | 打斗/反转瞬间，起手式 1.1 秒、刺剑 0.7 秒正是它的正确写法 |

**台词时长公式**（这条是实测出来的，保留）：

```
这一拍的最低时长(秒) = 台词CJK字数 / 语速(字/秒) + 0.8
```

语速按 `dialogue.pace` 三档取，不要一律用同一个数字：

- `normal` — **4.0 字/秒**：正常陈述/交代信息。
- `fast` — **5.5 字/秒**：急促/激动/吵架/催促。
- `slow` — **3.0 字/秒**：哽咽/压抑/停顿/若有所思。**这类最容易被低估**，
  "字不多但每个字之间有停顿"，按正常语速套会明显偏短。

时长不够时 LTX-2.5 会自己把台词总结/压缩（漏词漏句），**改措辞无效**
（ledger A2）。脚本逐拍硬拦这条——它正好抓出了手写版雪山决斗里
"今天……我们……只能活一个。"（9 字 slow，最低需 3.8 秒）只给 1.2 秒的缺陷。

`num_frames` 由 `duration_sec × 24fps` 吸附到最近的 `8k+1`
（73≈3.04s / 97≈4.04s / 121≈5.04s / 137≈5.71s / 145≈6.04s / 153≈6.375s /
169≈7.04s / 193≈8.04s）。`duration_sec` 直接写成合法值可以免掉一条 WARN。

**这条推翻了本指南的旧版本。** 旧版写"提示词里不需要写具体秒数"，但
`build_prompt.py` 对 >6 秒的单元用绝对时间前缀（`0-3.4s:`）——依据是雪山决斗
那次实跑。注意这**只有一个 datapoint**，官方文档没记载这个格式，6 秒这个分界
线是拍脑袋定的（ledger D3）。

### 规则 6：Token 预算

硬上限 1024，**工作预算 850**，超了脚本报错。超限不会报错、**会静默截尾**，
丢掉的正是排在最后的内容（ledger B2）。

估算公式 `0.9 × CJK字数 + 0.3 × 非CJK字符数`。中文侧用雪山决斗那条反标定过
（估 881 vs 实测 874）；**英文侧偏保守约 25%**，想要准确值用
`--tokenizer <path>` 走真实 Gemma 分词。

拆成 4-8 秒单元之后这个上限基本不是瓶颈（雪山决斗重建后单段估算
476/560/710 token），但长单镜会重新逼近它。

---

## 场景的变化来自切机位，不是来自单镜内摇镜头

这一节是 2026-09 为了修"生成的视频大多只保持一个不变的场景"加的。那个问题有两层，
**两层的解法完全不同**：

### 第一层：整场戏一个视角演完 → 靠切机位解决

以前每个地点只有一张场景底板（只按日/夜拆），所以同一场戏所有镜头都是同一个摄影机
位置，只有景别（裁切松紧）在变。实拍证据：
`output/出狱后我成为了非洲矿王/videos/ep02/_frames_check/` 里镜04 和镜07 是同一个
餐厅的同一个机位，只是拉宽了——同一盏吊灯在正中、同一个厨房门洞在右、同一个台灯在左。

现在每个场景有一组机位底板（`A主机位`/`B反打`/`C侧机位`/`D细节`），分镜表有「机位」列，
镜头卡有 `scene_plate` 和 `camera_en.position`。**这一层的活儿在分镜和关键帧阶段就
做完了**，到提示词这一层要做的只有两件：

1. `camera_en.position` 如实写这张底板是从哪拍的（从 `scenes.md` 的「空间关系」块翻译）。
2. **回头看一眼连续几个单元的 `scene_plate` 有没有变化。** 连续 3-4 个单元都是同一张
   底板，就是老毛病又回来了——那是分镜阶段的问题，回去提醒用户补机位，不要在提示词
   里写"镜头换个角度"来假装解决（首帧焊死，写了也不会变）。

### 第二层：单镜内背景像素级冻住 → 只能改善，不能承诺解决

`ep02_镜04` 的 frame00 和 frame04 背景完全一致，只有人物的手和表情在变。成因是
`--image <path> 0 1.0` 把首帧焊死 + distilled 只有 8 步。可用的杠杆见
`model_capability_ledger.md` A6/D4/D5，其中 `first_frame_strength` < 1.0 和
`keyframe_interpolation` **都还没实测**，别当成已知解法写进文档或承诺给用户。

### 哪些运镜是这张底板撑得起的

**这条是物理限制，不是风格建议：**

| 运镜 | 撑不撑得起 | 为什么 |
|---|---|---|
| 推 / 拉（zoom in/out） | ✅ 单张底板撑得起 | 本质是缩放，需要的像素都在画面里 |
| 轻微视差 / 呼吸感 | ⚠️ 取决于 `first_frame_strength` | 1.0 完全焊死时基本没有 |
| 摇 / 移（pan / track） | ❌ 一般撑不起 | 本质是平移，**需要画外的像素**。底板右边没有东西，"镜头向右摇露出门口"就是注定失败的一镜——模型不会现编，它会保持不动 |
| 换机位 | ❌ 单镜内做不到 | 这是**切**出来的，不是摇出来的 |

所以 `camera_en.move` 写摇/移之前，先问一句：这张底板的那个方向上真的有像素吗？
没有就改成推/拉，或者干脆拆成两镜切机位。分镜表如果写了撑不起的运镜，
回去提醒用户改分镜，不要在这一层硬写。

---

## 填卡之前的两道必做检查

### 第一道：跨镜头连贯性核对（不要只盯着这一镜）

这是实际返工率最高的问题来源：只孤立地看当前这一镜的关键帧，不回头核对
上一镜的结束状态、不确认下一镜的起始需求，结果同一场戏里前后两镜的姿态/
位置/情绪接不上——模型没有任何线索知道这是"错的"，会老老实实生成一个和
上一镜断裂的动作。

填每张卡之前先做三件事：

1. **回头看上一镜的结束状态**（`ep0X.md` 同场景段上一镜的"运动描述"结尾，
   B/C 级看"画面描述"结尾），确认这张卡的节拍 1 是同一个逻辑动作的延续。
   如果分镜表本身就没接上，**停下来提醒用户回头补分镜**，不要在提示词里
   "悄悄圆过去"掩盖分镜设计的断裂。
2. **看一眼下一镜的起始需求**，确认这张卡最后一拍的结束状态衔接得上。
3. **确认场景/光影/时间连续**：同一场景段内连续镜头，除非分镜表标了转场，
   光照方向、天气、时段应保持一致，别随手加一句和上一镜矛盾的光影描述。

多人物同框的额外核对：每个人物的位置/朝向是否和上一镜连续（除非明确是
正反打切换机位，而不是人物真的挪了位置）。

拆段单元之间同理，而且更严格——`first_frame_from` 那一段的
`first_frame_state_zh` 必须就是上一张卡最后一拍的结束状态。

### 第二道：过一遍能力清单

`model_capability_ledger.md` 里标为**已验证做不到**的项，命中了就必须在卡的
`known_limit.decision` 里写清楚打算怎么办（接受 / 降级成无台词表情镜 /
换 pipeline）。目的是不让 `loop-video-generation` 空烧 3 轮 GPU 去撞一面
已知的墙。

最常撞的一面墙是 A1：带台词的镜头，目标情绪是混合/克制型（苦笑带泪、
阴阳怪气冷笑）时会被收敛成通用开怀笑，正向反向都试过 3 轮无效。

---

## 运镜词汇对照（分镜表 → `camera_en`）

| 分镜表运镜 | `camera_en.move` 写法 |
|---|---|
| 推 | `the camera pushes in slowly, settling on her face` |
| 拉 | `the camera pulls back slowly, opening up the surroundings` |
| 摇（左/右/上/下） | `the camera pans slowly to the right, following her eyeline` |
| 移 | `the camera tracks sideways with her, matching her walking direction` |
| 跟 | `the camera follows her run with a slight handheld sway` |
| 固定 | `move: null`，`rig` 里写 `locked-off camera, the frame holds absolutely still` |

⚠️ **写「摇」和「移」之前先读上面「哪些运镜是这张底板撑得起的」。** 平移需要画外的
像素，单张场景底板一般没有——这两个运镜在本通道上大多是无效指令。

节奏副词按分级选：S 级用 `abruptly / hard / fast`，A 级用
`slowly / slightly / naturally`。

同一轴线上的**景别变化**（雪山决斗那种"正面近景↔面部特写、不换机位"）写在
`camera_en.framing_path`（整段走向）和 `beats[].framing_en`（这一拍看到多大
范围）里，不要写成运镜。

---

## 完整例子

```bash
# 校验 + 预览装配结果（不写文件）
python3 .claude/skills/short-drama-video-gen/scripts/build_prompt.py \
  output/雪山决斗/videos/shot01/shot_cards.json --lint

# 装配并写出 video_jobs.json
python3 .claude/skills/short-drama-video-gen/scripts/build_prompt.py \
  output/雪山决斗/videos/shot01/shot_cards.json \
  -o output/雪山决斗/videos/shot01/video_jobs_v2.json \
  --emit-prompts output/雪山决斗/videos/shot01/prompts_v2
```

- **卡**：`output/雪山决斗/videos/shot01/shot_cards.json`（3 个单元，
  5.71s / 6.375s / 5.71s，lint 全绿）
- **装配出的提示词**：`output/雪山决斗/videos/shot01/prompts_v2/*.txt`
- **反例**：`shot_cards_v1_replica.json` 是手写版的原样还原，**故意不修正**。
  跑 `--lint --lang zh` 会报出 3 条 ERROR（机位里的否定句、第 4 拍台词只给
  1.2 秒、估算 922 token 超预算）——这三条都是手写版里真实存在的缺陷，
  用来验证校验有效。

装配出的单段提示词长这样（u1）：

> locked-off camera at eye level, on the male lead's first-person axis, facing her straight on; the axis stays fixed for the whole take and she keeps looking straight into the lens. one medium close-up held for the whole take. the same young woman throughout, same face, same long black hair, same red scarf over black robes.
>
> Medium close-up on her upper body, her sword hand, and the blade angled up toward the lens; she keeps the sword where it already is, tip aimed at the lens, and her grip closes harder on the hilt until the blade tip picks up a fine, real tremor. Her brow draws in a fraction at a time, her eyelids lower, her jaw sets, her back teeth clamp, and her nostrils flare with shallow, held-in breaths. Driven snow streams in from screen left through her long hair, the loose strands at her forehead, her red scarf and her hem; snow grains settle on the ends of her hair and on her lashes, and her breath leaves a faint white plume. She speaks in Mandarin Chinese, low and forced out between her teeth, breaking off with a heavy breath before the volume climbs into a demand: "为什么……骗我的是你……为什么？为什么！". Howling wind and driven snow, her breathing.
>
> cinematic ultra-realistic wuxia, top-tier theatrical image quality, true skin texture with the natural flush of cold, cold grey-blue snowfield ambient light, real hair and cloth physics, snowfall with clear direction and volume, high dynamic range; her face, hairstyle and red-and-black costume stay identical to the first frame all the way through.

---

## 相关文件

- `shot_card_schema.md` —— 镜头卡字段定义
- `model_capability_ledger.md` —— 模型能做/做不到清单，每条带证据
- `video_jobs_schema.md` —— 下游 `video_jobs.json` 的结构
- `stability_playbook.md` —— 首帧质量、动作幅度、分段、测试档→正式档、3 轮上限
- `video_review_checklist.md` —— 验收怎么查
- `short-drama-ltx-export/references/resolution_presets.md` —— 分辨率档位
- `short-drama-ltx-generate/references/ltx_pipeline_gotchas.md` —— pipeline 参数细节
