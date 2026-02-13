#!/usr/bin/env python3
"""
Migration script to add monitor_updates_processed table.

This table tracks processed Law-to-Specification "Monitor updates" emails
to prevent duplicate processing.

Usage:
    python scripts/migrate_add_monitor_updates.py
"""

import sqlite3
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import get_connection

def migrate():
    """Add monitor_updates_processed table if it doesn't exist."""
    print("\n" + "="*80)
    print("Legal Eagle - Monitor Updates Migration")
    print("="*80 + "\n")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='monitor_updates_processed'
        """)
        
        if cursor.fetchone():
            print("✓ Table 'monitor_updates_processed' already exists. No migration needed.")
            conn.close()
            return
        
        print("Creating table: monitor_updates_processed...")
        
        # Create table
        cursor.execute("""
            CREATE TABLE monitor_updates_processed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                email_message_id TEXT UNIQUE NOT NULL,
                report_date TEXT,
                monitored_url TEXT,
                changes_json TEXT,
                processed_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            )
        """)
        
        # Create index for faster profile lookups
        cursor.execute("""
            CREATE INDEX idx_monitor_profile 
            ON monitor_updates_processed(profile_id)
        """)
        
        # Create index for message ID lookups
        cursor.execute("""
            CREATE INDEX idx_monitor_message_id 
            ON monitor_updates_processed(email_message_id)
        """)
        
        conn.commit()
        print("✓ Table 'monitor_updates_processed' created successfully")
        print("✓ Indexes created successfully")
        
        # Verify table structure
        cursor.execute("PRAGMA table_info(monitor_updates_processed)")
        columns = cursor.fetchall()
        
        print("\nTable structure:")
        print("-" * 80)
        for col in columns:
            col_id, name, col_type, not_null, default, pk = col
            print(f"  {name:20s} {col_type:10s} {'NOT NULL' if not_null else ''} {'PRIMARY KEY' if pk else ''}")
        print("-" * 80)
        
        conn.close()
        
        print("\n" + "="*80)
        print("✓ Migration completed successfully!")
        print("="*80 + "\n")
        
    except sqlite3.Error as e:
        print(f"\n✗ Migration failed: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)

if __name__ == "__main__":
    migrate()
