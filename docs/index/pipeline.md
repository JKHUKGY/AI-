# 流水线定位

下列 skill 名相对宿主根目录：Codex `.agents/skills/`；Claude `.claude/skills/`。
知道环节就直接读该 skill 的 `SKILL.md`；只找内部脚本/规范时才打开最后一列的分类表。

| 环节/关键词 | Skill | 内部文件地图 |
|---|---|---|
| 内部全流程联调、冒烟测试、断点续跑；出图/租卡前等确认 | `short-drama-internal-test` | 直接读该 skill；串联下列环节 |
| 选题、故事、分集大纲 | `short-drama-scout` | [故事与分镜](pipeline/story.md) |
| 分镜表、画风、人设、场景机位、逐步确认 | `short-drama-storyboard` | [故事与分镜](pipeline/story.md) |
| 人物三视图、场景图、素材出图 | `short-drama-image-gen` | [素材与关键帧](pipeline/images.md) |
| 关键帧卡、走位、场次主帧、连戏 | `short-drama-keyframe-gen` | [素材与关键帧](pipeline/images.md) |
| 镜头卡、视频提示词、L1/L2/L3 返工、背景运动检测 | `short-drama-video-gen` | [视频装配](pipeline/video.md) |
| LTX 提交前校验 / 实际生成 | `short-drama-ltx-export` / `short-drama-ltx-generate` | [校验与执行](pipeline/execution.md) |
| H3 六段提示词校验 / 自建或云 API 生成 | `minimax-h3-export` / `minimax-h3-generate` | [校验与执行](pipeline/execution.md) |
| RunPod 租卡、关机、空闲监控（两通道共用） | `short-drama-ltx-generate` | [校验与执行](pipeline/execution.md) |
| 出图 + 独立审查循环 | `loop-picture-generation` | 直接读该 skill |
| 出视频 + 独立审查循环 | `loop-video-generation` | 直接读该 skill |
| 单图→深度/3D/轨迹→可控视频、A/B demo与报告 | `single-image-video-control` | 本次源码在 `.claude/skills/single-image-video-control/SKILL.md`；Codex技能目录本会话只读，使用交付包或直接读取该源码 |

结构化卡是手写来源，提示词由 `build_*.py` 装配；定位技能不代表获准生成或租卡。
未命中时只在对应 skill 的 `scripts/` / `references/` 列文件，避免加载整套 skills。
