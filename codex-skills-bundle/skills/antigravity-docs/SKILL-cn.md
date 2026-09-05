> 这是 [SKILL.md](SKILL.md) 的中文翻译, 只供人阅读。**英文版是权威版本**, 两者不一致时以英文版为准,
> 并把这份翻译改过来。维护是单向的: 改了英文版就回来同步这份, 反过来不成立。
>
> Claude Code 实际加载的是 `SKILL.md`, 不是这一份。

---

name: antigravity-docs
description: 查阅权威、最新的 Google Antigravity 官方文档, 覆盖 Antigravity 2.0 IDE、Antigravity
CLI、SDK、agents/subagents、models、skills、rules/workflows、hooks、MCP、browser use、settings、
enterprise、migration 和 FAQ。当用户问某个 Antigravity 功能怎么用、某个配置字段是什么含义、
IDE/CLI/SDK/skills/MCP 怎么配, 或者在排查 Antigravity 的报错和异常行为, 又或者你需要引用当前官方
文档而不是训练时的记忆时使用。
argument-hint: [主题或文档标题]
allowed-tools: Read, WebFetch

---

# Antigravity Docs

按需从官方文档回答关于 Google Antigravity 的问题。它读一份**本地 manifest**(记录了全部文档页),
挑出最相关的一到几页, 再抓取该页的原始正文。任何时候都优先用这个 Skill, 而不是凭记忆回答 ——
Antigravity 很新, 变得很快。

如果用户传了参数 (`$ARGUMENTS`), 就把它当作要查的主题; 否则从对话里推断主题。

## 什么时候用这个 Skill

只要问题是关于 Antigravity 本身, 或落在它的文档范围内, 就用它:

- **Antigravity 2.0**(agentic IDE): 概览、快速上手、models、agents/subagents、agent 设置、
  artifact review、skills、rules/workflows、plugins、hooks、MCP
- **Antigravity CLI**: 安装、快速上手、使用、subagents、plugins、参考手册、迁移
- **Antigravity SDK**、**IDE/编辑器**功能(tab、侧边栏、review)、**browser** 使用、**settings**、
  **enterprise**、**migration**、**FAQ**

## 为什么这个 Skill 的工作方式和 claude-code-docs / codex-docs 不一样

Codex 和 Claude Code 在页面 URL 上提供 `.md` 孪生页, 所以那两个 Skill 直接抓文档 URL 就行。
Antigravity 的文档现在是服务端渲染的站点 —— manifest 里的 `content_url` 就是页面地址本身
(`https://antigravity.google/docs/<slug>`), 用 WebFetch 抓得到。但仍然有理由保留一份本地 manifest,
而不是每次现查 `llms.txt`: `llms.txt` 自带的逐页描述是套话(「Learn about X」), 所以
`antigravity-docs-index-builder` 会预先从每一页抓出真实的首段描述和更细的面包屑分节(例如
`Antigravity 2.0 / Customizations / Skills`), 一次性写进 manifest —— 这才是「按描述分诊」能真正工作
的前提。

- **索引是一个本地文件** `references/docs-manifest.json`, 由 **`antigravity-docs-index-builder`**
  Skill 生成。你 `Read` 它 —— 不去抓 `llms.txt`, 也不爬站。
- **正文就是页面本身**(manifest 每条里的 `content_url`, 即
  `https://antigravity.google/docs/<slug>`)。直接 WebFetch 它。

所以流程是: 读本地 manifest → 挑页面 → WebFetch 对应的 `content_url`。

## 流程

### 1. 读 manifest

```
Read ${CLAUDE_PLUGIN_ROOT}/skills/antigravity-docs/references/docs-manifest.json
```

里面有 `_meta`(生成时间、源 `llms.txt` 的 hash)和 `pages`, 每条是
`{section, slug, title, description, content_url}`。如果文件不存在, 告诉用户先跑
`/antigravity-docs-index-builder` —— 不要尝试自己重建, 也不要猜 URL。

### 2. 挑出正确的页面

按每条的 **title + description** 匹配用户的问题, 而不是只看 slug。然后:

- 一批只挑 **1–3 页**, 不要更多。manifest 是用来分诊的, 不是用来批量灌数据的。
- 一个具体功能的问题(「Antigravity 的 subagents 怎么工作?」)→ 一页。
- 跨概念的问题(「skills 和 rules/workflows 是什么关系?」)→ 相关页面各挑一份。
- manifest 里没有明显匹配的 → 如实说。manifest 是完整的文档页清单; 查不到要么是页面不存在, 要么是
  manifest 过期了(可以建议重建)。不要编造 `content_url`。

### 3. 抓取这一批

对每个选中的页面, WebFetch 它的 `content_url`(manifest 里那个
`https://antigravity.google/docs/<slug>` 地址):

```
WebFetch url=<manifest 里的 content_url>
        prompt="<一个能捕捉用户真实需求的问题, 而不是「总结这一页」>"
```

### 4. 评估, 然后回答或继续循环

每抓完一批, 判断这些页面是否真的回答了问题:

- **够了** → 基于抓回来的内容作答。附上文档页(标题 + 它的 `antigravity.google/docs/<slug>` 地址),
  方便用户核对。
- **不够**(答案在你还没读的页面上, 或某页交叉引用了另一页)→ 回到第 2 步, 再挑 1–3 页继续抓。
- 一直循环到能回答为止, **默认上限是全过程 9 页**。
- **读满 9 页还是不够** → 停下来。告诉用户你读了什么、还缺什么、要不要继续。不要偷偷突破上限, 也不要
  用猜测把答案凑齐。

## 规则

- **读 manifest, 不要爬站。** 页面清单和它们的 content URL 只来自 `references/docs-manifest.json`。
  不要猜一个不在 manifest 里的 `/docs/<slug>` 地址 —— slug 不总是能直觉猜到(比如 CLI 的页面在
  `cli/...` 下, IDE 的页面在 `ide/...` 下)。
- **小批次循环, 上限 9 页。** 先抓 1–3 页, 判断够不够, 不够再抓。到 9 页还不够就先问用户。
- **`content_url` 返回 404, 说明 manifest 过期了。** 上游把页面改名或删掉了。告诉用户跑
  `/antigravity-docs-index-builder` 刷新, 而不是去猜新地址。
- **直接引用 `content_url`。** 它就是人能直接打开的地址, 引用时不需要转换。
- **原样传达文档内容。** 不要激进地和已有知识融合 —— 用户要的是当前权威行为, 不是一份综述。
