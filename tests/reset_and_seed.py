import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from configurations.db import get_connection, create_schema_if_needed, create_authority, upsert_rss_feed

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test.db")

AUTHORITIES = [
    {"name": "Ministry of Human Resources", "aliases": "MoHR"},
    {"name": "Xanadu Social Insurance Organization", "aliases": "XNSO"},
]
RSS_FEEDS = [
    {"url": "http://localhost:9999/feeds/xn_feed_a_relevant.xml",   "publisher_name": "XN Ministry of HR",    "authority_name": "Ministry of Human Resources"},
    {"url": "http://localhost:9999/feeds/xn_feed_b_filtered.xml",   "publisher_name": "XN Mixed News Portal", "authority_name": None},
    {"url": "http://localhost:9999/feeds/xn_feed_c_duplicates.xml", "publisher_name": "XN Official Gazette",  "authority_name": None},
    {"url": "http://localhost:9999/feeds/xn_feed_d_repeated.xml",   "publisher_name": "XNSO Official Feed",   "authority_name": "Xanadu Social Insurance Organization"},
]

def reset_and_seed():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    conn = get_connection(TEST_DB_PATH)
    create_schema_if_needed(conn)
    conn.execute(
        "INSERT INTO profiles(country_code, lob, name, language, active) VALUES(?,?,?,?,?)",
        ("XN", "HCM", "Test Country HCM", "en", 1)
    )
    conn.commit()
    pid = conn.execute("SELECT id FROM profiles WHERE country_code='XN' AND lob='HCM'").fetchone()[0]
    auth_ids = {}
    for a in AUTHORITIES:
        auth_ids[a["name"]] = create_authority(conn, pid, a["name"], a["aliases"])
    for f in RSS_FEEDS:
        aid = auth_ids.get(f["authority_name"]) if f["authority_name"] else None
        upsert_rss_feed(conn, pid, f["url"], publisher_name=f["publisher_name"], authority_id=aid)
    for term in ["social insurance", "payroll", "employment contract", "maternity leave",
                 "pension fund", "minimum wage", "termination notice"]:
        conn.execute("INSERT OR IGNORE INTO glossary_terms(profile_id,term,lang) VALUES(?,?,?)", (pid, term, "en"))
    conn.commit()
    return conn, pid

if __name__ == "__main__":
    conn, pid = reset_and_seed()
    print(f"[OK] XN/HCM profile created (id={pid})")
    conn.close()
