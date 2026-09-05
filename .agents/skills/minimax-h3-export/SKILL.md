---
name: minimax-h3-export
description: 面向 MiniMax-H3（自建，SGLang 部署）图生视频通道的提交前关卡。上游 short-drama-video-gen 维护的镜头卡
  shot_cards.json 是模型无关的，本 skill 用 build_h3_prompt.py 把它装配成 H3 要的 **ref2va 六段结构化提示词**（subject_definitions
  / summary / retention_analysis / detailed_description / overall_soundscape / non_diegetic_music）和
  h3_jobs.json——**装配即校验**，装不出合规提示词就报 ERROR 不写文件。校验的每一条都对着 H3 官方硬规则：4-15 秒时长窗口（判的是
  num_frames 吸附到 17n+5 之后的时长，不是原始值）、20 个官方受控运镜词表 + 幅度 + 速度、台词必须包成 〈d〉[Language] 原文〈/d〉
  且标签内只放语言和原文、旁白固定短语 says in an off-screen voiceover 加闭嘴声明、说话人 ID 按发声顺序分配、retention_analysis
  段里不许出现 (Sx)、参考素材数量上限（图≤9/视频≤3/音频≤3/总数≤12）、宽高 32 的倍数、画幅吸附到官方比例、正文否定句（H3 是 guidance
  蒸馏、没有负面通道）。同时把关键帧映射成 〈Picture 1〉、角色三视图映射成 〈Subject N〉，核对文件真实存在，检查/生成 h3_remote_config.json，最后跑一次
  h3_submit.py --dry-run 看真实 HTTP 请求体。当用户说"用 H3 跑这一集""这批换成 MiniMax H3""校验 h3_jobs.json""把镜头卡装配成
  H3 的提示词""H3 的提示词怎么写"时使用。跑 LTX-2.5 用 short-drama-ltx-export，不要用这个。
---

## Codex 运行适配（迁移新增，以下原始正文保持不变）

- 在本项目根目录运行；此 skill 的 Codex 入口为 `.agents/skills/minimax-h3-export/SKILL.md`，用 `$minimax-h3-export` 调用。
- 原文中的 Read：文本用文件读取工具，图片用图片查看工具；Bash 用 shell，Write/Edit 用文件编辑工具，Glob/Grep 用文件搜索工具；WebFetch/WebSearch 用可用的网页检索工具。
- 原文提到其他 skill 时，读取同级 `../<skill-name>/SKILL.md`。Task/subagent/Generator/Reviewer 对应 Codex 的独立子代理能力；保留原来的职责隔离、轮次和预算，实际并发受宿主上限限制。能力缺失时报告限制，不声称已经执行。
- 原文相对于 skill 的 references/、scripts/ 路径仍相对于本目录。原文命令里的 `.claude/skills/` 脚本及文档路径在 Codex 执行时映射到 `.agents/skills/`；项目素材、输出和私有配置文件的路径保持原意。脚本内部实现及默认配置保持原样，源目录与目标目录共存。
- 原文的确认节点、输入要求和业务规则保持不变。本文只适配执行宿主，不自动执行生成、租卡或 API 调用。

<!-- ORIGINAL-BODY-START -->

# MiniMax-H3 提交文件打包助手 (minimax-h3-export)

承接 `short-drama-video-gen` 之后、`minimax-h3-generate` 之前的**提交前最后一道关卡**。

**跟 `short-drama-ltx-export` 是并列关系，不是替代关系**：同一份镜头卡
（`shot_cards.json`）可以装配给两个模型，走哪条看这一批用哪个模型。
LTX-2.5 走那边，H3 走这边。

> **本仓库一次都没有真的跑过 H3。** 这个 skill 里的每一条规则都来自官方文档
> （`MiniMaxAI/MiniMax-H3` 的 README / `docs/` / `scripts/readme/`、SGLang
> cookbook、diffusers pipeline 文档），**不是实测结论**。第一次实跑时遇到跟
> 文档不符的地方，回来把这份文档改掉，别让它继续误导下一次。

---

## 0. 先确认这次针对哪一集/哪几镜

不要一次性把全剧都打包，按用户指定的集数（`epNN`）处理；说"这几镜"就只处理
指定镜号，其余保留在已有的 `h3_jobs.json` 里（增量更新，不要覆盖掉别的镜头
已经校验过的记录）。

## 1. 确认输入齐不齐

- `output/<故事名>/videos/ep0X/shot_cards.json`——`short-drama-video-gen` 的
  产出，**本 skill 唯一的数据源**。没有就回去补，不要自己拼 JSON。
- `output/<故事名>/keyframes/ep0X/keyframes.md`——核对首帧路径确实是选中的
  关键帧文件，两边对不上以 `keyframes.md` 为准并提醒用户。
- `output/<故事名>/assets/selected.md`——如果这一批要用角色三视图当
  `<Subject N>`，从这里取选定的三视图路径。

## 2. H3 特有的三件事，先想清楚再装配

这三件都是 LTX 那边**根本不存在**的问题，所以别照搬 LTX 的经验。

### 2.1 时长必须落在 4–15 秒，而且时长是离散的

`num_frames` 必须是 `17n+5`（24fps），所以可用时长只有这些点：

```
n=5   90 帧  3.750s
n=6  107 帧  4.458s
n=7  124 帧  5.167s
n=8  141 帧  5.875s
n=9  158 帧  6.583s
n=10  175 帧  7.292s
n=11  192 帧  8.000s
```

**装配器会自动向上吸附，并且拿吸附后的时长判窗口**（官方原话是 "the
resulting duration has to stay in that window"）。所以 4.71s 会变成 5.167s、
合法；而 3.04s 吸附完还是 3.042s、不合法。

⚠️ **我们为 LTX 拆的 2–3 秒短单元，H3 一条都跑不了。**《出狱后》v2 ep01 的
40 个单元里有 16 个低于 4 秒。**出路是合并相邻单元，不是调下限**。

下限口径：SGLang / README / vLLM 都说 **4 秒**，只有 diffusers 说 5 秒。
默认 `--min-duration 4.0`（我们走 SGLang serve）。

### 2.2 这一批用哪些参考素材

H3 的 `ref2va` 吃**一组参考**，不是一张焊死的首帧。我们的映射：

| 素材 | H3 标签 | 怎么用 |
|---|---|---|
| 这一镜的关键帧 | `<Picture 1>` | 声明为 `[Shot 1]` 的首帧（ref guide §2.2 允许图充当具体帧锚点） |
| 角色三视图 | `<Subject N>` | 卡上可选字段 `references: [{name, image, note_zh}]` |

**只用来定义人物长相/场景/风格的图不单独立 `<Picture N>`**——官方明确要求把
图源写进对应 `<Subject N>` 的定义里。装配器已经按这条实现。

官方上限：**图 ≤9、视频 ≤3、音频 ≤3，跨类型总数 ≤12**。超了报 ERROR。

**要不要带角色三视图？** 带了等于多一条保人物一致性的通道，是 LTX 完全没有的
（那边 `ref_images` 是死字段）。但会占参考位、也没实测过效果。
建议：**先不带跑一轮基线，再带上跑一轮对比**，别一上来就当成必需品。

### 2.3 镜头卡的逐拍动作对 H3 来说可能太笼统

官方对生成类任务建议 `detailed_description` 写到 **350–500 英文词**。
我们从现有 LTX 卡装出来通常只有 150–200 词，装配器会 WARN。

**这不是让你在装配器里灌水凑字数**——WARN 的意思是回 `short-drama-video-gen`
把 `beats` 写细一档。H3 吃得下更细的时间轴描述，写粗了是浪费它的能力。

## 3. 装配即校验（本 skill 的核心）

H3 这一侧**没有独立的校验脚本**——装配器边装边校，装不出合规提示词就报 ERROR
不写文件。所以"校验"就是跑一次装配：

```bash
python3 .claude/skills/short-drama-video-gen/scripts/build_h3_prompt.py \
  output/<故事名>/videos/ep0X/shot_cards.json \
  -o output/<故事名>/videos/ep0X/h3_jobs.json
```

常用参数：

- `--lint`：只校验并打印装配结果，不写文件。**第一次先用这个把提示词读一遍。**
- `--only <镜id>`：只处理部分镜头
- `--min-duration 4.0`：时长下限，默认 4.0（SGLang 口径）
- `--task ref2va`：默认就是它。`fl2va`/`t2va` 保留是为了将来做首尾帧插值

### 它拦的每一条，对应的官方规则

**结构层**

- **六段齐全且顺序固定**：`subject_definitions` / `summary` /
  `retention_analysis` / `detailed_description` / `overall_soundscape` /
  `non_diegetic_music`。一段都不能少，没有内容就写 `N/A`。
- **风格句写在 `[Shot 1]` 之前**（ref guide §5.2，跟三段格式不同——那边风格
  写在 `[Shot 1]` 之后）。
- **`retention_analysis` 里不许出现 `(Sx)`**。那一段只写引用关系
  （`fully_preserved` / `partially_preserved` / `attribute_transfer` /
  `weak_reference`），说话人 ID 只出现在 `detailed_description`。

**内容层**

- **运镜必须命中官方 20 个受控词** + 可选的幅度（`with small|large amplitude`）
  + 速度（`at slow|fast speed`），写成镜头内的自然英文动作、不是末尾贴标签。
  **镜头不动也要显式写 `holds a static shot`**。
  装配器会先试着把 LTX 那种散文运镜翻过来
  （`a slow, restrained push-in that…` → `pushes in with small amplitude at
  slow speed`），翻不出来就报 ERROR，让人在卡上补 `camera_en.h3_move`。
  **别让它自由发挥**——H3 对这套词表的响应是训练出来的，写别的会退化成镜头不动。
- **台词包成 `<d>[Language] 原文</d>`**，语言取自 H3 稳定支持的 11 种。
  `<d>` 里**只放**语言标签和原文，逐字保留不翻译；说话人身份、动作、语气
  一律写在 `<d>` **外面**。
  装配器会把 LTX `delivery_en` 里自带的 "he says in Mandarin Chinese," 摘掉，
  否则会出现既重复又不合规的写法。
- **旁白**必须用官方固定短语 `says in an off-screen voiceover`，紧跟一句
  嘴闭着的声明。
- **说话人 ID** 按实际发声顺序分配 `(S1)`/`(S2)`，同一人跨镜不变，不发声的
  不给 ID。
- **否定句**：H3 是 guidance 蒸馏，**没有 `negative_prompt`、没有
  `guidance_scale`**，"不要 X" 只会把 X 注入编码器。`<d>` 里的台词原文豁免
  （那是人物真的在说的话）。

**参数层**

- 时长窗口（判吸附后的值）、`num_frames` = `17n+5`
- **宽高 32 的倍数**（注意不是 LTX 的 64）
- 画幅吸附到官方比例（21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16）——我们的
  704×1280 化简是 11:20，H3 不认，会吸附成 9:16
- 短边不是 768 时 WARN（开源只有 768p 档，2K 要走没开源的 `H3-Regenerate-2K`）
- `conditions[]` 里每个文件真实存在

**报错就回 `short-drama-video-gen` 改镜头卡再重跑装配，不要手改 JSON。**
手改会让 prompt 和卡脱钩，而且下次装配就把手改的内容冲掉了。

## 4. 检查/生成 `h3_remote_config.json`

跟 LTX 的 `ltx_remote_config.json` 是两份不同的文件，别混用——H3 走 HTTP、
没有 `pipeline_module`/`pipeline_extra_args` 那套 CLI 参数。

```json
{
  "model": "minimax-h3",
  "platform": "runpod",
  "instance_id": "<pod_id>",
  "network_volume_id": "<volume_id>",
  "ssh_host": "root@<公网IP>",
  "ssh_port": 12345,
  "ssh_key": "~/.ssh/id_ed25519",
  "model_variant": "ref2va",
  "model_path": "/workspace/MiniMax-H3",
  "endpoint": "http://127.0.0.1:30011"
}
```

- **`platform` + `instance_id` 必填**——"用完就关"那套收尾机制靠它们才知道
  该关哪台机器。租显卡那一步能拿到，别漏填；漏了最容易演变成"忘了关、
  显卡通宵计费"。
- `endpoint` 通常是 SSH 隧道的本地端口（见 `minimax-h3-generate`），
  不是 Pod 的公网地址。

## 5. Dry-run：看真实的 HTTP 请求体

```bash
python3 .claude/skills/minimax-h3-generate/scripts/h3_submit.py \
  --jobs output/<故事名>/videos/ep0X/h3_jobs.json \
  --out-dir output/<故事名>/videos/ep0X \
  --endpoint http://127.0.0.1:30011 --dry-run
```

不连远程，只把请求体打出来（首帧那段 base64 缩略成 `<data url, N chars>`）。
逐条确认：

- `task` 是 `ref2va`
- `target.duration_seconds` 是**吸附后**的值，落在 4–15
- `conditions[]` 的 `role` 都是 `reference`，**没有 `frame_index`**
  （有 `frame_index` 说明装成 fl2va 了，那是首帧焊死的模式，不是我们要的）
- 六段都在、顺序对

## 6. 汇报

给用户：这一批多少条、总时长、多少条被拦下（分别因为什么）、多少条带了
角色参考、`detailed_description` 词数偏短的有哪些。

**被拦下的短单元要单独列出来**，因为它们的出路是回 `short-drama-video-gen`
合并相邻单元——这是需要人决定的编辑动作，不要自己合。

## 与其他 skill 的衔接

- 上游 `short-drama-video-gen`：维护 `shot_cards.json`（模型无关）和
  `build_h3_prompt.py`。**镜头卡和装配器都住在那边**，本 skill 只是驱动它、
  并把 H3 特有的判断规则写清楚。
- 下游 `minimax-h3-generate`：租显卡、部署 SGLang、提交、验收、关机。
- 平行的 `short-drama-ltx-export`：同一份卡的 LTX 通道。**同一集不要混用
  两个模型**——质感、人脸、镜头语言都不一样，剪在一起会穿帮。
