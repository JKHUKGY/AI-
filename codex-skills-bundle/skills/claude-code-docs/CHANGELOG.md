# Changelog

All notable changes to the `claude-code-docs` skill are documented here.

## [0.2.1] - 2026-07-30

Conformed the skill to `docs-skill-builder` 0.1.1's revised output spec (commit `3eec443`,
"Append-only mechanism log and translation rules"). No change to how the skill reads the docs —
the mechanism, the numbers, and the procedure are all identical to 0.2.0.

- Restructured `references/mechanism.md` into the **append-only log** format: a file header,
  newest entry on top, and the prescribed entry shape (verdict / how the site is read / why
  this design / what would overturn it / rebuild must preserve). The 0.2.0 fact-sheet dump was
  folded into prose to fit the format's word budget; the probe output is re-derivable by
  re-running the probe, so nothing measured was lost.
- Added the two missing translated pairs the spec now requires at every tier: `SKILL-cn.md`
  and `references/mechanism-cn.md`.
- Added `README.md` as the authoritative English half of the README pair, and re-synced
  `README-cn.md` as its translation. Previously the Chinese file was a standalone original
  with no English counterpart. **This changes the sibling convention** — `codex-docs` and
  `antigravity-docs` still ship Chinese-only READMEs and are now inconsistent with the spec.
- Each `-cn.md` file opens with the convention note: English is authoritative, maintenance
  flows one way. `SKILL.md` itself makes no mention of translations, per spec.

## [0.2.0] - 2026-07-30

Re-probed `code.claude.com` with `docs-skill-builder` and refreshed against the measurements.
The mechanism did not change — the index is alive, still T0, still C0 — but the facts drifted
and several rules were missing.

- Added `references/mechanism.md`: the first recorded fact sheet, the T0/C0 decision with the
  tiers it beat, invalidation triggers, hand-written assets a rebuild must preserve, and the
  acceptance-test results. Previously there was no record to check against.
- Index is now **174 entries / 38,847 B**, not the "~150" the skill claimed.
- Added the **translate-first rule**. Measured: the Chinese query `钩子` matches 0 index
  entries where `hook` matches 17 — a non-English miss was previously indistinguishable from
  "not documented".
- Added a synonym-expansion step with a measured example (`resume` appears in 0 titles but 5
  descriptions, under *Manage sessions*).
- Added measured page sizes (10,628 B – 272,484 B, a 25× spread) and the reason to send
  WebFetch a pointed question rather than "summarize this page".
- Added a guard against `llms-full.txt` (6,556,407 B / ~1.64M tokens), which sits one path
  away from the index the skill already fetches.
- Documented that index URLs already end in `.md` and must be used **verbatim** — appending a
  second `.md` 404s.
- Broadened the `description` to cover doc areas that shipped since 0.1.2: agent teams, agent
  view, workflows, worktrees, channels, routines, scheduled tasks, sandboxing, code review,
  computer use, and the desktop/web/mobile/Slack/Chrome surfaces.
- Added Chinese trigger phrases to the `description`.
- Pointed the escalation ladder at the weekly `whats-new/` pages for recently-shipped features.

## [0.1.2] - 2026-07-03

- Added a small-batch fetch loop: 1–3 pages per batch, evaluate whether that's enough, continue up to a 9-page cap, then ask the user before reading more.

## [0.1.1] - 2026-07-03

- Initial release.
