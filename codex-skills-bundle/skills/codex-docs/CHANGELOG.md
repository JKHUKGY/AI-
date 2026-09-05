# Changelog

All notable changes to the `codex-docs` skill are documented here.

## [0.1.3] - 2026-07-30

Backfilled the files that `docs-skill-builder` 0.1.1 now requires of every produced skill. **No
change to how the skill reads the docs** — no probe was run and `SKILL.md` is untouched. This was
a documentation backfill only, at the owner's explicit instruction not to update the skill itself.

- Added `references/mechanism.md` as an append-only mechanism log, with a first entry marked
  **reconstruction** rather than measurement. Unlike `antigravity-docs` there is no local
  artifact to measure here, so the entry contains nothing measured today: the ~840-line hub
  index, the ~137 Codex entries, the ~132 reachable, and the ~5 stale ones are all inherited
  from the 2026-07-29 repair. The entry says so, and the next real `check` must run the probe
  and append a measured entry.
- Recorded the tier decision the skill had been implementing without stating: index **T1**
  (routed by the vendor's own `## Codex —` / `## Plugins —` sections, because the hub index is
  mostly other product lines), content **C0** (`.md` twins, reached through a two-call cross-host
  redirect). Also recorded why the obvious index was rejected — `codex/llms.txt` 308s to a 404,
  and the new host offers only a description-less sitemap that would drop the skill to T3.
- Added the translated counterparts the spec requires at every tier: `SKILL-cn.md`,
  `references/mechanism-cn.md`, and `README.md` as the authoritative English half of the README
  pair. `README-cn.md` gained the convention note (English is authoritative, maintenance flows
  one way).

## [0.1.2] - 2026-07-29

- Fixed the skill, which had gone completely dark at step 1: OpenAI moved the Codex documentation body to `learn.chatgpt.com/docs/`, and the blanket 308 redirect on the old host swept up `codex/llms.txt` too, sending it to a target that does not exist (404). The new host publishes no `llms.txt` of its own.
- Switched the index to the hub-wide `https://developers.openai.com/llms.txt`, which absorbed the whole Codex map into `## Codex — <Topic>` sections in the same `- [Title](URL): description` format. Step 1 now narrows to the `## Codex —` and `## Plugins —` families, since the hub index spans several unrelated product lines.
- Documented the two-call fetch: `WebFetch` does not follow cross-host redirects, so a `developers.openai.com/codex/<slug>.md` page takes one call to learn the redirect and a second to read `learn.chatgpt.com/docs/<slug>.md`. The pair counts as one page against the 9-page cap, and the `learn.chatgpt.com` URL is the one to cite.
- Warned that the new slugs are not a straight host swap (`codex/skills.md` lands on `docs/build-skills.md`, `codex/config-reference.md` on `docs/config-file/config-reference.md`), so a `learn.chatgpt.com` URL must never be hand-assembled.
- Noted that roughly 5 of the index's 137 Codex entries are stale upstream and 404 even after the redirect; treat those as missing pages rather than repairing the slug.
- Widened scope from `developers.openai.com/codex/*` to the Codex product family across hosts, and added plugins and marketplaces (`developers.openai.com/plugins/*`, which fetch directly) to the description and the in-scope list.

## [0.1.1] - 2026-07-03

- Initial release.
- Lazy-loads OpenAI Codex docs from `https://developers.openai.com/codex/llms.txt`.
- Small-batch fetch loop: 1–3 pages per batch, evaluate, continue up to a 9-page cap, then ask the user before reading more.
