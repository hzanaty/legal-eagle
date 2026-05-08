#!/usr/bin/env python3
"""
Migration: add url_date_template column to url_sources table.

Usage:
    python scripts/migrate_add_url_date_template.py

Safe to run multiple times (idempotent).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configurations.db import get_connection

def main():
    conn = get_connection()
    try:
        conn.execute("ALTER TABLE url_sources ADD COLUMN url_date_template TEXT")
        conn.commit()
        print("✓ Added url_date_template column to url_sources.")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print("✓ url_date_template column already exists — nothing to do.")
        else:
            print(f"ERROR: {e}")
            sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
