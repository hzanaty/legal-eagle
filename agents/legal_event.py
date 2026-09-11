"""
Shared legal-event identity check (v3.29).

Used by BOTH Reconcile (`compare_news.reconcile_by_act_ref`) and Announcement grouping
(`announcement_agent._same_group`) so they behave identically.

Rule: **same law → candidate → confirm same legal event → then reconcile/group.**
`law_id`/`act_ref` only NARROW candidates (the caller does that). `same_legal_event()`
CONFIRMS whether two candidate items describe the same underlying event, using
**L2 semantic similarity as the core signal**; `cited_article`, effective-date proximity,
and authority are **corroborating signals used where available — never mandatory ANDs**
(one source may omit the article/date, or a different authority may publish the same event).
"""

from datetime import datetime

# L2-summary cosine thresholds. A strong semantic match alone confirms the same event;
# a borderline match is confirmed only with at least one corroborating signal.
STRONG_SIM = 0.78
BORDERLINE_SIM = 0.62
DATE_WINDOW_DAYS = 183  # ~6 months


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except Exception:
        return None


def _date_close(a: dict, b: dict) -> bool:
    da = _parse_date(a.get("effective_date") or a.get("published_at"))
    db = _parse_date(b.get("effective_date") or b.get("published_at"))
    if not da or not db:
        return False  # no usable date → not a corroborator (don't fabricate closeness)
    return abs((da - db).days) <= DATE_WINDOW_DAYS


def _norm(s) -> str:
    return (s or "").strip().lower()


def same_legal_event(a: dict, b: dict, sim_l2: float) -> bool:
    """Confirm two (already law/act candidate-matched) items are the same legal event.

    `sim_l2` = cosine similarity of the two items' L2 summaries (the core signal).
    """
    if sim_l2 >= STRONG_SIM:
        return True
    if sim_l2 < BORDERLINE_SIM:
        return False
    # Borderline semantic match → require at least one corroborating signal.
    corroborators = 0
    ca, cb = _norm(a.get("cited_article")), _norm(b.get("cited_article"))
    if ca and cb and ca == cb:
        corroborators += 1
    if _date_close(a, b):
        corroborators += 1
    aa, ab = a.get("authority_id"), b.get("authority_id")
    if aa is not None and aa == ab:
        corroborators += 1
    return corroborators >= 1
