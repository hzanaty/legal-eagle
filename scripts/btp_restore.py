#!/usr/bin/env python3
"""
BTP Restore Script — Import ALL data back to BTP database from backup JSON.

This script imports a previously exported backup to restore BTP data after
a restart/restage/push that lost the database.

Usage:
    python scripts/btp_restore.py \
      --file btp_backup_20260917_221500.json \
      --url https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com \
      --secret <admin_secret>

Workflow:
1. Before restart:  python btp_backup.py → creates backup
2. Do restart:      cf restart legal-eagle-ui
3. After restart:   python btp_restore.py --file btp_backup_*.json

The script will:
1. Read the backup JSON file
2. Call /api/import-all on the BTP instance
3. Display summary of restored data
"""

import json
import argparse
import sys
from pathlib import Path
import requests
import os


def restore_btp(backup_file: str, url: str, secret: str) -> bool:
    """Import ALL data to BTP instance."""
    
    # Load backup file
    backup_path = Path(backup_file)
    if not backup_path.exists():
        print(f"❌ Error: Backup file not found: {backup_file}")
        return False
    
    print(f"📂 Loading backup: {backup_path.absolute()}")
    
    try:
        with open(backup_path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in backup file: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading backup file: {e}")
        return False
    
    # Normalize URL
    if not url.startswith("http"):
        url = f"https://{url}"
    url = url.rstrip("/")
    import_url = f"{url}/api/import-all"
    
    print(f"🔄 Connecting to: {url}")
    print(f"⚠️  WARNING: This will clear all existing data on BTP!")
    print(f"📥 Restoring {len([t for t in data if not t.startswith('_')])} tables...")
    
    # Confirm
    confirm = input("\n⚠️  Type 'restore' to proceed (or anything else to cancel): ").strip()
    if confirm.lower() != "restore":
        print("❌ Cancelled")
        return False
    
    try:
        # Call import endpoint with Bearer token
        headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            import_url,
            json=data,
            headers=headers,
            timeout=120
        )
        
        if response.status_code == 403:
            print("❌ Error: Unauthorized (invalid admin secret)")
            return False
        elif response.status_code != 200:
            print(f"❌ Error: HTTP {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
        
        result = response.json()
        
        print(f"\n✅ Restore complete!")
        print(f"📊 Summary:")
        print(f"   • Rows imported: {result.get('rows_imported', 0)}")
        print(f"   • Status: {result.get('status', 'unknown')}")
        
        metadata = data.get("_metadata", {})
        if metadata:
            print(f"\n📋 Backup info:")
            print(f"   • Exported: {metadata.get('export_timestamp', 'unknown')}")
            print(f"   • Version: {metadata.get('version', 'unknown')}")
        
        return True
        
    except requests.ConnectionError:
        print(f"❌ Error: Cannot connect to {url}")
        print("   Verify the URL is correct and BTP app is running")
        return False
    except requests.Timeout:
        print("❌ Error: Request timeout (restore may still be in progress)")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Restore ALL data to BTP Legal Eagle instance from backup"
    )
    parser.add_argument(
        "--file",
        "-f",
        required=True,
        help="Backup JSON file to restore"
    )
    parser.add_argument(
        "--url",
        default="https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com",
        help="BTP app URL (default: %(default)s)"
    )
    parser.add_argument(
        "--secret",
        required=False,
        help="Admin secret (or set LEGAL_EAGLE_ADMIN_SECRET env var)"
    )
    
    args = parser.parse_args()
    
    # Get secret from arg or environment
    secret = args.secret or os.environ.get("LEGAL_EAGLE_ADMIN_SECRET")
    
    if not secret:
        print("❌ Error: Admin secret not provided")
        print("   Use --secret flag or set LEGAL_EAGLE_ADMIN_SECRET environment variable")
        sys.exit(1)
    
    success = restore_btp(args.file, args.url, secret)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
