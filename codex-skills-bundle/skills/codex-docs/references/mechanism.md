# codex-docs — mechanism log

How this skill reads OpenAI Codex's documentation, and why. Newest entry first; the top entry
describes the current mechanism. Entries are appended, never rewritten.

## 2026-07-30 — reconstruction

**Verdict.** This entry is a **reconstruction, not a measurement.** The skill predates the
mechanism-log requirement and shipped without one, and the owner explicitly asked that it not
be re-probed or updated as part of writing this file. Everything below is recovered from the
shipped `SKILL.md`, `README-cn.md`, and `CHANGELOG.md`; every number in it was established by
the 2026-07-29 repair work and has **not** been re-verified today. There is no local artifact
here to measure against, so unlike `antigravity-docs` this entry contains nothing freshly
measured at all. The next real `check` must run the probe and append a properly measured entry.

**How the site is read.** The index is the hub-wide `https://developers.openai.com/llms.txt` —
roughly 840 lines spanning several unrelated OpenAI product lines, grouped as
`## <Product> — <Topic>`, in the usual `- [Title](URL): description` form. The skill narrows to
two families, `## Codex — <Topic>` and `## Plugins — <Topic>`, and then loads *all* their
entries at once and searches across them; the per-topic grouping is page layout, not a reason
to pre-filter further. Recorded at the time: about 137 Codex entries, of which roughly 132 are
reachable. Content pages are `.md` twins, but reaching them takes two calls: a
`developers.openai.com/codex/<slug>.md` URL 308-redirects to `learn.chatgpt.com/docs/<slug>.md`,
and WebFetch does not follow cross-host redirects — it returns the target instead. So the first
call learns the redirect, the second reads the page; the pair counts as one page against the
9-page cap, and the `learn.chatgpt.com` URL is the one to cite. Plugin-authoring pages under
`developers.openai.com/plugins/<path>.md` are the exception and fetch directly.

**Why this design.** Index tier **T1** (section-routed), content tier **C0** (plain-text `.md`
twins). T1 rather than T0 because the hub index is not a Codex index: most of it is OpenAI API,
Ads, Workspace Agents, and Agentic Commerce, so loading it whole would spend most of the budget
on out-of-scope material. The `## Codex —` / `## Plugins —` grouping is the vendor's own
hierarchy, which is exactly the kind of routing the catalog prefers — maintained upstream, always
current, nothing invented locally. The deliberate limit is that routing stops at the family
level: within Codex and Plugins everything loads flat, because narrowing by topic header would
reintroduce a blind routing decision for no saving worth having.

**Why not the obvious index.** `https://developers.openai.com/codex/llms.txt` is dead: a blanket
308 on the old host rewrites it to `https://learn.chatgpt.com/docs/llms.txt`, which 404s.
`codex/llms-full.txt` behaves the same way. The developer hub's own root index still advertises
the broken `codex/llms.txt` link, so following it leads nowhere. The new host publishes no
`llms.txt` of its own — only a `sitemap-index.xml` with no descriptions, which would drop the
skill to T3 and destroy triage-by-description. That is what forced the move up to the hub index.

**What would overturn it.** `learn.chatgpt.com` publishing its own `llms.txt` with descriptions
→ re-point the index there and drop the two-call redirect dance entirely; the single largest
simplification available. The 308 redirects being retired once the migration settles → one call
per page instead of two, halving fetch cost. The hub renaming or restructuring its `## Codex —`
section headers → step 1's prompt stops matching and the skill goes dark at the index, exactly
the failure mode of the 2026-07-29 outage. The hub index growing past a comfortable inline read
→ T2, a script that searches the cached index instead of WebFetching sections.

**Rebuild must preserve.** The two-call redirect procedure and the rule that the pair counts as
one page — nothing in any index states this, and without it the agent reads a `REDIRECT
DETECTED` response as an error. The prohibition on hand-assembling a `learn.chatgpt.com` URL,
which exists because the slug map is not a host swap (`codex/skills.md` → `docs/build-skills.md`,
`codex/config-reference.md` → `docs/config-file/config-reference.md`). The note that roughly 5
index entries are stale upstream and 404 even after the redirect, so the agent treats them as
missing pages instead of trying to repair the slug. And the definition of scope **by product
line** — the `## Codex —` and `## Plugins —` families on whatever host currently serves them —
rather than by URL prefix, which is what stops the next migration taking the skill down.

**Acceptance tests.** Not run. This pass was a file backfill under an explicit no-update
instruction; claiming a pass would be claiming a test that never executed. In particular the
~137/~132 entry counts and the 5 stale entries are inherited figures, not today's.
