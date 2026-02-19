#!/usr/bin/env python3
"""
Setup script for Türkiye HCM profile.
Creates profile, adds Turkish URL sources (iKanun + Resmi Gazete with date templates),
and adds Turkish/English HCM glossary terms.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import (
    get_connection,
    create_schema_if_needed,
    create_profile,
    upsert_url_source,
    upsert_email_receiver,
    add_glossary_term,
    add_audit_log,
)


def setup_turkey_hcm():
    """
    Set up Türkiye/HCM profile with:
    - iKanun URL source (dynamic mode)
    - Resmi Gazete URL source (date-templated mode)
    - Turkish/English HCM glossary terms
    - Email receiver: hany.zanaty@sap.com
    """
    conn = get_connection()
    create_schema_if_needed(conn)
    
    print("=" * 60)
    print("Setting up Türkiye/HCM Profile")
    print("=" * 60)
    
    # 1. Create Türkiye/HCM profile
    print("\n[1] Creating Türkiye/HCM profile...")
    profile_id = create_profile(
        conn,
        country_code="TR",
        lob="HCM",
        name="Türkiye HCM",
        language="tr",
        active=1
    )
    print(f"✓ Profile created with ID: {profile_id}")
    add_audit_log(conn, entity="profiles", action="create", 
                  details="Türkiye/HCM profile created via setup script", 
                  profile_id=profile_id)
    
    # 2. Add iKanun URL source (dynamic mode)
    print("\n[2] Adding iKanun URL source (force_dynamic mode)...")
    url_ikanun = "http://www.ikanun.com/duyurular"
    sample_ikanun = "http://www.ikanun.com/duyuru/muhsgk-beyanname-duzenleme-programinin-bdp-yeni-surumu-03022026-yayimlandi"
    
    upsert_url_source(
        conn,
        profile_id=profile_id,
        url=url_ikanun,
        mode="force_dynamic",
        sample_link=sample_ikanun,
        read_more_label=None,
        crawl_version="v1",
        max_depth=2,
        allowed_domains=None,
        path_filter=None,
        max_results=20,
        date_scope="all"
    )
    print(f"✓ URL source added: {url_ikanun}")
    print(f"  - Mode: force_dynamic")
    print(f"  - Sample: {sample_ikanun}")
    add_audit_log(conn, entity="url_sources", action="add",
                  details=f"iKanun (force_dynamic): {url_ikanun}",
                  profile_id=profile_id)
    
    # 3. Add Resmi Gazete URL source (date-templated mode)
    print("\n[3] Adding Resmi Gazete URL source (date-templated mode)...")
    url_gazette = "https://www.resmigazete.gov.tr/"
    
    # Note: This will require enhancement to url_sources_runner.py to handle date templates
    # For now, we'll add it with auto mode and a note in the database
    upsert_url_source(
        conn,
        profile_id=profile_id,
        url=url_gazette,
        mode="auto",
        sample_link="https://www.resmigazete.gov.tr/eskiler/2026/02/20260217.pdf",
        read_more_label="PDF Görüntüle",
        crawl_version="v1",
        max_depth=2,
        allowed_domains=None,
        path_filter=None,
        max_results=20,
        date_scope="last_7_days"
    )
    print(f"✓ URL source added: {url_gazette}")
    print(f"  - Mode: auto (will be enhanced for date-templated crawling)")
    print(f"  - Date scope: last_7_days")
    add_audit_log(conn, entity="url_sources", action="add",
                  details=f"Resmi Gazete (date-templated): {url_gazette}",
                  profile_id=profile_id)
    
    # 4. Add email receiver
    print("\n[4] Adding email receiver...")
    email = "hany.zanaty@sap.com"
    upsert_email_receiver(conn, profile_id=profile_id, email=email)
    print(f"✓ Email receiver added: {email}")
    add_audit_log(conn, entity="email_receivers", action="add",
                  details=f"Added receiver: {email}",
                  profile_id=profile_id)
    
    # 5. Add Turkish glossary terms
    print("\n[5] Adding Turkish glossary terms...")
    
    turkish_terms = [
        ("Asgari Ücret", "Minimum Wage", "Payroll"),
        ("Sosyal Güvenlik Kurumu", "Social Security Institution", "Social Security"),
        ("SGK", "Social Security Institution", "Social Security"),
        ("SSI", "Social Security", "Social Security"),
        ("SSK", "Social Security", "Social Security"),
        ("Vergi Dilimleri", "Tax Brackets", "Tax"),
        ("Gelir Vergisi Oranları", "Income Tax Rates", "Tax"),
        ("VERGİ", "Tax", "Tax"),
        ("Damga Vergisi", "Stamp Tax", "Tax"),
        ("kıdem tazminatı", "Severance Pay", "Payroll"),
        ("vergi istisnası", "Tax Exemption", "Tax"),
        ("Yemek yardımı", "Meal Allowance", "Benefits"),
        ("ARAŞTIRMA GELİŞTİRME", "R&D", "Incentives"),
        ("ARGE", "R&D", "Incentives"),
        ("prim desteği", "Premium Support", "Social Security"),
        ("sosyal yardım", "Social Aid", "Social Security"),
        ("gelir vergisi", "Income Tax", "Tax"),
        ("vergi matrahı", "Tax Base", "Tax"),
        ("brüt maaş", "Gross Salary", "Payroll"),
        ("sağlık sigortası", "Health Insurance", "Social Security"),
        ("emeklilik", "Retirement", "Social Security"),
        ("işveren", "Employer", "Employment"),
        ("çalışan", "Employee", "Employment"),
        ("işçi", "Worker", "Employment"),
        ("maaş", "Salary", "Payroll"),
        ("ücret", "Wage", "Payroll"),
        ("bordro", "Payroll", "Payroll"),
        ("vergi kesintisi", "Tax Withholding", "Tax"),
        ("ihbar tazminatı", "Notice Compensation", "Payroll"),
        ("yıllık izin", "Annual Leave", "Leave"),
        ("doğum izni", "Maternity Leave", "Leave"),
        ("babalık izni", "Paternity Leave", "Leave"),
        ("iş sözleşmesi", "Employment Contract", "Employment"),
        ("istihdam", "Employment", "Employment"),
        ("İŞKUR", "Turkish Employment Agency", "Employment"),
        ("iş kanunu", "Labor Law", "Employment"),
        ("toplu sözleşme", "Collective Agreement", "Employment"),
        ("fazla mesai", "Overtime", "Payroll"),
        ("işten çıkarma", "Termination", "Employment"),
    ]
    
    count = 0
    for term_tr, notes_en, category in turkish_terms:
        add_glossary_term(
            conn,
            profile_id=profile_id,
            term=term_tr,
            lang="tr",
            category=category,
            product=None,
            weight=1.0,
            notes=notes_en
        )
        count += 1
    
    print(f"✓ Added {count} Turkish glossary terms")
    
    # 6. Add English glossary terms
    print("\n[6] Adding English glossary terms...")
    
    english_terms = [
        ("Premium Support", "Social Security"),
        ("Social Aids", "Social Security"),
        ("Social Aid", "Social Security"),
        ("Income Tax", "Tax"),
        ("Tax Base", "Tax"),
        ("Tax Payer", "Tax"),
        ("Gross Salary", "Payroll"),
        ("Minimum Wage", "Payroll"),
        ("Social Security", "Social Security"),
        ("Health Insurance", "Social Security"),
        ("Retirement", "Social Security"),
        ("Severance Pay", "Payroll"),
        ("Tax Exemption", "Tax"),
        ("Tax Withholding", "Tax"),
        ("Meal Allowance", "Benefits"),
        ("R&D", "Incentives"),
        ("Employee", "Employment"),
        ("Employer", "Employment"),
        ("Worker", "Employment"),
        ("Salary", "Payroll"),
        ("Wage", "Payroll"),
        ("Payroll", "Payroll"),
        ("Employment Contract", "Employment"),
        ("Labor Contract", "Employment"),
        ("Employment", "Employment"),
        ("Labor Law", "Employment"),
        ("Collective Agreement", "Employment"),
        ("Overtime", "Payroll"),
        ("Termination", "Employment"),
        ("Annual Leave", "Leave"),
        ("Maternity Leave", "Leave"),
        ("Paternity Leave", "Leave"),
    ]
    
    for term_en, category in english_terms:
        add_glossary_term(
            conn,
            profile_id=profile_id,
            term=term_en,
            lang="en",
            category=category,
            product=None,
            weight=1.0,
            notes="English HCM term"
        )
        count += 1
    
    print(f"✓ Added {len(english_terms)} English glossary terms")
    print(f"✓ Total glossary terms: {count}")
    add_audit_log(conn, entity="glossary_terms", action="bulk_add",
                  details=f"Added {count} HCM terms (Turkish + English)",
                  profile_id=profile_id)
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Türkiye/HCM Profile Setup Complete!")
    print("=" * 60)
    print(f"\nProfile ID: {profile_id}")
    print(f"Country: TR (Türkiye)")
    print(f"LoB: HCM")
    print(f"Language: Turkish (tr)")
    print(f"URL Sources: 2 (iKanun + Resmi Gazete)")
    print(f"Glossary Terms: {count}")
    print(f"Email Receiver: hany.zanaty@sap.com")
    print("\nNext steps:")
    print("1. Enhance url_sources_runner.py for date-templated Resmi Gazete crawling")
    print("2. Access the admin UI: http://localhost:8080/admin")
    print(f"3. Navigate to the Türkiye HCM profile (ID: {profile_id})")
    print("4. Set schedule day for automated runs")
    print("5. Run the profile to test both sources")
    print("\n⚠️  Note: Resmi Gazete requires date-templated enhancement to be fully functional")
    print("\n")


if __name__ == "__main__":
    setup_turkey_hcm()
