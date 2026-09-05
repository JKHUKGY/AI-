#!/usr/bin/env python3
"""
Build .claude/skills/coding-agent-docs/skills/antigravity-docs/references/docs-manifest.json
from the live Antigravity web app.

Strategy (v2, 2026-07): antigravity.google/docs/* used to be a client-rendered SPA
with no fetchable per-page content, so the old builder reverse-engineered a
`DOCS_STRUCTURE` array out of the app's JS bundle and pointed at a separate
`/assets/docs/<path>/<filename>.md` twin for content. Antigravity has since
rebuilt the site as a server-rendered Astro app: `/docs/<slug>` now returns
real HTML with the doc body baked in, and the old JS-bundle/`.md`-twin URLs
are gone (404). So v2 does this instead:

  1. `llms.txt` still lists every doc page under "## Documentation", grouped
     by "### <product>" headings, as `- [Title](https://antigravity.google/docs/<slug>): desc`.
     This is the authoritative page list now (no bundle needed). Its
     descriptions are boilerplate ("Learn about X"), so they're only a fallback.
  2. Each page is fetched directly and scraped for three things pulled out of
     server-rendered HTML: the breadcrumb trail (`docs-main-content` nav —
     richer than llms.txt's flat section), the `<h1>` title, and the first
     substantial `<p>` after that `<h1>` as a real description.

     Each of those is a selector against markup this project does not control,
     so each can go stale silently. `report_fallbacks()` exists to make that
     loud: a field that falls back on most pages is reported as a stale
     selector, not buried in a successful-looking build.
  3. `content_url` in the manifest is just the page URL itself
     (`https://antigravity.google/docs/<slug>`) — it is now directly
     fetchable (WebFetch renders the SSR HTML fine), so `antigravity-docs`
     no longer needs a separate asset URL.

Usage:
    python3 build_manifest.py            # rebuild; no-op if llms.txt unchanged
    python3 build_manifest.py --force    # rebuild even if llms.txt hash matches
"""
import argparse
import gzip
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://antigravity.google"
LLMS_URL = f"{BASE}/llms.txt"
REQUEST_DELAY_SECONDS = 0.15

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "coding-agent-docs", "skills", "antigravity-docs",
    "references", "docs-manifest.json"))

GENERATED_AT = os.environ.get("ANTIGRAVITY_BUILD_DATE", "").strip()

LINK_RE = re.compile(
    r'-\s*\[([^\]]+)\]\(https://antigravity\.google/docs/([^)]+)\):\s*(.*)')
BREADCRUMB_RE = re.compile(
    r'<ul class="call-to-action--nav breadcrumb-list"[^>]*>(.*?)</ul>', re.S)
BC_SECTION_RE = re.compile(r'<li class="breadcrumb-section"[^>]*>(.*?)</li>', re.S)
BC_CURRENT_RE = re.compile(r'<li class="breadcrumb-current"[^>]*>(.*?)</li>', re.S)
H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)
# The lead paragraph is the first substantial <p> after the body's first <h1>.
# Two traps this encodes, both hit in the wild:
#   - `<p[^>]*>` also matches SVG `<path d="...">`; the \b is what keeps it honest.
#   - the page's nav emits its own <p> elements *before* the doc body, so the
#     search has to start at the <h1>, not at the top of the document.
PARA_RE = re.compile(r'<p\b[^>]*>(.*?)</p>', re.S)
MIN_DESCRIPTION_CHARS = 20
ANCHOR_RE = re.compile(r'<a[^>]*class="deep-link-anchor".*?</a>', re.S)
TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'\s+')


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "Accept-Encoding": "gzip",
        "User-Agent": "antigravity-docs-index-builder",
    })
    raw = urllib.request.urlopen(req, timeout=45).read()
    if raw[:2] == b"\x1f\x8b":  # gzip magic
        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    return raw.decode("utf-8", "replace")


def clean(html_fragment: str) -> str:
    text = ANCHOR_RE.sub("", html_fragment)
    # Substitute a space, not "": dropping tags outright welds the text on
    # either side together ("Antigravity 2.0Antigravity CLI" on /docs/enterprise).
    # The following whitespace collapse puts it back to single spaces.
    text = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", html.unescape(text)).strip()


DESCRIPTION_CAP = 280


def truncate_description(text: str) -> str:
    """Keep the manifest scannable for triage: cap at DESCRIPTION_CAP chars,
    preferring a sentence or word boundary over a hard cut."""
    if len(text) <= DESCRIPTION_CAP:
        return text
    sentence_end = text.rfind(". ", 0, DESCRIPTION_CAP)
    if sentence_end != -1 and sentence_end > DESCRIPTION_CAP * 0.4:
        return text[:sentence_end + 1]
    word_end = text.rfind(" ", 0, DESCRIPTION_CAP)
    cut = word_end if word_end > DESCRIPTION_CAP * 0.4 else DESCRIPTION_CAP
    return text[:cut].rstrip(".,;: ") + "…"


def parse_llms_doc_pages(text: str):
    """Parse '## Documentation' into ordered {section, title, slug, fallback_description},
    deduped by slug (first occurrence wins — some pages like MCP are cross-listed
    under several product sections)."""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Documentation")
    except StopIteration:
        sys.exit("ERROR: '## Documentation' section not found in llms.txt — "
                  "the page format changed, inspect it manually.")

    section = None
    seen = set()
    out = []
    for line in lines[start + 1:]:
        s = line.strip()
        if s.startswith("## "):
            break
        if s.startswith("### "):
            section = s[4:].strip()
            continue
        m = LINK_RE.match(s)
        if not m:
            continue
        title, slug, desc = m.group(1).strip(), m.group(2).rstrip("/"), m.group(3).strip()
        if slug in seen:
            continue
        seen.add(slug)
        out.append({"section": section or "", "title": title, "slug": slug,
                     "fallback_description": desc})

    if not out:
        sys.exit("ERROR: no documentation pages parsed from llms.txt — "
                  "the list format changed, inspect it manually.")
    return out


def scrape_page(url: str):
    """Return (section_path, title, description), any of which may be None
    if the expected markup isn't found on the page."""
    html = fetch(url)

    section_path = None
    bc_m = BREADCRUMB_RE.search(html)
    if bc_m:
        parts = [clean(s) for s in BC_SECTION_RE.findall(bc_m.group(1))]
        cur_m = BC_CURRENT_RE.search(bc_m.group(1))
        if cur_m:
            parts.append(clean(cur_m.group(1)))
        parts = [p for p in parts if p]
        section_path = " / ".join(parts) if parts else None

    h1_m = H1_RE.search(html)
    title = clean(h1_m.group(1)) if h1_m else None

    description = None
    if h1_m:
        for para_m in PARA_RE.finditer(html, h1_m.end()):
            text = clean(para_m.group(1))
            if len(text) >= MIN_DESCRIPTION_CHARS:
                description = truncate_description(text)
                break

    return section_path, title, description


FIELD_SELECTORS = {
    "section": "BREADCRUMB_RE / BC_SECTION_RE / BC_CURRENT_RE",
    "title": "H1_RE",
    "description": "PARA_RE (first substantial <p> after the first <h1>)",
}
# Above this share of pages, a fallback is a stale selector rather than a
# per-page quirk. Widespread fallback is the failure mode worth shouting about:
# the manifest still builds, so nothing else in the run looks wrong.
STALE_SELECTOR_THRESHOLD = 0.5


def report_fallbacks(fell_back, total, fetch_failure_count):
    """Print what the scrape did not find. Loudly, when a whole field is gone."""
    if not total:
        return
    print("\nScrape coverage:")
    for field, slugs in fell_back.items():
        got = total - len(slugs)
        print(f"  {field:12} {got}/{total} scraped"
              + (f"  ({len(slugs)} fell back to llms.txt)" if slugs else ""))

    for field, slugs in fell_back.items():
        # Pages that never loaded fall back on every field; that is already
        # reported above as a fetch failure, so don't blame the selector twice.
        if len(slugs) - fetch_failure_count <= 0:
            continue
        if len(slugs) / total < STALE_SELECTOR_THRESHOLD:
            continue
        print(f"\n  {'!' * 72}")
        print(f"  WARNING: '{field}' fell back on {len(slugs)}/{total} pages that fetched fine.")
        print(f"  That is a stale selector, not a per-page quirk. The manifest was still")
        print(f"  written, but its '{field}' column now carries llms.txt boilerplate.")
        print(f"  Check {FIELD_SELECTORS[field]} against the current page HTML before")
        print(f"  treating this build as good. Examples: {', '.join(slugs[:3])}")
        print(f"  {'!' * 72}")


def load_existing():
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def diff(old, new_pages):
    old_slugs = {p["slug"] for p in (old or {}).get("pages", [])}
    new_slugs = {p["slug"] for p in new_pages}
    added = sorted(new_slugs - old_slugs)
    removed = sorted(old_slugs - new_slugs)
    return added, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                     help="rebuild even if llms.txt is unchanged since the last build")
    args = ap.parse_args()

    existing = load_existing()

    print(f"Fetching {LLMS_URL} ...")
    llms_text = fetch(LLMS_URL)
    llms_sha256 = hashlib.sha256(llms_text.encode("utf-8")).hexdigest()

    if (existing and not args.force
            and existing.get("_meta", {}).get("llms_sha256") == llms_sha256):
        print("llms.txt unchanged since last build — docs list is up to date. "
              "Nothing to do. (Use --force to rebuild anyway; page bodies can "
              "change without the index changing.)")
        return

    entries = parse_llms_doc_pages(llms_text)
    print(f"  {len(entries)} documentation page(s) listed in llms.txt")

    pages = []
    scrape_failures = []
    # Track per-field fallbacks separately from fetch failures. A selector that
    # stops matching degrades every page at once while every fetch still
    # succeeds, so counting only exceptions reports a clean build on a manifest
    # that has quietly lost a field -- which is exactly how the description
    # scrape stayed broken from 2026-07-25 to 2026-07-30.
    fell_back = {"section": [], "title": [], "description": []}
    for i, e in enumerate(entries, 1):
        url = f"{BASE}/docs/{e['slug']}"
        section_path = title = description = None
        try:
            section_path, title, description = scrape_page(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as ex:
            scrape_failures.append((e["slug"], str(ex)))
        for field, scraped in (("section", section_path), ("title", title),
                                ("description", description)):
            if not scraped:
                fell_back[field].append(e["slug"])
        pages.append({
            "section": section_path or e["section"],
            "slug": e["slug"],
            "title": title or e["title"],
            "description": description or e["fallback_description"],
            "content_url": url,
        })
        print(f"  [{i}/{len(entries)}] {e['slug']}")
        time.sleep(REQUEST_DELAY_SECONDS)

    if scrape_failures:
        print(f"\n  NOTE: {len(scrape_failures)} page(s) failed to fetch and fell back "
              f"to llms.txt title/section/description:")
        for slug, err in scrape_failures:
            print(f"    - {slug}: {err}")

    report_fallbacks(fell_back, len(entries), len(scrape_failures))

    manifest = {
        "_meta": {
            "generated_at": GENERATED_AT or "unknown",
            "index_url": LLMS_URL,
            "llms_sha256": llms_sha256,
            "content_url_template": f"{BASE}/docs/{{slug}}",
            "page_count": len(pages),
            "builder_skill": "antigravity-docs-index-builder",
            "note": ("Auto-generated from antigravity.google/llms.txt (page list) "
                     "plus a per-page HTML scrape (breadcrumb section, <h1> title, "
                     "lead paragraph) of each server-rendered /docs/<slug> page. "
                     "content_url is the page URL itself — fetch it directly, no "
                     "separate asset twin. Do not hand-edit; regenerate with "
                     "/antigravity-docs-index-builder."),
        },
        "pages": pages,
    }

    added, removed = diff(existing, pages)
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nWrote {MANIFEST_PATH}")
    print(f"  pages: {len(pages)}")
    if existing:
        print(f"  added:   {added or '(none)'}")
        print(f"  removed: {removed or '(none)'}")
    else:
        print("  (first build — no previous manifest to diff against)")


if __name__ == "__main__":
    main()
