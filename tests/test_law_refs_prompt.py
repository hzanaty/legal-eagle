"""
Standalone prompt-iteration test for extract_law_refs().
Run: python -m tests.test_law_refs_prompt

Tests different prompt variants against realistic English summaries to find
the optimal rule before changing agents/l2_fetcher.py.
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from configurations.config_loader import creds
from agents.sap_ai_client import SAPAICoreClient

sap_cfg = creds.get("sap_aicore", {})
_client = SAPAICoreClient(
    base_url=sap_cfg["base_url"],
    auth_url=sap_cfg["auth_url"],
    client_id=sap_cfg["client_id"],
    client_secret=sap_cfg["client_secret"],
    chat_deployment_id=sap_cfg["chat_deployment_id"],
    embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
)


def _call_ai(prompt: str) -> dict:
    response = _client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        timeout=30.0,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```json?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw.strip())
    return json.loads(raw)


# ── Test cases ────────────────────────────────────────────────────────────────

CASES = {
    "SGK_circular": {
        "title": "SGK Circular 2026/21: Short-term employment support under Law No. 4447",
        "summary": (
            "The Social Security Institution (SGK) published Circular No. 2026/21 implementing "
            "the short-term employment support scheme established by temporary Article 36 of "
            "Unemployment Insurance Law No. 4447, as amended by Law No. 7590. "
            "The circular also references Law No. 2634 (Tourism Encouragement Law) for eligible "
            "sectors. The scheme is effective from 1 July 2026."
        ),
        "expected": {
            "primary": "Unemployment Insurance Law No. 4447 — temporary Article 36",
            "secondary": "Law No. 7590",
            "reference": "Law No. 2634 · SGK 2026/21 Circular",
        },
    },
    "OVP_presidential": {
        "title": "Presidential Decision No. 11752 on tourism incentives published in Official Gazette",
        "summary": (
            "Presidential Decision No. 11752 was published in Official Gazette No. 33362 on "
            "5 August 2026, introducing new incentive packages for tourism investments. "
            "No primary law is cited as the basis for this decision."
        ),
        "expected": {
            "primary": "",
            "secondary": "",
            "reference": "Presidential Decision No. 11752 · Official Gazette No. 33362",
        },
    },
    "simple_amendment": {
        "title": "Law No. 7410 amends maternity leave provisions",
        "summary": (
            "Law No. 7410 extends statutory maternity leave from 14 to 16 weeks by amending "
            "Article 74 of Labour Law No. 4857. The change is effective from 1 January 2027."
        ),
        "expected": {
            "primary": "Labour Law No. 4857 — Article 74",
            "secondary": "Law No. 7410",
            "reference": "",
        },
    },
}

# ── Prompt variants ───────────────────────────────────────────────────────────

PROMPTS = {}

PROMPTS["v1_current"] = lambda title, summary: (
    "You are a legal-compliance analyst. From the regulatory article below, capture "
    "exactly THREE fields and return STRICT JSON only (no markdown fences):\n"
    '{"primary": "...", "secondary": "...", "reference": "..."}\n\n'
    "1. primary   — the Primary Law / Article (the main actual law + its article/provision number)\n"
    "2. secondary — the Secondary Law / Article (the next most important actual law + article/provision)\n"
    "3. reference — everything else: gazette numbers, presidential-decision numbers, circular "
    "numbers, decree numbers, publication numbers, etc.\n\n"
    "RULE: Only ACTUAL LAWS and their article/provision numbers go into primary and secondary. "
    "Gazette / presidential-decision / circular / decree / publication numbers must NEVER go into "
    "primary or secondary — they go into reference. Use \"\" for any field with no value. "
    "If multiple items belong in reference, join them with ' · '.\n\n"
    f"Title: {title}\n\nArticle:\n{summary}"
)

PROMPTS["v2_english_summary"] = lambda title, summary: (
    "You are a legal-compliance analyst. The text below is an ENGLISH summary of a regulatory "
    "article. Identify the legal references and return STRICT JSON only (no markdown fences):\n"
    '{"primary": "...", "secondary": "...", "reference": "..."}\n\n'
    "DEFINITIONS:\n"
    "- primary   : the OPERATIVE law — the law that creates or substantially changes the legal "
    "obligation this news is about — with its specific article/provision (e.g. "
    "\"Unemployment Insurance Law No. 4447 — temporary Article 36\"). Leave \"\" if none.\n"
    "- secondary : the other PRINCIPAL law directly involved (e.g. the amending law, or the law "
    "being amended). One law only. Leave \"\" if none.\n"
    "- reference : EVERYTHING else — lesser laws, circulars, gazettes, presidential decisions, "
    "decree numbers, publication numbers. Separate multiple items with ' · '. Leave \"\" if none.\n\n"
    "STRICT RULES:\n"
    "* Circulars, gazettes, presidential decisions, decrees NEVER go in primary or secondary.\n"
    "* If the article is only a presidential decision / gazette / circular with no underlying law "
    "cited, primary and secondary must be \"\".\n"
    "* Output must be English (input is already English).\n\n"
    f"Title: {title}\n\nSummary:\n{summary}"
)

PROMPTS["v4_ordered_refs"] = lambda title, summary: (
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
    "* Output must be in English.\n\n"
    f"Title: {title}\n\nSummary:\n{summary}"
)

PROMPTS["v3_operative_first"] = lambda title, summary: (
    "You are a legal-compliance analyst. Read the English regulatory summary and return "
    "STRICT JSON only (no markdown fences):\n"
    '{"primary": "...", "secondary": "...", "reference": "..."}\n\n'
    "primary   = the law whose article/provision is the SUBJECT of this news item "
    "(i.e. the operative law that creates/changes the obligation). Include the specific "
    "article or provision number after an em-dash when mentioned. "
    "Example: \"Unemployment Insurance Law No. 4447 — temporary Article 36\". "
    "If no law is the operative subject (e.g. only a presidential decision), use \"\".\n\n"
    "secondary = the other main law directly cited alongside primary (e.g. the amending law, "
    "or the law being amended). One entry only. Use \"\" if there is none.\n\n"
    "reference = all remaining legal references: lesser laws, amending acts not in primary/secondary, "
    "circulars (e.g. SGK 2026/21), gazettes (e.g. Official Gazette No. 33362), presidential "
    "decisions, decrees, publication numbers. Join multiple with ' · '. Use \"\" if none.\n\n"
    "KEY RULE: Circulars, gazettes, and presidential decisions NEVER occupy primary or secondary. "
    "They always go to reference.\n\n"
    f"Title: {title}\n\nSummary:\n{summary}"
)

# ── Runner ────────────────────────────────────────────────────────────────────

def run():
    for prompt_name, prompt_fn in PROMPTS.items():
        print(f"\n{'='*70}")
        print(f"PROMPT: {prompt_name}")
        print('='*70)
        for case_name, case in CASES.items():
            print(f"\n  Case: {case_name}")
            prompt = prompt_fn(case["title"], case["summary"])
            try:
                result = _call_ai(prompt)
                ok_p = result.get("primary","") == case["expected"]["primary"]
                ok_s = result.get("secondary","") == case["expected"]["secondary"]
                ok_r = result.get("reference","") == case["expected"]["reference"]
                print(f"  primary   [{' OK' if ok_p else 'FAIL'}]  got: {result.get('primary','')!r}")
                print(f"  secondary [{' OK' if ok_s else 'FAIL'}]  got: {result.get('secondary','')!r}")
                print(f"  reference [{' OK' if ok_r else 'FAIL'}]  got: {result.get('reference','')!r}")
                if not (ok_p and ok_s and ok_r):
                    print(f"  expected primary  : {case['expected']['primary']!r}")
                    print(f"  expected secondary: {case['expected']['secondary']!r}")
                    print(f"  expected reference: {case['expected']['reference']!r}")
            except Exception as e:
                print(f"  ERROR: {e}")

if __name__ == "__main__":
    run()
