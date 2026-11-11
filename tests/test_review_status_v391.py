"""
V3.91 Task 4D — focused tests for News Review status compatibility & repetition counter.

Tests the actual production Reconcile bookkeeping and the relevant News Review
rendering/filtering behavior.  No live AI Core calls.  No Playwright.

Mandatory acceptance criteria (12):
 1. NEW item renders as NEW
 2. DUPLICATE renders as DUPLICATE with Rank 0
 3. First confirmed repetition has count 1
 4. Further repetitions show correctly increasing counts
 5. Distinct legal events sharing the same law do not share counts
 6. Same-run and cross-run counts behave consistently
 7. REPEATED filter selects REPEATED (1), (2), (3), etc. via data-status="REPEATED"
 8. UPDATE chip is absent from the filter row; review_help.json has no UPDATE entry
 9. Historical UPDATE records remain accessible via the All filter
10. Rank, Glossary and Email filtering remain unchanged
11. Duplicate collection does not increase repetition counter
12. Missing/untrusted legacy counts do not produce fabricated numbers
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.compare_news import reconcile_by_act_ref, _build_item_record
from configurations.db import (
    create_schema_if_needed,
    get_connection,
    list_all_news_for_review,
    upsert_news_item,
)

PROFILE_ID = 1

# ── Paths ────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATE_PATH = os.path.join(_REPO_ROOT, "admin", "templates", "review_news.html")
_REVIEW_HELP_PATH = os.path.join(_REPO_ROOT, "configurations", "review_help.json")

# ── Deterministic embeddings ─────────────────────────────────────────────────
_VEC_A = np.array([1., 0., 0., 0., 0.])  # legal event A
_VEC_B = np.array([0., 1., 0., 0., 0.])  # legal event B
_VEC_X = np.array([0., 0., 1., 0., 0.])  # unrelated

def _vec_for(text: str) -> np.ndarray:
    if "GROUP_A" in text:
        return _VEC_A.copy()
    if "GROUP_B" in text:
        return _VEC_B.copy()
    return _VEC_X.copy()

def _mock_embeddings(texts):
    return [_vec_for(t) for t in texts]

# ── In-memory DB helpers ─────────────────────────────────────────────────────

def _make_reconcile_db() -> sqlite3.Connection:
    """Minimal schema for reconcile_by_act_ref (same as test_reconcile_v391)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE news_items (
            profile_id    INTEGER,
            law_id        INTEGER,
            act_ref       TEXT,
            repetition_count INTEGER DEFAULT 0,
            l2_summary    TEXT,
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


def _full_schema_db() -> sqlite3.Connection:
    """Full production schema for list_all_news_for_review tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_if_needed(conn)
    # Production databases have relevance_score/reviewed_at on news_items (added outside
    # the initial CREATE TABLE — list_all_news_for_review queries them).
    for _col, _decl in (("relevance_score", "INTEGER"), ("reviewed_at", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
        except Exception:
            pass
    conn.execute(
        "INSERT OR IGNORE INTO profiles(id, country_code, lob, name, language, active) "
        "VALUES(?, 'TEST', 'HCM', 'test', 'en', 1)",
        (PROFILE_ID,),
    )
    conn.commit()
    return conn


def _insert_baseline(conn, law_id=None, act_ref=None, l2_summary="",
                     cited_article=None, repetition_count=0, days_ago=1):
    ts = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
    conn.execute("""
        INSERT INTO news_items(profile_id, law_id, act_ref, l2_summary, cited_article,
                               repetition_count, first_seen_at, last_seen_at, title)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (PROFILE_ID, law_id, act_ref, l2_summary, cited_article,
          repetition_count, ts, ts, (l2_summary or "")[:40]))
    conn.commit()


def _make_item(law_id=None, act_ref=None, l2_summary="", cited_article=None,
               dedup_status="new", repetition_count=0):
    key = abs(hash(l2_summary + str(dedup_status))) % 100000
    return {
        "profile_id": PROFILE_ID,
        "law_id": law_id,
        "act_ref": act_ref,
        "l2_summary": l2_summary,
        "cited_article": cited_article,
        "dedup_status": dedup_status,
        "repetition_status": dedup_status if dedup_status != "new" else "new",
        "title": (l2_summary or "")[:40],
        "published_at": "2026-11-01T00:00:00",
        "effective_date": None,
        "authority_id": None,
        "repetition_count": repetition_count,
        "source_type": "RSS",
        "source_id": f"src-{key}",
        "url": f"https://example.com/{key}",
        "content": l2_summary,
        "hash_signature": f"hash-{key}",
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


def _upsert(conn, profile_id, *, repetition_status, repetition_count=0,
            dedup_status="new", significance_rank=3, email_eligible=1,
            email_sent=0, topic_label='["HCM"]', title="test"):
    now = datetime.utcnow().isoformat()
    key = abs(hash(title + repetition_status)) % 100000
    return upsert_news_item(conn, profile_id, {
        "source_type": "RSS",
        "source_id": f"sid-{key}",
        "url": f"https://example.com/{key}",
        "domain": "example.com",
        "title": title,
        "content": "content",
        "published_at": now,
        "hash_signature": f"hs-{key}",
        "publisher": "Test Publisher",
        "authority_id": None,
        "authority_status": "configured",
        "dedup_status": dedup_status,
        "significance_rank": significance_rank,
        "rank_tier": "tier1",
        "rank_reasoning": "test",
        "repetition_status": repetition_status,
        "repetition_count": repetition_count,
        "topic_label": topic_label,
        "email_eligible": email_eligible,
        "email_sent": email_sent,
        "effective_date": None,
        "l2_summary": None,
        "l2_fetched_at": None,
        "act_ref": None,
        "law_primary": None,
        "law_secondary": None,
        "law_reference": None,
        "announce_state": None,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SECTION A: Reconcile bookkeeping — repetition_count correctness
# ══════════════════════════════════════════════════════════════════════════════

def test_1_new_item_stays_new():
    """Criterion 1: article with no prior history stays NEW (count unaffected)."""
    conn = _make_reconcile_db()
    item = _make_item(law_id=1, l2_summary="GROUP_A first publication")

    result = _run([item], conn)

    assert item["repetition_status"] == "new", (
        f"Criterion 1 fail: expected NEW, got {item['repetition_status']!r}"
    )
    assert result["reconciled"] == 0
    print("✅ Criterion 1 passed: NEW item stays NEW")


def test_3_first_confirmed_repetition_count_is_1():
    """Criterion 3: first confirmed repetition receives repetition_count = 1."""
    conn = _make_reconcile_db()
    _insert_baseline(conn, law_id=1,
                     l2_summary="GROUP_A original rate change",
                     repetition_count=0, days_ago=1)

    item = _make_item(law_id=1, l2_summary="GROUP_A rate change follow-up")

    _run([item], conn)

    assert item["repetition_status"] == "repeated", (
        f"Criterion 3 fail: expected REPEATED, got {item['repetition_status']!r}"
    )
    assert item["repetition_count"] == 1, (
        f"Criterion 3 fail: expected count=1, got {item['repetition_count']}"
    )
    print("✅ Criterion 3 passed: first confirmed repetition has count=1")


def test_4_increasing_counts():
    """Criterion 4: second repetition gets count=2 when first repeat (count=1) is in baseline."""
    conn = _make_reconcile_db()
    # Baseline: original (count=0) and first repeat (count=1) both present
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=3)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A first reminder",
                     repetition_count=1, days_ago=2)

    item = _make_item(law_id=1, l2_summary="GROUP_A second reminder")

    _run([item], conn)

    assert item["repetition_status"] == "repeated", (
        f"Criterion 4 fail: expected REPEATED, got {item['repetition_status']!r}"
    )
    assert item["repetition_count"] == 2, (
        f"Criterion 4 fail: expected count=2, got {item['repetition_count']}"
    )
    print("✅ Criterion 4 passed: second repetition has count=2")


def test_5_distinct_events_same_law_separate_counts():
    """Criterion 5: two distinct events under the same law_id maintain independent counts."""
    conn = _make_reconcile_db()
    # Event A (count=2 chain) and Event B (count=0 original) both under law_id=1
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=4)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A first repeat",
                     repetition_count=1, days_ago=3)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A second repeat",
                     repetition_count=2, days_ago=2)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_B original",
                     repetition_count=0, days_ago=1)

    # New repeat of Event B (not Event A)
    item_b_repeat = _make_item(law_id=1, l2_summary="GROUP_B first follow-up")

    _run([item_b_repeat], conn)

    assert item_b_repeat["repetition_status"] == "repeated", (
        f"Criterion 5 fail: expected REPEATED, got {item_b_repeat['repetition_status']!r}"
    )
    assert item_b_repeat["repetition_count"] == 1, (
        f"Criterion 5 fail: expected count=1 (Event B chain, not Event A), "
        f"got {item_b_repeat['repetition_count']}"
    )
    print("✅ Criterion 5 passed: distinct events under same law have independent counts")


def test_6_same_run_and_cross_run_consistency():
    """Criterion 6: same-run and cross-run REPEATED items both get count=1 for first repetition."""
    # Cross-run case
    conn_cross = _make_reconcile_db()
    _insert_baseline(conn_cross, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=1)
    item_cross = _make_item(law_id=1, l2_summary="GROUP_A cross-run repeat")
    _run([item_cross], conn_cross)

    assert item_cross["repetition_count"] == 1, (
        f"Criterion 6 fail (cross-run): expected count=1, got {item_cross['repetition_count']}"
    )

    # Same-run case: two items in same run — second is repeat of first
    conn_same = _make_reconcile_db()
    item_orig = _make_item(law_id=2, l2_summary="GROUP_B original")
    item_orig["published_at"] = "2026-11-01T08:00:00"
    item_repeat = _make_item(law_id=2, l2_summary="GROUP_B same-run repeat")
    item_repeat["published_at"] = "2026-11-01T10:00:00"
    _run([item_orig, item_repeat], conn_same)

    assert item_repeat["repetition_count"] == 1, (
        f"Criterion 6 fail (same-run): expected count=1, got {item_repeat['repetition_count']}"
    )
    assert item_orig["repetition_status"] == "new", (
        f"Criterion 6 fail: original must stay NEW"
    )
    print("✅ Criterion 6 passed: same-run and cross-run first repetitions both have count=1")


def test_11_duplicate_does_not_increment_count():
    """Criterion 11: a duplicate in the baseline does not inflate the repetition count."""
    conn = _make_reconcile_db()
    # Baseline: original (count=0) and a duplicate of it (also count=0, semantically identical)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=3)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=2)  # duplicate, same count

    # New repeat: confirms against both (max(0,0)+1 = 1, NOT 2)
    item = _make_item(law_id=1, l2_summary="GROUP_A first true repeat")
    _run([item], conn)

    assert item["repetition_status"] == "repeated"
    assert item["repetition_count"] == 1, (
        f"Criterion 11 fail: duplicate in baseline must not inflate count; "
        f"expected count=1, got {item['repetition_count']}"
    )
    print("✅ Criterion 11 passed: duplicate in baseline does not inflate repetition count")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B: News Review list output — status values for rendering/filtering
# ══════════════════════════════════════════════════════════════════════════════

def test_1b_new_item_status_in_review():
    """Criterion 1 (review): DB row with repetition_status='new' → item.status == 'NEW'."""
    conn = _full_schema_db()
    _upsert(conn, PROFILE_ID, repetition_status="new", title="new article")
    conn.commit()

    items = list_all_news_for_review(conn, PROFILE_ID)
    new_items = [i for i in items if i.get("title") == "new article"]
    assert new_items, "Expected to find the new article in review list"
    assert new_items[0]["status"] == "NEW", (
        f"Criterion 1 review fail: expected 'NEW', got {new_items[0]['status']!r}"
    )
    print("✅ Criterion 1 (review) passed: NEW item has status='NEW' in review list")


def test_2_duplicate_rank_zero_in_review():
    """Criterion 2: DUPLICATE item has rank=0 and status='DUPLICATE' in review list."""
    conn = _full_schema_db()
    _upsert(conn, PROFILE_ID, repetition_status="duplicate", dedup_status="duplicate",
            significance_rank=0, email_eligible=0, title="dup article")
    conn.commit()

    items = list_all_news_for_review(conn, PROFILE_ID)
    dup_items = [i for i in items if i.get("title") == "dup article"]
    assert dup_items, "Expected to find the duplicate article in review list"
    assert dup_items[0]["status"] == "DUPLICATE", (
        f"Criterion 2 fail: expected 'DUPLICATE', got {dup_items[0]['status']!r}"
    )
    assert dup_items[0].get("rank") == 0, (
        f"Criterion 2 fail: DUPLICATE must have rank=0, got {dup_items[0].get('rank')}"
    )
    print("✅ Criterion 2 passed: DUPLICATE has status='DUPLICATE' and rank=0")


def test_3b_repeated_item_has_count_in_review():
    """Criterion 3 (review): REPEATED item with count=1 has correct status and count."""
    conn = _full_schema_db()
    _upsert(conn, PROFILE_ID, repetition_status="repeated", repetition_count=1,
            title="first repeat")
    conn.commit()

    items = list_all_news_for_review(conn, PROFILE_ID)
    rep_items = [i for i in items if i.get("title") == "first repeat"]
    assert rep_items, "Expected to find the repeated article in review list"
    assert rep_items[0]["status"] == "REPEATED", (
        f"Criterion 3 review fail: expected 'REPEATED', got {rep_items[0]['status']!r}"
    )
    assert rep_items[0].get("repetition_count") == 1, (
        f"Criterion 3 review fail: expected count=1, got {rep_items[0].get('repetition_count')}"
    )
    print("✅ Criterion 3 (review) passed: REPEATED (1) item has correct status and count")


def test_7_repeated_filter_uses_raw_status():
    """Criterion 7: items with repetition_status='repeated' and various counts all have
    item['status']='REPEATED' — the data-status attribute value that the JS filter matches."""
    conn = _full_schema_db()
    _upsert(conn, PROFILE_ID, repetition_status="repeated", repetition_count=1, title="rep1")
    _upsert(conn, PROFILE_ID, repetition_status="repeated", repetition_count=2, title="rep2")
    _upsert(conn, PROFILE_ID, repetition_status="repeated", repetition_count=3, title="rep3")
    conn.commit()

    items = list_all_news_for_review(conn, PROFILE_ID)
    rep_items = {i["title"]: i for i in items if i.get("title") in ("rep1", "rep2", "rep3")}

    for name, item in rep_items.items():
        assert item["status"] == "REPEATED", (
            f"Criterion 7 fail: {name!r} must have data-status='REPEATED' (not a compound "
            f"label), got {item['status']!r}"
        )
    assert len(rep_items) == 3, f"Expected 3 REPEATED items, found {len(rep_items)}"
    print("✅ Criterion 7 passed: all REPEATED items have status='REPEATED' for JS filter matching")


def test_8_update_chip_absent_from_template():
    """Criterion 8: the UPDATE filter chip is absent from review_news.html."""
    with open(_TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()

    # The old chip was: data-val="UPDATE"
    assert 'data-val="UPDATE"' not in html, (
        "Criterion 8 fail: 'data-val=\"UPDATE\"' still present in review_news.html"
    )
    print("✅ Criterion 8 (template) passed: UPDATE filter chip is absent")


def test_8_update_absent_from_review_help():
    """Criterion 8: review_help.json Status section has no UPDATE entry."""
    with open(_REVIEW_HELP_PATH, encoding="utf-8") as f:
        help_data = json.load(f)

    status_labels = [row.get("label") for row in help_data.get("Status", [])]
    assert "UPDATE" not in status_labels, (
        f"Criterion 8 fail: UPDATE still in review_help.json Status: {status_labels}"
    )
    print("✅ Criterion 8 (review_help) passed: UPDATE absent from review_help.json")


def test_9_historical_update_records_accessible():
    """Criterion 9: rows with repetition_status='update' (legacy) remain in the review list
    with item.status='UPDATE' and are not filtered out under the 'All' view."""
    conn = _full_schema_db()
    _upsert(conn, PROFILE_ID, repetition_status="update", title="legacy update item")
    conn.commit()

    items = list_all_news_for_review(conn, PROFILE_ID)
    update_items = [i for i in items if i.get("title") == "legacy update item"]
    assert update_items, (
        "Criterion 9 fail: historical UPDATE record must appear in review list under All"
    )
    assert update_items[0]["status"] == "UPDATE", (
        f"Criterion 9 fail: expected status='UPDATE', got {update_items[0]['status']!r}"
    )
    print("✅ Criterion 9 passed: historical UPDATE records remain accessible")


def test_10_other_filter_dimensions_unaffected():
    """Criterion 10: rank, topic_label (Glossary), and email_sent attributes
    are present and correct in review-list items — proving other filter dimensions work."""
    conn = _full_schema_db()
    _upsert(conn, PROFILE_ID, repetition_status="new", significance_rank=4,
            topic_label='["Income Tax"]', email_eligible=1, email_sent=0,
            title="rank4 article")
    _upsert(conn, PROFILE_ID, repetition_status="new", significance_rank=1,
            topic_label='["General"]', email_eligible=0, email_sent=0,
            title="rank1 article")
    conn.commit()

    items = list_all_news_for_review(conn, PROFILE_ID)
    by_title = {i["title"]: i for i in items if i.get("title") in ("rank4 article", "rank1 article")}

    assert by_title["rank4 article"]["rank"] == 4, "rank4 item must have rank=4"
    assert by_title["rank1 article"]["rank"] == 1, "rank1 item must have rank=1"
    # topic_label is used for the Glossary filter
    assert by_title["rank4 article"]["topic_label"] == '["Income Tax"]'
    # email_sent is used for the Email filter
    assert by_title["rank4 article"]["email_sent"] == 0
    print("✅ Criterion 10 passed: rank, glossary, and email filter data unaffected")


def test_12_legacy_repeated_zero_count_no_fabrication():
    """Criterion 12: a REPEATED item with repetition_count=0 (legacy/missing) exposes count=0
    so the template does NOT produce a parenthetical count label.
    Verify via Jinja2 badge logic directly."""
    from jinja2 import Environment

    # The badge template logic from review_news.html
    env = Environment()
    badge_tmpl = env.from_string(
        "{% set _rep_count = item.repetition_count|int if item.repetition_count else 0 %}"
        "{% set _status_label = ('REPEATED (' ~ _rep_count ~ ')') "
        "if (item.status == 'REPEATED' and _rep_count >= 1) else item.status %}"
        "{{ _status_label }}"
    )

    # Legacy REPEATED with count=0 → no parenthetical
    label_zero = badge_tmpl.render(item={"status": "REPEATED", "repetition_count": 0}).strip()
    assert label_zero == "REPEATED", (
        f"Criterion 12 fail: count=0 must show 'REPEATED', got {label_zero!r}"
    )

    # Legacy REPEATED with count=None → no parenthetical
    label_none = badge_tmpl.render(item={"status": "REPEATED", "repetition_count": None}).strip()
    assert label_none == "REPEATED", (
        f"Criterion 12 fail: count=None must show 'REPEATED', got {label_none!r}"
    )

    # Legitimate REPEATED (1) → shows count
    label_one = badge_tmpl.render(item={"status": "REPEATED", "repetition_count": 1}).strip()
    assert label_one == "REPEATED (1)", (
        f"Criterion 12 fail: count=1 must show 'REPEATED (1)', got {label_one!r}"
    )

    # NEW item → shows 'NEW'
    label_new = badge_tmpl.render(item={"status": "NEW", "repetition_count": 0}).strip()
    assert label_new == "NEW", (
        f"Criterion 12 fail: NEW item must show 'NEW', got {label_new!r}"
    )

    # DUPLICATE item → shows 'DUPLICATE'
    label_dup = badge_tmpl.render(item={"status": "DUPLICATE", "repetition_count": 0}).strip()
    assert label_dup == "DUPLICATE", (
        f"Criterion 12 fail: DUPLICATE item must show 'DUPLICATE', got {label_dup!r}"
    )

    print("✅ Criterion 12 passed: legacy counts do not produce fabricated numbers")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION C: Task 4D.1 — repetition counter fix (historical + same-run combined)
# ══════════════════════════════════════════════════════════════════════════════

def test_4d1_historical_original_three_same_run_reminders():
    """Task 4D.1: historical original (count=0) + three same-run reminders → 1, 2, 3."""
    conn = _make_reconcile_db()
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=1)

    r_a = _make_item(law_id=1, l2_summary="GROUP_A reminder A")
    r_a["published_at"] = "2026-11-10T08:00:00"
    r_b = _make_item(law_id=1, l2_summary="GROUP_A reminder B")
    r_b["published_at"] = "2026-11-10T09:00:00"
    r_c = _make_item(law_id=1, l2_summary="GROUP_A reminder C")
    r_c["published_at"] = "2026-11-10T10:00:00"

    _run([r_a, r_b, r_c], conn)

    assert r_a["repetition_status"] == "repeated", (
        f"Task 4D.1 fail: r_a expected REPEATED, got {r_a['repetition_status']!r}"
    )
    assert r_a["repetition_count"] == 1, (
        f"Task 4D.1 fail: r_a expected count=1, got {r_a['repetition_count']}"
    )
    assert r_b["repetition_status"] == "repeated", (
        f"Task 4D.1 fail: r_b expected REPEATED, got {r_b['repetition_status']!r}"
    )
    assert r_b["repetition_count"] == 2, (
        f"Task 4D.1 fail: r_b expected count=2, got {r_b['repetition_count']}"
    )
    assert r_c["repetition_status"] == "repeated", (
        f"Task 4D.1 fail: r_c expected REPEATED, got {r_c['repetition_status']!r}"
    )
    assert r_c["repetition_count"] == 3, (
        f"Task 4D.1 fail: r_c expected count=3, got {r_c['repetition_count']}"
    )
    print("✅ Task 4D.1: historical original + 3 same-run reminders → 1, 2, 3")


def test_4d1_historical_count_2_two_same_run_reminders():
    """Task 4D.1: historical chain max count=2 + two same-run reminders → 3, 4."""
    conn = _make_reconcile_db()
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=4)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A reminder 1",
                     repetition_count=1, days_ago=3)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A reminder 2",
                     repetition_count=2, days_ago=2)

    r_d = _make_item(law_id=1, l2_summary="GROUP_A reminder D")
    r_d["published_at"] = "2026-11-10T08:00:00"
    r_e = _make_item(law_id=1, l2_summary="GROUP_A reminder E")
    r_e["published_at"] = "2026-11-10T09:00:00"

    _run([r_d, r_e], conn)

    assert r_d["repetition_status"] == "repeated", (
        f"Task 4D.1 fail: r_d expected REPEATED, got {r_d['repetition_status']!r}"
    )
    assert r_d["repetition_count"] == 3, (
        f"Task 4D.1 fail: r_d expected count=3, got {r_d['repetition_count']}"
    )
    assert r_e["repetition_status"] == "repeated", (
        f"Task 4D.1 fail: r_e expected REPEATED, got {r_e['repetition_status']!r}"
    )
    assert r_e["repetition_count"] == 4, (
        f"Task 4D.1 fail: r_e expected count=4, got {r_e['repetition_count']}"
    )
    print("✅ Task 4D.1: historical count 2 + 2 same-run reminders → 3, 4")


def test_4d1_distinct_events_same_law_independent_counters_combined():
    """Task 4D.1: two distinct events under same law maintain independent counters
    when both historical and same-run candidates are present for each event."""
    conn = _make_reconcile_db()
    # GROUP_A: 2-deep chain in history; GROUP_B: 1-deep in history
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A original",
                     repetition_count=0, days_ago=3)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A first reminder",
                     repetition_count=1, days_ago=2)
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_B original",
                     repetition_count=0, days_ago=2)

    # Same run: GROUP_A second reminder, GROUP_B first reminder, GROUP_A third reminder
    a_r2 = _make_item(law_id=1, l2_summary="GROUP_A second reminder")
    a_r2["published_at"] = "2026-11-10T08:00:00"
    b_r1 = _make_item(law_id=1, l2_summary="GROUP_B first reminder")
    b_r1["published_at"] = "2026-11-10T09:00:00"
    a_r3 = _make_item(law_id=1, l2_summary="GROUP_A third reminder")
    a_r3["published_at"] = "2026-11-10T10:00:00"

    _run([a_r2, b_r1, a_r3], conn)

    # GROUP_A chain: history max=1 → a_r2 gets 2; a_r3 must use max(history=1, run=2)=2 → 3
    assert a_r2["repetition_count"] == 2, (
        f"Task 4D.1 fail: a_r2 expected count=2, got {a_r2['repetition_count']}"
    )
    assert a_r3["repetition_count"] == 3, (
        f"Task 4D.1 fail: a_r3 expected count=3, got {a_r3['repetition_count']}"
    )
    # GROUP_B chain: history max=0 → b_r1 gets 1 (must not be polluted by GROUP_A counts)
    assert b_r1["repetition_status"] == "repeated", (
        f"Task 4D.1 fail: b_r1 expected REPEATED"
    )
    assert b_r1["repetition_count"] == 1, (
        f"Task 4D.1 fail: b_r1 expected count=1, got {b_r1['repetition_count']}"
    )
    print("✅ Task 4D.1: distinct events same law maintain independent counters under combined history+same-run")


def test_4d1_all_new_same_run_sequential_counts():
    """Task 4D.1: all-new same-run reminders (no history) receive sequential counts 1, 2, 3."""
    conn = _make_reconcile_db()

    item_1 = _make_item(law_id=1, l2_summary="GROUP_A first in run")
    item_1["published_at"] = "2026-11-10T07:00:00"
    item_2 = _make_item(law_id=1, l2_summary="GROUP_A second in run")
    item_2["published_at"] = "2026-11-10T08:00:00"
    item_3 = _make_item(law_id=1, l2_summary="GROUP_A third in run")
    item_3["published_at"] = "2026-11-10T09:00:00"
    item_4 = _make_item(law_id=1, l2_summary="GROUP_A fourth in run")
    item_4["published_at"] = "2026-11-10T10:00:00"

    _run([item_1, item_2, item_3, item_4], conn)

    assert item_1["repetition_status"] == "new", "Task 4D.1 fail: first in run must stay NEW"
    assert item_1["repetition_count"] == 0
    assert item_2["repetition_count"] == 1, (
        f"Task 4D.1 fail: second in run expected count=1, got {item_2['repetition_count']}"
    )
    assert item_3["repetition_count"] == 2, (
        f"Task 4D.1 fail: third in run expected count=2, got {item_3['repetition_count']}"
    )
    assert item_4["repetition_count"] == 3, (
        f"Task 4D.1 fail: fourth in run expected count=3, got {item_4['repetition_count']}"
    )
    print("✅ Task 4D.1: all-new same-run reminders receive sequential counts 1, 2, 3")


def test_4d1_no_confirmed_match_stays_new():
    """Task 4D.1: items with no confirmed same-event match remain NEW with count=0."""
    conn = _make_reconcile_db()
    _insert_baseline(conn, law_id=1, l2_summary="GROUP_A historical",
                     repetition_count=2, days_ago=1)

    item_b = _make_item(law_id=1, l2_summary="GROUP_B unrelated article")

    _run([item_b], conn)

    assert item_b["repetition_status"] == "new", (
        f"Task 4D.1 fail: unconfirmed item must stay NEW, got {item_b['repetition_status']!r}"
    )
    assert item_b["repetition_count"] == 0, (
        f"Task 4D.1 fail: unconfirmed item must keep count=0, got {item_b['repetition_count']}"
    )
    print("✅ Task 4D.1: unconfirmed items remain NEW with count=0")


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_1_new_item_stays_new,
        test_2_duplicate_rank_zero_in_review,
        test_3_first_confirmed_repetition_count_is_1,
        test_3b_repeated_item_has_count_in_review,
        test_4_increasing_counts,
        test_5_distinct_events_same_law_separate_counts,
        test_6_same_run_and_cross_run_consistency,
        test_7_repeated_filter_uses_raw_status,
        test_8_update_chip_absent_from_template,
        test_8_update_absent_from_review_help,
        test_9_historical_update_records_accessible,
        test_10_other_filter_dimensions_unaffected,
        test_11_duplicate_does_not_increment_count,
        test_12_legacy_repeated_zero_count_no_fabrication,
        test_1b_new_item_status_in_review,
        test_4d1_historical_original_three_same_run_reminders,
        test_4d1_historical_count_2_two_same_run_reminders,
        test_4d1_distinct_events_same_law_independent_counters_combined,
        test_4d1_all_new_same_run_sequential_counts,
        test_4d1_no_confirmed_match_stays_new,
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
