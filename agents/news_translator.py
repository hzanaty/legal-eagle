"""
News Translator — the TRANSLATE stage (v3.1, B8).

Translation was previously embedded inside `email_sender.py`. It is now its own
agent/stage so the pipeline has a single, testable responsibility per module and
translation can be invoked independently of email rendering.

Behaviour is preserved: `translate_grouped_summary` produces a translated copy of
the grouped summary using the SAP AI Core chat model. When the AI cache is active
(`LEGAL_EAGLE_AI_CACHE`), each per-group translation is recorded once and replayed
for deterministic, offline test runs. Same-language input is a no-op.
"""
import json
from typing import Any, Dict, List

from configurations.config_loader import creds
from agents.sap_ai_client import SAPAICoreClient
from agents.ai_cache import cached_chat

_LANG_NAMES = {
    "en": "English", "ar": "Arabic", "es": "Spanish", "de": "German",
    "fr": "French", "it": "Italian", "pt": "Portuguese", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "hi": "Hindi", "ru": "Russian",
}


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


def translate_grouped_summary(
    grouped_summary: List[Dict[str, Any]],
    from_lang: str,
    to_lang: str,
    openai_api_key: str = "",
) -> List[Dict[str, Any]]:
    """Translate each group's title/summary from `from_lang` to `to_lang`.

    Returns a translated copy; on any failure falls back to the original text.
    `openai_api_key` is retained for signature compatibility and unused (SAP AI Core).
    """
    if from_lang == to_lang:
        return grouped_summary

    from_lang_name = _LANG_NAMES.get(from_lang, from_lang)
    to_lang_name = _LANG_NAMES.get(to_lang, to_lang)
    print(f"🌐 Translating summary from {from_lang_name} to {to_lang_name}...")

    translated_summary: List[Dict[str, Any]] = []
    try:
        client = _get_ai_client()
        for group in grouped_summary:
            title = group.get("title", "")
            summary = group.get("summary", "")
            if isinstance(summary, dict):
                summary = summary.get("summary", "")

            prompt = f"""Translate the following legal news summary from {from_lang_name} to {to_lang_name}.
Maintain the professional tone and legal terminology accuracy.

Title: {title}

Summary: {summary}

Provide the translation in this exact JSON format:
{{
    "translated_title": "...",
    "translated_summary": "..."
}}"""

            def _call() -> str:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"You are a professional legal translator specializing in {from_lang_name} to {to_lang_name} translation."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
                return resp.choices[0].message.content.strip()

            translation_text = cached_chat(prompt, _call)

            try:
                if translation_text.startswith("```"):
                    translation_text = translation_text.split("```")[1]
                    if translation_text.startswith("json"):
                        translation_text = translation_text[4:]
                    translation_text = translation_text.strip()
                translation = json.loads(translation_text)
                translated_title = translation.get("translated_title", title)
                translated_summary_text = translation.get("translated_summary", summary)
            except json.JSONDecodeError:
                print(f"   ⚠️ Translation parse failed for: {title[:50]}...")
                translated_title = title
                translated_summary_text = summary

            translated_group = group.copy()
            translated_group["title"] = translated_title
            translated_group["summary"] = translated_summary_text
            translated_summary.append(translated_group)

        print(f"✅ Translated {len(translated_summary)} group(s)")
        return translated_summary
    except Exception as e:
        print(f"❌ Translation failed: {e}")
        print("   Falling back to original language")
        return grouped_summary
