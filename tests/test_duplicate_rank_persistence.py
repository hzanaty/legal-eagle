"""
V3.91 Task 4B — Duplicate rank persistence.

## V3.92 corrective patch history

Three tests in this file were written under the V3.91 Task 4B assumption that
a duplicate re-fetch should unconditionally overwrite the canonical record's
significance_rank with 0.  That assumption was wrong:

  Wrong assumption (V3.91 Task 4B):
    A duplicate re-fetch of an article that was previously ranked MUST reset its
    rank to 0.  The COALESCE(?, significance_rank) pattern with a pre-set 0 value
    would "win" over the stored rank.

  Correct behavior (V3.92 corrective patch):
    A duplicate observation is only a re-fetch from the source.  It must NEVER
    overwrite the canonical analysis, rank, RRR history, human decision, or email
    state.  Only last_seen_at may advance.  The V3.92 fix removes the pre-set-0
    block and replaces it with an early-return that only touches last_seen_at.

The three tests that expected rank=0 after a duplicate re-fetch have been
updated to reflect the correct V3.92 behavior.  Comments on each test explain
why the old expectation was wrong.

Uses an in-memory SQLite database — no mocking of persistence.
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
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Corrected: previously-ranked article PRESERVES rank on duplicate re-fetch
# ---------------------------------------------------------------------------
def test_previously_ranked_article_preserves_rank_when_duplicate():
    """
    V3.92 CORRECTED BEHAVIOR (was: test_previously_ranked_article_resets_to_zero_when_duplicate).

    Why the old expectation was wrong:
      A duplicate re-fetch is a technical signal — the source's RSS feed served
      the same article again.  It is NOT a new business event.  The canonical
      article was already fully analyzed and ranked (rank=4 here).  Overwriting
      its rank with 0 silently destroyed completed legal analysis and could
      suppress email delivery on a rank-eligible article.

    V3.92 correct behavior:
      When upsert_news_item finds an existing row AND the incoming observation
      has dedup_status='duplicate', it performs only an UPDATE SET last_seen_at
      and returns immediately — leaving all business state intact.

    Step 1: Persist article as NEW with rank=4.
    Step 2: Re-collect the same article as DUPLICATE.
    Step 3: DB record must PRESERVE rank=4, rank_tier='tier2', email_eligible=1.
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

    # --- Step 2: Re-collect as DUPLICATE ---
    dup_item = _item(
        "Payroll Law Update",
        url,
        dedup_status="duplicate",
        significance_rank=None,
        rank_tier=None,
        email_eligible=0,
    )
    upsert_news_item(conn, 1, dup_item)

    # --- Step 3: Verify canonical state is preserved ---
    stored = _fetch(conn, url)
    assert stored["dedup_status"] == "new", (
        f"Canonical dedup_status must stay 'new'; got '{stored['dedup_status']}'"
    )
    assert stored["significance_rank"] == 4, (
        f"Canonical rank must stay 4; got {stored['significance_rank']}"
    )
    assert stored["rank_tier"] == "tier2", (
        f"Canonical rank_tier must stay 'tier2'; got '{stored['rank_tier']}'"
    )
    assert stored["email_eligible"] == 1, (
        f"Canonical email_eligible must stay 1; got {stored['email_eligible']}"
    )

    conn.close()


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


# ---------------------------------------------------------------------------
# Corrected: orphan duplicate (no prior canonical row) produces NO row
# ---------------------------------------------------------------------------
def test_fresh_duplicate_without_prior_row_creates_no_row():
    """
    V3.92 CORRECTED BEHAVIOR (was: test_fresh_duplicate_insert_has_rank_zero).

    Why the old expectation was wrong:
      Inserting a rank-0 'duplicate' row for an article that has never been
      analyzed is meaningless — there is no canonical record to reference it,
      no ranking, no legal analysis.  The row would silently block any future
      genuine occurrence of the same article (COALESCE would preserve the
      placeholder rank=0).

    V3.92 correct behavior:
      When no existing canonical row is found AND the incoming observation is a
      duplicate, upsert_news_item returns -1 without inserting any row.  The
      first genuine NEW occurrence will create the canonical record normally.
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
    result = upsert_news_item(conn, 1, dup_item)

    assert result == -1, f"Orphan duplicate must return -1; got {result}"

    row = _fetch(conn, url)
    assert row is None, f"No row must be created for an orphan duplicate; found: {row}"

    conn.close()


# ---------------------------------------------------------------------------
# Corrected: news review query sees preserved rank after duplicate re-fetch
# ---------------------------------------------------------------------------
def test_news_review_query_returns_original_rank_after_duplicate():
    """
    V3.92 CORRECTED BEHAVIOR (was: test_news_review_query_returns_rank_zero_for_duplicate).

    Why the old expectation was wrong:
      The review page showing rank=0 after a source rerun for a rank-5 article
      is wrong — it was displaying destroyed analysis.  The PM would see a
      rank-5 article demoted to noise by a routine source refresh, with no
      ability to recover without a full re-run.

    V3.92 correct behavior:
      After a duplicate re-fetch, the review query (SELECT from news_items)
      must return the original rank=5 and rank_tier='tier1'.
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
    assert row["significance_rank"] == 5, (
        f"Review query must return original rank=5; got {row['significance_rank']}"
    )
    assert row["rank_tier"] == "tier1", (
        f"Review query must return original rank_tier='tier1'; got '{row['rank_tier']}'"
    )
    assert row["email_eligible"] == 1, (
        f"Review query must return email_eligible=1; got {row['email_eligible']}"
    )
    assert row["dedup_status"] == "new", (
        f"Review query must return canonical dedup_status='new'; got '{row['dedup_status']}'"
    )

    conn.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_previously_ranked_article_preserves_rank_when_duplicate,
        test_new_article_retains_rank,
        test_fresh_duplicate_without_prior_row_creates_no_row,
        test_news_review_query_returns_original_rank_after_duplicate,
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
