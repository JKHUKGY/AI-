#!/usr/bin/env python3
"""
Generic, config-driven query tool for an `xxx-docs` skill. Pure stdlib.

Copied verbatim into each produced skill as `scripts/docs_query.py` and paired
with a sibling `docs-source.json` that declares the site's contract. The script
is the same everywhere; only the JSON differs. That is deliberate -- the spec
lives in data, so a site's mechanism can be re-declared without new code.

The point of every command here is that filtering happens OUTSIDE the model's
context: a 200 KB index goes through the pipe, and only matching lines are
printed. Cost is proportional to what matched, not to the index.

The index is cached under the user cache dir with a TTL, so repeated queries in
a session cost zero network requests. The cache is derived and disposable --
delete it any time. It is NOT a build artifact and must never be committed.

Commands:
    sections                 list section names, entry counts, byte sizes
    search <pat> [pat ...]   regex search over entries (multiple = OR)
    section <name>           print every entry in one section
    get <url>                fetch a page as plain text (if the site offers it)
    stats                    index size, cache age, token estimates
    refresh                  force re-download the index
"""
import argparse
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "docs-source.json")
DEFAULT_TTL = 86400

ENTRY_RE = re.compile(r'^\s*[-*]\s*\[([^\]]*)\]\(\s*([^)\s]+)[^)]*\)\s*(?:[:—-]\s*(.*))?$')
LOC_RE = re.compile(r'<loc>\s*([^<]+?)\s*</loc>', re.I)


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"config not found: {path}\nThis skill is incomplete -- rebuild it with "
            f"/docs-skill-builder.")
    except json.JSONDecodeError as e:
        die(f"config is not valid JSON ({path}): {e}")


def fetch(url, headers=None, timeout=45):
    hdrs = {"User-Agent": "claude-docs-skill", "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        final = r.geturl()
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except OSError:
            pass
    return raw.decode("utf-8", "replace"), final


def cache_path(cfg):
    root = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    d = os.path.join(root, "claude-docs-skills", cfg.get("name", "docs"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "index.txt")


def get_index(cfg, refresh=False):
    """Return (text, age_seconds, from_cache). Downloads at most once per TTL."""
    ix = cfg.get("index") or {}
    url = ix.get("url") or die("config.index.url is missing")
    ttl = int(ix.get("cache_ttl_seconds", DEFAULT_TTL))
    path = cache_path(cfg)

    if not refresh and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < ttl:
            with open(path, encoding="utf-8") as f:
                return f.read(), age, True

    try:
        text, _ = fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        if os.path.exists(path):  # stale cache beats no answer
            with open(path, encoding="utf-8") as f:
                print(f"warning: could not refresh index ({e}); using cached copy",
                      file=sys.stderr)
                return f.read(), time.time() - os.path.getmtime(path), True
        die(f"could not fetch index {url}: {e}")

    if (ix.get("format") or "llms-txt") == "sitemap":
        text = "\n".join(f"- [{urllib.parse.urlsplit(u).path.strip('/') or u}]({u})"
                         for u in LOC_RE.findall(text))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text, 0.0, False


def parse_entries(text):
    """Yield dicts of {section, title, url, desc, line} for every index entry."""
    section = "(root)"
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip()
            continue
        if s.startswith("### ") and len(s) > 4:
            section = f"{section} / {s[4:].strip()}" if section != "(root)" else s[4:].strip()
            continue
        m = ENTRY_RE.match(s)
        if not m:
            continue
        out.append({"section": section, "title": (m.group(1) or "").strip(),
                    "url": m.group(2).strip(), "desc": (m.group(3) or "").strip(),
                    "line": s})
    return out


def fmt(e, width=140, show_section=True):
    head = f"[{e['section']}] " if show_section else ""
    body = f"{e['title']} :: {e['url']}"
    if e["desc"]:
        d = e["desc"]
        if len(d) > width:
            d = d[:width].rstrip() + "…"
        body += f" :: {d}"
    return head + body


def cmd_sections(cfg, args):
    text, age, cached = get_index(cfg, args.refresh)
    entries = parse_entries(text)
    agg = {}
    for e in entries:
        a = agg.setdefault(e["section"], {"n": 0, "b": 0})
        a["n"] += 1
        a["b"] += len(e["line"]) + 1
    if not agg:
        die("no entries parsed from the index -- the upstream format changed. "
            "Re-run /docs-skill-builder check.")
    print(f"{len(entries)} entries in {len(agg)} sections "
          f"(index {len(text):,} B, cache age {int(age)}s)\n")
    for name, a in sorted(agg.items(), key=lambda kv: -kv[1]["b"]):
        print(f"  {a['b']:>7,} B  ~{a['b']//4:>6,} tok  {a['n']:>4} entries  {name}")


def cmd_search(cfg, args):
    text, age, cached = get_index(cfg, args.refresh)
    entries = parse_entries(text)
    try:
        pats = [re.compile(p, re.I) for p in args.pattern]
    except re.error as e:
        die(f"bad regex: {e}")
    hits = [e for e in entries
            if any(p.search(e["line"]) for p in pats)]
    if not hits:
        print(f"0 matches for {args.pattern} among {len(entries)} entries.\n"
              f"Before concluding the topic is undocumented:\n"
              f"  1. widen the query with synonyms and the term the docs would use\n"
              f"     (a page about request timeouts may be titled 'Duration')\n"
              f"  2. if the query was not in English, retry with English terms --\n"
              f"     this index is English-only\n"
              f"  3. fall back to `sections` then `section <name>` for full recall\n"
              f"     inside the most plausible section")
        return 1
    shown = hits[: args.max]
    for e in shown:
        print(fmt(e, width=args.desc_width))
    if len(hits) > len(shown):
        print(f"\n... {len(hits) - len(shown)} more match(es) not shown "
              f"(raise with --max {len(hits)}, or narrow the pattern)")
    return 0


def cmd_section(cfg, args):
    text, age, cached = get_index(cfg, args.refresh)
    entries = parse_entries(text)
    want = args.name.lower()
    hits = [e for e in entries if want in e["section"].lower()]
    if not hits:
        names = sorted({e["section"] for e in entries})
        die("no section matching %r. Available:\n  %s" % (args.name, "\n  ".join(names)))
    b = sum(len(e["line"]) + 1 for e in hits)
    print(f"# {hits[0]['section']} -- {len(hits)} entries, ~{b//4:,} tokens\n")
    for e in hits:
        print(fmt(e, width=args.desc_width, show_section=False))


def resolve_content_url(cfg, url):
    c = cfg.get("content") or {}
    tmpl = c.get("url_template")
    if not tmpl:
        return url
    p = urllib.parse.urlsplit(url)
    return tmpl.format(url=url, url_no_slash=url.rstrip("/"), path=p.path,
                       slug=p.path.strip("/"), host=f"{p.scheme}://{p.netloc}")


def cmd_get(cfg, args):
    c = cfg.get("content") or {}
    mode = c.get("mode", "plain-text")
    target = resolve_content_url(cfg, args.url)
    if mode != "plain-text":
        print(f"This site serves HTML only (mode={mode!r}); piping raw HTML into context "
              f"wastes tokens.\nUse WebFetch on:\n  {target}\n"
              f"WebFetch converts the page to markdown before it reaches context.")
        return 0
    headers = c.get("headers") or None
    try:
        body, final = fetch(target, headers=headers)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        die(f"could not fetch {target}: {e}\nA 404 here usually means the index is "
            f"stale (page renamed upstream). Re-run /docs-skill-builder check.")
    if "<html" in body[:1500].lower():
        print(f"warning: {final} returned HTML, not plain text -- the content contract "
              f"changed. Re-run /docs-skill-builder check.", file=sys.stderr)
    if len(body) > args.max_bytes:
        print(f"[truncated at {args.max_bytes:,} of {len(body):,} bytes; "
              f"re-run with --max-bytes {len(body)} for the rest]\n")
        body = body[: args.max_bytes]
    print(body)


def cmd_stats(cfg, args):
    text, age, cached = get_index(cfg, args.refresh)
    entries = parse_entries(text)
    desc = sum(1 for e in entries if len(e["desc"].split()) >= 4)
    print(f"name          : {cfg.get('name')}")
    print(f"index url     : {(cfg.get('index') or {}).get('url')}")
    print(f"index bytes   : {len(text):,}  (~{len(text)//4:,} tokens if fully loaded)")
    print(f"entries       : {len(entries)}")
    print(f"sections      : {len({e['section'] for e in entries})}")
    print(f"with prose desc: {desc} ({round(100*desc/max(len(entries),1))}%)")
    print(f"content mode  : {(cfg.get('content') or {}).get('mode')}")
    print(f"cache         : {cache_path(cfg)}")
    print(f"cache age     : {int(age)}s (from_cache={cached}, "
          f"ttl={(cfg.get('index') or {}).get('cache_ttl_seconds', DEFAULT_TTL)}s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--refresh", action="store_true", help="ignore the cached index")
    ap.add_argument("--desc-width", type=int, default=140)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sections")
    p = sub.add_parser("search")
    p.add_argument("pattern", nargs="+")
    p.add_argument("--max", type=int, default=25)
    p = sub.add_parser("section")
    p.add_argument("name")
    p = sub.add_parser("get")
    p.add_argument("url")
    p.add_argument("--max-bytes", type=int, default=200_000)
    sub.add_parser("stats")
    sub.add_parser("refresh")

    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.cmd == "refresh":
        args.refresh = True
        get_index(cfg, True)
        print(f"index refreshed -> {cache_path(cfg)}")
        return 0
    return {"sections": cmd_sections, "search": cmd_search, "section": cmd_section,
            "get": cmd_get, "stats": cmd_stats}[args.cmd](cfg, args) or 0


if __name__ == "__main__":
    sys.exit(main())
