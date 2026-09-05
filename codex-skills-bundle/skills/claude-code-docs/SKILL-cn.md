> 这是 [SKILL.md](SKILL.md) 的中文翻译, 只供人阅读。**英文版是权威版本**, 两者不一致时以英文版为准,
> 并把这份翻译改过来。维护是单向的: 改了英文版就回来同步这份, 反过来不成立。
>
> Claude Code 实际加载的是 `SKILL.md`, 不是这一份。

---

name: claude-code-docs
description: 查阅权威、最新的 Claude Code 官方文档, 覆盖 CLI、settings、权限、hooks、MCP、skills、
plugins 与 marketplace、subagents、agent teams、workflows、worktrees、sandbox、channels、
routines、定时任务、桌面端 / Web / 移动端 / Slack / IDE 各使用面、code review、Agent SDK
(Python 与 TypeScript)、网关、Bedrock/Vertex/Foundry 部署、企业管理与故障排查。当用户问某个
Claude Code 功能怎么用、某个配置字段是什么含义、hooks/MCP/skills/subagents/plugins 怎么配,
或者在排查 Claude Code 的报错和异常行为, 又或者你需要引用当前官方文档而不是训练时的记忆时使用。
中文触发语包括: 查一下 Claude Code 文档、Claude Code 官方文档怎么说、Claude Code 的
hooks/MCP/skills/权限/配置 怎么用。
argument-hint: [主题或文档标题]
allowed-tools: WebFetch

---

# Claude Code Docs

按需从官方文档回答 Claude Code 的问题: 用 WebFetch 抓取 `llms.txt` 索引(一份扁平的全站页面清单,
每条都带一句真实描述), 挑出匹配的页面, 再把这些页面按原始 Markdown 抓下来。任何时候都优先用这个
Skill, 而不是凭记忆回答 —— 文档变化的速度快过训练数据。

如果用户传了参数 (`$ARGUMENTS`), 就把它当作要查的主题; 否则从对话里推断主题。

## 什么时候用这个 Skill

只要问题是关于 Claude Code 本身, 或落在它的文档范围内, 就用它:

- **CLI 与会话层面** —— slash 命令、CLI 参数、交互模式、快捷键、状态栏、输出风格、全屏、语音输入、
  会话管理、checkpointing、worktrees
- **配置** —— settings、环境变量、权限与权限模式、CLAUDE.md 记忆、模型配置、`.claude` 目录、
  服务端托管的 settings
- **扩展能力** —— hooks、MCP、skills、plugins、plugin marketplace、subagents、agent teams、
  dynamic workflows、channels、routines、定时任务、computer use
- **Agent SDK**(Python 与 TypeScript)—— agent loop、会话、streaming、自定义工具、hooks、权限、
  结构化输出、tool search、托管、可观测性
- **各个使用面与集成** —— 桌面端、Web、移动端、Slack、Chrome、VS Code、JetBrains、devcontainer、
  GitHub Actions、GitLab CI/CD
- **企业与部署** —— 管理员配置、Bedrock、Google Cloud、Microsoft Foundry、LLM 网关、
  Claude apps gateway、网络配置、analytics、成本、安全、数据使用
- **参考手册与故障排查** —— 工具参考、错误码参考、术语表、changelog、每周的 `What's new` 页面、
  troubleshooting

不在范围内: **Anthropic API / Anthropic SDK 本身**(Messages API、定价、模型 id)。那些走
`claude-api` Skill。

## 这个站点是怎么工作的

实测于 2026-07-30; 完整事实记录在 [references/mechanism.md](references/mechanism.md)。

- **索引**: `https://code.claude.com/docs/llms.txt` —— 38,847 字节(约 9,700 tokens), 174 条,
  100% 带真实描述。只有一个扁平的 `## Docs` 分节, 没有子分节可以用来路由, 所以描述是唯一的分诊信号。
- **内容**: 索引里的 URL 本身就以 `.md` 结尾, 直接返回原始 Markdown。实测 `hooks.md` 是 242,078
  字节, 而 HTML 版是 2,423,751 字节, 便宜约 90%。不存在另外一份需要拼出来的 `.md` twin —— 索引给
  的 URL 直接原样用。
- **各页体积差 25 倍**: 实测从 10,628 字节(`troubleshooting.md`)到 272,484 字节(`settings.md`);
  `hooks.md` 242,078 字节, `cli-reference.md` 104,140 字节, `mcp.md` 80,866 字节, `overview.md`
  16,445 字节。给 WebFetch 的问题要具体 —— 在 270 KB 的页面上写一个笼统的 prompt, 大半次抓取就浪费了。
- **坑 —— `llms-full.txt`**: `https://code.claude.com/docs/llms-full.txt` 有 6,556,407 字节
  (约 164 万 tokens)。那是全文 dump 不是索引。绝对不要抓。

## 流程

### 1. 读索引

```
WebFetch url=https://code.claude.com/docs/llms.txt
        prompt="Return the raw markdown. I need every `- [Title](URL): description` line unmodified."
```

每一条的格式是 `- [Title](https://code.claude.com/docs/en/<slug>.md): description`。

这一步不能跳过, 哪怕你觉得自己记得正确的 URL。slug 会改名, 页面每周新增; 索引才是真相来源。

### 2. 挑出正确的页面

按**描述**(冒号后面那段文字)匹配, 而不只是标题。然后:

- 一批只挑 **1–3 页**, 不要更多。索引是用来分诊的, 不是用来批量灌数据的。
- 一个具体功能的问题(「hooks 怎么工作?」)→ 一页。
- 跨概念的问题(「skills 和 subagents 是什么关系?」)→ 相关页面各抓一份。
- 注意有些主题散在几个地方 —— 比如 `hooks.md`(参考手册)、`hooks-guide.md`(教程)、
  `agent-sdk/hooks.md`(SDK 版)。挑对用户真正问的那一份。

### 3. 如果索引里看起来没有匹配项

**不要**就此断定这个主题没有文档。按顺序升级:

1. **换同义词扩大范围。** 文档用的词往往不是用户用的词。本索引实测: 「resume」在标题里出现 **0 次**,
   却在描述里出现 5 次, 它在 `sessions.md`(*Manage sessions*)下面。同类情况:
   「auto-approve」→ *permission modes*; 「parallel checkouts」→ *worktrees*;
   「cron」→ *scheduled tasks* / *routines*。
2. **非英文查询先翻成英文。** 这份索引只有英文。实测: 中文查询 `钩子` 命中 **0** 条, 而 `hook` 命中
   17 条 —— 非英文查不到, 完全说明不了覆盖情况。绝不要根据一次非英文搜索就回答「没有文档」。
3. **问一句「最近有什么变化?」** —— `whats-new/index.md` 加上 18 个每周的 `whats-new/2026-wNN.md`
   页面, 覆盖了那些老的、更稳定的页面还没提到的新功能。
4. **到这一步之后**才可以说文档里没有, 并且要说清楚查过哪些词。

### 4. 抓取这一批

对每个选中的 URL, 原样使用索引里给的地址(它已经以 `.md` 结尾):

```
WebFetch url=<索引里的 URL>
        prompt="<一个能捕捉用户真实需求的问题, 而不是「总结这一页」>"
```

### 5. 评估, 然后回答或继续循环

每抓完一批, 判断这些页面是否真的回答了问题:

- **够了** → 基于抓回来的内容作答。陈述不那么显然的事实时附上文档页(标题 + URL), 方便用户核对。
- **不够**(答案在你还没读的页面上, 或某一页指向了另一页)→ 回到第 2 步, 再挑 1–3 页继续抓。
- 一直循环, **默认上限是全过程 9 页**。
- **读满 9 页还是不够** → 停下来。告诉用户你读了什么、还缺什么、要不要继续。不要偷偷突破上限, 也不要
  用猜测把答案凑齐。

## 上下文开销

| 步骤 | 开销 | 说明 |
| :--- | :--- | :--- |
| 索引 | 约 9,700 tokens | 每个问题一次; 同一轮里的多个批次复用它 |
| 页面 | 原始约 3k–68k tokens | 每批 1–3 页; WebFetch 会先做压缩再进上下文 |

典型的一个问题: 索引 + 1–2 页。只有当对话转向不相关的主题时才重新读索引 —— 批次之间不要重读。

## 规则

- **绝不编造文档 URL。** 索引里没有的页面就是不存在 —— 如实说, 不要拼一个 slug。索引里的 URL 返回
  404 说明索引过期了; 对这个 Skill 重新跑一次 `/docs-skill-builder check`。
- **绝不抓 `llms-full.txt`**(6.5 MB / 约 164 万 tokens)。
- **小批次循环, 上限 9 页。** 先抓 1–3 页, 判断够不够, 不够再抓。不要把整份索引啃一遍, 也不要用编造
  填补空缺。
- **守住范围。** 这个 Skill 只覆盖 `code.claude.com/docs/*`。Anthropic API 走 `claude-api`。
- **原样传达文档内容。** 不要激进地和已有知识融合 —— 用户要的是当前权威行为, 不是一份综述。
