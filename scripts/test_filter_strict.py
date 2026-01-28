#!/usr/bin/env python3
"""
Strict filter gate tester for Legal Eagle.

This script validates the new category-aware glossary mapping, strict glossary gate,
and domain/country gating in agents/news_filter.py without requiring full pipeline runs.

Usage examples:
  python3 scripts/test_filter_strict.py --lob HCM --country SA
  python3 scripts/test_filter_strict.py --lob FIN --country AE --allowed www.gosi.gov.sa www.uqn.gov.sa
  python3 scripts/test_filter_strict.py --profile-id 1 --lob HCM --country SA
  python3 scripts/test_filter_strict.py --dry --lob HCM --country SA

Notes:
- If LEGAL_EAGLE_OPENAI_API_KEY is set and --dry is NOT passed, the script will call the LLM classifier.
- If --dry is passed or no API key is set, the script will only apply the strict gates and simulate classification.
"""

import os
import sys
import argparse
import json
from typing import Dict, Any, List

# Ensure project root is on sys.path when running as scripts/test_filter_strict.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    # Import filter functions and entry point
    from agents.news_filter import (
        get_relevant_news,
        matches_glossary,
        _parse_domain,
        mentions_country,
    )
except Exception as e:
    print(f"❌ Failed to import agents.news_filter: {e}")
    sys.exit(1)

# Optional: load glossary from DB
def try_load_glossary_from_db(profile_id: int):
    try:
        from configurations.config_loader import load_glossary
        gf = load_glossary(profile_id)
        return gf
    except Exception as e:
        print(f"⚠️ Could not load glossary from DB for profile_id={profile_id}: {e}")
        return None

def build_category_glossary_text(glossary_flat: Dict[str, Any], lob: str) -> Dict[str, str]:
    """
    Replicates the controller's category-aware builder:
    - Use per-term category (HCM/FIN)
    - Default uncategorized terms to active LoB
    - Include synonyms in the same category
    Returns: dict with comma-joined strings for HCM/FIN and OTHER descriptor.
    """
    groups = {"HCM": [], "FIN": []}
    active_lob = "FIN" if (lob or "").upper() == "FIN" else "HCM"
    for term in (glossary_flat.get("terms") or []):
        name = (term.get("term") or "").strip()
        if not name:
            continue
        cat = (term.get("category") or "").upper()
        if cat not in ("HCM", "FIN"):
            cat = active_lob
        groups[cat].append(name)
        for s in (term.get("synonyms") or []):
            s_name = (s or "").strip()
            if s_name:
                groups[cat].append(s_name)
    hcm_text = ", ".join(sorted(set(groups["HCM"]))) if groups["HCM"] else ""
    fin_text = ", ".join(sorted(set(groups["FIN"]))) if groups["FIN"] else ""
    other_text = "Any content not related to HCM or FIN"
    return {"HCM": hcm_text, "FIN": fin_text, "OTHER": other_text}

def build_fallback_glossary(lob: str) -> Dict[str, Any]:
    """
    Fallback glossary if DB not available. Provides minimal coverage for test cases.
    """
    if (lob or "").upper() == "FIN":
        terms = [
            {"term": "VAT", "category": "FIN", "synonyms": ["value-added tax"]},
            {"term": "tax", "category": "FIN", "synonyms": ["corporate tax", "income tax"]},
            {"term": "Zakat", "category": "FIN", "synonyms": []},
        ]
    else:
        terms = [
            {"term": "Wage Protection", "category": "HCM", "synonyms": ["WPS"]},
            {"term": "iqama", "category": "HCM", "synonyms": ["residency permit"]},
            {"term": "visa", "category": "HCM", "synonyms": []},
        ]
    return {"terms": terms}

def sample_items(country_slug: str) -> List[Dict[str, Any]]:
    """
    Create sample items:
    - HCM item (should pass for HCM LoB): Wage Protection with SA mention and whitelisted domain
    - General government announcement (should drop): cabinet meeting, foreign policy
    - Wrong-country FIN item (should drop when country gate is active for SA/HCM): UAE VAT
    """
    return [
        {
            "title": "Wage Protection Program: new compliance window announced",
            "content": "Saudi Arabia Ministry announces updates to the Wage Protection System (WPS) for private sector. Employers must comply within 90 days.",
            "url": "https://www.gosi.gov.sa/ar/MediaCenter/News/NewsDetails/1/18122025",
        },
        {
            "title": "Cabinet meeting discusses foreign policy priorities",
            "content": "General government announcement on international relations and diplomatic visits. No changes to labor or finance regulations.",
            "url": "https://www.example.com/news/politics/cabinet-meeting",
        },
        {
            "title": "UAE VAT rate discussion in 2026",
            "content": "United Arab Emirates officials consider VAT changes. Businesses to prepare for potential adjustments.",
            "url": "https://www.mof.gov.ae/en/news/vat-update",
        },
    ]

def run_test(profile_id: int, lob: str, country: str, allowed_domains: List[str], dry: bool):
    glossary_flat = try_load_glossary_from_db(profile_id) if profile_id else None
    if not glossary_flat:
        glossary_flat = build_fallback_glossary(lob)

    glossary_text = build_category_glossary_text(glossary_flat, lob)
    items = sample_items(country)
    openai_api_key = os.environ.get("LEGAL_EAGLE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""

    # Gating summary
    allowed_set = set([d.lower() for d in allowed_domains or []])
    active_lob = "FIN" if (lob or "").upper() == "FIN" else "HCM"

    prefilter_pass = []
    for it in items:
        title = it.get("title", "") or ""
        content = it.get("content", "") or ""
        text = f"{title} {content}".strip()
        url = it.get("url") or ""
        domain = _parse_domain(url) if url else ""

        domain_ok = (not allowed_set) or (domain in allowed_set) or mentions_country(text, country)
        glossary_ok = matches_glossary(text, glossary_text, lob)
        it["_domain"] = domain
        it["_domain_ok"] = domain_ok
        it["_glossary_ok"] = glossary_ok
        if domain_ok and glossary_ok:
            prefilter_pass.append(it)

    print("\n=== Prefilter Gate Results ===")
    for it in items:
        print(f"- [{it.get('title')}] domain={it.get('_domain')} domain_ok={it.get('_domain_ok')} glossary_ok={it.get('_glossary_ok')}")

    if dry or not openai_api_key:
        print("\n⚠️ Running in DRY mode (no LLM). Accepting items that passed gates and tagging with active LoB.")
        relevant = []
        for it in prefilter_pass:
            it["category"] = active_lob
            relevant.append(it)
        print(f"\n✅ Relevant items (dry): {len(relevant)}\n")
        print(json.dumps({"items": relevant}, ensure_ascii=False, indent=2))
        return

    # Full path with LLM classification
    print("\n🧹 Running strict filter with LLM classification...")
    result = get_relevant_news(items, openai_api_key, glossary_text, "en", lob, allowed_domains, country)
    relevant = result.get("items", [])
    errors = result.get("errors", [])

    print(f"\n✅ Relevant items: {len(relevant)} | ⚠️ Errors: {len(errors)}\n")
    print(json.dumps({"items": relevant, "errors": errors}, ensure_ascii=False, indent=2))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-id", type=int, default=0, help="Profile ID to load glossary from DB (optional)")
    ap.add_argument("--lob", type=str, default="HCM", choices=["HCM", "FIN"], help="Line of Business")
    ap.add_argument("--country", type=str, default="SA", help="Country slug/name for mentions gating (>=3 chars recommended)")
    ap.add_argument("--allowed", nargs="*", default=["www.gosi.gov.sa", "www.uqn.gov.sa"], help="Allowed domains for gating")
    ap.add_argument("--dry", action="store_true", help="Run without LLM, only strict gates")
    args = ap.parse_args()

    run_test(args.profile_id, args.lob, args.country, args.allowed, args.dry)

if __name__ == "__main__":
    main()
