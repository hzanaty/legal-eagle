#!/usr/bin/env python3
"""
Seed Greece HCM profile with URL sources and glossary terms.
Idempotent — safe to run multiple times.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from configurations.db import (
    get_connection, create_schema_if_needed, create_profile,
    add_glossary_term, upsert_url_source,
)

DB_PATH = os.environ.get("LEGAL_EAGLE_DB", os.path.join(os.path.dirname(__file__), "..", "configurations", "config.db"))

URL_SOURCES = [
    ("https://ergani.gov.gr", "auto"),
    ("https://ypergasias.gov.gr", "auto"),
    ("https://www.efka.gov.gr", "auto"),
    ("https://teka.gov.gr", "auto"),
    ("https://eservices.yeka.gr", "auto"),
    ("https://www.aade.gr", "auto"),
    ("https://www.et.gr", "auto"),
    ("https://www.gov.gr", "auto"),
]

# (term, category) — sourced from Resources/Greece_Glossary.md
GLOSSARY_TERMS = [
    # Employment & Labor Law
    ("ERGANI", "Employment & Labor Law"),
    ("ERGANI II", "Employment & Labor Law"),
    ("Digital Work Card", "Employment & Labor Law"),
    ("Work Card", "Employment & Labor Law"),
    ("Employment Contract", "Employment & Labor Law"),
    ("Fixed-Term Contract", "Employment & Labor Law"),
    ("Permanent Contract", "Employment & Labor Law"),
    ("Working Time", "Employment & Labor Law"),
    ("Working Hours", "Employment & Labor Law"),
    ("Overtime", "Employment & Labor Law"),
    ("Flexible Working Time", "Employment & Labor Law"),
    ("Shift Work", "Employment & Labor Law"),
    ("Leave", "Employment & Labor Law"),
    ("Annual Leave", "Employment & Labor Law"),
    ("Absence", "Employment & Labor Law"),
    ("Vacation Entitlement", "Employment & Labor Law"),
    ("Collective Agreement", "Employment & Labor Law"),
    ("Collective Labor Agreement", "Employment & Labor Law"),
    ("Hiring", "Employment & Labor Law"),
    ("Recruitment", "Employment & Labor Law"),
    ("Employment Relationship", "Employment & Labor Law"),
    ("Contract Amendment", "Employment & Labor Law"),
    ("Termination", "Employment & Labor Law"),
    ("Dismissal", "Employment & Labor Law"),
    ("Resignation", "Employment & Labor Law"),
    ("Probation Period", "Employment & Labor Law"),
    ("Labor Inspection", "Employment & Labor Law"),
    ("Labor Code", "Employment & Labor Law"),
    ("Ministry of Labor", "Employment & Labor Law"),
    # Social Insurance
    ("EFKA", "Social Insurance"),
    ("e-EFKA", "Social Insurance"),
    ("APD", "Social Insurance"),
    ("Analytical Periodic Declaration", "Social Insurance"),
    ("Social Insurance", "Social Insurance"),
    ("Insurance Contributions", "Social Insurance"),
    ("Insurance Days", "Social Insurance"),
    ("Pension", "Social Insurance"),
    ("Supplementary Pension", "Social Insurance"),
    ("TEKA", "Social Insurance"),
    ("AMKA", "Social Insurance"),
    ("Insurance Package", "Social Insurance"),
    ("Insurance Fund", "Social Insurance"),
    ("Contribution Rates", "Social Insurance"),
    ("Employer Contributions", "Social Insurance"),
    ("Employee Contributions", "Social Insurance"),
    # Payroll
    ("Payroll", "Payroll"),
    ("Salary", "Payroll"),
    ("Wage", "Payroll"),
    ("Minimum Wage", "Payroll"),
    ("Basic Salary", "Payroll"),
    ("Salary Increase", "Payroll"),
    ("Salary Adjustment", "Payroll"),
    ("Bonus", "Payroll"),
    ("Allowance", "Payroll"),
    ("Payroll Reporting", "Payroll"),
    ("Payroll Declaration", "Payroll"),
    ("Payroll Compliance", "Payroll"),
    ("Payroll Tax", "Payroll"),
    # Taxation
    ("AADE", "Taxation"),
    ("Income Tax", "Taxation"),
    ("Tax Declaration", "Taxation"),
    ("Tax Reporting", "Taxation"),
    ("Tax Withholding", "Taxation"),
    ("Tax Exemption", "Taxation"),
    ("Tax Rate", "Taxation"),
    ("Tax Authority", "Taxation"),
    # Government Reporting & XML
    ("XML", "Government Reporting & XML"),
    ("Schema", "Government Reporting & XML"),
    ("XSD", "Government Reporting & XML"),
    ("Digital Declaration", "Government Reporting & XML"),
    ("Electronic Submission", "Government Reporting & XML"),
    ("Government Reporting", "Government Reporting & XML"),
    ("Reporting Obligation", "Government Reporting & XML"),
    ("Digital Platform", "Government Reporting & XML"),
    ("Electronic Filing", "Government Reporting & XML"),
    # SAP-Specific Mapping Terms
    ("IT3219", "SAP-Specific"),
    ("IT3220", "SAP-Specific"),
    ("IT0007", "SAP-Specific"),
    ("IT0008", "SAP-Specific"),
    ("IT0016", "SAP-Specific"),
    ("Work Card Declaration", "SAP-Specific"),
    ("Employment Modification", "SAP-Specific"),
    ("Employment Commencement", "SAP-Specific"),
    ("Employment Termination", "SAP-Specific"),
    ("Leave Declaration", "SAP-Specific"),
    ("APD Reporting", "SAP-Specific"),
    ("ERGANI Reporting", "SAP-Specific"),
]


def main():
    conn = get_connection(DB_PATH)
    create_schema_if_needed(conn)

    # Create or retrieve profile (idempotent via INSERT OR IGNORE inside create_profile)
    pid = create_profile(conn, country_code="GR", lob="HCM", name="Greece HCM",
                         language="el", active=1)
    print(f"Profile: Greece HCM (id={pid})")

    # URL sources
    for url, mode in URL_SOURCES:
        upsert_url_source(conn, pid, url=url, mode=mode)
        print(f"  URL: {url}")

    # Glossary terms
    count = 0
    for term, category in GLOSSARY_TERMS:
        add_glossary_term(conn, pid, term, lang="en", category=category)
        count += 1
    print(f"  Glossary: {count} terms imported")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
