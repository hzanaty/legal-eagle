"""
Timing stage (v3.19) — light, DETERMINISTIC (no AI call).

Derives a timing signal from the Impact gate's effective_date + the matched law's
status. Emits:
    timing_class  : immediate | upcoming | future | past | draft | none
    timing_signal : 0 (none/past) · 1 (upcoming/future/draft) · 2 (immediate)

Rank consumes timing_signal. Values are persisted so the Re-rank path recomputes
consistently.
"""

from datetime import datetime, timedelta

from configurations.db import update_news_fields

_IMMEDIATE_WINDOW_DAYS = 30   # within ±30 days of today counts as "immediate"


def _parse(d):
    if not d:
        return None
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d")
    except Exception:
        return None


def _classify(item: dict) -> tuple[str, int]:
    eff = _parse(item.get("effective_date"))
    status = (item.get("law_status") or "").strip().lower()
    if eff is None:
        # No date — a draft law is still "upcoming"; otherwise no timing signal.
        if status == "draft":
            return "draft", 1
        return "none", 0
    delta_days = (eff - datetime.utcnow()).days
    if abs(delta_days) <= _IMMEDIATE_WINDOW_DAYS:
        return "immediate", 2
    if delta_days > _IMMEDIATE_WINDOW_DAYS:
        return "upcoming" if delta_days <= 365 else "future", 1
    return "past", 0


def apply_timing(items: list[dict], conn, profile_id: int | None = None) -> dict:
    """Set + persist timing_class / timing_signal for each item. Deterministic."""
    for it in items:
        cls, sig = _classify(it)
        it["timing_class"] = cls
        it["timing_signal"] = sig
        update_news_fields(conn, it, {"timing_class": cls, "timing_signal": sig}, profile_id)
    conn.commit()
    return {"timed": len(items)}
