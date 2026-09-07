"""
prep_xanadu_demo.py — prepare the LIVE Xanadu (XN/HCM) profile in configurations/config.db
for the Legal Eagle v3 team demo.

This is the DEMO prep tool. It is NOT scripts/load_harness_run.py (that one imports harness
output into config.db for manual testing).

TWO MODES
---------
  (default) repeat-reset      — run before EACH re-demo:
                                reset ONLY Xanadu review/news data (runs, run_logs, news_items,
                                filtered_news, news_announcements), then RE-SEED the REPEATED
                                baseline. All configuration (glossary, authorities, email, ranking
                                signals, and any URL source you added live) is PRESERVED.

  --rebuild-config            — first-time full build: additionally (re)build the Xanadu config
                                from scratch (authorities, glossary, email, ranking signals,
                                date_scope), THEN reset review data + seed baseline. Idempotent.

SAFETY
------
Both modes resolve the target profile by (country_code='XN', lob='HCM', name='Xanadu HCM') and
REFUSE to run if it is missing or does not match. Every mutation is scoped to that resolved
profile_id. No other profile's data or configuration is ever touched — the script verifies this
by snapshotting every other profile's row counts before and after.

The Xanadu gov site is a LOCAL fixture added as a URL source (full-body scraping) — not an RSS
feed. By default the URL source is added live in the runbook (Run 1); pass --url-source to pre-seed
it here (un-simulated, so the full-body scraper is used). Either way it is preserved across
repeat-resets.

Usage:
  python3 scripts/prep_xanadu_demo.py                     # repeat-reset (keep config)
  python3 scripts/prep_xanadu_demo.py --rebuild-config    # first-time full build
  python3 scripts/prep_xanadu_demo.py --rebuild-config --email you@example.com
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import (
    get_connection,
    create_authority,
    add_glossary_term,
    upsert_email_receiver_with_lang,
    upsert_news_item,
    upsert_url_source,
)
from agents.text_utils import hash_signature

LIVE_DB = os.path.join(os.path.dirname(__file__), "..", "configurations", "config.db")

# --- Expected Xanadu demo profile identity (the safety guard) ---
EXPECT_COUNTRY = "XN"
EXPECT_LOB = "HCM"
EXPECT_NAME = "Xanadu HCM"
DEMO_DATE_SCOPE = "last_30_days"

# --- Config seeded by --rebuild-config ---
AUTHORITIES = [
    {"name": "Ministry of Human Resources", "aliases": "MoHR"},
    {"name": "Xanadu Social Insurance Organization", "aliases": "XNSO"},
]
GLOSSARY_TERMS = [
    "social insurance", "contribution rate", "pension fund", "maternity leave",
    "employment contract", "payroll", "health insurance", "termination notice", "labour law",
]
# Bootstrap Tier 1 ranking signals (mirror tests/reset_and_seed.py). "contribution rate" and
# "social insurance" at min_rank 3 give the flagship its rank-3 base; the REPEATED +1 elevation
# in news_ranker then lifts it to 4.
RANKING_SIGNALS = [
    {"signal_type": "keyword", "pattern": "maternity leave",     "min_rank": 4, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "termination notice",  "min_rank": 4, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "employment law",      "min_rank": 4, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "pension fund",        "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "social insurance",    "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "health insurance",    "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "contribution rate",   "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "payroll compliance",  "min_rank": 3, "confidence": 1.0, "created_from": "bootstrap"},
    {"signal_type": "keyword", "pattern": "employment contract", "min_rank": 2, "confidence": 1.0, "created_from": "bootstrap"},
]

# --- The REPEATED baseline (the "prior announcement" of the flagship change) ---
# Different wording + different guid/url from the live gov-site article, so the pipeline matches
# them SEMANTICALLY (cosine 0.72–0.80), not by exact key. repetition_count=3 makes the live item
# tag REPEATED and the ranker elevate it. Keep the shared phrase "social insurance contribution
# rate" but let the body diverge so cosine stays below the 0.80 duplicate threshold.
BASELINE_ITEM = {
    "source_type": "RSS",
    "source_id": "xn-mohr-si-rate-reform-2026-08",
    "url": "https://xanadu-mohr.example.gov.xn/news/social-insurance-contribution-rate-reform",
    "title": "New law changes the social insurance contribution rate",
    "content": (
        "The Ministry of Human Resources has enacted a reform to the social insurance "
        "contribution rate under the amended Social Insurance Act. The revised rate applies to "
        "all covered employees and replaces the previous schedule. Employers will be required to "
        "apply the new social insurance contribution rate once it enters into force."
    ),
    "published_at": "2026-08-18",
    "dedup_status": "new",
    "repetition_count": 3,
    "topic_label": '["Social Insurance"]',
}


def resolve_xanadu_profile(conn):
    """Resolve the Xanadu demo profile, or abort. Never falls back to another profile."""
    row = conn.execute(
        "SELECT id, country_code, lob, name FROM profiles WHERE country_code=? AND lob=?",
        (EXPECT_COUNTRY, EXPECT_LOB),
    ).fetchone()
    if not row:
        sys.exit(
            f"ABORT: no {EXPECT_COUNTRY}/{EXPECT_LOB} profile found in config.db. "
            "Refusing to run — this script only operates on the Xanadu demo profile."
        )
    if (row["name"] or "") != EXPECT_NAME:
        sys.exit(
            f"ABORT: {EXPECT_COUNTRY}/{EXPECT_LOB} profile name is '{row['name']}', "
            f"expected '{EXPECT_NAME}'. Refusing to run to avoid touching the wrong profile."
        )
    return int(row["id"])


def snapshot_other_profiles(conn, pid):
    """Row counts for every OTHER profile's data, to prove non-interference."""
    snap = {}
    others = [r["id"] for r in conn.execute("SELECT id FROM profiles WHERE id<>?", (pid,))]
    for oid in others:
        snap[oid] = {
            "news_items": conn.execute("SELECT COUNT(*) FROM news_items WHERE profile_id=?", (oid,)).fetchone()[0],
            "runs": conn.execute("SELECT COUNT(*) FROM runs WHERE profile_id=?", (oid,)).fetchone()[0],
            "glossary_terms": conn.execute("SELECT COUNT(*) FROM glossary_terms WHERE profile_id=?", (oid,)).fetchone()[0],
            "rss_feeds": conn.execute("SELECT COUNT(*) FROM rss_feeds WHERE profile_id=?", (oid,)).fetchone()[0],
            "authorities": conn.execute("SELECT COUNT(*) FROM authorities WHERE profile_id=?", (oid,)).fetchone()[0],
        }
    return snap


def reset_review_data(conn, pid):
    """Delete ONLY the Xanadu profile's run/review data. Config is untouched."""
    run_ids = [r[0] for r in conn.execute("SELECT id FROM runs WHERE profile_id=?", (pid,)).fetchall()]
    if run_ids:
        ph = ",".join("?" * len(run_ids))
        conn.execute(f"DELETE FROM news_announcements WHERE run_id IN ({ph})", run_ids)
        conn.execute(f"DELETE FROM run_logs WHERE run_id IN ({ph})", run_ids)
    conn.execute("DELETE FROM news_items WHERE profile_id=?", (pid,))
    conn.execute("DELETE FROM filtered_news WHERE profile_id=?", (pid,))
    conn.execute("DELETE FROM runs WHERE profile_id=?", (pid,))
    conn.commit()


def rebuild_config(conn, pid, email=None):
    """First-time full build of the Xanadu config (idempotent). URL source is NOT added here (use --url-source or add live)."""
    # Profile-level settings for the demo
    conn.execute(
        "UPDATE profiles SET date_scope=?, language='en', active=1 WHERE id=?",
        (DEMO_DATE_SCOPE, pid),
    )
    # Clear config we own so re-running is idempotent (create_authority is a plain INSERT)
    conn.execute("DELETE FROM authorities WHERE profile_id=?", (pid,))
    conn.execute("DELETE FROM glossary_terms WHERE profile_id=?", (pid,))
    conn.execute("DELETE FROM ranking_signals WHERE profile_id=?", (pid,))
    conn.commit()

    for a in AUTHORITIES:
        create_authority(conn, pid, a["name"], a["aliases"])
    for term in GLOSSARY_TERMS:
        add_glossary_term(conn, pid, term, lang="en")
    for s in RANKING_SIGNALS:
        conn.execute(
            "INSERT INTO ranking_signals(profile_id, signal_type, pattern, min_rank, confidence, created_from) VALUES(?,?,?,?,?,?)",
            (pid, s["signal_type"], s["pattern"], s["min_rank"], s["confidence"], s["created_from"]),
        )
    if email:
        upsert_email_receiver_with_lang(conn, pid, email, translation_lang="en")
    conn.commit()


def seed_baseline(conn, pid):
    """Insert the single REPEATED baseline item (the prior announcement of the flagship change)."""
    rec = dict(BASELINE_ITEM)
    rec["hash_signature"] = hash_signature(rec["title"], rec["content"])
    upsert_news_item(conn, pid, rec)
    conn.commit()


def normalize_url_sources_full_body(conn, pid):
    """Force any Xanadu URL source onto the FULL-BODY legacy scraper.

    Runtime routing sends a source to the snippet-only scraper (`scrape_url_source_with_config`)
    only when `simulation_status='success'` AND `container_selector` is set. Clearing those columns
    routes it to `run_unified_sources`, which follows each article link and extracts the full body
    — required for the flagship's semantic REPEATED match. `read_more_label` + `sample_link` help
    the legacy path discover detail links.
    """
    rows = conn.execute("SELECT url FROM url_sources WHERE profile_id=?", (pid,)).fetchall()
    # Resolve the Ministry authority id so URL-scraped items attribute to it (publisher + authority),
    # giving a "Ministry of Human Resources · URL" source label and grouping (not "Other Topics").
    arow = conn.execute(
        "SELECT id FROM authorities WHERE profile_id=? AND name=?",
        (pid, "Ministry of Human Resources"),
    ).fetchone()
    mohr_id = arow[0] if arow else None
    for r in rows:
        conn.execute(
            """UPDATE url_sources SET simulation_status='pending', container_selector=NULL,
               field_selectors=NULL, read_more_selector=NULL, pagination_type=NULL,
               pagination_selector=NULL, sample_link=NULL, read_more_label='Read more',
               publisher_name=?, authority_id=?
               WHERE profile_id=? AND url=?""",
            ("Ministry of Human Resources", mohr_id, pid, r["url"]),
        )
    conn.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Prepare the Xanadu demo profile in config.db.")
    ap.add_argument("--rebuild-config", action="store_true",
                    help="First-time full build: (re)build Xanadu config, then reset + seed.")
    ap.add_argument("--email", default=None,
                    help="Email receiver to seed (only used with --rebuild-config).")
    ap.add_argument("--url-source", default=None,
                    help="Optional: pre-seed the local Xanadu gov site as a URL source "
                         "(e.g. http://127.0.0.1:8000/). Left un-simulated (no container_selector) "
                         "so the full-body scraper is used. Otherwise add it live in the runbook.")
    args = ap.parse_args()

    if not os.path.exists(LIVE_DB):
        sys.exit(f"ABORT: {LIVE_DB} not found.")

    conn = get_connection(LIVE_DB)
    pid = resolve_xanadu_profile(conn)
    print(f"[OK]   Target profile resolved: {EXPECT_COUNTRY}/{EXPECT_LOB} '{EXPECT_NAME}' (id={pid})")

    before = snapshot_other_profiles(conn, pid)

    if args.rebuild_config:
        rebuild_config(conn, pid, email=args.email)
        print(f"[OK]   Config rebuilt: {len(AUTHORITIES)} authorities, {len(GLOSSARY_TERMS)} glossary terms, "
              f"{len(RANKING_SIGNALS)} ranking signals"
              + (f", email={args.email}" if args.email else " (no email — add in UI or pass --email)"))
    else:
        print("[OK]   Repeat-reset mode: configuration preserved (glossary, authorities, email, feeds, signals)")

    reset_review_data(conn, pid)
    print("[OK]   Xanadu review data reset (runs, run_logs, news_items, filtered_news, announcements)")

    seed_baseline(conn, pid)
    print(f"[OK]   Seeded REPEATED baseline: \"{BASELINE_ITEM['title']}\" (repetition_count={BASELINE_ITEM['repetition_count']})")

    # Optional: pre-seed the local gov site as a URL source (full-body path — no simulator selectors)
    if args.url_source:
        upsert_url_source(conn, pid, args.url_source, mode="auto")
        conn.commit()
        print(f"[OK]   Seeded URL source (un-simulated, full-body path): {args.url_source}")

    # Force any existing Xanadu URL source onto the full-body scraper (undo a prior Simulate run)
    n_url = normalize_url_sources_full_body(conn, pid)
    if n_url:
        print(f"[OK]   Normalized {n_url} URL source(s) to full-body path (cleared simulator selectors)")

    # Prove no other profile was touched
    after = snapshot_other_profiles(conn, pid)
    if before != after:
        conn.rollback()
        sys.exit(f"ABORT: other-profile row counts changed!\n  before={before}\n  after ={after}")
    print(f"[OK]   Verified {len(after)} other profile(s) untouched")

    urls = conn.execute("SELECT COUNT(*) FROM url_sources WHERE profile_id=?", (pid,)).fetchone()[0]
    print(f"[INFO] Xanadu URL sources currently configured: {urls} "
          "(add the local gov-site URL live in Run 1 if 0; do NOT run the Source Simulator)")
    conn.close()
    print("[DONE] Xanadu demo profile is ready.")


if __name__ == "__main__":
    main()
