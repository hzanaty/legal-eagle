#!/usr/bin/env python3
"""
Export Legal Eagle configuration data from local database.

This script exports ONLY configuration tables (profiles, glossary, sources, etc.)
for deployment to BTP. Production data (news_items, runs, etc.) is NOT exported.

Usage:
    python scripts/export_config.py [--output config_export.json] [--db path/to/config.db]

Output:
    JSON file with all configuration tables, safe for version control review.
"""

import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Configuration tables to export (exclude production data)
CONFIG_TABLES = [
    "profiles",
    "settings",
    "rss_feeds",
    "tweet_accounts",
    "url_sources",
    "email_receivers",
    "glossary_terms",
    "glossary_synonyms",
    "glossary_patterns",
    "glossary_labels",
    "authorities",
    "law_refs",
    "ranking_signals",
    "ranking_grounding",
    "rcm_reference_titles",
]

# Production tables (NOT exported)
PRODUCTION_TABLES = [
    "news_items",
    "filtered_news",
    "runs",
    "run_logs",
    "news_announcements",
    "audit_log",
]


def export_config(db_path: str, output_path: str) -> None:
    """Export configuration from database to JSON file."""
    
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)
    
    print(f"📊 Exporting configuration from: {db_path}")
    print(f"💾 Output file: {output_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "db_version": "v3.33",
            "tables": {},
            "metadata": {
                "total_profiles": 0,
                "total_feeds": 0,
                "total_glossary_terms": 0,
                "total_sources": 0,
                "total_authorities": 0,
            }
        }
        
        # Export each configuration table
        for table_name in CONFIG_TABLES:
            try:
                rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
                table_data = [dict(row) for row in rows]
                export_data["tables"][table_name] = table_data
                
                # Update metadata
                if table_name == "profiles":
                    export_data["metadata"]["total_profiles"] = len(table_data)
                elif table_name == "rss_feeds":
                    export_data["metadata"]["total_feeds"] = len(table_data)
                elif table_name == "glossary_terms":
                    export_data["metadata"]["total_glossary_terms"] = len(table_data)
                elif table_name == "url_sources":
                    export_data["metadata"]["total_sources"] = len(table_data)
                elif table_name == "authorities":
                    export_data["metadata"]["total_authorities"] = len(table_data)
                
                print(f"  ✅ {table_name}: {len(table_data)} rows")
            except sqlite3.OperationalError as e:
                print(f"  ⚠️  {table_name}: Table not found (new schema)")
        
        # Verify we're not exporting production data
        print("\n🔍 Verifying production tables are NOT included:")
        for table_name in PRODUCTION_TABLES:
            if table_name in export_data["tables"]:
                print(f"  ❌ ERROR: Production table '{table_name}' was included!")
                sys.exit(1)
            print(f"  ✅ {table_name}: Excluded (good)")
        
        # Write JSON
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print(f"\n✅ Export complete!")
        print(f"📊 Summary:")
        print(f"   • Profiles: {export_data['metadata']['total_profiles']}")
        print(f"   • RSS Feeds: {export_data['metadata']['total_feeds']}")
        print(f"   • Glossary Terms: {export_data['metadata']['total_glossary_terms']}")
        print(f"   • URL Sources: {export_data['metadata']['total_sources']}")
        print(f"   • Authorities: {export_data['metadata']['total_authorities']}")
        print(f"\n💾 Ready to import to BTP: {output_path}")
        
    finally:
        conn.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Export Legal Eagle configuration data for BTP deployment"
    )
    parser.add_argument(
        "--output",
        default="scripts/test_runs/config_export.json",
        help="Output JSON file (default: scripts/test_runs/config_export.json)"
    )
    parser.add_argument(
        "--db",
        default="configurations/config.db",
        help="Input database path (default: configurations/config.db)"
    )
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    
    export_config(args.db, args.output)


if __name__ == "__main__":
    main()