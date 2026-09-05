---
name: antigravity-docs-index-builder
description: Rebuild the docs-manifest.json that the antigravity-docs skill relies on, by parsing the page list from antigravity.google/llms.txt and scraping each server-rendered /docs/<slug> page for its breadcrumb, title, and lead-paragraph description. Use when Antigravity has shipped new/renamed/removed doc pages, when antigravity-docs reports a stale or missing page, or when you simply want to refresh the manifest. Manually invoked (e.g. /antigravity-docs-index-builder).
argument-hint: [--force]
allowed-tools: Bash, Read, Write
---

# Antigravity Docs Index Builder

Regenerates `.claude/skills/coding-agent-docs/skills/antigravity-docs/references/docs-manifest.json` — the static index that the **`antigravity-docs`** skill (published as part of the `coding-agent-docs` plugin) reads to answer questions. This is a maintenance skill you run by hand whenever the Antigravity docs may have changed; `antigravity-docs` itself never runs it.

## Why this skill has to exist

`antigravity.google/docs/*` used to be a **client-rendered SPA** — a plain fetch of a doc page returned an empty shell, so the only way to build a page list was to reverse-engineer a `DOCS_STRUCTURE` array out of the app's JS bundle, and content had to be fetched from a separate `/assets/docs/<path>/<filename>.md` twin.

As of 2026-07 Antigravity rebuilt the site as a **server-rendered Astro app**. `/docs/<slug>` now returns real HTML with the doc body baked in — no bundle, no `.md` twin, both of the old URLs 404 now. So this builder instead:

1. Fetches **`llms.txt`**, which lists every doc page under `## Documentation` as `- [Title](https://antigravity.google/docs/<slug>): description`, grouped by `### <product>` headings — this is now the authoritative page list (no bundle needed). Its descriptions are boilerplate ("Learn about X"), so they're only a fallback.
2. Fetches **each page directly** and scrapes three things out of the server-rendered HTML:
   - the breadcrumb trail (`docs-main-content` nav) — richer than llms.txt's flat section, e.g. `Antigravity 2.0 / Customizations / Skills`
   - the `<h1>` title
   - the lead paragraph — the first substantial `<p>` after that `<h1>` — as a real description, capped at 280 chars
3. Records `content_url` as **the page URL itself** (`https://antigravity.google/docs/<slug>`) — it's directly fetchable now (WebFetch renders the SSR HTML fine), so `antigravity-docs` no longer needs a separate asset URL.

## Procedure

### 1. Run the builder script

```
python3 .claude/skills/antigravity-docs-index-builder/scripts/build_manifest.py
```

- Set today's date so the manifest is stamped:
  `ANTIGRAVITY_BUILD_DATE=<YYYY-MM-DD> python3 .../build_manifest.py`
- Pass `--force` (or `$ARGUMENTS`) to rebuild even when `llms.txt` is unchanged.

What it does: fetches `llms.txt` and **short-circuits if its hash matches the one already recorded in the manifest** (page list unchanged → nothing to do — note this only catches list changes; a page's body can be edited without llms.txt changing, so `--force` periodically is reasonable). Otherwise it parses the page list, fetches every `/docs/<slug>` page (~81 requests, throttled), scrapes breadcrumb/title/description from each, and writes the manifest — printing the added/removed page slugs versus the previous version, any pages that failed to fetch, and a **Scrape coverage** block reporting how many pages yielded each field.

### 2. Report the result

Relay to the user: the page count, the added/removed diff, and the **Scrape coverage** numbers. If pages were added or removed, that's the signal that `antigravity-docs` now covers new material (or dropped stale slugs).

**Read the coverage block before calling the build good.** Three fields, each `n/total scraped`. Anything short of full coverage on `section`, `title`, or `description` that isn't explained by a fetch failure means a selector is drifting. If a field falls back on more than half the pages that fetched fine, the script prints a boxed `WARNING: '<field>' fell back on n/total pages` naming the regex to check — do not relay a build carrying that warning as a success.

### 3. If the script errors

The script fails loudly (rather than writing a bad manifest) if the page-list format changes:

- **"'## Documentation' section not found in llms.txt"** or **"no documentation pages parsed"** — `llms.txt`'s structure changed. `curl -s https://antigravity.google/llms.txt` and re-derive `parse_llms_doc_pages`'s heading/line regex.

A scrape failure on an individual page is **not** fatal — it's logged and that page falls back to llms.txt-derived fields. If breadcrumb/title/description come back empty for most or all pages (not just a few flaky ones), the site's HTML structure changed; the Scrape coverage block will say so explicitly. To fix: `curl -s --compressed <a /docs/<slug> URL> -o page.html` and re-derive `BREADCRUMB_RE`/`H1_RE`/`PARA_RE` from the current markup around `docs-main-content`.

Note that `--compressed` is not optional: this server gzips even when asked not to, so a bare `curl` hands you gzip bytes that look like binary garbage.

Fix the script, re-run, and note what changed in this skill's `CHANGELOG.md`.

## Rules

- **Never hand-edit `docs-manifest.json`.** It is generated. Any manual fix will be silently overwritten on the next run — fix the builder instead.
- **Raw fetch, not WebFetch, when scraping HTML markup.** The builder needs the exact markup (`breadcrumb-list`, `<h1>`, the paragraphs after it) to regex out of raw HTML; a markdown-converting fetcher would lose that structure. That's why this skill uses `Bash`, not `WebFetch`.
- **A widespread fallback is a broken selector, not noise.** A page or two failing (timeout, transient 5xx) is fine and falls back gracefully. A field falling back on *most* pages means the site's HTML changed. This is the failure mode that costs the most, because the build still succeeds and the manifest still looks complete — it just quietly carries `Learn about X.` in the column you were relying on. Exactly that happened between 2026-07-25 and 2026-07-30, undetected. The Scrape coverage block exists so it cannot happen silently again; do not paper over it.
- **Don't widen scope.** This builder only writes the manifest for `antigravity-docs`. It does not fetch or cache full page content — that's `antigravity-docs`' job at answer time.
