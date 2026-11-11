"""
V3.91 Task 4B — Controller routing: DUPLICATE bypass tests.

Contract:
- DUPLICATE items are persisted and visible (tested via compare_news mock calls).
- DUPLICATE items NEVER reach L2 Fetch, Reconcile, Glossary Match, Law Match,
  RCM Match, Impact Gate, Timing, or Rank.
- NEW items continue through all expensive stages unchanged.
- All-duplicate input runs without errors and makes no unnecessary AI calls.
- skip_comparison=True routes all items as NEW through the full pipeline.
"""
import sys
import os
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _Row(dict):
    """Minimal SQLite row: dict that supports row["key"] access."""
    pass


def _make_conn():
    """Mock DB connection satisfying all SQL queries in run_profile_once."""
    conn = MagicMock()

    def _execute(sql, params=None):
        m = MagicMock()
        if "SELECT * FROM profiles" in sql:
            m.fetchone.return_value = _Row({
                "id": 1, "country_code": "AE", "lob": "HCM",
                "schedule_day": "Monday",
            })
        else:
            m.fetchone.return_value = None
            m.fetchall.return_value = []
        return m

    conn.execute.side_effect = _execute
    return conn


def _make_item(title, url, dedup_status="new"):
    """Minimal item dict as produced by compare_news."""
    return {
        "title": title,
        "url": url,
        "link": url,
        "guid": f"guid-{abs(hash(title)) % 100000}",
        "source_type": "RSS",
        "profile_id": 1,
        "content": f"Content for {title}",
        "dedup_status": dedup_status,
        "repetition_status": dedup_status,
        "significance_rank": 0,
        "rank_tier": "duplicate" if dedup_status == "duplicate" else None,
    }


@contextlib.contextmanager
def _mock_run(all_items, compare_result, captured):
    """
    Patch every external dependency in run_profile_once.

    all_items   — what the URL-source runner returns (combined raw collection)
    compare_result — dict with new_items/update_items keys
    captured    — dict filled by spy side-effects
    """
    conn = _make_conn()

    # Spy: capture the first positional argument (the items list)
    def _spy(key):
        def _fn(items, *a, **kw):
            captured[key] = list(items)
        return _fn

    # RCM spy: signature is (conn, profile_id, items)
    def _rcm_spy(conn, pid, items):
        captured["rcm_items"] = list(items)

    with contextlib.ExitStack() as stack:
        for p in [
            # --- DB ---
            patch("agents.agents_controller.get_connection", return_value=conn),
            patch("agents.agents_controller.create_schema_if_needed"),
            # --- Config ---
            patch("agents.agents_controller.load_language",             return_value="English"),
            patch("agents.agents_controller.load_rss_feeds",            return_value=[]),
            patch("agents.agents_controller.load_tweet_accounts",       return_value=[]),
            patch("agents.agents_controller.load_email_receivers",      return_value=["t@x.com"]),
            patch("agents.agents_controller.load_email_receivers_with_lang", return_value={}),
            patch("agents.agents_controller.load_glossary",             return_value={"terms": []}),
            patch("agents.agents_controller.load_url_sources",          return_value=[]),
            patch("agents.agents_controller.load_profile_date_scope",   return_value="7d"),
            patch("agents.agents_controller.get_setting_value",         return_value=None),
            patch("agents.agents_controller.parse_date_scope",          return_value=7),
            # --- Health ---
            patch("agents.agents_controller.run_health_checks", return_value={}),
            patch("agents.agents_controller.summarize",          return_value="OK"),
            patch("agents.agents_controller.hard_failures",      return_value=[]),
            # --- Sources ---
            patch("agents.agents_controller.parse_rss_feed",            return_value=[]),
            patch("agents.agents_controller.run_unified_sources",
                  return_value={"items": all_items, "errors": []}),
            patch("agents.agents_controller.filter_items_by_date",
                  side_effect=lambda it, **kw: it),
            patch("agents.agents_controller.filter_source_items",
                  side_effect=lambda it, src: it),
            patch("agents.agents_controller.update_rss_feed_last_fetch_timestamp"),
            patch("agents.agents_controller.update_url_source_fetch_timestamp"),
            # --- Attribution ---
            patch("agents.agents_controller.attribute_items"),
            patch("agents.agents_controller.build_feed_config", return_value={}),
            patch("agents.agents_controller.build_url_config",  return_value={}),
            # --- Comparing ---
            patch("agents.agents_controller.run_compare_news_agent",
                  return_value=compare_result),
            # --- Expensive stages (spy) ---
            patch("agents.l2_fetcher.run_l2_fetch",
                  side_effect=_spy("l2_items")),
            patch("agents.l2_fetcher.L2FetchError", Exception),
            patch("agents.authority_attributor.resolve_primary_authority",
                  side_effect=_spy("resolve_items")),
            patch("agents.glossary_match.match_glossary",
                  side_effect=_spy("glossary_items")),
            patch("agents.glossary_match.save_topic_labels"),
            patch("agents.glossary_match.flag_glossary_gaps"),
            patch("agents.law_ref_matcher.match_law_refs",
                  side_effect=_spy("law_items")),
            patch("agents.law_ref_matcher.save_law_matches"),
            patch("agents.compare_news.reconcile_by_act_ref",
                  side_effect=_spy("reconcile_items")),
            patch("agents.announcement_agent.match_rcm_titles",
                  side_effect=_rcm_spy),
            patch("agents.impact_gate.assess_impact",
                  side_effect=_spy("impact_items")),
            patch("agents.timing.apply_timing",
                  side_effect=_spy("timing_items")),
            patch("agents.news_ranker.rank_items",
                  side_effect=_spy("rank_items")),
            # --- Persistence ---
            patch("configurations.config_loader.add_news_item"),
            patch("configurations.db.update_news_fields"),
            patch("agents.compare_news._build_item_record",
                  side_effect=lambda it: {"title": it.get("title", "")}),
            # --- Email ---
            patch("agents.agents_controller.send_email", return_value=True),
        ]:
            stack.enter_context(p)
        yield


# ---------------------------------------------------------------------------
# Helper to call run_profile_once
# ---------------------------------------------------------------------------

def _run(all_items, compare_result, captured=None, **kwargs):
    """Run run_profile_once inside the mock context."""
    if captured is None:
        captured = {}
    with _mock_run(all_items, compare_result, captured):
        from agents.agents_controller import run_profile_once
        result = run_profile_once(1, **kwargs)
    return result, captured


# ---------------------------------------------------------------------------
# Test 1 (mandatory): 1 NEW + 1 DUPLICATE — routing contract
# ---------------------------------------------------------------------------
def test_new_and_dup_routing():
    """
    Core routing contract: expensive stages receive only the NEW item;
    both items remain persisted (the compare mock was called with all_items).
    """
    new = _make_item("New payroll law", "https://example.com/new")
    dup = _make_item("Duplicate article", "https://example.com/dup",
                     dedup_status="duplicate")

    all_items      = [new, dup]
    compare_result = {"new_items": [new], "update_items": []}
    captured       = {}

    result, captured = _run(all_items, compare_result, captured)

    assert result is True, f"run_profile_once returned {result!r}"

    # L2 Fetch must be called with exactly the NEW item
    assert "l2_items" in captured, "run_l2_fetch was never called"
    assert len(captured["l2_items"]) == 1, (
        f"L2 Fetch received {len(captured['l2_items'])} items; expected 1 (new only)"
    )
    assert captured["l2_items"][0]["dedup_status"] == "new"

    # Reconcile must receive only the NEW item
    assert "reconcile_items" in captured, "reconcile_by_act_ref was never called"
    assert len(captured["reconcile_items"]) == 1

    # Glossary Match must receive only the NEW item
    assert "glossary_items" in captured, "match_glossary was never called"
    assert len(captured["glossary_items"]) == 1

    # Law Match must receive only the NEW item
    assert "law_items" in captured, "match_law_refs was never called"
    assert len(captured["law_items"]) == 1

    # Rank must receive only the NEW item
    assert "rank_items" in captured, "rank_items was never called"
    assert len(captured["rank_items"]) == 1
    assert captured["rank_items"][0]["dedup_status"] == "new"

    print("✅ Test 1 passed: new+dup routing — expensive stages receive only new items")


# ---------------------------------------------------------------------------
# Test 2: DUPLICATE item is not email-eligible; NEW item can be
# ---------------------------------------------------------------------------
def test_duplicate_not_email_eligible():
    """
    DUPLICATE must have email_eligible=0 (or unset).
    A NEW item ranked above threshold must be email_eligible=1.
    """
    new = _make_item("High-rank new law", "https://example.com/new-hr")
    dup = _make_item("Dup article",       "https://example.com/dup-hr",
                     dedup_status="duplicate")

    all_items      = [new, dup]
    compare_result = {"new_items": [new], "update_items": []}
    captured       = {}

    # Override rank spy to set a high rank on the new item
    def rank_spy_high(items, *a, **kw):
        captured["rank_items"] = list(items)
        for it in items:
            it["significance_rank"] = 4

    with _mock_run(all_items, compare_result, captured):
        with patch("agents.news_ranker.rank_items", side_effect=rank_spy_high):
            from agents.agents_controller import run_profile_once
            result = run_profile_once(1)

    assert result is True

    # DUPLICATE must never become email-eligible
    assert dup.get("email_eligible") != 1, (
        "DUPLICATE item must not have email_eligible=1"
    )

    # NEW item with rank=4 above threshold=3 must be eligible
    assert new.get("email_eligible") == 1, (
        f"NEW item with rank=4 should be email_eligible=1, got {new.get('email_eligible')}"
    )

    print("✅ Test 2 passed: DUPLICATE not email-eligible; NEW rank≥threshold is eligible")


# ---------------------------------------------------------------------------
# Test 3: All DUPLICATE — no unnecessary AI calls, no crash
# ---------------------------------------------------------------------------
def test_all_duplicate_no_ai_calls():
    """
    When every collected item is a DUPLICATE, the pipeline must complete
    without errors and without calling any expensive AI stage.
    """
    dup1 = _make_item("Dup one", "https://example.com/d1", dedup_status="duplicate")
    dup2 = _make_item("Dup two", "https://example.com/d2", dedup_status="duplicate")

    all_items      = [dup1, dup2]
    compare_result = {"new_items": [], "update_items": []}
    captured       = {}

    result, captured = _run(all_items, compare_result, captured)

    assert result is True, f"run_profile_once failed with all-duplicate input: {result!r}"

    # No expensive AI call should receive any item
    assert captured.get("l2_items",       []) == [], "L2 Fetch must not receive duplicate items"
    assert captured.get("reconcile_items",[]) == [], "Reconcile must not receive duplicate items"
    assert captured.get("glossary_items", []) == [], "Glossary Match must not receive duplicate items"
    assert captured.get("law_items",      []) == [], "Law Match must not receive duplicate items"
    assert captured.get("rank_items",     []) == [], "Rank must not receive duplicate items"
    assert captured.get("impact_items",   []) == [], "Impact Gate must not receive duplicate items"
    assert captured.get("timing_items",   []) == [], "Timing must not receive duplicate items"
    assert captured.get("rcm_items",      []) == [], "RCM Match must not receive duplicate items"

    print("✅ Test 3 passed: all-duplicate input → no AI calls, no crash")


# ---------------------------------------------------------------------------
# Test 4: All NEW — all items flow through the full pipeline
# ---------------------------------------------------------------------------
def test_all_new_full_pipeline():
    """
    When all items are NEW, every expensive stage receives every item.
    """
    new1 = _make_item("New regulation A", "https://example.com/a")
    new2 = _make_item("New regulation B", "https://example.com/b")

    all_items      = [new1, new2]
    compare_result = {"new_items": [new1, new2], "update_items": []}
    captured       = {}

    result, captured = _run(all_items, compare_result, captured)

    assert result is True
    assert len(captured.get("l2_items",       [])) == 2
    assert len(captured.get("reconcile_items",[])) == 2
    assert len(captured.get("glossary_items", [])) == 2
    assert len(captured.get("law_items",      [])) == 2
    assert len(captured.get("rank_items",     [])) == 2

    print("✅ Test 4 passed: all-new input → all items through full pipeline")


# ---------------------------------------------------------------------------
# Test 5: skip_comparison=True → all items treated as NEW
# ---------------------------------------------------------------------------
def test_skip_comparison_all_new():
    """
    With skip_comparison=True, compare_news returns all items as NEW.
    The controller must pass all of them to expensive stages.
    """
    item1 = _make_item("Item one", "https://example.com/i1")
    item2 = _make_item("Item two", "https://example.com/i2")
    item1["dedup_status"] = "new"
    item2["dedup_status"] = "new"

    all_items      = [item1, item2]
    compare_result = {"new_items": [item1, item2], "update_items": []}
    captured       = {}

    result, captured = _run(all_items, compare_result, captured,
                            skip_comparison=True)

    assert result is True
    assert len(captured.get("l2_items", [])) == 2, (
        "skip_comparison=True: both items must reach L2 Fetch"
    )
    assert len(captured.get("rank_items", [])) == 2

    print("✅ Test 5 passed: skip_comparison=True → all items reach analysis")


# ---------------------------------------------------------------------------
# Test 6: update_items wiring is removed — no residual update handling
# ---------------------------------------------------------------------------
def test_update_items_are_not_routed():
    """
    update_items is permanently empty after Task 4A.  The controller must not
    add update_items to the pipeline or to the email digest.

    Simulates a rogue compare_news that returns update_items (should be
    ignored by the controller).
    """
    new = _make_item("Real new article", "https://example.com/real")
    phantom_update = _make_item("Should not appear", "https://example.com/phantom")
    phantom_update["dedup_status"] = "update"   # rogue — should be dropped

    all_items = [new]
    # compare_result with a non-empty update_items (rogue)
    compare_result = {"new_items": [new], "update_items": [phantom_update]}
    captured       = {}

    result, captured = _run(all_items, compare_result, captured)

    assert result is True

    # L2 must receive only the NEW item, not the phantom update
    l2 = captured.get("l2_items", [])
    assert len(l2) == 1, f"Expected 1 item for L2; got {len(l2)}"
    assert l2[0]["dedup_status"] == "new"

    # Rank must also see only the new item
    rk = captured.get("rank_items", [])
    assert len(rk) == 1

    print("✅ Test 6 passed: update_items ignored — only new_items reach pipeline")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_new_and_dup_routing,
        test_duplicate_not_email_eligible,
        test_all_duplicate_no_ai_calls,
        test_all_new_full_pipeline,
        test_skip_comparison_all_new,
        test_update_items_are_not_routed,
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
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed:
        sys.exit(1)
