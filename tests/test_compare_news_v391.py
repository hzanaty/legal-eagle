"""
V3.91 Task 4A — Focused tests for the Comparing cleanup.

Verifies that run_compare_news_agent() classifies items strictly as NEW or DUPLICATE,
never UPDATE or REPEATED, using only reliable technical identity signals.

All tests use skip_persist=True (no DB writes) and an empty or controlled baseline.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock

from agents.compare_news import run_compare_news_agent


def _item(title, content="", url=None, guid=None, profile_id=1):
    return {
        "title": title,
        "content": content,
        "url": url or f"https://example.com/{hash(title) % 100000}",
        "link": url or f"https://example.com/{hash(title) % 100000}",
        "guid": guid or f"guid-{hash(title) % 100000}",
        "source_type": "RSS",
        "profile_id": profile_id,
        "publisher": "Test Publisher",
    }


def _run(items, baseline=None):
    """Run compare agent with an empty or stub baseline."""
    baseline = baseline or []
    with patch("agents.compare_news.get_weekly_baseline", return_value=baseline), \
         patch("agents.compare_news.get_baseline_days", return_value=7), \
         patch("agents.compare_news.add_news_item"):
        result = run_compare_news_agent(
            items,
            outputs_dir=None,
            skip_persist=True,
        )
    return result


def _statuses(items):
    return [(it["dedup_status"], it["repetition_status"]) for it in items]


# ---------------------------------------------------------------------------
# Test 1: Identical URL → DUPLICATE
# ---------------------------------------------------------------------------
def test_identical_url_is_duplicate():
    shared_url = "https://example.com/law-article"
    baseline_item = _item("Original Article", url=shared_url)
    baseline_item["hash_signature"] = None  # ensure only URL triggers
    baseline_item["guid"] = "baseline-guid-unique"

    current = [_item("Original Article (reposted)", url=shared_url, guid="new-guid")]
    result = _run(current, baseline=[baseline_item])
    assert result["new_items"] == [], f"Expected no new items, got {result['new_items']}"
    assert current[0]["dedup_status"] == "duplicate", current[0]["dedup_status"]
    assert current[0]["repetition_status"] == "duplicate"
    print("✅ Test 1 passed: identical URL → DUPLICATE")


# ---------------------------------------------------------------------------
# Test 2: Identical hash_signature → DUPLICATE
# ---------------------------------------------------------------------------
def test_identical_hash_is_duplicate():
    from agents.text_utils import hash_signature
    title = "Shared headline content"
    content = "Shared body content"
    sig = hash_signature(title, content)

    baseline_item = _item(title, content=content, guid="b-guid", url="https://old.example.com/1")
    baseline_item["hash_signature"] = sig

    current_item = _item(title, content=content, guid="new-guid-2", url="https://new.example.com/2")

    result = _run([current_item], baseline=[baseline_item])
    assert current_item["dedup_status"] == "duplicate", current_item["dedup_status"]
    assert current_item["repetition_status"] == "duplicate"
    print("✅ Test 2 passed: identical hash_signature → DUPLICATE")


# ---------------------------------------------------------------------------
# Test 3: Same URL in same run → second item is DUPLICATE
# ---------------------------------------------------------------------------
def test_same_url_same_run_is_duplicate():
    url = "https://example.com/same-url-twice"
    item1 = _item("Article A", url=url, guid="guid-a")
    item2 = _item("Article B different title", url=url, guid="guid-b")

    result = _run([item1, item2], baseline=[])
    assert item1["dedup_status"] == "new", item1["dedup_status"]
    assert item2["dedup_status"] == "duplicate", item2["dedup_status"]
    assert item2["repetition_status"] == "duplicate"
    print("✅ Test 3 passed: same URL within a run → second item DUPLICATE")


# ---------------------------------------------------------------------------
# Test 4: Two articles sharing only a law reference → both NEW
# ---------------------------------------------------------------------------
def test_same_law_reference_both_new():
    item1 = _item(
        "GVK Article 23/20 tax exemption for qualified service centers",
        content="Employees in qualified service centers receive an income-tax exemption.",
        guid="tr-001",
    )
    item2 = _item(
        "New reporting table in Muhtasar form for GVK Article 23/20",
        content="A new column must be added to the Muhtasar ve Prim Hizmet Beyannamesi.",
        guid="tr-002",
    )

    result = _run([item1, item2], baseline=[])
    assert item1["dedup_status"] == "new", item1["dedup_status"]
    assert item2["dedup_status"] == "new", item2["dedup_status"]
    assert item1["repetition_status"] == "new"
    assert item2["repetition_status"] == "new"
    print("✅ Test 4 passed: same law reference → both NEW")


# ---------------------------------------------------------------------------
# Test 5: Two articles on same topic → both NEW
# ---------------------------------------------------------------------------
def test_same_topic_both_new():
    item1 = _item(
        "Social insurance contribution rates increased",
        content="Employer rate rises from 7% to 8.5% effective November 2026.",
        guid="xn-001",
    )
    item2 = _item(
        "Countdown to social insurance rate change",
        content="One week remaining before the new contribution rates take effect.",
        guid="xn-002",
    )

    result = _run([item1, item2], baseline=[])
    assert item1["dedup_status"] == "new"
    assert item2["dedup_status"] == "new"
    print("✅ Test 5 passed: same topic → both NEW")


# ---------------------------------------------------------------------------
# Test 6: Türkiye Case A — GVK exemption vs GVK reporting table → both NEW
# ---------------------------------------------------------------------------
def test_turkiye_case_a_both_new():
    exemption = _item(
        "GVK Madde 23/20 Nitelikli hizmet merkezi çalışanlarına vergi istisnası",
        content="3 veya 5 kat asgari ücret tutarında gelir vergisi istisnası uygulanacaktır.",
        guid="gvk-exemption-001",
        url="https://tr.example.com/gvk-exemption",
    )
    reporting = _item(
        "Muhtasar Beyanname GVK 23/20 istisnası için yeni tablo",
        content="Nitelikli hizmet merkezi istisnası için Muhtasar formuna yeni satır eklenecek.",
        guid="gvk-reporting-001",
        url="https://tr.example.com/gvk-reporting",
    )

    result = _run([exemption, reporting], baseline=[])
    assert exemption["dedup_status"] == "new", exemption["dedup_status"]
    assert reporting["dedup_status"] == "new", reporting["dedup_status"]
    assert exemption["repetition_status"] == "new"
    assert reporting["repetition_status"] == "new"
    print("✅ Test 6 passed: Türkiye Case A → both NEW")


# ---------------------------------------------------------------------------
# Test 7: Different-language articles on same legal event → both NEW
# ---------------------------------------------------------------------------
def test_different_language_same_event_both_new():
    english = _item(
        "Royal Decree No. 18/2026 increases social insurance contributions",
        content="Employer contribution rate rises from 7% to 8.5% effective 15 Nov 2026.",
        guid="xn-en-001",
        url="https://en.example.com/decree-18-2026",
    )
    arabic = _item(
        "المرسوم الملكي رقم 18/2026 يرفع اشتراكات التأمينات الاجتماعية",
        content="ترتفع حصة صاحب العمل من 7% إلى 8.5% اعتباراً من 15 نوفمبر 2026.",
        guid="xn-ar-001",
        url="https://ar.example.com/decree-18-2026",
    )

    result = _run([english, arabic], baseline=[])
    assert english["dedup_status"] == "new", english["dedup_status"]
    assert arabic["dedup_status"] == "new", arabic["dedup_status"]
    print("✅ Test 7 passed: different language, same event → both NEW")


# ---------------------------------------------------------------------------
# Test 8: Empty baseline → all items NEW
# ---------------------------------------------------------------------------
def test_empty_baseline_all_new():
    items = [
        _item("Article One", guid="e-001"),
        _item("Article Two", guid="e-002"),
        _item("Article Three", guid="e-003"),
    ]

    result = _run(items, baseline=[])
    assert len(result["new_items"]) == 3
    for it in items:
        assert it["dedup_status"] == "new", it["dedup_status"]
        assert it["repetition_status"] == "new"
    print("✅ Test 8 passed: empty baseline → all NEW")


# ---------------------------------------------------------------------------
# Test 9: DUPLICATE items are still passed to DB persistence
# ---------------------------------------------------------------------------
def test_duplicates_persisted():
    shared_url = "https://example.com/persisted-dup"
    baseline_item = _item("Baseline Article", url=shared_url, guid="b-persist")
    current_item = _item("Same Article Again", url=shared_url, guid="c-persist")

    with patch("agents.compare_news.get_weekly_baseline", return_value=[baseline_item]), \
         patch("agents.compare_news.get_baseline_days", return_value=7), \
         patch("agents.compare_news.add_news_item") as mock_add:
        run_compare_news_agent([current_item], outputs_dir=None, skip_persist=False)

    # add_news_item must be called for the duplicate item (persistence preserved)
    assert mock_add.called, "add_news_item was not called — duplicates not persisted"
    print("✅ Test 9 passed: DUPLICATE items written to DB")


# ---------------------------------------------------------------------------
# Test 10: No item ever gets dedup_status/repetition_status = 'update' or 'repeated'
# ---------------------------------------------------------------------------
def test_no_update_or_repeated_from_step4():
    items = [
        _item("New law on payroll reporting", guid="nr-001"),
        _item("Ministry announces payroll software update", guid="nr-002"),
        _item("Same payroll reporting article", guid="nr-001"),  # same guid → dup
    ]

    result = _run(items, baseline=[])
    all_items = items
    for it in all_items:
        assert it.get("dedup_status") != "update", f"update found: {it['title']}"
        assert it.get("dedup_status") != "repeated", f"repeated dedup found: {it['title']}"
        assert it.get("repetition_status") != "update", f"update repetition: {it['title']}"
        assert it.get("repetition_status") != "repeated", f"repeated repetition: {it['title']}"
    print("✅ Test 10 passed: no UPDATE or REPEATED assigned by Step 4")


# ---------------------------------------------------------------------------
# Test 11: update_items in return is always empty
# ---------------------------------------------------------------------------
def test_update_items_always_empty():
    items = [_item("Some article", guid="ui-001"), _item("Another article", guid="ui-002")]
    result = _run(items, baseline=[])
    assert result["update_items"] == [], f"Expected empty update_items, got {result['update_items']}"
    print("✅ Test 11 passed: update_items always []")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_identical_url_is_duplicate,
        test_identical_hash_is_duplicate,
        test_same_url_same_run_is_duplicate,
        test_same_law_reference_both_new,
        test_same_topic_both_new,
        test_turkiye_case_a_both_new,
        test_different_language_same_event_both_new,
        test_empty_baseline_all_new,
        test_duplicates_persisted,
        test_no_update_or_repeated_from_step4,
        test_update_items_always_empty,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__} FAILED: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed:
        sys.exit(1)
