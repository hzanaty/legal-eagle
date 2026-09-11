"""
L2 Deep Fetch Agent — MANDATORY pipeline step (runs right after Compare, before
Glossary/Law/Impact/Rank). "Read rich once": ONE AI call over the FULL article
returns everything downstream needs, so nothing re-reads the long article.

Single article-grounded call (`_analyze_article`) → STRICT JSON:
  - summary          : 2-3 factual English sentences (stays short)
  - law_primary      : the operative law (+ specific article after an em-dash), or ""
  - law_secondary    : the other main law directly cited, or ""
  - references        : ordered list of NON-law citations, each {type, number, label}
                        (presidential decisions, gazettes, circulars, decrees, communiques …)
                        — every identifier preserved, never collapsed
  - impact_evidence  : compact list of the EXACT clauses that may indicate operational
                        HCM/payroll impact (verbatim snippets) — consumed by the Impact gate
  - primary_authority: the government body PRIMARILY RESPONSIBLE for the overall
                        regulatory/policy subject (subject-owner rule) — mapped to a
                        registered authority downstream (or left unknown)

References/laws/authority are extracted from the ARTICLE, never from the generated
summary. Failure policy — MANDATORY: any fetch/extraction hard-failure raises
L2FetchError and stops the run.
"""

import json
import re
from datetime import datetime, timezone

import requests

from agents.ai_cache import cached_chat
from agents.url_sources_runner import extract_article

_UA = "Mozilla/5.0 (compatible; LegalEagle; +https://sap.com)"
_TIMEOUT = 30


class L2FetchError(Exception):
    """Raised when an item's L2 fetch/extraction fails — stops the run."""


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


def _fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _analyze_article(full_text: str, title: str,
                     known_laws: list[str] | None = None,
                     known_authorities: list[str] | None = None) -> dict:
    """ONE AI call over the full article → the structured L2 output (see module docstring)."""
    laws_block = ""
    if known_laws:
        laws_block = ("\nRegistered laws for this profile — when the item refers to one, use its "
                      "EXACT canonical name (+ number) for law_primary/law_secondary:\n"
                      + "\n".join(f"- {n}" for n in known_laws[:40]) + "\n")
    auth_block = ""
    if known_authorities:
        auth_block = ("\nKnown authorities for this profile — prefer the exact matching name for "
                      "primary_authority when one fits:\n"
                      + "\n".join(f"- {n}" for n in known_authorities[:40]) + "\n")

    prompt = (
        "You are a legal-compliance analyst. Read the FULL regulatory article below and return "
        "STRICT JSON only (no markdown fences), all values in English:\n"
        '{"summary": "...", "law_primary": "...", "law_secondary": "...", '
        '"references": [{"type": "...", "number": "...", "label": "..."}], '
        '"impact_evidence": ["..."], "primary_authority": "..."}\n\n'
        "FIELDS:\n"
        "- summary: 2-3 factual sentences — what regulation, what changed, effective when. No editorializing.\n"
        "- law_primary: the operative law that creates/changes the obligation, with the specific article "
        "after an em-dash when stated (e.g. \"Unemployment Insurance Law No. 4447 — temporary Article 36\"). "
        "\"\" if none. law_secondary: the other main law directly cited, else \"\".\n"
        "- references: an ARRAY of every NON-law citation, each as {type, number, label}. "
        "type ∈ presidential_decision | official_gazette | circular | decree | communique | other. "
        "PRESERVE each identifier/number; NEVER collapse two references into one; [] if none. "
        "Example: [{\"type\":\"presidential_decision\",\"number\":\"11752\",\"label\":\"Presidential Decision No. 11752\"},"
        "{\"type\":\"official_gazette\",\"number\":\"33362\",\"label\":\"Official Gazette No. 33362\"}].\n"
        "- impact_evidence: the EXACT clauses/sentences (verbatim, short) that may indicate operational "
        "HCM/payroll impact (how to calculate, pay, or deduct; who it applies to; conditions). [] if none.\n"
        "- primary_authority: the government body PRIMARILY RESPONSIBLE for the overall subject — the one "
        "that OWNS / PREPARES / ISSUES / ADMINISTERS the change/program. Do NOT pick a body merely mentioned "
        "as an affected body, implementation participant, system owner, data-sharing party, or beneficiary. "
        "\"\" if unclear.\n\n"
        "KEY RULES:\n"
        "* Circulars, gazettes, presidential decisions, decrees NEVER go in law_primary/law_secondary — only in references.\n"
        "* Extract from the ARTICLE, not from your own summary.\n"
        f"{laws_block}{auth_block}\n"
        f"Title: {title}\n\nArticle:\n{full_text[:8000]}"
    )

    def _call():
        client = _get_ai_client()
        r = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}], timeout=40.0,
        )
        return r.choices[0].message.content.strip()

    raw = cached_chat(prompt, _call)
    raw = re.sub(r"^```json?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    parsed = json.loads(raw)

    refs = []
    for r in (parsed.get("references") or []):
        if not isinstance(r, dict):
            continue
        label = (r.get("label") or "").strip()
        if not label:
            continue
        refs.append({"type": (r.get("type") or "other").strip(),
                     "number": (str(r.get("number")).strip() if r.get("number") else ""),
                     "label": label})
    evidence = [str(e).strip() for e in (parsed.get("impact_evidence") or []) if str(e).strip()]
    return {
        "summary": (parsed.get("summary") or "").strip(),
        "law_primary": (parsed.get("law_primary") or "").strip(),
        "law_secondary": (parsed.get("law_secondary") or "").strip(),
        "references": refs,
        "impact_evidence": evidence,
        "primary_authority": (parsed.get("primary_authority") or "").strip(),
    }


def fetch_l2_for_item(item: dict, known_laws: list[str] | None = None,
                      known_authorities: list[str] | None = None) -> dict:
    """Fetch the full article + one structured analysis call. Mutates and returns the item.

    Raises L2FetchError on any hard failure (mandatory stage).
    """
    url = item.get("url") or item.get("link")
    if not url:
        raise L2FetchError(f"item {item.get('id') or item.get('title')!r} has no URL")

    try:
        html = _fetch_html(url)
        article = extract_article(url, url, html)
        full_text = article.get("content") or ""
        if not full_text.strip():
            raise L2FetchError(f"no article text extracted from {url}")
        title = item.get("title") or article.get("title") or ""
        res = _analyze_article(full_text, title, known_laws=known_laws, known_authorities=known_authorities)
    except L2FetchError:
        raise
    except Exception as e:
        raise L2FetchError(f"L2 fetch failed for {url}: {type(e).__name__}: {e}") from e

    item["l2_summary"] = res["summary"]
    item["l2_fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    item["law_primary"] = res["law_primary"]
    item["law_secondary"] = res["law_secondary"]
    # Structured references (v3.25) + a derived joined string for back-compat display.
    item["references"] = res["references"]
    item["law_references_json"] = json.dumps(res["references"], ensure_ascii=False)
    item["law_reference"] = " · ".join(r["label"] for r in res["references"])
    # Impact evidence (v3.31) — consumed by the Impact gate, never re-reading the article.
    item["impact_evidence"] = res["impact_evidence"]
    item["impact_evidence_json"] = json.dumps(res["impact_evidence"], ensure_ascii=False)
    # Responsible-authority candidate (v3.26) — mapped to a registered authority downstream.
    item["primary_authority"] = res["primary_authority"]
    # act_ref = the operative law (clustering candidate key); L2 is authoritative.
    if res["law_primary"]:
        item["act_ref"] = res["law_primary"]
    return item


def run_l2_fetch(items: list[dict], known_laws: list[str] | None = None,
                 known_authorities: list[str] | None = None) -> list[dict]:
    """Run the mandatory L2 analysis across all items. Raises L2FetchError on first failure.

    `known_laws` / `known_authorities` ground law and responsible-authority extraction.
    Skips items already analyzed this run.
    """
    for item in items:
        if item.get("l2_fetched_at") and item.get("l2_summary"):
            continue
        fetch_l2_for_item(item, known_laws=known_laws, known_authorities=known_authorities)
    return items
