#!/usr/bin/env python3
"""Probe a documentation domain for a lazy-loadable index and a plain-text content contract."""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Mapping, Sequence

# --------------------------------------------------------------------------------------
# Tunables. Thresholds are the executable source of truth for the tier hints; the prose
# explanation of what each tier means lives in references/mechanism-catalog.md.
# --------------------------------------------------------------------------------------

USER_AGENT = "docs-skill-builder-probe (+one-off documentation capability probe)"
DEFAULT_REQUEST_BUDGET = 28
DEFAULT_REQUEST_DELAY = 0.2
DEFAULT_TIMEOUT = 30
BODY_CAP = 4_000_000
SITEMAP_SCAN_CAP = 2_000_000

T0_MAX_BYTES = 40_000
T0_MIN_PROSE_PCT = 60
T1_MAX_BYTES = 150_000
T1_MIN_SECTIONS = 4
T1_MIN_PROSE_PCT = 50
OVERSIZED_INDEX_BYTES = 400_000
HUB_COVERAGE_MAX = 0.6

ENTRY_RE = re.compile(r"^\s*[-*]\s*\[([^\]]*)\]\(\s*([^)\s]+)[^)]*\)\s*(?:([:—-])\s*(.*))?$")
LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.I)
SITEMAP_DIRECTIVE_RE = re.compile(r"^\s*sitemap:\s*(\S+)", re.I | re.M)
DISALLOW_ALL_RE = re.compile(r"^\s*disallow:\s*/\s*$", re.I | re.M)
AUTH_WALL_RE = re.compile(r"/(login|signin|sign-in|auth|sso)\b", re.I)


# --------------------------------------------------------------------------------------
# Rule registry. Every convention this script knows how to try lives here and nowhere
# else -- teaching it a new one is a single entry, not a new code path.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexRule:
    """A conventional location where a site may publish an agent-readable index."""

    name: str
    relative_path: str
    note: str = ""


@dataclass(frozen=True)
class ContentRule:
    """A conventional way to ask a doc page for plain text instead of HTML.

    `url_template` placeholders: {url} as given, {stripped} without a trailing
    slash, {sep} the correct query separator for the URL.
    """

    name: str
    url_template: str
    headers: Mapping[str, str] | None = None
    requires_path: bool = False
    note: str = ""


@dataclass(frozen=True)
class SitemapRule:
    """A conventional sitemap location, used when robots.txt declares none."""

    name: str
    relative_path: str


@dataclass(frozen=True)
class ProbeRegistry:
    index_rules: tuple[IndexRule, ...]
    content_rules: tuple[ContentRule, ...]
    sitemap_rules: tuple[SitemapRule, ...]


REGISTRY = ProbeRegistry(
    index_rules=(
        IndexRule("llms-txt", "llms.txt", "the de facto standard agent index"),
        IndexRule("llms-full-txt", "llms-full.txt", "usually a full-text dump, not an index"),
        IndexRule("well-known-llms-txt", ".well-known/llms.txt", "rare but proposed location"),
    ),
    content_rules=(
        ContentRule("as-is", "{url}", note="baseline; measures the HTML cost"),
        ContentRule("md-suffix", "{stripped}.md", requires_path=True,
                    note="Mintlify/Fern/Vercel style .md twin"),
        ContentRule("index-md", "{stripped}/index.md", requires_path=True,
                    note="directory-style twin"),
        ContentRule("txt-suffix", "{stripped}.txt", requires_path=True),
        ContentRule("accept-markdown", "{url}", headers={"Accept": "text/markdown"},
                    note="content negotiation"),
        ContentRule("plain-query", "{url}{sep}plain=1", note="GitHub-style plain view"),
    ),
    sitemap_rules=(
        SitemapRule("sitemap", "sitemap.xml"),
        SitemapRule("sitemap-index", "sitemap_index.xml"),
    ),
)


# --------------------------------------------------------------------------------------
# Result dataclasses. The JSON report is exactly `dataclasses.asdict(ProbeReport)`.
# --------------------------------------------------------------------------------------


@dataclass
class HttpResult:
    url: str
    status: int | None = None
    content_type: str = ""
    final_url: str = ""
    bytes: int = 0
    error: str | None = None
    body: str = field(default="", repr=False, compare=False)


@dataclass
class Calibration:
    """What a missing page looks like on this host, learned from a bogus URL."""

    probe_url: str
    status: int | None
    bytes: int
    content_type: str
    signature: str | None
    answers_200_for_missing: bool
    error: str | None = None


@dataclass
class SectionStat:
    name: str
    entries: int
    bytes: int


@dataclass
class IndexStats:
    bytes: int
    lines: int
    entry_count: int
    section_count: int
    entry_separator: str | None
    description_prose_pct: int
    description_terse_pct: int
    description_bare_pct: int
    targets_are_md_pct: int
    sections: list[SectionStat]
    hosts: dict[str, int]
    sample_targets: list[str]


@dataclass
class IndexCandidate:
    rule: str
    requested_url: str
    final_url: str
    status: int | None
    bytes: int
    content_type: str
    exists: bool
    is_index_like: bool
    oversized: bool
    error: str | None = None
    stats: IndexStats | None = None


@dataclass
class ContentVariantResult:
    rule: str
    url: str | None
    status: int | None = None
    content_type: str = ""
    bytes: int = 0
    exists: bool = False
    is_html: bool = False
    is_plain_text: bool = False
    saving_vs_html: float | None = None
    skipped: str | None = None
    error: str | None = None


@dataclass
class ContentProbe:
    sample_url: str
    results: list[ContentVariantResult]


@dataclass
class RobotsInfo:
    url: str
    bytes: int
    declared_sitemaps: list[str]
    disallow_all: bool


@dataclass
class SitemapInfo:
    url: str
    status: int | None
    exists: bool
    is_sitemap_index: bool = False
    loc_count: int = 0
    truncated: bool = False
    sample: list[str] = field(default_factory=list)


@dataclass
class CoverageInfo:
    index_entries: int
    sitemap_urls: int
    ratio: float
    verdict: str  # "leaf-level" | "hub-level"


@dataclass
class Conclusion:
    """The script's mechanical read of its own measurements.

    These are deterministic hints derived from the thresholds at the top of this
    file, not a design decision. The agent confirms or overrides them against
    references/mechanism-catalog.md -- in particular `needs_manual_discovery`
    means the conventional locations came up empty and a web search is required.
    """

    needs_manual_discovery: bool
    best_index_url: str | None
    best_index_reason: str
    index_tier_hint: str
    index_tier_reason: str
    layer_hub_descend: bool
    coverage_verdict: str
    content_mode: str
    content_url_template: str | None
    content_headers: dict[str, str] | None
    content_tier_hint: str
    content_reason: str
    warnings: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


@dataclass
class ProbeReport:
    domain: str
    generated_at: str
    origins_probed: list[str]
    requests_used: int
    request_budget: int
    calibration: Calibration | None
    indexes: list[IndexCandidate]
    content_probes: list[ContentProbe]
    robots: RobotsInfo | None
    sitemaps: list[SitemapInfo]
    coverage: CoverageInfo | None
    conclusion: Conclusion | None
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------------------


class BudgetExhausted(Exception):
    pass


class Fetcher:
    """Throttled, budgeted, redirect-following fetcher."""

    def __init__(self, budget: int, delay: float, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.budget = budget
        self.delay = delay
        self.timeout = timeout
        self.count = 0
        self._last = 0.0

    def get(self, url: str, headers: Mapping[str, str] | None = None,
            cap: int = BODY_CAP) -> HttpResult:
        if self.count >= self.budget:
            raise BudgetExhausted(f"request budget of {self.budget} exhausted at {url}")
        gap = self.delay - (time.time() - self._last)
        if gap > 0:
            time.sleep(gap)
        self.count += 1
        self._last = time.time()

        hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
        if headers:
            hdrs.update(headers)
        out = HttpResult(url=url, final_url=url)
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=hdrs), timeout=self.timeout) as r:
                raw = r.read(cap)
                out.status = r.status
                out.content_type = (r.headers.get("Content-Type") or "").split(";")[0].strip()
                out.final_url = r.geturl()
        except urllib.error.HTTPError as e:
            raw = e.read(cap)
            out.status = e.code
            out.content_type = (e.headers.get("Content-Type") or "").split(";")[0].strip()
            out.final_url = e.url or url
        except Exception as e:  # URLError, timeout, ssl, bad host, ...
            out.error = f"{type(e).__name__}: {e}"
            return out

        if raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except OSError:
                pass
        out.bytes = len(raw)
        out.body = raw.decode("utf-8", "replace")
        return out


def signature(body: str) -> str:
    import hashlib

    return hashlib.sha256(re.sub(r"\s+", " ", body).encode("utf-8", "replace")).hexdigest()[:16]


def normalize_domain(domain: str) -> str:
    return domain if "://" in domain else "https://" + domain


def origins_for(domain: str) -> list[str]:
    """The given path and each of its parents, nearest first."""
    p = urllib.parse.urlsplit(normalize_domain(domain))
    host = f"{p.scheme}://{p.netloc}"
    parts = [seg for seg in p.path.split("/") if seg]
    out: list[str] = []
    for i in range(len(parts), -1, -1):
        base = host + ("/" + "/".join(parts[:i]) if i else "")
        if base not in out:
            out.append(base)
    return out


def exists(result: HttpResult, cal: Calibration) -> bool:
    """Whether a response is meaningfully different from this host's 404."""
    if result.error or result.status != 200 or result.bytes == 0:
        return False
    if AUTH_WALL_RE.search(urllib.parse.urlsplit(result.final_url).path):
        return False
    if cal.signature and signature(result.body) == cal.signature:
        return False
    if cal.answers_200_for_missing and cal.bytes and abs(result.bytes - cal.bytes) < 64:
        return False
    return True


# --------------------------------------------------------------------------------------
# Index analysis
# --------------------------------------------------------------------------------------


def looks_like_index(body: str) -> bool:
    """ENTRY_RE is anchored, so it must be applied per line, not to the whole body."""
    head = body.lstrip()[:2000]
    if head[:1] == "<" or "<html" in head[:400].lower():
        return False
    for line in body.splitlines()[:4000]:
        if ENTRY_RE.match(line.strip()):
            return True
    return head.startswith("#")


def analyze_index(body: str) -> IndexStats:
    lines = body.splitlines()
    sections: list[SectionStat] = []
    current = SectionStat(name="(root)", entries=0, bytes=0)
    targets: list[str] = []
    hosts: dict[str, int] = {}
    seps: dict[str, int] = {}
    prose = terse = bare = md_targets = 0

    for line in lines:
        s = line.strip()
        if s.startswith("## "):
            if current.entries:
                sections.append(current)
            current = SectionStat(name=s[3:].strip(), entries=0, bytes=0)
            continue
        m = ENTRY_RE.match(s)
        if not m:
            continue
        _title, url, sep, desc = m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip()
        current.entries += 1
        current.bytes += len(line) + 1
        targets.append(url)
        if sep:
            seps[sep] = seps.get(sep, 0) + 1
        words = len(desc.split())
        if words >= 4:
            prose += 1
        elif words:
            terse += 1
        else:
            bare += 1
        if url.split("?")[0].rstrip("/").endswith(".md"):
            md_targets += 1
        netloc = urllib.parse.urlsplit(url).netloc
        if netloc:
            hosts[netloc] = hosts.get(netloc, 0) + 1
    if current.entries:
        sections.append(current)

    n = max(len(targets), 1)
    return IndexStats(
        bytes=len(body.encode("utf-8")),
        lines=len(lines),
        entry_count=len(targets),
        section_count=len(sections),
        entry_separator=max(seps, key=lambda k: seps[k]) if seps else None,
        description_prose_pct=round(100 * prose / n),
        description_terse_pct=round(100 * terse / n),
        description_bare_pct=round(100 * bare / n),
        targets_are_md_pct=round(100 * md_targets / n),
        sections=sorted(sections, key=lambda s: -s.bytes),
        hosts=dict(sorted(hosts.items(), key=lambda kv: -kv[1])[:5]),
        sample_targets=targets[:40],
    )


# --------------------------------------------------------------------------------------
# Probe steps
# --------------------------------------------------------------------------------------


def calibrate(fetch: Fetcher, origin: str) -> Calibration:
    bogus = f"{origin.rstrip('/')}/__docs_skill_builder_probe_404__/x"
    r = fetch.get(bogus)
    return Calibration(
        probe_url=bogus, status=r.status, bytes=r.bytes, content_type=r.content_type,
        signature=signature(r.body) if r.body else None,
        answers_200_for_missing=r.status == 200, error=r.error,
    )


def probe_indexes(fetch: Fetcher, origins: Sequence[str], extra: Sequence[str],
                  cal: Calibration) -> list[IndexCandidate]:
    candidates: list[tuple[str, str]] = [("user-supplied", u) for u in extra]
    for origin in origins:
        for rule in REGISTRY.index_rules:
            candidates.append((rule.name, f"{origin.rstrip('/')}/{rule.relative_path}"))

    out: list[IndexCandidate] = []
    seen: set[str] = set()
    for rule_name, url in candidates:
        if url in seen:
            continue
        seen.add(url)
        r = fetch.get(url)
        ok = exists(r, cal)
        cand = IndexCandidate(
            rule=rule_name, requested_url=url, final_url=r.final_url, status=r.status,
            bytes=r.bytes, content_type=r.content_type, exists=ok,
            is_index_like=ok and looks_like_index(r.body),
            oversized=r.bytes > OVERSIZED_INDEX_BYTES, error=r.error,
        )
        if cand.is_index_like:
            cand.stats = analyze_index(r.body)
        out.append(cand)
    return out


def pick_sample_urls(indexes: Sequence[IndexCandidate], domain: str, count: int) -> list[str]:
    """Prefer an in-scope leaf page: probing a marketplace or blog URL measures
    the wrong contract, and the index root measures nothing at all."""
    usable = [i for i in indexes if i.is_index_like and i.stats]
    if not usable:
        return []
    sane = [i for i in usable if not i.oversized] or usable
    best = max(sane, key=lambda i: i.stats.entry_count if i.stats else 0)
    target = urllib.parse.urlsplit(normalize_domain(domain))
    prefix = "/" + target.path.strip("/").split("/")[0] if target.path.strip("/") else ""

    scored: list[tuple[int, str]] = []
    for url in best.stats.sample_targets if best.stats else []:
        p = urllib.parse.urlsplit(url)
        if not url.startswith("http") or not p.path.strip("/"):
            continue
        score = 0
        if p.netloc == target.netloc:
            score += 2
        if prefix and p.path.startswith(prefix):
            score += 4
        if p.path.strip("/").count("/") >= 1:
            score += 1
        scored.append((score, url))
    scored.sort(key=lambda su: -su[0])

    picked: list[str] = []
    for _score, url in scored:
        if url not in picked:
            picked.append(url)
        if len(picked) >= count:
            break
    return picked


def probe_content(fetch: Fetcher, sample_url: str, cal: Calibration) -> ContentProbe:
    stripped = sample_url.rstrip("/")
    sep = "&" if "?" in sample_url else "?"
    has_path = urllib.parse.urlsplit(sample_url).path.strip("/") != ""
    results: list[ContentVariantResult] = []
    html_bytes: int | None = None

    for rule in REGISTRY.content_rules:
        if rule.requires_path and not has_path:
            results.append(ContentVariantResult(
                rule=rule.name, url=None,
                skipped="sample URL has no path; this variant would build an invalid host"))
            continue
        url = rule.url_template.format(url=sample_url, stripped=stripped, sep=sep)
        try:
            r = fetch.get(url, headers=rule.headers)
        except BudgetExhausted as e:
            results.append(ContentVariantResult(rule=rule.name, url=url, skipped=str(e)))
            break
        ok = exists(r, cal)
        head = r.body.lstrip()[:200]
        is_html = "<html" in r.body[:1500].lower() or head.startswith("<!")
        plain = bool(ok and not is_html and (
            r.content_type in ("text/markdown", "text/plain", "text/x-markdown")
            or head.startswith("#") or "\n#" in r.body[:2000]))
        if rule.name == "as-is" and ok:
            html_bytes = r.bytes
        results.append(ContentVariantResult(
            rule=rule.name, url=url, status=r.status, content_type=r.content_type,
            bytes=r.bytes, exists=ok, is_html=is_html, is_plain_text=plain,
            saving_vs_html=(round(1 - r.bytes / html_bytes, 2)
                            if plain and html_bytes else None),
            error=r.error,
        ))
    return ContentProbe(sample_url=sample_url, results=results)


def probe_sitemaps(fetch: Fetcher, origin: str,
                   cal: Calibration) -> tuple[RobotsInfo | None, list[SitemapInfo], bool]:
    """Returns (robots, sitemaps, budget_exhausted). The flag must be surfaced:
    silently returning an empty list would erase the coverage verdict and read as
    'this site has no sitemap'."""
    robots: RobotsInfo | None = None
    urls: list[str] = []
    try:
        r = fetch.get(f"{origin.rstrip('/')}/robots.txt")
        if exists(r, cal):
            declared = SITEMAP_DIRECTIVE_RE.findall(r.body)[:5]
            robots = RobotsInfo(url=r.final_url, bytes=r.bytes, declared_sitemaps=declared,
                                disallow_all=bool(DISALLOW_ALL_RE.search(r.body)))
            urls.extend(declared)
    except BudgetExhausted:
        return robots, [], True

    for rule in REGISTRY.sitemap_rules:
        candidate = f"{origin.rstrip('/')}/{rule.relative_path}"
        if candidate not in urls:
            urls.append(candidate)

    out: list[SitemapInfo] = []
    for url in urls[:3]:
        try:
            r = fetch.get(url, cap=SITEMAP_SCAN_CAP)
        except BudgetExhausted:
            return robots, out, True
        if not exists(r, cal):
            out.append(SitemapInfo(url=url, status=r.status, exists=False))
            continue
        locs = LOC_RE.findall(r.body)
        out.append(SitemapInfo(
            url=r.final_url, status=r.status, exists=True,
            is_sitemap_index="<sitemapindex" in r.body[:2000].lower(),
            loc_count=len(locs), truncated=r.bytes >= SITEMAP_SCAN_CAP, sample=locs[:5],
        ))
    return robots, out, False


# --------------------------------------------------------------------------------------
# Conclusion
# --------------------------------------------------------------------------------------


def derive_conclusion(report: ProbeReport) -> Conclusion:
    warnings: list[str] = []
    actions: list[str] = []

    real = [i for i in report.indexes if i.is_index_like and i.stats]
    sane = [i for i in real if not i.oversized]
    for cand in report.indexes:
        if cand.exists and cand.oversized:
            warnings.append(
                f"{cand.final_url} is {cand.bytes:,} bytes (~{cand.bytes // 4:,} tokens). "
                f"Never load it into context; a full-text dump is not an index.")
    if len(real) > 1:
        warnings.append(
            "More than one index found. Prefer the one whose entry hosts match the docs "
            "host: a marketing-site llms.txt often shadows the docs one.")
    if report.calibration and report.calibration.answers_200_for_missing:
        warnings.append(
            "Host answers 200 for missing paths; existence was decided by body signature.")

    best = max(sane, key=lambda i: i.stats.entry_count if i.stats else 0) if sane else None

    coverage_verdict = report.coverage.verdict if report.coverage else "unknown"
    layer_hub = coverage_verdict == "hub-level"

    if best is None:
        has_sitemap = any(s.exists and s.loc_count for s in report.sitemaps)
        tier = "T3" if has_sitemap else "unknown"
        reason = ("no conventional index found, but a sitemap exists -- slug-only search"
                  if has_sitemap else "no index and no sitemap found at conventional locations")
        actions.append(
            "Conventional locations came up empty. Do NOT stop here: web-search "
            "'<product> llms.txt' and '<product> docs for LLMs', check the vendor's "
            "docs-for-AI page, and look for an open-source docs repo. Re-run with "
            "--extra_index_url for anything found.")
        index_url = None
        index_reason = "none of the registered index rules matched"
    else:
        st = best.stats
        assert st is not None
        index_url = best.final_url
        index_reason = (f"{st.entry_count} entries, {st.bytes:,} B, {st.section_count} "
                        f"sections, {st.description_prose_pct}% prose descriptions")
        if st.bytes <= T0_MAX_BYTES and st.description_prose_pct >= T0_MIN_PROSE_PCT:
            tier = "T0"
            reason = (f"{st.bytes:,} B <= {T0_MAX_BYTES:,} and prose "
                      f"{st.description_prose_pct}% >= {T0_MIN_PROSE_PCT}% -- the whole index "
                      f"fits in context, so no query script is needed")
        elif (st.bytes <= T1_MAX_BYTES and st.section_count >= T1_MIN_SECTIONS
                and st.description_prose_pct >= T1_MIN_PROSE_PCT):
            tier = "T1"
            reason = (f"{st.bytes:,} B with {st.section_count} sections and "
                      f"{st.description_prose_pct}% prose -- route by section, "
                      f"search as the escape hatch")
        else:
            tier = "T2"
            reason = (f"{st.bytes:,} B / {st.description_bare_pct}% bare descriptions -- "
                      f"search must filter outside context; section is the fallback")
        if layer_hub and report.coverage:
            actions.append(
                f"Layer T4 on top: the index covers only {report.coverage.ratio:.1%} of the "
                f"site, so entries point at area landing pages. Plan a second hop.")

    content_mode = "unknown"
    content_template: str | None = None
    content_headers: dict[str, str] | None = None
    content_tier = "unknown"
    content_reason = "no content probe ran"
    for probe in report.content_probes:
        plain = [r for r in probe.results if r.is_plain_text]
        html = next((r for r in probe.results if r.rule == "as-is" and r.exists), None)
        if plain:
            # Pick by registry order, not by size. The smallest plain-text response is
            # often a stub: on vercel.com/docs, index-md returns 1,191 B where the
            # correct md-suffix twin returns 4,991 B of real content.
            order = {r.name: i for i, r in enumerate(REGISTRY.content_rules)}
            winner = min(plain, key=lambda r: order.get(r.rule, 99))
            content_mode = "plain-text"
            content_tier = "C0"
            content_template = {
                "md-suffix": "{url_no_slash}.md",
                "index-md": "{url_no_slash}/index.md",
                "txt-suffix": "{url_no_slash}.txt",
                "plain-query": "{url}?plain=1",
            }.get(winner.rule)
            if winner.rule == "accept-markdown":
                content_headers = {"Accept": "text/markdown"}
            content_reason = (
                f"{winner.rule} returns plain text ({winner.bytes:,} B"
                + (f" vs {html.bytes:,} B of HTML" if html else "") + ")")
            biggest = max(plain, key=lambda r: r.bytes)
            if biggest.rule != winner.rule and winner.bytes < 0.5 * biggest.bytes:
                warnings.append(
                    f"{winner.rule} ({winner.bytes:,} B) is less than half of "
                    f"{biggest.rule} ({biggest.bytes:,} B) for the same page. One of them "
                    f"is probably a stub -- open both before committing to a template.")
            actions.append(
                "Sanity-check the winning variant's body before trusting it -- a smaller "
                "response can be a stub rather than a better answer.")
        elif html:
            content_mode = "html-webfetch"
            content_tier = "C1"
            content_reason = (f"every registered variant returned HTML "
                              f"({html.bytes:,} B/page); use WebFetch, not curl")
        break

    if content_tier == "unknown" and best is not None:
        actions.append("Content contract undetermined -- re-run with a larger "
                       "--request_budget or a different --content_samples.")

    return Conclusion(
        needs_manual_discovery=best is None,
        best_index_url=index_url,
        best_index_reason=index_reason,
        index_tier_hint=tier,
        index_tier_reason=reason,
        layer_hub_descend=layer_hub,
        coverage_verdict=coverage_verdict,
        content_mode=content_mode,
        content_url_template=content_template,
        content_headers=content_headers,
        content_tier_hint=content_tier,
        content_reason=content_reason,
        warnings=warnings,
        next_actions=actions,
    )


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def render(report: ProbeReport) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"domain        : {report.domain}")
    add(f"requests used : {report.requests_used} / {report.request_budget}")
    if report.calibration:
        c = report.calibration
        add(f"404 signature : status={c.status} bytes={c.bytes:,} type={c.content_type}"
            + ("   <-- host answers 200 for missing paths" if c.answers_200_for_missing else ""))
    add("")
    add("INDEX CANDIDATES")
    if not any(i.exists for i in report.indexes):
        add("  none of the registered locations returned a real file")
    for cand in report.indexes:
        if not cand.exists and not cand.stats:
            continue
        add(f"  [{cand.rule}] {cand.final_url}")
        st = cand.stats
        if st is None:
            add(f"    exists but is not an index (status {cand.status}, {cand.bytes:,} B)")
            continue
        add(f"    {st.bytes:,} B | ~{st.bytes // 4:,} tokens | {st.entry_count} entries"
            f" | {st.section_count} sections | separator={st.entry_separator!r}")
        add(f"    descriptions: {st.description_prose_pct}% prose /"
            f" {st.description_terse_pct}% terse / {st.description_bare_pct}% bare")
        add(f"    targets ending in .md: {st.targets_are_md_pct}% | hosts: {st.hosts}")
        for s in st.sections[:6]:
            add(f"      {s.bytes:>7,} B  {s.entries:>4} entries  {s.name}")
    add("")
    add("CONTENT CONTRACT")
    for probe in report.content_probes:
        add(f"  sample: {probe.sample_url}")
        for r in probe.results:
            if r.skipped:
                add(f"    {r.rule:<16} SKIPPED ({r.skipped})")
                continue
            flag = "PLAIN-TEXT" if r.is_plain_text else ("html" if r.exists else "-")
            save = f" saves {int(r.saving_vs_html * 100)}% vs HTML" if r.saving_vs_html else ""
            err = f"  ({r.error})" if r.error else ""
            add(f"    {r.rule:<16} {str(r.status):<5} {r.bytes:>9,} B  {flag}{save}{err}")
    if not report.content_probes:
        add("  (not run -- no index entry available to sample)")
    if report.coverage:
        cov = report.coverage
        add("")
        add(f"INDEX COVERAGE: {cov.index_entries} index entries vs {cov.sitemap_urls} "
            f"sitemap URLs ({cov.ratio:.1%}) -> {cov.verdict.upper()}")
    add("")
    add("SITEMAP / ROBOTS")
    if report.robots:
        add(f"  robots.txt: {report.robots.url} disallow_all={report.robots.disallow_all}")
        for s in report.robots.declared_sitemaps:
            add(f"    declares: {s}")
    for s in report.sitemaps:
        if s.exists:
            add(f"  {s.url}: {s.loc_count} <loc>"
                + (" (sitemap index)" if s.is_sitemap_index else "")
                + (" [TRUNCATED]" if s.truncated else ""))
        else:
            add(f"  {s.url}: absent (status {s.status})")

    if report.conclusion:
        k = report.conclusion
        add("")
        add("CONCLUSION (mechanical -- confirm against references/mechanism-catalog.md)")
        add(f"  needs_manual_discovery : {k.needs_manual_discovery}")
        add(f"  best_index_url         : {k.best_index_url}")
        add(f"                           {k.best_index_reason}")
        add(f"  index_tier_hint        : {k.index_tier_hint}"
            + ("  + T4 hub-descend" if k.layer_hub_descend else ""))
        add(f"                           {k.index_tier_reason}")
        add(f"  content_tier_hint      : {k.content_tier_hint}  (mode={k.content_mode}"
            f", template={k.content_url_template})")
        add(f"                           {k.content_reason}")
        for w in k.warnings:
            add(f"  WARNING: {w}")
        for n in k.next_actions:
            add(f"  NEXT   : {n}")
    for n in report.notes:
        add(f"  NOTE   : {n}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------


def _main(
    domain: str,
    extra_index_url: list[str] | None = None,
    request_budget: int = DEFAULT_REQUEST_BUDGET,
    request_delay: float = DEFAULT_REQUEST_DELAY,
    content_samples: int = 1,
    generated_at: str = "unset",
    json_out: str | None = None,
    quiet: bool = False,
) -> int:
    """Probe one documentation domain and print a structured capability report.

    Walks the rule registry above: tries each conventional index location at the
    given path and every parent, measures the structure and description coverage
    of whatever it finds, tests each plain-text content convention against a real
    leaf page, and counts sitemap URLs to see how much of the site the index
    actually covers.

    This only checks locations that are known and deterministic. It cannot find an
    index published somewhere unconventional -- when `needs_manual_discovery` is
    true in the conclusion, a web search is required, and anything found that way
    should be fed back in via --extra_index_url.

    Returns 0 when the probe completed, 1 when the domain is unreachable.
    """
    origins = origins_for(domain)
    report = ProbeReport(
        domain=domain, generated_at=generated_at, origins_probed=origins,
        requests_used=0, request_budget=request_budget, calibration=None,
        indexes=[], content_probes=[], robots=None, sitemaps=[], coverage=None,
        conclusion=None,
    )
    fetch = Fetcher(budget=request_budget, delay=request_delay)

    try:
        report.calibration = calibrate(fetch, origins[0])
        if report.calibration.error:
            print(f"ERROR: cannot reach {domain}: {report.calibration.error}", file=sys.stderr)
            return 1

        report.indexes = probe_indexes(fetch, origins, extra_index_url or [],
                                       report.calibration)
        for sample in pick_sample_urls(report.indexes, domain, content_samples):
            report.content_probes.append(probe_content(fetch, sample, report.calibration))
        report.robots, report.sitemaps, sitemap_cut = probe_sitemaps(
            fetch, origins[0], report.calibration)
        if sitemap_cut:
            report.notes.append(
                "Budget ran out during the sitemap step, so index coverage is UNKNOWN rather "
                "than absent. Re-run with a larger --request_budget before concluding "
                "anything about how much of the site the index covers.")
    except BudgetExhausted as e:
        report.notes.append(f"{e}. Re-run with a larger --request_budget if a section "
                            f"of the report is missing.")

    real = [i for i in report.indexes if i.is_index_like and i.stats and not i.oversized]
    biggest_map = max((s.loc_count for s in report.sitemaps
                       if s.exists and not s.is_sitemap_index), default=0)
    if real and biggest_map:
        n = max(i.stats.entry_count for i in real if i.stats)
        ratio = n / biggest_map
        report.coverage = CoverageInfo(
            index_entries=n, sitemap_urls=biggest_map, ratio=round(ratio, 3),
            verdict="leaf-level" if ratio >= HUB_COVERAGE_MAX else "hub-level")

    report.requests_used = fetch.count
    report.conclusion = derive_conclusion(report)

    if not quiet:
        print(render(report))
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(report), f, indent=2, ensure_ascii=False,
                      default=str)
            f.write("\n")
        if not quiet:
            print(f"\nfact sheet -> {json_out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="probe_docs_source",
        description="Probe a documentation domain for a lazy-loadable index and a "
                    "plain-text content contract. Checks only conventional, "
                    "deterministic locations -- it supplements web search, it does "
                    "not replace it.",
    )
    parser.add_argument("--domain", required=True,
                        help="docs entry URL or bare domain, e.g. https://docs.example.com")
    parser.add_argument("--extra_index_url", action="append", default=[],
                        help="additional index URL to probe (repeatable); use for a "
                             "location found by web search rather than by convention")
    parser.add_argument("--request_budget", type=int, default=DEFAULT_REQUEST_BUDGET,
                        help=f"max HTTP requests (default {DEFAULT_REQUEST_BUDGET})")
    parser.add_argument("--request_delay", type=float, default=DEFAULT_REQUEST_DELAY,
                        help=f"seconds between requests (default {DEFAULT_REQUEST_DELAY})")
    parser.add_argument("--content_samples", type=int, default=1,
                        help="how many index entries to test the content contract against")
    parser.add_argument("--generated_at", default="unset",
                        help="date stamp recorded in the report, e.g. $(date +%%F)")
    parser.add_argument("--json_out", default=None,
                        help="also write the full dataclass report as JSON to this path")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the human-readable report (use with --json_out)")
    args = parser.parse_args(argv)
    return _main(
        domain=args.domain,
        extra_index_url=args.extra_index_url,
        request_budget=args.request_budget,
        request_delay=args.request_delay,
        content_samples=args.content_samples,
        generated_at=args.generated_at,
        json_out=args.json_out,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
