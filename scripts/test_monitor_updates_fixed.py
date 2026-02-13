#!/usr/bin/env python3
"""
Test script to verify monitor updates email matching with fixes:
1. Handles "FW:" prefix in subject
2. Checks ALL email receivers
3. Fresh database (no processed emails blocking)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.email_inbox_parser import fetch_monitor_updates
from configurations.db import get_connection, create_schema_if_needed
from configurations.env_loader import load_env

print("="*80)
print("Testing Monitor Updates Email Matching (Fixed)")
print("="*80)

# Load environment
env = load_env()
gmail_email = env.get("LEGAL_EAGLE_GMAIL_SENDER")
gmail_password = env.get("LEGAL_EAGLE_GMAIL_APP_PASSWORD")

if not gmail_email or not gmail_password:
    print("❌ Gmail credentials not found in environment")
    sys.exit(1)

print(f"\n📧 Gmail: {gmail_email}")

# Test with SA/HCM profile
profile_id = 1  # Assuming SA/HCM is profile 1
test_receivers = [
    "alanoud.alsaud@sap.com",
    "hany.zanaty@sap.com"
]

print(f"🔍 Testing with receivers: {', '.join(test_receivers)}")
print(f"   (Any of these can forward monitor emails)")

# Connect to database
conn = get_connection()
create_schema_if_needed(conn)

print("\n🔄 Fetching monitor updates...")
try:
    monitor_updates = fetch_monitor_updates(
        profile_id=profile_id,
        recipient_emails=test_receivers,  # Pass all receivers
        gmail_email=gmail_email,
        gmail_app_password=gmail_password,
        conn=conn
    )
    
    print(f"\n✅ Found {len(monitor_updates)} monitor update email(s)")
    
    if monitor_updates:
        for i, update in enumerate(monitor_updates, 1):
            print(f"\n--- Email {i} ---")
            print(f"Report Date: {update.get('report_date', 'N/A')}")
            print(f"Monitored URL: {update.get('monitored_url', 'N/A')}")
            print(f"Changes: {len(update.get('changes', []))}")
            for j, change in enumerate(update.get('changes', [])[:3], 1):
                print(f"  {j}. {change[:100]}...")
            if len(update.get('changes', [])) > 3:
                print(f"  ... and {len(update.get('changes', [])) - 3} more")
    else:
        print("\nℹ️ No new monitor updates found")
        print("\nPossible reasons:")
        print("1. No 'Monitor updates' emails in Gmail inbox")
        print("2. Emails already processed (check database)")
        print("3. Email 'From' field doesn't match any receiver")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    conn.close()

print("\n" + "="*80)
print("Test Complete")
print("="*80)
