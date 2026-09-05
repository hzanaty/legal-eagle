"""
News Ranker — the RANK stage (v3.2).

Three-tier ranking engine that assigns significance_rank (0–5) to each item:

  Tier 0  DUPLICATE passthrough:
          Items with dedup_status='duplicate' are stamped rank=0, rank_tier='duplicate'
          and skip both Tier 1 and Tier 2 entirely.

  Tier 1  Deterministic keyword/regex rules loaded from the ranking_signals DB table.
          Fast, fully explainable, no AI call. If a Tier 1 rule fires at rank ≥ 4 the
          item is promoted immediately and Tier 2 is skipped.

  Tier 2  AI (GPT-4o via sap_ai_client). Fires when Tier 1 gives rank < 4 or produces
          no match. Prompt includes up to 10 ranking_grounding summaries as few-shot
          examples. AI call is wrapped in ai_cache for offline harness determinism.

Post-scoring adjustments (order matters):
  • First-party source boost: if item authority_id matches the feed's configured
    authority_id, significance_rank = max(significance_rank, 2).
  • REPEATED elevation: if repetition_tag='repeated' AND repetition_count >= 3 AND
    significance_rank >= 2 → significance_rank += 1 (capped at 5).

Public interface:
  rank_items(items, profile_id, db_conn) -> items
    Mutates each item dict in place with significance_rank, rank_tier, rank_reasoning.
"""
import json
import re
from typing import Any, Dict, List, Optional

from configurations.config_loader import creds
from agents.sap_ai_client import SAPAICoreClient
from agents.ai_cache import cached_chat

_DUPLICATE = "duplicate"
_TIER1 = "tier1"
_TIER2 = "tier2"

_BOOTSTRAP_EXAMPLES = [
    {"rank": 5, "title": "Parliament passes amendment to Employment Act — effective immediately",
     "reasoning": "Enacted legislation with immediate effect; direct compliance obligation."},
    {"rank": 4, "title": "Ministry releases draft regulation for public consultation",
     "reasoning": "Upcoming regulatory change; requires advance preparation."},
    {"rank": 3, "title": "New social insurance contribution rates announced for next quarter",
     "reasoning": "Operational impact on payroll processing; known timeline."},
    {"rank": 2, "title": "Labor tribunal issues ruling on overtime pay classification",
     "reasoning": "Relevant case law; indirect compliance implication."},
    {"rank": 1, "title": "Central bank raises benchmark interest rate by 50 bps",
     "reasoning": "Finance/macro news; no direct HCM regulatory obligation."},
]


def _get_ai_client() -> SAPAICoreClient:
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
    )


def _load_signals(db_conn, profile_id: int) -> List[Dict[str, Any]]:
    rows = db_conn.execute(
        "SELECT signal_type, pattern, min_rank FROM ranking_signals WHERE profile_id=? ORDER BY min_rank DESC",
        (profile_id,),
    ).fetchall()
    return [{"type": r["signal_type"], "pattern": r["pattern"], "min_rank": r["min_rank"]} for r in rows]


def _load_grounding(db_conn, profile_id: int) -> List[Dict[str, Any]]:
    rows = db_conn.execute(
        "SELECT rank, summary FROM ranking_grounding WHERE profile_id=? ORDER BY id DESC LIMIT 10",
        (profile_id,),
    ).fetchall()
    return [{"rank": r["rank"], "title": r["summary"] or "", "reasoning": ""} for r in rows]


def _tier1_score(text: str, signals: List[Dict[str, Any]]) -> Optional[int]:
    """Return the highest matching min_rank, or None if no signals match."""
    best: Optional[int] = None
    text_lower = text.lower()
    for sig in signals:
        if sig["type"] == "keyword":
            if sig["pattern"].lower() in text_lower:
                best = sig["min_rank"] if best is None else max(best, sig["min_rank"])
        elif sig["type"] == "regex":
            try:
                if re.search(sig["pattern"], text, re.IGNORECASE):
                    best = sig["min_rank"] if best is None else max(best, sig["min_rank"])
            except re.error:
                pass
    return best


def _tier2_score(item: Dict[str, Any], grounding: List[Dict[str, Any]]) -> tuple[int, str]:
    """Call AI to produce rank 1–5 + one-line reasoning. Returns (rank, reasoning)."""
    title = item.get("title", "")
    content = item.get("content", "") or ""

    examples_text = "\n".join(
        f'  rank {e["rank"]}: "{e["title"]}" — {e["reasoning"]}'
        for e in (_BOOTSTRAP_EXAMPLES + grounding)[-10:]
    )
    prompt = (
        "You are a regulatory significance ranker for HR/labor law news.\n"
        "Rate the following news item on a scale of 1–5:\n"
        "  5 = enacted legislation with immediate compliance effect\n"
        "  4 = upcoming regulatory change requiring preparation\n"
        "  3 = operational impact (payroll, deadlines, rates)\n"
        "  2 = relevant case law or indirect implication\n"
        "  1 = off-topic or macro/finance news with no direct HR obligation\n\n"
        f"Examples:\n{examples_text}\n\n"
        f'Title: "{title}"\n'
        f'Content: "{content[:400]}"\n\n'
        'Respond with a JSON object: {"rank": <1-5>, "reasoning": "<one sentence>"}'
    )

    def _call():
        client = _get_ai_client()
        return client.chat(prompt)

    try:
        raw = cached_chat(prompt, _call)
        # Extract JSON from the response (may be wrapped in markdown code block)
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            rank = max(1, min(5, int(parsed.get("rank", 2))))
            reasoning = str(parsed.get("reasoning", ""))
            return rank, reasoning
    except Exception:
        pass
    return 2, "Tier 2 fallback — AI unavailable or parse error"


def rank_items(
    items: List[Dict[str, Any]],
    profile_id: int,
    db_conn,
) -> List[Dict[str, Any]]:
    """Rank all items in place. Returns the same list with rank fields populated."""
    signals = _load_signals(db_conn, profile_id)
    grounding = _load_grounding(db_conn, profile_id)

    for item in items:
        # Tier 0 — duplicate passthrough
        if item.get("dedup_status") == _DUPLICATE:
            item["significance_rank"] = 0
            item["rank_tier"] = _DUPLICATE
            item["rank_reasoning"] = "duplicate — skipped ranker"
            continue

        text = f"{item.get('title', '')} {item.get('content', '') or ''}"

        # Tier 1 — deterministic keyword/regex
        t1_rank = _tier1_score(text, signals)
        if t1_rank is not None:
            item["significance_rank"] = t1_rank
            item["rank_tier"] = _TIER1
            item["rank_reasoning"] = f"Tier 1 signal match (rank {t1_rank})"
            if t1_rank >= 4:
                # Strong Tier 1 match — skip AI
                _apply_boosts(item)
                continue

        # Tier 2 — AI (fires when Tier 1 gives rank < 4 or no match)
        t2_rank, t2_reasoning = _tier2_score(item, grounding)
        # Take the better of Tier 1 and Tier 2
        final_rank = max(t1_rank or 0, t2_rank)
        item["significance_rank"] = final_rank
        item["rank_tier"] = _TIER2 if (t1_rank is None or t2_rank > (t1_rank or 0)) else _TIER1
        item["rank_reasoning"] = t2_reasoning if item["rank_tier"] == _TIER2 else item.get("rank_reasoning", "")

        _apply_boosts(item)

    return items


def _apply_boosts(item: Dict[str, Any]) -> None:
    """Apply first-party source boost and REPEATED elevation in place."""
    # First-party source boost: known authority on its own feed → floor at 2
    if item.get("authority_status") == "configured" and item.get("authority_id"):
        if item.get("significance_rank", 0) < 2:
            item["significance_rank"] = 2
            item["rank_reasoning"] = (item.get("rank_reasoning") or "") + " [first-party boost]"

    # REPEATED elevation: story seen ≥ 3 times + currently scored ≥ 2 → +1
    if (
        item.get("repetition_tag") == "repeated"
        and (item.get("repetition_count") or 0) >= 3
        and item.get("significance_rank", 0) >= 2
    ):
        item["significance_rank"] = min(5, item["significance_rank"] + 1)
        item["rank_reasoning"] = (item.get("rank_reasoning") or "") + " [repeated +1]"


def rerank_items_for_profile(profile_id: int, db_conn) -> int:
    """Re-run the full ranker over all news_items for the profile's latest run.

    Returns the count of items re-ranked.
    """
    latest_run = db_conn.execute(
        "SELECT id FROM runs WHERE profile_id=? ORDER BY id DESC LIMIT 1", (profile_id,)
    ).fetchone()
    if not latest_run:
        return 0

    run_id = latest_run["id"]
    rows = db_conn.execute(
        "SELECT * FROM news_items WHERE run_id=?", (run_id,)
    ).fetchall()
    if not rows:
        return 0

    items = [dict(r) for r in rows]
    rank_items(items, profile_id, db_conn)

    for item in items:
        db_conn.execute(
            "UPDATE news_items SET significance_rank=?, rank_tier=?, rank_reasoning=? WHERE id=?",
            (item.get("significance_rank", 0), item.get("rank_tier", ""), item.get("rank_reasoning", ""), item["id"]),
        )
    return len(items)
