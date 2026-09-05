# Mechanism catalog — how to pick a docs-lookup design

Applied by `docs-skill-builder` after `scripts/probe_docs_source.py` has produced a fact
sheet. Every threshold below is keyed to a number the probe actually prints, so the choice
is a lookup, not a debate.

Two independent decisions. Make them separately:

1. **Index mechanism** — how the agent finds *which page* answers the question.
2. **Content contract** — how the agent reads *that page* without burning tokens on HTML.

---

## 1. The governing tradeoff

An `xxx-docs` skill is a lazy loader. Its quality is one ratio: **answers found per token
spent**. Three forces pull against each other.

| Force | Push | Cost of over-serving it |
| :--- | :--- | :--- |
| **Resident cost** | keep the always-loaded index small | agent routes blind, picks the wrong branch |
| **Recall** | show the agent everything | 50k tokens gone before the question is even read |
| **Freshness** | derive everything at query time | more requests, more latency |

### Why levels are not free

Each level of hierarchy is a routing decision, and routing decisions multiply. Two levels
at 90% correct routing give 81% end-to-end recall; three give 73%. A miss at level 1 is
usually unrecoverable — the agent never sees the branch containing the answer, and it does
not know that it missed.

So the rule is not "add levels to save tokens". It is:

> **Add a level only when the level above it carries enough description to route correctly,
> and always keep a flat escape hatch that searches everything at once.**

`docs_query.py` enforces this shape: `section` gives you the hierarchy, `search` ignores it
and scans every entry. A bad routing decision costs one extra command, not the answer.

### Prefer the site's hierarchy over an invented one

If the vendor already groups pages (`##` sections in `llms.txt`, breadcrumbs, a landing page
that links to its children), use *that*. It is maintained upstream, it is always current,
and it costs nothing to keep. An invented grouping is a static artifact that starts rotting
the moment it is written. This is the single biggest lever on long-term skill quality.

---

## 2. Index discovery ladder

Run in order. Stop at the first tier that yields a real, complete-enough index. Cheap tiers
first — do not spend a crawl budget before checking whether the vendor already published
the answer.

| Step | What | How |
| :--- | :--- | :--- |
| 1 | **`llms.txt` by convention** | `probe_docs_source.py --domain <url>` walks `REGISTRY.index_rules` — `/llms.txt`, `/llms-full.txt`, `/.well-known/llms.txt` — at the target path *and every parent*, against a calibrated 404 |
| 2 | **`llms.txt` by search** | its location is not standardized — WebSearch `"<product> llms.txt"`, and check the vendor's docs-for-AI / developer page. Feed anything found back in via `--extra_index_url` |
| 3 | **Vendor's own agent tooling** | an official MCP server, Claude Code plugin, or docs search API often exists. If it does, say so — it may make the skill unnecessary, or complementary |
| 4 | **Sitemap** | `robots.txt` `Sitemap:` directives, `/sitemap.xml`, `/sitemap_index.xml`. Gives complete URL coverage but **no descriptions** |
| 5 | **Open-source docs repo** | many vendors publish docs as markdown on GitHub. `git` metadata or the GitHub API gives a full file list plus raw markdown. Caveat: the repo may be *ahead of* the published site |
| 6 | **Crawl** | last resort — see §6 |

Traps the probe already handles, all observed in the wild:

- **Soft 404s.** Sites that answer `200` for everything. Existence is decided by comparing
  against a deliberately bogus URL, never by status alone.
- **Two different `llms.txt`.** `databricks.com/llms.txt` is a *marketing* index; the docs
  one is `docs.databricks.com/llms.txt`. Prefer the one whose entry hosts match the docs host.
- **Auth walls.** A `200` served from `/login?next=…` proves nothing. Treated as absent.
- **`llms-full.txt` is a trap.** Vercel's is 7.7 MB (~1.9M tokens). It is a full-text dump,
  not an index. Never load it; rarely worth even searching.

---

## 3. Index mechanism tiers

Read the probe's `bytes`, `description_prose_pct`, `section_count`, and `coverage`.

The probe's `conclusion` block already applies these thresholds and reports an
`index_tier_hint` / `content_tier_hint`. Treat it as a typed starting point, not a verdict:
it knows only what its registry covers, so confirm it here and override it — saying why — when
the site is unusual. Its `needs_manual_discovery` flag means the conventional locations came
up empty, which is a cue to search harder, never a finding that no index exists.

| Tier | Trigger (from the fact sheet) | Design | Runtime cost |
| :--- | :--- | :--- | :--- |
| **T0 — inline index** | ≤ 40 KB **and** prose ≥ 60% | No script. SKILL.md tells the agent to WebFetch the index each time, then fetch 1–3 pages | ~10k tok once per question |
| **T1 — section-routed** | 40–150 KB, ≥ 4 real sections, prose ≥ 50% | `sections` → `section <name>` → pages. `search` stays available as the escape hatch | 0.3–2k tok |
| **T2 — search-first** | > 150 KB **or** bare-description ≥ 50% | `search <regex>` is the primary path; `section` is the fallback when search misses | ~0.2k tok per query |
| **T3 — sitemap-derived** | no `llms.txt`, sitemap exists | Same script, `format: "sitemap"`. Entries are slugs only, so recall rests on URL wording | ~0.2k tok, weaker recall |
| **T4 — hub-descend** | `coverage.verdict == "hub-level"` | Index routes to a landing page; the agent then follows that page's own links. Layer on top of T0–T2 | +1 page fetch |
| **T5 — pre-built manifest** | everything above failed acceptance | Scrape real descriptions once into a committed manifest. **Last resort** — see §6 | ~1–3k tok, goes stale |

Worked examples, all measured:

| Site | Index | Facts | Tier |
| :--- | :--- | :--- | :--- |
| Claude Code | `code.claude.com/docs/llms.txt` | ~150 entries, rich descriptions | **T0** |
| Databricks | `docs.databricks.com/llms.txt` | 47 KB, 252 entries, 15 sections, 98% prose, coverage 252/5645 = 4.5% | **T1 + T4** |
| Vercel | `vercel.com/llms.txt` | 202 KB, 1406 entries, 20 sections, 86% bare | **T2** |
| Antigravity | `antigravity.google/llms.txt` | descriptions are boilerplate ("Learn about X") | **T5** |

Databricks is the instructive one: a *comfortable* index (47 KB, near-perfect descriptions)
that covers only 4.5% of the site. The index alone answers "which area", not "which page" —
hence T4 on top. Without the coverage measurement you would ship a skill that confidently
misses 95% of the docs.

---

## 4. Recall ladder (build this into every produced skill)

Recall, not index size, is what actually breaks these skills. The failure is silent: the
agent greps, gets nothing, and reports "not documented".

Encode this escalation in the produced SKILL.md, in order, before ever concluding absence:

1. **Search the obvious term.**
2. **Expand the query.** The docs' word is often not the user's word — a page about request
   timeouts is titled *Duration*; retries live under *Resilience*. Search 3–5 synonyms as one
   alternation, which costs the same as one search.
3. **Translate non-English queries.** These indexes are English-only. A Chinese query scores
   literally zero matches. Never conclude "undocumented" from a non-English miss.
4. **Fall back to the section.** Load the most plausible whole section — full recall inside
   it, for 1–4k tokens.
5. **Descend a hub entry** (T4) — fetch the area landing page and read its child links.
6. **Only then** report that it is not in the docs, and say what was searched.

This ladder is *dynamic enrichment*: it buys recall with query-time reasoning instead of a
static artifact that has to be maintained. Prefer it to enriching the index every time.

---

## 5. Content contract tiers

From the probe's `CONTENT CONTRACT` block. The winner is the smallest variant flagged
`PLAIN-TEXT`.

| Tier | Trigger | Produced config | Note |
| :--- | :--- | :--- | :--- |
| **C0 — plain-text twin** | any variant returns markdown | `mode: "plain-text"` + `url_template` | Vercel: `.md` twin is 4,991 B vs 916,562 B of HTML — **99% cheaper** |
| **C1 — HTML only** | every variant returns HTML | `mode: "html-webfetch"` | **Use WebFetch, not curl.** It converts HTML→markdown before anything reaches context. Databricks: 50,782 B of HTML for one page |
| **C2 — source repo** | docs are open source | `mode: "plain-text"` against `raw.githubusercontent.com` | Verify the repo tracks the published version |

C1 is the counterintuitive one. Elsewhere a shell pipe beats WebFetch because filtering
happens outside the context; for HTML *page bodies* the opposite holds, because there is
nothing to filter — you either pay for the whole HTML or let WebFetch reduce it first.

Always sanity-check the winning variant's body. A site can return `200` plain text that is a
stub or a redirect notice: on the same Vercel page, `index-md` returns 1,191 B where the
correct `md-suffix` twin returns 4,991 B — a smaller number that is not a better answer. The
probe therefore picks by **registry preference order**, not by size, and warns when two
variants disagree by more than 2×. Open the winner before committing to a template.

---

## 6. Crawling: the last resort, and what justifies it

A pre-built static index (**T5**) is a build artifact. It has a real, permanent cost: the
docs change and it does not. The Antigravity manifest is justified only because that site's
`llms.txt` descriptions are literally "Learn about X", so triage-by-description cannot work
at all without scraping real lead paragraphs.

Adopt T5 only when **all** of these hold, and say so explicitly in the produced skill:

- prose descriptions < 30%, **and**
- the acceptance test (§7) fails at T2/T3 — measured, not assumed, **and**
- no source repo (step 5) offers the same text, **and**
- the artifact ships with a rebuild path so it can be regenerated, not hand-patched.

Rules when crawling is genuinely warranted:

- Check `robots.txt` first; the probe already reports `disallow_all`.
- Throttle ≥ 0.15 s, single descriptive User-Agent, hard request cap.
- Tell the user the request count **before** starting, and get agreement for anything
  over ~100 pages.
- Cache-and-diff on the index hash so a rebuild is a no-op when nothing changed.

**Never** cache page *bodies* into the repo. That is the one artifact guaranteed to be
wrong: content changes far faster than structure. Bodies are always fetched live.

---

## 7. Acceptance test — a skill is not done until it passes

Run against the built skill, with real queries, and report measured token cost:

1. **An easy lookup** — a term that appears verbatim in a title. Proves the happy path.
2. **A vocabulary-mismatch lookup** — pick a topic whose page title does *not* contain the
   obvious search word (timeout → "Duration"). Proves the recall ladder, not just the index.
3. **A non-English query** — proves the translate-first rule is actually written down.
4. **One content fetch** — proves the contract and reports real bytes.

If test 2 only succeeds by loading the entire index, the tier is wrong: move down a tier or
add descriptions. Report the numbers to the user; do not just claim it passed.

---

## 8. Anti-patterns

- **Loading the index to "see what's there".** The index is a filter target, not a document.
- **`llms-full.txt` for anything.** Megabytes of full text; the index plus 2 pages is better.
- **Committing a page list that the site already publishes.** You have created a second
  source of truth that only ever gets worse.
- **Levels with no descriptions.** A menu of bare section names forces blind routing.
- **Silent caps.** If results are truncated or a section was skipped, print it. A quiet
  truncation reads as "that's everything".
- **Guessing URLs.** If it is not in the index, say so. Slugs get renamed (`dlt/` → `ldp`
  on Databricks, mid-2026); an invented URL is a confident 404.
- **Re-downloading the index every query.** Cache with a TTL — it is derived and disposable.
