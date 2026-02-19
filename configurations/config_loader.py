import os
from typing import List, Dict, Any, Optional

# -----------------------------
# Country-to-Language Mapping
# -----------------------------

COUNTRY_LANG_MAP = {
    # Middle East
    "SA": "ar", "AE": "ar", "EG": "ar", "JO": "ar", "KW": "ar", "QA": "ar", "BH": "ar", "OM": "ar",
    # Europe - Spanish
    "ES": "es", "MX": "es", "AR": "es", "CO": "es", "CL": "es", "PE": "es", "VE": "es",
    # Europe - German
    "DE": "de", "AT": "de", "CH": "de",
    # Europe - French
    "FR": "fr", "BE": "fr", "LU": "fr",
    # Europe - Italian
    "IT": "it",
    # Europe - Portuguese
    "PT": "pt", "BR": "pt",
    # Asia
    "CN": "zh", "JP": "ja", "KR": "ko", "IN": "hi", "TH": "th", "VN": "vi",
    # English-speaking
    "US": "en", "UK": "en", "GB": "en", "AU": "en", "CA": "en", "NZ": "en", "IE": "en",
    # Others
    "RU": "ru", "TR": "tr", "PL": "pl", "NL": "nl", "SE": "sv", "NO": "no", "DK": "da", "FI": "fi",
}

LANGUAGE_NAMES = {
    "en": "English",
    "ar": "Arabic",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "hi": "Hindi",
    "th": "Thai",
    "vi": "Vietnamese",
    "ru": "Russian",
    "tr": "Turkish",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
}

def get_language_for_country(country_code: str) -> str:
    """
    Get the default language for a country code.
    Returns 'en' if country not found in mapping.
    """
    return COUNTRY_LANG_MAP.get(country_code.upper(), "en")


def get_language_display_name(lang_code: str) -> str:
    """
    Get the display name for a language code.
    Returns the code itself if not found in mapping.
    """
    return LANGUAGE_NAMES.get(lang_code.lower(), lang_code)


# Environment-based credentials loader (.env locally, CI secrets in GitHub Actions)
from .env_loader import load_env_credentials

# Global variable so agents can just `from config_loader import creds`
# Use strict env loading; if missing, fall back to a best-effort dict to allow Admin UI to start.
try:
    creds = load_env_credentials()
except RuntimeError:
    env = os.environ
    creds = {
        "openai_api_key": env.get("LEGAL_EAGLE_OPENAI_API_KEY"),
        "gmail": {
            "email_sender": env.get("LEGAL_EAGLE_GMAIL_EMAIL_SENDER"),
            "app_password": env.get("LEGAL_EAGLE_GMAIL_APP_PASSWORD"),
            "client_id": env.get("LEGAL_EAGLE_GMAIL_CLIENT_ID"),
            "client_secret": env.get("LEGAL_EAGLE_GMAIL_CLIENT_SECRET"),
            "refresh_token": env.get("LEGAL_EAGLE_GMAIL_REFRESH_TOKEN"),
            "scope": env.get("LEGAL_EAGLE_GMAIL_SCOPE"),
            "token_uri": env.get("LEGAL_EAGLE_GMAIL_TOKEN_URI"),
        },
        "twitter": {
            "x_bearer_token": env.get("LEGAL_EAGLE_TWITTER_BEARER_TOKEN")
        }
    }


# -----------------------------
# DB-backed configuration loader
# -----------------------------
from .db import (
    get_connection,
    create_schema_if_needed,
    list_profiles,
    get_profile,
    list_rss_feeds,
    list_tweet_accounts,
    list_crawl_urls,
    list_snap_urls,
    list_email_receivers,
    get_language,
    get_setting,
    set_setting,
    list_glossary_terms,
    flatten_glossary_for_prompt,
    upsert_news_item,
    update_last_seen,
    list_baseline_items,
    get_reviewed_news_baseline as db_get_reviewed_news_baseline,
    # New unified sources/audit (no credentials in DB)
    list_url_sources,
    upsert_url_source,
    add_audit_log,
)

DB_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), "config.db")


def _get_conn() -> Any:
    """
    Get a connection and ensure schema exists.
    """
    conn = get_connection(DB_PATH_DEFAULT)
    create_schema_if_needed(conn)
    return conn


# -----------------------------
# Profile resolution and listing
# -----------------------------

def resolve_profile(country_code: str, lob: str) -> Optional[int]:
    """
    Return profile_id for (country_code, lob), or None if not found.
    """
    conn = _get_conn()
    row = get_profile(conn, country_code, lob)
    return int(row["id"]) if row else None


def list_active_profiles() -> List[Dict[str, Any]]:
    """
    List active profiles as dicts (country_code, lob, name, language, id).
    """
    conn = _get_conn()
    rows = list_profiles(conn, active_only=True)
    return [
        {
            "id": int(r["id"]),
            "country_code": r["country_code"],
            "lob": r["lob"],
            "name": r["name"],
            "language": r["language"],
            "active": int(r["active"] or 0),
        }
        for r in rows
    ]


# -----------------------------
# Per-profile configuration APIs
# -----------------------------

def load_language(profile_id: int) -> str:
    """
    Get configured language for the profile.
    """
    conn = _get_conn()
    return get_language(conn, profile_id)


def load_rss_feeds(profile_id: int) -> List[str]:
    """
    List RSS feed URLs for the profile.
    """
    conn = _get_conn()
    return list_rss_feeds(conn, profile_id)


def load_tweet_accounts(profile_id: int) -> List[str]:
    """
    List tweet account handles for the profile.
    """
    conn = _get_conn()
    return list_tweet_accounts(conn, profile_id)


def load_crawl_urls(profile_id: int) -> List[str]:
    """
    List crawl URL targets for the profile (simple URLs; advanced selectors remain in code).
    """
    conn = _get_conn()
    return list_crawl_urls(conn, profile_id)


def load_snap_urls(profile_id: int) -> List[str]:
    """
    List snap URL targets for the profile.
    """
    conn = _get_conn()
    return list_snap_urls(conn, profile_id)


def load_email_receivers(profile_id: int) -> List[str]:
    """
    List email receivers for the profile (backward compatibility).
    """
    conn = _get_conn()
    return list_email_receivers(conn, profile_id)


def load_email_receivers_with_lang(profile_id: int) -> List[Dict[str, Any]]:
    """
    List email receivers with their translation language preference.
    Returns: [{"email": "x@y.com", "translation_lang": "en"}, ...]
    """
    from .db import list_email_receivers_with_lang as db_list_email_receivers_with_lang
    conn = _get_conn()
    return db_list_email_receivers_with_lang(conn, profile_id)


def load_glossary(profile_id: int) -> Dict[str, Any]:
    """
    Load normalized glossary terms and flatten into prompt-ready structure.
    """
    conn = _get_conn()
    rows = list_glossary_terms(conn, profile_id)
    return flatten_glossary_for_prompt(rows)


# -----------------------------
# Settings helpers (per profile)
# -----------------------------

def get_setting_value(profile_id: int, key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Convenience wrapper to read a setting value for a profile.
    """
    conn = _get_conn()
    return get_setting(conn, profile_id, key, default)


def set_setting_value(profile_id: int, key: str, value: str) -> None:
    """
    Convenience wrapper to write a setting value for a profile.
    """
    conn = _get_conn()
    set_setting(conn, profile_id, key, value)


# -----------------------------
# News baseline wrappers
# -----------------------------

def add_news_item(profile_id: int, item: Dict[str, Any]) -> int:
    """
    Upsert a news item into the weekly baseline storage.
    Expected item keys:
      - source_type: 'rss' | 'tweet' | 'crawl' | 'snap'
      - source_id: optional stable id (rss guid, tweet id)
      - url, domain, title, content, published_at, hash_signature
    Returns: news_id (int) or -1 on failure
    """
    conn = _get_conn()
    return upsert_news_item(conn, profile_id, item)


def touch_news_item(news_id: int) -> None:
    """
    Update last_seen_at on an existing news item.
    """
    conn = _get_conn()
    update_last_seen(conn, news_id)


def get_weekly_baseline(profile_id: int, days: int = 7) -> List[Dict[str, Any]]:
    """
    Retrieve baseline items for the last 'days' days for a profile.
    """
    conn = _get_conn()
    return list_baseline_items(conn, profile_id, days)


def get_reviewed_baseline(profile_id: int, min_score: int = 4) -> List[Dict[str, Any]]:
    """
    Retrieve high-quality reviewed news items to use as a comparison baseline.
    These are items from the filtered_news table that have been manually reviewed
    and assigned a high relevance score (default: 4 or 5).
    
    Args:
        profile_id: The profile to fetch reviewed items for.
        min_score: Minimum relevance score (1-5). Default is 4.
        
    Returns:
        List of reviewed items, formatted for use in the compare_news baseline.
    """
    conn = _get_conn()
    return db_get_reviewed_news_baseline(conn, profile_id, min_score)


# -----------------------------
# Unified URL sources + Global credentials
# -----------------------------

def load_url_sources(profile_id: int) -> List[Dict[str, Any]]:
    """
    Load unified URL sources for a profile.
    Returns list of dicts: {"url", "mode", "sample_link", "created_at"}.
    """
    conn = _get_conn()
    return list_url_sources(conn, profile_id)


def load_global_credentials() -> Dict[str, Any]:
    """
    Load global credentials strictly from environment (.env/process).
    No SQLite usage.
    """
    gmail_cfg = (creds.get("gmail") or {}) if isinstance(creds, dict) else {}
    tw_cfg = (creds.get("twitter") or {}) if isinstance(creds, dict) else {}

    result: Dict[str, Any] = {
        "twitter_api_key": None,
        "twitter_api_secret": None,
        "twitter_bearer_token": tw_cfg.get("x_bearer_token"),
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": gmail_cfg.get("email_sender"),
        "smtp_password": gmail_cfg.get("app_password"),
        "smtp_use_tls": 1,
        "global_sender_email": gmail_cfg.get("email_sender"),
        "openai_api_key": creds.get("openai_api_key") if isinstance(creds, dict) else None,
        "gmail_client_id": gmail_cfg.get("client_id"),
        "gmail_client_secret": gmail_cfg.get("client_secret"),
        "gmail_refresh_token": gmail_cfg.get("refresh_token"),
        "gmail_scope": gmail_cfg.get("scope"),
        "gmail_token_uri": gmail_cfg.get("token_uri"),
        "gmail_app_password": gmail_cfg.get("app_password"),
        "gmail_email_sender": gmail_cfg.get("email_sender"),
    }
    return result


def migrate_urls_to_unified(profile_id: Optional[int] = None) -> int:
    """
    One-time helper to migrate existing crawl_urls/snap_urls into url_sources (mode='auto').
    If profile_id is provided, migrate only that profile; otherwise migrate all active profiles.
    Returns count of upserts performed.
    """
    conn = _get_conn()
    total = 0

    target_profiles: List[int] = []
    if profile_id is not None:
        target_profiles = [profile_id]
    else:
        # all active profiles
        rows = list_profiles(conn, active_only=False)
        target_profiles = [int(r["id"]) for r in rows]

    for pid in target_profiles:
        crawl = list_crawl_urls(conn, pid)
        snap = list_snap_urls(conn, pid)
        seen = set()  # avoid duplicates between old lists
        for url in crawl + snap:
            if url in seen:
                continue
            seen.add(url)
            upsert_url_source(conn, pid, url=url, mode="auto", sample_link=None)
            total += 1
        if seen:
            add_audit_log(conn, entity="url_sources", action="migrate_auto", details=f"migrated={len(seen)}", profile_id=pid)

    return total
