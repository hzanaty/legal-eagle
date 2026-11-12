"""
RRR Matcher (v3.92) — evaluate approved re-rank rules against new pipeline items.

Public interface:
    run_rrr_match(items, profile_id, db_conn) -> None
        Mutates each item in place:
          - significance_rank: updated if a rule applies unambiguously
          - pre_rrr_rank:      initial system rank (set only on rank change or conflict)
          - rrr_rule_id:       FK to rrr_rules (set on upgrade/downgrade only)
          - rrr_match_outcome: 'upgraded' | 'downgraded' | 'conflict' | None

Matching rules:
  - Rank 1 items and duplicates are never evaluated.
  - Direction guard: upgrade rules (override_rank > original_rank) are eligible only
    when initial_rank < override_rank.  Downgrade rules only when initial_rank > override_rank.
    This prevents a rule learned from 3→4 from downgrading a Rank 5 article.
  - For each eligible item, direction-eligible rules are evaluated in one AI call that
    returns APPLY / DO_NOT_APPLY / INSUFFICIENT_EVIDENCE per rule.
  - Only APPLY verdicts count; INSUFFICIENT_EVIDENCE is logged but does not change rank.
  - One applicable rule: apply its override_rank.
  - Multiple rules agree on target rank: apply that rank.
  - Multiple rules disagree: preserve initial rank, set rrr_match_outcome='conflict'.
  - No applicable rules or AI call fails: preserve initial rank silently.
"""
import json
import re
from typing import Any, Dict, List

from agents.sap_ai_client import SAPAICoreClient
from agents.ai_cache import cached_chat
from configurations.config_loader import creds
from configurations.db import list_rrr_rules

_RANK_LABELS = {1: "Noise", 2: "Signal", 3: "Watch", 4: "Legal Change", 5: "Urgent"}

# Valid AI verdict values (uppercase normalised)
_VERDICT_APPLY = "APPLY"
_VERDICT_DO_NOT_APPLY = "DO_NOT_APPLY"
_VERDICT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
_VALID_VERDICTS = {_VERDICT_APPLY, _VERDICT_DO_NOT_APPLY, _VERDICT_INSUFFICIENT}


def _ai_client() -> SAPAICoreClient:
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
    )


def _rule_eligible_for_item(rule: Dict[str, Any], initial_rank: int) -> bool:
    """Return True if applying this rule preserves the direction of the original correction.

    Upgrade rules (override_rank > original_rank) are eligible only when
    initial_rank < override_rank — i.e., applying it is still an upgrade.

    Downgrade rules (override_rank < original_rank) are eligible only when
    initial_rank > override_rank — i.e., applying it is still a downgrade.

    Examples:
        Rule 3→4 (upgrade), item rank 5:  5 < 4 → False  (would downgrade — blocked)
        Rule 3→4 (upgrade), item rank 3:  3 < 4 → True
        Rule 4→2 (downgrade), item rank 2: 2 > 2 → False  (no-op — blocked)
        Rule 4→2 (downgrade), item rank 5: 5 > 2 → True
    """
    if rule["override_rank"] > rule["original_rank"]:  # upgrade rule
        return initial_rank < rule["override_rank"]
    else:  # downgrade rule
        return initial_rank > rule["override_rank"]


def _evaluate_rules_for_item(
    item: Dict[str, Any],
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Evaluate direction-eligible rules against the item in one AI call.

    Returns list of {rule_id, verdict, reasoning} where verdict is one of
    APPLY | DO_NOT_APPLY | INSUFFICIENT_EVIDENCE.
    Returns [] on failure (caller preserves initial rank).
    """
    if not rules:
        return []

    title = (item.get("title") or "").strip()
    l2_summary = (item.get("l2_summary") or "").strip()
    content = l2_summary or (item.get("content") or "")[:1500]
    evidence_raw = item.get("impact_evidence_json") or "[]"
    try:
        evidence = json.loads(evidence_raw)
        evidence_text = "\n".join(f"  - {e}" for e in evidence[:5]) if evidence else "  (none)"
    except Exception:
        evidence_text = "  (none)"

    rules_text = "\n".join(
        f'Rule {r["id"]}:\n'
        f'  WHY: {r["why_text"]}\n'
        f'  WHEN: {r["when_text"]}\n'
        f'  WHEN NOT: {r["when_not_text"]}'
        for r in rules
    )

    prompt = (
        "You are evaluating whether approved re-rank rules apply to a news article.\n"
        "Evaluate APPLICABILITY (WHEN/WHEN NOT conditions), not topic similarity.\n\n"
        f"News Article:\n"
        f"  Title: \"{title}\"\n"
        f"  Summary: \"{content[:800]}\"\n"
        f"  Operative clauses:\n{evidence_text}\n\n"
        f"Rules to evaluate:\n{rules_text}\n\n"
        "For each rule return one of three verdicts:\n"
        "  APPLY               — all WHEN conditions are met AND no WHEN NOT exception fires\n"
        "  DO_NOT_APPLY        — at least one WHEN condition is not met, or a WHEN NOT exception fires\n"
        "  INSUFFICIENT_EVIDENCE — the article lacks enough information to evaluate this rule reliably\n\n"
        "Consider WHEN NOT exceptions carefully — they override WHEN conditions.\n"
        "INSUFFICIENT_EVIDENCE means the article is genuinely ambiguous, not just 'no match'.\n\n"
        "Respond with a JSON array:\n"
        '[{"rule_id": <int>, "verdict": "<APPLY|DO_NOT_APPLY|INSUFFICIENT_EVIDENCE>", '
        '"reasoning": "<one sentence>"}, ...]'
    )

    def _call() -> str:
        client = _ai_client()
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return resp.choices[0].message.content

    try:
        raw = cached_chat(prompt, _call)
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            results = []
            for r in parsed:
                if not isinstance(r, dict) or "rule_id" not in r:
                    continue
                verdict = str(r.get("verdict", "")).strip().upper()
                if verdict not in _VALID_VERDICTS:
                    verdict = _VERDICT_DO_NOT_APPLY
                results.append({
                    "rule_id": int(r["rule_id"]),
                    "verdict": verdict,
                    "reasoning": str(r.get("reasoning", "")),
                })
            return results
    except Exception:
        pass
    return []


def run_rrr_match(
    items: List[Dict[str, Any]],
    profile_id: int,
    db_conn,
) -> None:
    """Evaluate and apply approved RRR rules to eligible items. Mutates items in place."""
    rules = list_rrr_rules(db_conn, profile_id, active_only=True)
    if not rules:
        return

    rule_by_id = {r["id"]: r for r in rules}

    for item in items:
        initial_rank = item.get("significance_rank", 0)

        if item.get("dedup_status") == "duplicate":
            continue
        if initial_rank <= 1:
            continue

        eligible_rules = [r for r in rules if _rule_eligible_for_item(r, initial_rank)]
        if not eligible_rules:
            continue

        evaluations = _evaluate_rules_for_item(item, eligible_rules)
        if not evaluations:
            continue

        # Log INSUFFICIENT_EVIDENCE for investigation without acting on them
        for ev in evaluations:
            if ev["verdict"] == _VERDICT_INSUFFICIENT:
                print(
                    f"  ↳ [RRR INSUFFICIENT] rule {ev['rule_id']} | "
                    f"\"{(item.get('title') or '')[:52]}\" | {ev['reasoning']}"
                )

        applicable = [
            ev for ev in evaluations
            if ev["verdict"] == _VERDICT_APPLY and ev["rule_id"] in rule_by_id
        ]
        if not applicable:
            continue

        target_ranks = {rule_by_id[ev["rule_id"]]["override_rank"] for ev in applicable}

        if len(target_ranks) > 1:
            item["pre_rrr_rank"] = initial_rank
            item["rrr_match_outcome"] = "conflict"
            print(
                f"  ↳ [RRR CONFLICT] \"{(item.get('title') or '')[:52]}\" "
                f"| initial rank {initial_rank} | conflicting targets {target_ranks}"
            )
        else:
            target_rank = next(iter(target_ranks))
            winning_rule_id = next(
                ev["rule_id"] for ev in applicable
                if rule_by_id[ev["rule_id"]]["override_rank"] == target_rank
            )
            outcome = "upgraded" if target_rank > initial_rank else "downgraded"
            item["pre_rrr_rank"] = initial_rank
            item["significance_rank"] = target_rank
            item["rrr_rule_id"] = winning_rule_id
            item["rrr_match_outcome"] = outcome
            print(
                f"  ↳ [RRR {outcome.upper()}] \"{(item.get('title') or '')[:52]}\" "
                f"| {initial_rank} → {target_rank} (rule {winning_rule_id})"
            )
