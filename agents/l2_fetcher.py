"""
L2 Deep Fetch Agent (v3.13) — MANDATORY pipeline step, runs after Glossary Match
and before Rank.

For each item it follows the item URL, extracts the full article text (reusing
`extract_article` from url_sources_runner), then makes ONE AI call to produce:
  - l2_summary : 2-3 sentence factual summary in English (what regulation, what changed, effective when)
  - act_ref    : the law/act/gazette reference (clustering key), or "" when none stated

A second sub-step (`extract_law_refs`) runs against the English l2_summary to produce the
3-field legal-reference triplet (law_primary, law_secondary, law_reference) — in English,
bounded to what made the summary, never reading the raw (possibly foreign-language) article.

Failure policy — MANDATORY: any item whose fetch or extraction hard-fails raises
L2FetchError, which stops the run (the controller marks it failed and logs the item).
There is no silent degradation. A genuinely-absent act_ref (article has none) is NOT
a failure — act_ref is simply left empty.
"""

import json
import re
from datetime import datetime, timezone

import requests

from agents.ai_cache import cached_chat
from agents.url_sources_runner import extract_article

_UA = "Mozilla/5.0 (compatible; LegalEagle/3.13; +https://sap.com)"
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


def _summarize(full_text: str, title: str) -> dict:
    """One AI call → {summary}. Raises on unparseable AI output."""
    prompt = (
        "You are a legal-compliance analyst. Read the following regulatory article "
        "and return STRICT JSON only (no markdown fences):\n"
        '{"summary": "..."}\n\n'
        "- summary: 2-3 factual sentences — what regulation, what changed, effective when. "
        "Do not editorialize or add anything not in the text.\n\n"
        f"Title: {title}\n\n"
        f"Article:\n{full_text[:8000]}"
    )

    def _call():
        client = _get_ai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        return response.choices[0].message.content.strip()

    raw = cached_chat(prompt, _call)
    raw = re.sub(r"^```json?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    parsed = json.loads(raw)
    return {"summary": (parsed.get("summary") or "").strip()}


def extract_law_refs(summary_text: str, title: str, known_laws: list[str] | None = None) -> dict:
    """Dedicated L2 sub-step (one AI call) — capture the legal-reference triplet.

    Reads the ENGLISH L2 summary (not the raw article) so output is always English
    and bounded to the references that made the summary. When `known_laws` (the
    profile's registered Law Reference names/numbers) is provided, the model is
    grounded to prefer those exact canonical names — so extraction is consistent and
    downstream Law Match resolves reliably.

    Returns {"primary": str, "secondary": str, "reference": str}.
    Empty strings when a field has no value.
    """
    grounding = ""
    if known_laws:
        grounding = (
            "\nKnown registered laws for this profile — when the item refers to one of "
            "these, use its EXACT canonical name (+ number) for `primary`/`secondary`:\n"
            + "\n".join(f"- {n}" for n in known_laws[:40]) + "\n"
        )
    prompt = (
        "You are a legal-compliance analyst. Read the English regulatory summary and return "
        "STRICT JSON only (no markdown fences):\n"
        '{"primary": "...", "secondary": "...", "reference": "..."}\n\n'
        "primary   = the law whose article/provision is the SUBJECT of this news item "
        "(the operative law that creates/changes the obligation). Include the specific "
        "article or provision after an em-dash when mentioned. "
        "Example: \"Unemployment Insurance Law No. 4447 — temporary Article 36\". "
        "Leave \"\" if no law is the operative subject.\n\n"
        "secondary = the other main law directly cited alongside primary "
        "(the amending law, or the law being amended). One entry only. Leave \"\" if none.\n\n"
        "reference = all remaining legal references listed in this order: "
        "(1) any lesser laws by short form (e.g. \"Law No. 2634\"), "
        "(2) presidential decisions and decrees (e.g. \"Presidential Decision No. 11752\"), "
        "(3) circulars (e.g. \"SGK 2026/21 Circular\"), "
        "(4) official gazettes and other publication references (e.g. \"Official Gazette No. 33362\"). "
        "Join multiple with ' · '. Leave \"\" if none. "
        "Do NOT include verbose law names in parentheses — short-form only.\n\n"
        "KEY RULES:\n"
        "* Circulars, gazettes, and presidential decisions NEVER occupy primary or secondary.\n"
        "* Output must be in English.\n"
        f"{grounding}\n"
        f"Title: {title}\n\n"
        f"Summary:\n{summary_text[:4000]}"
    )

    def _call():
        client = _get_ai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        return response.choices[0].message.content.strip()

    try:
        raw = cached_chat(prompt, _call)
        raw = re.sub(r"^```json?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        parsed = json.loads(raw)
        return {
            "primary": (parsed.get("primary") or "").strip(),
            "secondary": (parsed.get("secondary") or "").strip(),
            "reference": (parsed.get("reference") or "").strip(),
        }
    except Exception as e:
        print(f"    ⚠️  extract_law_refs failed: {e}")
        return {"primary": "", "secondary": "", "reference": ""}


def fetch_l2_for_item(item: dict, known_laws: list[str] | None = None) -> dict:
    """Fetch + summarize one item. Mutates and returns the item dict.

    Sets item['l2_summary'], item['l2_fetched_at']; sets item['act_ref'] only when
    the article names one AND the item doesn't already carry one (glossary_match
    may have filled it from L1). Raises L2FetchError on any hard failure.
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
        result = _summarize(full_text, title)
        # Dedicated legal-reference sub-step reads the English summary (not the raw article)
        # so output is always English and bounded to what made the summary.
        refs = extract_law_refs(result["summary"], title, known_laws=known_laws)
    except L2FetchError:
        raise
    except Exception as e:
        raise L2FetchError(f"L2 fetch failed for {url}: {type(e).__name__}: {e}") from e

    item["l2_summary"] = result["summary"]
    item["l2_fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    item["law_primary"] = refs["primary"]
    item["law_secondary"] = refs["secondary"]
    item["law_reference"] = refs["reference"]
    # act_ref = the primary law (clustering identity); L2 is authoritative over the
    # L1 best-effort value glossary_match may have set.
    if refs["primary"]:
        item["act_ref"] = refs["primary"]
    return item


def run_l2_fetch(items: list[dict], known_laws: list[str] | None = None) -> list[dict]:
    """Run mandatory L2 fetch across all items. Raises L2FetchError on first failure.

    `known_laws` grounds legal-reference extraction with the profile's registered laws.
    Skips items already fetched this run (l2_fetched_at present with a summary).
    """
    for item in items:
        if item.get("l2_fetched_at") and item.get("l2_summary"):
            continue
        fetch_l2_for_item(item, known_laws=known_laws)
    return items
