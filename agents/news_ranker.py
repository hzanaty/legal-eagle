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
  • REPEATED elevation: if repetition_status='repeated' AND repetition_count >= 3 AND
    significance_rank >= 2 → significance_rank += 1 (capped at 5).

Public interface:
  rank_items(items, profile_id, db_conn) -> items
    Mutates each item dict in place with significance_rank, rank_tier, rank_reasoning.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from configurations.config_loader import creds
from agents.sap_ai_client import SAPAICoreClient
from agents.ai_cache import cached_chat

# AI-rank refinement (Tier 2 AI adjusting the rank of Tier-1 / unmatched items) is
# gated OFF by default. The AI chat call was historically broken (always fell back to
# rank 2), so enabling real AI ranking would change many ranks and needs its own
# validation pass. With this off, ranking behaves exactly as shipped; the Tier-2 AI
# call is still made to extract the effective_date. Set LEGAL_EAGLE_AI_RANK_REFINE=0
# to disable AI rank influence and fall back to rank 2 for all Tier-2 items.
_AI_RANK_REFINE = os.environ.get("LEGAL_EAGLE_AI_RANK_REFINE", "1") == "1"
_FALLBACK_RANK = 2  # fallback used when LEGAL_EAGLE_AI_RANK_REFINE=0
_TIER2_WORKERS = 8  # matches health_check.py

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


_AI_CLIENT: Optional[SAPAICoreClient] = None


def _ai_client() -> SAPAICoreClient:
    global _AI_CLIENT
    if _AI_CLIENT is None:
        _AI_CLIENT = _get_ai_client()
    return _AI_CLIENT


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


def _tier2_score(item: Dict[str, Any], grounding: List[Dict[str, Any]]) -> tuple[int, str, Optional[str]]:
    """Call AI to produce rank 1–5 + one-line reasoning + optional effective date.

    Returns (rank, reasoning, effective_date) where effective_date is an ISO
    'YYYY-MM-DD' string if the article explicitly states when the change comes
    into force, else None.
    """
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
        "Also extract the EFFECTIVE DATE — the date the described law, policy, regulation or "
        "rate comes into force / takes effect — but ONLY if the article states a specific date. "
        "Return it as 'YYYY-MM-DD'. If no specific effective date is stated, return null.\n\n"
        f"Examples:\n{examples_text}\n\n"
        f'Title: "{title}"\n'
        f'Content: "{content[:1500]}"\n\n'
        'Respond with a JSON object: '
        '{"rank": <1-5>, "reasoning": "<one sentence>", "effective_date": "<YYYY-MM-DD or null>"}'
    )

    def _call() -> str:
        client = _ai_client()
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content

    try:
        raw = cached_chat(prompt, _call)
        # Extract JSON from the response (may be wrapped in markdown code block)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            rank = max(1, min(5, int(parsed.get("rank", 2))))
            reasoning = str(parsed.get("reasoning", ""))
            effective_date = _normalize_effective_date(parsed.get("effective_date"))
            return rank, reasoning, effective_date
    except Exception:
        pass
    return 2, "Tier 2 fallback — AI unavailable or parse error", None


def _normalize_effective_date(value: Any) -> Optional[str]:
    """Normalize an AI-returned effective date to ISO 'YYYY-MM-DD', or None.

    Accepts a real date string (any parseable format); returns None for null,
    empty, the literal 'null', or an unparseable value.
    """
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if not v or v.lower() == "null":
        return None
    try:
        from agents.news_filter import parse_date_string
        dt = parse_date_string(v)
        return dt.strftime("%Y-%m-%d") if dt else None
    except Exception:
        return None


def rank_items(
    items: List[Dict[str, Any]],
    profile_id: int,
    db_conn,
) -> List[Dict[str, Any]]:
    """Rank all items in place. Returns the same list with rank fields populated."""
    signals = _load_signals(db_conn, profile_id)
    grounding = _load_grounding(db_conn, profile_id)

    # Pass 1: stamp duplicates + compute Tier-1 scores
    non_dupes = []
    t1_scores = {}
    for item in items:
        if item.get("dedup_status") == _DUPLICATE:
            item["significance_rank"] = 0
            item["rank_tier"] = _DUPLICATE
            item["rank_reasoning"] = "duplicate — skipped ranker"
            continue
        text = f"{item.get('title', '')} {item.get('content', '') or ''}"
        t1_scores[id(item)] = _tier1_score(text, signals)
        non_dupes.append(item)

    # Pass 2: parallel Tier-2 AI scoring
    print(f"[Ranker] Tier-2 AI scoring {len(non_dupes)} items ({_TIER2_WORKERS} workers)...")
    with ThreadPoolExecutor(max_workers=_TIER2_WORKERS) as pool:
        t2_results = list(pool.map(lambda it: _tier2_score(it, grounding), non_dupes))

    # Pass 3: apply final ranks + boosts
    for item, (t2_rank, t2_reasoning, effective_date) in zip(non_dupes, t2_results):
        t1_rank = t1_scores[id(item)]
        item["effective_date"] = effective_date
        rank_for_scoring = t2_rank if _AI_RANK_REFINE else _FALLBACK_RANK

        if t1_rank is not None:
            item["significance_rank"] = t1_rank
            item["rank_tier"] = _TIER1
            item["rank_reasoning"] = f"Tier 1 signal match (rank {t1_rank})"
            if t1_rank >= 4:
                _apply_boosts(item)
                continue

        final_rank = max(t1_rank or 0, rank_for_scoring)
        item["significance_rank"] = final_rank
        item["rank_tier"] = _TIER1 if t1_rank is not None else _TIER2
        item["rank_reasoning"] = t2_reasoning if item["rank_tier"] == _TIER2 else item.get("rank_reasoning", "")
        _apply_boosts(item)

    return items


def _apply_boosts(item: Dict[str, Any]) -> None:
    """Apply first-party source boost and REPEATED elevation in place."""
    # Glossary relevance floor: a real glossary match (topic_label set by the tagger,
    # which runs before ranking) means the item is on-topic for the profile's legal
    # domain → it must never be scored as off-topic (rank 1). Floor at 2 ("relevant");
    # genuine significance (≥3) is still earned by Tier-1 signals or the AI.
    label = item.get("topic_label")
    if label:
        try:
            matches = json.loads(label)
        except Exception:
            matches = []
        real = [m for m in matches if m and m != "General"]
        if real and item.get("significance_rank", 0) < 2:
            item["significance_rank"] = 2
            item["rank_reasoning"] = (item.get("rank_reasoning") or "") + " [glossary relevance floor]"

    # First-party source boost: known authority on its own feed → floor at 2
    if item.get("authority_status") == "configured" and item.get("authority_id"):
        if item.get("significance_rank", 0) < 2:
            item["significance_rank"] = 2
            item["rank_reasoning"] = (item.get("rank_reasoning") or "") + " [first-party boost]"

    # REPEATED elevation: story seen ≥ 3 times + currently scored ≥ 2 → +1
    if (
        item.get("repetition_status") == "repeated"
        and (item.get("repetition_count") or 0) >= 3
        and item.get("significance_rank", 0) >= 2
    ):
        item["significance_rank"] = min(5, item["significance_rank"] + 1)
        item["rank_reasoning"] = (item.get("rank_reasoning") or "") + " [repeated +1]"


def rerank_items_for_profile(profile_id: int, db_conn) -> int:
    """Re-run the full ranker over all current news_items for the profile.

    Returns the count of items re-ranked.
    """
    # news_items is scoped by profile_id (there is no run_id column), so re-rank the profile's
    # current items directly.
    rows = db_conn.execute(
        "SELECT * FROM news_items WHERE profile_id=?", (profile_id,)
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
    db_conn.commit()
    return len(items)
