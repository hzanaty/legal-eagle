#!/usr/bin/env python3
"""
Migration script to add translation language support:
1. Add translation_lang column to email_receivers table
2. Fix existing profile languages based on country code
3. Set default translation_lang='en' for existing receivers
"""

import sys
import os

# Add parent directory to path so we can import configurations
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import get_connection, create_schema_if_needed
from configurations.config_loader import COUNTRY_LANG_MAP


def run_migration():
    """Execute the translation language migration."""
    print("🔄 Starting translation language migration...\n")
    
    conn = get_connection()
    create_schema_if_needed(conn)
    
    # Step 1: Add translation_lang column (already handled by create_schema_if_needed with ALTER TABLE)
    print("✅ Step 1: translation_lang column added to email_receivers")
    
    # Step 2: Fix profile languages based on country code
    print("\n📍 Step 2: Fixing profile languages based on country...")
    
    profiles = conn.execute("SELECT id, country_code, language FROM profiles").fetchall()
    updated_profiles = 0
    
    for profile in profiles:
        profile_id = profile["id"]
        country_code = profile["country_code"]
        current_lang = profile["language"]
        
        # Get expected language from country mapping
        expected_lang = COUNTRY_LANG_MAP.get(country_code.upper(), "en")
        
        # Update if language is NULL, empty, or doesn't match expected
        if not current_lang or current_lang != expected_lang:
            conn.execute(
                "UPDATE profiles SET language = ? WHERE id = ?",
                (expected_lang, profile_id)
            )
            updated_profiles += 1
            print(f"   ✓ Profile {profile_id} ({country_code}): '{current_lang or 'NULL'}' → '{expected_lang}'")
    
    conn.commit()
    print(f"✅ Updated {updated_profiles} profile(s)")
    
    # Step 3: Set default translation_lang='en' for existing receivers
    print("\n📧 Step 3: Setting default translation language for receivers...")
    
    result = conn.execute(
        "UPDATE email_receivers SET translation_lang = 'en' WHERE translation_lang IS NULL"
    )
    conn.commit()
    
    affected = result.rowcount
    print(f"✅ Set default translation_lang='en' for {affected} receiver(s)")
    
    # Step 4: Verify results
    print("\n📊 Migration Summary:")
    print("=" * 60)
    
    # Count profiles by language
    lang_counts = conn.execute("""
        SELECT language, COUNT(*) as count 
        FROM profiles 
        GROUP BY language 
        ORDER BY count DESC
    """).fetchall()
    
    print("\nProfiles by language:")
    for row in lang_counts:
        print(f"   {row['language']}: {row['count']} profile(s)")
    
    # Count receivers by translation language
    trans_counts = conn.execute("""
        SELECT translation_lang, COUNT(*) as count 
        FROM email_receivers 
        GROUP BY translation_lang 
        ORDER BY count DESC
    """).fetchall()
    
    print("\nReceivers by translation language:")
    for row in trans_counts:
        print(f"   {row['translation_lang']}: {row['count']} receiver(s)")
    
    # Show sample profile configurations
    print("\n📋 Sample Profile Configurations:")
    samples = conn.execute("""
        SELECT p.id, p.country_code, p.lob, p.language,
               GROUP_CONCAT(e.email || ' (' || e.translation_lang || ')') as receivers
        FROM profiles p
        LEFT JOIN email_receivers e ON p.id = e.profile_id
        GROUP BY p.id
        LIMIT 5
    """).fetchall()
    
    for sample in samples:
        print(f"\n   Profile {sample['id']}: {sample['country_code']}/{sample['lob']}")
        print(f"      Analysis Language: {sample['language']}")
        if sample['receivers']:
            print(f"      Receivers: {sample['receivers']}")
        else:
            print(f"      Receivers: (none)")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Migration completed successfully!")
    print("\nNext steps:")
    print("  1. Verify profile languages match expected countries")
    print("  2. Update receiver translation languages in Admin UI as needed")
    print("  3. Test email sending with translated content")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
