"""
V3.91 Task 4C — Focused tests for reconcile_by_act_ref().

Tests the actual production function directly, using controlled SQLite in-memory data
and deterministic embedding fixtures.  No live AI Core calls.

Mandatory coverage (10 cases):
  1. First publication remains NEW
  2. Same-run reminder becomes REPEATED
  3. Cross-run reminder becomes REPEATED
  4. Distinct development under the same law remains NEW
  5. Repeat of the second distinct development becomes REPEATED
  6. Same-event coverage in another language becomes REPEATED
  7. Embedding failure does not cause false repetition
  8. Reconcile never changes dedup_status to UPDATE
  9. No occurrence-count threshold is required
 10. Reconciled statuses are persisted correctly through the production path
"""
import sys
import os
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.compare_news import reconcile_by_act_ref, _build_item_record

PROFILE_ID = 1

# ── Deterministic embedding vectors ─────────────────────────────────────────
# Each "event group" gets an orthogonal unit vector.
# Same group → cosine = 1.0 ≥ STRONG_SIM (0.78) → confirmed same event.
# Different groups → cosine = 0.0 < BORDERLINE_SIM (0.62) → different event.
_VEC_CONTRIBUTION = np.array([1., 0., 0., 0., 0.])  # contribution-rate event (Art 14)
_VEC_REPORTING    = np.array([0., 1., 0., 0., 0.])  # reporting-obligation event (Art 22)
_VEC_EXEMPTION    = np.array([0., 0., 1., 0., 0.])  # tax-exemption event
_VEC_UNRELATED    = np.array([0., 0., 0., 1., 0.])  # something else entirely


def _vec_for(text: str) -> np.ndarray:
    """Map marker strings in text to deterministic vectors."""
    if "GROUP_CONTRIBUTION" in text:
        return _VEC_CONTRIBUTION.copy()
    if "GROUP_REPORTING" in text:
        return _VEC_REPORTING.copy()
    if "GROUP_EXEMPTION" in text:
        return _VEC_EXEMPTION.copy()
    return _VEC_UNRELATED.copy()


def _mock_embeddings(texts):
    return [_vec_for(t) for t in texts]


# ── SQLite helpers ───────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    """Minimal in-memory news_items table with the columns reconcile queries."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE news_items (
            profile_id   INTEGER,
            law_id       INTEGER,
            act_ref      TEXT,
            repetition_count INTEGER DEFAULT 0,
            l2_summary   TEXT,
            cited_article TEXT,
            authority_id  INTEGER,
            published_at  TEXT,
            effective_date TEXT,
            title         TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at  TEXT NOT NULL,
            source_type   TEXT DEFAULT 'RSS',
            source_id     TEXT,
            url           TEXT,
            domain        TEXT,
            content       TEXT,
            hash_signature TEXT DEFAULT '',
            dedup_status  TEXT DEFAULT 'new',
            repetition_status TEXT DEFAULT 'new'
        )
    """)
    return conn


def _insert_baseline(conn, law_id=None, act_ref=None, l2_summary="",
                     cited_article=None, repetition_count=0, days_ago=1):
    """Insert a prior-run row that falls inside the reconcile baseline window."""
    ts = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
    conn.execute("""
        INSERT INTO news_items(profile_id, law_id, act_ref, l2_summary, cited_article,
                               repetition_count, first_seen_at, last_seen_at, title)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (PROFILE_ID, law_id, act_ref, l2_summary, cited_article,
          repetition_count, ts, ts, (l2_summary or "")[:40]))
    conn.commit()


def _make_item(law_id=None, act_ref=None, l2_summary="", cited_article=None):
    """Minimal pipeline item dict as Reconcile sees it (after L2 + Law Match)."""
    return {
        "profile_id": PROFILE_ID,
        "law_id": law_id,
        "act_ref": act_ref,
        "l2_summary": l2_summary,
        "cited_article": cited_article,
        "dedup_status": "new",
        "repetition_status": "new",
        "title": (l2_summary or "")[:40],
        "published_at": "2026-11-01T00:00:00",
        "effective_date": None,
        "authority_id": None,
        "repetition_count": 0,
        "source_type": "RSS",
        "source_id": f"src-{abs(hash(l2_summary)) % 100000}",
        "url": f"https://example.com/{abs(hash(l2_summary)) % 100000}",
        "content": l2_summary,
        "hash_signature": f"hash-{abs(hash(l2_summary)) % 100000}",
        "publisher": None,
        "authority_status": None,
        "law_primary": None,
        "law_secondary": None,
        "law_reference": None,
        "l2_fetched_at": None,
    }


def _run(items, conn, days=7):
    with patch("agents.embeddings_util.get_embeddings", side_effect=_mock_embeddings):
        return reconcile_by_act_ref(items, conn, PROFILE_ID, days=days)


# ── Test 1: First publication remains NEW ───────────────────────────────────
def test_first_publication_remains_new():
    """An article with no prior history is not touched by Reconcile."""
    conn = _make_db()  # empty baseline
    item = _make_item(law_id=1, l2_summary="GROUP_CONTRIBUTION rate change to 8.5%")

    result = _run([item], conn)

    assert item["repetition_status"] == "new", (
        f"First publication must stay NEW, got: {item['repetition_status']!r}"
    )
    assert result["reconciled"] == 0
    print("✅ Test 1 passed: first publication remains NEW")


# ── Test 2: Same-run reminder becomes REPEATED ──────────────────────────────
def test_same_run_reminder_becomes_repeated():
    """
    Two items arrive in the same run with the same law and semantically identical L2.
    The second (reminder) must become REPEATED.
    (Xanadu: Article A + Article B, same Royal Decree No. 18/2026.)
    """
    conn = _make_db()  # empty baseline

    item_a = _make_item(law_id=1, l2_summary="GROUP_CONTRIBUTION social insurance rate change")
    item_b = _make_item(law_id=1, l2_summary="GROUP_CONTRIBUTION countdown to rate change")
    # Make item_b later so it is processed after item_a
    item_b["published_at"] = "2026-11-02T00:00:00"

    result = _run([item_a, item_b], conn)

    assert item_a["repetition_status"] == "new", (
        f"First article must stay NEW, got: {item_a['repetition_status']!r}"
    )
    assert item_b["repetition_status"] == "repeated", (
        f"Same-run reminder must become REPEATED, got: {item_b['repetition_status']!r}"
    )
    assert result["reconciled"] == 1
    print("✅ Test 2 passed: same-run reminder becomes REPEATED")


# ── Test 3: Cross-run reminder becomes REPEATED ─────────────────────────────
def test_cross_run_reminder_becomes_repeated():
    """
    A reminder article arrives in a later run; the original is in the baseline.
    The reminder must become REPEATED without any occurrence-count check.
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION social insurance rate change",
                     days_ago=1)

    reminder = _make_item(law_id=1,
                          l2_summary="GROUP_CONTRIBUTION countdown to rate change")

    result = _run([reminder], conn)

    assert reminder["repetition_status"] == "repeated", (
        f"Cross-run reminder must become REPEATED, got: {reminder['repetition_status']!r}"
    )
    assert result["reconciled"] == 1
    print("✅ Test 3 passed: cross-run reminder becomes REPEATED")


# ── Test 4: Distinct development under same law remains NEW ─────────────────
def test_distinct_development_same_law_stays_new():
    """
    Article C covers a different legal development (reporting obligation) under the
    same Social Insurance Act as Article A (contribution rates). Must stay NEW despite
    sharing the law_id.
    (Xanadu: Article C has cited_article="Article 22", A has "Article 14".)
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION social insurance rate change",
                     cited_article="Article 14", days_ago=1)

    article_c = _make_item(law_id=1,
                           l2_summary="GROUP_REPORTING monthly electronic reporting obligation",
                           cited_article="Article 22")

    result = _run([article_c], conn)

    assert article_c["repetition_status"] == "new", (
        f"Distinct development must stay NEW, got: {article_c['repetition_status']!r}"
    )
    assert result["reconciled"] == 0
    print("✅ Test 4 passed: distinct development under same law stays NEW")


# ── Test 5: Repeat of second distinct development becomes REPEATED ───────────
def test_repeat_of_second_event_becomes_repeated():
    """
    Two distinct events under the same law_id are in the baseline.
    A repeat of the second event must match the second baseline candidate, not the first.
    This specifically tests the multi-candidate fix (bug 1).
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION social insurance rate change",
                     cited_article="Article 14", days_ago=2)
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_REPORTING monthly electronic reporting obligation",
                     cited_article="Article 22", days_ago=1)

    repeat_c = _make_item(law_id=1,
                          l2_summary="GROUP_REPORTING reporting obligation reminder",
                          cited_article="Article 22")

    result = _run([repeat_c], conn)

    assert repeat_c["repetition_status"] == "repeated", (
        f"Repeat of second distinct event must become REPEATED, got: {repeat_c['repetition_status']!r}"
    )
    assert result["reconciled"] == 1
    print("✅ Test 5 passed: repeat of second distinct development becomes REPEATED")


# ── Test 6: Same-event coverage in another language becomes REPEATED ─────────
def test_cross_language_same_event_becomes_repeated():
    """
    An Arabic article about the same contribution-rate change as an English baseline
    must become REPEATED; law_id match + semantic confirmation across languages.
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION employer contribution rate increased to 8.5%",
                     days_ago=1)

    arabic_article = _make_item(
        law_id=1,
        l2_summary="GROUP_CONTRIBUTION نسبة مساهمة صاحب العمل ارتفعت إلى 8.5%",
    )

    result = _run([arabic_article], conn)

    assert arabic_article["repetition_status"] == "repeated", (
        f"Cross-language same-event coverage must become REPEATED, "
        f"got: {arabic_article['repetition_status']!r}"
    )
    assert result["reconciled"] == 1
    print("✅ Test 6 passed: cross-language same-event coverage becomes REPEATED")


# ── Test 7: Embedding failure does not cause false repetition ────────────────
def test_embedding_failure_preserves_new():
    """
    When get_embeddings raises an exception (AI Core down), Reconcile must NOT
    flip the status to REPEATED — it must preserve NEW (rule 8).
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION social insurance rate change",
                     days_ago=1)

    item = _make_item(law_id=1,
                      l2_summary="GROUP_CONTRIBUTION another article about rates")

    def _fail(texts):
        raise RuntimeError("AI Core unavailable")

    with patch("agents.embeddings_util.get_embeddings", side_effect=_fail):
        result = reconcile_by_act_ref([item], conn, PROFILE_ID, days=7)

    assert item["repetition_status"] == "new", (
        f"Embedding failure must preserve NEW, got: {item['repetition_status']!r}"
    )
    assert result["reconciled"] == 0
    print("✅ Test 7 passed: embedding failure does not cause false repetition")


# ── Test 8: Reconcile never changes dedup_status ────────────────────────────
def test_reconcile_never_changes_dedup_status():
    """
    When an item is confirmed as REPEATED, dedup_status must remain 'new' throughout.
    Reconcile must never set dedup_status to 'update' or any other value.
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION social insurance rate change",
                     days_ago=1)

    item = _make_item(law_id=1,
                      l2_summary="GROUP_CONTRIBUTION rate change confirmed again")

    result = _run([item], conn)

    assert item["dedup_status"] == "new", (
        f"Reconcile must never change dedup_status; got: {item['dedup_status']!r}"
    )
    assert item["repetition_status"] == "repeated", "item must be REPEATED"
    assert result["reconciled"] == 1
    print("✅ Test 8 passed: dedup_status stays 'new' even when item becomes REPEATED")


# ── Test 9: No occurrence-count threshold ────────────────────────────────────
def test_no_occurrence_count_threshold():
    """
    Even the very first confirmed match (repetition_count=0 in baseline) must
    produce repetition_status='repeated' immediately — no threshold of 3 required.
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION social insurance rate change",
                     repetition_count=0,  # first-ever occurrence
                     days_ago=1)

    item = _make_item(law_id=1,
                      l2_summary="GROUP_CONTRIBUTION rate change follow-up")

    result = _run([item], conn)

    assert item["repetition_status"] == "repeated", (
        f"First confirmed match must produce REPEATED immediately "
        f"(no count threshold), got: {item['repetition_status']!r}"
    )
    assert result["reconciled"] == 1
    print("✅ Test 9 passed: no occurrence-count threshold — first match → REPEATED")


# ── Test 10: Reconciled status flows through _build_item_record ──────────────
def test_reconciled_status_persisted_via_build_item_record():
    """
    After Reconcile sets repetition_status='repeated' on an item, the production
    persistence helper _build_item_record() must include it in the serialized record.
    This validates the pipeline handoff without requiring a full DB upsert.
    """
    conn = _make_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_CONTRIBUTION social insurance rate change",
                     days_ago=1)

    item = _make_item(law_id=1,
                      l2_summary="GROUP_CONTRIBUTION rate change follow-up")
    item["source_type"] = "RSS"

    result = _run([item], conn)

    assert item["repetition_status"] == "repeated", "item must be REPEATED after reconcile"

    record = _build_item_record(item)
    assert record["repetition_status"] == "repeated", (
        f"_build_item_record must carry repetition_status='repeated', "
        f"got: {record['repetition_status']!r}"
    )
    assert record["dedup_status"] == "new", (
        f"_build_item_record must carry dedup_status='new', "
        f"got: {record['dedup_status']!r}"
    )
    assert result["reconciled"] == 1
    print("✅ Test 10 passed: reconciled status flows through _build_item_record correctly")


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_first_publication_remains_new,
        test_same_run_reminder_becomes_repeated,
        test_cross_run_reminder_becomes_repeated,
        test_distinct_development_same_law_stays_new,
        test_repeat_of_second_event_becomes_repeated,
        test_cross_language_same_event_becomes_repeated,
        test_embedding_failure_preserves_new,
        test_reconcile_never_changes_dedup_status,
        test_no_occurrence_count_threshold,
        test_reconciled_status_persisted_via_build_item_record,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            print(f"❌ {t.__name__} FAILED: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed:
        sys.exit(1)
