---
name: index
description: AI 短剧仓库的分层定位入口。查文件、素材、脚本、网址账号、实时进度或历史决策时使用；按问题只读一条索引分支，避免全仓库扫描。
---

# 分层定位

在仓库根执行命令。当前技能目录记作 `I`（本文件所在目录），技能根目录记作 `S`（`I` 的上级）。
Codex 的 `S=.agents/skills`；Claude 的 `S=.claude/skills`。共同地图在根目录 `docs/index/`。
下面的 `I` / `S` 是路径占位符，执行前替换；不用先读脚本源码。
下钻文档若使用 `.claude/skills/` 的脚本/规范路径，Codex 使用 `.agents/skills/` 对应文件；私有配置和项目素材路径保持原意。

## 先选一条分支

| 问题 | 最小读取入口（地图路径相对仓库根） |
|---|---|
| 已知文件路径、剧名/集号/镜号 | 直接访问；需查文件名模板才读 `docs/index/outputs.md` |
| 不知道是哪部剧或哪个版本 | `docs/index/projects.md` → 指定项目 |
| 找 skill、脚本、规范 | `docs/index/pipeline.md` → 对应环节；已知 skill 就直接读 `S/<名称>/SKILL.md` |
| 找网站代码 | `docs/index/web.md` |
| 找网址、账号、主机、API key、原始剧本 | [资源入口](references/resources.md) → 只读对应资源页 |
| 现在做到哪一步、还缺什么 | `python3 I/scripts/snapshot.py --project <剧名>`；全部进度才省略 `--project` |
| 历史决策、研究依据 | `docs/index/history.md` → 只读长文命中章节 |
| 归档、配置、技能包、临时文件 | `docs/index/repository.md` |
| 完全不知道属于哪类、仓库全貌 | `INDEX.md`；其他分支不必先读它 |

## 读取与维护

- 一次只展开命中的分支；拿到路径就停。优先文件名搜索，再读相关片段；大 JSON/JSONL 按镜号或 ID 提取条目，不输出全文件。
- 未命中先在目标项目的某集/某阶段或目标 skill 内查；连续两次未命中，回分类入口换分支。私有配置、外部资源、冷归档先查对应页；确需扩大时逐级扩大目录，只返回匹配路径。
- `rg --files <限定目录>` / `rg -n '关键词' <文件>`；没有 `rg` 则用限定深度的 `find` / `grep -n`。长文查标题行号后用 `sed -n` 读对应段，不顺序扫到尾。
- 数量及完成状态以磁盘为准，候选文件数不等于验收数；网址/IP/线上状态先验证再引用（`--online`、`curl`、`az vm list -d -o table`）。查询不触发生成、租卡或改服务。
- 新文件只更新所属分类，新增类别才改入口；保持入口短小，不把详细流程、进度数字、完整文件清单塞回来。共享地图只维护 `docs/index/`；资源/入口修改同步两个宿主。
