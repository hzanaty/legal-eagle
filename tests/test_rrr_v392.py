"""V3.92 RRR Learning & Matching — corrective-patch acceptance tests (v3.92.1).

Acceptance criteria tested:
 1.  rrr_rules table is created by create_schema_if_needed
 2.  insert_rrr_rule writes a row with all required fields
 3.  list_rrr_rules returns active rules only by default
 4.  deactivate_rrr_rule sets active=0
 5.  news_items.pre_rrr_rank / rrr_rule_id / rrr_match_outcome columns exist
 6.  Eligibility: rank 1 items are never evaluated by RRR Match
 7.  Eligibility: _RRR_ALLOWED_TARGETS from real app module (not a copy)
 8.  Rule generation returns {why, when, when_not, sufficient, readiness}
 8b. validate_rule_sections blocks failure text and placeholders
 9.  RRR Match applies upgrade when one APPLY verdict fires
10.  RRR Match preserves rank when DO_NOT_APPLY
11.  RRR Match preserves rank when INSUFFICIENT_EVIDENCE
12.  RRR Match preserves rank + flags conflict for two APPLY verdicts with different targets
12b. persist_rrr_outcomes writes pre_rrr_rank for ALL non-dup items, outcomes for matched
12c. pre_rrr_rank written even for items that received no RRR adjustment
13.  Direction: upgrade rule (3→4) must not apply to rank 5 item
14.  Direction: downgrade rule (4→2) must not apply to rank 2 item
R1.  list_all_news_for_review SELECT returns pre_rrr_rank + rrr_rule_id
R2.  Route: challenge returns allowed_targets, rejects rank 1
R3.  Route: confirm-challenge enforces eligibility (1→4 rejected, 2→3 rejected, 2→4 accepted)
R4.  Route: confirm-challenge rejects empty reason
R5.  Route: /override enforces same eligibility (no bypass)
R6.  Route: /override requires reason
"""
import json
import os
import sqlite3
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import (
    create_schema_if_needed,
    deactivate_rrr_rule,
    insert_rrr_rule,
    list_rrr_rules,
    persist_rrr_outcomes,
    list_all_news_for_review,
)

PROFILE_ID = 1


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema_if_needed(conn)
    conn.execute(
        "INSERT INTO profiles(id,country_code,lob,name,active) VALUES(1,'XN','HCM','test',1)"
    )
    conn.commit()
    return conn


def _insert_news_item(conn, *, rank=3, source_id="s1", url="http://x.com/1",
                       hash_sig="h1", dedup_status="new", rank_tier="auto"):
    conn.execute("""
        INSERT INTO news_items
          (profile_id,source_type,source_id,url,title,content,
           first_seen_at,last_seen_at,hash_signature,significance_rank,dedup_status,rank_tier)
        VALUES (1,'rss',?,?,?,'Content',
                datetime('now'),datetime('now'),?,?,?,?)
    """, (source_id, url, f"Title for {source_id}", hash_sig, rank, dedup_status, rank_tier))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ─── Criteria 1–5: DB schema ────────────────────────────────────────────────

def test_rrr_rules_table_created():
    conn = _mem_db()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "rrr_rules" in tables


def test_insert_and_list_rrr_rules():
    conn = _mem_db()
    rid = insert_rrr_rule(conn, PROFILE_ID, None, 3, 4,
                          "New law affects payroll", "WHY text", "WHEN text", "WHEN NOT text")
    assert rid > 0
    rules = list_rrr_rules(conn, PROFILE_ID)
    assert len(rules) == 1
    assert rules[0]["why_text"] == "WHY text"
    assert rules[0]["active"] == 1


def test_list_rrr_rules_active_only():
    conn = _mem_db()
    rid = insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "r", "w", "wh", "whn")
    deactivate_rrr_rule(conn, rid)
    assert list_rrr_rules(conn, PROFILE_ID, active_only=True) == []
    assert len(list_rrr_rules(conn, PROFILE_ID, active_only=False)) == 1


def test_deactivate_rrr_rule():
    conn = _mem_db()
    rid = insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "r", "w", "wh", "whn")
    deactivate_rrr_rule(conn, rid)
    row = conn.execute("SELECT active FROM rrr_rules WHERE id=?", (rid,)).fetchone()
    assert row["active"] == 0


def test_news_items_rrr_columns_exist():
    conn = _mem_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(news_items)").fetchall()]
    assert "pre_rrr_rank" in cols
    assert "rrr_rule_id" in cols
    assert "rrr_match_outcome" in cols


# ─── Criteria 6–7: Eligibility ──────────────────────────────────────────────

def test_rrr_match_skips_rank_1():
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    item = {"profile_id": PROFILE_ID, "significance_rank": 1,
            "title": "Noise item", "dedup_status": "new", "impact_evidence_json": "[]"}
    run_rrr_match([item], PROFILE_ID, conn)
    assert item.get("rrr_match_outcome") is None
    assert item.get("pre_rrr_rank") is None


def test_eligibility_uses_real_app_constant():
    """_RRR_ALLOWED_TARGETS is imported from admin.app (not a copied dict)."""
    from admin.app import _RRR_ALLOWED_TARGETS
    assert 3 not in _RRR_ALLOWED_TARGETS.get(2, set()), "rank2→3 must not be allowed"
    assert 4 in _RRR_ALLOWED_TARGETS.get(2, set()), "rank2→4 must be allowed"
    assert 1 not in _RRR_ALLOWED_TARGETS, "rank 1 must have no allowed targets"
    # Verify it is a dict, not a set copy
    assert isinstance(_RRR_ALLOWED_TARGETS, dict)
    assert isinstance(next(iter(_RRR_ALLOWED_TARGETS.values())), set)


# ─── Criteria 8–8b: Rule generation + readiness ─────────────────────────────

def test_generate_rrr_rule_returns_readiness():
    from agents.rrr_generator import generate_rrr_rule

    item = {
        "title": "New minimum wage regulation effective March 2027",
        "l2_summary": "Ministry of Labour announced a 15% minimum wage increase effective 2027-03-01.",
        "impact_evidence_json": json.dumps(["Article 3: minimum monthly wage set to 1500 XNR"]),
        "topic_label": json.dumps(["Minimum Wage"]),
        "law_references_json": json.dumps([{"type": "decree", "number": "2026-441", "label": ""}]),
        "significance_rank": 3,
        "profile_id": PROFILE_ID,
    }

    mock_response = json.dumps({
        "readiness": "ok",
        "why": "This regulation directly sets minimum wage rates affecting payroll calculations.",
        "when": "- Decree or regulation explicitly sets a new minimum wage rate\n- Stated effective date is present",
        "when_not": "- General announcements without a confirmed effective date\n- Commentary on proposed changes",
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )

    with patch("agents.rrr_generator._ai_client", return_value=mock_client), \
         patch("agents.rrr_generator.cached_chat", side_effect=lambda p, fn: fn()):
        rule = generate_rrr_rule(item, override_rank=4, human_reason="Payroll impact confirmed")

    assert rule["sufficient"] is True
    assert rule["readiness"] == "ok"
    assert rule["why"] and rule["when"] and rule["when_not"]


def test_generate_rrr_rule_insufficient_readiness():
    from agents.rrr_generator import generate_rrr_rule

    item = {"title": "Vague government notice", "significance_rank": 3}
    mock_response = json.dumps({
        "readiness": "insufficient",
        "why": "INSUFFICIENT: missing regulatory subject and effective date",
        "when": "- N/A",
        "when_not": "- N/A",
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )

    with patch("agents.rrr_generator._ai_client", return_value=mock_client), \
         patch("agents.rrr_generator.cached_chat", side_effect=lambda p, fn: fn()):
        rule = generate_rrr_rule(item, override_rank=4, human_reason="Unclear")

    assert rule["sufficient"] is False
    assert rule["readiness"] in ("insufficient", "failed")


def test_validate_rule_sections_blocks_failure_text():
    from agents.rrr_generator import validate_rule_sections
    assert validate_rule_sections("INSUFFICIENT: missing facts", "- when", "- when_not") is not None
    assert validate_rule_sections("n/a", "- when", "- when_not") is not None
    assert validate_rule_sections("rule generation failed", "- when", "- when_not") is not None


def test_validate_rule_sections_blocks_placeholders():
    from agents.rrr_generator import validate_rule_sections
    assert validate_rule_sections("Valid why", "- TBD", "- when_not") is not None
    assert validate_rule_sections("Valid why", "- [insert condition]", "- when_not") is not None


def test_validate_rule_sections_accepts_valid():
    from agents.rrr_generator import validate_rule_sections
    assert validate_rule_sections(
        "This affects payroll for HCM in XN.",
        "- Article contains minimum wage rate change\n- Effective date present",
        "- Change is a consultation only\n- No effective date stated",
    ) is None


def test_validate_rule_sections_blocks_empty():
    from agents.rrr_generator import validate_rule_sections
    assert validate_rule_sections("", "- when", "- when_not") is not None
    assert validate_rule_sections("Valid why", "", "- when_not") is not None


# ─── Criteria 9–12b: RRR Match verdict logic + persist ──────────────────────

def _make_item(rank: int, title: str = "Test item", source_id: str = "s1") -> Dict[str, Any]:
    return {
        "id": None,
        "profile_id": PROFILE_ID,
        "significance_rank": rank,
        "title": title,
        "l2_summary": "Summary of " + title,
        "impact_evidence_json": "[]",
        "law_references_json": "[]",
        "topic_label": '["General"]',
        "dedup_status": "new",
        "source_type": "rss",
        "source_id": source_id,
        "url": f"http://x.com/{source_id}",
        "hash_signature": f"h_{source_id}",
    }


def _mock_client_with_response(response_json: str) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=response_json))]
    )
    return client


def test_rrr_match_applies_upgrade_on_apply_verdict():
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "Payroll", "why",
                    "- minimum wage mentioned", "- no effective date stated")
    conn.commit()
    item = _make_item(rank=3, title="New minimum wage announced", source_id="s1")

    rules = list_rrr_rules(conn, PROFILE_ID)
    resp = json.dumps([{"rule_id": rules[0]["id"], "verdict": "APPLY", "reasoning": "matched"}])
    with patch("agents.rrr_matcher._ai_client", return_value=_mock_client_with_response(resp)), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda p, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 4
    assert item["pre_rrr_rank"] == 3
    assert item["rrr_match_outcome"] == "upgraded"


def test_rrr_match_preserves_on_do_not_apply():
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "Payroll", "why", "- minimum wage", "- none")
    conn.commit()
    item = _make_item(rank=3, title="Unrelated news")

    rules = list_rrr_rules(conn, PROFILE_ID)
    resp = json.dumps([{"rule_id": rules[0]["id"], "verdict": "DO_NOT_APPLY", "reasoning": "not matching"}])
    with patch("agents.rrr_matcher._ai_client", return_value=_mock_client_with_response(resp)), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda p, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 3
    assert item.get("rrr_match_outcome") is None


def test_rrr_match_insufficient_evidence_does_not_change_rank():
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "Payroll", "why", "- minimum wage", "- none")
    conn.commit()
    item = _make_item(rank=3, title="Ambiguous regulatory notice")

    rules = list_rrr_rules(conn, PROFILE_ID)
    resp = json.dumps([{"rule_id": rules[0]["id"], "verdict": "INSUFFICIENT_EVIDENCE",
                         "reasoning": "article lacks product scope info"}])
    with patch("agents.rrr_matcher._ai_client", return_value=_mock_client_with_response(resp)), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda p, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 3
    assert item.get("rrr_match_outcome") is None


def test_rrr_match_conflict_preserves_rank():
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "r1", "why1", "- kw", "- none")
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 5, "r2", "why2", "- kw", "- none")
    conn.commit()
    item = _make_item(rank=3)

    rules = list_rrr_rules(conn, PROFILE_ID)
    resp = json.dumps([
        {"rule_id": rules[0]["id"], "verdict": "APPLY", "reasoning": "match"},
        {"rule_id": rules[1]["id"], "verdict": "APPLY", "reasoning": "also match"},
    ])
    with patch("agents.rrr_matcher._ai_client", return_value=_mock_client_with_response(resp)), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda p, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 3, "Conflict must preserve initial rank"
    assert item["rrr_match_outcome"] == "conflict"
    assert item.get("rrr_rule_id") is None


def test_persist_rrr_outcomes_writes_pre_rrr_rank_for_all_items():
    """persist_rrr_outcomes writes pre_rrr_rank even when no RRR adjustment occurred."""
    conn = _mem_db()
    item_id = _insert_news_item(conn, rank=3, source_id="s1")

    # Item stamped with pre_rrr_rank but no RRR outcome
    item = {
        "significance_rank": 3,
        "pre_rrr_rank": 3,
        "rrr_rule_id": None,
        "rrr_match_outcome": None,
        "source_type": "rss",
        "source_id": "s1",
    }
    persist_rrr_outcomes(conn, [item], PROFILE_ID)
    conn.commit()

    row = dict(conn.execute("SELECT * FROM news_items WHERE id=?", (item_id,)).fetchone())
    assert row["pre_rrr_rank"] == 3, "pre_rrr_rank must be persisted even without RRR adjustment"
    assert row["rrr_rule_id"] is None
    assert row["rrr_match_outcome"] is None
    assert row["rank_tier"] != "rrr", "rank_tier must not be 'rrr' for unmatched item"


def test_persist_rrr_outcomes_writes_upgrade_columns():
    """persist_rrr_outcomes writes all columns including rank_tier='rrr' for upgraded items."""
    conn = _mem_db()
    rid = insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "reason", "why", "- when", "- not")
    conn.commit()
    item_id = _insert_news_item(conn, rank=3, source_id="s2")

    item = {
        "significance_rank": 4,
        "pre_rrr_rank": 3,
        "rrr_rule_id": rid,
        "rrr_match_outcome": "upgraded",
        "source_type": "rss",
        "source_id": "s2",
    }
    persist_rrr_outcomes(conn, [item], PROFILE_ID)
    conn.commit()

    row = dict(conn.execute("SELECT * FROM news_items WHERE id=?", (item_id,)).fetchone())
    assert row["significance_rank"] == 4
    assert row["pre_rrr_rank"] == 3
    assert row["rrr_rule_id"] == rid
    assert row["rrr_match_outcome"] == "upgraded"
    assert row["rank_tier"] == "rrr"


def test_persist_rrr_outcomes_does_not_overwrite_pre_rrr_rank_with_final():
    """Second persist_rrr_outcomes call must not corrupt pre_rrr_rank."""
    conn = _mem_db()
    item_id = _insert_news_item(conn, rank=4, source_id="s3")

    # Simulate first persist: initial rank=3, upgraded to 4
    conn.execute("UPDATE news_items SET significance_rank=4, pre_rrr_rank=3 WHERE id=?", (item_id,))
    conn.commit()

    # A second persist with the same item dict should not change pre_rrr_rank
    item = {
        "significance_rank": 4,
        "pre_rrr_rank": 3,
        "rrr_rule_id": None,
        "rrr_match_outcome": None,
        "source_type": "rss",
        "source_id": "s3",
    }
    persist_rrr_outcomes(conn, [item], PROFILE_ID)
    conn.commit()

    row = dict(conn.execute("SELECT * FROM news_items WHERE id=?", (item_id,)).fetchone())
    assert row["pre_rrr_rank"] == 3, "pre_rrr_rank must not be overwritten with final rank"
    assert row["significance_rank"] == 4


# ─── Criteria 13–14: Direction guard ────────────────────────────────────────

def test_upgrade_rule_does_not_downgrade_higher_rank():
    from agents.rrr_matcher import run_rrr_match, _rule_eligible_for_item
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "Payroll", "why", "- minimum wage", "- none")
    conn.commit()

    rule = list_rrr_rules(conn, PROFILE_ID)[0]
    assert not _rule_eligible_for_item(rule, initial_rank=5)

    item = _make_item(rank=5, title="Critical emergency decree")
    run_rrr_match([item], PROFILE_ID, conn)
    assert item["significance_rank"] == 5
    assert item.get("rrr_match_outcome") is None


def test_downgrade_rule_does_not_apply_at_or_below_target():
    from agents.rrr_matcher import run_rrr_match, _rule_eligible_for_item
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 4, 2, "Not relevant", "why", "- no change", "- none")
    conn.commit()

    rule = list_rrr_rules(conn, PROFILE_ID)[0]
    assert not _rule_eligible_for_item(rule, initial_rank=2)

    item = _make_item(rank=2, title="Central bank policy")
    run_rrr_match([item], PROFILE_ID, conn)
    assert item["significance_rank"] == 2
    assert item.get("rrr_match_outcome") is None


# ─── R1: Review query returns audit columns ──────────────────────────────────

def test_list_all_news_for_review_returns_rrr_columns():
    """list_all_news_for_review SELECT must contain pre_rrr_rank and rrr_rule_id."""
    import inspect
    from configurations import db as db_module
    src = inspect.getsource(db_module.list_all_news_for_review)
    assert "pre_rrr_rank" in src, "list_all_news_for_review SELECT must include pre_rrr_rank"
    assert "rrr_rule_id" in src, "list_all_news_for_review SELECT must include rrr_rule_id"
    assert "rrr_match_outcome" in src, "list_all_news_for_review SELECT must include rrr_match_outcome"


# ─── R2–R6: Route tests using real Flask test client ────────────────────────

def _app_with_test_db():
    """Spin up the Flask app with a temp DB so routes can be tested without a live config."""
    import tempfile, importlib, os
    # Create an isolated DB file
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    # Patch get_connection to return a connection to our temp DB
    import sqlite3 as _sq3
    from configurations.db import create_schema_if_needed

    def _get_conn():
        c = _sq3.connect(db_path)
        c.row_factory = _sq3.Row
        c.execute("PRAGMA foreign_keys = ON")
        create_schema_if_needed(c)
        return c

    # Seed profile + item
    seed = _get_conn()
    seed.execute("INSERT OR IGNORE INTO profiles(id,country_code,lob,name,active) VALUES(1,'XN','HCM','test',1)")
    seed.commit()
    seed.close()

    import admin.app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False

    old_gc = app_module.get_connection
    app_module.get_connection = _get_conn

    client = app_module.app.test_client()
    return client, _get_conn, lambda: (setattr(app_module, "get_connection", old_gc), os.unlink(db_path))


def _seed_item(get_conn, rank=3, dedup_status="new"):
    conn = get_conn()
    conn.execute("""
        INSERT INTO news_items
          (profile_id,source_type,source_id,url,title,content,
           first_seen_at,last_seen_at,hash_signature,significance_rank,dedup_status)
        VALUES (1,'rss','x','http://x.com/x','Title','Content',
                datetime('now'),datetime('now'),'hx',?,?)
    """, (rank, dedup_status))
    conn.commit()
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return item_id


def test_route_challenge_rejects_rank_1():
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=1)
        resp = client.post(f"/admin/news/{item_id}/challenge",
                           content_type="application/json")
        data = json.loads(resp.data)
        assert not data["ok"], f"Rank 1 challenge must be rejected, got: {data}"
    finally:
        cleanup()


def test_route_challenge_returns_allowed_targets_for_rank_2():
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=2)
        resp = client.post(f"/admin/news/{item_id}/challenge",
                           content_type="application/json")
        data = json.loads(resp.data)
        assert data["ok"], f"Rank 2 challenge must succeed, got: {data}"
        assert set(data["allowed_targets"]) == {4, 5}
    finally:
        cleanup()


def test_route_confirm_rejects_rank1_to_4():
    """Backend eligibility guard: rank 1 → 4 must fail."""
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=1)
        resp = client.post(f"/admin/news/{item_id}/confirm-challenge",
                           json={"override_rank": 4, "override_reason": "test", "create_rule": False})
        data = json.loads(resp.data)
        assert not data["ok"], "Rank 1→4 must be rejected"
    finally:
        cleanup()


def test_route_confirm_rejects_rank2_to_3():
    """Rank 2 → 3 is not in the approved transition matrix."""
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=2)
        resp = client.post(f"/admin/news/{item_id}/confirm-challenge",
                           json={"override_rank": 3, "override_reason": "test", "create_rule": False})
        data = json.loads(resp.data)
        assert not data["ok"], "Rank 2→3 must be rejected"
    finally:
        cleanup()


def test_route_confirm_accepts_rank2_to_4():
    """Rank 2 → 4 is a valid transition."""
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=2)
        with patch("admin.app.get_setting_value", return_value="3"):
            resp = client.post(f"/admin/news/{item_id}/confirm-challenge",
                               json={"override_rank": 4, "override_reason": "Valid reason",
                                     "create_rule": False})
        data = json.loads(resp.data)
        assert data.get("ok"), f"Rank 2→4 must succeed, got: {data}"
    finally:
        cleanup()


def test_route_confirm_rejects_empty_reason():
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=3)
        resp = client.post(f"/admin/news/{item_id}/confirm-challenge",
                           json={"override_rank": 4, "override_reason": "", "create_rule": False})
        data = json.loads(resp.data)
        assert not data["ok"], "Empty reason must be rejected"
    finally:
        cleanup()


def test_route_override_rejects_rank1():
    """Legacy /override endpoint must enforce the same eligibility as confirm-challenge."""
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=1)
        resp = client.post(f"/admin/news/{item_id}/override",
                           json={"rank": 4, "reason": "test reason"})
        data = json.loads(resp.data)
        assert not data["ok"], "Legacy /override must reject rank 1 items"
    finally:
        cleanup()


def test_route_override_requires_reason():
    """Legacy /override endpoint must require a reason — no silent bypass."""
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=3)
        resp = client.post(f"/admin/news/{item_id}/override",
                           json={"rank": 4})
        data = json.loads(resp.data)
        assert not data["ok"], "/override without reason must be rejected"
    finally:
        cleanup()


def test_route_override_rejects_invalid_transition():
    """Legacy /override with rank 2→3 (invalid) must be rejected."""
    client, get_conn, cleanup = _app_with_test_db()
    try:
        item_id = _seed_item(get_conn, rank=2)
        resp = client.post(f"/admin/news/{item_id}/override",
                           json={"rank": 3, "reason": "bad transition"})
        data = json.loads(resp.data)
        assert not data["ok"], "/override rank 2→3 must be rejected"
    finally:
        cleanup()
