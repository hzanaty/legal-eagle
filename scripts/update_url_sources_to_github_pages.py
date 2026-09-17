#!/usr/bin/env python3
"""
Update URL sources in config.db to use GitHub Pages URLs instead of local file:// paths.

Usage:
  python3 scripts/update_url_sources_to_github_pages.py
  
This script updates all file:// URLs pointing to xanadu-gov-site to use the GitHub Pages URL:
  https://pages.github.tools.sap/I077750/legal-eagle/xanadu.html
"""

import sys
import os
from configurations.db import get_connection, create_schema_if_needed

# GitHub Pages URL for Xanadu site
GITHUB_PAGES_URL = "https://pages.github.tools.sap/I077750/legal-eagle/xanadu.html"

def update_url_sources():
    """
    Update all file:// URLs to GitHub Pages URL.
    """
    db_path = os.environ.get("LEGAL_EAGLE_DB") or os.path.join(
        os.path.dirname(__file__), "..", "configurations", "config.db"
    )
    
    conn = get_connection(db_path)
    create_schema_if_needed(conn)
    
    # Find all URL sources with file:// paths
    cursor = conn.execute(
        "SELECT id, profile_id, url FROM url_sources WHERE url LIKE 'file://%xanadu%'"
    )
    rows = cursor.fetchall()
    
    if not rows:
        print("✅ No file:// URLs found to update")
        return 0
    
    count = 0
    for row in rows:
        source_id = row[0]
        profile_id = row[1]
        old_url = row[2]
        
        # Update to GitHub Pages URL
        conn.execute(
            "UPDATE url_sources SET url = ? WHERE id = ?",
            (GITHUB_PAGES_URL, source_id)
        )
        print(f"✅ Updated profile_id {profile_id}:")
        print(f"   FROM: {old_url}")
        print(f"   TO:   {GITHUB_PAGES_URL}")
        count += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n📊 Summary: Updated {count} URL source(s)")
    return count

if __name__ == "__main__":
    try:
        updated = update_url_sources()
        sys.exit(0 if updated >= 0 else 1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)