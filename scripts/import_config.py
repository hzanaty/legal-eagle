#!/usr/bin/env python3
"""
Import config from scripts/btp_seed_data.json into the BTP DB.
Run via: cf run-task legal-eagle-ui --command "python3 scripts/import_config.py" -m 128M

Full replace — wipes all 10 config tables then reimports from JSON.
Never touches: settings (ANS keys), runs, run_logs, news_items,
               filtered_news, audit_log.
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
    # Order matters — children before parents would break FK constraints,
    # so delete in reverse order, insert in forward order.
    "profiles",
    "url_sources",
    "rss_feeds",
    "tweet_accounts",
    "email_receivers",
    "glossary_terms",
    "glossary_synonyms",
    "glossary_patterns",
    "repo_nodes",
    "repo_assets",
]

SEED_FILE = os.path.join(os.path.dirname(__file__), "btp_seed_data.json")


def main():
    if not os.path.exists(SEED_FILE):
        print(f"ERROR: {SEED_FILE} not found. Run export_config.py locally first, then cf push.")
        sys.exit(1)

    with open(SEED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_connection(DB_PATH)
    create_schema_if_needed(conn)

    # Disable FK checks during wipe/reload to avoid cascade issues
    conn.execute("PRAGMA foreign_keys = OFF")

    # Wipe in reverse order (assets before nodes, synonyms before terms, etc.)
    for table in reversed(TABLES):
        conn.execute(f"DELETE FROM {table}")
        print(f"  cleared {table}")
    conn.commit()

    # Re-enable FK checks
    conn.execute("PRAGMA foreign_keys = ON")

    # Insert in forward order
    total = 0
    for table in TABLES:
        rows = data.get(table, [])
        if not rows:
            print(f"  {table}: 0 rows (skipped)")
            continue
        cols = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        for row in rows:
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
        conn.commit()
        print(f"  {table}: {len(rows)} rows imported")
        total += len(rows)

    conn.close()
    print(f"\nDone. {total} rows imported across {len(TABLES)} tables.")


if __name__ == "__main__":
    main()
