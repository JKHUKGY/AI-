# Changelog

All notable changes to the `antigravity-docs-index-builder` skill are documented here.

## [0.2.2] - 2026-07-30

Fixes a description scrape that had been silently falling back to `llms.txt` boilerplate since
0.2.1, and the reporting gap that let it go unnoticed for five days.

- **Fixed the lead-paragraph selector.** `DESC_RE` matched
  `<div class="caption template-content-paragraph">`, a class that no longer appears anywhere in
  the page HTML — verified zero occurrences on a live fetch of `/docs/rules-workflows`. Replaced
  with `PARA_RE`: the first `<p>` of at least 20 characters after the body's first `<h1>`.
  Verified against 10 live pages spanning Antigravity 2.0, CLI, IDE, SDK, Home, FAQ, and
  Enterprise — all 10 now yield a real description where all 10 previously yielded
  `Learn about X.`. Two traps are encoded in the regex and its comment: `<p[^>]*>` also matches
  SVG `<path …>` (hence `\b`), and the page nav emits its own `<p>` elements before the doc body
  (hence anchoring the search at the `<h1>`).
- **Made a stale selector impossible to miss.** `scrape_failures` only ever recorded network
  exceptions, so a regex matching nothing degraded all 81 pages while the build reported
  success. Added `report_fallbacks()`: every run now prints a `Scrape coverage` block
  (`n/total scraped` per field), and a field that falls back on more than half the pages that
  fetched fine gets a boxed warning naming the regex to check. Fetch failures are subtracted
  first, so pages that 404 do not get blamed on a selector.
- **`clean()` no longer welds words together or leaks HTML entities.** Tags are replaced with a
  space rather than deleted (`/docs/enterprise` produced "Antigravity 2.0Antigravity CLI"), and
  the result goes through `html.unescape` ("Background tasks &amp; subagents" → "&").
- `SKILL.md` updated: the coverage block must be read before calling a build good, `DESC_RE` →
  `PARA_RE` in the troubleshooting pointers, request count ~77 → ~81, and a note that `curl`
  needs `--compressed` because this server gzips unconditionally.

## [0.2.1] - 2026-07-25

- Rewrote the builder for Antigravity's site rewrite: `antigravity.google/docs/*` moved from a client-rendered SPA (JS bundle + `.md` asset twins) to a server-rendered Astro app. Both of the old strategy's URLs 404 now.
- New source of truth: parses the page list from `llms.txt`'s `## Documentation` section (no more JS bundle reverse-engineering).
- New content strategy: scrapes each `/docs/<slug>` page directly for its breadcrumb section, `<h1>` title, and lead-paragraph description (capped at 280 chars) — richer than `llms.txt`'s boilerplate per-page descriptions.
- `content_url` is now the page URL itself; consumers (`antigravity-docs`) WebFetch it directly instead of a separate `/assets/docs/....md` twin.
- Change-detection short-circuit now hashes `llms.txt` content instead of the JS bundle filename.
- 77 pages at time of writing (11 new CLI pages picked up: slash commands, `cli/modes`, `cli/projects`).

## [0.1.1] - 2026-07-03

- Initial release.
- Extracts `DOCS_STRUCTURE` from the Antigravity web app JS bundle (`main-<hash>.js`) and joins titles/descriptions from `llms.txt` on `slug`.
- Writes `.claude/skills/antigravity-docs/references/docs-manifest.json` (66 pages at time of writing; bundle `main-C7HXKFZQ.js`).
- Short-circuits when the bundle hash is unchanged; `--force` to override. Prints an added/removed page diff versus the previous manifest.
