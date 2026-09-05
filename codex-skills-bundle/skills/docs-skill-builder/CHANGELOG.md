# Changelog

All notable changes to the `docs-skill-builder` skill are documented here.

## [0.1.2] - 2026-07-31

Fixes this skill's own frontmatter and hardens the output spec against the same defect.

- **Fixed `argument-hint` in `SKILL.md`.** It read
  `argument-hint: [build|check] <target-path> for <docs URL or product> [notes]`. In YAML a value
  beginning with `[` is a flow sequence, so it closed after `[build|check]` and the trailing text
  became an unanchored scalar — the whole document failed to parse, and plugin validation refused
  to tag the release. Now single-quoted. Every `SKILL.md` in the repo was re-parsed to confirm
  this was the only one broken; 18 others use an unquoted `[phrase]`, which is benign because a
  bare bracketed phrase is a valid one-element sequence.
- **Template now specifies quoting and explains why.** `references/skill-template.md` gained a
  frontmatter section, and its example uses `argument-hint: '[topic]'`. The rule extends to any
  value containing `: ` or starting with `{`, `&`, `*`, `!`, `|`, `>`, `%`, or `@`.
- **Phase 4 now opens by parsing the emitted frontmatter**, before any lookup test. This is the
  real hardening: the failure does not raise. A skill whose frontmatter fails to parse loads with
  **empty metadata** — no name, no description — so it never triggers, and every acceptance test
  after it would be measuring a skill the agent can no longer find. The parse error also points
  at line 2 rather than the offending line, so eyeballing it is not reliable.
- Added a matching rule: never ship frontmatter you have not parsed. `SKILL-cn.md`, `README.md`,
  and `README-cn.md` updated in the same pass.

## [0.1.1] - 2026-07-30

- Initial release. Builds (and re-verifies) `xxx-docs` lazy-loading documentation skills from
  a measured probe of the target site, rather than from assumptions about its layout.

### `scripts/probe_docs_source.py`

Pure-stdlib CLI following the project's Python CLI standard: typed `_main(...)` carrying the
logic, thin `main(argv)` doing argparse, `--arg_name` flags only, `sys.exit(main())` entry.
`_main` is importable and testable without the command line.

- **Rule registry.** Every convention it knows lives in a single `REGISTRY` of `IndexRule` /
  `ContentRule` / `SitemapRule`. Teaching it a new convention is one entry, not a code path.
- **Dataclass report.** The whole result is a dataclass tree (`ProbeReport`); `--json_out`
  writes exactly `dataclasses.asdict(...)`. Response bodies are excluded from the report.
- **Strongly-typed `Conclusion`.** A deterministic reading of the thresholds at the top of the
  file — `index_tier_hint`, `content_tier_hint`, `content_url_template`, `coverage_verdict`,
  plus `needs_manual_discovery`, which flags that the conventional locations came up empty and
  a web search is required. It is a starting point for the agent, not a decision.
- Bounded (~28 requests) and throttled, with the budget surfaced in the report.
- Calibrates against a deliberately bogus URL, so hosts that answer `200` for missing paths are
  classified correctly. Verified against `docs.databricks.com`, whose 404 is a consistent
  12,999-byte `text/html` body.
- Rejects auth walls: a `200` served from `/login?next=…` is not evidence a file exists
  (observed on `vercel.com/llms-full.txt`).
- Reports **index coverage** — index entries vs sitemap URLs. Databricks lists 252 entries
  against 5,645 sitemap URLs (4.5%), identifying its `llms.txt` as a curated hub index and
  forcing a second-hop design that entry counts alone would have hidden.
- Tests six content conventions against a real in-scope leaf page, and picks the winner by
  **registry preference order rather than size** — on `vercel.com/docs`, `index-md` returns a
  1,191-byte stub where the correct `md-suffix` twin returns 4,991 bytes. Warns when two
  plain-text variants disagree by more than 2×.

### `assets/docs_query.py`

The runtime copied verbatim into each produced skill, driven by a per-site `docs-source.json`
so the spec lives in data and not in forked code.

- `search` / `sections` / `section` / `get` / `stats` / `refresh` over `llms-txt` or `sitemap`
  indexes. Filtering happens outside the model's context, so cost tracks matches, not index
  size.
- Caches the index under `~/.cache/claude-docs-skills/` with a 24 h TTL — repeat queries cost
  zero requests (measured 1.97 s → 0.156 s on Vercel's 202 KB index) — and falls back to a
  stale cache when the network fails.
- On a miss it prints the recall ladder instead of returning silently, which is what stops an
  agent from reporting "not documented" when it merely used the wrong word.

### References

- `references/mechanism-catalog.md` — six index tiers (T0 inline → T5 pre-built manifest) and
  three content tiers, each keyed to a probe number; the recall ladder; the levels-vs-recall
  tradeoff; the conditions that justify crawling; and the acceptance test.
- `references/skill-template.md` — file set, `docs-source.json` schema, and the SKILL.md
  skeleton for produced skills, including the mandatory context-budget table.
- Measured worked examples baked into the catalog: Vercel (202 KB index, 86% bare
  descriptions, `.md` twin at 4,991 B vs 916,562 B of HTML — 99% cheaper) and Databricks
  (47 KB index, 98% prose, HTML-only content at 50,782 B/page).

### Docs

- `SKILL.md` (authoritative) with `SKILL-cn.md`, and `README.md` (authoritative) with
  `README-cn.md`. Phase 1 is split into a mechanical half (the probe, which only checks
  conventional locations) and a human half (web search, source-repo hunt, vendor tooling
  check) that is explicitly not optional.
- `SKILL.md` says nothing about the translation existing: it is the published artifact and the
  text loaded into the agent's context, so the convention lives only in `SKILL-cn.md`, which
  also records that maintenance flows one way. `references/skill-template.md` imposes the same
  rule on generated skills.
- Produced skills ship three translated pairs, all required: `SKILL.md`, `README.md`, and
  `references/mechanism.md`, each with a `-cn.md` counterpart written in the same pass.
- `references/mechanism.md` is an append-only log rather than a static record — newest entry
  on top, one entry per `build` and per `check` (including no-change checks), past entries
  never rewritten. Entry length is budgeted by how much moved (≤1000 / ≤500 / ≤200 words) so
  the file stays readable after many iterations, and a no-change entry is forbidden from
  restating the mechanism.
