#!/usr/bin/env python3
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "configurations", "config.db")

def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for r in rows:
        # row format: cid, name, type, notnull, dflt_value, pk
        if (r[1] == column) or (isinstance(r, sqlite3.Row) and r["name"] == column):
            return True
    return False

def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        added = False
        with conn:
            if not column_exists(conn, "url_sources", "crawl_version"):
                conn.execute("ALTER TABLE url_sources ADD COLUMN crawl_version TEXT")
                added = True
            # Default existing rows to 'v1' when NULL or empty
            conn.execute("UPDATE url_sources SET crawl_version = 'v1' WHERE crawl_version IS NULL OR crawl_version = ''")
        print(f"OK: crawl_version column {'added' if added else 'already exists'}; defaulted existing rows to 'v1'.")
    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
