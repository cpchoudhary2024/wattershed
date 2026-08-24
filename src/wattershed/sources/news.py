# Copyright (c) 2026 Chandra Prakash Choudhary. All rights reserved.
"""Google News RSS adapter — announcement tracking, NOT a data source.

Hard boundary: nothing this module returns may ever reach a pillar score.
News headlines are unverified secondary reporting; a screening tool whose
whole claim is per-value provenance cannot let a press release move a number.
What they are good for is *lead generation* — telling a human "a campus was
announced near here, go look" — so records are written to their own file,
labelled unverified, and rendered as leads.

Keyless and stable: the RSS endpoint takes a query string and returns Atom-ish
RSS 2.0. Parsed with the stdlib ElementTree, so no feedparser dependency.
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .base import SourceUnavailable, fetch_text

log = logging.getLogger("wattershed.news")

RSS_URL = "https://news.google.com/rss/search"

# Queries are quoted phrases so the feed stays on-topic; broad terms like
# "data center" alone return mostly market-analyst noise.
QUERIES: tuple[str, ...] = (
    '"hyperscale data center" announcement',
    '"data center" "under construction"',
    '"data center" "new permit" OR "permit approved"',
)

# Hard ceiling on retained items. This file is committed on every sync, so an
# unbounded append would bloat the repository history by design. Newest wins.
MAX_ITEMS = 400

# Community-friction terms. A match records that organised opposition or a
# legal/procedural challenge is being REPORTED near a project — nothing more.
#
# This signal is descriptive and non-scoring, and the naming matters: it is not
# a "NIMBY" index. Coverage volume tracks media-market size and population, not
# community harm, so scaling a burden percentile by it would mean a tract in a
# large media market outranks an equally burdened rural tract with no reporter
# covering it. It would also invert the burden pillar's meaning — residents of
# an already-overburdened tract objecting to another facility is the signal the
# pillar exists to surface, not a discount to apply to it.
FRICTION_TERMS: tuple[str, ...] = (
    "moratorium",
    "noise litigation",
    "zoning lawsuit",
    "rezoning denied",
    "permit denied",
    "injunction",
    "appeal filed",
    "community opposition",
)

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", s or "")).strip()


def _iso(pubdate: str) -> str:
    try:
        return parsedate_to_datetime(pubdate).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


def _item_id(link: str, title: str) -> str:
    """Stable id for dedupe. Google rewrites tracking links between fetches,
    so the title is folded in rather than trusting the URL alone."""
    basis = (link or "").split("?")[0] + "|" + _strip_html(title).lower()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def parse_feed(xml_text: str, query: str) -> list[dict]:
    """Pure: RSS text in, normalized records out. No network, no state."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("news: unparseable feed for %r — %s", query, e)
        return []
    out = []
    for item in root.iterfind(".//channel/item"):
        title = _strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append(
            {
                "id": _item_id(link, title),
                "title": title,
                "url": link,
                "source": _strip_html(item.findtext("source") or ""),
                "published": _iso(item.findtext("pubDate") or ""),
                "query": query,
                "verified": False,   # never flips true from this pipeline
            }
        )
    return out


def friction_terms_in(text: str, terms: tuple[str, ...] = FRICTION_TERMS) -> list[str]:
    """Friction terms present in a headline, lowercased and deduped. Pure."""
    low = (text or "").lower()
    return sorted({t for t in terms if t in low})


def annotate_friction(items: list[dict], terms: tuple[str, ...] = FRICTION_TERMS) -> list[dict]:
    """Tag each item with the friction terms it mentions. Pure; returns new dicts.

    `friction` is evidence of reporting, not of harm, and never feeds a score —
    tests assert no scoring module imports this layer.
    """
    out = []
    for it in items:
        hits = friction_terms_in(it.get("title", ""), terms)
        out.append(dict(it, friction=hits, friction_n=len(hits)))
    return out


def friction_summary(items: list[dict]) -> dict:
    """Counts per term across retained leads. Pure."""
    counts: dict[str, int] = {}
    for it in items:
        for t in it.get("friction") or []:
            counts[t] = counts.get(t, 0) + 1
    flagged = sum(1 for it in items if it.get("friction_n"))
    return {
        "items_total": len(items),
        "items_with_friction": flagged,
        "by_term": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "basis": (
            "Counts of unverified press headlines matching friction terms. "
            "Descriptive only: coverage volume tracks media-market size, not "
            "community harm, and this modifies no score."
        ),
    }


def fetch_announcements(queries: tuple[str, ...] = QUERIES, timeout: int = 45) -> list[dict]:
    """Query each phrase; a failing query is skipped, not fatal."""
    seen: dict[str, dict] = {}
    for q in queries:
        try:
            xml_text = fetch_text(
                RSS_URL, params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=timeout
            )
        except SourceUnavailable as e:
            log.warning("news: query %r unavailable — %s", q, e)
            continue
        items = parse_feed(xml_text, q)
        log.info("news: %-46s %3d items", q[:46], len(items))
        for it in annotate_friction(items):
            seen.setdefault(it["id"], it)
    return list(seen.values())


def merge(existing: list[dict], incoming: list[dict], max_items: int = MAX_ITEMS) -> list[dict]:
    """Append-with-dedupe, newest first, capped. Pure."""
    by_id: dict[str, dict] = {}
    for rec in list(existing) + list(incoming):
        rid = rec.get("id")
        if rid:
            by_id.setdefault(rid, rec)
    ordered = sorted(by_id.values(), key=lambda r: r.get("published") or "", reverse=True)
    return ordered[:max_items]


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "FRICTION_TERMS",
    "MAX_ITEMS",
    "QUERIES",
    "annotate_friction",
    "fetch_announcements",
    "friction_summary",
    "friction_terms_in",
    "merge",
    "parse_feed",
    "utc_now_iso",
]
