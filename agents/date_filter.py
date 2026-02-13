# agents/date_filter.py
"""
Date filtering utility for news items.
Filters RSS, tweets, and URL-crawled content by publication date.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


def filter_items_by_date(items: List[Dict[str, Any]], days: int = 7) -> List[Dict[str, Any]]:
    """
    Filter news items to only include those from the last X days.
    
    Args:
        items: List of news items (RSS, tweets, URL sources, etc.)
        days: Lookback window in days (default: 7)
    
    Returns:
        Filtered list containing only items within the date range
    
    Note:
        Tries multiple date field names: 'date', 'published', 'published_at', 'pubDate'
        Items without parseable dates are KEPT (fail-safe: don't lose data)
    """
    if not items:
        return []
    
    if days <= 0:
        return items  # No filtering if days is 0 or negative
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
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
        
        if not date_str:
            # No date found - keep item (fail-safe)
            filtered.append(item)
            no_date_count += 1
            continue
        
        # Try to parse date
        try:
            # Handle different date formats
            if "T" in date_str:
                # ISO 8601 format (e.g., "2025-01-05T10:30:00Z" or "2025-01-05T10:30:00.000Z")
                date_str_clean = date_str.split(".")[0].replace("Z", "")  # Remove milliseconds and Z
                item_date = datetime.fromisoformat(date_str_clean)
            else:
                # Simple date format (e.g., "2025-01-05")
                item_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
            
            # Check if within lookback window
            if item_date >= cutoff_date:
                filtered.append(item)
            else:
                skipped_count += 1
                
        except (ValueError, TypeError) as e:
            # Date parsing failed - keep item (fail-safe)
            filtered.append(item)
            no_date_count += 1
    
    # Report filtering results
    if skipped_count > 0 or no_date_count > 0:
        print(f"📅 Date filter ({days} days): kept {len(filtered)}/{len(items)} items")
        if skipped_count > 0:
            print(f"   ↳ Skipped {skipped_count} items older than {days} days")
        if no_date_count > 0:
            print(f"   ↳ Kept {no_date_count} items without parseable dates (fail-safe)")
    
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
    
    if not date_str:
        return None
    
    try:
        if "T" in date_str:
            # ISO 8601 format
            date_str_clean = date_str.split(".")[0].replace("Z", "")
            return datetime.fromisoformat(date_str_clean)
        else:
            # Simple date format
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
