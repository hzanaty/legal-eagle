#!/usr/bin/env python3
"""
Migration: Add last_successful_fetch column to url_sources table

This enables incremental fetching where we only fetch news since the last
successful run, with the date_scope acting as a safety cap (max lookback).

Usage:
    python scripts/migrate_add_last_successful_fetch.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from configurations.db import get_connection, create_schema_if_needed


def migrate():
    """Add last_successful_fetch column to url_sources table"""
    print("🔄 Starting migration: Add last_successful_fetch to url_sources")
    
    conn = get_connection()
    create_schema_if_needed(conn)
    
    try:
        # Check if column already exists
        cursor = conn.execute("PRAGMA table_info(url_sources)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'last_successful_fetch' in columns:
            print("✅ Column 'last_successful_fetch' already exists. Migration skipped.")
            conn.close()
            return
        
        # Add the column
        print("   Adding column 'last_successful_fetch' (TEXT, nullable)...")
        conn.execute("""
            ALTER TABLE url_sources 
            ADD COLUMN last_successful_fetch TEXT
        """)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        print("")
        print("📝 Next steps:")
        print("   1. Deploy updated code (date_filter.py, url_sources_runner.py, agents_controller.py)")
        print("   2. First run will use full date_scope (NULL timestamps)")
        print("   3. Subsequent runs will use incremental fetching")
        print("")
        print("ℹ️  Column details:")
        print("   - Name: last_successful_fetch")
        print("   - Type: TEXT (ISO 8601 datetime)")
        print("   - Default: NULL (triggers full scan)")
        print("   - Updated: After each successful URL source fetch")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()