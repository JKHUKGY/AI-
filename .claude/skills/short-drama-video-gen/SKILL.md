---
name: short-drama-video-gen
description: 面向 AI 短剧的图生视频提示词与角色动画编排助手：承接 short-drama-keyframe-gen 产出的关键帧图库和 ep0X.md 分镜表里的"运动描述"列，把每个 S/A 级镜头的动作拆解成"起始姿态→过程关键点→结束姿态"分阶段动画描述，展开成可直接提交给可灵/即梦/Vidu/PixVerse/海螺/Runway/Veo 等图生视频平台的完整提示词（含运镜、光影变化、结尾定格、负面提示词、首尾帧/参考图用法），并给出稳定性方案（运动幅度控制、分段生成拼接、先测后上正式分辨率）防止人脸崩坏和动作失控；B 级镜头改用本地零成本的 ffmpeg 推拉摇移脚本直接产出视频，不进图生视频模型。当用户说"把关键帧做成视频""生成图生视频提示词""这一镜怎么做动画""关键帧转视频""设计视频生成工作流""引导角色动作"时使用。
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
这种情况不是"平台订阅"，而是用户自己完全控制的推理环境，SSH 是通用协议，
不存在"各家 API 不一样"的问题，所以本 skill 对这种情况提供了实际的调用
脚本 `scripts/ltx_ssh_submit.py`，直接跑通"上传首帧 → 远程推理 → 下载
视频"，不需要用户手动操作网页，见第 4.5 步和
`references/ltx2_self_hosted.md`。

另一个例外是 B 级镜头——那个可以用本地 `ffmpeg` 零成本搞定，见第 5 步。

先跟用户确认属于哪种情况（SaaS 手动提交 / 自建模型 SSH 调用 / 都不是），
避免走错流程。

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

- **C 级**：直接复用已有视频片段，跳过，不产出新 job。
- **B 级**：不进图生视频模型，走第 5 步的本地 `ken_burns.py` 脚本，零成本
  出片。
- **S/A 级**：本 skill 的核心工作，进入第 3-4 步展开详细提示词。

## 3. 角色动画怎么"引导"：把动作拆成三段，而不是一句话带过

这是这一步最容易做得敷衍的地方——很多人直接把分镜表"运动描述"列的一句话
（比如"她哭了"）原样丢给视频模型，模型会自己脑补一个不可控的动作。正确做法
是把动作拆解成三个阶段分别描述，具体方法见
`references/video_prompt_guide.md`，核心原则：

1. **起始姿态**：不用重新描述外观（关键帧已经锁定），只确认这一镜开始时人物
   的姿势/表情/视线方向，作为动作的"零点"。
2. **过程关键点**：把动作拆成 1-3 个具体的中间动作点（比如"眼眶泛红→睫毛
   颤动→泪水滑落→嘴角下撇"），每个点给一个动词短语，避免笼统形容词堆砌。
3. **结束姿态/定格**：明确这一镜结束时人物停在什么姿态，配合
   `short-drama-storyboard` 分镜割手法里的"定格感"——关键情绪瞬间让画面在
   结束前有 0.5-1 秒的停顿感，而不是一直动到镜头切换。

动作幅度要克制：S 级镜头（值得多轮生成、预算最高）才适合大幅度动作（打斗、
拥抱、跌倒），A 级镜头（对话/反应镜，全集主体）只做小幅度动作（微表情、
转头、抬手），幅度越大越容易人脸变形/肢体拉伸，这一点在
`references/stability_playbook.md` 里有具体规避方法。

## 4. 展开完整提示词、选平台、定首尾帧策略

对每个选中的 S/A 级镜头：

1. 按 `references/video_prompt_guide.md` 的公式，把"运动描述+运镜+分级"
   展开成完整正向提示词 + 负面提示词。提示词要聚焦"动作和镜头怎么变化"，
   不要重复堆砌关键帧里已经锁定的外观/服装描述（会稀释动作指令的权重）。
   同时把 `ep0X.md` 该镜的"台词/旁白"列原样摘抄进 `video_jobs.md`/
   `video_jobs.json` 的 `台词/旁白` / `dialogue` 字段——这只是给配音/剪辑
   环节对照用的参考信息，**不要**把台词塞进正向提示词里指望模型生成语音
   或对口型，目前没有确认过任何平台能可靠做到这件事。
2. 判断这一镜要不要用"首尾帧控制"：如果动作有明确的起止状态差异（比如从
   跪地到站起），优先选支持首尾帧的平台，尾帧如果关键帧库里没有对应的
   "结束状态"图，先判断要不要回到 `short-drama-keyframe-gen` 补一张，不
   要让视频模型自己瞎猜结束姿态。
3. 参照 `references/video_platform_comparison.md` 给这个镜头推荐 1-2 个
   平台（结合镜头需求、用户预算/账号情况），列出该平台需要几张参考图、怎么
   传首尾帧、时长上限。
4. 长动作（超过平台单次时长上限，或包含多个动作阶段）按
   `references/stability_playbook.md` 的分段生成法拆成 2-3 个短片段，
   前一段的结束帧作为下一段的起始帧，而不是硬塞一个长 prompt 赌一次成型。

把结果整理成 `output/<故事名>/videos/ep0X/video_jobs.md`（字段结构见
`references/video_jobs_schema.md`），这就是给用户手动提交生成的清单。如果
用户明确要接自己的 API，再额外导出一份对应的 JSON。

## 4.5 自建 LTX-2.5：SSH 直接提交生成任务

如果用户是自己租显卡、自己部署了 `Lightricks/LTX-2`（LTX-2.5）这类开源
模型，不要停在"整理清单等用户手动提交"这一步——按下面的流程直接跑：

1. 先读 `references/ltx2_self_hosted.md`，确认当前对 LTX-2.5 接口的已知
   信息和不确定项（尤其是首尾帧参数名、`--negative-prompt` 是否通用），
   不要凭空编参数名。
2. 找用户要 SSH 访问信息（地址/端口/密钥），以及远程机器上 LTX-2 仓库路径
   和模型权重路径，按模板整理成 `ltx_remote_config.json`。
3. 把第 4 步展开好的提示词，按 `video_jobs_schema.md` 的 JSON 格式导出，
   额外补 LTX 需要的 `width`/`height`（像素，需 64 整除）等字段。
4. 先对 1-2 个用户指定的关键镜头跑：
   ```bash
   python3 .claude/skills/short-drama-video-gen/scripts/ltx_ssh_submit.py \
     --config ltx_remote_config.json \
     --jobs output/<故事名>/videos/ep0X/video_jobs.json \
     --out-dir output/<故事名>/videos/ep0X \
     --only <镜号> --dry-run
   ```
   `--dry-run` 先确认拼出来的远程命令对不对，再去掉这个参数真跑。
5. 视频下载回本地后，按第 6 步抽帧验收；不合格就回
   `stability_playbook.md` 调整提示词/参数后用 `--only` 只重跑这一镜，
   确认没问题再批量跑剩下的镜头，不要没验证过第一条就把整集一次性提交。

## 5. B 级镜头：本地零成本推拉摇移

B 级镜头不用麻烦图生视频平台，直接用关键帧图跑本地 Ken Burns 效果：

```bash
ffmpeg -version   # 先确认已安装，没有就指导用户 apt-get/brew 装一下
python3 .claude/skills/short-drama-video-gen/scripts/ken_burns.py \
  output/<故事名>/videos/ep0X/kenburns_jobs.json \
  --out-dir output/<故事名>/videos/ep0X
```

`kenburns_jobs.json` 格式和用法见脚本头部注释：每条 job 指定关键帧图片、
运镜方向（推/拉/摇左/摇右/摇上/摇下）、时长、输出分辨率，脚本调用 ffmpeg
的 `zoompan` 滤镜合成 mp4，不消耗任何生成 API 额度。运镜方向要对应分镜表
"运镜"列，不要随手选一个和分镜意图不符的方向。

## 6. 验收：视频不能像图片一样直接 Read，要先抽帧

Read 工具能看图片，看不了视频。验收视频质量要先用脚本抽帧再看：

```bash
python3 .claude/skills/short-drama-video-gen/scripts/extract_frames.py \
  <生成的视频文件路径> --out-dir <帧输出目录> --count 5
```

用 Read 工具逐张查看抽出来的帧，按 `references/video_review_checklist.md`
核对：首帧是否还是原关键帧的样子（没有跑偏）、中间帧人脸/服装是否保持一致
没有变形换脸、动作方向和分镜表运动描述是否一致、结尾帧是否落在预期的定格
姿态。音画同步（口型/BGM 卡点）只能靠用户自己听，Claude 帮不了这部分，
提醒用户自己确认。

不合格就按 `references/stability_playbook.md` 的思路调整提示词（缩小动作
幅度、拆得更短、加强负面提示词）重新提交，单个镜头连续 3 轮选不出可用片段
就停下来向用户汇报具体卡在哪，不要无限重试烧钱——视频比图片贵得多。

## 7. 汇报

结束时给一个小结：本集 S/A 级镜头共 N 个，展开了几份提示词、推荐了什么
平台；B 级镜头本地生成了几个（零成本）；如果用户已经手动提交生成过，核对
了几轮、最终确认了哪几个镜头的视频文件路径。这些数字并入
`short-drama-storyboard` 输出模板的"成本与检查记录"。

## 与其他 skill 的衔接

- 上游：`short-drama-keyframe-gen`（关键帧图库 `keyframes.md`）+
  `short-drama-storyboard` 分镜表（`ep0X.md` 的"运动描述""运镜""分级"列）+
  `short-drama-image-gen` 的 `selected.md`（补充一致性参考图）。
- 下游：`video_jobs.md` 是给用户/剪辑环节的提交清单，用户手动生成或接自己
  API 拿到视频文件后，路径要回填进这份表，方便剪辑阶段按镜号找素材；
  `ken_burns.py` 产出的 B 级视频文件可以直接进剪辑时间线，不需要额外处理；
  自建 LTX-2.5 的场景由 `ltx_ssh_submit.py` 直接把视频下载到
  `output/<故事名>/videos/ep0X/`，同样要把路径回填进 `video_jobs.md`。
