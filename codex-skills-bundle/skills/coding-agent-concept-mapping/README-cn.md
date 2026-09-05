# Concept Mapping Skill

这个 Skill 是一个跨工具的概念映射知识库,回答同一个项目级配置概念在 Claude Code、Codex、Antigravity 三个 AI 编程工具里分别长什么样,以及把一套配置从一个工具搬到另一个工具时要注意什么。它是给读者查阅用的那一层;这些文件怎么写出来、怎么维护,归隔壁的 `coding-agent-concept-mapping-builder` Skill 管。

---

## 1. 它解决什么问题

同一个概念在不同工具里常常换了名字、换了文件位置、换了语法。你在 Claude Code 里配好的项目指令、skills、hooks、MCP、权限,搬到 Codex 或 Antigravity 时,很难一眼看出对应关系,更别说其中的坑。这个知识库就是把这些对应关系提前梳理好,让你不用每次都重新对着三份官方文档比对。

它以 Claude Code 作为「种子」(seed):每个概念都用 Claude Code 的词汇来命名和框定,另外两个工具的列则描述它们如何实现同一个概念,或者干脆没有对应物。真正有价值的不是三份互不相干的说明,而是它们之间的对齐,以及跨工具搬运时的具体注意事项。

---

## 2. 怎么用

大多数时候你不用做什么。当你的问题涉及某个配置概念在这三个工具之间如何对应、或者如何迁移时,触发这个 Skill 即可。

它的用法是「先读索引,再按需加载详情」。先看 [ref/00-context-index.md](ref/00-context-index.md),那里一行一个概念,列出每个工具的主要文件位置,并链接到对应的详情文件。找到匹配的概念后,再打开它的 `XY-concept-name.md` 详情文件,读你关心的那个方面。每个详情文件把概念拆成若干方面(文件位置、格式、作用域、加载行为等),每个方面是一张三工具对比表,最后一行 `Porting-in notes` 说明搬进每个工具时要注意什么。

如果索引里没有匹配的概念,它会如实说「还没映射过」,而不是猜。

---

## 3. 它和 builder 的关系

这个 Skill 只负责读和答,不负责写。知识库里的文件由 `coding-agent-concept-mapping-builder` 撰写和维护,而 builder 的每一条事实都通过 `claude-code-docs`、`codex-docs`、`antigravity-docs` 三个文档 Skill 从当前官方文档取证。所以这里的内容不靠记忆,而是落在可核查的官方来源上。

要新增一个概念、按最新文档刷新某个概念、或者修正某处映射,都走 `coding-agent-concept-mapping-builder`,这样所有文件才会保持一致的结构和口径。不要在这里手工添加新事实。

builder 是维护者侧的工具,不随本 plugin 一起分发,所以这里给的是绝对链接: https://github.com/MacHu-GWU/shsk_coding_agent_docs-project/blob/main/.claude/skills/coding-agent-concept-mapping-builder/SKILL.md

---

## 4. 目录结构

```text
coding-agent-concept-mapping/
├── SKILL.md              入口, 定义先读索引再按需加载详情的用法
├── README-cn.md          本文件
└── ref/
    ├── 00-context-index.md    索引, 一行一个概念, 由 builder 汇总生成
    └── XY-concept-name.md     每个概念一份的详情文件, 由 builder 撰写
```

目前已映射的概念,按注册表顺序:project prompt、project settings、skills、custom commands、hooks、MCP servers、subagents、permissions、plugins and marketplaces。每新增一个概念,builder 会先写详情文件,再把它汇总进索引。
