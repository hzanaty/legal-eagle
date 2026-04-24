#!/usr/bin/env python3
"""
Fix SMMM Bilgi Formu URL - use the correct homepage URL.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations import db

print('=' * 80)
print('Updating SMMM Bilgi Formu URL')
print('=' * 80)

conn = db.get_connection()

# Get Turkey HCM profile
profile = db.get_profile(conn, 'TR', 'HCM')
profile_id = profile['id']

print(f'\nProfile: TR/HCM (ID: {profile_id})')

# Delete the incorrect URL
print('\n[1] Removing incorrect URL...')
db.delete_url_source(conn, profile_id, 'https://www.muhasebeyazilari.com/guncelmevzuat/')
print('✅ Removed: muhasebeyazilari.com/guncelmevzuat/')

# Add the correct URL
print('\n[2] Adding correct URL...')
db.upsert_url_source(
    conn=conn,
    profile_id=profile_id,
    url='https://www.smmmbilgiformu.com/',
    mode='force_static',
    sample_link='https://www.muhasebeyazilari.com/guncelmevzuat/mevzuat_oku.php?mevzuat_id=7188',
    read_more_label=None,
    crawl_version='v1',
    max_depth=2,
    allowed_domains=None,
    path_filter=None,
    max_results=20,
    date_scope='all'
)
print('✅ Added: www.smmmbilgiformu.com/')
print('   This is the homepage that lists all circulars')
print('   Articles link to muhasebeyazilari.com (which is correct)')

# Verify
print('\n[3] Verifying configuration...')
url_sources = db.list_url_sources(conn, profile_id)

print(f'\n✅ URL Sources ({len(url_sources)}):')
for source in url_sources:
    print(f'   • {source["url"]}')
    if 'smmmbilgiformu' in source['url']:
        print(f'     ✅ CORRECT - This is the homepage with circular listings')

conn.close()

print('\n' + '=' * 80)
print('✅ Configuration Updated Successfully!')
print('=' * 80)
print('\nHow it works:')
print('1. Legal Eagle scrapes www.smmmbilgiformu.com/ (homepage)')
print('2. Finds circular links (e.g., SGK Genelgesi 2026/9)')
print('3. Links point to muhasebeyazilari.com articles')
print('4. Scraper follows links and extracts full text')
print('5. Delivers in your daily email')
print('\n' + '=' * 80)