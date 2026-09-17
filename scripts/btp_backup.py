#!/usr/bin/env python3
"""
BTP Backup Script — Export ALL data from BTP database to local JSON file.

This script exports both config and production data from a running BTP instance
so you can restore it after a restart/restage/push.

Usage:
    python scripts/btp_backup.py \
      --url https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com \
      --secret <admin_secret> \
      [--output btp_backup.json]

The script will:
1. Call /api/export-all on the BTP instance
2. Save the JSON to a local file with timestamp
3. Display summary of backed-up data

Before restart: python scripts/btp_backup.py
After restart:  python scripts/btp_restore.py --file btp_backup_<timestamp>.json
"""

import json
import argparse
import sys
from datetime import datetime
from pathlib import Path
import requests
import os


def backup_btp(url: str, secret: str, output_path: str = None) -> bool:
    """Export ALL data from BTP instance."""
    
    if not url.startswith("http"):
        url = f"https://{url}"
    
    # Normalize URL
    url = url.rstrip("/")
    export_url = f"{url}/api/export-all"
    
    print(f"🔄 Connecting to: {url}")
    print(f"📊 Exporting all data...")
    
    try:
        # Call export endpoint with Bearer token
        headers = {
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json"
        }
        
        response = requests.get(export_url, headers=headers, timeout=60)
        
        if response.status_code == 403:
            print("❌ Error: Unauthorized (invalid admin secret)")
            return False
        elif response.status_code != 200:
            print(f"❌ Error: HTTP {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
        
        data = response.json()
        
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
        print(f"\n💡 To restore after restart:")
        print(f"   python scripts/btp_restore.py --file {output_file.name}")
        
        return True
        
    except requests.ConnectionError:
        print(f"❌ Error: Cannot connect to {url}")
        print("   Verify the URL is correct and BTP app is running")
        return False
    except requests.Timeout:
        print("❌ Error: Request timeout (BTP may be restarting)")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Backup ALL data from BTP Legal Eagle instance"
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
    parser.add_argument(
        "--output",
        "-o",
        help="Output filename (default: btp_backup_<timestamp>.json)"
    )
    
    args = parser.parse_args()
    
    # Get secret from arg or environment
    secret = args.secret or os.environ.get("LEGAL_EAGLE_ADMIN_SECRET")
    
    if not secret:
        print("❌ Error: Admin secret not provided")
        print("   Use --secret flag or set LEGAL_EAGLE_ADMIN_SECRET environment variable")
        sys.exit(1)
    
    success = backup_btp(args.url, secret, args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
