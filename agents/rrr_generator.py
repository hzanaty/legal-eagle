"""
RRR Generator (v3.92) — derive structured re-rank rules from human override decisions.

Public interface:
    generate_rrr_rule(item, override_rank, human_reason, db_conn, profile_id) -> dict
        Returns {"why": str, "when": str, "when_not": str, "sufficient": bool,
                 "readiness": "ok" | "insufficient" | "failed"}
        - readiness="ok"           → valid draft; safe to offer as a reusable rule
        - readiness="insufficient" → evidence too thin; LPM can fill gaps and approve manually
        - readiness="failed"       → technical generation error; why/when/when_not unusable

    is_rule_sufficient(why, when, when_not) -> bool
        True when none of the three sections contain failure markers AND all are non-empty.

    validate_rule_sections(why, when, when_not) -> str | None
        Returns an error message string if the sections fail structural checks, else None.
        Used before saving a rule to block empty sections, stale drafts, and failure text.
"""
import json
import re
from typing import Any, Dict, Optional

from agents.sap_ai_client import SAPAICoreClient
from agents.ai_cache import cached_chat
from configurations.config_loader import creds

_RANK_LABELS = {1: "Noise", 2: "Signal", 3: "Watch", 4: "Legal Change", 5: "Urgent"}

# Text patterns that mark a section as containing a generation failure or unresolvable insufficiency.
# A rule containing any of these must not be saved as an active reusable rule.
_FAILURE_PREFIXES = (
    "insufficient:",
    "rule generation failed",
    "n/a",
    "not applicable",
)

# Placeholder strings that indicate an unresolved draft (common in AI outputs)
_PLACEHOLDER_PATTERNS = ("tbd", "to be determined", "to be confirmed", "[insert", "<insert")


def is_rule_sufficient(why: str, when: str, when_not: str) -> bool:
    """Return False if any rule section is empty or contains a failure/insufficiency marker."""
    for text in (why, when, when_not):
        lower = (text or "").strip().lower()
        if not lower:
            return False
        if any(lower.startswith(p) for p in _FAILURE_PREFIXES):
            return False
    return True


def validate_rule_sections(why: str, when: str, when_not: str) -> Optional[str]:
    """Structural validation before saving a rule.

    Returns an error message string if validation fails, else None.
    This runs on both AI-generated drafts and LPM-edited text.
    It blocks obviously broken content without claiming the LPM's legal conclusion is correct.
    """
    for label, text in (("WHY", why), ("WHEN", when), ("WHEN NOT", when_not)):
        stripped = (text or "").strip()
        if not stripped:
            return f"{label} section is required."
        lower = stripped.lower()
        if any(lower.startswith(p) for p in _FAILURE_PREFIXES):
            return f"{label} section contains a generation failure marker and cannot be saved."
        for pat in _PLACEHOLDER_PATTERNS:
            if pat in lower:
                return f"{label} section contains an unresolved placeholder ('{pat}'). Edit before saving."
    return None


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


def _build_sap_grounding(item: Dict[str, Any], db_conn, profile_id: int) -> str:
    """Build a SAP localization grounding block from approved profile/item context.

    Sources (in order of reliability):
    1. profile country code + LoB (from DB or item)
    2. law references (from impact analysis, already vetted by the Law Match stage)
    3. RCM match status (approved SAP regulatory change management scope)
    4. authority name (from SAP authority registry, not AI-inferred)
    5. impact evidence (verbatim operative clauses from the article, selected by AI Attributor)
    """
    lines = []

    # --- Profile context ---
    if db_conn is not None and profile_id:
        try:
            row = db_conn.execute(
                "SELECT country_code, lob FROM profiles WHERE id=?", (profile_id,)
            ).fetchone()
            if row:
                lines.append(f"Profile jurisdiction: {row['country_code']} / {row['lob']}")
        except Exception:
            pass

    # --- Law references (authoritative: from Law Match stage, not AI-generated) ---
    law_raw = item.get("law_references_json") or "[]"
    try:
        law_refs = json.loads(law_raw)
        if law_refs:
            law_strs = "; ".join(
                f"{r.get('type', '?')} {r.get('number', '?')} {r.get('label', '') or ''}"
                for r in law_refs
            )
            lines.append(f"Matched law references: {law_strs}")
    except Exception:
        pass

    # --- RCM match status (SAP Regulatory Change Management scope) ---
    rcm = item.get("rcm_match_status") or ""
    if rcm:
        rcm_desc = {
            "tracked": "article covers a change already tracked in SAP RCM",
            "net-new": "article introduces a regulatory change not yet in SAP RCM",
        }.get(rcm, rcm)
        lines.append(f"RCM match: {rcm_desc}")

    # --- Authority (from SAP authority registry, only when reliably assigned) ---
    auth_status = item.get("authority_status") or ""
    auth_name = item.get("authority_name") or ""
    if auth_name and auth_status == "configured":
        lines.append(f"Issuing authority (configured): {auth_name}")

    # --- Impact evidence (verbatim operative clauses selected by the Attributor) ---
    ev_raw = item.get("impact_evidence_json") or "[]"
    try:
        evidence = json.loads(ev_raw)
        if evidence:
            lines.append("Operative clauses from article:")
            for clause in evidence[:5]:
                lines.append(f"  - {clause}")
    except Exception:
        pass

    return "\n".join(lines) if lines else "(no additional SAP grounding available)"


def generate_rrr_rule(
    item: Dict[str, Any],
    override_rank: int,
    human_reason: str,
    db_conn=None,
    profile_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate WHY / WHEN / WHEN NOT rule sections for an approved rank override.

    Uses SAP localization grounding (law refs, RCM status, authority, impact evidence)
    in addition to article text.

    Returns:
        {"why": str, "when": str, "when_not": str, "sufficient": bool}

    When sufficient=False the why section begins with "INSUFFICIENT: " and lists the
    missing decision-critical facts that prevent a reliable rule from being written.
    All failure / N/A responses are returned as sufficient=False; they must never be
    saved as active reusable rules.
    """
    title = (item.get("title") or "").strip()
    l2_summary = (item.get("l2_summary") or "").strip()
    content = l2_summary or (item.get("content") or "")[:1500]

    try:
        topic_labels = json.loads(item.get("topic_label") or "[]")
        topic_text = ", ".join(t for t in topic_labels if t and t != "General") or "None"
    except Exception:
        topic_text = "None"

    original_rank = item.get("significance_rank") or 0
    original_rank_label = _RANK_LABELS.get(original_rank, "?")
    override_rank_label = _RANK_LABELS.get(override_rank, "?")

    pid = profile_id or item.get("profile_id")
    sap_grounding = _build_sap_grounding(item, db_conn, pid)

    prompt = f"""You are a legal regulatory classification expert for SAP HCM/FIN compliance monitoring.

A Legal Process Manager has reviewed a regulatory news item and overridden its system-assigned rank.
Derive a SPECIFIC, TESTABLE, REUSABLE rule that captures this decision.

## Override Decision
- System rank: {original_rank} ({original_rank_label})
- Human-approved rank: {override_rank} ({override_rank_label})
- Human reason: "{human_reason}"

## News Item
Title: "{title}"
Regulatory topics: {topic_text}
Summary: "{content[:1000]}"

## SAP Localization Grounding (authoritative — do not contradict or invent beyond this)
{sap_grounding}

## Internal Analysis (reason through each dimension before writing output)
1. What ranking principle does this override establish? Is it an upgrade or downgrade?
2. What regulatory subject type is this (minimum wage, social insurance contribution, leave entitlement, etc.)?
3. Which country/jurisdiction and Line of Business does it apply to?
4. Which employees or payroll elements are directly affected?
5. What specific, observable signals in an article text would trigger this rule?
6. Under what conditions should this rule NOT apply (exceptions, exclusions, out-of-scope signals)?
7. Which SAP products are genuinely affected by this type of change (do not invent capabilities)?
8. What level of evidence in the article is needed to confirm applicability?
9. Why does rank {override_rank} ({override_rank_label}) fit the significance criteria for this type?
10. When should this rule be revisited or retired?

If you cannot write a reliable, testable rule because critical information is missing from the article
and grounding, set "readiness" to "insufficient" and begin the WHY section with "INSUFFICIENT: " listing
the missing decision-critical facts. The LPM can then fill in the gaps and approve the rule manually.

## Output Requirements
- SPECIFIC: name the regulatory type, jurisdiction, and affected population
- TESTABLE: every WHEN condition must be verifiable from article text alone
- Do NOT invent SAP capabilities, law numbers, or facts beyond what the grounding provides
- Do NOT add placeholders ("TBD", "N/A", "to be confirmed")

Respond with JSON:
{{
  "readiness": "ok | insufficient",
  "why": "1–2 sentences: what change type this is and why it warrants rank {override_rank}.",
  "when": "Conditions that must ALL be present in the article for this rule to apply. Each on its own line starting with '- '.",
  "when_not": "Exceptions that override the WHEN conditions. Each on its own line starting with '- '."
}}"""

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
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            why = str(parsed.get("why", "")).strip()
            when = str(parsed.get("when", "")).strip()
            when_not = str(parsed.get("when_not", "")).strip()
            if why and when and when_not:
                # Default to "insufficient" — a missing or unrecognised readiness signal
                # means the AI did not confirm the rule was ready; treat as not ready.
                ai_readiness = str(parsed.get("readiness", "insufficient")).strip().lower()
                if ai_readiness not in ("ok", "insufficient"):
                    ai_readiness = "insufficient"
                # The text-prefix check is the definitive gate — AI readiness is advisory
                suffix_ok = is_rule_sufficient(why, when, when_not)
                readiness = ai_readiness if suffix_ok else "insufficient"
                return {
                    "why": why,
                    "when": when,
                    "when_not": when_not,
                    "sufficient": readiness == "ok",
                    "readiness": readiness,
                }
    except Exception:
        pass

    return {
        "why": "Rule generation failed — AI unavailable or parse error.",
        "when": "N/A",
        "when_not": "N/A",
        "sufficient": False,
        "readiness": "failed",
    }
