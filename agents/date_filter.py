# agents/date_filter.py
"""
Date filtering utility for news items.
Filters RSS, tweets, and URL-crawled content by publication date.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional


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
    # Primary: dateutil handles ISO, RFC, and localized/human date strings and
    # raises on malformed components (e.g. month 31).
    try:
        from dateutil import parser as _du
        dt = _du.parse(s)
        # Normalise to naive UTC so comparisons with datetime.utcnow() don't raise.
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        pass
    # Fallback (dateutil unavailable): ISO / YYYY-MM-DD only.
    try:
        if "T" in s:
            return datetime.fromisoformat(s.split(".")[0].replace("Z", ""))
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
