# claude-code-docs — mechanism log

How this skill reads Claude Code's documentation, and why. Newest entry first; the top entry
describes the current mechanism. Entries are appended, never rewritten.

## 2026-07-30 — check

**Verdict.** First recorded entry, establishing the baseline. The skill had been hand-built
with no mechanism record, so this check had nothing to diff against. The mechanism itself is
unchanged and healthy — T0/C0 both still hold — but the numbers written into SKILL.md had
drifted and two recall rules were missing.

**How the site is read.** The index is `https://code.claude.com/docs/llms.txt`: 38,847 B
(~9,700 tokens), 174 entries, one flat `## Docs` section, 100% of entries carrying real prose
descriptions rather than boilerplate. Every target ends in `.md` and lives on `code.claude.com`.
Byte-identical copies are served at `/llms.txt` and `/docs/.well-known/llms.txt`. The skill
WebFetches the whole index once per question, triages on the descriptions (not the titles),
then fetches 1–3 pages per batch to a cap of 9. Page URLs are used **verbatim from the index**
— they already end in `.md` and serve raw markdown as-is; `md-suffix`, `index-md`, and
`txt-suffix` variants all 404, so there is no twin to construct. Page bodies span 25×: 10,628 B
(`troubleshooting.md`) to 272,484 B (`settings.md`), with `hooks.md` at 242,078 B against
2,423,751 B for the same page as HTML. Sibling file `llms-full.txt` is 6,556,407 B (~1.64M
tokens) — a full-text dump, never to be fetched.

**Why this design.** Index tier **T0**, content tier **C0**. T0 because 38,847 B ≤ the 40,000 B
threshold and prose coverage is 100% ≥ 60% — the whole index fits in one WebFetch, so no query
script, no `docs-source.json`, no cache layer. C0 with **no `url_template`**: this is the one
place a reflexive `{url_no_slash}.md` rule would break the skill. Rejected **T1**: the index has
exactly one section, so routing would mean inventing a taxonomy. Rejected **T2**: it would cut
per-question cost from ~9,700 to ~200 tokens, but T0's recall is free — all 174 descriptions
sit in context, which is why the vocabulary-mismatch case resolves with no escalation at all.
Rejected **T4**: no sitemap is published at the probed paths so coverage has no ratio, but 174
concrete `.md` leaf targets on the docs host make this a leaf-level index, not a hub list.

**What would overturn it.** The index crossing 40,000 B → move to T2 (copy `docs_query.py`, add
`docs-source.json` with `url_template` omitted, rewrite Procedure step 1 as `search`, keep the
step-3 ladder verbatim as it becomes load-bearing). This is the live risk: 38,847 B is **97% of
the threshold**, and the `whats-new/2026-wNN` weekly pages add roughly one entry per week on top
of new feature pages. Real `##` sections appearing → T1, preferable to T2 because the hierarchy
would be vendor-maintained. `.md` targets vanishing or 404ing → re-probe the content contract.
Descriptions decaying toward boilerplate → the T5 discussion. An official Anthropic docs MCP
server or search API shipping → this skill may become redundant or complementary; none exists
as of this entry.

**Rebuild must preserve.** The Chinese trigger phrases in `description` — the index is
English-only and no script can derive them. The area bullets under "When to use this skill",
hand-derived from slug clusters because the index offers only one section name. The out-of-scope
pointer to the `claude-api` skill, a local convention invisible to the docs site.

**Acceptance tests, run this date.** `hook` → 17 index matches across `hooks.md`,
`hooks-guide.md`, `agent-sdk/hooks.md`. Vocabulary mismatch `resume` → 0 title matches but 5
description matches, landing on `sessions.md` (*Manage sessions*) with no escalation needed.
Non-English `钩子` → 0 matches against 17 for `hook`; the translate-first rule this proves
necessary is now written into Procedure step 3. Content fetch `hooks.md` → 242,078 B of markdown.
