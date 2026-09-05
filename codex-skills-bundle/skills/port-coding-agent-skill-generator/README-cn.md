# Port Skill Generator Skill

这个 Skill 是一整个 port skill 家族的「工厂」和唯一维护点。它不亲自搬运配置,而是负责生成那些真正干活的 skill: 给定一对源 agent 和目标 agent, 它一次刻出两个 skill, 一个执行迁移的 `port-<source>-to-<target>`, 一个只读审查的 `port-<source>-to-<target>-checker`。

---

## 1. 它解决什么问题

现在有三个编码 agent (Claude Code, Codex, Antigravity), 两两互转有 6 个方向, 每个方向需要一个执行 skill 加一个审查 skill, 一共 12 个。手工维护 12 份几乎雷同的文件, 改一处逻辑就要同步改十几遍, 很快就会漂移不一致。

这个 generator 把「所有 port 对共有的逻辑」收进两份模板 (执行版和审查版), 12 个 skill 全部由这两份模板刻出来, 彼此结构完全一致, 只在源和目标 agent 上有差别。要改所有 port skill 的行为, 就改这里的模板再重新生成, 永远不要去手改生成出来的 skill。

---

## 2. 一条最关键的设计线: agent 名单可以写死, 概念清单绝对不能

把两类知识严格分开:

- **agent 名单** (有哪些 agent, 它们的规范名, slug, 对应的文档查询 skill) 小而稳定, 新增一个 agent 是罕见的大事。所以在 generator 里用一张解析表来认它是可以的。这张表要和概念映射标准 `../coding-agent-concept-mapping-builder/ref/mapping-file-standard.md` 第 2 节的工具列表保持一致, 那里才是权威来源。
- **概念清单** (project prompt, settings, skills, commands, hooks, MCP, subagents, permissions, 以及以后还会加的) 一直在增长。绝不能把它写死进 generator 或模板。生成出来的 skill 每次运行时, 都从概念映射索引 `coding-agent-concept-mapping/ref/00-context-index.md` 现取。这个索引同时既是「概念清单」, 又是「每个 agent 对应哪个文件/位置」的地图, 所以生成的 skill 拿它当扫描清单和文件映射, 天然不需要硬编码任何概念。

---

## 3. 生成出来的两个 skill 各干什么

**执行版 `port-<source>-to-<target>`**: 接收项目路径, 读概念索引拿到清单和文件位置, 在项目里扫源 agent 的配置产物, 对每个命中的概念去读该概念的详情文件 (或调用 `coding-agent-concept-mapping` skill) 理解映射和转入注意事项, 必要时查目标 agent 的 docs skill 核对当前格式, 然后在项目里创建或修改目标 agent 的对应文件。源文件全部保留, 两套配置并存, 不覆盖。带 `disable-model-invocation`, 只能手动触发, 因为它会真的改文件。

**审查版 `port-<source>-to-<target>-checker`**: 扫描和映射逻辑和执行版一样, 但只读。它对比源侧和目标侧的现状, 判断每个概念是完整迁移, 部分迁移, 还是缺失, 把缺口, 建议改法, 优先级/影响写成一份结构化报告, 固定输出到项目里的 `tmp/review-port-<source>-to-<target>.md` (存在则覆盖)。除了这份报告文件, 不动项目里任何配置。

---

## 4. 怎么用

```
/port-coding-agent-skill-generator cc to cdx
/port-coding-agent-skill-generator claude code to codex
/port-coding-agent-skill-generator ag to cc
```

方向写成 `<source> to <target>`, 两侧都能用缩写 (cc / cdx / ag) 或全名。generator 解析方向, 认领两个 agent, 算出所有占位符, 读两份模板做替换, 分别写到 `.claude/skills/port-<source>-to-<target>/SKILL.md` 和 `.claude/skills/port-<source>-to-<target>-checker/SKILL.md`。已存在就覆盖, 重新生成就是更新这一对 skill 的方式。

---

## 5. 目录结构

```text
port-coding-agent-skill-generator/
├── SKILL.md                          生成流程本体
├── README-cn.md                      本文件
└── ref/
    ├── port-skill-template.md        执行版 skill 的模板
    └── checker-skill-template.md     审查版 skill 的模板
```
