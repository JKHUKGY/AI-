# Docs Skill Builder

A meta-tool: give it a vendor's documentation site and it produces an `xxx-docs` skill — the
kind of on-demand documentation lookup that `claude-code-docs`, `codex-docs`, and
`antigravity-docs` provide.

```
/docs-skill-builder build .claude/skills/databricks-docs for https://docs.databricks.com
/docs-skill-builder check  .claude/skills/databricks-docs
```

The goal is to stop re-deriving the mechanism in a long conversation for every new docs site.
That exploration is now a probe script plus two decision tables.

A Chinese translation is [README-cn.md](README-cn.md). **This English version is
authoritative**; if the two disagree, this one wins and the translation gets fixed.

---

## 1. The problem it solves

An `xxx-docs` skill is a lazy loader, and its quality is one ratio: **answers found per token
spent**. Three forces pull against each other:

- **Resident cost** — the index should be small, but too small and the agent routes blind;
- **Recall** — you want the agent to see everything, but that means tens of thousands of
  tokens up front;
- **Freshness** — deriving everything at query time is the most accurate and the most
  expensive in requests.

The key conclusion is that **levels are not free**. Every level of hierarchy is a routing
decision, and routing decisions multiply. Two levels at 90% correct routing give 81%
end-to-end recall; three give 73%. Worse, a miss at level 1 is usually unrecoverable — the
agent never sees the branch holding the answer, and does not know it missed.

So the rule is not "add levels to save tokens". It is:

> Add a level only when the level above carries **enough description to route correctly**, and
> always keep a **flat escape hatch** that searches every entry at once.

The generated `docs_query.py` has exactly this shape: `section` walks the hierarchy, `search`
ignores it and scans everything. A bad routing decision costs one extra command, not the
answer.

A corollary that matters more than it sounds: **prefer the site's own hierarchy**. The `##`
sections in `llms.txt`, breadcrumbs, area landing pages — these are maintained upstream and
are always current. An invented taxonomy starts rotting the moment it is written.

---

## 2. Three hard preferences

These are enforced by the Standing principles in `SKILL.md` on every build:

1. **Describe the contract; don't materialize the list.** Anything expressible as a rule
   ("append `.md` to the URL") must never become a scraped page inventory. An inventory is a
   second source of truth that only gets worse.
2. **Buy recall with reasoning, not artifacts.** Query-time synonym expansion and section
   fallback beat a pre-enriched index that goes stale.
3. **Crawling is the last resort.** Only when prose descriptions fall below 30%, the
   acceptance test **measurably** fails, and no open-source docs repo offers the same text —
   and even then it ships with a rebuild path. Caching page *bodies* into the repo is never
   allowed; bodies change fastest.

Request volume is bounded too: the probe is hard-capped (~28 requests) and throttled, and the
build never bulk-fetches pages. The produced skill's runtime is one index fetch per 24 h plus
1–3 pages per question.

---

## 3. Workflow

**Phase 1 — Discovery.** Two halves. The *mechanical* half runs
`scripts/probe_docs_source.py`, which walks a registry of conventional locations. The *human*
half — web-searching for the index (its location is not standardized, so guessing URLs misses
things), looking for an open-source docs repo, and checking whether the vendor already ships
an MCP server or plugin — is not optional. When the probe reports
`needs_manual_discovery: true` that means "search harder", **not** "this site has no index".

**Phase 2 — Decide.** Read `references/mechanism-catalog.md` and pick an **index tier
(T0–T5)** and **content tier (C0–C2)** from the measured numbers. The probe's `conclusion`
block is a typed starting point, not a verdict. Then send the user **one** consolidated
message; ask only what would genuinely change the build.

**Phase 3 — Emit.** Write the files per `references/skill-template.md`. `docs_query.py` is
copied **verbatim**; all per-site difference lives in `docs-source.json`. Forking the script
is not allowed.

**Phase 4 — Acceptance test.** Must actually run. It opens by parsing the emitted frontmatter,
because YAML that fails to parse does not raise — the skill loads with empty metadata and simply
never triggers, which would make every later measurement meaningless. Then the test that exposes
real failures: a query whose **target page title does not contain the obvious search word**. That
is how these skills fail in practice.

**`check` mode.** Re-probes against the baseline in the top entry of the produced skill's
`references/mechanism.md` and diffs it: index moved, structure drifted across a tier
threshold, `.md` twins appeared or vanished (often a large token swing). Either way it appends
a new log entry — including when the finding is "nothing changed", since a check that leaves
no trace is indistinguishable from one that never ran.

---

## 4. What the probe actually is

Worth being precise, because the name oversells it. `probe_docs_source.py` is a **measuring
tape, not a detector**. It automates "fire off twenty WebFetch calls by hand and eyeball the
results", and it avoids a set of known traps. It does four mechanical things:

1. Tries every location in its rule registry — `llms.txt`, `llms-full.txt`,
   `.well-known/llms.txt` — at the target path **and each parent**.
2. Measures what it finds: size, entry count, section count, description coverage, link hosts.
3. Tries six plain-text conventions (`.md`, `/index.md`, `.txt`, `Accept: text/markdown`,
   `?plain=1`, as-is) against one real leaf page.
4. Reads `robots.txt` for declared sitemaps and counts their URLs.

It **cannot** find an index at an unconventional location, does not judge description quality,
and does not make the design decision. Its `Conclusion` dataclass is a deterministic reading
of the thresholds at the top of the file, offered so the agent has a typed starting point.

Traps it handles, all found against live sites while building this:

- **Soft 404s.** Many sites answer `200` for missing paths. The probe first requests a URL
  that cannot exist and uses that as a **baseline signature**, then decides existence by body
  comparison rather than status code. `docs.databricks.com` returns a constant 12,999-byte
  `text/html` 404.
- **Two `llms.txt` under one brand.** `databricks.com/llms.txt` is the marketing index; the
  docs one is `docs.databricks.com/llms.txt`. Pick by whether entry hosts match the docs host.
- **Auth walls.** `vercel.com/llms-full.txt` redirects to `/login?next=…` and returns `200`.
  That is not evidence the file exists; it is classified as absent.
- **`llms-full.txt` is a trap.** Vercel's is 7.7 MB (~1.9M tokens) — a full-text dump, not an
  index. Never load it.
- **Index coverage.** Databricks lists 252 entries against 5,645 sitemap URLs — **4.5%**. That
  identifies it as a *curated hub index*, not a full page list, and forces a second-hop
  design. Entry count alone hides this completely, and missing it means shipping a skill that
  confidently misses 95% of the docs.
- **Smallest is not best.** On `vercel.com/docs`, `index-md` returns 1,191 B where the correct
  `md-suffix` twin returns 4,991 B. The winner is chosen by registry preference order, and a
  large size disagreement between variants raises a warning.
- **Counterintuitive content rule.** When a site serves HTML only, use **WebFetch, not curl** —
  WebFetch converts HTML to markdown before it reaches context. One Databricks page is 50,782
  bytes of raw HTML; Vercel's `.md` twin is 4,991 bytes against 916,562 bytes of HTML for the
  same page, a **99% saving**.

---

## 5. Why `docs_query.py` is copied into every produced skill

The produced skill needs an executable at question time. `SKILL.md` is instructions for the
agent, and those instructions have to name a command. There are two options: `curl … | grep`,
or the script. Measured difference on the same two queries:

| | `curl \| grep` | `docs_query.py` |
| :--- | :--- | :--- |
| Repeat query | re-downloads 202 KB (1.97 s) | 0 requests within 24 h (0.156 s) |
| Hit format | raw line only | annotated with its section, `[Compute]` |
| **On a miss** | **silently returns nothing** | prints the recall ladder |
| Whole-section fallback | site-specific `awk` | `section <name>` |
| Truncated results | silent | states how many were withheld |

The third row is the dangerous one. A silent empty result leaves the agent unable to tell "this
product lacks the feature" from "I used the wrong word" — so it answers "not documented", and
is wrong.

It is the **same script everywhere**, configured by `docs-source.json`. That is the "describe
the spec" principle applied literally, and it means there is no per-site script to maintain.

**T0 skills do not get the script at all.** When the index is small and well-described (like
`claude-code-docs`, ~150 entries), `SKILL.md` just tells the agent to WebFetch the index and no
`scripts/` directory is generated. The script earns its place only at T1–T3, where the index is
too large to enter context whole.

---

## 6. Layout

```
docs-skill-builder/
├── SKILL.md                          build procedure and hard rules (authoritative)
├── SKILL-cn.md                       Chinese translation
├── README.md / README-cn.md          this file and its translation
├── scripts/probe_docs_source.py      stdlib CLI; measures, does not decide
├── assets/docs_query.py              runtime copied verbatim into produced skills
└── references/
    ├── mechanism-catalog.md          decision tables: 6 index tiers + 3 content tiers,
    │                                 recall ladder, crawl criteria, acceptance test
    └── skill-template.md             produced-skill file set, config schema, SKILL.md skeleton
```

### What a produced skill looks like

```
<product>-docs/
├── SKILL.md                          how to query this product's docs (authoritative)
├── SKILL-cn.md                       Chinese translation
├── README.md / README-cn.md          overview and its translation
├── VERSION / CHANGELOG.md
├── scripts/                          omitted entirely at T0
│   ├── docs_query.py                 copied verbatim — never forked
│   └── docs-source.json              the whole per-site difference
└── references/
    ├── mechanism.md                  append-only mechanism log (authoritative)
    └── mechanism-cn.md               Chinese translation
```

`references/mechanism.md` is a **changelog-style log, newest entry on top**. Every `build` and
every `check` appends one entry recording the facts measured at the time, the reasoning behind
the choice, and what would overturn it — so `check` has a baseline to diff against, and a
future rebuild can re-decide rather than copy. Entry length is budgeted by how much actually
moved: ≤1000 words when the mechanism changed, ≤500 for drift, ≤200 for "nothing changed" —
which keeps the file readable after ten entries. Past entries are never rewritten; the log's
value is that it shows what was believed then and why it stopped being true.

**Three pairs are translated**, and all three are required: `SKILL.md`, `README.md`, and
`references/mechanism.md`. English is authoritative, both halves are written in the same pass,
and the English file never mentions the translation — that convention lives only in the
`-cn.md` file. The builder is bilingual, and so is what it produces.

---

## 7. Script conventions

Both scripts are pure standard library and follow the project's
[Python CLI standard](../../../../shsk_lesson_smith-project/.claude/skills/lesson-smith/skills/lesson-smith/scripts/python-cli-script-standard.md):
a `_main(...)` carrying typed arguments and the real logic, a thin `main(argv)` doing argparse,
`--arg_name` keyword flags only, and `sys.exit(main())` at the bottom. `_main` is importable
and directly testable without going through the command line.

`probe_docs_source.py` additionally centralizes every convention it knows in a single
`REGISTRY` (`IndexRule` / `ContentRule` / `SitemapRule`), so teaching it a new convention is
one entry rather than a new code path. Its entire report is a dataclass tree — `--json_out`
writes exactly `dataclasses.asdict(ProbeReport)` — ending in a strongly-typed `Conclusion`.
