---
name: docs-skill-builder
description: Build (or re-verify) an `xxx-docs` Agent Skill that looks up a vendor's official
  documentation on demand — by probing the site for an llms.txt/sitemap/source-repo index and
  a plain-text content contract, then picking the lazy-load design that maximizes recall per
  token. Use when asked to create a docs-lookup skill for a product ("build a databricks-docs
  skill", "make a skill for Stripe's docs"), to check whether an existing one has gone stale,
  or to work out how to query some vendor's documentation efficiently.
argument-hint: '[build|check] <target-path> for <docs URL or product> [notes]'
allowed-tools: Bash, Read, Write, Edit, WebFetch, WebSearch
---

# Docs Skill Builder

Produces an `xxx-docs` skill: a lazy loader that answers questions from a vendor's live
documentation. Invocation:

```
/docs-skill-builder build .claude/skills/databricks-docs for https://docs.databricks.com
/docs-skill-builder check  .claude/skills/databricks-docs
```

Parse `$ARGUMENTS` into **mode** (`build`, default, or `check`), **target path**, **subject**
(a URL or product name), and any **notes**. Notes are requirements, not suggestions — honor
them or say plainly why you did not.

The whole job is one question: **what is the cheapest way to find the right page, and the
cheapest way to read it?** Everything else follows from measurements.

## Standing principles

Hold these for the whole build; they decide the close calls.

- **Measure, don't assume.** Every number in the produced skill comes from the probe. If you
  cannot measure it, do not claim it.
- **Describe the contract; don't materialize the list.** Prefer a rule ("append `.md`") over a
  committed inventory. A copied page list is a second source of truth that only decays.
- **Use the site's own hierarchy.** Its sections and landing pages are maintained upstream and
  are always current. An invented taxonomy is a liability.
- **Buy recall with reasoning, not artifacts.** Query expansion and section fallback at query
  time beat a pre-enriched index that goes stale.
- **Crawling is the last resort**, and needs the explicit justification in catalog §6.
- **Be a polite client.** The probe is capped at ~28 requests and throttled. Do not loop it.
  Never bulk-fetch pages during a build.

## Phase 1 — Discovery

Discovery is **yours**, not the script's. Two halves, run together.

### 1a. The mechanical half — run the probe

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/probe_docs_source.py \
    --domain <docs-url> --generated_at $(date +%F) --json_out /tmp/<name>-facts.json
```

Read `scripts/probe_docs_source.py --help` for the full flag list. What it does: walks a
registry of **conventional, deterministic locations** — `llms.txt`, `llms-full.txt`,
`.well-known/llms.txt` at the target path *and every parent* — then measures whatever it
finds, tests six plain-text content conventions against a real leaf page, and counts sitemap
URLs. It prints a report and, with `--json_out`, the same data as a JSON dataclass tree.

**Understand exactly what this buys you.** It is a fast, careful substitute for you firing off
twenty WebFetch calls by hand and eyeballing the results. That is all. Specifically:

- It only knows the locations in its registry. **A site that publishes its index somewhere
  unconventional will come back empty, and that is not evidence the index does not exist.**
- It does not judge quality — it counts words in descriptions, it does not read them.
- It does not decide. Its `conclusion` block is a deterministic reading of its own thresholds,
  offered so you have a typed starting point. Confirm it against the catalog; override it when
  the site is unusual, and say why.

When the conclusion reports `needs_manual_discovery: true`, the mechanical half has finished
and found nothing. **Do not report "no index available" on that basis.** Go do 1b properly.

### 1b. The human half — search and reason

Always do this, even when the probe found something:

- **Web-search for the index.** `llms.txt` locations are not standardized: `"<product>
  llms.txt"`, `"<product> docs for LLMs"`, and the vendor's own docs-for-AI / developer page.
  Feed anything found back in with `--extra_index_url <url>` and re-run once.
- **Look for an open-source docs repo.** Many vendors publish docs as markdown on GitHub. A
  repo gives a complete file list plus raw markdown, often beating both llms.txt and sitemap.
  Verify it tracks the published version rather than being ahead of it.
- **Check what the vendor already ships** — an official MCP server, Claude Code plugin, or docs
  search API. If one exists, report it: it may make this skill redundant, or complementary
  (hand-written best practices vs. authoritative live text). Let the user decide; do not
  silently build a duplicate.
- **Look at the actual docs site** if the probe came up empty. How does its own search work? Is
  there a JSON endpoint behind it? Is there a print/raw view? These are real mechanisms the
  registry cannot guess at.

If you find a convention the registry does not know, add it there — one entry in
`REGISTRY.index_rules` or `REGISTRY.content_rules` — so the next build gets it for free.

## Phase 2 — Decide

Read [references/mechanism-catalog.md](references/mechanism-catalog.md) now and apply its
decision tables. Pick an **index tier (T0–T5)** and a **content tier (C0–C2)**, using the
probe's `conclusion` as a starting point rather than a verdict, and note which alternative you
rejected and why.

Then send the user **one** consolidated message: the key numbers, the chosen design, the
tradeoff in a sentence, anything the vendor already ships, and any scope question. Ask via
AskUserQuestion only if the answer would genuinely change the build — for example two tiers
within measuring error, or whether to include a heavyweight API-reference section. If the
facts are decisive and the notes cover scope, say what you are doing and build it.

Two calls that are easy to get wrong:

- **A comfortable index that covers little.** Check `coverage`. Databricks' index is 47 KB with
  98% prose descriptions and covers 4.5% of the site — it needs T4 layered on, or the skill
  confidently misses almost everything.
- **HTML-only content.** Use WebFetch, not curl. It reduces HTML to markdown before anything
  reaches context; a raw page can be 50 KB–900 KB.

## Phase 3 — Emit

Follow [references/skill-template.md](references/skill-template.md) for the exact file set,
`docs-source.json` schema, and SKILL.md structure. Also:

- Copy `assets/docs_query.py` **verbatim** into `<target>/scripts/`. Do not fork it — per-site
  behavior belongs in `docs-source.json`. If a site genuinely cannot be expressed in that
  config, prefer extending the config schema over writing a bespoke script, and say so.
- Skip `scripts/` entirely at **T0**. An inline-index skill needs no code.
- Open `references/mechanism.md` with the first log entry: how the site is read, why this
  design and which alternative lost, what would overturn it, and any hand-written asset a
  rebuild must preserve. It is append-only from here — see the template for the entry format
  and its word budget.
- Match this project's conventions: `VERSION` (start at `0.1.1`) and `CHANGELOG.md`.
- **Ship all three translated pairs**: `SKILL.md`, `README.md`, and `references/mechanism.md`
  each get a `-cn.md` counterpart, written in the same pass, English authoritative. The
  English files never mention that a translation exists; only the `-cn.md` files carry the
  convention. This is required at every tier.
- Write the `description` so it triggers: front-load the product name and the real top-level
  areas taken from the index's own section names. If the user works in Chinese, add Chinese
  trigger phrases — the index has none, so this is hand-written and must be flagged in
  `mechanism.md` as rebuild-preserved.

## Phase 4 — Acceptance test (not optional)

First, prove the skill can load at all:

```bash
python3 -c "import sys,yaml; d=yaml.safe_load(open(sys.argv[1]).read().split('---',2)[1]); print({k:type(v).__name__ for k,v in d.items()})" <target>/SKILL.md
```

Expect four `str` fields. This runs first because frontmatter that fails to parse does not
error — the skill loads with **empty metadata** and therefore never triggers, so every test
below would be measuring a skill the agent can no longer find. A `list` where you expected a
`str` means an unquoted `[…]`; see the template's frontmatter section.

Then run the built skill's own commands and report real numbers. Per catalog §7:

1. An easy lookup whose term appears in a title.
2. **A vocabulary-mismatch lookup** — a topic whose page title lacks the obvious search word.
   This is the test that matters; it is how these skills actually fail.
3. A non-English query, to confirm the translate-first rule is written down and works.
4. One content fetch, reporting measured bytes.

If test 2 only passes by loading the whole index, the tier is wrong — go back to Phase 2.
Report the measured costs. Do not claim a pass you did not run.

## `check` mode

For an existing skill at `<target-path>`: read the top entry of its `references/mechanism.md`,
re-run the probe against the recorded index URL, and diff the facts against that baseline.
Report:

- **Index moved or died** (redirect, 404, auth wall) → the skill is broken; rebuild.
- **Structure drifted** (sections renamed, size changed sharply, description coverage moved
  across a tier threshold) → the tier may no longer be right; say which way it moved.
- **Content contract changed** (`.md` twins appeared or vanished) → often a large token win or
  loss; C1→C0 is worth rebuilding for on its own.
- **Nothing changed** → say so plainly. A no-op is a good result.

Re-run the Phase 4 tests either way — a skill can rot without any fact changing, and the
vocabulary-mismatch test is what catches it.

Then **append one entry to `references/mechanism.md`** (and its translation) recording what
this check found, including when the answer was "nothing". A check that leaves no trace is
indistinguishable from a check that never ran. Keep a no-change entry under 200 words and do
not restate the mechanism — the entry below it still holds.

## Rules

- **The probe supplements discovery; it does not perform it.** An empty probe means "search
  harder", never "this site has no index".
- **Never hand-write a number into a produced skill.** It comes from the fact sheet or it
  does not appear.
- **Never commit page bodies.** Content is always fetched live; bodies change fastest.
- **Never ship a placeholder.** No `<…>` from the template survives into output.
- **Never ship frontmatter you have not parsed.** Quote `argument-hint`; a bare `[…]` is a YAML
  sequence, not a string. Unparseable frontmatter loads as empty metadata instead of failing, so
  the skill goes silently untriggerable — verify it in Phase 4, do not eyeball it.
- **Never rewrite a past `mechanism.md` entry.** Append a new one. The value of the log is that
  it shows what was believed at the time and why that changed.
- **Never leave a translation behind.** `SKILL.md`, `README.md`, and `references/mechanism.md`
  ship with their `-cn.md` counterparts, updated in the same pass. A stale translation is
  worse than a missing one — it reads as current.
- **Report what you skipped.** If a probe hit its budget, a section was excluded, or a test
  was not run, say so. Silent omission reads as coverage.
- **One probe run per site per build.** If you need more requests, raise `--request_budget`
  once with a reason — do not loop the script.
