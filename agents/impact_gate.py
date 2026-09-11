"""
Impact gate (v3.18) — the relevance + change-assessment stage.

One AI call per item over the L2 summary, grounded by a per-profile RUBRIC, returns
the semantic signals the deterministic Rank consumes:
    operational_impact          : 0-3  (degree of payroll operational impact)
    regulatory_change_confirmed : bool  (current-news evidence of an actual change)
    preparation_required        : bool  (the change needs advance preparation)
    effective_date              : YYYY-MM-DD | None  (moved here out of the ranker)

Relevance lives here (not in Rank): an operational_impact of 0 with no glossary/law
match falls to Noise in Rank. No hard drop — everything is scored, nothing discarded.
"""

import json
import re
import sqlite3

from agents.ai_cache import cached_chat

# Editable per-profile via the `impact_rubric` setting; this is the seeded default.
DEFAULT_RUBRIC = (
    "In scope = a requirement that affects PAYROLL: how to calculate, pay, or deduct "
    "(wages, income tax, stamp tax, social security/SGK, unemployment insurance, "
    "benefits, allowances, leave, severance, minimum wage, incentives/support). "
    "Out of scope = general economic, political, or market news with no direct payroll obligation."
)


def _get_ai_client():
    from configurations.config_loader import creds
    from agents.sap_ai_client import SAPAICoreClient
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
    )


def _assess_one(item: dict, rubric: str) -> dict:
    # v3.31: reason on the L2 summary + preserved impact_evidence + glossary/law/authority
    # context — NEVER re-read the full article.
    summary = (item.get("l2_summary") or item.get("content") or "")[:1500]
    title = item.get("title") or ""
    evidence = item.get("impact_evidence")
    if evidence is None:
        try:
            evidence = json.loads(item.get("impact_evidence_json") or "[]")
        except Exception:
            evidence = []
    evidence_block = "\n".join(f"  - {e}" for e in (evidence or [])) or "  (none extracted)"
    ctx = []
    if item.get("topic_label"):
        ctx.append(f"glossary labels: {item.get('topic_label')}")
    if item.get("law_primary"):
        ctx.append(f"law: {item.get('law_primary')}" + (f" (status: {item.get('law_status')})" if item.get('law_status') else ""))
    if item.get("primary_authority"):
        ctx.append(f"responsible authority: {item.get('primary_authority')}")
    context_block = "; ".join(ctx) or "(none)"
    prompt = (
        "You are a payroll-compliance relevance analyst. Using the scope rubric below, assess "
        "one news item and return STRICT JSON only (no fences):\n"
        '{"operational_impact": <0-3>, "regulatory_change_confirmed": <true|false>, '
        '"preparation_required": <true|false>, "effective_date": "<YYYY-MM-DD or null>"}\n\n'
        f"SCOPE RUBRIC:\n{rubric}\n\n"
        "operational_impact: 0 = out of scope / no payroll impact; 1 = indirect or minor; "
        "2 = clear operational impact (rates, thresholds, deadlines, process); "
        "3 = major direct change to how payroll is calculated/paid/deducted.\n"
        "regulatory_change_confirmed: true only if an ACTUAL enacted/decided regulatory change "
        "(not speculation, opinion, or a general discussion).\n"
        "preparation_required: true if the change requires configuration/process preparation.\n"
        "effective_date: the date when the measure becomes legally or operationally applicable. "
        "If the article explicitly says the measure is effective immediately / enters into force "
        "upon publication / applies from the publication date, then use that date. "
        "Do not assume publication, approval, Gazette, decision, or article date is the effective "
        "date unless the article explicitly links that date to entry into force/applicability. "
        "If no explicit effective/applicability date is stated, return null.\n"
        "Base your judgment on the IMPACT EVIDENCE clauses below (the operative details); the summary "
        "may compress them away.\n\n"
        f"Title: {title}\n\nSummary: {summary}\n\n"
        f"Impact evidence (verbatim clauses):\n{evidence_block}\n\n"
        f"Context: {context_block}"
    )

    def _call():
        client = _get_ai_client()
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content

    try:
        raw = cached_chat(prompt, _call)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(m.group() if m else raw)
        oi = max(0, min(3, int(parsed.get("operational_impact", 0) or 0)))
        _impact_labels = {0: "out-of-scope", 1: "minor", 2: "operational", 3: "major"}
        print(
            f"  ↳ [IMPACT] \"{(item.get('title') or '')[:52]}\" "
            f"→ {_impact_labels.get(oi, str(oi))} \xb7 "
            f"change={'yes' if parsed.get('regulatory_change_confirmed') else 'no'} \xb7 "
            f"prep={'yes' if parsed.get('preparation_required') else 'no'} \xb7 "
            f"eff={parsed.get('effective_date') or 'none'}"
        )
        return {
            "operational_impact": oi,
            "regulatory_change_confirmed": 1 if parsed.get("regulatory_change_confirmed") else 0,
            "preparation_required": 1 if parsed.get("preparation_required") else 0,
            "effective_date": _norm_date(parsed.get("effective_date")),
        }
    except Exception as e:
        print(f"    ⚠️  impact assess failed ({type(e).__name__}); conservative fallback (impact=1)")
        # Conservative fallback: keep the item visible as a Watch rather than dropping it.
        return {"operational_impact": 1, "regulatory_change_confirmed": 0,
                "preparation_required": 0, "effective_date": item.get("effective_date")}


def _norm_date(value):
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


def assess_impact(items: list[dict], conn: sqlite3.Connection, profile_id: int) -> dict:
    """Run the Impact gate over items; mutate + persist the semantic signals."""
    if not items:
        return {"assessed": 0}
    from configurations.db import get_setting
    rubric = get_setting(conn, profile_id, "impact_rubric", DEFAULT_RUBRIC) or DEFAULT_RUBRIC
    for it in items:
        res = _assess_one(it, rubric)
        it.update(res)
    _persist(items, conn, profile_id)
    return {"assessed": len(items)}


def _persist(items: list[dict], conn: sqlite3.Connection, profile_id: int | None) -> None:
    for it in items:
        vals = (it.get("operational_impact"), it.get("regulatory_change_confirmed"),
                it.get("preparation_required"), it.get("effective_date"))
        item_id = it.get("id")
        if item_id:
            conn.execute(
                "UPDATE news_items SET operational_impact=?, regulatory_change_confirmed=?, "
                "preparation_required=?, effective_date=? WHERE id=?", (*vals, item_id))
            continue
        src_type = it.get("source_type", "RSS")
        src_id = it.get("source_id") or it.get("guid") or it.get("tweet_id")
        url = it.get("url") or it.get("link")
        hash_sig = it.get("hash_signature")
        pid = it.get("profile_id") or profile_id
        base = ("UPDATE news_items SET operational_impact=?, regulatory_change_confirmed=?, "
                "preparation_required=?, effective_date=? WHERE profile_id=? AND source_type=? AND ")
        if src_id and pid:
            conn.execute(base + "source_id=?", (*vals, pid, src_type, src_id))
        elif url and pid:
            conn.execute(base + "url=?", (*vals, pid, src_type, url))
        elif hash_sig and pid:
            conn.execute(base + "hash_signature=?", (*vals, pid, src_type, hash_sig))
    conn.commit()
