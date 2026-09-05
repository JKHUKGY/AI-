> 这是 [SKILL.md](SKILL.md) 的中文翻译, 只供人阅读。**英文版是权威版本**, 两者不一致时以英文版为准,
> 并把这份翻译改过来。维护是单向的: 改了英文版就回来同步这份, 反过来不成立。
>
> Claude Code 实际加载的是 `SKILL.md`, 不是这一份。

---

name: codex-docs
description: 查阅权威、最新的 OpenAI Codex 官方文档, 覆盖 CLI、IDE 扩展、Codex app、cloud、
subagents、skills、plugins 与 marketplace、MCP、sandbox、配置、企业版和各类集成。当用户问某个
Codex 功能怎么用、某个配置字段是什么含义、CLI/IDE/app/cloud/skills/plugins/MCP 怎么配, 或者在排查
Codex 的报错和异常行为, 又或者你需要引用当前官方文档而不是训练时的记忆时使用。
argument-hint: [主题或文档标题]
allowed-tools: WebFetch

---

# Codex Docs

按需惰性加载 OpenAI Codex 官方文档: 读开发者站的索引 `https://developers.openai.com/llms.txt`,
挑出最相关的一到几页, 再抓取它们。任何时候都优先用这个 Skill, 而不是凭记忆回答 —— 文档变得很频繁。

如果用户传了参数 (`$ARGUMENTS`), 就把它当作要查的主题; 否则从对话里推断主题。

## 什么时候用这个 Skill

只要问题是关于 Codex 本身, 或落在它的文档范围内, 就用它:

- Codex CLI: 安装、slash 命令、命令行选项、功能、配置、sandbox、认证
- Codex IDE 扩展、ChatGPT 桌面应用(automations、commands、worktrees、computer use、Chrome 扩展),
  以及 Codex cloud / web
- 概念: sandbox、定制化、subagents、skills、plugins 与 marketplace、MCP、网络安全
- 企业版配置、集成(GitHub、Linear、Slack)、Amazon Bedrock、app-server 协议、故障排查

如果问题是关于更广的 **OpenAI API / OpenAI SDK**(而不是 Codex 这个编码 agent), 那属于
`developers.openai.com/api` 的范围, 不在这个 Skill 里。

## 文档到底在哪

OpenAI 把 Codex 文档正文搬到了新域名, 而旧的入口以一种会让这个 Skill 无声失灵的方式坏掉了。有三件事
必须记住:

1. **`https://developers.openai.com/codex/llms.txt` 已经死了。** 它会 308 跳到
   `https://learn.chatgpt.com/docs/llms.txt`, 而那个地址返回 404。`codex/llms-full.txt` 同理。
   开发者站自己的根索引至今还挂着那个坏掉的 `codex/llms.txt` 链接 —— 忽略它。
2. **能用的索引是上一级的 `https://developers.openai.com/llms.txt`。** 它把整张 Codex 地图并了进来,
   放在 `## Codex — <主题>` 这些分节里, 格式还是老的 `- [Title](URL): description`。
3. **正文页会跨域名跳转。** `https://developers.openai.com/codex/<slug>.md` 会 308 跳到
   `https://learn.chatgpt.com/docs/<slug>.md`。WebFetch **不**跟随跨域名跳转, 而是把跳转目标返回给
   你。所以抓一个 Codex 页面通常要两次 WebFetch。见第 3 步。

新旧 slug 不总是简单换域名(`codex/skills.md` 落在 `docs/build-skills.md`,
`codex/config-reference.md` 落在 `docs/config-file/config-reference.md`), 这是另一个「绝对不要自己
拼 `learn.chatgpt.com` 地址」的理由。让跳转告诉你。

插件开发相关的页面是例外: 它们在 `https://developers.openai.com/plugins/<path>.md`, 落在
`## Plugins — <主题>` 分节下, 直连可达, 不跳转。

## 流程

### 1. 读索引

```
WebFetch url=https://developers.openai.com/llms.txt
        prompt="Return the raw markdown of every section whose header starts with '## Codex —' or '## Plugins —'. I need each `- [Title](URL): description` line unmodified, including the section headers."
```

这份 hub 索引约 840 行, 覆盖好几条产品线。Codex 落在 `## Codex — <主题>` 这批分节里, 插件开发落在
`## Plugins — <主题>` 里; 其余的(OpenAI API、Ads、Workspace Agents、Agentic Commerce)不在范围内,
这就是上面那个 prompt 只收窄到这两族的原因, 而不是把整个文件拉下来。

在 Codex 和 Plugins 这两族之内, 一次性把它们的条目全部载入, 直接在里面搜。在你还没看过条目之前, 不要
再按主题标题做二次预筛 —— 按主题分组只是页面的排版方式, 不构成跳过某些部分的理由。

### 2. 挑出正确的页面

按**描述**(冒号后面那段文字)匹配用户的问题, 而不只是标题。然后:

- 一批只挑 **1–3 页**, 不要更多。索引是用来分诊的, 不是用来批量灌数据的。
- 一个具体功能的问题(「Codex 的 slash 命令怎么用?」)→ 一页。
- 跨概念的问题(「skills 和 subagents 是什么关系?」)→ 相关页面各抓一份。
- 索引里没有明显匹配的 → 如实说。不要猜 URL。

### 3. 抓取这一批

对每个选中的 URL:

```
WebFetch url=<索引里的 URL>
        prompt="<一个能捕捉用户真实需求的问题, 而不是「总结这一页」>"
```

`developers.openai.com/codex/...` 的 URL 会返回 `REDIRECT DETECTED`, 指向
`learn.chatgpt.com/docs/...`。这是预期行为, 不是报错。用那个跳转地址和同样的 prompt 再调一次
WebFetch。这一对算作 9 页上限里的**一页**, 引用时写实际提供内容的 `learn.chatgpt.com` 地址。

有少数索引条目在上游就已经失效, 跳转之后仍然 404(约 137 条 Codex 条目里有 5 条左右, 例如
`codex/overview.md` 和 `codex/resources.md`)。碰到就当作「这一页不存在了」, 换一条, 不要试图手工修
slug。

### 4. 评估, 然后回答或继续循环

每抓完一批, 判断这些页面是否真的回答了问题:

- **够了** → 基于抓回来的内容作答。陈述不那么显然的事实时附上文档页(标题 + URL), 方便用户核对。
- **不够**(答案在你还没读的页面上, 或某一页指向了另一页)→ 回到第 2 步, 从索引里再挑 1–3 页继续抓。
- 一直循环到能回答为止, **默认上限是全过程 9 页**。
- **读满 9 页还是不够** → 停下来。告诉用户你读了什么、还缺什么、要不要继续。不要偷偷突破上限, 也不要
  用猜测把答案凑齐。

## 规则

- **绝不编造文档 URL。** 索引里没有的页面就是不存在 —— 如实说, 不要拼一个 slug。这条对
  `learn.chatgpt.com` 的地址加倍适用: 只能通过跟随跳转到达, 绝不能自己改写域名拼出来。
- **不要跳过第 1 步**, 哪怕你觉得自己记得正确的 URL。slug 会改名; 索引才是真相来源。
- **用 `developers.openai.com/llms.txt`, 不要用 `codex/llms.txt`。** Codex 专属索引经过跳转后返回
  404。如果你发现自己在盯着一个 404 的索引, 原因就在这里。
- **小批次循环, 上限 9 页。** 先抓 1–3 页, 判断够不够, 不够再抓。一对跳转算一页。读满 9 页还不够就
  先问用户 —— 不要把整份索引啃一遍, 也不要用编造填补空缺。
- **守住范围。** 这个 Skill 覆盖 Codex 产品族: hub 索引里的 `## Codex —` 和 `## Plugins —` 两族,
  以及它们当前落在的任何域名(`developers.openai.com/codex/*`、`developers.openai.com/plugins/*`,
  和它们的 `learn.chatgpt.com/docs/*` 跳转目标)。更广的 OpenAI API 请指向
  `developers.openai.com/api`。
- **引用实际提供内容的那个 URL。** 跨域名跳转之后, 那是 `learn.chatgpt.com/docs/<slug>.md` 的形态,
  而不是你一开始用的 `developers.openai.com` 地址。
- **原样传达文档内容。** 不要激进地和已有知识融合 —— 用户要的是当前权威行为, 不是一份综述。
