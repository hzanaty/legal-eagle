#!/usr/bin/env python3
"""
Setup script for Spain HCM profile.
Creates profile, adds Spanish Tax Agency URL source with recursive crawl,
and adds generic HCM glossary terms.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import (
    get_connection,
    create_schema_if_needed,
    create_profile,
    upsert_url_source,
    add_glossary_term,
    add_audit_log,
)


def setup_spain_hcm():
    """
    Set up Spain/HCM profile with:
    - Spanish Tax Agency URL source (recursive mode)
    - Generic HCM glossary terms
    """
    conn = get_connection()
    create_schema_if_needed(conn)
    
    print("=" * 60)
    print("Setting up Spain/HCM Profile")
    print("=" * 60)
    
    # 1. Create Spain/HCM profile
    print("\n[1] Creating Spain/HCM profile...")
    profile_id = create_profile(
        conn,
        country_code="ES",
        lob="HCM",
        name="Spain HCM",
        language="es",
        active=1
    )
    print(f"✓ Profile created with ID: {profile_id}")
    add_audit_log(conn, entity="profiles", action="create", 
                  details="Spain/HCM profile created via setup script", 
                  profile_id=profile_id)
    
    # 2. Add Spanish Tax Agency URL source (recursive mode)
    print("\n[2] Adding Spanish Tax Agency URL source (recursive mode)...")
    url = "https://sede.agenciatributaria.gob.es/Sede/irpf/novedades-impuesto.html"
    allowed_domains = "sede.agenciatributaria.gob.es\nwww2.agenciatributaria.gob.es"
    
    upsert_url_source(
        conn,
        profile_id=profile_id,
        url=url,
        mode="recursive",
        sample_link="https://www2.agenciatributaria.gob.es/ES13/S/IAFRIAFRC12F?TIPO=R&CODIGO=0141773",
        read_more_label=None,
        crawl_version="v2",  # Use v2 for recursive crawl
        max_depth=3,
        allowed_domains=allowed_domains,
        path_filter="novedades",
        max_results=20,
        date_scope="all"
    )
    print(f"✓ URL source added: {url}")
    print(f"  - Mode: recursive")
    print(f"  - Max Depth: 3")
    print(f"  - Allowed Domains: sede.agenciatributaria.gob.es, www2.agenciatributaria.gob.es")
    print(f"  - Path Filter: novedades")
    print(f"  - Max Results: 20")
    add_audit_log(conn, entity="url_sources", action="add",
                  details=f"Spanish Tax Agency (recursive): {url}",
                  profile_id=profile_id)
    
    # 3. Add generic HCM glossary terms
    print("\n[3] Adding generic HCM glossary terms...")
    
    # English terms
    english_terms = [
        "employee",
        "employment",
        "labor contract",
        "employment contract",
        "payroll",
        "social security",
        "income tax",
        "personal income tax",
        "tax withholding",
        "withholding tax",
        "employer",
        "worker",
        "salary",
        "wages",
        "pension",
        "retirement",
        "benefits",
        "compensation",
        "hiring",
        "termination",
        "severance",
        "working hours",
        "overtime",
        "vacation",
        "sick leave",
        "maternity leave",
        "paternity leave",
    ]
    
    # Spanish terms
    spanish_terms = [
        "empleado",
        "empleo",
        "contrato laboral",
        "nómina",
        "seguridad social",
        "impuesto sobre la renta",
        "IRPF",
        "retención fiscal",
        "empleador",
        "trabajador",
        "salario",
        "sueldo",
        "pensión",
        "jubilación",
        "despido",
        "indemnización",
        "horas de trabajo",
        "vacaciones",
        "baja por enfermedad",
        "baja maternal",
        "baja paternal",
    ]
    
    count = 0
    
    # Add English terms
    for term in english_terms:
        add_glossary_term(
            conn,
            profile_id=profile_id,
            term=term,
            lang="en",
            category="HCM",
            product=None,
            weight=1.0,
            notes="Generic HCM term"
        )
        count += 1
    
    # Add Spanish terms
    for term in spanish_terms:
        add_glossary_term(
            conn,
            profile_id=profile_id,
            term=term,
            lang="es",
            category="HCM",
            product=None,
            weight=1.0,
            notes="Generic HCM term (Spanish)"
        )
        count += 1
    
    print(f"✓ Added {count} glossary terms ({len(english_terms)} English + {len(spanish_terms)} Spanish)")
    add_audit_log(conn, entity="glossary_terms", action="bulk_add",
                  details=f"Added {count} generic HCM terms",
                  profile_id=profile_id)
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Spain/HCM Profile Setup Complete!")
    print("=" * 60)
    print(f"\nProfile ID: {profile_id}")
    print(f"Country: ES (Spain)")
    print(f"LoB: HCM")
    print(f"URL Sources: 1 (recursive mode)")
    print(f"Glossary Terms: {count}")
    print("\nNext steps:")
    print("1. Access the admin UI: http://localhost:8080/admin")
    print(f"2. Navigate to the Spain HCM profile (ID: {profile_id})")
    print("3. Add email receivers for notifications")
    print("4. Set schedule day for automated runs")
    print("5. Run the profile to test the recursive crawler")
    print("\n")


if __name__ == "__main__":
    setup_spain_hcm()
