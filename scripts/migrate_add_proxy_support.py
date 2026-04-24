#!/usr/bin/env python3
"""
Migration: Add proxy support to url_sources table
Version: v2.5.0
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from configurations.db import get_connection

def migrate():
    print("=" * 70)
    print("Migration: Adding Proxy Support")
    print("=" * 70)
    
    conn = get_connection()
    
    # Add proxy_url column
    try:
        conn.execute("ALTER TABLE url_sources ADD COLUMN proxy_url TEXT")
        print("✅ Added proxy_url column")
    except Exception as e:
        if "duplicate column name" in str(e).lower():
            print("⚠️  proxy_url column already exists")
        else:
            print(f"❌ Error adding proxy_url: {e}")
    
    # Add proxy_enabled column
    try:
        conn.execute("ALTER TABLE url_sources ADD COLUMN proxy_enabled INTEGER DEFAULT 0")
        print("✅ Added proxy_enabled column")
    except Exception as e:
        if "duplicate column name" in str(e).lower():
            print("⚠️  proxy_enabled column already exists")
        else:
            print(f"❌ Error adding proxy_enabled: {e}")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 70)
    print("✅ Migration complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Configure proxy URL in environment variable:")
    print("   export LEGAL_EAGLE_PROXY_URL='http://user:pass@proxy:port'")
    print("2. Enable proxy for specific URLs in Admin UI")
    print("=" * 70)

if __name__ == "__main__":
    migrate()