---
name: maintain-claude-plugins
description: My personal, authoritative spec for building, developing, versioning, releasing, and wiring dependencies for my own Claude Code plugins through a split-repo plus central-marketplace setup. Use when creating a new plugin repo, laying out a plugin's .claude/skills/<name>/ folder, writing plugin.json or marketplace.json, tagging a plugin release, wiring plugin-to-plugin dependencies, authenticating private repos, or when I ask how to structure, release, or publish my Claude Code plugin.
---

# 维护我自己的 Claude Code 插件

这是我维护自己 Claude Code 插件的终极规范. 完整内容在 [reference/personal-plugin-marketplace-best-practices.md](reference/personal-plugin-marketplace-best-practices.md) —— 需要具体做法或想回看某条决策的理由时读它.

## 架构一句话

三类 GitHub 仓库各司其职:

- **每个插件一个独立 repo**, 插件代码放在 `.claude/skills/<插件名>/` 下 (开发时靠 `@skills-dir` 自动加载, 发布时用 `git-subdir` 引用).
- **一个中央 marketplace repo**, 只有一个 `.claude-plugin/marketplace.json` catalog, 用 `git-subdir` source + `ref` 指向各插件 repo 的发布 tag.
- **使用者的 workspace repo**, 在 `.claude/settings.json` 里用 `extraKnownMarketplaces` + `enabledPlugins` 声明式装插件.

## 什么时候读 reference 的哪一节

| 我要做的事 | 读哪节 |
| :--- | :--- |
| 建新插件 repo / 摆放插件目录 / 写 plugin.json | 1, 2.1 |
| 写中央 marketplace.json | 2.2 |
| 让使用者 clone 即用 (settings.json) | 2.3 |
| 开发时加载测试, 搞懂作用域限制 | 3 |
| 搞清 skill / agent 的命名空间前缀 | 4 |
| 一个插件依赖另一个插件 | 5 |
| 插件内 / 跨插件 skill 互相调用 | 6 |
| 私有 repo 认证 (手动 / 后台更新) | 7 |
| 发新版本的完整流程 | 8 |
| 使用者怎么装 | 9 |
| 命令速查 / 决策速查 | 10 |

## 发布一个新版本 (最常用)

在插件 repo 里: 改代码 → bump `plugin.json` 的 `version` → `git commit` → `mise run tag-plugin` (扫描 `.claude/skills/` 批量打 `{插件名}--v{版本}` tag 并推送) → 去 marketplace repo 把对应 `source.ref` 改成新 tag 并 push → 用户 `/plugin marketplace update`. 细节和为什么这么做见 reference 第 8 节.

## 底层脚本: scripts/plugin_release.py

`mise run tag-plugin` 和 `mise run list-plugins` 背后都是这一个 0 依赖纯标准库 CLI: [scripts/plugin_release.py](scripts/plugin_release.py). 它从当前目录**往上找到 `.git`** 定位 git repo 根, 扫描 `<repo根>/.claude/skills/` 下每个目录, 对含 `.claude-plugin/plugin.json` 的做校验 (必须有 `name`/`description`/`version`, 且 `version` 是 `x.y.z`; 有文件但格式不对就报错), 没有 manifest 的当 standalone skill 忽略.

| 命令 | 作用 |
| :--- | :--- |
| `python3 scripts/plugin_release.py list` | 列出并校验所有插件 (加 `--json` 输出机器可读) |
| `python3 scripts/plugin_release.py tag` | 先整体校验 (任一 manifest 非法则中止), 再逐个 cd 进插件目录跑 `claude plugin tag --push`, 已存在的 tag 跳过 (`--no-push` 只本地打, `--force` 移动已存在 tag) |

因为靠 git-root 自动发现, 这个脚本在**任何**插件 repo 里都能直接跑, 不只这个 repo. 在别的插件 repo 里复用时, 把这个 skill 带过去, 再在那个 repo 的 `mise.toml` 里加一行指向本脚本的 `tag-plugin` 任务即可.
