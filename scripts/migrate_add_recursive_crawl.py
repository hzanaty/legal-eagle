#!/usr/bin/env python3
"""
Migration: Add recursive crawling support to url_sources table.

Adds columns:
- max_depth: INTEGER (default 2) - how many levels to drill down
- allowed_domains: TEXT - JSON array or newline-separated list of domains
- path_filter: TEXT - only follow links containing this path segment
- max_results: INTEGER (default 20) - stop after finding N articles
- date_scope: TEXT (default 'all') - 'all', 'last_month', 'last_3_months', etc.

Also updates mode CHECK constraint to include 'recursive'.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import get_connection


def migrate_recursive_crawl_support(db_path: str = None) -> None:
    """
    Add recursive crawling columns to url_sources table.
    """
    conn = get_connection(db_path)
    
    print("[Migration] Adding recursive crawl support columns...")
    
    with conn:
        # Add max_depth column
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN max_depth INTEGER DEFAULT 2")
            print("  ✓ Added max_depth column")
        except Exception as e:
            print(f"  ℹ max_depth column already exists or error: {e}")
        
        # Add allowed_domains column (stores JSON array or newline-separated)
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN allowed_domains TEXT")
            print("  ✓ Added allowed_domains column")
        except Exception as e:
            print(f"  ℹ allowed_domains column already exists or error: {e}")
        
        # Add path_filter column
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN path_filter TEXT")
            print("  ✓ Added path_filter column")
        except Exception as e:
            print(f"  ℹ path_filter column already exists or error: {e}")
        
        # Add max_results column
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN max_results INTEGER DEFAULT 20")
            print("  ✓ Added max_results column")
        except Exception as e:
            print(f"  ℹ max_results column already exists or error: {e}")
        
        # Add date_scope column
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN date_scope TEXT DEFAULT 'all'")
            print("  ✓ Added date_scope column")
        except Exception as e:
            print(f"  ℹ date_scope column already exists or error: {e}")
        
        # Update mode constraint to include 'recursive'
        # SQLite doesn't support ALTER CONSTRAINT, so we need to recreate the table
        print("\n[Migration] Updating mode constraint to include 'recursive'...")
        
        # Check if constraint needs updating
        schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='url_sources'"
        ).fetchone()
        
        if schema and 'recursive' not in schema['sql']:
            print("  Creating new table with updated constraint...")
            
            # Create new table with updated constraint
            conn.execute("""
                CREATE TABLE url_sources_new (
                    id INTEGER PRIMARY KEY,
                    profile_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('auto','force_static','force_dynamic','recursive')),
                    sample_link TEXT,
                    read_more_label TEXT,
                    crawl_version TEXT,
                    max_depth INTEGER DEFAULT 2,
                    allowed_domains TEXT,
                    path_filter TEXT,
                    max_results INTEGER DEFAULT 20,
                    date_scope TEXT DEFAULT 'all',
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(profile_id, url),
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                )
            """)
            
            # Copy data from old table
            conn.execute("""
                INSERT INTO url_sources_new 
                SELECT id, profile_id, url, mode, sample_link, read_more_label, 
                       crawl_version, max_depth, allowed_domains, path_filter, 
                       max_results, date_scope, created_at
                FROM url_sources
            """)
            
            # Drop old table and rename new one
            conn.execute("DROP TABLE url_sources")
            conn.execute("ALTER TABLE url_sources_new RENAME TO url_sources")
            
            print("  ✓ Updated mode constraint to include 'recursive'")
        else:
            print("  ℹ Mode constraint already includes 'recursive' or table structure unknown")
    
    conn.close()
    print("\n[Migration] Complete!")


if __name__ == "__main__":
    migrate_recursive_crawl_support()
