# v3.4 Design — Challenge + Grounding Loop

**Date:** 2026-09-05
**Version:** v3.4
**Status:** Approved

---

## Context

v3.3 shipped the V2 digest composer (`email_composer.py`) and the `news_announcements` data model, but two things were left incomplete:

1. `email_composer.generate_digest()` was never wired into `run_profile_once()` — the pipeline still calls the old `email_sender` path, so `news_announcements` has 0 rows in production.
2. The Review tab still shows a flat list — no Topic→Announcement→Sources hierarchy, no Challenge button, no grounding write-back.

v3.4 completes this: wires the digest, restructures the Review tab around the agreed 3-level hierarchy, adds the Challenge modal that teaches the ranker, and writes confirmed signals back to `ranking_grounding` and `ranking_signals`.

---

## Terminology (locked)

| Level | Term | Source | Table |
|---|---|---|---|
| 1 | **Topic** | Glossary tagger (`topic_label`) | `news_items.topic_label` |
| 2 | **Announcement** | AI-generated draft in RCM format | `news_announcements` (renamed from `news_aspects`) |
| 3 | **Sources** | Individual news articles backing the announcement | `news_items` |

An Announcement has RCM structure: intro, business need, sources. Clicking one in the Review tab renders its `announcement_md` as markdown. The full RCM-styled template (branded, with publish action and JIRA linking) is v3.5.

---

## Scope

1. **Housekeeping** — rename `news_aspects` → `news_announcements` throughout; update roadmap; reset production DB
2. **Pipeline wire** — call `email_composer.generate_digest()` from `run_profile_once()`, pass HTML to `email_sender.send_email()`
3. **Review tab** — Topic→Announcement→Sources nested hierarchy (Option A: nested indent); click Announcement → renders `announcement_md` inline
4. **Challenge modal** (Option C: centered modal) — ⚡ button on each Source; re-evaluates via Tier 1 + Tier 2; shows original vs suggested rank + reasoning; user edits reason + clicks Confirm & Learn
5. **Grounding write-back** — on confirm: writes to `ranking_grounding` (few-shot example) + `ranking_signals` (Tier 1 pattern)
6. **Re-rank** — per-item ↺ button on Source cards; bulk "Re-rank All" on Run tab

---

## UI Decisions

### Review Tab: Option A (Nested Indent)
```
Topic row (dark navy, collapsible ▼)
  Announcement row (indented, purple left border, collapsible ▼)
    [rendered announcement_md when expanded]
    Source card (rank badge · title · publisher · ↺ Re-rank · ⚡ Challenge)
    Source card ...
  Announcement row ...
Topic row ...
```

All topics and announcements open by default on page load.

### Challenge: Option C (Modal)
Centered overlay modal. Focused interaction — intentional, one decision at a time. Appropriate for a "teach the AI" action.

Flow:
1. Click ⚡ → modal opens, loading state
2. POST `/admin/news/<id>/challenge` → re-runs Tier 1 + Tier 2
3. Modal shows: original rank | AI-suggested rank | AI reasoning
4. User edits reason (pre-filled if AI disagrees) → clicks **Confirm & Learn**
5. POST `/admin/news/<id>/confirm-challenge` → writes grounding + signal rows
6. Reflection message shown: *"Understood — future items matching '[pattern]' will be ranked [N]."*
7. Modal auto-closes after 2.5s

---

## Key Existing Code to Reuse

| What | Where |
|---|---|
| `_tier1_score()` + `_tier2_score()` | `agents/news_ranker.py` |
| `generate_digest()` | `agents/email_composer.py` |
| `send_email()` | `agents/email_sender.py` |
| `ranking_grounding` table DDL (read path exists) | `configurations/db.py` |
| `ranking_signals` table DDL (read path exists) | `configurations/db.py` |
| `human_rank_override`, `human_override_reason` columns | `news_items` table |

---

## What v3.5 Will Enhance (not rebuild)

v3.4 renders `announcement_md` as plain markdown inline. v3.5 adds:
- Full RCM-branded template page (not just inline markdown)
- Publish action (sends to RCM)
- JIRA Legal Change creation from announcement
- Announcement editing before publish

v3.5 does NOT need to build the data model or announcement generation — that's all done in v3.4.
