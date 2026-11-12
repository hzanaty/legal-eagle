"""V3.92 RRR Learning & Matching — acceptance tests.

Mandatory acceptance criteria:
 1. rrr_rules table is created by create_schema_if_needed
 2. insert_rrr_rule writes a row with all required fields
 3. list_rrr_rules returns active rules only by default
 4. deactivate_rrr_rule sets active=0
 5. news_items.pre_rrr_rank / rrr_rule_id / rrr_match_outcome columns exist after schema migration
 6. Eligibility: rank 1 items are never evaluated by RRR Match
 7. Eligibility: invalid override targets are rejected (allowed-targets table assertion)
 8. Rule generation returns {why, when, when_not, sufficient} JSON with all keys
 9. RRR Match applies upgrade when one rule APPLY verdict fires
10. RRR Match preserves rank when no rule applies (DO_NOT_APPLY verdict)
11. RRR Match preserves rank and flags conflict when two rules produce APPLY with different targets
12. Pipeline persist: pre_rrr_rank and rrr_match_outcome are written to DB
13. Direction: upgrade rule (3→4) must not be applied to rank 5 item
14. Direction: downgrade rule (4→2) must not be applied to rank 2 item
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


# ─── Criteria 1–5: DB schema ────────────────────────────────────────────────

def test_rrr_rules_table_created():
    conn = _mem_db()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "rrr_rules" in tables, "rrr_rules table not created"


def test_insert_and_list_rrr_rules():
    conn = _mem_db()
    rid = insert_rrr_rule(
        conn, PROFILE_ID, None, 3, 4,
        "New law affects payroll",
        "WHY text", "WHEN text", "WHEN NOT text",
    )
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
    assert "pre_rrr_rank" in cols, "pre_rrr_rank column missing"
    assert "rrr_rule_id" in cols, "rrr_rule_id column missing"
    assert "rrr_match_outcome" in cols, "rrr_match_outcome column missing"


# ─── Criteria 6–7: Eligibility ──────────────────────────────────────────────

def test_rrr_match_skips_rank_1():
    """Rank 1 items are never evaluated — no audit columns set."""
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    item = {"id": None, "profile_id": PROFILE_ID, "significance_rank": 1,
            "title": "Noise item", "dedup_status": "new", "impact_evidence_json": "[]"}
    run_rrr_match([item], PROFILE_ID, conn)
    assert item.get("rrr_match_outcome") is None
    assert item.get("pre_rrr_rank") is None


def test_eligibility_invalid_target_rejected():
    """Verify the allowed-targets constant excludes invalid combinations."""
    from admin.app import _RRR_ALLOWED_TARGETS
    assert 3 not in _RRR_ALLOWED_TARGETS.get(2, set()), "rank2→3 must not be allowed"
    assert 4 in _RRR_ALLOWED_TARGETS.get(2, set()), "rank2→4 must be allowed"
    assert 1 not in _RRR_ALLOWED_TARGETS, "rank 1 must have no allowed targets"


# ─── Criterion 8: Rule generation contract ──────────────────────────────────

def test_generate_rrr_rule_structure():
    """Generator returns {why, when, when_not, sufficient} with non-empty strings."""
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
        "why": "This regulation directly sets minimum wage rates affecting payroll calculations.",
        "when": "- Decree or regulation explicitly sets a new minimum wage rate\n- Stated effective date is present",
        "when_not": "- General announcements without a confirmed effective date\n- Commentary on proposed changes",
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )

    with patch("agents.rrr_generator._ai_client", return_value=mock_client), \
         patch("agents.rrr_generator.cached_chat", side_effect=lambda prompt, fn: fn()):
        rule = generate_rrr_rule(item, override_rank=4, human_reason="Payroll impact confirmed")

    assert isinstance(rule, dict), "Expected dict"
    assert "why" in rule and rule["why"], "Missing why"
    assert "when" in rule and rule["when"], "Missing when"
    assert "when_not" in rule and rule["when_not"], "Missing when_not"
    assert "sufficient" in rule, "Missing sufficient"
    assert rule["sufficient"] is True, "Expected sufficient=True for valid rule"


def test_generate_rrr_rule_insufficient():
    """Generator marks insufficient rules; they must not be saved as active rules."""
    from agents.rrr_generator import generate_rrr_rule, is_rule_sufficient

    item = {"title": "Vague government notice", "significance_rank": 3}
    mock_response = json.dumps({
        "why": "INSUFFICIENT: missing regulatory subject, jurisdiction, and effective date",
        "when": "- N/A",
        "when_not": "- N/A",
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )

    with patch("agents.rrr_generator._ai_client", return_value=mock_client), \
         patch("agents.rrr_generator.cached_chat", side_effect=lambda prompt, fn: fn()):
        rule = generate_rrr_rule(item, override_rank=4, human_reason="Unclear")

    assert rule["sufficient"] is False, "Expected sufficient=False for failure-prefixed rule"
    assert not is_rule_sufficient(rule["why"], rule["when"], rule["when_not"])


# ─── Criteria 9–11: RRR Match verdict logic ─────────────────────────────────

def _make_item(rank: int, title: str = "Test item") -> Dict[str, Any]:
    return {
        "id": None,
        "profile_id": PROFILE_ID,
        "significance_rank": rank,
        "title": title,
        "l2_summary": "Summary of " + title,
        "impact_evidence_json": "[]",
        "topic_label": '["General"]',
        "dedup_status": "new",
    }


def test_rrr_match_applies_upgrade_on_apply_verdict():
    """APPLY verdict from a single rule upgrades the rank."""
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4,
                    "Payroll impact", "Payroll why",
                    "- minimum wage mentioned", "- no effective date stated")
    conn.commit()
    item = _make_item(rank=3, title="New minimum wage announced")

    rules = list_rrr_rules(conn, PROFILE_ID)
    mock_response = json.dumps([
        {"rule_id": rules[0]["id"], "verdict": "APPLY", "reasoning": "Minimum wage mentioned"}
    ])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )
    with patch("agents.rrr_matcher._ai_client", return_value=mock_client), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda prompt, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 4, f"Expected 4, got {item['significance_rank']}"
    assert item["pre_rrr_rank"] == 3
    assert item["rrr_match_outcome"] == "upgraded"


def test_rrr_match_preserves_on_do_not_apply():
    """DO_NOT_APPLY verdict — rank unchanged, no audit columns set."""
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "Payroll", "why", "- minimum wage", "- none")
    conn.commit()
    item = _make_item(rank=3, title="Unrelated central bank news")

    rules = list_rrr_rules(conn, PROFILE_ID)
    mock_response = json.dumps([
        {"rule_id": rules[0]["id"], "verdict": "DO_NOT_APPLY", "reasoning": "Not matching"}
    ])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )
    with patch("agents.rrr_matcher._ai_client", return_value=mock_client), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda prompt, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 3, "Rank must be unchanged"
    assert item.get("rrr_match_outcome") is None, "No outcome for non-match"


def test_rrr_match_insufficient_evidence_does_not_change_rank():
    """INSUFFICIENT_EVIDENCE verdict — rank unchanged (logged but ignored)."""
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "Payroll", "why", "- minimum wage", "- none")
    conn.commit()
    item = _make_item(rank=3, title="Ambiguous regulatory notice")

    rules = list_rrr_rules(conn, PROFILE_ID)
    mock_response = json.dumps([
        {"rule_id": rules[0]["id"], "verdict": "INSUFFICIENT_EVIDENCE",
         "reasoning": "Article lacks jurisdiction and effective date details"}
    ])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )
    with patch("agents.rrr_matcher._ai_client", return_value=mock_client), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda prompt, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 3, "INSUFFICIENT_EVIDENCE must not change rank"
    assert item.get("rrr_match_outcome") is None


def test_rrr_match_conflict_preserves_rank():
    """Two rules with conflicting APPLY verdicts → preserve initial rank, flag conflict."""
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "r1", "why1", "- keyword", "- none")
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 5, "r2", "why2", "- keyword", "- none")
    conn.commit()
    item = _make_item(rank=3, title="Item with keyword")

    rules = list_rrr_rules(conn, PROFILE_ID)
    mock_response = json.dumps([
        {"rule_id": rules[0]["id"], "verdict": "APPLY", "reasoning": "match"},
        {"rule_id": rules[1]["id"], "verdict": "APPLY", "reasoning": "also match"},
    ])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )
    with patch("agents.rrr_matcher._ai_client", return_value=mock_client), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda prompt, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    assert item["significance_rank"] == 3, "Conflict must preserve initial rank"
    assert item["rrr_match_outcome"] == "conflict"
    assert item.get("rrr_rule_id") is None, "No rrr_rule_id on conflict"


# ─── Criterion 12: Pipeline persist ─────────────────────────────────────────

def test_pipeline_persist_rrr_outcomes():
    """After run_rrr_match, items with outcomes can be persisted to DB."""
    from agents.rrr_matcher import run_rrr_match
    conn = _mem_db()
    conn.execute("""
        INSERT INTO news_items
          (profile_id,source_type,source_id,url,title,content,
           first_seen_at,last_seen_at,hash_signature,significance_rank,dedup_status)
        VALUES (1,'rss','src1','http://x.com','Minimum wage increase announced','Content',
                datetime('now'),datetime('now'),'hash1',3,'new')
    """)
    conn.commit()
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4, "reason", "why", "- minimum wage", "- no date")
    conn.commit()

    item = dict(conn.execute("SELECT * FROM news_items WHERE id=?", (item_id,)).fetchone())

    rules = list_rrr_rules(conn, PROFILE_ID)
    mock_response = json.dumps([
        {"rule_id": rules[0]["id"], "verdict": "APPLY", "reasoning": "match"}
    ])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=mock_response))]
    )
    with patch("agents.rrr_matcher._ai_client", return_value=mock_client), \
         patch("agents.rrr_matcher.cached_chat", side_effect=lambda prompt, fn: fn()):
        run_rrr_match([item], PROFILE_ID, conn)

    if item.get("rrr_match_outcome"):
        conn.execute(
            "UPDATE news_items SET significance_rank=?,pre_rrr_rank=?,rrr_rule_id=?,rrr_match_outcome=? WHERE id=?",
            (item["significance_rank"], item.get("pre_rrr_rank"),
             item.get("rrr_rule_id"), item["rrr_match_outcome"], item_id),
        )
        conn.commit()

    row = dict(conn.execute("SELECT * FROM news_items WHERE id=?", (item_id,)).fetchone())
    assert row["significance_rank"] == 4, "significance_rank must be updated"
    assert row["pre_rrr_rank"] == 3, "pre_rrr_rank must capture initial rank"
    assert row["rrr_match_outcome"] == "upgraded"


# ─── Criteria 13–14: Direction guard ────────────────────────────────────────

def test_upgrade_rule_does_not_downgrade_higher_rank():
    """Upgrade rule (3→4) must not apply to rank 5 item — direction guard blocks it."""
    from agents.rrr_matcher import run_rrr_match, _rule_eligible_for_item
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 3, 4,
                    "Payroll impact", "why", "- minimum wage", "- none")
    conn.commit()

    rule = list_rrr_rules(conn, PROFILE_ID)[0]
    assert not _rule_eligible_for_item(rule, initial_rank=5), \
        "Upgrade rule (3→4) must be ineligible for rank 5 (would downgrade)"

    item = _make_item(rank=5, title="Critical minimum wage emergency decree")
    # No AI mock needed — direction guard filters rule before any AI call
    run_rrr_match([item], PROFILE_ID, conn)
    assert item["significance_rank"] == 5, "Upgrade rule (3→4) must not downgrade rank 5"
    assert item.get("rrr_match_outcome") is None


def test_downgrade_rule_does_not_apply_at_or_below_target():
    """Downgrade rule (4→2) must not apply to rank 2 item — no-op, blocked."""
    from agents.rrr_matcher import run_rrr_match, _rule_eligible_for_item
    conn = _mem_db()
    insert_rrr_rule(conn, PROFILE_ID, None, 4, 2,
                    "Not directly relevant", "why", "- no confirmed change", "- none")
    conn.commit()

    rule = list_rrr_rules(conn, PROFILE_ID)[0]
    assert not _rule_eligible_for_item(rule, initial_rank=2), \
        "Downgrade rule (4→2) must be ineligible for rank 2 (already at/below target)"

    item = _make_item(rank=2, title="Central bank policy discussion")
    run_rrr_match([item], PROFILE_ID, conn)
    assert item["significance_rank"] == 2, "Downgrade rule (4→2) must not affect rank 2 item"
    assert item.get("rrr_match_outcome") is None
