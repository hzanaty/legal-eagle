#!/usr/bin/env python3
"""
BTP Backup Script — Export ALL data from BTP database to local JSON file.

Uses `cf` CLI to run a backup task on BTP container.

Usage:
    python scripts/btp_backup.py [--output btp_backup.json]

The script will:
1. Run a backup task on BTP via `cf run-task`
2. Download config.db from BTP container
3. Export to JSON and save locally with timestamp
4. Display summary of backed-up data

Workflow:
1. Before restart: python scripts/btp_backup.py
2. Do restart:     cf restart legal-eagle-ui
3. After restart:  python scripts/btp_check.py (shows comparison)
4. If needed:      python scripts/btp_restore.py --file btp_backup_<timestamp>.json
"""

import json
import argparse
import sys
import subprocess
from datetime import datetime
from pathlib import Path
import sqlite3
import os


def run_command(cmd, capture=True):
    """Run shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=capture,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            print(f"❌ Command failed: {cmd}")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return None
        return result.stdout.strip() if capture else True
    except subprocess.TimeoutExpired:
        print(f"❌ Command timeout: {cmd}")
        return None
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return None


def export_db_to_json(db_path: str) -> dict:
    """Export SQLite database to JSON."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        tables_to_export = [
            "profiles", "settings", "authorities",
            "rss_feeds", "tweet_accounts", "url_sources", "email_receivers",
            "glossary_labels", "glossary_terms", "glossary_synonyms", "glossary_patterns",
            "law_refs", "ranking_signals", "ranking_grounding", "rcm_reference_titles",
            "news_items", "filtered_news", "news_announcements",
            "runs", "run_logs", "audit_log",
        ]
        
        export_data = {}
        for table in tables_to_export:
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                export_data[table] = [dict(row) for row in rows]
            except Exception:
                export_data[table] = []
        
        conn.close()
        
        export_data["_metadata"] = {
            "export_timestamp": datetime.utcnow().isoformat(),
            "version": "v3.34",
        }
        
        return export_data
    except Exception as e:
        print(f"❌ Error exporting database: {e}")
        return None


def backup_btp(output_path: str = None) -> bool:
    """Backup BTP database using cf commands."""
    
    print("🔄 Preparing BTP backup via cf CLI...")
    
    # Check if cf CLI is available
    if not run_command("cf --version"):
        print("❌ Error: cf CLI not found. Install Cloud Foundry CLI first.")
        return False
    
    # Check if logged in
    target = run_command("cf target")
    if not target or "No target" in target:
        print("❌ Error: Not logged in to BTP. Run: cf login")
        return False
    
    print(f"✅ Logged in to BTP")
    
    # Create temporary directory for backup
    temp_dir = Path("/tmp/legal_eagle_backup")
    temp_dir.mkdir(exist_ok=True)
    temp_db = temp_dir / "config.db"
    
    # Download config.db from BTP
    print("📥 Downloading database from BTP...")
    download_cmd = f"cf download legal-eagle-ui /home/vcap/app/configurations/config.db -o {temp_db}"
    
    if not run_command(download_cmd, capture=False):
        print("❌ Error: Could not download database from BTP")
        print("   Make sure BTP app 'legal-eagle-ui' is running")
        return False
    
    if not temp_db.exists():
        print("❌ Error: Database file not found after download")
        return False
    
    print(f"✅ Database downloaded: {temp_db}")
    
    # Export to JSON
    print("📊 Exporting database to JSON...")
    data = export_db_to_json(str(temp_db))
    
    if not data:
        return False
    
    # Generate output filename if not provided
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"btp_backup_{timestamp}.json"
    
    # Ensure directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Save to file
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    # Calculate summary
    total_rows = 0
    table_count = 0
    for key, rows in data.items():
        if not key.startswith("_") and isinstance(rows, list):
            table_count += 1
            total_rows += len(rows)
    
    print(f"\n✅ Backup complete!")
    print(f"📁 File: {output_file.absolute()}")
    print(f"📊 Summary:")
    print(f"   • Tables: {table_count}")
    print(f"   • Total rows: {total_rows}")
    print(f"   • Size: {output_file.stat().st_size / 1024:.1f} KB")
    print(f"\n💡 Next steps:")
    print(f"   1. Do your restart/push: cf restart legal-eagle-ui")
    print(f"   2. Check if data was lost: python scripts/btp_check.py --file {output_file.name}")
    print(f"   3. If needed, restore: python scripts/btp_restore.py --file {output_file.name}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Backup ALL data from BTP Legal Eagle instance (uses cf CLI)"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output filename (default: btp_backup_<timestamp>.json)"
    )
    
    args = parser.parse_args()
    
    success = backup_btp(args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
