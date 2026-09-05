"""
Authority Attributor — the ATTRIBUTE stage (v3.1).

Stamps each fetched news item with its source attribution:
  - publisher:        display name of the source (from feed config)
  - authority_id:     FK to the `authorities` table (from feed config)
  - authority_status: 'configured' when an authority is linked in feed config,
                      else 'unknown'. ('inferred' via AI is reserved for v3.2+.)

v3.1 implements the *configured* path only: attribution comes straight from the
per-feed configuration (rss_feeds.publisher_name / rss_feeds.authority_id). No AI
call is made here, which keeps the pipeline (and the test harness) deterministic.
"""
from typing import Any, Dict, List, Optional

CONFIGURED = "configured"
UNKNOWN = "unknown"


def build_feed_config(rss_feeds: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map feed URL -> {publisher, authority_id} from loaded RSS feed rows."""
    cfg: Dict[str, Dict[str, Any]] = {}
    for f in rss_feeds or []:
        url = f.get("url") if isinstance(f, dict) else None
        if not url:
            continue
        cfg[url] = {
            "publisher": f.get("publisher_name"),
            "authority_id": f.get("authority_id"),
        }
    return cfg


def attribute_items(
    items: List[Dict[str, Any]],
    feed_config: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Stamp publisher / authority_id / authority_status onto each item in place.

    An item is matched to its feed via `item['feed_url']` (set by rss_parser).
    Items without a matching configured authority are stamped 'unknown' but still
    receive a publisher when one is configured for the feed.
    """
    feed_config = feed_config or {}
    for it in items:
        cfg = feed_config.get(it.get("feed_url")) if it.get("feed_url") else None
        if cfg is not None:
            if cfg.get("publisher"):
                it["publisher"] = cfg.get("publisher")
            if cfg.get("authority_id"):
                it["authority_id"] = cfg.get("authority_id")
                it["authority_status"] = CONFIGURED
            else:
                it.setdefault("authority_status", UNKNOWN)
        else:
            it.setdefault("authority_status", UNKNOWN)
    return items
