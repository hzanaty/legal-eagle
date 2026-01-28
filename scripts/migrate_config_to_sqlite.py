#!/usr/bin/env python3
"""
Seed SQLite configuration DB from existing configurations/agents_config.py.

- Creates schema if not exists
- Creates/gets a default profile (KSA/HCM) unless overridden by env
- Seeds:
  * rss_feeds (list of URLs)
  * tweet_accounts (list of handles)
  * crawl_urls (URLs only; advanced selectors remain in agents_config for now)
  * snap_urls (URLs only)
  * email_receivers (list of emails)
  * settings.language for the profile
  * glossary_terms by splitting configured text into comma-separated terms
    (category taken from GLOSSARY keys, e.g., HCM/FIN/OTHER)

Credentials are NOT migrated; they remain in configurations/credentials.json.

ENV overrides:
  PROFILE_COUNTRY=KSA PROFILE_LOB=HCM PROFILE_NAME="Default KSA/HCM" PROFILE_LANG=ar
"""

import os
import sys
from typing import List

# Local imports
# Run from repo root or from scripts/ directory; adjust sys.path so we can import configurations.*
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from configurations import db as cfgdb
    from configurations import agents_config as cfg
except Exception as e:
    print(f"Failed to import configuration modules: {e}")
    sys.exit(1)


def _split_terms(text: str) -> List[str]:
    """
    Heuristic splitting of glossary free-text into individual terms.
    We split by comma first, then strip whitespace. Empty entries discarded.
    """
    # Normalize whitespace and split on commas
    parts = []
    for raw in text.split(","):
        t = " ".join(raw.strip().split())
        if t:
            parts.append(t)
    return parts


def main() -> None:
    country = os.environ.get("PROFILE_COUNTRY", "KSA")
    lob = os.environ.get("PROFILE_LOB", "HCM")
    name = os.environ.get("PROFILE_NAME", f"Default {country}/{lob}")
    language = os.environ.get("PROFILE_LANG", getattr(cfg, "LANGUAGE_PREFERENCE", "en"))

    conn = cfgdb.get_connection()
    cfgdb.create_schema_if_needed(conn)

    profile_id = cfgdb.create_profile(conn, country_code=country, lob=lob, name=name, language=language, active=1)
    if profile_id <= 0:
        # Try to fetch if it already existed
        row = cfgdb.get_profile(conn, country, lob)
        if not row:
            print("❌ Failed to create or locate profile.")
            sys.exit(2)
        profile_id = int(row["id"])

    print(f"✅ Using profile id={profile_id} for {country}/{lob} ({name}), language={language}")

    # Seed RSS_FEED_URLS
    rss = getattr(cfg, "RSS_FEED_URLS", [])
    for url in rss:
        try:
            cfgdb.upsert_rss_feed(conn, profile_id, url)
        except Exception as e:
            print(f"⚠️ Failed to insert rss url '{url}': {e}")
    print(f"✅ Seeded {len(rss)} RSS feeds")

    # Seed TWEET_ACCOUNTS
    tweets = getattr(cfg, "TWEET_ACCOUNTS", [])
    for handle in tweets:
        try:
            cfgdb.upsert_tweet_account(conn, profile_id, handle)
        except Exception as e:
            print(f"⚠️ Failed to insert tweet handle '{handle}': {e}")
    print(f"✅ Seeded {len(tweets)} tweet accounts")

    # Seed CRAWL_URLS (URLs only; keep advanced dict in agents_config for now)
    crawl = getattr(cfg, "CRAWL_URLS", [])
    crawl_urls = []
    for entry in crawl:
        if isinstance(entry, dict):
            u = entry.get("url")
            if u:
                crawl_urls.append(u)
        elif isinstance(entry, str):
            crawl_urls.append(entry)
    for url in crawl_urls:
        try:
            cfgdb.upsert_crawl_url(conn, profile_id, url)
        except Exception as e:
            print(f"⚠️ Failed to insert crawl url '{url}': {e}")
    print(f"✅ Seeded {len(crawl_urls)} crawl urls")

    # Seed SNAP_URLS (URLs only)
    snap = getattr(cfg, "SNAP_URLS", [])
    snap_urls = []
    for entry in snap:
        if isinstance(entry, dict):
            u = entry.get("url")
            if u:
                snap_urls.append(u)
        elif isinstance(entry, str):
            snap_urls.append(entry)
    for url in snap_urls:
        try:
            cfgdb.upsert_snap_url(conn, profile_id, url)
        except Exception as e:
            print(f"⚠️ Failed to insert snap url '{url}': {e}")
    print(f"✅ Seeded {len(snap_urls)} snap urls")

    # Seed EMAIL_RECEIVERS
    receivers = getattr(cfg, "EMAIL_RECEIVERS", [])
    for email in receivers:
        try:
            cfgdb.upsert_email_receiver(conn, profile_id, email)
        except Exception as e:
            print(f"⚠️ Failed to insert email '{email}': {e}")
    print(f"✅ Seeded {len(receivers)} email receivers")

    # Seed language setting (redundant with profiles.language, but keep setting available)
    try:
        cfgdb.set_setting(conn, profile_id, "LANGUAGE_PREFERENCE", language)
        print("✅ Set LANGUAGE_PREFERENCE setting")
    except Exception as e:
        print(f"⚠️ Failed to set LANGUAGE_PREFERENCE: {e}")

    # Seed Glossary
    glossary = getattr(cfg, "GLOSSARY", {})
    term_count = 0
    for category, block in glossary.items():
        terms = _split_terms(block)
        for term in terms:
            try:
                term_id = cfgdb.add_glossary_term(
                    conn,
                    profile_id=profile_id,
                    term=term,
                    lang=language or "en",
                    category=category,
                    product=None,
                    weight=1.0,
                    notes=None,
                )
                if term_id > 0:
                    term_count += 1
            except Exception as e:
                print(f"⚠️ Failed to insert glossary term '{term}' ({category}): {e}")
    print(f"✅ Seeded {term_count} glossary terms (category-tagged)")

    print("🎉 Migration completed successfully.")


if __name__ == "__main__":
    main()
