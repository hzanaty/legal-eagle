#!/usr/bin/env python3
"""
Compare RSS generator output vs Legal Eagle URL scraper output.

Usage:
    python scripts/compare_rss_output.py \
        --rss "https://rss-feed-creator-dev.cfapps.eu21.hana.ondemand.com/feed?url=..." \
        --json outputs/SA_HCM/all_news.json \
        --since today

The RSS feed URL is fetched with feedparser. The JSON is the all_news.json
produced by a Legal Eagle run (URL source only, skip filtering, skip comparison).

--since filters Eagle's items by publish date so the comparison window matches
what the RSS generator covers (typically today only, since it scrapes the page once).
Legal Eagle may loop over 7 days; --since today keeps only today's items for a
fair apples-to-apples comparison.
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

try:
    import feedparser
except ImportError:
    print("ERROR: feedparser is not installed. Run: pip install feedparser")
    sys.exit(1)


# ── Normalization helpers ──────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Lowercase scheme+host, strip trailing slash, drop fragment."""
    try:
        p = urlparse(url.strip())
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, p.params, p.query, ""))
    except Exception:
        return url.strip().lower()


def normalize_title(title: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for fuzzy matching."""
    t = unicodedata.normalize("NFKC", title or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ── Date filtering ─────────────────────────────────────────────────────────────

def parse_since(since_arg: str) -> date | None:
    """Parse --since value into a date. Returns None if arg is None."""
    if since_arg is None:
        return None
    if since_arg.lower() == "today":
        return date.today()
    try:
        return datetime.strptime(since_arg, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERROR: --since must be 'today' or 'YYYY-MM-DD', got: {since_arg}")
        sys.exit(1)


_DATE_PATTERNS = [
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d.%m.%Y",
]


def item_date(date_str: str) -> date | None:
    """Try to parse a date string from Eagle's 'date' field. Returns None on failure."""
    if not date_str:
        return None
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    try:
        import email.utils
        return email.utils.parsedate_to_datetime(date_str.strip()).date()
    except Exception:
        pass
    return None


def filter_by_date(items: list[dict], since: date | None) -> tuple[list[dict], int]:
    """Return (items_on_or_after_since, skipped_count). Items with unparseable dates pass through."""
    if since is None:
        return items, 0
    kept, skipped = [], 0
    for item in items:
        d = item_date(item.get("date", ""))
        if d is None or d >= since:
            kept.append(item)
        else:
            skipped += 1
    return kept, skipped


# ── Parsing ────────────────────────────────────────────────────────────────────

def load_rss(rss_source: str) -> list[dict]:
    """Parse the RSS feed from a URL or local file path."""
    feed = feedparser.parse(rss_source)
    if feed.bozo and not feed.entries:
        print("WARNING: feedparser reported an issue parsing the RSS source.")
        if hasattr(feed.bozo_exception, "__str__"):
            print(f"         {feed.bozo_exception}")

    items = []
    for entry in feed.entries:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""
        summary = getattr(entry, "summary", "") or ""
        published = getattr(entry, "published", "") or ""
        items.append({
            "title": title.strip(),
            "link": link.strip(),
            "summary": summary.strip(),
            "published": published.strip(),
        })
    return items


def load_eagle_json(json_path: str) -> list[dict]:
    """Load all_news.json and filter to URL-scraped items only."""
    path = Path(json_path)
    if not path.exists():
        print(f"ERROR: File not found: {json_path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"ERROR: Expected a JSON array in {json_path}, got {type(data).__name__}")
        sys.exit(1)

    url_types = {"URL_Static", "URL_Dynamic", "URL_Recursive"}
    return [item for item in data if item.get("source_type") in url_types]


# ── Matching ───────────────────────────────────────────────────────────────────

def build_index(items: list[dict], key_fn) -> dict[str, int]:
    """Build a lookup: normalized-key → original-index (first seen wins)."""
    index = {}
    for i, item in enumerate(items):
        k = key_fn(item)
        if k and k not in index:
            index[k] = i
    return index


def match_items(rss_items: list[dict], eagle_items: list[dict], strategy: str):
    """
    Returns:
        matched    — list of (rss_item, eagle_item) pairs
        rss_only   — rss_items with no match
        eagle_only — eagle_items with no match
    """
    rss_link_idx    = build_index(rss_items,   lambda x: normalize_url(x["link"]))
    eagle_link_idx  = build_index(eagle_items, lambda x: normalize_url(x.get("link", "")))
    rss_title_idx   = build_index(rss_items,   lambda x: normalize_title(x["title"]))
    eagle_title_idx = build_index(eagle_items, lambda x: normalize_title(x.get("title", "")))

    matched_rss, matched_eagle, matched = set(), set(), []

    for ri, rss in enumerate(rss_items):
        ei = None
        if strategy in ("link", "both"):
            ei = eagle_link_idx.get(normalize_url(rss["link"]))
        if ei is None and strategy in ("title", "both"):
            ei = eagle_title_idx.get(normalize_title(rss["title"]))
        if ei is not None and ei not in matched_eagle:
            matched.append((rss, eagle_items[ei]))
            matched_rss.add(ri)
            matched_eagle.add(ei)

    rss_only   = [rss_items[i]   for i in range(len(rss_items))   if i not in matched_rss]
    eagle_only = [eagle_items[i] for i in range(len(eagle_items)) if i not in matched_eagle]
    return matched, rss_only, eagle_only


# ── Report ─────────────────────────────────────────────────────────────────────

def truncate(s: str, n: int = 90) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s[:n] + "…" if len(s) > n else s


def print_report(matched, rss_only, eagle_only, rss_total, eagle_total, strategy, since, eagle_skipped):
    SEP = "─" * 70

    print(f"\n{SEP}")
    print(f"  RSS GENERATOR  →  {rss_total} items")
    since_label = f"since {since}" if since else "all dates"
    print(f"  LEGAL EAGLE    →  {eagle_total} items  (URL sources, {since_label})")
    if eagle_skipped:
        print(f"                    ({eagle_skipped} older items excluded by --since filter)")
    print(f"  Match strategy : {strategy}")
    print(SEP)

    print(f"\n✅  MATCHED  ({len(matched)} items)")
    if matched:
        for rss, _ in matched:
            print(f"    · {truncate(rss['title'])}")
    else:
        print("    (none)")

    print(f"\n🟡  RSS ONLY  ({len(rss_only)} items)  — generator found these, Legal Eagle missed them")
    if rss_only:
        for item in rss_only:
            print(f"    · {truncate(item['title'])}")
            print(f"      {truncate(item['link'], 80)}")
    else:
        print("    (none — Legal Eagle found everything the generator did ✓)")

    print(f"\n🔵  EAGLE ONLY  ({len(eagle_only)} items)  — Legal Eagle found these, generator missed them")
    if eagle_only:
        for item in eagle_only:
            print(f"    · {truncate(item.get('title', ''))}")
            print(f"      {truncate(item.get('link', ''), 80)}")
    else:
        print("    (none — generator found everything Legal Eagle did ✓)")

    print(f"\n{SEP}")
    rss_coverage   = len(matched) / rss_total   * 100 if rss_total   else 0.0
    eagle_coverage = len(matched) / eagle_total * 100 if eagle_total else 0.0

    print(f"  SUMMARY")
    print(f"    Matched        : {len(matched)}")
    print(f"    RSS only       : {len(rss_only)}")
    print(f"    Eagle only     : {len(eagle_only)}")
    print(f"    RSS coverage   : {rss_coverage:.1f}%  (Eagle found this % of what RSS found)")
    print(f"    Eagle coverage : {eagle_coverage:.1f}%  (RSS found this % of what Eagle found)")
    print(SEP)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compare RSS generator output vs Legal Eagle URL scraper output."
    )
    parser.add_argument(
        "--rss", required=True,
        help="RSS feed URL from the generator, or path to a saved .xml file"
    )
    parser.add_argument(
        "--json", default="outputs/SA_HCM/all_news.json",
        help="Path to Legal Eagle's all_news.json (default: outputs/SA_HCM/all_news.json)"
    )
    parser.add_argument(
        "--by", choices=["link", "title", "both"], default="both",
        help="Match strategy: link | title | both (default: both)"
    )
    parser.add_argument(
        "--since",
        help=(
            "Filter Eagle items by publish date: 'today' or 'YYYY-MM-DD'. "
            "Use --since today to match the RSS generator's scope "
            "(it scrapes the page once; Eagle may loop over 7 days)."
        )
    )
    args = parser.parse_args()

    since = parse_since(args.since)

    print(f"Loading RSS feed: {args.rss}")
    rss_items = load_rss(args.rss)
    print(f"  → {len(rss_items)} items from RSS generator")

    print(f"Loading Legal Eagle output: {args.json}")
    eagle_items_raw = load_eagle_json(args.json)
    eagle_items, eagle_skipped = filter_by_date(eagle_items_raw, since)
    if since:
        print(f"  → {len(eagle_items)} URL-sourced items on/after {since}  ({eagle_skipped} older items filtered out)")
    else:
        print(f"  → {len(eagle_items)} URL-sourced items in all_news.json")

    if not rss_items and not eagle_items:
        print("\nBoth sources are empty — nothing to compare.")
        return

    matched, rss_only, eagle_only = match_items(rss_items, eagle_items, args.by)
    print_report(matched, rss_only, eagle_only, len(rss_items), len(eagle_items), args.by, since, eagle_skipped)


if __name__ == "__main__":
    main()
