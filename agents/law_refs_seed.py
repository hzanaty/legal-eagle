"""
Law Reference registry seed (v3.16).

Seeds a profile's `law_refs` catalog — the canonical per-profile list of monitored
laws. A resolved law becomes the primary cross-language grouping/dedup identity
(law_id). Idempotent: a law is matched on (profile_id, law_number) when a number
exists, else on (profile_id, name_en); existing rows are updated in place.

Authorities are resolved/created by name via get_or_create_authority.

The TR/HCM seed below is from Resources/Turkey_HCM_Law_Reference.md (LPM-authored). Run:
    python3 -m agents.law_refs_seed <profile_id>        # defaults to TR/HCM seed
"""

import sys
from typing import Any, Dict, List

from configurations.db import (
    get_connection, create_schema_if_needed, get_or_create_authority,
    add_law_ref, update_law_ref,
)

# Each row mirrors the 9-field schema. authority is a NAME (resolved to authority_id).
# status ∈ {Active, Partially Active, Repealed, Draft}.
TR_HCM_LAWS: List[Dict[str, Any]] = [
    {"name_en": "Labour Law", "name_native": "İş Kanunu", "law_number": "4857",
     "law_year": "2003", "authority": "Ministry of Labour and Social Security",
     "effective_date": "2003-06-10", "status": "Active", "source_url": "Ministry / Mevzuat",
     "key_articles": "2; 7; 17; 24; 25; 30; 32; 39; 41; 46; 47; 53-60; 63; 74"},
    {"name_en": "Social Insurance and General Health Insurance Law",
     "name_native": "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu", "law_number": "5510",
     "law_year": "2006", "authority": "Sosyal Güvenlik Kurumu (SGK)", "effective_date": "2008-10-01", "status": "Active",
     "source_url": "SGK / Mevzuat", "key_articles": "4; 8; 17; 18; 60; 80; 81; 82; 86; 88"},
    {"name_en": "Unemployment Insurance Law", "name_native": "İşsizlik Sigortası Kanunu",
     "law_number": "4447", "law_year": "1999", "authority": "Sosyal Güvenlik Kurumu (SGK)",
     "effective_date": "1999-09-08", "status": "Active", "source_url": "İŞKUR / Mevzuat",
     "key_articles": "46-55; Temporary Articles 10; 36"},
    {"name_en": "Income Tax Law", "name_native": "Gelir Vergisi Kanunu", "law_number": "193",
     "law_year": "1960", "authority": "Gelir İdaresi Başkanlığı (GİB)", "effective_date": "1961-01-01",
     "status": "Active", "source_url": "GİB / Mevzuat", "key_articles": "23; 31; 32; 61; 63; 94; 103; 104"},
    {"name_en": "Stamp Tax Law", "name_native": "Damga Vergisi Kanunu", "law_number": "488",
     "law_year": "1964", "authority": "Gelir İdaresi Başkanlığı (GİB)", "effective_date": "1964-07-11",
     "status": "Active", "source_url": "GİB / Mevzuat", "key_articles": "1; 3; 4; 8; 10; 14"},
    {"name_en": "Former Labour Law — Severance Provision", "name_native": "İş Kanunu",
     "law_number": "1475", "law_year": "1971", "authority": "Ministry of Labour and Social Security",
     "effective_date": "1971-09-01", "status": "Partially Active", "source_url": "Ministry / Mevzuat",
     "key_articles": "14"},
    {"name_en": "Occupational Health and Safety Law", "name_native": "İş Sağlığı ve Güvenliği Kanunu",
     "law_number": "6331", "law_year": "2012", "authority": "Ministry of Labour and Social Security",
     "effective_date": "2012-06-30", "status": "Active", "source_url": "Ministry / Mevzuat",
     "key_articles": "4; 6; 10; 15; 17; 26; 38"},
    {"name_en": "Law on Supporting Research, Development and Design Activities",
     "name_native": "Araştırma, Geliştirme ve Tasarım Faaliyetlerinin Desteklenmesi Hakkında Kanun",
     "law_number": "5746", "law_year": "2008", "authority": "Ministry of Industry and Technology",
     "effective_date": "2008-04-01", "status": "Active",
     "source_url": "Ministry of Industry and Technology / Mevzuat", "key_articles": "3; 4"},
    {"name_en": "Technology Development Zones Law", "name_native": "Teknoloji Geliştirme Bölgeleri Kanunu",
     "law_number": "4691", "law_year": "2001", "authority": "Ministry of Industry and Technology",
     "effective_date": "2001-07-06", "status": "Active",
     "source_url": "Ministry of Industry and Technology / Mevzuat", "key_articles": "3; 7; Temporary Article 2"},
    {"name_en": "International Labour Force Law", "name_native": "Uluslararası İşgücü Kanunu",
     "law_number": "6735", "law_year": "2016", "authority": "Ministry of Labour and Social Security",
     "effective_date": "2016-08-13", "status": "Active", "source_url": "Ministry / Mevzuat",
     "key_articles": "4; 6; 9; 10; 13; 16; 23"},
    {"name_en": "Trade Unions and Collective Labour Agreements Law",
     "name_native": "Sendikalar ve Toplu İş Sözleşmesi Kanunu", "law_number": "6356",
     "law_year": "2012", "authority": "Ministry of Labour and Social Security",
     "effective_date": "2012-11-07", "status": "Active", "source_url": "Ministry / Mevzuat",
     "key_articles": "17; 25; 41; 42; 50; 53"},
]


def seed_law_refs(conn, profile_id: int, laws: List[Dict[str, Any]]) -> int:
    """Upsert law rows for a profile. Match on law_number (or name_en). Returns count written."""
    n = 0
    for law in laws:
        authority_id = get_or_create_authority(conn, profile_id, law.get("authority", ""))
        fields = {
            "name_en": law["name_en"], "name_native": law.get("name_native"),
            "law_number": law.get("law_number"), "law_year": law.get("law_year"),
            "authority_id": authority_id, "effective_date": law.get("effective_date"),
            "status": law.get("status"), "source_url": law.get("source_url"),
            "key_articles": law.get("key_articles"),
        }
        num = (law.get("law_number") or "").strip()
        existing = None
        if num:
            existing = conn.execute(
                "SELECT id FROM law_refs WHERE profile_id=? AND law_number=?", (profile_id, num)
            ).fetchone()
        if not existing:
            existing = conn.execute(
                "SELECT id FROM law_refs WHERE profile_id=? AND name_en=?", (profile_id, law["name_en"])
            ).fetchone()
        if existing:
            update_law_ref(conn, int(existing["id"]), fields)
        else:
            add_law_ref(conn, profile_id, fields)
        n += 1
    conn.commit()
    return n


def _main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m agents.law_refs_seed <profile_id>", file=sys.stderr)
        return 2
    profile_id = int(argv[1])
    conn = get_connection()
    create_schema_if_needed(conn)
    n = seed_law_refs(conn, profile_id, TR_HCM_LAWS)
    print(f"✅ Seeded {n} law references for profile {profile_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
