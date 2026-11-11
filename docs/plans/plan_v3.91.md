# V3.91 — Task 1: Reconciliation Status Investigation Report

**Date:** 2026-11-11  
**Author:** Independent design review (Opus Gate 2) + Sonnet  
**Status:** Investigation complete — awaiting PM approval before implementation  
**SPEC version at investigation time:** 3.81

---

## 1. Business Question

The review UI shows four status pills: NEW / UPDATE / REPEATED / DUPLICATE.

The user reported that items which are **reminder-style recaps** of already-known events (e.g., contribution-rate countdown articles) receive the `UPDATE` status, indistinguishable from items that contain **genuinely new regulatory information**. The investigation answers: is SIMILAR already distinguished from UPDATE in the pipeline, or does a code change require it?

---

## 2. Two-Column Status Model

The pipeline maintains two separate status fields per item:

| Column | Set by | Purpose |
|---|---|---|
| `dedup_status` | Compare (Step 4) + Reconcile (Step 8) | Technical duplicate / update detection |
| `repetition_status` | Compare (Step 4) finalization block | Visible UI pill value |

The Review UI reads `repetition_status` exclusively (via `db.py` line 1977: `item['status'] = (r['repetition_status'] or '').upper()`).

The four visible values are: `new`, `update`, `repeated`, `duplicate`.

**Verified:** There is no `similar` value anywhere in the codebase. SIMILAR does not exist as a distinct status.

---

## 3. Assignment Logic

### Step 4 — Compare (`agents/compare_news.py`)

Runs **before** L2 Fetch. Technical dedup on exact keys + embeddings.

| Condition | `dedup_status` | `repetition_status` |
|---|---|---|
| Exact key match (same source_id/guid/hash) | `duplicate` | `duplicate` |
| Cosine ≥ 0.80 | `duplicate` | `duplicate` |
| Cosine in [0.72, 0.80) **AND** `_has_meaningful_delta` = True | `update` | `update` |
| Cosine in [0.72, 0.80) **AND** `_has_meaningful_delta` = False | `duplicate` | `duplicate` |
| Cosine < 0.72 | `new` | `new` |

`_has_meaningful_delta` (lines ~560-580): requires at least one sentence with low word overlap (< 0.3) **and** a glossary term present in that sentence. This delta test is applied **only in the Compare mid-cosine band**.

**Finalization block (lines 607–622):** After the cosine logic, `repetition_status` is overwritten:
- If `repetition_count ≥ 3` AND same-run follow-up flag → `repeated`
- Otherwise: `repetition_status = dedup_status`

### Step 8 — Reconcile (`agents/compare_news.py`, `reconcile_by_act_ref`)

Runs **after** L2 Fetch + Law Match. Semantic matching keyed on `law_id`/`act_ref` + L2 embedding confirmation.

**Critical gap:** Reconcile only upgrades `new` items. It never calls `_has_meaningful_delta` or `_compute_delta`. Any `new` item whose `law_id` matches a prior item's `act_ref` is promoted to `update` — regardless of whether it contains genuinely new information or is just a reminder/recap.

```python
# Reconcile assigns 'update' with no delta test:
if count >= 3:
    item['repetition_status'] = 'repeated'
    item['dedup_status'] = 'update'
else:
    item['repetition_status'] = 'update'
    item['dedup_status'] = 'update'
```

### REPEATED — count threshold, not semantic intent

`repetition_status = 'repeated'` is set when `repetition_count ≥ 3` (same law seen 3+ times in the run) **or** the same-run follow-up flag is set. It is not a semantic signal for "reminder-intent content." A genuinely new amendment seen for the third time in a run would also receive `repeated`.

---

## 4. Why the Contribution-Rate Reminder Gets `UPDATE`

The Xanadu article `social-insurance-rate-countdown.html` (published 08 Nov 2026, effective 15 Nov 2026) is a deadline-reminder article for Royal Decree No. 18/2026 — a law that was already processed in an earlier run.

Pipeline trace:
1. **Compare (Step 4):** Cosine to the original article is likely < 0.72 (different content focus — reminder vs. enactment). Exits Compare as `new`.
2. **L2 + Law Match (Steps 5–6):** Matches `act_ref = "Royal Decree No. 18/2026"`.
3. **Reconcile (Step 8):** Finds prior item with same `act_ref`. `repetition_count` < 3 (first reminder). Upgrades to `update`. No delta test.
4. **Result:** `repetition_status = 'update'` — same pill as a genuine amendment.

---

## 5. Gap Analysis

| Business distinction | Current behavior | Gap |
|---|---|---|
| Genuine new information for a known law | `UPDATE` | Correct |
| Reminder/recap with no new information | `UPDATE` | **Wrong** — should be `SIMILAR` |
| Same story seen 3+ times | `REPEATED` | Correct (count-based) |
| Exact or near-exact copy | `DUPLICATE` | Correct |

The gap is in **Reconcile**: it conflates same-event re-coverage with genuine updates into a single `update` label because it never applies a delta test.

---

## 6. Full Dependency Map

Any code change to add `similar` as a distinct value touches:

| Layer | File | What changes |
|---|---|---|
| Pipeline logic | `agents/compare_news.py` | `reconcile_by_act_ref`: add `_has_meaningful_delta` check; emit `similar` when delta is absent |
| DB schema | `configurations/db.py` | `repetition_status` is plain TEXT (no CHECK constraint) — no schema migration needed |
| Review UI data builder | `configurations/db.py` line 1977 | No change needed — reads `repetition_status` as-is |
| Review UI template | `admin/templates/review_news.html` lines 224-228 | Add `SIMILAR` filter chip |
| Review UI CSS | Wherever `.status-pill.status-update` is styled | Add `.status-pill.status-similar` rule |
| Ranker | `agents/news_ranker.py` | `rank_items`: `dedup_status != 'duplicate'` filter at controller level; ranker itself is unaffected |
| Controller | `agents/agents_controller.py` lines 687, 697, 707 | Filter `dedup_status != 'duplicate'` — `similar` items must pass this filter (they should, since `similar` ≠ `duplicate`) |
| Announcements / Email | Any downstream consumer of `repetition_status` | Audit required — `similar` items should likely be suppressed from announcement emails same as `repeated` |
| Test fixtures | `tests/` | Any test asserting `repetition_status = 'update'` for a reminder-type item must be updated |

---

## 7. Risk Assessment

**Low risk:**
- DB has no CHECK constraint on `repetition_status` — no migration needed.
- The ranker does not branch on `update` vs. `similar` — rank is unchanged.
- The controller's duplicate filter passes `similar` items through correctly.

**Medium risk:**
- `_has_meaningful_delta` in Compare requires a glossary term in a low-overlap sentence. Applied to Reconcile, it may be too strict (a reminder article with no new glossary-bearing sentence would become `similar` even if it adds a deadline date). The delta threshold may need tuning.
- Announcement/email consumers are not fully audited here — a `similar` item treated as `update` by a downstream consumer could generate a spurious announcement.

**Low-to-none:**
- No UI breakage: the pill renders `item.status|lower` dynamically; adding a CSS rule for `status-similar` is purely additive.

---

## 8. Recommendation — Smallest Safe Scope for V3.91

**Change 1 (core logic): `agents/compare_news.py` — `reconcile_by_act_ref`**

After finding a `law_id`/`act_ref` match, apply `_has_meaningful_delta` before emitting `update`:
- If delta present → `update` (genuine new information)
- If delta absent → `similar` (same-event re-coverage / reminder)

**Change 2 (UI): `admin/templates/review_news.html`**

Add a `SIMILAR` filter chip alongside NEW / UPDATE / REPEATED / DUPLICATE.

**Change 3 (UI): CSS**

Add `.status-pill.status-similar` style (suggest amber/yellow — between green NEW and orange UPDATE).

**Change 4 (tests): update fixtures**

Any test fixture where a reminder-type item asserts `repetition_status = 'update'` must be updated to `similar`.

**Out of scope for V3.91:**
- Changes to `repetition_status = 'repeated'` semantics (count-based logic is acceptable for now)
- Announcement/email suppression of `similar` items (separate audit required)
- Any Rank Gate changes (rank is already correct for these items based on `oi`/`rc`/`tm` signals)

---

## 9. Open Questions for PM

1. Should `similar` items be suppressed from announcement emails the same way `repeated` items are?
2. Should the `SIMILAR` filter chip be visible by default or hidden behind an "advanced" toggle?
3. Is the existing `_has_meaningful_delta` threshold (glossary term + < 0.3 word overlap) the right signal for Reconcile, or should a simpler test be used (e.g., embedding cosine delta only)?

---

*End of V3.91 Task 1 investigation report.*
