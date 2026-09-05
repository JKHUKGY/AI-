# 其他目录

路径相对仓库根。这里只索引区域，临时目录不枚举文件。

| 区域 | 用途/下一步 |
|---|---|
| `.agents/skills/` / `.claude/skills/` | Codex / Claude 的实际技能入口；定位环节见 [流水线](pipeline.md) |
| `docs/index/` | 两个宿主共用的分类地图 |
| `scripts/ARCHIVE.md` | 素材冷归档到 Google Drive、恢复方法；先查标题再读相关段 |
| `docs/archives/README.md` | 历史测试媒体、网站验收与发布快照的 Google Drive 选择性归档及恢复清单 |
| `scripts/archive.py` / `scripts/archive_config.json` | 归档工具及配置；仅定位不会触发归档/下载 |
| `README.md` | 给人的流水线使用说明、触发词、环境准备 |
| `.gitignore` | 私有配置和临时文件的忽略规则 |
| `AGENTS.md` / `.codex/config.toml` | 项目文件修改边界及 Codex 沙盒/免审批默认设置 |
| `web/server/data/` | 本机登录账号哈希、会话密钥（gitignore）；部署另看 `web/DEPLOY.md` |
| `.claude/settings.local.json` / `.codex/` | 宿主本地配置区域；具体内容以磁盘为准 |
| `codex-skills-bundle/` / `codex-skills-bundle.zip` | 导出的技能包；日常执行读实际宿主目录 |
| `shsk_coding_agent_docs-project/` | 编程 agent 文档相关项目；仅在问题指向它时查内部入口 |
| `tmp/` | 临时工作、迁移/检查产物；按任务关键词限定文件名查找 |
| 根目录 `.docx` / `.pdf` / `列车重逢/` | 外部剧本与参考素材；详见 index skill 资源入口 |

`review.json` 要提交；`_web_state/logs/`、`.env`、`runpod_config.json` 等按规则忽略。
找不到私有配置先读资源页确认它在哪台机器，不要全仓库搜索密钥。
