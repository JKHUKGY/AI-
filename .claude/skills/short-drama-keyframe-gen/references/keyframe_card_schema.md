# 关键帧卡 keyframe_cards.json 结构定义

关键帧卡是**分镜表和出图提示词之间的中间层**，和 `short-drama-video-gen` 的
`shot_cards.json` 是同一套思路：**提示词不手写**，人只维护卡上的字段，
提示词由 `scripts/build_keyframe_prompt.py` 按固定模板机械装配——同一张卡
永远装配出同一段字符串。要改提示词，只能改卡上的字段再重跑脚本。

落盘位置：`output/<故事名>/keyframes/ep0X/keyframe_cards.json`（顶层是数组）。

**一张卡 = 分镜表里的一镜。** 一集 27 镜就是 27 张卡。

它存在的理由是这一步真实失败过的三种方式（证据见 `blocking_guide.md`）：

1. 朝向靠散文暗示 → 模型默认给正脸，多人镜变成"全员面对镜头的合影"。
2. 纵深不写 → 几个人并排站在同一条线上，像列队。
3. 景别写成一句尾巴 `【景别】中景`，同时又要求"保持场景与底板完全一致" →
   两条指令打架，画面退回底板那个大全景。

这三样在卡上都是**必填的枚举或必填的裁切说明**，脚本会硬拦。

---

## 字段总表

| 字段 | 必填 | 进提示词 | 说明 |
|---|---|---|---|
| `id` | ✅ | ✗ | `ep{集号:02d}_镜{镜号:02d}`，如 `ep03_镜03`。作为输出子目录名 |
| `shot_no` | ✅ | ✗ | 分镜表镜号（整数） |
| `scene` | ✅ | ✗ | 场景编号，抄分镜表「场景编号」列 |
| `tier` | 建议 | ✗ | `S`/`A`/`B`/`C`，抄分镜表「分级」列 |
| `plate_id` | ✅ | ✗ | 机位底板 id，如 `SC03_顾家别墅客厅_B反打`。抄分镜表「机位」列 |
| `plate_image` | ✅ | ✗ | 该底板选中图的路径。查 `selected.md`，查不到就**报缺**，不要顶替 |
| `plate_read_zh` | ✅ | ✗ | **看过底板图之后**如实写这张底板里左/中/右/纵深各是什么、地面占多少。见下 |
| `script_ref_zh` | ✅ | ✗ | 抄分镜表「剧本原文锚点」列。给人和 Reviewer 验收用，**不进提示词** |
| `beat_zh` | ✅ | ✗ | 抄分镜表「画面描述」列原文。只是给人在审阅表里对照，**不进提示词** |
| `style_anchor_zh` | ✅ | ✅ | 画风锚点，从 `style_bible.md`/`characters.md` 开头**原句抄**，全集一致 |
| `camera_zh` | ✅ | ✅ | 相机站在房间哪个位置往哪看 + 机高。从 `scenes.md`「空间关系」块翻过来 |
| `framing.shot_size` | ✅ | ✅ | 景别，抄分镜表「景别」列（`特写`/`近景`/`中近景`/`中景`/`全景`…） |
| `framing.subject_frac` | ✅ | ✅ | 主体在画幅**高度**上占的比例（0–1）。脚本按景别查区间 |
| `framing.crop_zh` | ✅ | ✅ | 画面上下边**切在人身上哪里**、地面/天花各留多少。见下 |
| `framing.plate_crop_zh` | 非全景时✅ | ✅ | 这一镜取底板的哪一块、放大多少、底板里哪些东西这一镜看不到了。见下 |
| `light_zh` | 建议 | ✅ | 光从哪来、打在谁身上。抄分镜表画面描述里的光线句 |
| `people[]` | ✅（空镜填 `[]`） | ✅ | 逐人走位，见下方专门一节 |
| `props_zh` | ✗ | ✅ | 道具及其位置的中文短句数组。`people` 为空的道具镜必填 |
| `relation_zh` | 多人时建议 | ✅ | 一句话讲这一镜的人物关系落差（"她凑近问、他懒得答"） |
| `avoid_extra_zh` | ✗ | ✅ | 追加进"避免"尾块的本镜专属条目。**不许写朝向/景别**，见下 |
| `count` | ✗ | ✗ | 这一镜这一轮出几张，默认 3 |
| `notes` | ✗ | ✗ | 自由备注，原样带进 `jobs.json` 的同名字段 |

---

## `people[]`：逐人走位（这一层是本 skill 的核心）

```json
{
  "name": "顾万通",
  "ref_images": ["output/.../顾万通_得势期_背面转身_00.png"],
  "ref_note_zh": "背面转身基准图",
  "pos_x": "right",
  "depth": "near",
  "body_dir": "screen_left",
  "camera_relation": "three_quarter_back",
  "gaze_at": "off_down",
  "posture_zh": "刚甩完包站定，重心压在右腿，胸口一起一伏",
  "action_zh": "左手把已经松开的领带整条攥进手心，脸只略微转向刘兰的方向",
  "contact_zh": null
}
```

| 字段 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `name` | ✅ | | 角色名，和 `characters.md` 一致 |
| `ref_images` | ✅ | | 该角色基准图路径数组（1–2 张）。查不到对应造型/视图就**报缺** |
| `ref_note_zh` | 建议 | | 这几张参考图是什么视图，会写进"参考图N 是…"那句 |
| `pos_x` | ✅ | `far_left`/`left`/`center`/`right`/`far_right` | 在画幅横向的位置 |
| `depth` | ✅ | `near`/`mid`/`far` | 纵深层。**多人镜必须至少有两个不同的层** |
| `body_dir` | ✅ | `screen_left`/`screen_right`/`to_camera`/`away` | 身体朝画面哪边/朝镜头/朝纵深里 |
| `camera_relation` | ✅ | `front`/`three_quarter_front`/`profile`/`three_quarter_back`/`back` | **相对镜头**露多少脸。词表和规则见 `blocking_guide.md` |
| `gaze_at` | ✅ | 另一个人物名 / `lens` / `off_left` / `off_right` / `off_up` / `off_down` / `prop:<名>` | 视线落点 |
| `posture_zh` | ✅ | | 身体姿态、重心、坐/站/蹲/半躺 |
| `action_zh` | ✅ | | 这一**瞬间**在做什么（手在哪、脸上什么表情）。写瞬间，不写过程 |
| `contact_zh` | ✗ | | 和别人/家具的接触点（"右手撑在沙发扶手上"）。没有就 `null` |

### `body_dir` 和 `camera_relation` 必须自洽

脚本硬拦不自洽的组合：

- `body_dir: to_camera` → `camera_relation` 只能是 `front` / `three_quarter_front`
- `body_dir: away` → 只能是 `back` / `three_quarter_back`
- `body_dir: screen_left` / `screen_right` → 只能是 `profile` /
  `three_quarter_front` / `three_quarter_back`

### `gaze_at` 指向另一个人时，朝向要跟着对

如果视线目标在自己的画面右边，`body_dir` 就必须是 `screen_right`
（`to_camera`/`away` 只给 WARN，因为偶尔"看着他却不转身"是刻意的）；
目标在左边同理。两人 `pos_x` 相同时脚本没法核对，会报 WARN 让人自己看。

---

## `plate_read_zh`：必填，而且必须真的打开底板图看过

和 `shot_cards.json` 的 `first_frame_state_zh` 是同一条纪律。理由一样：
底板被"保持场景与参考图完全一致"这句**锁死**，所以人往哪站、能站多近、
画面能裁到哪，全部由底板已经拍成什么样决定，不由想象决定。

填法（真实例子，`SC03_顾家别墅客厅_C侧机位`）：

> 实际看图确认：竖屏，画面左侧是黑色转角沙发与深灰大理石电视墙，
> 右侧至纵深端是落地玻璃幕墙和窗外泳池，中央上方悬水晶流苏吊灯。
> **画面下半部约 40% 是空的米白抛光大理石地面**——人如果按底板原样比例
> 站在沙发区，就只能占到画幅一半高，这一镜要的中景必须靠裁掉下方地面实现。

最后那一句就是 `framing.plate_crop_zh` 的依据。没看过图的人写不出这句。

---

## `framing`：景别怎么写才不漂

三个字段互相咬合，缺一个就会漂回底板的大全景：

- `shot_size` 是**说法**（分镜语言），单独存在没有约束力。
- `subject_frac` 是**数**。主体（多人镜取最靠前那个人）从头顶到画面底边
  占画幅高度的比例。脚本按景别查区间：

  | 景别 | `subject_frac` 合理区间 |
  |---|---|
  | 特写 | 0.75 – 1.0 |
  | 近景 | 0.50 – 0.80 |
  | 中近景 | 0.45 – 0.70 |
  | 中景 | 0.30 – 0.60 |
  | 全景 / 远景 / 定场 | 0.10 – 0.45 |

- `crop_zh` 是**裁切线**：上下边切在人身上哪里、地面留几分。
  `中景` 只写"中景"模型不知道切哪；写成"底边切在两人大腿中段，
  顶边留头顶上方约半头，地面只占画面下缘约 1/8"它才有依据。
- `plate_crop_zh` 是**和底板锁定句的和解**。非全景镜必填，明写这一镜取底板
  的哪一块、放大多少、底板里哪些东西因此看不到了（"取底板画面中段并向前
  推近，纵深端玄关只保留上半部，下方空地面全部裁掉"）。不写这句，
  "保持场景与参考图完全一致"就会被理解成"连取景范围也一致"。

---

## `avoid_extra_zh`：可以有，但不许拿它写走位

Codex CLI 的 `image_gen` 没有独立的 negative prompt 参数，"避免"只能写进
prompt 尾块——这一点沿用 `short-drama-image-gen/references/jobs_schema.md`。
装配器会自动补一条固定的通用尾块（多余肢体/手指数量/五官崩坏/水印文字/
与参考图不符/多余人物），`avoid_extra_zh` 只加本镜专属的。

按 OpenAI 官方口径，"避免"里的内容要分两种看：

- **保留型否定 —— 官方推荐，该写，而且每一镜都重复**：`no watermark`、
  "画面内文字字幕"、"多余人物"、"与参考图不符"。它保护的是**已经存在的东西
  不要被改动**，我们的固定尾块全是这一类。
- **设计型否定 —— 实测无效，脚本报 ERROR**：用"不要 X"去定义"要什么"。

**所以朝向、景别、姿态一律不许写在这里。** 历史上
`ep03_镜03` 的尾块写了 `顾万通正面朝镜头`、`刘兰站姿直立不前倾`，
`ep03_镜10` 写了 `苏慧低头含胸`、`位置左右互换`——这些全都没拦住，
因为否定句只是把"正面朝镜头"这个概念又注入了一遍。这些意图现在有
`camera_relation` / `body_dir` / `framing.*` 这些正向枚举承载。

---

## 完整可跑的例子

`.claude/skills/short-drama-keyframe-gen/examples/ep03_keyframe_cards.json`
——从《出狱后》ep03 已经跑过的 `jobs_ep03.json` 逆向重建的 3 张卡
（镜02 道具特写 / 镜03 双人反打 / 镜10 三人侧机位），**无 ERROR，3 条 WARN**
（画风锚点里的"高细节"是质量咒）。那 3 条 WARN **故意不修**：《出狱后》
ep01-03 已经按这句锚点出过一批图，**在制项目中途改画风锚点会让新旧镜头画风
对不上**，一致性优先——这个改动留到下一部戏。新项目按
`short-drama-image-gen/references/jobs_schema.md`「关于质量咒」那节写锚点：

```bash
python3 .claude/skills/short-drama-keyframe-gen/scripts/build_keyframe_prompt.py \
  .claude/skills/short-drama-keyframe-gen/examples/ep03_keyframe_cards.json --lint
```

同目录 `ep03_keyframe_cards_v1_replica.json` 是**照原样**还原当时那批手写
提示词的走位（三人并排同一纵深、两人正脸、中景却给 0.42 的
`subject_frac`、否定句写朝向），**故意不修正**，用来验证校验有效——应当
报出多条 ERROR。
