> 这是 [mechanism.md](mechanism.md) 的中文翻译, 只供人阅读。**英文版是权威版本**, 两者不一致时以英文版为准,
> 并把这份翻译改过来。维护是单向的: 改了英文版就回来同步这份, 反过来不成立。

# antigravity-docs — 机制日志

这个 Skill 用什么方式读 Google Antigravity 的官方文档, 以及为什么这么设计。最新的条目在最上面, 顶部
那条描述的就是当前的机制。条目只追加, 不改写。

## 2026-07-31 — build

**结论。** 下面那条记录的缺陷已修复。机制没有变化 —— 仍然是对本地 manifest 的 T5、内容仍然是 C1 ——
但 manifest 的描述列第一次带上了真实文本, 所以分诊从一个可用信号变成了两个。

**变了什么。** `antigravity-docs-index-builder` 0.2.2 把已经失效的 `template-content-paragraph`
选择器换成了「正文第一个 `<h1>` 之后第一个够长的 `<p>`」, 并新增了 `Scrape coverage` 报告, 让「选择器
不再匹配」这件事无法再无声地降级 manifest。用 `--force` 重新生成: 81 页(没有新增也没有删除),
21,934 字节 → 33,005 字节, 覆盖率 **section / title / description 全部 81/81**, 无警告。套话描述从
81/81 降到 **0/81**; 描述长度从中位数 3 个词(最长 6)变成中位数 21(最长 48)。标题和面包屑里残留的
HTML 实体也没了 —— `clean()` 现在会做 unescape, 也不再把被剥掉标签两侧的词粘在一起。

**验收测试, 新旧 manifest 并排跑。** 简单查询 `hooks?`: 2 → 5 条。真正体现修复效果的是同义词错配这几
组, 因为这些词在任何标题和面包屑里都不出现: `isolation` 0 → 1(`cli/sandbox`), `parallel` 0 → 2
(`subagents`、`cli/subagents`), `open standard` 0 → 6(`mcp`、`skills`、`cli/mcp`、`sdk/mcp` 等)。
两个诚实的负面结果: `12,000`(写在 `rules-workflows` 正文里的一个限制)在新旧 manifest 里都命中 0 ——
索引带的是首段, 不是全文, 这是设计如此; 非英文查询 `钩子` 在新旧里也都命中 0, 对一份英文索引来说这是
预期之内, 但它的意义比看上去大, 见下条。

**新暴露出来的缺口, 未修。** `SKILL.md` 里没有召回升级阶梯: 第 2 步从「manifest 里没有明显匹配」直接
跳到「如实说没有」。既没有「换同义词再搜一遍」, 也没有「非英文查询先翻成英文」。上面 `钩子` → 0 的结果
正是这条阶梯要防的那种无声失败, 而同门的 `claude-code-docs` 在 0.2.0 里就是因为同样的实测结果加上了
它。这次没动, 因为本轮范围只到 manifest; 但它是这个 Skill 目前还剩下的最大一项改进空间。

## 2026-07-30 — 补录(reconstruction)

**结论。** 这一条是**倒推补录的, 不是实测**。这个 Skill 早于「机制日志」这项要求, 交付时就没有;
而且 owner 明确要求写这个文件时不要重新探测、不要更新这个 Skill。所以下面的设计是从已交付的
`SKILL.md`、`README-cn.md`、`CHANGELOG.md` 里还原出来的, 其中所有关于线上站点的数字都继承自
2026-07-25 和 2026-07-29 那两次 0.2.1/0.2.2 的工作, 今天没有重新核实。本条目里唯一实测过的数字,
是从已提交的 manifest 里读出来的那些 —— 那不需要联网。下一次真正的 `check` 必须跑 probe, 并追加一条
有实测支撑的条目。

**这个站点是怎么读的。** 索引是**本地的**: `references/docs-manifest.json`, 21,934 字节, 由另一个
`antigravity-docs-index-builder` Skill 生成。文档 Skill 直接 `Read` 它 —— 不抓 `llms.txt`, 也不爬站。
文件里有 `_meta`(生成日期、源 `llms.txt` 的 SHA-256、`content_url_template`、页面数)和 81 条
`pages`, 每条是 `{section, slug, title, description, content_url}`。`section` 是完整的面包屑路径
(`Antigravity 2.0 / Customizations / Skills`), 而且每页唯一 —— 81 个值全都不重复, 所以它是逐页的
标签, 不是可以用来路由的分组。正文就是文档页本身: `content_url` 是
`https://antigravity.google/docs/<slug>`, 直接 WebFetch, 每批 1–3 页, 上限 9 页。从 0.2.1 起站点是
服务端渲染的 Astro 应用; 在那之前是纯前端渲染的 SPA, 页面 URL 只返回一个空壳, 这就是 0.1.1 要去抓
单独的 `/assets/docs/….md` 孪生页的原因。那个孪生页现在已经不存在了。这台服务器还会无条件 gzip,
即使请求头写了 `Accept-Encoding: identity` 也照压, 所以手动 `curl` 验证时必须加 `--compressed`,
否则拿到的看起来就是一堆二进制乱码。

**为什么是这个设计。** 索引分层 **T5**(预构建 manifest), 内容分层 **C1**(纯 HTML, 只能用 WebFetch,
不能 curl)。T5 是 catalog 里的最后手段, 在这里成立只靠一个理由: `antigravity.google/llms.txt` 对每
一页的描述都是「Learn about X」, 所以「按描述分诊」在官方索引上根本跑不起来。manifest 是被认可的、用
来换取真实描述的做法, 而且它带有重建路径(`/antigravity-docs-index-builder`), 不是靠手工打补丁维护
的。C1 则是页面是 HTML 的直接后果: WebFetch 会先把它压成 Markdown 再进上下文。

**已知缺陷 —— 两个分诊信号里有一个是空的, 原因是一条正则过期了。** 在已提交的 manifest 里实测:
**81 条描述全部仍然是 `Learn about <X>.` 的形态**, 中位数 3 个词, 最长 6 个词, 和 `llms.txt` 的
fallback 一模一样。同日追到了源头: builder 的 `DESC_RE` 找的是
`<div class="caption template-content-paragraph">`, 而这个 class 在当前页面 HTML 里**出现 0 次**
(实测抓取 `/docs/rules-workflows` 验证过); 首段现在是紧跟在 `<h1>` 后面的一个普通 `<p>`。另外两处
抓取没有受影响 —— `breadcrumb-list` 和 `<h1>` 都仍然匹配, 这正是 manifest 的面包屑既正确又细致的
原因。这个失败是无声的: `build_manifest.py` 只在 `fetch()` 抛异常时才把 fallback 记进
`scrape_failures`, 而一条匹配不到任何东西的正则会静默 fallback、不产生任何警告, 所以构建过程报告的
是成功。

**这并不推翻 T5。** 光是面包屑相对官方索引就是一次很大的提升: `llms.txt` 只给了 9 个粗分组
(Home、Antigravity 2.0、Antigravity CLI、SDK、IDE、Migration、Enterprise、Plans、FAQ), 而 manifest
带的是逐页路径, 比如 `Antigravity 2.0 / Customizations / Skills` 和
`Antigravity CLI / Commands / Resume (/resume)`。按 title 加面包屑分诊是能工作的, Skill 本身是可用
的。丢掉的是第二个独立信号 —— 也就是当一个查询的措辞既不匹配标题也不匹配面包屑时, 本来该由它兜住。
按「不更新」的要求原样保留; 要修的话是在 `antigravity-docs-index-builder` 里改一条正则, 不在这个
Skill 里, 而且那个静默 fallback 的行为值得一并修掉 —— 正是它让这件事没被发现。

**什么情况下这个判断会被推翻。** 真正抓取的描述进入 manifest → T5 的正当性才和文档里写的一致。
Antigravity 发布带可用描述的 `llms.txt` → 直接扔掉 manifest 和构建器 Skill, 改成对线上索引做 T0 或
T1, 这是一次很大的维护成本削减。页面 URL 出现 `.md` 孪生页 → C1 变 C0。站点退回前端渲染 → C1 直接失
效, 那套 asset 孪生页的绕法要回来。任何 `content_url` 返回 404 → 说明 manifest 过期了, 而不是 URL
写错了; 应该重建而不是猜。

**重建时必须保留的东西。** `SKILL.md` 里「Why this skill works differently from
claude-code-docs / codex-docs」那一节 —— 那是唯一在 agent 读取时向它解释 T5 选择的地方。指向
`/antigravity-docs-index-builder` 的「manifest 过期就去那里修」这条路径, 它是阻止 agent 自己编 slug
的关键。README 第 6 节里写的 gzip 陷阱: 这东西在文档站上看不出来, 重新踩一遍要花一个小时。

**验收测试。** 没有跑。这一轮是在「明确不更新」的前提下补文件, 声称测试通过就等于声称跑过一个从未执行
的测试。
