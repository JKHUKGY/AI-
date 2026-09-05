# Template for a produced `xxx-docs` skill

Fill every `<…>` from the fact sheet. Delete tier sections that do not apply. Never leave a
placeholder or an unmeasured number in the output — if a number is not in the fact sheet,
measure it or drop the claim.

## Files to emit

```
<target-path>/
├── SKILL.md                       # from the template below — authoritative
├── SKILL-cn.md                    # Chinese translation of SKILL.md
├── VERSION                        # 0.1.1
├── CHANGELOG.md                   # see project convention
├── README.md                      # English overview — authoritative
├── README-cn.md                   # Chinese translation of README.md
├── scripts/
│   ├── docs_query.py              # copied verbatim from assets/docs_query.py
│   └── docs-source.json           # the site contract (below)
└── references/
    ├── mechanism.md               # append-only mechanism log — authoritative
    └── mechanism-cn.md            # Chinese translation of mechanism.md
```

### The three translated pairs

`SKILL.md`, `README.md`, and `references/mechanism.md` each ship with a `-cn.md` counterpart.
All three pairs are **required**, not optional — the builder itself is bilingual and what it
produces is too.

The rules are the same for every pair:

- **English is authoritative.** When the two disagree, the English wins and the translation
  gets corrected — never the reverse.
- **Update both in the same pass.** A translation that lags is worse than none, because it
  reads as current. Any `build` or `check` that touches an English file touches its
  translation before finishing.
- **The English file never mentions that a translation exists.** `SKILL.md` in particular is
  the published artifact and the text loaded into the agent's context; a note about
  translation conventions is pure noise there. The convention is documented only in the
  `-cn.md` file, which also states that maintenance flows one way.

Each `-cn.md` opens with a note in that spirit:

```markdown
> 这是 [SKILL.md](SKILL.md) 的中文翻译, 只供人阅读。**英文版是权威版本**, 两者不一致时以英文版为准,
> 并把这份翻译改过来。维护是单向的: 改了英文版就回来同步这份, 反过来不成立。
```

Omit `scripts/` entirely for **T0** — an inline-index skill needs no code. The document set
above is required at every tier.

## `docs-source.json`

```json
{
  "name": "<skill-name>",
  "index": {
    "url": "<verified index URL, post-redirect>",
    "format": "llms-txt",
    "cache_ttl_seconds": 86400
  },
  "content": {
    "mode": "plain-text",
    "url_template": "{url_no_slash}.md"
  }
}
```

Fill `index.url`, `content.mode`, and `content.url_template` from the probe's `conclusion`
(`best_index_url`, `content_mode`, `content_url_template`) rather than by hand.

- `format`: `llms-txt` or `sitemap`.
- `mode`: `plain-text` (C0/C2) or `html-webfetch` (C1). With `html-webfetch`, omit
  `url_template` unless the page URL needs rewriting; `get` then tells the agent to WebFetch.
- `url_template` placeholders: `{url}`, `{url_no_slash}`, `{path}`, `{slug}`, `{host}`.
- `content.headers`: only when the winning variant was `accept-markdown` — copy the probe's
  `conclusion.content_headers` (e.g. `{"Accept": "text/markdown"}`) and omit `url_template`.

## `SKILL.md`

### The frontmatter has to parse as YAML

Non-negotiable, and easy to get wrong: a value beginning with `[` is a YAML **flow sequence**,
not a string. `argument-hint: [topic]` happens to survive as a one-element list, but the moment
the brackets are followed by anything else the document stops parsing:

```yaml
argument-hint: [build|check] <path> [notes]    # ✗ sequence closes, then a stray scalar
argument-hint: '[build|check] <path> [notes]'  # ✓
```

**So always single-quote `argument-hint`.** The same applies to any value containing `: `, or
starting with `{`, `&`, `*`, `!`, `|`, `>`, `%`, or `@`.

This failure is worth more than one line of caution because of how it presents: the parse error
points at line 2 (`name:`), nowhere near the offending line, and a skill whose frontmatter fails
to parse **loads with empty metadata rather than erroring** — no name, no description, so it
simply never triggers, silently. Before shipping, parse it and confirm you get four string
fields:

```bash
python3 -c "import sys,yaml; d=yaml.safe_load(open(sys.argv[1]).read().split('---',2)[1]); print({k:type(v).__name__ for k,v in d.items()})" <target>/SKILL.md
```

````markdown
---
name: <product>-docs
description: Look up authoritative, up-to-date <Product> documentation covering <the real
  top-level areas, taken from the index's own section names>. Use when the user asks how a
  <Product> feature works, what a config field does, how to set up <top areas>, when
  troubleshooting a <Product> error, or when you need current official docs rather than
  training-cutoff knowledge.
argument-hint: '[topic]'
allowed-tools: <Bash(python3 *) and/or WebFetch — only what the tier actually uses>
---

# <Product> Docs

Answers <Product> questions from the official docs on demand: <one line naming the tier —
e.g. "searches a cached copy of the 202 KB llms.txt index, then fetches the matching pages
as raw markdown">. Always prefer this skill over recalling docs from memory — the docs
change faster than training data.

If the user passed an argument (`$ARGUMENTS`), treat it as the topic. Otherwise infer it.

## When to use this skill

- <area 1 — from the index's own section names>
- <area 2>
- <area 3>

Out of scope: <adjacent product/API that has its own docs, and where to send the user>.

## How this site works

Measured <YYYY-MM-DD>; full fact sheet in [references/mechanism.md](references/mechanism.md).

- **Index**: `<url>` — <bytes> B, <n> entries, <s> sections, <p>% with prose descriptions.
- **Coverage**: <n> index entries vs <m> sitemap URLs (<r>%) — <leaf-level: the index is the
  complete page list | hub-level: entries point at area landing pages, so expect a second hop>.
- **Content**: <"every page has a `.md` twin — <a> B vs <b> B of HTML" | "HTML only — use
  WebFetch, never curl the raw page">.
- **Gotchas**: <redirects, dual llms.txt, auth walls, oversized llms-full.txt — only real ones>.

## Procedure

### 1. Find candidate pages

<T0>
```
WebFetch url=<index-url>
        prompt="Return the raw markdown. I need every `- [Title](URL): description` line unmodified."
```
</T0>

<T1/T2/T3>
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/docs_query.py search '<term>|<synonym>|<the word the docs would use>'
```
The index is fetched once and cached for 24 h, so repeat queries cost no requests. Only
matching lines enter context — never load the whole index.

Routing commands, cheapest first:

| Command | Cost | Use when |
| :--- | :--- | :--- |
| `search '<regex>'` | ~<x> tok | always start here |
| `sections` | ~<y> tok | search missed and you need the map |
| `section '<name>'` | <a>–<b> tok | full recall inside one area |
</T1/T2/T3>

### 2. If the search comes back empty

Do **not** conclude the topic is undocumented. Escalate:

1. Widen with synonyms — the docs' word is often not the user's (<a real example from this
   site, e.g. "timeout" lives under "Duration">).
2. If the query was not in English, retry with English terms. This index is English-only and
   a non-English query scores zero matches for reasons that have nothing to do with coverage.
3. `sections`, then `section '<most plausible>'` for full recall inside it.
4. <T4 only> Fetch the area landing page and follow its own links — the index lists areas,
   not every page.
5. Only then say it is not in the docs, and state what you searched.

### 3. Read the pages

<C0>
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/docs_query.py get <url-from-search>
```
Returns raw markdown (~<n> B/page).
</C0>

<C1>
```
WebFetch url=<url-from-search>
        prompt="<the user's actual question, not 'summarize this page'>"
```
Pages are HTML-only (~<n> B raw). WebFetch converts to markdown before it reaches context —
do not curl them.
</C1>

Fetch **1–3 pages per batch**, then judge whether that answers the question. Loop if not, to
a cap of **9 pages**. At 9 and still short, stop and tell the user what you read and what is
missing — do not silently continue or fill the gap with guesses.

## Context budget

| Step | Cost | Notes |
| :--- | :--- | :--- |
| `search` | ~<x> tok | only matched lines |
| `section` | <a>–<b> tok | one area, full recall |
| page | ~<n> tok each | 1–3 per batch |

Typical question: search + 1–2 pages ≈ **<total> tokens**. Loading the index whole would be
~<index> tokens, which is why nothing here does that. Read **one** section at a time; if you
cannot tell which section to read, that is a signal to search again with better terms, not to
load several.

## Rules

- **Never invent a doc URL.** Not in the index → say so. Slugs get renamed.
- **Never load the whole index**<, and never touch `llms-full.txt` (<size>)>.
- **Cite the URL that served the content.**
- **A 404 on a page URL means the index is stale** — re-run `/docs-skill-builder check <path>`.
- **Pass through what the docs say.** The user wants current authoritative behavior, not a
  synthesis with your prior knowledge.
````

## `references/mechanism.md`

An **append-only log**, changelog-style: newest entry on top, older entries never edited.
Every `build` and every `check` appends exactly one entry. The top entry always describes the
mechanism as it currently stands, so a reader stops after one entry unless they want history.

This is what lets `check` re-verify against a recorded baseline and a future rebuild
**re-decide rather than copy** — the reasoning is on the record, not just the conclusion.

### Length budget

The hard constraint is that this file stays readable after ten entries. Size the entry to how
much actually moved:

| What happened | Budget |
| :--- | :--- |
| Mechanism changed — tier moved, index relocated, content contract flipped | **≤ 1000 words** |
| Numbers drifted, a section renamed, a new gotcha found | **≤ 500 words** |
| Re-verified and nothing changed | **≤ 200 words** |

Write in prose, not bare bullets — someone six months out has to understand *why* the design
is what it is, and a bullet list does not carry reasoning. But stay well under the budget when
the content allows; these are ceilings, not targets.

**A no-change entry must not restate the mechanism.** Say it is unchanged, give the numbers
re-measured and the tests re-run, and stop. The entry below it still holds; repeating it is
what makes these files unreadable.

### File header

```markdown
# <product>-docs — mechanism log

How this skill reads <Product>'s documentation, and why. Newest entry first; the top entry
describes the current mechanism. Entries are appended, never rewritten.
```

### Entry format — a build, or a check that found change

````markdown
## <YYYY-MM-DD> — <build | check> · docs-skill-builder <version>

**Verdict.** <One line: what this entry establishes or what moved since the last one.>

**How the site is read.** <The index: URL, what kind, measured size, entry count, description
coverage, coverage vs. the sitemap. How the skill queries it — which command, what enters
context. How a page body is fetched and how big one is. Enough that the design could be
rebuilt from this paragraph alone.>

**Why this design.** Index tier **<T?>**, content tier **<C?>**. <The specific measurements
that forced the choice — not the rule, the numbers. Then the alternative considered and one
line on why it lost.>

**What would overturn it.** <Concrete, checkable triggers, each naming the tier it would move
to: e.g. "per-section llms.txt appears → T1, drop the script"; "prose descriptions pass 50%
→ T2 collapses to T1"; "`.md` twins appear → C1 to C0, large token win".>

**Rebuild must preserve.** <Hand-written assets no script can regenerate — e.g. Chinese
trigger phrases in `description`, absent from an English-only index.>
````

### Entry format — a check that found nothing

````markdown
## <YYYY-MM-DD> — check · docs-skill-builder <version>

**Verdict.** No change. The mechanism described in the <date> entry still holds.

Re-probed <index URL>: <size> B (was <size>), <n> entries (was <n>), <s> sections, <p>% with
descriptions — all within noise. Content contract unchanged: <the rule> still returns
<content-type>. Acceptance tests re-run, including the vocabulary-mismatch case
(<query> → <page>); <result>.
````
