# 仓库索引

AI 短剧流水线。这里只选区域；**只读命中的一份分类索引，定位后停止展开**。
已知路径就直接读目标文件，无需从入口重走。下列链接相对仓库根目录。

| 要找什么 | 下一步 |
|---|---|
| 哪部剧、原版/v2/v3、试拍目录 | [项目目录](docs/index/projects.md) |
| 分镜、人设、场景、图片、关键帧卡、镜头卡、视频、反馈 | [产出文件](docs/index/outputs.md)；已知剧名时直接用路径模板 |
| 哪个 skill、生成/校验脚本、提示词规则 | [流水线](docs/index/pipeline.md) |
| 网站前后端、登录、在线编辑、重新生成 | [网站代码](docs/index/web.md) |
| 网址、账号、云主机、API key、原始剧本 | 当前宿主的 index skill → `references/resources.md`（资源分类入口） |
| 实时进度、还缺什么 | 当前宿主的 index skill → `scripts/snapshot.py --project <剧名>`；全部项目才省略筛选 |
| 历史决策、需求、研究依据 | [历史与研究](docs/index/history.md) |
| 归档、配置、技能副本、临时文件 | [其他目录](docs/index/repository.md) |

宿主：Codex 用 `.agents/skills/`，Claude 用 `.claude/skills/`；地图共用 `docs/index/`。
索引只记用途和路径，不记录动态进度。新增文件更新所属分类；新增类别才改本页。
