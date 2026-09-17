#!/usr/bin/env python3
"""
BTP Restore Script — Restore data from backup JSON back to BTP database.

Uses `cf` commands to upload database to BTP container.

Usage:
    python scripts/btp_restore.py --file btp_backup_20260917_221500.json

Workflow:
1. Before restart:  python btp_backup.py
2. Do restart:      cf restart legal-eagle-ui
3. After restart:   python btp_check.py --file btp_backup.json (check if lost)
4. If needed:       python btp_restore.py --file btp_backup.json
"""

import json
import argparse
import sys
import subprocess
from pathlib import Path
import sqlite3


def run_command(cmd, capture=True):
    """Run shell command."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture, text=True, timeout=120)
        if result.returncode != 0:
            print(f"❌ Command failed: {cmd}")
            if result.stderr:
                print(f"   {result.stderr}")
            return None
        return result.stdout.strip() if capture else True
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def import_json_to_db(json_file: str, db_path: str) -> bool:
    """Import JSON backup data into SQLite database."""
    try:
        with open(json_file) as f:
            data = json.load(f)
        
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = OFF")
        
        # Clear tables
        tables_to_clear = [
            "run_logs", "runs", "news_announcements", "filtered_news", "news_items",
            "rcm_reference_titles", "ranking_grounding", "ranking_signals",
            "law_refs", "glossary_patterns", "glossary_synonyms", "glossary_terms",
            "glossary_labels", "email_receivers", "url_sources", "tweet_accounts",
            "rss_feeds", "authorities", "settings", "profiles", "audit_log",
        ]
        for table in tables_to_clear:
            try:
                conn.execute(f"DELETE FROM {table}")
            except:
                pass
        conn.commit()
        
        # Import data
        total = 0
        for table, rows in data.items():
            if not rows or table.startswith("_"):
                continue
            try:
                cols = list(rows[0].keys())
                placeholders = ", ".join("?" for _ in cols)
                col_names = ", ".join(cols)
                for row in rows:
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
                        [row.get(c) for c in cols],
                    )
                    total += 1
                conn.commit()
            except Exception as e:
                print(f"⚠️  Error in {table}: {e}")
                conn.rollback()
        
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()
        
        return total
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0


def restore_btp(backup_file: str) -> bool:
    """Restore data from backup to BTP using cf commands."""
    
    backup_path = Path(backup_file)
    if not backup_path.exists():
        print(f"❌ Backup file not found: {backup_file}")
        return False
    
    print(f"📂 Backup file: {backup_path.absolute()}")
    print(f"⚠️  WARNING: This will clear all existing BTP data!")
    
    # Confirm
    confirm = input("\n⚠️  Type 'restore' to proceed (or anything else to cancel): ").strip()
    if confirm.lower() != "restore":
        print("❌ Cancelled")
        return False
    
    # Check cf CLI
    if not run_command("cf --version"):
        print("❌ cf CLI not found")
        return False
    
    # Create temp database for import
    print("\n🔄 Preparing restore...")
    temp_dir = Path("/tmp/legal_eagle_restore")
    temp_dir.mkdir(exist_ok=True)
    temp_db = temp_dir / "config.db"
    
    # Download current BTP database
    print("📥 Downloading current BTP database...")
    download_cmd = f"cf download legal-eagle-ui /home/vcap/app/configurations/config.db -o {temp_db}"
    if not run_command(download_cmd, capture=False):
        print("❌ Could not download database")
        return False
    
    # Import from backup JSON into temp database
    print("📊 Importing backup data...")
    rows_imported = import_json_to_db(str(backup_path), str(temp_db))
    if rows_imported == 0:
        print("❌ No data imported")
        return False
    
    print(f"✅ Imported {rows_imported} rows")
    
    # Upload modified database back to BTP
    print("📤 Uploading restored database to BTP...")
    upload_cmd = f"cf upload-file legal-eagle-ui {temp_db} /home/vcap/app/configurations/config.db"
    if not run_command(upload_cmd, capture=False):
        print("⚠️  Could not upload via cf upload-file")
        print("   BTP may not support this operation")
        print("   Alternative: Restart BTP manually and re-import")
        return False
    
    print(f"\n✅ Restore complete!")
    print(f"📊 Summary:")
    print(f"   • Rows imported: {rows_imported}")
    print(f"\n⚠️  IMPORTANT: Restart BTP app for changes to take effect:")
    print(f"   cf restart legal-eagle-ui")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Restore data from backup to BTP")
    parser.add_argument("--file", "-f", required=True, help="Backup JSON file")
    args = parser.parse_args()
    
    success = restore_btp(args.file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
