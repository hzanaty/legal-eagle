#!/usr/bin/env python3
"""
Add SGK monitoring sources to Turkey HCM profile.

This script adds:
1. Twitter account: sgksosyalmedya (via Twitter API)
2. SMMM Bilgi Formu: URL source for SGK circulars
3. SGK Duyuru: URL source for official announcements
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations import db

def add_sgk_sources():
    """
    Add all 3 SGK monitoring sources to Turkey HCM profile.
    """
    print("=" * 80)
    print("Adding SGK Monitoring Sources to Turkey HCM Profile")
    print("=" * 80)
    
    conn = db.get_connection()
    
    # Get Turkey HCM profile
    print("\n[1] Finding Turkey HCM profile...")
    profile = db.get_profile(conn, "TR", "HCM")
    
    if not profile:
        print("❌ ERROR: Turkey HCM profile not found!")
        print("   Please create the profile first.")
        conn.close()
        return
    
    profile_id = profile["id"]
    print(f"✅ Found profile: TR/HCM (ID: {profile_id})")
    
    # Add Twitter account
    print("\n[2] Adding Twitter account: @sgksosyalmedya...")
    try:
        db.upsert_tweet_account(conn, profile_id, "sgksosyalmedya")
        print("✅ Twitter account added successfully")
        print("   Uses your existing Twitter API credentials")
    except Exception as e:
        print(f"❌ ERROR adding Twitter account: {e}")
    
    # Add SMMM Bilgi Formu URL source
    print("\n[3] Adding SMMM Bilgi Formu (circulars source)...")
    try:
        db.upsert_url_source(
            conn=conn,
            profile_id=profile_id,
            url="https://www.muhasebeyazilari.com/guncelmevzuat/",
            mode="force_static",
            sample_link="https://www.muhasebeyazilari.com/guncelmevzuat/mevzuat_oku.php?mevzuat_id=7188",
            read_more_label=None,
            crawl_version="v1",
            max_depth=2,
            allowed_domains=None,
            path_filter=None,
            max_results=20,
            date_scope="all"
        )
        print("✅ SMMM Bilgi Formu added successfully")
        print("   URL: https://www.muhasebeyazilari.com/guncelmevzuat/")
        print("   Mode: force_static (no JavaScript needed)")
        print("   Sample: Circular 2026/9 article")
    except Exception as e:
        print(f"❌ ERROR adding SMMM Bilgi Formu: {e}")
    
    # Add SGK Duyuru URL source
    print("\n[4] Adding SGK Duyuru (official announcements)...")
    try:
        db.upsert_url_source(
            conn=conn,
            profile_id=profile_id,
            url="https://sgk.gov.tr/duyuru",
            mode="force_dynamic",
            sample_link="https://sgk.gov.tr/duyuru/detay/Bedeli-Odenecek-Ilaclar-Listesinde-Yapilan-Duzenlemeler-Hakkinda-Duyuru-202615-2026-04-08-04-47-45",
            read_more_label=None,
            crawl_version="v1",
            max_depth=2,
            allowed_domains=None,
            path_filter=None,
            max_results=20,
            date_scope="all"
        )
        print("✅ SGK Duyuru added successfully")
        print("   URL: https://sgk.gov.tr/duyuru")
        print("   Mode: force_dynamic (may require JavaScript)")
        print("   Sample: Medicine list announcement")
    except Exception as e:
        print(f"❌ ERROR adding SGK Duyuru: {e}")
    
    # Verify configuration
    print("\n[5] Verifying configuration...")
    print("\n" + "-" * 80)
    
    # List all sources
    tweet_accounts = db.list_tweet_accounts(conn, profile_id)
    url_sources = db.list_url_sources(conn, profile_id)
    
    print(f"\n✅ Twitter Accounts ({len(tweet_accounts)}):")
    for account in tweet_accounts:
        print(f"   • @{account}")
    
    print(f"\n✅ URL Sources ({len(url_sources)}):")
    for source in url_sources:
        print(f"   • {source['url']}")
        print(f"     Mode: {source['mode']}")
        if source['sample_link']:
            print(f"     Sample: {source['sample_link'][:80]}...")
    
    conn.close()
    
    # Final summary
    print("\n" + "=" * 80)
    print("✅ Configuration Complete!")
    print("=" * 80)
    print("\n📊 Turkey HCM Profile Now Monitors:")
    print("   1. 🐦 Twitter: @sgksosyalmedya (via API)")
    print("   2. 📚 SMMM Bilgi Formu: SGK circulars with full text")
    print("   3. 📢 SGK Duyuru: Official announcements")
    print("\n🎯 Coverage Strategy:")
    print("   • Twitter: Real-time alerts (fastest)")
    print("   • SGK Duyuru: Official announcements (hours/days)")
    print("   • SMMM: Detailed circulars with analysis (3-4 days)")
    print("\n🚀 Next Steps:")
    print("   1. Run Legal Eagle for Turkey HCM")
    print("   2. Check daily digest email")
    print("   3. Verify circular 2026/9 would be captured")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    add_sgk_sources()