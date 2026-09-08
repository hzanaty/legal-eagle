import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from configurations.db import (
    get_connection, create_schema_if_needed, create_authority,
    upsert_rss_feed, upsert_news_item,
)

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test.db")
BASELINE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "seed", "baseline.json")

# 30-day lookback: window includes the Aug-15 repeated items (R1-R3) but excludes
# the Aug-3 minimum-wage item (B4), which must be dropped by the age filter.
PROFILE_DATE_SCOPE = "last_30_days"

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

# Bootstrap Tier 1 ranking signals for the XN/HCM profile (v3.2).
# These deterministic keyword rules let the harness assert ranks without AI.
RANKING_SIGNALS = [
    {"signal_type": "keyword", "pattern": "maternity leave",        "min_rank": 4, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "termination notice",     "min_rank": 4, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "employment law",         "min_rank": 4, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "pension fund",           "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "social insurance",       "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "health insurance",       "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "contribution rate",      "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "payroll compliance",     "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "employment contract",    "min_rank": 2, "confidence": 1.0, "created_from": "bootstrap"},
    # v3.5: "workplace safety" is NOT in the seeded glossary, so an item matching it
    # ranks >= 3 with topic_label ["General"] → a deterministic glossary gap.
    # min_rank=4 keeps Tier 1 authoritative (>=4 short-circuits the AI Tier 2), so the
    # A5 gap item stays fully deterministic in the harness (no AI cache dependency).
    {"signal_type": "keyword", "pattern": "workplace safety",        "min_rank": 4, "confidence": 1.0, "created_from": "bootstrap"},
]


def _inject_baseline(conn, pid):
    """Load historical baseline rows into news_items so dedup has prior context
    (C1 exact-dup vs S2, C2 near-dup vs S3, R1-R3 vs S4-S6).
    S4-S6 carry repetition_count=3 to exercise the REPEATED tag logic (v3.2)."""
    try:
        rows = json.loads(open(BASELINE_PATH, encoding="utf-8").read())
    except Exception as e:
        print(f"⚠️ Could not load baseline.json: {e}")
        return 0
    # v3.3: topic_label pre-assigned for seed items (glossary match simulation)
    _seed_topic_labels = {
        "S1": '["Labour Law"]',
        "S2": '["Social Insurance"]',
        "S3": '["Social Insurance"]',
        "S4": '["Social Insurance"]',
        "S5": '["Payroll"]',
        "S6": '["Employment Contracts"]',
    }
    n = 0
    for r in rows:
        rec = {
            "source_type": r.get("source_type", "RSS"),
            "source_id": r.get("guid"),
            "url": r.get("url"),
            "domain": None,
            "title": r.get("title"),
            "content": r.get("content"),
            "published_at": None,
            "hash_signature": r.get("hash_signature"),
            "dedup_status": "new",
            "repetition_count": r.get("repetition_count"),
            "topic_label": _seed_topic_labels.get(r.get("id_label", ""), None),
        }
        upsert_news_item(conn, pid, rec)
        n += 1
    return n


def reset_and_seed():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    conn = get_connection(TEST_DB_PATH)
    create_schema_if_needed(conn)
    conn.execute(
        "INSERT INTO profiles(country_code, lob, name, language, active, date_scope) VALUES(?,?,?,?,?,?)",
        ("XN", "HCM", "Test Country HCM", "en", 1, PROFILE_DATE_SCOPE)
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
                 "pension fund", "minimum wage", "termination notice",
                 "health insurance", "labour law"]:
        conn.execute("INSERT OR IGNORE INTO glossary_terms(profile_id,term,lang) VALUES(?,?,?)", (pid, term, "en"))
    # v3.2: seed bootstrap Tier 1 ranking signals
    for s in RANKING_SIGNALS:
        conn.execute(
            "INSERT INTO ranking_signals(profile_id, signal_type, pattern, min_rank, confidence, created_from) VALUES(?,?,?,?,?,?)",
            (pid, s["signal_type"], s["pattern"], s["min_rank"], s["confidence"], s["created_from"])
        )
    # v3.13: LOKA topic + RCM reference titles (ground announcement title generation)
    conn.execute("INSERT INTO settings(profile_id, key, value) VALUES(?,?,?)", (pid, "loka_topic", "HCM"))
    conn.execute("INSERT INTO settings(profile_id, key, value) VALUES(?,?,?)",
                 (pid, "rcm_url", "https://app.main.regulatory-change-manager.cloud.sap/index.html#/detail/XN-DEMO"))
    for jira, title, eff in [
        ("XN-5001", "Social Insurance Contribution Rate Update Q1 2027", "2027-01-01"),
        ("XN-5002", "Employment Law Amendment: Termination Notice Period", "2027-01-01"),
        ("XN-5003", "Statutory Maternity Leave Extension to 16 Weeks", "2027-01-01"),
    ]:
        conn.execute(
            "INSERT INTO rcm_reference_titles(profile_id, jira_key, regulation_title, country, effective_date) VALUES(?,?,?,?,?)",
            (pid, jira, title, "Xanadu", eff),
        )
    conn.commit()
    n = _inject_baseline(conn, pid)
    conn.commit()
    print(f"[OK]  Injected {n} baseline items into news_items")
    return conn, pid

if __name__ == "__main__":
    conn, pid = reset_and_seed()
    print(f"[OK] XN/HCM profile created (id={pid})")
    conn.close()
