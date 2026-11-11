"""
V3.91 Task 4B — Blocking Correction: DUPLICATE rank persistence.

Business rule: every article that reaches the DB as DUPLICATE must have
significance_rank=0, rank_tier='duplicate', and email_eligible=0,
even if the same article was previously stored with a non-zero rank.

Uses a temporary in-memory SQLite database — no mocking of persistence.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import create_schema_if_needed, upsert_news_item


def _fresh_conn():
    """In-memory SQLite with the full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_if_needed(conn)
    return conn


def _item(title, url, dedup_status="new", significance_rank=None,
          rank_tier=None, email_eligible=0, profile_id=1):
    return {
        "profile_id": profile_id,
        "source_type": "RSS",
        "source_id": f"sid-{abs(hash(url)) % 100000}",
        "url": url,
        "title": title,
        "content": f"Content for {title}",
        # hash_signature is NOT NULL in schema; use a stable hash per URL
        "hash_signature": f"hash-{abs(hash(url + title)) % 1000000:06d}",
        "dedup_status": dedup_status,
        "repetition_status": dedup_status,
        "significance_rank": significance_rank,
        "rank_tier": rank_tier,
        "email_eligible": email_eligible,
    }


def _fetch(conn, url, profile_id=1):
    row = conn.execute(
        "SELECT significance_rank, rank_tier, email_eligible, dedup_status "
        "FROM news_items WHERE url=? AND profile_id=?",
        (url, profile_id),
    ).fetchone()
    assert row is not None, f"No row found for url={url}"
    return dict(row)


# ---------------------------------------------------------------------------
# Mandatory regression test
# ---------------------------------------------------------------------------
def test_previously_ranked_article_resets_to_zero_when_duplicate():
    """
    Step 1: Persist article as NEW with rank=4.
    Step 2: Re-collect the same article as DUPLICATE (rank not set).
    Step 3: DB record must show rank=0, rank_tier='duplicate', email_eligible=0.
    """
    conn = _fresh_conn()
    url = "https://example.com/law-article"

    # --- Step 1: Insert as NEW with rank 4 ---
    ranked_item = _item(
        "Payroll Law Update",
        url,
        dedup_status="new",
        significance_rank=4,
        rank_tier="tier2",
        email_eligible=1,
    )
    upsert_news_item(conn, 1, ranked_item)

    stored = _fetch(conn, url)
    assert stored["significance_rank"] == 4,       "Precondition: rank must be 4 after first insert"
    assert stored["rank_tier"] == "tier2",          "Precondition: rank_tier must be tier2"
    assert stored["email_eligible"] == 1,           "Precondition: email_eligible must be 1"

    # --- Step 2: Re-collect as DUPLICATE (rank fields not set — bypassed ranking) ---
    dup_item = _item(
        "Payroll Law Update",
        url,
        dedup_status="duplicate",
        significance_rank=None,   # bypassed ranking → not set
        rank_tier=None,           # bypassed ranking → not set
        email_eligible=0,
    )
    upsert_news_item(conn, 1, dup_item)

    # --- Step 3: Verify DB enforces business rule ---
    stored = _fetch(conn, url)
    assert stored["dedup_status"] == "duplicate", (
        f"Expected dedup_status='duplicate', got '{stored['dedup_status']}'"
    )
    assert stored["significance_rank"] == 0, (
        f"DUPLICATE article retained rank {stored['significance_rank']} — must be 0"
    )
    assert stored["rank_tier"] == "duplicate", (
        f"DUPLICATE article has rank_tier='{stored['rank_tier']}' — must be 'duplicate'"
    )
    assert stored["email_eligible"] == 0, (
        f"DUPLICATE article has email_eligible={stored['email_eligible']} — must be 0"
    )

    conn.close()
    print("✅ Mandatory regression passed: previously-ranked article reset to rank=0 on DUPLICATE upsert")


# ---------------------------------------------------------------------------
# NEW article is unaffected
# ---------------------------------------------------------------------------
def test_new_article_retains_rank():
    """
    A separate NEW article with a non-zero rank must not be affected by the fix.
    """
    conn = _fresh_conn()
    url_new = "https://example.com/unrelated-new"

    new_item = _item(
        "Unrelated new regulation",
        url_new,
        dedup_status="new",
        significance_rank=3,
        rank_tier="tier1",
        email_eligible=1,
    )
    upsert_news_item(conn, 1, new_item)

    stored = _fetch(conn, url_new)
    assert stored["significance_rank"] == 3,   "NEW article must retain its rank"
    assert stored["rank_tier"] == "tier1",      "NEW article must retain its rank_tier"
    assert stored["email_eligible"] == 1,       "NEW article must retain email_eligible=1"
    assert stored["dedup_status"] == "new",     "NEW article must retain dedup_status='new'"

    conn.close()
    print("✅ NEW article retains rank=3, rank_tier='tier1', email_eligible=1")


# ---------------------------------------------------------------------------
# DUPLICATE insert (first time, no prior record)
# ---------------------------------------------------------------------------
def test_fresh_duplicate_insert_has_rank_zero():
    """
    An article inserted for the first time as DUPLICATE must also have rank=0.
    """
    conn = _fresh_conn()
    url = "https://example.com/fresh-dup"

    dup_item = _item(
        "Fresh duplicate article",
        url,
        dedup_status="duplicate",
        significance_rank=None,
        rank_tier=None,
        email_eligible=0,
    )
    upsert_news_item(conn, 1, dup_item)

    stored = _fetch(conn, url)
    assert stored["significance_rank"] == 0,         "Fresh DUPLICATE insert must have rank=0"
    assert stored["rank_tier"] == "duplicate",        "Fresh DUPLICATE insert must have rank_tier='duplicate'"
    assert stored["email_eligible"] == 0,             "Fresh DUPLICATE insert must have email_eligible=0"

    conn.close()
    print("✅ Fresh DUPLICATE insert has rank=0, rank_tier='duplicate', email_eligible=0")


# ---------------------------------------------------------------------------
# News Review query returns correct rank for DUPLICATE records
# ---------------------------------------------------------------------------
def test_news_review_query_returns_rank_zero_for_duplicate():
    """
    Simulate the News Review SELECT (list_all_news_for_review path).
    After a ranked article is re-stored as DUPLICATE, the significance_rank
    returned by the review query must be 0.
    """
    conn = _fresh_conn()
    url = "https://example.com/review-check"

    # Insert as ranked NEW
    upsert_news_item(conn, 1, _item("Review article", url,
                                    dedup_status="new",
                                    significance_rank=5, rank_tier="tier1", email_eligible=1))
    # Re-upsert as DUPLICATE
    upsert_news_item(conn, 1, _item("Review article", url,
                                    dedup_status="duplicate",
                                    significance_rank=None, rank_tier=None))

    row = conn.execute(
        "SELECT significance_rank, rank_tier, email_eligible, dedup_status "
        "FROM news_items WHERE url=? AND profile_id=1",
        (url,),
    ).fetchone()
    assert row is not None
    assert row["significance_rank"] == 0,    f"News Review query returned rank={row['significance_rank']}"
    assert row["rank_tier"] == "duplicate",   f"News Review query returned rank_tier={row['rank_tier']}"
    assert row["email_eligible"] == 0,        f"News Review query returned email_eligible={row['email_eligible']}"

    conn.close()
    print("✅ News Review query returns rank=0 for DUPLICATE record")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_previously_ranked_article_resets_to_zero_when_duplicate,
        test_new_article_retains_rank,
        test_fresh_duplicate_insert_has_rank_zero,
        test_news_review_query_returns_rank_zero_for_duplicate,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            print(f"❌ {t.__name__} FAILED: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed:
        sys.exit(1)
