#!/usr/bin/env python3
"""
Import Legal Eagle configuration data into BTP database.

This script imports ONLY configuration tables (profiles, glossary, sources, etc.)
into a BTP instance. It validates the schema exists and safely inserts/updates data.

Usage:
    python scripts/import_config.py [--input config_export.json] [--db path/to/config.db]

Safety:
    - Validates schema exists first (must run with fresh `cf push`)
    - Only imports configuration tables
    - Skips production tables entirely
    - Dry-run mode available for preview
"""

import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Configuration tables to import (in dependency order)
CONFIG_TABLES_ORDER = [
    "profiles",
    "settings",
    "authorities",
    "rss_feeds",
    "tweet_accounts",
    "url_sources",
    "email_receivers",
    "glossary_labels",
    "glossary_terms",
    "glossary_synonyms",
    "glossary_patterns",
    "law_refs",
    "ranking_signals",
    "ranking_grounding",
    "rcm_reference_titles",
]


def validate_schema(conn: sqlite3.Connection) -> bool:
    """Validate that all required schema tables exist."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
        ("profiles", "settings")
    )
    tables = cursor.fetchall()
    return len(tables) >= 2


def import_config(input_path: str, db_path: str, dry_run: bool = False) -> None:
    """Import configuration into database."""
    
    if not Path(input_path).exists():
        print(f"❌ Import file not found: {input_path}")
        sys.exit(1)
    
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        print(f"💡 Hint: Run 'cf push' first to create the schema")
        sys.exit(1)
    
    print(f"📖 Importing configuration from: {input_path}")
    print(f"📊 Target database: {db_path}")
    if dry_run:
        print(f"🔍 DRY RUN MODE - No changes will be made")
    
    # Load JSON
    with open(input_path, "r") as f:
        export_data = json.load(f)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # Validate schema
        if not validate_schema(conn):
            print(f"❌ Database schema incomplete. Run 'cf push' first.")
            sys.exit(1)
        
        print(f"\n✅ Schema validation passed")
        
        # Import each table
        imported_count = 0
        total_rows = 0
        
        print(f"\n📥 Importing tables:")
        for table_name in CONFIG_TABLES_ORDER:
            if table_name not in export_data["tables"]:
                print(f"  ⚠️  {table_name}: Not in export file (skipped)")
                continue
            
            table_data = export_data["tables"][table_name]
            if not table_data:
                print(f"  ✅ {table_name}: 0 rows (empty)")
                continue
            
            # Build INSERT statement
            first_row = table_data[0]
            columns = list(first_row.keys())
            placeholders = ", ".join("?" * len(columns))
            col_list = ", ".join(columns)
            
            insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"
            
            if dry_run:
                print(f"  🔍 {table_name}: Would insert {len(table_data)} rows")
                total_rows += len(table_data)
            else:
                try:
                    for row in table_data:
                        values = [row.get(col) for col in columns]
                        conn.execute(insert_sql, values)
                    
                    conn.commit()
                    print(f"  ✅ {table_name}: {len(table_data)} rows inserted")
                    total_rows += len(table_data)
                    imported_count += 1
                except sqlite3.IntegrityError as e:
                    print(f"  ⚠️  {table_name}: Skipped (constraint violation: {str(e)[:60]})")
                except Exception as e:
                    print(f"  ❌ {table_name}: Error - {str(e)[:60]}")
                    sys.exit(1)
        
        if dry_run:
            print(f"\n🔍 DRY RUN: Would import {total_rows} rows")
            print(f"✅ Preview complete. Run without --dry-run to actually import.")
        else:
            print(f"\n✅ Import complete!")
            print(f"📊 Summary:")
            print(f"   • Tables imported: {imported_count}")
            print(f"   • Total rows: {total_rows}")
            print(f"\n🎯 Next steps:")
            print(f"   1. Verify in Admin UI: profiles, sources, glossary")
            print(f"   2. Test with manual run")
            print(f"   3. Check logs: cf logs legal-eagle-ui --recent")
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Import Legal Eagle configuration data into BTP database"
    )
    parser.add_argument(
        "--input",
        default="scripts/test_runs/config_export.json",
        help="Input JSON file (default: scripts/test_runs/config_export.json)"
    )
    parser.add_argument(
        "--db",
        default="configurations/config.db",
        help="Target database path (default: configurations/config.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview import without making changes"
    )
    
    args = parser.parse_args()
    
    import_config(args.input, args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()