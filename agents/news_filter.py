# agents/news_filter.py
"""
News Filter — the FILTER stage.

Pipeline entry-point:
  filter_source_items(items, source_copy) -> List[Dict]
    Applies the date window already computed on source_copy (since_date or days)
    to a list of collected items. Called per-source during the COLLECT stage so
    every source type (RSS, URL, simulated URL) is filtered with its own anchor.

Utility functions (used by other agents):
  filter_items_by_date(items, days, since_date) -> List[Dict]
  parse_item_date(item)                          -> Optional[datetime]
  parse_date_string(date_str)                    -> Optional[datetime]
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional


def filter_source_items(items: List[Dict[str, Any]], source_copy: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply the date window already computed on source_copy to a list of items.

    Uses since_date if set (delta mode), falls back to days (full window).
    Returns the filtered list unchanged if neither key is present.
    """
    since = source_copy.get('since_date')
    days = source_copy.get('days')
    if since:
        return filter_items_by_date(items, since_date=since)
    if days is not None:
        return filter_items_by_date(items, days=days)
    return items


def filter_items_by_date(
    items: List[Dict[str, Any]],
    days: Optional[int] = None,
    since_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Filter news items by date using either a lookback window or a specific start date.

    Args:
        items: List of news items (RSS, tweets, URL sources, etc.)
        days: Lookback window in days (e.g., 7 for last 7 days). Mutually exclusive with since_date.
        since_date: Fetch items published since this datetime (incremental mode). Mutually exclusive with days.

    Returns:
        Filtered list containing only items within the date range

    Note:
        - Tries multiple date field names: 'date', 'published', 'published_at', 'pubDate'
        - Items without a parseable publish date are REJECTED (dropped) and reported as an
          error — a publish date is required; we do not capture undated news.
        - If neither days nor since_date provided, defaults to 7 days
        - If both provided, since_date takes precedence
    """
    if not items:
        return []

    # Determine cutoff date
    if since_date:
        # Incremental mode: fetch since specific datetime
        cutoff_date = since_date
    elif days is not None and days > 0:
        # Window mode: fetch last N days
        cutoff_date = datetime.utcnow() - timedelta(days=days)
    elif days == 0 or days is None:
        # Default: last 7 days
        cutoff_date = datetime.utcnow() - timedelta(days=7)
    else:
        # No filtering if days is negative
        return items
    filtered = []
    skipped_count = 0
    no_date_count = 0

    for item in items:
        # Try to extract date from various field names
        date_str = (
            item.get("date") or
            item.get("published") or
            item.get("published_at") or
            item.get("pubDate") or
            item.get("created_at") or
            ""
        )

        # Strictly parse the publish date. Missing or unparseable → REJECT the item
        # (a publish date is required; undated news is not captured).
        item_date = parse_date_string(date_str)
        if item_date is None:
            no_date_count += 1
            title = (item.get("title") or "")[:80]
            print(f'❌ Date filter: rejected item — missing/invalid publish date: "{title}"')
            continue

        # Check if within lookback window
        if item_date >= cutoff_date:
            filtered.append(item)
        else:
            skipped_count += 1

    # Report filtering results
    if skipped_count > 0 or no_date_count > 0:
        print(f"📅 Date filter ({days} days): kept {len(filtered)}/{len(items)} items")
        if skipped_count > 0:
            print(f"   ↳ Skipped {skipped_count} items older than {days} days")
        if no_date_count > 0:
            print(f"❌ Date filter: rejected {no_date_count} item(s) with missing/invalid publish date")

    return filtered


def parse_item_date(item: Dict[str, Any]) -> Optional[datetime]:
    """
    Extract and parse publication date from a news item.

    Args:
        item: News item dict

    Returns:
        datetime object if date found and parsed, None otherwise
    """
    date_str = (
        item.get("date") or
        item.get("published") or
        item.get("published_at") or
        item.get("pubDate") or
        item.get("created_at") or
        ""
    )
    return parse_date_string(date_str)


def parse_date_string(date_str: Optional[str]) -> Optional[datetime]:
    """Strictly parse a single date string to a datetime, or None if empty/unparseable.

    Accepts ISO-8601, simple YYYY-MM-DD, and common human/localized formats
    (e.g. "September 4, 2026") via dateutil when available. Genuinely absent
    (empty/non-string) or malformed values (e.g. '2026-31-12') return None so
    callers can reject the item — a real but non-ISO date is kept, only a
    missing/uncapturable one is rejected.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s:
        return None
    # ISO-8601 first (YYYY-MM-DD / YYYY-MM-DDTHH:MM:SS). These are unambiguous and
    # MUST NOT be passed to dateutil with dayfirst=True — dateutil would misread
    # "2026-09-02" as day=09/month=02. RSS feeds normalise to ISO, so this is the
    # common path.
    import re as _re
    if _re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            if "T" in s:
                return datetime.fromisoformat(s.split(".")[0].replace("Z", ""))
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
    # Non-ISO: dateutil with dayfirst=True so European/Turkish DD.MM.YYYY dates
    # (e.g. "10.05.2026" = 10 May) parse correctly rather than as US month-first.
    try:
        from dateutil import parser as _du
        dt = _du.parse(s, dayfirst=True)
        # Normalise to naive UTC so comparisons with datetime.utcnow() don't raise.
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None
