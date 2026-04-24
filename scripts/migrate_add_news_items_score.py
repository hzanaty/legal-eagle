#!/usr/bin/env python3
"""
Migration: Add relevance_score and reviewed_at columns to news_items table.
This allows scoring of accepted news items (not just filtered ones).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations import db

def migrate():
    """
    Add relevance_score and reviewed_at columns to news_items table.
    """
    print("=" * 80)
    print("Migration: Add relevance_score to news_items")
    print("=" * 80)
    
    conn = db.get_connection()
    db.create_schema_if_needed(conn)
    
    # Add relevance_score column (1-5 scale, NULL until reviewed)
    print("\n[1] Adding relevance_score column...")
    try:
        conn.execute("ALTER TABLE news_items ADD COLUMN relevance_score INTEGER")
        print("✅ Added relevance_score column")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print("⚠️ Column already exists (skipped)")
        else:
            print(f"❌ Error: {e}")
    
    # Add reviewed_at column (ISO timestamp when scored)
    print("\n[2] Adding reviewed_at column...")
    try:
        conn.execute("ALTER TABLE news_items ADD COLUMN reviewed_at TEXT")
        print("✅ Added reviewed_at column")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print("⚠️ Column already exists (skipped)")
        else:
            print(f"❌ Error: {e}")
    
    # Create index for efficient filtering by score
    print("\n[3] Creating index...")
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_items_reviewed ON news_items(profile_id, relevance_score)"
        )
        print("✅ Created index on (profile_id, relevance_score)")
    except Exception as e:
        print(f"❌ Error creating index: {e}")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ Migration Complete!")
    print("=" * 80)
    print("\nNews items can now be scored just like filtered news.")
    print("This enables review of ALL news (accepted + filtered).")
    print("\n" + "=" * 80)

if __name__ == "__main__":
    migrate()