# 文档 Skill 构建器

> 这是 [README.md](README.md) 的中文翻译。**英文版是权威版本**, 两者不一致时以英文版为准, 并把翻译改过来。

这个 Skill 是一个**元工具**: 你给它一个厂商的文档站, 它产出一个 `xxx-docs` Skill —— 也就是 `claude-code-docs`、`codex-docs`、`antigravity-docs` 那一类"按需去查官方文档"的技能。

```
/docs-skill-builder build .claude/skills/databricks-docs for https://docs.databricks.com
/docs-skill-builder check  .claude/skills/databricks-docs
```

目标是: 以后不再需要为每个新文档站开一轮长对话去摸索机制。摸索的过程被固化成了一个探测脚本加两张决策表。

---

## 1. 它到底在解决什么问题

一个 `xxx-docs` Skill 本质是个 lazy loader, 好坏只看一个比值: **每花一个 token 能找到多少答案**。这里面有三个互相拉扯的力:

- **常驻成本** —— 索引要小, 但太小了 agent 就得盲选分支;
- **召回率** —— 想让 agent 看全, 但看全意味着一次性烧掉几万 token;
- **新鲜度** —— 全部查询时现算最准, 但请求数会涨。

关键结论是: **层级不是免费的**。每加一层就是一次路由决策, 而路由决策是相乘的。两层各 90% 的正确率, 端到端只剩 81%; 三层只剩 73%。更糟的是第一层选错通常无法挽回 —— agent 根本看不到含答案的那个分支, 而且它不知道自己漏了。

所以规则不是"多加几层省 token", 而是:

> 只有当上一层带着**足够的描述**能支撑正确路由时才加这一层, 并且永远保留一个**平的兜底通道**, 可以一次搜遍全部条目。

产出的 `docs_query.py` 就是这个形状: `section` 走层级, `search` 无视层级扫全部。路由选错只多花一条命令, 不会丢答案。

还有一条推论比听上去更重要: **优先用站点自己的层级结构**。`llms.txt` 里的 `##` 分节、面包屑、区域落地页 —— 这些是厂商在维护的, 永远是最新的。自己发明一套分类, 从写下的那一刻就开始烂。

---

## 2. 三条硬性偏好

这三条已经写进 `SKILL.md` 的 Standing principles, 每次构建都会生效:

1. **只描述规范, 不物化清单。** 能用一条规则("URL 后面加 `.md`")表达的, 绝不落成一份抓下来的页面清单。清单是第二个真相来源, 只会越来越错。
2. **用推理换召回, 不用产物换召回。** 查询时做同义词扩展、分节兜底, 好过预先生成一份会过期的富化索引。
3. **爬虫是下下策。** 只有当散文描述低于 30%、并且验收测试**实测**失败、并且没有开源文档仓库可用时才考虑, 而且必须带上重建路径。缓存正文进仓库则是永远禁止的 —— 正文变得最快。

请求数也被约束住了: 探测脚本硬上限约 28 个请求并带节流, 构建过程绝不批量抓页面。产出的 Skill 运行时是"每 24 小时抓一次索引 + 每个问题 1–3 个页面"。

---

## 3. 工作流程

**Phase 1 Discovery** —— 分两半。**机械的那一半**跑 `scripts/probe_docs_source.py`, 它遍历一个约定俗成位置的注册表。**人的那一半**不可跳过: 联网搜索索引位置(它的位置没有标准, 靠拼 URL 会漏)、找开源文档仓库、检查厂商是否已经自己发了 MCP server 或插件。当探测报告里 `needs_manual_discovery: true`, 那意思是"再搜仔细点", **不是**"这个站没有索引"。

**Phase 2 决策** —— 读 `references/mechanism-catalog.md`, 按实测数字选出**索引档位 T0–T5** 和**正文档位 C0–C2**。探测脚本的 `conclusion` 是一个带类型的起点, 不是判决。然后**一次性**把结论汇总给用户; 只有真正会改变构建结果的问题才问。

**Phase 3 产出** —— 按 `references/skill-template.md` 写文件。`docs_query.py` 是**原样复制**的, 站点差异全部落在 `docs-source.json` 里, 不允许 fork 脚本。

**Phase 4 验收** —— 必须实跑。第一步是解析产出的 frontmatter, 因为 YAML 解析失败不会抛错 —— Skill 会以空 metadata 加载, 于是压根不会被触发, 那后面所有的测量就都没有意义了。然后才是那个**真正会暴露问题的用例**: 一个"目标页面标题里根本没有那个搜索词"的查询。这才是这类 Skill 的实际失败方式。

**`check` 模式** —— 拿产出 Skill 里 `references/mechanism.md` **最顶上那条**当基线重新探测做 diff: 索引搬家了、结构漂移跨过了档位阈值、`.md` 孪生页出现或消失(这条经常意味着一大笔 token 的得失)。无论结果如何都要追加一条新日志 —— 包括结论是"什么都没变"的时候, 因为一次不留痕迹的 check 和一次根本没跑过的 check 是分不出来的。

---

## 4. 探测脚本到底是什么

这一节值得说精确, 因为它的名字容易被理解得过大。`probe_docs_source.py` 是一把**卷尺, 不是探测器**。它自动化的是"手工发二十个 WebFetch 然后肉眼数"这件事, 并且绕开了一批已知的坑。它机械地做四件事:

1. 把规则注册表里的每个位置都试一遍 —— `llms.txt`、`llms-full.txt`、`.well-known/llms.txt`, 在目标路径**和每一级父路径**上;
2. 对找到的东西做统计: 体积、条目数、分节数、描述覆盖率、链接指向的 host;
3. 拿一个真实叶子页面试 6 种纯文本约定 (`.md`、`/index.md`、`.txt`、`Accept: text/markdown`、`?plain=1`、原样);
4. 读 `robots.txt` 里声明的 sitemap 并数 URL 数。

它**做不到**: 找到放在非常规位置的索引、判断描述写得好不好、做设计决策。它的 `Conclusion` dataclass 只是按文件顶部那些阈值做的确定性推断, 目的是给 agent 一个带类型的起点。

它已经处理掉的坑, 全部是写这个 Skill 时对着真站点测出来的:

- **软 404。** 很多站点对不存在的路径也返回 200。脚本先请求一个必然不存在的 URL 做**基线签名**, 之后靠正文比对判断存在性, 不看状态码。`docs.databricks.com` 的 404 是一个固定 12,999 字节的 `text/html`。
- **一个品牌下有两个 `llms.txt`。** `databricks.com/llms.txt` 是市场官网的索引, 文档的那份在 `docs.databricks.com/llms.txt`。按"条目 host 是否等于文档 host"来选。
- **登录墙。** `vercel.com/llms-full.txt` 会跳到 `/login?next=…` 然后返回 200, 这不证明文件存在, 已识别为不存在。
- **`llms-full.txt` 是陷阱。** Vercel 那份 7.7 MB(约 190 万 token), 是全文转储不是索引, 永远不要加载。
- **索引覆盖率。** Databricks 索引 252 条, sitemap 有 5,645 个 URL —— 只覆盖 **4.5%**。这说明它是**精选的枢纽索引**而非完整页面清单, 必须叠加"再下探一跳"的设计。只看条目数完全看不出这一点, 而看不出就会发布一个自信地漏掉 95% 文档的 Skill。
- **最小的不等于最好的。** 在 `vercel.com/docs` 上, `index-md` 返回 1,191 字节, 而正确的 `md-suffix` 孪生页是 4,991 字节。所以胜出者按注册表的偏好顺序选, 并且当不同变体体积差距过大时会告警。
- **正文体积的反直觉结论。** 站点只有 HTML 时, 要用 **WebFetch 而不是 curl** —— WebFetch 会先把 HTML 转成 markdown 再进上下文。Databricks 单页原始 HTML 是 50,782 字节; Vercel 的 `.md` 孪生页 4,991 字节, 而同一页 HTML 是 916,562 字节, **省 99%**。

---

## 5. 为什么 `docs_query.py` 要拷进每个产出的 Skill

产出的 Skill 在**用户提问的那一刻**需要一个执行体。`SKILL.md` 是给 agent 的说明书, 说明书里总得写"跑什么命令"。只有两个选项: `curl … | grep`, 或者这个脚本。同样两条查询的实测差别:

| | `curl \| grep` | `docs_query.py` |
| :--- | :--- | :--- |
| 重复查询 | 每次重下 202KB (1.97s) | 24h 内 0 请求 (0.156s) |
| 命中结果 | 只有原始行 | 标注了所属分节 `[Compute]` |
| **查不到时** | **静默返回空** | 打印出召回阶梯 |
| 取整节兜底 | 要写站点特定的 awk | `section <名字>` |
| 结果被截断 | 静默 | 明说还有几条没显示 |

第三行是最要命的。静默的空结果让 agent 分不清"这个产品没这个功能"和"我词用错了" —— 于是它会回答"文档里没有", 而这是错的。

而且它是**同一个脚本**配不同的 `docs-source.json`。这就是"只描述规范"的字面落实, 也意味着不存在每个站维护一份脚本的问题。

**T0 档根本不拷这个脚本。** 索引小又描述全的站点(比如 `claude-code-docs` 那种 ~150 条的), `SKILL.md` 里直接让 agent WebFetch 索引就完事, `scripts/` 目录压根不生成。脚本只在 T1–T3(索引大到不能整个进上下文)才有存在价值。

---

## 6. 目录结构

```
docs-skill-builder/
├── SKILL.md                          构建流程与硬性规则(权威版)
├── SKILL-cn.md                       中文翻译
├── README.md / README-cn.md          本文件及其翻译
├── scripts/probe_docs_source.py      纯标准库 CLI; 只测量, 不决策
├── assets/docs_query.py              原样复制进产出 Skill 的运行时
└── references/
    ├── mechanism-catalog.md          决策表: 索引 6 档 + 正文 3 档、召回阶梯、
    │                                 爬虫的准入条件、验收测试
    └── skill-template.md             产出 Skill 的文件清单、配置 schema、SKILL.md 骨架
```

### 产出的 Skill 长什么样

```
<product>-docs/
├── SKILL.md                          怎么查这个产品的文档(权威版)
├── SKILL-cn.md                       中文翻译
├── README.md / README-cn.md          概览及其翻译
├── VERSION / CHANGELOG.md
├── scripts/                          T0 档完全不生成
│   ├── docs_query.py                 原样复制 —— 绝不 fork
│   └── docs-source.json              站点差异全在这一个文件里
└── references/
    ├── mechanism.md                  只追加的机制日志(权威版)
    └── mechanism-cn.md               中文翻译
```

`references/mechanism.md` 是一份 **changelog 形式的日志, 最新的在最上面**。每次 `build` 和每次 `check` 都追加一条, 记录当时实测的事实、选型理由、以及什么情况下该推翻这个选型 —— 这样 `check` 才有基线可比, 下次重建也能重新判断而不是照抄。条目长度按"实际变了多少"来定: 机制变了 ≤1000 词, 只是漂移 ≤500 词, 什么都没变 ≤200 词 —— 这是为了让这个文件迭代十次之后仍然读得下去。已有的条目永远不改写; 这份日志的价值就在于它记录了当时相信什么、以及后来为什么不成立了。

**三对文件要翻译**, 而且一个都不能少: `SKILL.md`、`README.md`、`references/mechanism.md`。英文为准, 两边在同一轮里一起写完, 而且英文版里绝不提翻译的存在 —— 那条约定只写在 `-cn.md` 里。Builder 自己是中英双语的, 它产出的东西也应该是。

---

## 7. 脚本规范

两个脚本都是纯标准库, 遵循项目的 [Python CLI 脚本规范](../../../../shsk_lesson_smith-project/.claude/skills/lesson-smith/skills/lesson-smith/scripts/python-cli-script-standard.md): 底层 `_main(...)` 接收带类型标注的参数并承载全部逻辑, 顶层 `main(argv)` 只做 argparse, 全部用 `--arg_name` 关键字风格, 文件末尾固定 `sys.exit(main())`。`_main` 可以直接 import 进来测试, 不必走命令行。

`probe_docs_source.py` 另外把它认识的**所有约定集中在一个 `REGISTRY` 注册机**里 (`IndexRule` / `ContentRule` / `SitemapRule`), 所以教会它一个新约定是加一条记录, 而不是加一条代码路径。它的整份报告是一棵 dataclass 树 —— `--json_out` 写出的正是 `dataclasses.asdict(ProbeReport)` —— 最后收敛到一个强类型的 `Conclusion`。
