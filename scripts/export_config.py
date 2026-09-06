#!/usr/bin/env python3
"""
Export local DB config tables to scripts/btp_seed_data.json.
Run this locally whenever you make config changes, before cf push.

Tables exported (no secrets, no runtime data):
  profiles, url_sources, rss_feeds, tweet_accounts, email_receivers,
  glossary_terms, glossary_synonyms, glossary_patterns

NOT exported (environment-specific or runtime):
  settings (ANS keys — BTP-only), runs, run_logs, news_items,
  filtered_news, audit_log
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from configurations.db import get_connection, create_schema_if_needed

DB_PATH = os.environ.get(
    "LEGAL_EAGLE_DB",
    os.path.join(os.path.dirname(__file__), "..", "configurations", "config.db"),
)

TABLES = [
    "profiles",
    "url_sources",
    "rss_feeds",
    "tweet_accounts",
    "email_receivers",
    "glossary_terms",
    "glossary_synonyms",
    "glossary_patterns",
]

OUTPUT = os.path.join(os.path.dirname(__file__), "btp_seed_data.json")


def main():
    conn = get_connection(DB_PATH)
    create_schema_if_needed(conn)

    data = {}
    total = 0
    for table in TABLES:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        data[table] = [dict(r) for r in rows]
        print(f"  {table}: {len(rows)} rows")
        total += len(rows)

    conn.close()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nExported {total} rows across {len(TABLES)} tables → {OUTPUT}")
    print("Now: git commit + push, then cf push, then run import_config.py on BTP.")


if __name__ == "__main__":
    main()
