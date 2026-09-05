> 这是 [README.md](README.md) 的中文翻译, 只供人阅读。**英文版是权威版本**, 两者不一致时以英文版为准,
> 并把这份翻译改过来。维护是单向的: 改了英文版就回来同步这份, 反过来不成立。

# Antigravity 文档索引 Skill

这个 Skill 让 agent 在需要了解 Google Antigravity 时,不再依赖训练时记住的、可能已经过期的知识,而是去读官方文档的最新版本。Antigravity 是个很新的产品,IDE、CLI、SDK、skills、MCP、权限模型都在快速变化,靠记忆回答很容易出错。这个 Skill 的作用就是把「先查官方文档、再回答」这件事固化成一个稳定流程。

它和 `claude-code-docs`、`codex-docs` 目标一致,但**取文档的机制不一样**——这是理解它的关键,下面会讲清楚。

---

## 1. 它解决什么问题

假设你要写一段关于 Antigravity 异步 subagent 的说明,或者在配置 CLI、MCP 时遇到报错,又或者想知道某个 agent 设置到底是什么含义。这些答案都在官方文档里,而且随时会更新。凭印象回答,你给出的命令、字段、slug 很可能已经被改掉了。

这个 Skill 覆盖 Antigravity 的全部文档范围:Antigravity 2.0(agentic IDE)、Antigravity CLI、SDK、以及 agents/subagents、models、skills、rules/workflows、hooks、MCP、browser、settings、enterprise、migration、FAQ。

---

## 2. 怎么用

大多数时候你什么都不用做。当你的任务依赖 Antigravity 的官方信息时,直接触发这个 Skill,它会自己完成查询。你可以把一个具体话题作为参数传进去(比如 `subagents` 或 `cli install`),也可以什么都不传,让它从当前对话里推断主题。

它的输出会落在真实文档内容上,并在陈述不那么显然的事实时附上文档标题和页面 URL,方便你回去核对。你从它这里拿到的不是一段综合了旧知识的复述,而是当前官方文档怎么说,它就怎么传达。

一句话总结前半段:只要你要做的事情依赖 Antigravity 的官方最新信息,参考这个 Skill 就够了。

---

## 3. 它和另外两个 docs skill 的关键区别

Codex 和 Claude Code 的文档页都有 `.md` 孪生页,所以那两个 Skill 直接抓页面 URL 就能拿到正文。Antigravity 以前不行——文档页是纯前端渲染的 SPA,抓页面 URL 只会得到一个空壳,得靠单独的 asset 地址取正文。**2026-07 前后 Antigravity 把官网重写成了服务端渲染**,现在 `content_url` 就是文档页本身(`https://antigravity.google/docs/<slug>`),直接 WebFetch 就能拿到正文,和 Codex/Claude Code 那两个 Skill 已经趋同。

那为什么还留着一个本地 manifest,不干脆现查 `llms.txt`?因为 `llms.txt` 自带的每页描述是套话("Learn about X"),没法拿来做 triage。配套的 `antigravity-docs-index-builder` Skill 会预先把每一页抓一遍,提炼出真正有信息量的首段描述、以及比 `llms.txt` 更细的面包屑分组(比如 `Antigravity 2.0 / Customizations / Skills`),一次性写进 manifest——这正是"按 title+description 匹配挑页面"这一步能有效工作的前提。

- **索引是一个本地文件** `references/docs-manifest.json`,由配套的 `antigravity-docs-index-builder` Skill 生成。这个 Skill 直接 `Read` 它,**不去抓 `llms.txt`,也不爬网站**。
- **正文就是页面本身**(manifest 每条里的 `content_url`,即 `https://antigravity.google/docs/<slug>`)。直接 WebFetch 它。

所以它的流程是:**读本地 manifest → 挑页面 → WebFetch 对应的 `content_url`**。

> **一段值得知道的历史:** 2026-07-25 到 07-30 之间, 上面这段只在设计上成立。builder 抓描述的正则找的
> 是一个在页面 HTML 里已经不存在的 class, 而且会静默 fallback, 所以 81 条描述全是 `Learn about X.`
> 套话, 实际分诊只靠 title 加面包屑。已在 `antigravity-docs-index-builder` 0.2.2 修复, 并于
> 2026-07-31 重新生成: 现在覆盖率 81/81, 套话描述 0 条。`references/mechanism.md` 里有实测的前后对比。

---

## 4. 工作流程是怎么设计的

Skill 的核心是一个「小批次 + 评估 + 循环」的过程。

第一步是读 manifest。它 `Read` 那个本地 JSON,里面有 `_meta`(生成日期、源 `llms.txt` 的 hash)和 `pages`,每条是 `{section, slug, title, description, content_url}`。如果文件不存在,就提示用户先跑 `/antigravity-docs-index-builder`,而不是自己去猜 URL。

第二步是挑页面。拿用户的问题去和每条的 `title + description` 匹配,而不是只看 slug。一个批次只挑一到三页;具体功能问题对应一页;跨概念问题才分别挑多页;如果 manifest 里没有明显匹配的,就如实说没有(manifest 是完整的文档页清单,查不到要么确实不存在,要么 manifest 过期了,可以建议重建),绝不凭空造一个 `content_url`。

第三步是抓这一批。对每个选中的页面,WebFetch 它的 `content_url`(那个 `https://antigravity.google/docs/<slug>` 地址),prompt 写成能捕捉用户真实需求的问题,而不是笼统的「总结这一页」。

第四步是评估,然后决定回答还是继续循环。抓完一批,先判断够不够回答。够了就作答并附出处(引用 `content_url`,就是那个人能打开的页面地址);不够就回到第二步再挑一到三页。循环直到能回答,但最多读九页。读满九页还不够,就停下来,如实告诉用户已读了哪些、还缺什么,并询问要不要继续——不偷偷突破上限,也不用猜测凑答案。

```mermaid
flowchart TD
    A[用户提问] --> B[Read 本地 docs-manifest.json]
    B --> C[按 title+description 匹配挑 1 到 3 页]
    C --> D[WebFetch 对应的 docs/slug 页面]
    D --> E{信息够回答了吗?}
    E -->|够| F[基于真实文档作答, 引用 docs/slug 页面]
    E -->|不够, 累计 < 9 页| C
    E -->|不够, 已达 9 页上限| G[如实说明已读与欠缺, 询问是否继续]
    G -->|用户同意| C
    G -->|用户不再需要| F
```

---

## 5. 几条硬规则背后的道理

**读 manifest,不要爬站。** 页面清单和 `content_url` 只能来自 `references/docs-manifest.json`。不要去猜不在 manifest 里的 `/docs/<slug>` 地址——slug 不总是直觉能猜到的(比如 CLI 页面在 `cli/...` 下,IDE 页面在 `ide/...` 下)。这条是这个 Skill 可靠性的来源。

**小批次循环,九页封顶。** 一次抓一到三页,评估够不够,不够再抓,到九页还不够就先问用户。理由和另外两个 docs skill 一样:一次抓太多稀释信号,一批又常常不够,循环 + 上限在两者之间取平衡,而"到顶就问"是把"继续深挖还是打住"的判断交回用户。

**`content_url` 抓出来 404,意味着 manifest 过期了。** 说明上游把页面改名或删了。这时应该提示用户跑 `/antigravity-docs-index-builder` 刷新,而不是去猜新地址。这也正是"索引"和"消费"分成两个 Skill 的价值:内容层只管用,过期了交给构建器层去修。

**尽量原样传达文档内容,不要激进地和旧知识融合。** 用户要的是当前权威行为,而不是一份掺了过时假设的综述。

---

## 6. 人类怎么手动复现(以及一个容易踩的 gzip 陷阱)

如果你想自己拿终端验证一下某个 `content_url` 到底能不能抓、内容长什么样,直接 `curl` 大概率会踩坑——**裸 `curl` 拿到的不是 Markdown,甚至看起来不是文本,而是一坨二进制/乱码**,原因和"抓不抓得到"无关,是另外两件事叠在一起:

1. **返回的本来就是 HTML,不是 Markdown。** `https://antigravity.google/docs/<slug>` 这类地址返回的是服务端渲染好的网页源码(一堆 `<div class="docs-main-content">`、`<script>`、埋点代码),不是纯 Markdown 文件。你在这个 Skill 的回答里看到的"Markdown 正文",是 WebFetch 工具抓到 HTML 之后**自己转换**出来的,服务器并不提供现成的 `.md` 文件——这也是为什么第 3 节说"不要去猜 `/assets/docs/...` 地址",那条路已经不存在了,唯一能抓的就是这个会返回 HTML 的页面 URL。
2. **这台服务器不管你要不要,一律强制 gzip 压缩。** 哪怕你在请求头里明确写 `Accept-Encoding: identity`(意思是"别压缩"),它照样压缩返回。而 `curl` 默认既不会主动请求 gzip,也不会自动解压——所以裸 `curl url` 拿到的就是原始 gzip 字节,终端把它当文本打印出来,自然是乱码;这正是你看到的"一堆 binary/像 JS"的来源。

正确的手动验证姿势,分两步:

```bash
# 第一步:确认地址活着、内容是不是预期的 HTML(注意 --compressed,少了这个 flag 就是乱码)
curl -sI --compressed "https://antigravity.google/docs/rules-workflows"   # 看状态码是不是 200
curl -s --compressed "https://antigravity.google/docs/rules-workflows" | head -c 500   # 看前几百字节像不像 HTML

# 第二步:想看转换成可读文本之后的样子,直接用浏览器打开这个 URL 最省事;
# 或者用 antigravity-docs-index-builder/scripts/build_manifest.py 里同款的正则,粗提一下正文段落
curl -s --compressed "https://antigravity.google/docs/rules-workflows" | \
  grep -oE '<div class="caption template-content-paragraph"[^>]*>.*?</div>'
```

`antigravity-docs-index-builder` 的 `build_manifest.py` 里就踩过并处理过这个 gzip 陷阱——它的 `fetch()` 函数会检测响应开头是不是 gzip 魔数字节(`\x1f\x8b`),是的话手动用 Python 的 `gzip` 模块解开,而不是依赖 `urllib`/`curl` 的默认行为。你自己手动验证时,记得 `curl` 要加 `--compressed`,别的语言/工具同理要显式做 gzip 解压这一步,否则会误以为页面"抓不到"或者"返回的是垃圾数据"。

---

理解了这六节,你就明白这个 Skill 为什么把索引做成本地文件、为什么不直接现查 `llms.txt`、为什么把刷新的活儿甩给另一个构建器 Skill。它和 `antigravity-docs-index-builder` 是一对:构建器负责"文档地图始终新鲜、描述始终有信息量",这个 Skill 负责"基于地图给出可靠答案"。
