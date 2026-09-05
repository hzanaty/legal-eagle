"""
RCM Filler (v3.6) — fills the official RCM announcement template with AI once per announcement.

Result is stored in news_announcements.announcement_rcm_json (JSON string).
Subsequent calls return the saved value without re-invoking AI.
"""

import json
import os
import re

from agents.ai_cache import cached_chat


def _get_ai_client():
    from configurations.creds import creds
    from configurations.sap_ai_core_client import SAPAICoreClient
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
    )


def fill_rcm_template(ann: dict, sources: list) -> dict:
    """One AI call to fill the RCM template for a single announcement.

    Returns dict: {introduction: [...], business_background: [...]}
    related_legislation is assembled from sources by the caller (no AI needed).
    Falls back to wrapping announcement_md if AI is unavailable.
    """
    _tmpl_path = os.path.join(
        os.path.dirname(__file__), "..", "configurations", "rcm_template.json"
    )
    with open(_tmpl_path, encoding="utf-8") as f:
        tmpl = json.load(f)

    sources_text = "\n".join(
        f"- {s.get('title') or s.get('publisher') or 'Source'}: {s.get('url', '')} "
        f"(published {s.get('published_at', '')[:10] if s.get('published_at') else ''}, "
        f"by {s.get('publisher', '')})"
        for s in sources
    )

    prompt = tmpl["ai_prompt"].format(
        title=ann.get("title", ""),
        summary=ann.get("announcement_md", ""),
        sources_text=sources_text or "(no sources)",
    )

    def _call():
        return _get_ai_client().chat(prompt)

    try:
        raw = cached_chat(prompt, _call)
        raw = re.sub(r"^```json?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        result = json.loads(raw)
        # Ensure expected keys exist
        if "introduction" not in result:
            raise ValueError("AI response missing 'introduction' key")
        return result
    except Exception as e:
        print(f"  ⚠️  fill_rcm_template AI failed: {e} — using fallback")
        return {
            "introduction": [ann.get("announcement_md", "")],
            "business_background": [],
        }
