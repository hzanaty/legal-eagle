#!/usr/bin/env python3
"""
Seed initial Greece Legal Repo nodes from Resources/.
Idempotent — skips nodes that already exist (same country+domain+subdomain+topic).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from configurations.db import (
    get_connection, create_schema_if_needed,
    create_repo_node, add_repo_asset, list_repo_nodes,
)

DB_PATH = os.environ.get("LEGAL_EAGLE_DB", os.path.join(os.path.dirname(__file__), "..", "configurations", "config.db"))

NODES = [
    {
        "key": "ergani_ii",
        "parent_key": None,
        "country_code": "GR",
        "domain": "Labor",
        "subdomain": "ERGANI",
        "topic": "ERGANI II",
        "status": "ANALYZED",
        "authority": "ERGANI",
        "law_reference": "Decision 32689/12.12.2025 — FEK B’ 6745/16-12-2025",
        "official_url": "https://ergani.gov.gr",
        "effective_date": "2026-02-16",
        "summary": (
            "Ministerial Decision 32689/12.12.2025 introduces a new framework of digital declarations "
            "for work time organization, employment changes, hiring, termination, collective agreements, "
            "and work card reporting under ERGANI II. All legacy E-forms (E1–E12) are abolished. "
            "Effective 16 February 2026."
        ),
        "assets": [
            ("mindmap", "ERGANI II Mind Map v2", "Resources/ERGANI_II_MindMap_v2.html", None),
            ("jira_epic", "GSREQSE-15293", "GSREQSE-15293", "https://jira.tools.sap/browse/GSREQSE-15293"),
        ],
    },
    {
        "key": "ergani_ii_ma",
        "parent_key": "ergani_ii",
        "country_code": "GR",
        "domain": "Labor",
        "subdomain": "ERGANI",
        "topic": "Employment Relationship Modification (MA_v1)",
        "status": "SCOPING",
        "authority": "ERGANI",
        "law_reference": "Decision 32689/2025 — Art. 2.3",
        "official_url": "https://ergani.gov.gr",
        "effective_date": "2026-02-16",
        "summary": (
            "New MA_v1 XML schema replaces E4. 17 change reason codes mapped to SAP infotypes "
            "IT0001, IT0002, IT0008, IT0016, IT3219, IT3220. New SAP program HGRLLIA4. "
            "Two new customizing tables T7GR1ERG1, T7GR1ERG2."
        ),
        "assets": [
            ("jira_req", "GSREQSE-16012", "GSREQSE-16012", "https://jira.tools.sap/browse/GSREQSE-16012"),
        ],
    },
    {
        "key": "ergani_ii_hiring",
        "parent_key": "ergani_ii",
        "country_code": "GR",
        "domain": "Labor",
        "subdomain": "ERGANI",
        "topic": "Work Commencement Notification (Art. 2.1)",
        "status": "NEW",
        "authority": "ERGANI",
        "law_reference": "Decision 32689/2025 — Art. 2.1",
        "official_url": "https://ergani.gov.gr",
        "effective_date": "2026-02-16",
        "summary": "Replaces E3/E4 hiring forms. Submitted before work starts. Employee must accept via MyErgani.",
        "assets": [
            ("jira_req", "GSREQSE-16014", "GSREQSE-16014", "https://jira.tools.sap/browse/GSREQSE-16014"),
        ],
    },
    {
        "key": "ergani_ii_termination",
        "parent_key": "ergani_ii",
        "country_code": "GR",
        "domain": "Labor",
        "subdomain": "ERGANI",
        "topic": "Contract Termination Notification (Art. 2.7)",
        "status": "NEW",
        "authority": "ERGANI",
        "law_reference": "Decision 32689/2025 — Art. 2.7",
        "official_url": "https://ergani.gov.gr",
        "effective_date": "2026-02-16",
        "summary": "Replaces E5/E6/E7. Covers voluntary departure, dismissal, fixed-term end, death, probation.",
        "assets": [
            ("jira_req", "GSREQSE-16016", "GSREQSE-16016", "https://jira.tools.sap/browse/GSREQSE-16016"),
        ],
    },
    {
        "key": "ergani_ii_workcard",
        "parent_key": "ergani_ii",
        "country_code": "GR",
        "domain": "Labor",
        "subdomain": "ERGANI",
        "topic": "Digital Work Card Declarations (Art. 2.11)",
        "status": "NEW",
        "authority": "ERGANI",
        "law_reference": "Decision 32689/2025 — Art. 2.11",
        "official_url": "https://ergani.gov.gr",
        "effective_date": "2026-02-16",
        "summary": "Real-time clock-in/clock-out per employee. 5-year local retention, 6 months in ERGANI II system.",
        "assets": [
            ("jira_req", "GSREQSE-16022", "GSREQSE-16022", "https://jira.tools.sap/browse/GSREQSE-16022"),
        ],
    },
    {
        "key": "efka",
        "parent_key": None,
        "country_code": "GR",
        "domain": "Social Insurance",
        "subdomain": "EFKA",
        "topic": "e-EFKA Social Insurance Authority",
        "status": "NEW",
        "authority": "EFKA",
        "law_reference": None,
        "official_url": "https://www.efka.gov.gr",
        "effective_date": None,
        "summary": "Greek unified social insurance authority. Manages contributions, pensions, and employer reporting.",
        "assets": [],
    },
    {
        "key": "teka",
        "parent_key": None,
        "country_code": "GR",
        "domain": "Social Insurance",
        "subdomain": "TEKA",
        "topic": "TEKA Supplementary Pension Authority",
        "status": "NEW",
        "authority": "TEKA",
        "law_reference": None,
        "official_url": "https://teka.gov.gr",
        "effective_date": None,
        "summary": "Supplementary pension fund for private sector employees.",
        "assets": [],
    },
    {
        "key": "aade",
        "parent_key": None,
        "country_code": "GR",
        "domain": "Taxation",
        "subdomain": "AADE",
        "topic": "AADE Tax Authority",
        "status": "NEW",
        "authority": "AADE",
        "law_reference": None,
        "official_url": "https://www.aade.gr",
        "effective_date": None,
        "summary": "Independent Authority for Public Revenue. Manages income tax, payroll tax withholding, and employer tax reporting.",
        "assets": [],
    },
]


def main():
    from datetime import date
    conn = get_connection(DB_PATH)
    create_schema_if_needed(conn)

    # Build existing node map to avoid duplicates
    existing = {
        (r["country_code"], r["domain"], r["subdomain"], r["topic"]): r["id"]
        for r in conn.execute("SELECT * FROM repo_nodes").fetchall()
    }

    key_to_id = {}

    for node_def in NODES:
        key = (node_def["country_code"], node_def["domain"],
               node_def["subdomain"], node_def["topic"])
        if key in existing:
            nid = existing[key]
            print(f"  EXISTS: {node_def['topic']} (id={nid})")
        else:
            parent_id = key_to_id.get(node_def["parent_key"])
            nid = create_repo_node(
                conn,
                country_code=node_def["country_code"],
                domain=node_def["domain"],
                subdomain=node_def["subdomain"],
                topic=node_def["topic"],
                status=node_def["status"],
                authority=node_def.get("authority"),
                law_reference=node_def.get("law_reference"),
                official_url=node_def.get("official_url"),
                summary=node_def.get("summary"),
                effective_date=node_def.get("effective_date"),
                date_detected=date.today().isoformat(),
                parent_node_id=parent_id,
            )
            print(f"  CREATED: {node_def['topic']} (id={nid})")
            for asset_type, title, reference, url in node_def.get("assets", []):
                add_repo_asset(conn, nid, asset_type, title, reference, url)
                print(f"    asset: {asset_type} — {title}")

        key_to_id[node_def["key"]] = nid

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
