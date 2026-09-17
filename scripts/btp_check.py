#!/usr/bin/env python3
"""
BTP Check Script — Compare BTP current vs backup, show if data was lost.
Shows comparison table. You decide whether to restore.

Usage:
    python scripts/btp_check.py --file btp_backup_20260917_221500.json
"""

import json
import argparse
import sys
import subprocess
from pathlib import Path
import sqlite3


def run_command(cmd, capture=True):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture, text=True, timeout=120)
        if result.returncode != 0:
            return None
        return result.stdout.strip() if capture else True
    except Exception:
        return None


def get_btp_db():
    temp_dir = Path("/tmp/legal_eagle_check")
    temp_dir.mkdir(exist_ok=True)
    temp_db = temp_dir / "config_btp.db"
    download_cmd = f"cf download legal-eagle-ui /home/vcap/app/configurations/config.db -o {temp_db}"
    if not run_command(download_cmd, capture=False):
        print("❌ Could not download database from BTP")
        return None
    return str(temp_db) if temp_db.exists() else None


def get_table_counts(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        tables = ["profiles", "settings", "authorities", "rss_feeds", "tweet_accounts",
                  "url_sources", "email_receivers", "glossary_labels", "glossary_terms",
                  "glossary_synonyms", "glossary_patterns", "law_refs", "ranking_signals",
                  "ranking_grounding", "rcm_reference_titles", "news_items", "filtered_news",
                  "news_announcements", "runs", "run_logs", "audit_log"]
        counts = {}
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
            except:
                counts[table] = 0
        conn.close()
        return counts
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def load_backup_counts(backup_file):
    try:
        with open(backup_file) as f:
            data = json.load(f)
        return {t: len(r) for t, r in data.items() if not t.startswith("_") and isinstance(r, list)}
    except Exception as e:
        print(f"❌ Error reading backup: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Compare BTP vs backup")
    parser.add_argument("--file", "-f", required=True, help="Backup JSON file")
    args = parser.parse_args()
    
    if not Path(args.file).exists():
        print(f"❌ File not found: {args.file}")
        sys.exit(1)
    
    print("🔄 Checking BTP vs Backup...")
    if not run_command("cf --version"):
        print("❌ cf CLI not found")
        sys.exit(1)
    
    print("📥 Downloading BTP database...")
    btp_db = get_btp_db()
    if not btp_db:
        sys.exit(1)
    
    print("📊 Analyzing...")
    backup = load_backup_counts(args.file)
    btp = get_table_counts(btp_db)
    
    if not backup or not btp:
        sys.exit(1)
    
    total_backup = sum(backup.values())
    total_btp = sum(btp.values())
    data_lost = total_btp < (total_backup * 0.5)
    
    print("\n" + "=" * 100)
    print(f"{'Table':<30} | {'Backup':<15} | {'BTP Now':<15} | {'Status':<15}")
    print("=" * 100)
    for table in sorted(backup.keys()):
        b = backup.get(table, 0)
        c = btp.get(table, 0)
        if b == c:
            status = "✅ OK"
        elif c == 0 and b > 0:
            status = "❌ LOST"
        elif c < b:
            status = "⚠️  PARTIAL"
        else:
            status = "📈 GROWN"
        print(f"{table:<30} | {b:>15} | {c:>15} | {status:<15}")
    print("=" * 100)
    
    print(f"\n📋 Summary:")
    print(f"   Backup rows: {total_backup}")
    print(f"   BTP rows:    {total_btp}")
    print(f"   Difference:  {total_backup - total_btp}")
    
    if data_lost:
        print(f"\n❌ DATA LOSS DETECTED")
        print(f"\n✅ Recommendation: Restore from backup")
        print(f"   python scripts/btp_restore.py --file {Path(args.file).name}")
    else:
        print(f"\n✅ No data loss detected")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
