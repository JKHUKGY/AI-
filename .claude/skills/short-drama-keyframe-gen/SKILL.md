---
name: short-drama-keyframe-gen
description: 面向 AI 短剧的逐集关键分镜关键帧生成助手：读取 short-drama-storyboard 产出的分集分镜表（ep0X.md）和 short-drama-image-gen 已经选定的人物/场景基准图，按集从分镜表里挑出约 8-12 个真正关键的镜头（开场钩子/结尾钩子/S级高光镜/核心冲突反应镜），把该镜的简写提示词展开成完整 prompt 并引用对应人物+场景基准图，调用 Codex CLI（ChatGPT 账号登录，内置 image_gen 工具）合成出这一镜的关键帧图，逐张核对是否还原了画面描述/景别/人物场景一致性，不合格就调整重生成，产出可直接用于图生视频起始帧或分镜预览的关键帧图库。当用户要求"生成关键分镜图""按分镜出关键帧""把这集分镜做成图""这一集挑几个镜头出图"时使用。
---

# AI 短剧关键分镜关键帧生成助手 (short-drama-keyframe-gen)

承接 `short-drama-storyboard`（分镜表）+ `short-drama-image-gen`（人物/场景
基准图）之后的下一步：不逐镜全出图，只挑每集真正关键的镜头，把人物和场景
基准图合成到具体的分镜画面里，产出这一集的关键帧图库。

## 0. 先确认输入齐不齐

需要三样东西，缺哪样就先引导用户补上，不要凭空臆造：

- `short-drama-storyboard` 产出的分集分镜表 `ep0X.md`（含镜号/场景/出场
  人物/画面描述/景别/分级/图像生成提示词等列）。
- `short-drama-image-gen` 产出的 `selected.md`（人物/场景最终选中的基准图
  文件路径登记表）——没有这个就没法保证关键帧里的人物/场景和之前出的立绘
  是同一套，必须先跑 `short-drama-image-gen` 把角色/场景图定下来。
- `characters.md` / `scenes.md`（画风锚点、造型/表情/场景版本对照）。

同时问清楚**这次要处理哪几集**——默认不要一次性把全剧所有集数都跑一遍，
除非用户明确说"全部集数都做"，逐集处理更方便中途核对质量、控制成本。

## 1. 挑关键镜头（每集约 8-12 个，灵活）

按 `references/shot_selection.md` 的规则从这一集的分镜表里挑镜头：必选
开场钩子镜、结尾钩子镜、所有 S 级镜、核心冲突相关的关键 A 级反应镜；视情况
补选新场景定场镜；跳过标了"复用素材"的镜和纯环境空镜。数量不是硬指标，
剧情密度大就多选，铺垫戏份就少选。

先把选中镜号 + 一句选中理由的清单给用户看一眼再往下走，避免选错重点返工。

## 2. 展开提示词、收集参考图

对每个选中镜头，按 `references/keyframe_prompt_guide.md` 把分镜表里的
简写"图像生成提示词"展开成完整可用的 prompt，并去 `selected.md` 查出对应
的人物/场景基准图文件路径（注意日夜版本、造型阶段要对上分镜表里的标注）。
查不到对应素材就停下来告诉用户缺哪张，不要用文字硬猜替代已有的基准图。

组装成 `jobs.json`（复用 `short-drama-image-gen` 的
`references/jobs_schema.md` 格式），`id` 用 `ep{集号:02d}_镜{镜号:02d}`
命名，`ref_images` 通常是"1张场景图 + 1-2 张人物图"，`count` 默认 2-3。

## 3. 调用脚本生成

直接复用 `short-drama-image-gen` 的生成脚本，不重复造轮子：

```bash
python3 .claude/skills/short-drama-image-gen/scripts/generate_images.py \
  output/<故事名>/keyframes/jobs_ep0X.json \
  --out-dir output/<故事名>/keyframes/ep0X
```

API Key 设置、模型选择、速率限制注意事项参照
`.claude/skills/short-drama-image-gen/references/api_setup.md`，这里不再
重复。

## 4. 验收，不合格就调整重生成

用 Read 工具逐张实际查看生成的关键帧图，按
`references/keyframe_review_checklist.md` 核对：是否还原了画面描述、景别
对不对、人物/场景是否与基准图保持一致、多人物位置关系是否合理。不合格就
调整 prompt（写清楚上一轮具体问题）重新小批量生成，单个镜头连续 3 轮选不出
可用图就停下来向用户汇报，不要无限重试。

## 5. 整理产出

把每个镜头最终选中的一张（或用户要求保留的备选）整理进
`output/<故事名>/keyframes/ep0X/keyframes.md`：

| 镜号 | 场景 | 出场人物 | 对应画面描述 | 选中文件路径 | 分级 |
|---|---|---|---|---|---|

这份表就是后续"图生视频"环节要直接引用的起始帧素材清单，也可以直接当作
给团队/客户看的分镜预览图。

## 6. 汇报

结束时给一个小结：本集分镜表共 N 镜，挑了 M 个关键镜出图（未选的因为
复用/空镜跳过），本轮共调用生成 API 多少次，供并入
`short-drama-storyboard` 输出模板里的"成本与检查记录"。

## 与其他 skill 的衔接

- 上游：`short-drama-storyboard`（分镜表）+ `short-drama-image-gen`（人物/
  场景基准图与 `generate_images.py` 脚本，本 skill 直接复用不重复实现）。
- 下游：`keyframes.md` 里的文件路径会被 `short-drama-video-gen`（图生视频
  提示词与动画编排）直接引用作为起始帧，后续如果手动改了文件名/位置要同步
  更新这份表，否则下一步会引用失效路径。
