# CHANGELOG

## v3.92 — 2026-11-12
### RRR Learning & Matching

**What it does:** Legal Eagle can now learn from meaningful human rank corrections, store them as approved reusable rules (Re-rank Rules / RRR), and automatically apply those rules to future pipeline items after initial ranking.

**New pipeline stage — RRR Match (`agents/rrr_matcher.py`):**
- Runs after `rank_items()` (deterministic signal-fusion, unchanged) and before the email gate.
- Evaluates all active LPM-approved rules for the profile against eligible non-rank-1 items.
- One AI call per item (GPT-4o) returns `APPLY / DO_NOT_APPLY / INSUFFICIENT_EVIDENCE` per rule.
- Only `APPLY` verdicts change the rank. `INSUFFICIENT_EVIDENCE` is logged for investigation and ignored.
- Direction guard: upgrade rules (`override_rank > original_rank`) are never used to downgrade a higher-ranked item; downgrade rules are never used to upgrade. A rule learned from rank 3→4 cannot downgrade a rank 5 item to 4.
- Conflict handling: when two `APPLY` verdicts disagree on the target rank, the initial rank is preserved and `rrr_match_outcome='conflict'` flags the item for human review.
- Original system rank is preserved in `pre_rrr_rank`; no initial ranking logic was changed.

**Rule generation (`agents/rrr_generator.py`):**
- Takes an item, a human-selected override rank, and a human reason; returns structured WHY / WHEN / WHEN NOT sections grounded in SAP localization evidence (law references from Law Match stage, RCM match status, configured authority name, impact evidence clauses, profile country/LoB).
- Failure detection: rules containing "insufficient:", "n/a", or other failure markers return `sufficient=False` and are blocked from being saved as active rules (`is_rule_sufficient()` guard in both generator and confirm-challenge route).
- Stale rule invalidation: if the LPM changes the override rank or human reason after generating a rule, the JS draft is cleared — the rule must be regenerated before it can be saved.

**Review UI — re-rank dialog (`admin/templates/review_news.html`):**
- Replaced the legacy "AI SUGGESTS" two-panel modal (dead code since v3.19 deterministic ranking) with a four-step dialog:
  1. Current Rank display (read-only).
  2. Override Rank dropdown (dynamically filtered to allowed targets only; rank 1 is excluded entirely).
  3. Human Reason textarea (required for both one-off corrections and rule creation).
  4. Generate Rule button → WHY / WHEN / WHEN NOT textareas (editable before saving).
- "Confirm & Learn" creates a reusable rule + saves the override. "Save one-off" saves only the override without creating a rule.
- Item cards now display Original Rank (`pre_rrr_rank`) and RRR ID (`rrr_rule_id`) alongside the existing rank; both fields are blank when no RRR adjustment occurred.

**Eligibility enforcement:**
- Rank 1 items have no allowed override targets (RRR skips them entirely).
- Ranks 2–3: targets 4, 5. Ranks 4–5: targets 2, 3, (5 or 4). Enforced in both the challenge route and the confirm-challenge route (backend guard).
- `_RRR_ALLOWED_TARGETS` constant is the single source of truth.

**Routes (`admin/app.py`):**
- `POST /admin/news/<id>/challenge` — simplified: returns item data + allowed targets; no AI call at this stage.
- `POST /admin/news/<id>/generate-rule` — new: generates WHY/WHEN/WHEN NOT via SAP-grounded AI call.
- `POST /admin/news/<id>/confirm-challenge` — redesigned: enforces eligibility, validates rule sufficiency, saves override + optional rule. No longer writes to legacy `ranking_grounding` / `ranking_signals` tables.

**DB changes (`configurations/db.py`):**
- New table: `rrr_rules` (profile_id, source_item_id, original_rank, override_rank, human_reason, why_text, when_text, when_not_text, active, created_at).
- New columns on `news_items`: `pre_rrr_rank INTEGER`, `rrr_rule_id INTEGER`, `rrr_match_outcome TEXT` (added via idempotent ALTER, safe for existing DBs).
- New CRUD helpers: `insert_rrr_rule`, `list_rrr_rules`, `deactivate_rrr_rule`.

**Tests (`tests/test_rrr_v392.py`):**
- 16 acceptance tests covering all 14 criteria: DB schema, rule CRUD, generator contract (including insufficient detection), matcher verdict logic (APPLY/DO_NOT_APPLY/INSUFFICIENT_EVIDENCE), conflict handling, pipeline persist, and direction guard.
- All 16 V3.92 tests pass. All 51 V3.91 regression tests pass.

## v3.92 live hotfix — 2026-11-12
### Re-rank dialog showing `undefined — ?` on first Xanadu test

**Root cause:** The LaunchAgent-managed server process was never restarted after V3.92 Python edits. The file on disk contained the V3.92 challenge route (returning `initial_rank` / `allowed_targets`), but the running process held the pre-V3.92 code in memory and continued returning the old contract (`original_rank`, `suggested_rank`, `agrees`). Frontend JS expected `initial_rank`; the old server returned `original_rank` → `undefined` in the dialog.

**Confirmed by:** `curl -X POST http://127.0.0.1:5001/admin/news/9/challenge` returned `{"original_rank":5,"suggested_rank":3,"agrees":false,...}` before restart; returns `{"initial_rank":5,"allowed_targets":[2,3,4],...}` after.

**Fix:**
- Restarted server via `launchctl kickstart -k gui/<uid>/com.legaleagle.admin`. Live endpoint now returns the correct V3.92 contract; rank 5 → `allowed_targets: [2,3,4]`.
- Added strict frontend contract validation in `openChallenge()` (`admin/templates/review_news.html`): if `initial_rank` is missing or not a number, or `allowed_targets` is missing or empty, a clear error message is shown and the dialog closes — no silent `undefined` rendering.
- Added `test_route_challenge_rank5_exact_contract` (`tests/test_rrr_v392.py`): exercises the production challenge endpoint via Flask test client, asserts all required frontend fields (`initial_rank`, `allowed_targets`, `title`) are present with correct values for rank 5, and explicitly asserts the absence of old-contract fields (`original_rank`, `suggested_rank`, `agrees`).

**Tests:** 43/43 V3.92 tests pass. 51/51 V3.91 regressions pass.

## v3.92 corrective patch — 2026-11-12
### Five defects fixed before release acceptance

**1. Review audit fields (`configurations/db.py`, `agents/agents_controller.py`):**
- `list_all_news_for_review()` SELECT now includes `pre_rrr_rank`, `rrr_rule_id`, `rrr_match_outcome` so Review page can display all three fields.
- `pre_rrr_rank` is now stamped on ALL non-duplicate newly-ranked items (not just those matched by a rule) before `run_rrr_match()` is called, preserving the immutable initial system rank.
- Extracted `persist_rrr_outcomes(conn, items, profile_id)` helper in `configurations/db.py`: writes `pre_rrr_rank` for all stamped items and RRR outcome columns only for rule-matched items; replaces the inline 30-line persist loop in `agents_controller.py`.

**2. Rank eligibility enforcement (`admin/app.py`, `admin/templates/review_news.html`):**
- Re-rank button (&#128681;) is now hidden in HTML for Rank 0/1 items (`{% if score >= 2 %}`).
- Legacy `POST /admin/news/<id>/override` endpoint retrofitted with the same eligibility guard and mandatory `reason` requirement as `confirm_challenge_news_item`; previously bypassed both with no validation.

**3. RRR Match grounding (`agents/rrr_matcher.py`):**
- Matcher prompt now includes law references (from Law Match stage), configured authority name (only when `authority_status == "configured"`), RCM scope signal, and rule direction context (`original_rank→override_rank`).
- INSUFFICIENT_EVIDENCE vs DO_NOT_APPLY distinction strengthened: explicit "CRITICAL REMINDERS" section prevents topic-similarity from triggering APPLY; evidence must be positively established, not merely absent.

**4. Generator readiness validation (`agents/rrr_generator.py`, `admin/app.py`):**
- `generate_rrr_rule()` now returns a machine-readable `readiness` field (`"ok" | "insufficient" | "failed"`); prompt requests explicit `"readiness": "ok | insufficient"` from AI.
- New `validate_rule_sections(why, when, when_not) -> Optional[str]` checks for empty sections, failure prefixes, and placeholder patterns (`tbd`, `[insert`, etc.) before a rule is saved.
- `confirm_challenge_news_item` route now calls `validate_rule_sections()` instead of the weaker prefix-only `is_rule_sufficient()` check.

**5. Tests replaced (`tests/test_rrr_v392.py`):**
- Rewritten from 16 to 32 tests. Previous tests simulated SQL persistence manually and lacked Flask route coverage.
- New tests: `persist_rrr_outcomes` integration tests (real in-memory DB), `validate_rule_sections` structural validation (4 tests), `readiness` field contract, `inspect.getsource()` SELECT column verification, and Flask test-client route tests for eligibility enforcement (rank 1 block, invalid transition, missing reason) on both `/challenge`, `/confirm-challenge`, and `/override`.
- All 32 V3.92 tests pass. All 51 V3.91 regression tests pass.

## v3.92 final patch — 2026-11-12
### Three defects fixed after independent code review of 36be6cb

**1. Generator readiness defaults (`agents/rrr_generator.py`):**
- Missing `readiness` key in AI response now defaults to `"insufficient"` (was `"ok"`). An AI that does not explicitly signal readiness must not produce an approvable rule automatically.
- Unrecognised `readiness` values now default to `"insufficient"` (was `"ok"`). Unknown states are treated as unconfirmed.
- Deliberate LPM approval path preserved: `readiness="insufficient"` produces an editable draft; after the LPM resolves missing information and edits the sections, `validate_rule_sections()` (not `readiness`) gates the save — so a corrected draft saves without a second AI call.
- AI call exceptions continue to return `readiness="failed"` with unusable content; `validate_rule_sections()` blocks those at save via `_FAILURE_PREFIXES`.

**2. Product-scope evidence in RRR Match (`agents/rrr_matcher.py`):**
- Added explicit `PRODUCT-SCOPE EVIDENCE` section to the matcher prompt: law references, configured authority status, and RCM tracking are regulatory context — they confirm what regulation requires, not whether SAP supports the relevant payroll process, report, or interface.
- Prompt now instructs: if a WHEN condition requires a product-scope fact (e.g., "SAP Payroll localises this contribution type") and no such confirmation appears in the article's operative clauses, use `INSUFFICIENT_EVIDENCE` — do not infer SAP product coverage from regulatory context alone.

**3. Original Rank display (`admin/templates/review_news.html`):**
- Outer condition changed from `{% if item.pre_rrr_rank or item.rrr_rule_id %}` to `{% if item.pre_rrr_rank or item.rrr_rule_id or (score >= 1 and item.rank_tier != 'human') %}`.
- Previously the historical fallback (`Orig: {{ score }}`) was unreachable for new unchanged items because the outer guard required at least one RRR field to be set.
- Human-overridden legacy records (no `pre_rrr_rank`, `rank_tier='human'`) are correctly excluded — the original rank before the human override is unknown and must not be fabricated.

**Tests added (`tests/test_rrr_v392.py`, 32 → 42 tests):**
- P1 readiness: `test_generate_rrr_rule_missing_readiness_defaults_to_insufficient`, `test_generate_rrr_rule_invalid_readiness_defaults_to_insufficient`, `test_generate_rrr_rule_ai_exception_returns_failed`, `test_route_confirm_rejects_failed_content`, `test_route_confirm_accepts_lpm_edited_insufficient_draft`
- P2 product-scope: `test_rrr_matcher_prompt_contains_product_scope_instruction`, `test_rrr_match_regulatory_context_alone_cannot_justify_scope_dependent_downgrade`
- P3 template: `test_template_orig_rank_shows_for_new_unchanged_item`, `test_template_orig_rank_shows_for_rrr_adjusted_item`, `test_template_orig_rank_hidden_for_human_overridden_legacy_item`
- All 42 V3.92 tests pass. All 51 V3.91 regression tests pass.

## v3.91 — 2026-11-11
### Task 4D — News Review Status Compatibility & Repetition Counter

Step 8 repetition bookkeeping is now complete, and News Review presents confirmed repetition counts alongside REPEATED status badges.

**Reconcile bookkeeping (`agents/compare_news.py`):**
- Replaced `_first_confirmed()` helper with `_max_confirmed_count()`, which scans ALL confirmed candidates and returns the maximum `repetition_count` among them (or -1 if none confirm). This enables event-specific cumulative counting without a separate event registry.
- Both confirmed-match branches (prior-run and same-run) now set `it["repetition_count"] = max_confirmed_count + 1`, so: original = 0, first repeat = 1, second repeat = 2, and so on.
- Counts are automatically scoped to the same legal development: semantic confirmation via `same_legal_event()` ensures that candidates from different events under the same law do not contribute to each other's count chains.
- Duplicate observations do not increment the counter — they are not passed to Reconcile and their stored count stays at 0 (same as the original), so they cannot inflate future counts even when present in the baseline.

**News Review UI (`admin/templates/review_news.html`):**
- STATUS filter row updated: `All | NEW | REPEATED | DUPLICATE`. The UPDATE chip is removed.
- Individual status badges for REPEATED items now display `REPEATED (n)` when `n ≥ 1`. Legacy items with `repetition_count = 0` or NULL display plain `REPEATED` (no fabricated count).
- `data-status` attribute on each card continues to hold the raw status value (`REPEATED`, not `REPEATED (1)`), so the REPEATED filter chip correctly matches all REPEATED items regardless of count.
- Added `.status-duplicate` CSS class to correctly style DUPLICATE status badges (was missing — the existing `.status-dup` class was unreachable from the template's `status-{{ item.status|lower }}` expression).

**Historical compatibility:**
- Legacy rows with `repetition_status = 'update'` remain visible in the review list with `status = 'UPDATE'`. The removed UPDATE filter chip does not cause these records to disappear — they are accessible under the All filter.
- No destructive migration or rank rewrite is performed.

**Help text (`configurations/review_help.json`):**
- UPDATE entry removed from the Status section.
- REPEATED description updated to explain the count badge meaning (no longer references the obsolete "3 or more runs" threshold).
- DUPLICATE description updated for clarity.

**Test file created:** `tests/test_review_status_v391.py` — 20 focused tests covering all 12 mandatory acceptance criteria plus 5 new Task 4D.1 counter-fix tests; **20/20 passing**. Task 4C regression 10/10 passing. Task 4A regression 11/11 passing.

### Task 4D.1 — Repetition Counter Fix: Unified Max Across Both Candidate Groups

Corrected a bookkeeping error where same-run reminders arriving after a historical match was found would reset to the historical baseline count instead of advancing from the highest count already assigned in the same run.

**Bug:** `reconcile_by_act_ref()` used an if/else that checked historical candidates first; if a baseline match existed, same-run candidates were never consulted. With a historical original (count=0) and three same-run reminders, all three received count=1 instead of 1, 2, 3.

**Fix (`agents/compare_news.py`):** Both candidate groups are now evaluated unconditionally. `repetition_count = max(base_max, run_max) + 1`. `_repeated_followup` is still set whenever `run_max ≥ 0`. No change to semantic matching thresholds or AI call count.

**Tests added to `tests/test_review_status_v391.py`:**
- Historical original + three same-run reminders → 1, 2, 3
- Historical count 2 + two same-run reminders → 3, 4
- Distinct events same law maintain independent counters under combined history+same-run
- All-new same-run reminders receive sequential counts (regression)
- No confirmed match remains NEW with count 0 (regression)

### Task 4C — Reconcile: Correct Event Matching

Step 8 (Reconcile) has been corrected to comply with the approved business rules for NEW vs REPEATED classification.

**Bugs corrected in `reconcile_by_act_ref()` (`agents/compare_news.py`):**

1. **Multi-candidate fix** — `baseline_by_law` and `baseline_by_ref` now hold lists of all candidates per law_id/act_ref (previously only the first candidate was retained). This allows distinct legal developments under the same law to each be independently recognized as NEW or REPEATED.
2. **`dedup_status` never changed** — Reconcile no longer sets `dedup_status = "update"`. Only `repetition_status` is mutated; `dedup_status` remains `"new"` for both NEW and REPEATED articles (rule 6).
3. **No occurrence-count threshold** — A confirmed same-event match immediately sets `repetition_status = "repeated"`, regardless of prior occurrence count. The old `>= 3` promotion delay is removed (rule 4).
4. **Same-run tracking uses lists** — `seen_law` and `seen_ref` now hold lists of same-run candidates (previously only the first per identity); `_register` appends; a new `_first_confirmed()` helper scans all candidates.
5. **Embedding failure preserves NEW** — `_confirm()` now returns `False` when embeddings are unavailable (previously returned `True`, causing false REPEATED on AI outage). Aligns with rule 8: if semantic evidence is unavailable, preserve NEW.

**Test file created:** `tests/test_reconcile_v391.py` — 10 focused tests covering all mandatory scenarios; 10/10 passing. Task 4A regression 11/11 passing. Task 4B regression 6/6 + 4/4 passing.

### Task 4B — Controller Routing: DUPLICATE Bypass

DUPLICATE items returned by Comparing now stop before all expensive downstream stages. They remain persisted and visible in News Review (handled by compare_news, tested in Task 4A), but never enter L2 Fetch, Authority Resolution, Glossary Match, Law Match, Reconcile, RCM Match, Impact Gate, Timing, or Rank.

**Changes:**
- `agents/agents_controller.py` — after Comparing, only `new_items` is routed to the analyzing stage and email rank gate; obsolete `update_items` wiring removed (was permanently `[]` after Task 4A); all-duplicate input skips the analyzing block without errors or unnecessary AI calls; `final_items` for the email digest is now `new_items` only
- `tests/test_controller_4b.py` — 6 focused integration tests covering: new+dup routing (mandatory), duplicate not email-eligible, all-duplicate no-AI-calls, all-new full pipeline, skip_comparison=True, update_items not routed; 6/6 passing; Task 4A regression suite 11/11 passing

**Blocking correction (DUPLICATE rank persistence):**
- `configurations/db.py` — `upsert_news_item()` now unconditionally enforces `significance_rank=0`, `rank_tier='duplicate'`, `email_eligible=0` for any item with `dedup_status='duplicate'`, on both INSERT and UPDATE paths; this prevents a previously-ranked article from retaining its old rank when re-collected as a duplicate
- `tests/test_duplicate_rank_persistence.py` — 4 regression tests using a real in-memory SQLite DB: previously-ranked article reset to rank=0 (mandatory), NEW article retains rank, fresh DUPLICATE insert has rank=0, News Review query returns rank=0; 4/4 passing

### Task 4A — Restrict Comparing to NEW/DUPLICATE only

Step 4 (Comparing) now classifies strictly as **NEW** or **DUPLICATE** using reliable technical identity only (source_id, URL, content hash). Cosine similarity, entity fingerprinting, and the `is_fp_intrarun` path are removed — legal-event identity belongs to Reconcile (Step 8). REPEATED and UPDATE are never assigned by Step 4.

**Changes:**
- `agents/compare_news.py` — removed embedding generation, cosine-based classification, `is_fp_intrarun` path, mid-cosine UPDATE branch, and `prior_count >= 3 → REPEATED` promotion; added `seen_sigs` set for same-run content-hash dedup; `update_items` always returns `[]` (controller compatibility preserved for Task 4B)
- `tests/test_compare_news_v391.py` — 11 focused tests covering all mandatory scenarios; 11/11 passing
- `docs/plans/plan_v3.91.md` — V3.91 investigation report + Task 4A implementation plan
- `CLAUDE.md` — governance role boundaries updated (Opus owns `docs/plans/` and `docs/roadmap/`; Sonnet owns source, tests, and `docs/SPEC.md` post-execution) + 6-step development workflow documented

**Deferred (identified dead code, no external callers):** `_compute_delta()`, `_has_meaningful_delta()`, `_get_ai_client()`, `_embed_texts()`, `DEDUP_COSINE_DUP/UPDATE`, `JACCARD_*` constants — cleanup scheduled for a separate task after V3.91 ships.

## v3.39 — 2026-11-10
### Governance setup + GitHub Pages rename

- **Rename:** `docs/xanadu/xanadu.html` → `docs/xanadu/index.html` so GitHub Pages serves the site at the bare directory URL without a filename suffix.
- Added `.clinerules/ai-governance.md` — short reference to `docs/AI_GOVERNANCE.md` defining Cline's role and approval boundaries. Product Manager authorized setup; no production implementation plan involved.
- Added `docs/AI_GOVERNANCE.md` and project-level `CLAUDE.md` governance constitution defining role boundaries (Sonnet = Implementation Engineer, Opus = Independent Design Reviewer).

## v3.35 — 2026-10-08
### Dated URL sources fix + lifecycle documentation

- **Bug: dated URL sources produced 0 items** — `scrape_url_source_with_config()` was fetching the base URL once and applying the stored selector, ignoring `url_date_template` entirely. Sources like Resmi Gazette (daily gazette URL `https://resmigazete.gov.tr/{DD}.{MM}.{YYYY}`) collected 0 items every run.
- **Fix: dated URL generation inside the scraper** — `scrape_url_source_with_config()` now checks `url_date_template`; if set, calls `_generate_dated_urls(template, days or 30)` to compose one URL per day going back N days, scrapes each with the stored selector via the new `_scrape_single_url()` helper, and injects the URL's date as authoritative (overrides any date the page itself returns).
- **Fix: simulation uses a dated URL** — the simulate endpoint (`/api/simulate`) and the Simulate button now compose yesterday's dated URL when `url_date_template` is present, so simulation actually tests the same path that the scraper takes during a run.
- **Lifecycle documentation** — `Roadmap/lifecycle.html`:
  - "Select Profile" step renamed to "Run Orchestrator" — makes clear this step triggers `agents_controller.py` which drives the entire Run phase in FULL or DELTA mode per source.
  - URL Scrape detail: new `url_date_template` column describing how dated URL generation works end-to-end.
  - Sources setup detail: `url_date_template` field listed and explained.

**Root cause:** `scrape_url_source_with_config()` was the simulated-source path but had no dated URL logic. `agents_controller.py` passes the source dict (including `url_date_template`) but the scraper was not reading it. The date injection guard `if not it.get("date")` also silently skipped injection whenever the page returned any non-empty string (even an unparseable Turkish date string).

- **Run Now → autorun flow** — "Run Now" button replaced with a link to the run_status page with `?autorun=1`; page auto-submits the run form on load, so the user lands on the run status page with sources visible before the run fires.
- **Source selection persistence** — chip selections saved to `localStorage` per profile; restored on next page load so the user's last-used source set is pre-selected.
- **Toggle all** — "Deselect all" replaced with "Toggle selection" (checks all if any are unchecked, unchecks all if all are checked).
- **History pill timestamp** — truncation extended to 16 chars to show full `YYYY-MM-DDTHH:MM` timestamp.

**Files changed:**
- `agents/url_sources_runner.py` — `_scrape_single_url()` helper (extracted); `scrape_url_source_with_config()` rewritten with dated URL branch; date injection changed to unconditional `it["date"] = date_str`
- `admin/app.py` — `/api/simulate` endpoint composes dated URL when `url_date_template` is in payload
- `admin/templates/profile.html` — Simulate button passes `url_date_template` to `startSimulation()`
- `admin/templates/base.html` — "Run Now" → `<a>` link with `?autorun=1`; `text-decoration: none; display: inline-block` on `.btn-run-now`
- `admin/templates/run_status.html` — form wraps full left panel; source persistence + toggle-all; history pill 16-char timestamp
- `Roadmap/lifecycle.html` — "Run Orchestrator" step + `url_date_template` documentation

---

## v3.34 — 2026-09-17
### BTP Data Persistence: Backup/Restore API + CLI Scripts

- **BTP Ephemeral Database Problem** — SQLite database lives in the container filesystem. On `cf push`, `cf restart`, or `cf restage`, Cloud Foundry may create a new container on a different Diego Cell, resulting in a brand-new empty database. All config and production data is lost.
- **Solution: Export/Import API** — New endpoints `/api/export-all` (GET) and `/api/import-all` (POST) in `admin/app.py`:
  - Export: returns ALL tables (config + production data) as JSON; protected by admin secret
  - Import: clears all data and reimports from JSON; protected by admin secret; requires confirmation
- **Local CLI Scripts**:
  - `scripts/btp_backup.py` — exports BTP database to timestamped JSON file
  - `scripts/btp_restore.py` — imports JSON backup into BTP database
  - Both read admin secret from arg or `LEGAL_EAGLE_ADMIN_SECRET` env var
- **Workflow**: `python btp_backup.py` → `cf push` → `python btp_restore.py --file backup.json`
- **Documentation**:
  - `BTP_DEPLOYMENT_DIFFERENCES.md` Section 14 — full backup/restore workflow and API reference
  - `memory-bank/activeContext.md` — updated current version to v3.34

**Files Changed:**
- `admin/app.py` — `/api/export-all`, `/api/import-all` (143 lines)
- `scripts/btp_backup.py` — new local tool (163 lines)
- `scripts/btp_restore.py` — new local tool (160 lines)
- `BTP_DEPLOYMENT_DIFFERENCES.md` — Section 14 added
- `memory-bank/activeContext.md` — version bumped to v3.34

---

## v3.33 — 2026-09-14
### REPEATED classification fix · configurable baseline window

- **REPEATED classification fixed** — `reconcile_by_act_ref` same-run branch was setting `dedup_status = "duplicate"` for follow-up articles sharing the same `act_ref`/`law_id` as an earlier article in the same run. Root cause: reconcile runs after L2 fetch sets `act_ref`, so two articles about the same law in one run (e.g. an original decree + a countdown reminder) triggered the duplicate branch instead of the follow-up branch. Fix: same-run act_ref/law_id matches are classified as `dedup_status = "update"` + `repetition_status = "repeated"`, routing them through the full pipeline (ranker, impact gate, announcement grouping). The original article remains `dedup_status = "new"`.
- **Configurable baseline window** — removed the hardcoded `WEEKLY_BASELINE_DAYS = 7` constant. Replaced with `get_baseline_days(profile_id)` in `config_loader.py` that reads a per-profile `"baseline_days"` setting (existing `settings` table), falling back to 7. The window is no longer tied to "weekly" — it reflects the actual publication cadence of each profile's sources.
- **Source simulator date detection tier 3** — `source_simulator.py` now falls back to content-based date parsing (using `parse_date_string`) when no `<time>` tag or CSS class hint is found in the article container.
- **Xanadu demo site** — `Roadmap/v3/xanadu-gov-site/` — full Republic of Xanadu Ministry of Human Resources demo site with 7 articles, proper styling, and `file://` URLs compatible with the URL source scraper. Includes the Royal Decree No. 18/2026 pair (Aug 20 original + Sep 5 countdown) that drove the REPEATED fix.


### effective_date prompt fix · user-friendly per-item signal observability

- **effective_date instruction tightened** — `impact_gate.py` hardcoded field definition now explicitly forbids using publication, approval, Gazette, decision, or article dates as `effective_date` unless the article explicitly links that date to entry into force / applicability. Aligns with matching guidance added to the Impact Rubric config.
- **[IMPACT] per-item log** — after each AI call, `_assess_one()` prints a readable summary: impact level (out-of-scope / minor / operational / major), whether change was confirmed, prep required, and effective date.
- **[RANK] per-item log + gate attribution** — `rank_items()` prints each item's final rank with label (Watch / Legal Change / Urgent…), the plain-language gate that fired, and grounding signals (glossary✓ law✓ rcm=tracked authority✓). Eliminates the need for DB queries to diagnose ranking decisions.
- **Version annotations removed from log messages** — `"(v3.1)"` tag stripped from the "items passed to pipeline stages" log line in `agents_controller.py`.

### Glossary Labels · announce decoupled from email · RCM config section

- **Glossary Labels (canonical, multilingual topic grouping)** — a **label** is one canonical
  topic (e.g. `SGK`, `Tax`, `Employment`); under it live many member terms in any language
  (`SGK`, `Sosyal Güvenlik Kurumu`, `Social Security Institution` …). New `glossary_labels`
  table + `label_id` on `glossary_terms`. The matcher (`glossary_match.py`) now matches term +
  synonyms + patterns and stamps the **canonical label name** as `topic_label` — so any
  language/spelling collapses to one label and separate announcements about the same entity
  group together instead of splitting by surface form. `rematch_news_item` inherits this;
  `rematch_items_for_profile` + a **Re-match all** action re-label a whole profile after edits.
- **Config → Knowledge rebuilt as label cards** — editable label name, member-term chips (with
  `lang`), add-term-under-label, add/delete label. New label routes in `admin/app.py`.
- **Seed migration** — `agents/glossary_labels_seed.py` seeds a profile's labels + terms (no
  manual creation); folds pre-existing flat terms into their label. Türkiye HCM (profile 4)
  seeded with 7 labels / 72 terms.
- **Announcement inclusion decoupled from the email flag** — `get_pending_announce_items` now
  gates on **rank ≥ threshold** (not the run-time `email_eligible` flag). A human 🚩 re-rank /
  override now also refreshes `email_eligible`, so a rank upgrade qualifies an item for **both**
  announcement inclusion and the email digest without a pipeline rerun.
- **Announce view groups by canonical label** — topic bar buckets announcements by their
  most-shared Glossary Label (frequency, order-independent), resolving the SGK vs
  "Sosyal Güvenlik" split.
- **RCM moved to its own Configure section** — new **RCM** anchor tab; "LOKA Topic" renamed
  **RCM Topic**; added **RCM History** (expandable list of synced reference titles with JIRA
  links).
- **Fixes** — confirm-challenge now writes `significance_rank` so the badge reflects the human
  rank; `ranking_grounding` rows persist the `rank`.

## v3.13 — 2026-09-08
### L2 deep-fetch · title-first grouping · persistent announcements · direct RCM

- **L2 Deep Fetch (new mandatory pipeline step)** — `agents/l2_fetcher.py` runs after Glossary
  Match and before Rank. For each item it follows the URL, extracts the full article
  (reusing `extract_article` from `url_sources_runner`), and makes one AI call for a factual
  `l2_summary` + structured `act_ref` (law/act/gazette reference). **Any item failure stops the
  run** (`L2FetchError`) — no silent degradation. Ranking now sees the richer context.
- **Announcement grouping rebuilt** — new `agents/announcement_agent.py` owns
  Select → Title → Embed → Cluster → Assign → Compose → Persist. Grouping key is an
  **AI-generated English title** (cross-language), clustered by cosine with an **act_ref-first,
  date-proximity-fallback** merge guard. RCM body JSON is generated directly (PASS 2), so
  "Preview for RCM" is now instant.
- **Persistent, profile-scoped announcements** — `news_announcements` gains `profile_id`; the
  old delete-and-regenerate-per-run behaviour is gone. Announcements carry a `draft → done`
  (published/frozen) lifecycle. Item state machine on `news_items`: `announce_state`
  (`pending → assigned → excluded`), `announcement_id`, `english_title`, `added_after_publish`.
- **Incremental processing** — the new **Announcement tab** has a **"Process New/Changed"**
  button that runs the agent on `pending` items only (bounded cost). Re-rank / re-match flips an
  item back to `pending`; a `done` announcement is never mutated — a matching new item joins it
  marked **added after publish**.
- **`email_composer.py` is now a pure formatter** — reads `news_announcements` and renders the
  digest; all AI grouping/title/body generation moved to `announcement_agent`.
- **RCM action simplified** — Preview modal now offers a direct **Open RCM** link (per-profile
  `rcm_url` setting, replacing `l2s_url`); the JIRA Legal Change input was removed.
- **RCM reference titles cache** — new `rcm_reference_titles` table + `agents/rcm_reference_sync.py`
  + `/sync-rcm-titles` Claude Code command pull per-profile regulation titles from LOKA
  (`scope=regulations`, `topic=HCM`/`FIN`) to ground title generation. New profile config fields:
  **LOKA Topic** + **RCM Portal URL**.
- **Reusable `agents/embeddings_util.py`** (`get_embeddings` + `cosine`) factored out of
  `compare_news.py`.
- **Legacy `news_grouper.py` archived** (`archive/news_grouper.py`); its 3 controller call sites
  removed (each item is its own group on the retained v1 preview path).
- **News Details accordion** — `l2_summary` shown as an inline expandable section on Review items
  and Announcement source cards.

## v3.12 — 2026-09-08
### "Tag" retired · Analyze split · Review item-action redesign

- **Terminology: "tag" is gone as a concept.** Glossary step renamed **Glossary Match**
  (`agents/news_tagger.py` → `agents/glossary_match.py`, `tag_items` → `match_glossary`); the
  dedup/repetition classification is now **Status** (DB column `repetition_tag` →
  `repetition_status`, in-place migration; Review filter "Tag" → "Status"). UI/JS/CSS/docs all
  updated; `topic_label` / `dedup_status` unchanged.
- **Pipeline "Analyze" split into two visible steps: Glossary Match → Rank** (stepper now 9
  pills; controller emits per-step log markers; help modal + SPEC + lifecycle updated to match
  the real order — Glossary Match runs before Rank so a match can floor the rank).
- **Review item-action redesign**: **🚩 Re-rank** (formerly "Challenge"), **🔖 Re-match**, and
  **🌐 Translate** now sit on *every* card in both the flat and grouped views (previously the
  challenge/re-rank buttons only appeared inside the announcements view). The bare 1–5 override
  no longer changes rank silently — clicking a number opens the Re-rank modal pre-filled, and a
  **reason is mandatory** (saved as grounding + a Tier-1 signal). Toolbar "Re-rank All" removed.
- **Per-item Re-match** (`POST /admin/news/<id>/rematch`): re-runs Glossary Match on one item
  (deterministic, no AI).
- **Per-item Translate**: header language picker (remembered per browser), side-by-side
  original/translation display; `/review/translate` generalized from English-only to any
  `target_lang`.
- **Fix**: the `/challenge` route unpacked `_tier2_score` as 2 values but it returns 3 since
  v3.10 (rank, reasoning, effective_date) — the Re-rank/Challenge flow was erroring; now fixed.
- **Override display**: the 1–5 override strip is replaced by an **`AI rank: N`** label that
  shows **`AI: N › You: M`** (reason on hover) once overridden — the AI original stays visible.
  `human_rank_override`/`human_override_reason` are now loaded into the Review list.
- **Translate UX**: clicking 🌐 splits the card (original left, translation right) instead of
  appending a duplicated block; fixed a broken AI-client import (`email_sender` →
  `email_composer`) that made translation fail.
- **Docs**: README "How It Works" pipeline rewritten from the v2-era flow (removed the legacy
  `GROUP (AI)` step); SPEC §7.5 stage checklist and §7.10 Review UI refreshed; ranking sections
  and rank-scale table aligned (1–5, duplicates noted as a Compare dedup outcome).
- **Test Harness**: 22/22.

## v3.11 — 2026-09-08
### Pipeline Stage Help + Turkish source fixes

- **Pipeline help modal**: "?" button pinned to the right of the Run-tab stepper opens a modal explaining all 8 stages. Text sourced from a single canonical file, `configurations/pipeline_help.json` (loaded per-request; reword with no template/code change). `admin/app.py` `_load_pipeline_help()` + `run_status.html` modal; SPEC §9.1 points to the JSON.
- **Turkish date parsing** (`agents/news_filter.py`): parse ISO strictly first, then dateutil with `dayfirst=True` — DD.MM.YYYY (e.g. 10.05.2026) now reads as 10 May, not 5 October. Fixes months-old Turkish articles slipping past a 7-day lookback.
- **UTF-8 decoding** (`agents/url_sources_runner.py`): fall back to `apparent_encoding` when a server omits charset — fixes Turkish mojibake (Güvenlik was rendering as GÃ¼venlik). Applied to both `scrape_url_source_with_config` and `http_get`.
- **Glossary Turkish-İ matching + relevance floor** (`agents/news_tagger.py`, `agents/news_ranker.py`): `_norm()` strips the combining dot from `İ.lower()` so `istihdam` matches `İstihdam`; a real glossary match now floors significance at rank 2 so on-topic items aren't scored off-topic.
- **Reset Data** (`configurations/db.py`, `admin/templates/review_news.html`): new review-screen button with confirmation modal; reset now also clears each URL source's `last_successful_fetch` so re-runs start from a clean window instead of a stale delta anchor.
- **Rank scale documented**: the 1–5 significance scale — with labels Noise/Signal/Watch/Legal Change/Urgent (0 = Duplicate) — is now written up in SPEC.md §5.7a and surfaced in the Run-tab help modal via `configurations/pipeline_help.json` (`Analyzing.ranks`). Previously the per-level meaning lived only in the ranker's Tier-2 prompt.
- **Review filter help**: "?" button on the Review filter bar opens a modal explaining all four dimensions (Rank / Tag / Glossary / Email). Tag/Glossary/Email text in new `configurations/review_help.json`; the Rank scale is reused from `pipeline_help.json` (single source, no duplication).
- **Test Harness**: 22/22.

## v3.7 — 2026-09-06
### Deprecate Legal Repository
Retired the Legal Repository subsystem that was bundled into Legal Eagle by mistake (predates v3, out of scope for the pipeline tool):
- Removed `repo_nodes` + `repo_assets` table schema and all 11 DB helper functions from `configurations/db.py`
- Removed 8 Flask routes (`/admin/legal-repo/*`, `/admin/.../to-legal-repo`) from `admin/app.py`
- Deleted `admin/templates/legal_repo.html`
- Removed "Send to Legal Repo" modal variables (`repo_node_map`, `repo_parent_options`) from the review route
- Removed "Legal Repo ›" nav link from `admin/templates/base.html`
- Deleted `agents/loka_client.py` (stub with zero callers)
- Removed `repo_nodes`/`repo_assets` from `scripts/export_config.py` + `scripts/import_config.py`
- Data archived to `scripts/archive/repo_export_v3.7.json` before removal

## v3.6 — 2026-09-06
### Preview for RCM + Close-the-Loop

- **`rcm_template.json`** (`configurations/rcm_template.json`): official RCM announcement template structure (Introduction, Business Background/Impact, Reference to Related Legislation, Additional Information) + AI prompt template — single source of truth for all RCM-format rendering.
- **`announcement_rcm_json` column** on `news_announcements`: AI-filled RCM content (JSON), generated once on first Preview click and cached — never regenerated.
- **`rcm_filler.py`** (`agents/rcm_filler.py`): `fill_rcm_template(ann, sources)` — one AI call returns `{introduction, business_background}`; sources auto-assembled as Related Legislation; falls back to wrapping `announcement_md` if AI unavailable.
- **Preview for RCM modal** (`admin/templates/review_news.html`): "Preview for RCM" button per Announcement row; modal shows Title heading + Introduction bullets + Business Background bullets + Reference to Related Legislation links; Copy button copies full structured text to clipboard. First click triggers AI fill; all subsequent clicks read from DB.
- **Close-the-loop**: JIRA Legal Change # field + Mark Done button in the same modal → saves to `jira_legal_change` + `status='done'` columns; row status pill shows `✓ Done · <JIRA#>` and persists.
- **Hand-off**: per-profile L2S URL setting ("Open L2S" link in modal); set once, stored in `settings` table.
- **New routes** (`admin/app.py`): `GET /admin/announcements/<id>/template` (fills + returns RCM content), `POST /admin/announcements/<id>/publish` (save JIRA#/status), `POST /admin/profiles/<id>/l2s-url` (save L2S URL).
- **Test Harness v3.6**: 37/37 pass (4 skipped — AI). Three new `column_exists` assertions: `jira_legal_change`, `status`, `announcement_rcm_json`.

## v3.5 — 2026-09-05
### Glossary Gap Alert

- **`glossary_gap` column** on `news_items` (`configurations/db.py`): set by the Tag stage when `significance_rank ≥ 3` AND `topic_label = ["General"]` — a rank-significant item the current glossary cannot explain.
- **`flag_glossary_gaps()`** (`agents/news_tagger.py`): runs after `save_topic_labels()` in the TAG stage (`agents/agents_controller.py`); same id/source_id/url/hash fallback persistence as topic labels.
- **Review tab** (`admin/templates/review_news.html`): `⚠ N glossary gaps` toolbar strip with "Show only gaps" (reuses the existing LoB=gap filter chip); `⚠ Gap — no LoB match` badge per gap card (template was pre-scaffolded, now activated via `is_gap`).
- **Inline "+ Add to Glossary" panel**: AI suggests keywords for the item; user confirms a term + LoB; term is saved, item re-tagged, and the gap flag cleared — no navigation away.
- **New routes** (`admin/app.py`): `POST /admin/profiles/<id>/glossary/suggest` (AI keyword suggestions, regex fallback), `POST /admin/news/<id>/add-to-glossary` (add term + re-tag + clear flag).
- **Test Harness v3.5**: A5 `workplace safety` item (Tier-1 signal `min_rank=4`, no glossary match) asserts `glossary_gap=1`; maternity-leave item asserts `glossary_gap=0`. 34/34 pass (4 skipped — AI).
- **Docs**: `docs/lifecycle.html` corrected — the mislabeled "RCM Publish · v3.5" card is now split into a shipped green "Glossary Gap · v3.5" card and a "RCM Publish · v3.6" card (RCM/JIRA publish is v3.6, not v3.5).

## v3.4 — 2026-09-05
### Challenge + Grounding loop

- **Challenge modal** (`admin/app.py`, `admin/templates/review_news.html`): inline Challenge button per item; Challenge Agent calls GPT-4o with counter-argument prompt; result stored in `news_items.challenge_result`.
- **Grounding loop**: after Challenge the Tier 2 ranker re-runs on the challenged item; updated rank stored back. Re-rank action (F6) available on all items.
- **Topic→Announcement→Sources hierarchy** in Review tab: Level 1 = Topic, Level 2 = Announcement (`news_announcements` table, renamed from `news_aspects`), Level 3 = Sources. Clicking an Announcement renders `announcement_md` inline as markdown.
- **Email wired into pipeline**: `email_composer.generate_digest()` replaces old `email_sender` call in `agents_controller.py`.
- **Xanadu HCM demo profile** added to production DB (`configurations/config.db`); `scripts/refresh_xanadu_demo.py` copies latest harness run data from `tests/test.db` with full ID remapping.
- **Test Harness v3.4**: 32/32 pass (4 skipped — AI).
- **New DB**: `human_rank_override` + `challenge_result` columns on `news_items`; `news_announcements` table (renamed from `news_aspects`).

**Files Changed:**
- `admin/app.py` — challenge POST route, re-rank route, Xanadu review fix
- `admin/templates/review_news.html` — Topic→Announcement→Sources UI, challenge button
- `agents/agents_controller.py` — email wired into pipeline
- `agents/news_ranker.py` — re-rank on challenge
- `configurations/db.py` — new columns + table rename migration
- `scripts/refresh_xanadu_demo.py` — NEW Xanadu demo refresh script
- `tests/fixtures/expected/v3.4.json` — NEW harness assertions
- `tests/run_harness.py` — v3.4 harness function
- `docs/lifecycle.html` — Challenge step + Announcement → green

---

## v3.3 — 2026-09-05
### Tagging + Email V2 digest

- **Keyword tagging replaces AI grouping** (`agents/news_tagger.py` — new): deterministic glossary keyword matching assigns `topic_label` (JSON array) to every pipeline item; no LLM call for grouping.
- **Email gated on rank ≥ 3**: `email_eligible = 1` for rank ≥ 3 non-duplicate items (configurable threshold).
- **Email V2 digest format** (`agents/email_composer.py` — new): AI newsletter grouped by Authority → Topic Label; one cached AI call per group detects aspects; writes `news_aspects` rows; SAP Blue inline-CSS HTML.
- **`email_sender.py`** (`send_digest()`): calls composer, sends via SMTP, updates `email_sent` + `runs.email_status` (PENDING→SENDING→SENT/FAILED/SKIPPED).
- **Review UI**: email filter chip (All / Unsent only), Sent/Unsent pills, Send Email toolbar button with live count.
- **Run status page**: email stage bar + Resend button (FAILED state).
- **Publish dates** surfaced on review cards.
- **Test Harness v3.3**: 24/24 pass (26/26 after post-ship additions).
- **New DB**: `glossary_terms` table; `topic_label` + `email_eligible` columns on `news_items`; `news_aspects` table.

**Files Changed:**
- `agents/news_tagger.py` — NEW keyword tagger
- `agents/email_composer.py` — NEW V2 digest composer
- `agents/email_sender.py` — NEW `send_digest()` SMTP sender
- `agents/agents_controller.py` — TAGGING stage; digest wired post-SUCCESS
- `admin/app.py` — POST `/admin/send-email` route; email filter
- `admin/templates/review_news.html` — email filter chip, pills, toolbar button
- `admin/templates/run_status.html` — email stage bar + Resend
- `configurations/db.py` — `glossary_terms` table; new `news_items` columns
- `tests/fixtures/expected/v3.3.json` — NEW
- `tests/run_harness.py` — v3.3 harness function
- `docs/lifecycle.html` — Tag + Email Send + Save DB steps → green

---

## v3.2 — 2026-09-05
### Ranking Engine + Attribution AI

- **Three-tier ranking engine** (`agents/news_ranker.py` — new): Tier 0 DUPLICATE passthrough (rank 0, skips both tiers); Tier 1 deterministic keyword/regex rules from `ranking_signals` DB table; Tier 2 GPT-4o AI scoring (1–5) with few-shot grounding from `ranking_grounding` table. All AI calls wrapped via `ai_cache.py` for deterministic harness replay.
- **REPEATED tag** (`agents/compare_news.py`): items whose entity fingerprint has appeared in ≥3 prior runs get `repetition_tag='repeated'`; rank auto-elevated +1 (cap 5).
- **Attribution AI inference path** (`agents/authority_attributor.py`): feeds with no configured `authority_id` call GPT-4o with (title, content, authorities list) → best-match authority stamped as `authority_status='inferred'`.
- **Review UI**: rank badges (0–5 colour-coded circles), ✦ spark icon on inferred-attribution items, inline authority override dropdown on inferred items.
- **RANK pipeline stage** (`agents/agents_controller.py`): inserted after COMPARE; runs on all items including duplicates; upserts rank fields back to DB via `add_news_item()` upsert pattern.
- **Test Harness v3.2**: 19/19 pass (3 skipped — pending AI cache recording run for attribution + semantic-dedup assertions).
- **New DB**: 5 new columns on `news_items` (`significance_rank`, `rank_tier`, `rank_reasoning`, `repetition_tag`, `repetition_count`); 2 new tables (`ranking_signals`, `ranking_grounding`).

**Files Changed:**
- `agents/news_ranker.py` — NEW three-tier ranking engine
- `agents/compare_news.py` — REPEATED tag + repetition_count
- `agents/authority_attributor.py` — AI inference path (authority_status='inferred')
- `agents/agents_controller.py` — ATTRIBUTE wires db_conn; RANK stage after COMPARE
- `configurations/db.py` — 5 new columns + 2 new tables
- `admin/app.py` — authority override POST route
- `admin/templates/review_news.html` — rank badges, ✦ icon, authority override dropdown
- `tests/fixtures/expected/v3.2.json` — NEW (22 assertions)
- `tests/run_harness.py` — ai_available requires both emb + chat cache
- `docs/lifecycle.html` — Rank step resolved to green

---

## v3.1 — 2026-09-05
### First Pipeline-Touching Release — Harness-First

- **Structural fixes B1–B8**: age gate restored (was filtering in-date items), baseline anchor fixed, category bug resolved, OTHER category suppressed, missing publish date surfaced (`published_at` field), binary filter removed (items scored not deleted), hash fingerprint for exact dedup, translation layer decoupled.
- **F1–F5 features**: per-source `last_successful_fetch` (null = new source → fallback to date_scope), pre-run health check (parallel Gmail/AI Core/DB — hard block on failure), `runs.error_step`/`error_message` for per-stage error capture, immediate stop via threading event, force-fetch bounded by `date_scope` (re-fetched items score as DUPLICATE rank 0).
- **Source Simulator** (`tests/server.py` — new): localhost:9999 static HTTP server serving fixture XML feeds; enables fully offline harness runs.
- **Run All Active backend**: sequential profile thread with SSE live-row status updates per profile; skip-on-failure.
- **ATTRIBUTE pipeline stage** (`agents/authority_attributor.py` — new): stamps `publisher` + `authority_id` from feed config onto every collected item (`authority_status='configured'`).
- **Test Harness v3.1**: 23/23 pass — first full pipeline run against XN/HCM imaginary profile with real dedup + attribution assertions.

**Files Changed:**
- `agents/agents_controller.py` — structural fixes; ATTRIBUTE stage; Run All Active backend
- `agents/compare_news.py` — B1/B3/B6/B8 fixes; publisher/authority fields in item record
- `agents/authority_attributor.py` — NEW configured attribution path
- `configurations/db.py` — publisher/authority columns on news_items; authorities table
- `configurations/config_loader.py` — authority config helpers
- `admin/app.py` — Run All Active SSE; F3 error capture
- `tests/run_harness.py` — v3.1 harness function
- `tests/server.py` — NEW fixture server
- `tests/reset_and_seed.py` — XN/HCM profile + ranking_signals seed
- `tests/assertions.py` — publisher/authority/dedup assertion types
- `tests/fixtures/` — 4 RSS feed XML files + expected/v3.1.json

---

## v3.0 — 2026-09-04
### Admin UI Overhaul + Source Attribution Config + Test Harness Foundation

- **Admin UI redesign**: FCL 3-state layout — Configure / Run / Review tabs replace the previous single-page scroll. Per-tab content panels with persistent tab state.
- **Run All Active UI**: one-click multi-profile runner button on the dashboard; per-profile status pills; toast notification on trigger (backend wired in v3.1).
- **Source Attribution config**: new `authorities` DB table + Authorities CRUD section in Configure tab; RSS feed add/edit forms extended with Publisher and Authority dropdowns; "Channel" replaces "Source Type" label in Review UI.
- **Test Harness v3.0** (`tests/run_harness.py` — new): DB schema verification only — seeds XN/HCM imaginary profile (Xanadu, Finland/HCM) and asserts required tables + columns exist.
- **Repo cleanup**: `Roadmap/` directory for pipeline redesign spec; `docs/lifecycle.html` pipeline lifecycle diagram added; `.claude/` added to `.gitignore`.

**Files Changed:**
- `admin/app.py` — FCL tab routing; authorities CRUD routes; Run All Active trigger
- `admin/templates/` — base.html FCL layout; profile.html Configure tab; run_status.html Run tab; review_news.html Review tab (Channel rename)
- `configurations/db.py` — authorities table
- `tests/run_harness.py` — NEW (v3.0 schema assertions)
- `tests/reset_and_seed.py` — NEW (XN/HCM profile seed)
- `tests/assertions.py` — NEW (assertion runner)
- `docs/lifecycle.html` — NEW pipeline lifecycle diagram
- `Roadmap/v3-pipeline-redesign.md` — NEW pipeline redesign spec

---

## v2.32 — 2026-06-28
### ANS Disabled (Non-BTP Mode) + ANS OAuth Fix + Gitignore Cleanup

- **ANS disabled**: ANS send path commented out — Gmail SMTP is now the sole active email transport. ANS code preserved for re-activation when BTP environment is rebuilt. Re-provision button remains visible in UI but is dimmed/disabled with tooltip.
- **ANS OAuth fix**: Token request now uses HTTP Basic auth (`auth=(client_id, client_secret)`) instead of body params — required by SAP XSUAA for client credentials flow. Fixes 404 errors when provisioning ANS Actions via "Re-provision all"
- **Gitignore cleanup**: Added `.playwright-mcp/`, `.superpowers/`, `docs/superpowers/`, `server.pid`, `outputs/GR_HCM/` to `.gitignore`

**Files Changed:**
- `agents/ans_sender.py` — ANS implementation commented out; stub always returns `None`
- `agents/email_sender.py` — ANS-first block commented out; direct Gmail SMTP path
- `admin/app.py` — ANS provisioning calls commented out; `ans_available` hardcoded `False`
- `admin/templates/profile.html` — Re-provision button dimmed/disabled when ANS unavailable
- `.gitignore` — added tooling and runtime artifacts

## v2.31 — 2026-06-01
### UI Fixes & Enhancements

- **URL source editing**: Edit form now exposes all fields including URL rename, mode, sample link, read more label, date template, recursive depth/domains/filter
- **Auto-translate in Review**: Non-English profiles auto-translate visible news items to English on page load via SAP AI Core (shown inline below original)
- **Pre-run preflight checklist**: Start Run button disabled until all checks pass — sources configured, email receiver, AI Core creds, Twitter token validity
- **Legal Repo lifecycle bar**: completed=green, current=blue, future=dark grey
- **Resources/ served by Flask**: MindMap and other Resources/ files accessible via `/Resources/<path>`

## v2.30 — 2026-06-01
### Legal Repository + Greece Profile

**Legal Repository:**
- New global `/admin/legal-repo` page — three-column layout (countries / topic tree / node detail)
- New DB tables: `repo_nodes` + `repo_assets`
- Node lifecycle: NEW → SCOPING → ANALYZED → COMPLETE with maturity levels 1–4
- Parent-child hierarchy: EPIC-level parent nodes with independent topic-level children
- SAP Linkage: attach jira_epic, jira_req, sap_note, prd, kba, mindmap, xml_schema, analysis assets per node
- Review page: `📋 In Legal Repo` badge + `+ L2S Prompt` button — news → repo traceability
- `📚 Legal Repo` link added to navbar

**Greece Profile:**
- New Greece HCM profile (GR/HCM, language el) with 8 URL sources and 87 glossary terms
- 8 seed repo nodes: ERGANI II parent (ANALYZED, Level 3) + 4 ERGANI II children + EFKA + TEKA + AADE
- ERGANI II MindMap v2 linked as knowledge asset (mindmap type)
- Seeding scripts: `scripts/seed_greece_profile.py`, `scripts/seed_greece_repo.py` (both idempotent)

## v2.26 — 2026-05-13
### Run Log Visualization + ANS Email Integration + Per-Feed RSS Tracking

**Run Log Visualization (run_status.html — major redesign):**
- Replaced raw terminal log with a two-panel layout: vertical stage checklist (left) + per-stage log panel (right)
- 7 pipeline stages (Starting, Collecting, Filtering, Comparing, Grouping, Sending, Done) with live state icons (idle · / active ⟳ / done ✓ / skipped ⏭ / failed ✗)
- Per-stage status summaries extracted from log lines (e.g. "55 collected", "4 relevant", "0 new · 0 updated", "sent ✓")
- Collecting stage expands to show individual source sub-items:
  - **RSS feeds**: one row per feed URL (`↳ RSS: {url}: fetching...` / `↳ RSS: {url}: N items`)
  - **Twitter accounts**: one row per `@handle` (parsed from `↳ Fetching from N accounts: @h1, @h2, …`)
  - **URL sources**: registered idle from `↳ {url}: MODE mode`, activated by `[Source N/M] url={url}`
- Clicking any sub-item or stage switches the right panel to show only that source's log lines
- Log lines auto-follow the active source during a live run; full log retained for debugging

**ANS Email Integration (agents/ans_sender.py — new file):**
- Added SAP BTP Alert Notification Service (ANS) as the primary email transport on BTP
- Gmail App Passwords are rejected from cloud IPs; ANS handles outbound digest emails
- Auto-provisions one Action + Condition + Subscription per recipient (idempotent)
- Fallback chain in `email_sender.py`: ANS first → Gmail SMTP on failure
- Gmail IMAP credentials still required for reading monitor-update emails via IMAP
- BTP_DEPLOYMENT.md updated with ANS setup instructions

**Per-Feed RSS Tracking (agents/agents_controller.py):**
- Added `↳ RSS: {url}: fetching...` / `↳ RSS: {url}: N items` print statements to the RSS loop in `run_single_profile()`
- Enables the visualization to show individual RSS feed progress as sub-items

**Files Changed:**
- `admin/templates/run_status.html` — Complete run log visualization redesign
- `agents/ans_sender.py` — New ANS email sender module
- `agents/email_sender.py` — ANS-first fallback chain; Gmail as secondary
- `agents/agents_controller.py` — Per-feed RSS print statements
- `BTP_DEPLOYMENT.md` — ANS service binding and setup instructions

---

## v2.25 — 2026-05-12
### Skip Grouping Run Option

**New Feature:**
- **Skip Grouping Checkbox**: New run option to bypass the AI news grouping stage
  - Located in Run Options between "Skip filtering" and "Test mode"
  - When checked: each collected item appears as its own separate email entry (no AI clustering)
  - When unchecked: normal AI grouping behaviour (items clustered by regulatory theme)
  - State persisted in browser localStorage (remembered across sessions)
  - Useful for: testing email layout, bypassing slow LLM grouping, debugging

**How it works:**
- Backend wraps each item into a single-item group compatible with the email sender
- Uses the item's raw `content` field as the email summary (no AI-generated summary)
- All items retain their original category, links, and update status
- Produces longer emails with more granular per-article entries

**Files Changed:**
- `agents/agents_controller.py` — Added `skip_grouping: bool = False` parameter to `run_profile_once()`; bypass/wrap logic in grouping stage
- `admin/app.py` — Reads `skip_grouping` from form, passes through `_worker` to `run_profile_once()`
- `admin/templates/run_status.html` — Added checkbox + localStorage persistence

---

## v2.23 — 2026-05-08
### Run-Level Lookback Override

**New Feature:**
- **Lookback Dropdown in Run Modal**: Per-run override of the profile-level lookback window
  - Replaces the old "Force full fetch" checkbox
  - Options: Use profile default / Force full (re-fetch all) / Delta (since last fetch) / Today only / Last 7 days / Last 30 days
  - "Use profile default" = no override; profile's configured date_scope applies
  - "Force full (re-fetch all)" = bypass delta tracking for this run only
  - Override is one-time: profile setting is unchanged after the run

**Design rationale:**
- "Force full re-fetch" is now a per-run option rather than a permanent profile setting
- `force_full` removed from the profile Default Lookback Window dropdown (profile now has 4 clean options)
- Existing profiles with `force_full` or `all` in the DB are backward compatible (treated as "Delta")

**Files Changed:**
- `agents/agents_controller.py` — Added `lookback_override: Optional[str] = None` param; injects over `PROFILE_DATE_SCOPE` when set
- `admin/app.py` — Replaced `force_run` form field with `lookback_override`; maps `force_full` → `force_run=True` for backward compat
- `admin/templates/run_status.html` — Replaced "Force full fetch" checkbox with "Lookback" select dropdown
- `admin/templates/profile.html` — Removed `force_full` option from Default Lookback Window; updated help text

---

## v2.22 — 2026-05-08
### Profile-Level Lookback Window

**New Feature:**
- **Unified Lookback at Profile Level**: Single `date_scope` setting on the profile drives all sources
  - Applies to: RSS feeds, Twitter accounts, and URL sources
  - Removes the need to set lookback days individually per RSS feed, Twitter account, or URL source
  - "🗓 Default Lookback Window" card added to the profile configuration page (above RSS Feeds)

**Lookback options:**
| Value | Meaning |
|-------|---------|
| `delta` | Fetch everything on first run; only new items since last run afterwards |
| `today` | Today only (UTC midnight as anchor) |
| `last_7_days` | Last 7 calendar days |
| `last_30_days` | Last 30 calendar days |

**Profile UI changes:**
- Per-source "Lookback Days" columns removed from RSS Feeds, Twitter Accounts, and URL Sources tables
- Per-source lookback fields removed from all Add/Edit forms
- New "Default Lookback Window" card with 4-option dropdown and Save button

**Bug fixes:**
- Fixed `PROFILE_DATE_SCOPE` NameError in `run_profile_once()` — was referenced but never defined, causing URL sources to crash on every manual run
- Fixed `days=0` (today only) bug — `filter_items_by_date(days=0)` silently defaulted to 7 days; fixed by injecting `since_date = start_of_UTC_midnight` instead

**Database:**
- Added `date_scope TEXT DEFAULT 'delta'` column to `profiles` table (auto-migrated)
- `max_lookback_days` columns on `rss_feeds` and `tweet_accounts` kept in DB but no longer shown in UI

**Files Changed:**
- `configurations/db.py` — `ALTER TABLE profiles ADD COLUMN date_scope` (idempotent)
- `configurations/config_loader.py` — `parse_date_scope()` updated; added `load_profile_date_scope()`, `save_profile_date_scope()`
- `agents/agents_controller.py` — Both `run_controller()` and `run_profile_once()` read `PROFILE_DATE_SCOPE`; apply to RSS, Twitter, and URL sources
- `admin/app.py` — New `POST /admin/profiles/<id>/date-scope/update` route; removed `date_scope` from URL source add/update
- `admin/templates/profile.html` — New Default Lookback Window card; removed per-source Lookback Days from all tables and forms

---

## v2.21 — 2026-05-08
### URL Date Control (Mechanism A + Delta Tracking)

**New Feature — Mechanism A (Post-Scrape Date Filter):**
- URL sources now apply a post-scrape date filter after content is collected
- Controller injects `since_date` (for delta/today) or `days` (for fixed windows) into each URL source run
- Correctly handles "today only" by using UTC midnight as the anchor (not current time)

**New Feature — Delta Tracking:**
- `last_successful_fetch` timestamp per URL source tracked and updated after each successful fetch
- DELTA mode: fetches items published since last run (incremental)
- FULL mode: fetches entire lookback window (first run, force_full override, or `force_run`)
- Mode printed in logs: e.g. `DELTA mode: since 2026-05-07T09:30:00 (max lookback: 7 days)`

**Files Changed:**
- `agents/url_sources_runner.py` — Mechanism A post-scrape filter using injected `since_dt`/`days`
- `agents/agents_controller.py` — Per-source delta/full mode calculation; injects correct params into runner

---

## v2.20 — 2026-04-28
### Skip Filtering + Run Options Persistence

**New Features:**
1. **Skip Filtering Checkbox**
   - New option to bypass LLM relevance check for testing
   - Useful for debugging: see all collected items without filtering
   - Shows warning in logs when enabled
   - All collected items treated as relevant

2. **Run Options Persistence**
   - All 4 run option checkboxes now remember your selections
   - Saved to browser localStorage per profile
   - Auto-restores on page load, auto-saves on change
   - Persisted options:
     - Force full fetch
     - Skip comparison (treat all as new)
     - Skip filtering (accept all as relevant) ← NEW
     - Test mode (skip emails)

**User Experience:**
- **Before**: Had to re-check options every run (e.g., "Test mode")
- **After**: Checkbox states remembered automatically ✅
- **Before**: No way to see all collected items without filtering
- **After**: Can toggle "Skip filtering" for testing ✅

**Files Changed:**
- `admin/templates/run_status.html` — Added skip filtering checkbox + localStorage persistence
- `admin/app.py` — Captures and passes skip_filtering parameter
- `agents/agents_controller.py` — Implements skip_filter logic
- `memory-bank/` — Updated documentation
- `CHANGELOG.md` — This entry

---

## v2.19 — 2026-04-28
### Source Selection Fix (Empty Selection = Run None)
- **Problem**: Unchecking all URL sources ran ALL sources instead of none
  - Root cause: Empty list `[]` was converted to `None` (meaning "run all")
  - Violated user intent: unchecked boxes should mean "run none"

- **Solution**: Smart detection with hidden UI flags
  - Added `has_rss_sources`, `has_twitter_sources`, `has_url_sources` flags
  - Backend distinguishes between:
    - Empty list `[]` (UI shown, user wants none) → Run **0 sources** ✅
    - `None` (no UI, API call) → Run **all sources** ✅ (backward compatible)

- **Result**: 
  - Uncheck all sources → Runs 0 sources (respects user choice)
  - API calls without form data → Runs all sources (backward compatible)
  - No breaking changes to existing automation

### Files Changed
- `admin/app.py` — Added smart detection logic
- `admin/templates/run_status.html` — Added hidden flags
- `memory-bank/` — Updated documentation
- `CHANGELOG.md` — This entry

---

## v2.18 — 2026-04-28
### Twitter Status Card Compact Design
- **Error-Only Display**: Twitter status card now only appears when there's an error
  - No card shown when everything is working (saves vertical space)
  - Red error banner appears only when Twitter API has issues
  - Shows error message with "Clear Error & Retry" button
  - Same error flag system from profile page, now consistent on Run page

### Rationale
- Reduces visual clutter on Run page
- Users only see Twitter status when action is needed
- Consistent with "show errors, hide success" design pattern
- Saves ~100px of vertical space per profile

### Files Changed
- `admin/templates/run_status.html` — Replaced card with error-only banner
- `admin/app.py` — Added twitter_error_flag to run_status template
- `CHANGELOG.md` — This entry

---

## v2.17 — 2026-04-28
### Review UI Simplification & Cleanup
- **Review Page UI Improvements**:
  - Removed redundant tab buttons (Accepted/Filtered/Reviewed)
  - Made stat cards clickable for direct navigation
  - Added hover effects and active state styling
  - Cleaner, more intuitive card-based interface

- **Run Page Cleanup**:
  - Removed "Clear Historical News" button (redundant with Review page controls)
  - Users now manage history from Review page with granular options:
    - "Clear All" button (clears everything)
    - "Clear Reviewed" button (clears only scored items)

- **Scoring Integration**:
  - Confirmed scoring is integrated into filtering pipeline
  - High-score rescue mechanism: items scored ≥ 4 are used as baseline
  - Filtering priority: Age Gate → LLM/Glossary Check → High-Score Rescue
  - Your scores teach the system to recognize relevant patterns

### Files Changed
- `admin/templates/review_news.html` — Removed tab buttons, made cards clickable
- `admin/templates/run_status.html` — Removed Clear button and dialog
- `memory-bank/` — Updated all documentation files
- `CHANGELOG.md` — This entry

---

## v2.16 — 2026-04-28
### Admin UI Fixes & Enhancements
- **Table Consistency Improvements**:
  - Added "Lookback Days" column to RSS Feeds table
  - Added "Lookback Days" column to Twitter Accounts table
  - Added "Lookback Days", "Sample Link", and "Read More Label" columns to URL Sources table
  - All tables now show complete configuration at a glance

- **Form Field Ordering**:
  - Reordered Add form fields to match table column order
  - Reordered Edit form fields to match table column order
  - Consistent left-to-right flow: Lookback Days → Sample Link → Read More Label → Crawl Type

- **Section Reordering**:
  - Reordered profile page sections to match pipeline execution order:
    1. Profile Language
    2. RSS Feeds
    3. Twitter Accounts
    4. URL Sources
    5. Email Receivers
    6. Monitor Notifications
    7. Glossary

- **Recursive Fields Toggle**:
  - Fixed recursive fields toggle in Add form (now shows/hides correctly)
  - Added recursive fields toggle to Edit form for non-recursive sources
  - Both Add and Edit forms now have identical behavior when selecting "Recursive" mode
  - Dynamic IDs for each edit form (edit1UrlMode, edit2UrlMode, etc.)

- **Developer Experience**:
  - Enabled Flask `TEMPLATES_AUTO_RELOAD` for faster template iteration
  - Templates now reload automatically without server restart

### Files Changed
- `admin/templates/profile.html` — Table columns, form field ordering, recursive fields toggle
- `admin/app.py` — Added TEMPLATES_AUTO_RELOAD configuration
- `SPEC.md` — Updated Section 9 (Admin UI) documentation
- `memory-bank/` — Updated all documentation files
- `CHANGELOG.md` — This entry

---

## v2.15 — 2026-04-28
### Scheduler Removal & Cleanup
- **Removed Built-in Scheduler**: Eliminated incomplete scheduler implementation
  - Deleted `scripts/schedule_runner.py` (194 lines)
  - Deleted `scripts/scheduler_entry.sh` (34 lines)
  - Deleted `scripts/launchd/legal.eagle.scheduler.plist` (63 lines)
  - Removed Schedule section from Admin UI profile page
  - Total: 291 lines of unused code removed

- **Documentation Updates**: Clarified scheduling approach
  - Updated SPEC.md to remove scheduler references
  - Updated README.md scripts/ description
  - Updated BTP_DEPLOYMENT.md architecture diagram
  - Documented external scheduling options (BTP Job Scheduler, cron, etc.)

### Rationale
- Built-in scheduler was incomplete and non-functional
- Prefer external scheduling for better flexibility and platform integration
- Eliminates confusion from misleading UI showing non-working schedule settings
- Cleaner codebase with one less system to maintain

### External Scheduling Options
Users can schedule runs via:
- **BTP Job Scheduler** (for cloud deployments) — calls Admin UI or API endpoints
- **Cron** (for Linux/macOS) — `0 9 * * * cd /path/to/legal-eagle && python3 agents/agents_controller.py --profile-id 1`
- **Windows Task Scheduler** (for Windows)
- **Manual runs** via Admin UI (always available)

### Files Changed
- `scripts/schedule_runner.py` — Deleted
- `scripts/scheduler_entry.sh` — Deleted
- `scripts/launchd/legal.eagle.scheduler.plist` — Deleted
- `admin/templates/profile.html` — Removed Schedule section
- `SPEC.md` — Removed scheduler references
- `README.md` — Updated scripts/ description
- `BTP_DEPLOYMENT.md` — Updated architecture diagram
- `memory-bank/` — Updated all documentation files
- `CHANGELOG.md` — This entry

---

## v2.14 — 2026-04-28
### Selective Source Execution & Bug Fixes
- **Selective Source Execution**: Users can now choose which sources to run from the Run page
  - Added source selection panel with checkboxes for RSS Feeds, Twitter Accounts, and URL Sources
  - Collapsible sections with source counts in headers (e.g., "RSS Feeds (1)")
  - Selection state persisted in browser localStorage (remembers your last selection)
  - Default behavior: all sources selected (opt-out model)
  - Backend filters sources before fetching based on your selection
  - Logs show filtered counts: "📰 Filtered RSS feeds: 1 selected out of 1"

- **Critical Bug Fixes**: Resolved multiple runtime errors blocking pipeline execution
  1. **Missing Python imports** — Fixed `name 'Optional' is not defined` error
  2. **Twitter API errors** — Fixed `'dict' object has no attribute 'lstrip'` error when fetching tweets
  3. **Email generation errors** — Fixed `name 'nbg' is not defined` error when building email
  4. **UI button issues** — Fixed "Clear Historical News" and "Resend Last Email" buttons not working
  5. **Stale run detection** — Fixed buttons being disabled due to old crashed runs in database

### Use Cases
- **Test single source**: Select one RSS feed or Twitter account to test configuration
- **Skip problematic sources**: Temporarily exclude sources that are down or timing out
- **Faster testing**: Run only the sources you need during development/debugging
- **Flexible workflows**: Mix and match sources for different monitoring scenarios

### Files Changed
- `agents/agents_controller.py` — Added source filtering logic and imports
- `admin/app.py` — Added template variables and source selection extraction
- `agents/email_sender.py` — Fixed variable typos
- `admin/templates/run_status.html` — Added source selection UI
- `memory-bank/` — Updated all documentation files
- `CHANGELOG.md` — This entry

---

## v2.13 — 2026-04-24
### Strategic Roadmap Update & AI4GPM Submission
- **Updated Strategic Evolution**: Expanded from 5-stage to 6-stage roadmap
  - Added **Stage 3 — SAP Consultant** with Taxonomy MCP integration
  - Maps legal changes to affected SAP products (HCM, Payroll, SuccessFactors, S/4HANA)
  - Identifies impacted SAP objects, processes, and functional areas
  - Determines if changes require standard configuration or custom enhancement
  - Bridges gap between legal interpretation and implementable SAP requirements
  - New sequence: Journalist → Lawyer → **SAP Consultant** → Smart MCP → Virtual LPM → Executive Advisor

- **AI4GPM Idea Submission**: Created production JIRA idea (GSIDEAS-457)
  - Title: "Legal Eagle: From Regulatory Intelligence to Virtual Localization Product Manager"
  - Complete 6-stage evolution roadmap with quantifiable benefits
  - Submitted to AI4GPM evaluation pipeline for review
  - URL: https://jira.tools.sap/browse/GSIDEAS-457

- **Documentation Cleanup**: Renamed `docs/README.md` to `docs/INDEX.md`
  - Eliminated naming conflict with root README.md
  - Clarified purpose as documentation navigation/index file
  - Updated header to "Legal Eagle Documentation Index"

### Files Changed
- `README.md` — Updated vision with 6-stage evolution, added SAP Consultant stage description
- `Big_Picture.md` — Already contained v4 with 6-stage roadmap (source of truth)
- `docs/INDEX.md` — Renamed from docs/README.md, updated header
- `CHANGELOG.md` — This entry
- `memory-bank/activeContext.md` — Updated to v2.13
- `memory-bank/progress.md` — Added v2.13 entry

---

## v2.12 — 2026-04-24
### Server Stability & Auto-Reload
- **Fixed Flask Reloader Crashes**: Disabled Flask's built-in reloader to prevent orphan processes
  - Issue: Flask reloader creates parent + child processes; crashes leave orphans blocking port 8080
  - Solution: Set `use_reloader=False` in `app.run()` to prevent port conflicts
  - Trade-off: Manual restart required after code changes (but more stable)

- **Auto-Reload with Watchdog**: Added smart file-watching script for development
  - New script: `scripts/start_admin_with_autoreload.sh`
  - Uses `watchdog` package to monitor all Python files
  - Automatically restarts server when any `.py` file changes
  - Cleans up old processes before restart (no port conflicts)
  - Watches recursively: `admin/`, `agents/`, `configurations/`
  - Ignores: test files, `__pycache__`, hidden files

- **Fixed Admin UI Dict Error**: Resolved crash when viewing run page
  - Error: `AttributeError: 'dict' object has no attribute 'lstrip'` on line 330
  - Cause: `load_tweet_accounts()` now returns `List[Dict]` but code expected `List[str]`
  - Fix: Updated to handle both formats: `a['handle'] if isinstance(a, dict) else a`
  - Impact: Run page now displays Twitter account list correctly

### Development Workflow
- **Best of Both Worlds**: Auto-reload during development + auto-start after restart
  - Development: Use `start_admin_with_autoreload.sh` for instant code reload
  - Production: Add same script to Login Items for auto-start on login
  - No need to choose between features anymore

### Dependencies
- Added `watchdog==6.0.0` for file monitoring

### Files Changed
- `admin/app.py` — Set `use_reloader=False`, fixed Dict handling on line 330
- `scripts/start_admin_with_autoreload.sh` — New auto-reload script with watchdog

---

## v2.11 — 2026-04-22
### Bilingual Email Body
- **Bilingual card design**: Each news group now renders as a single card with two halves:
  - Top half: profile language (flag-inspired left border + tinted background per country)
  - Bottom half: English translation (gray left border + light gray background)
  - Thin horizontal divider separates the two halves
  - Language badge (e.g. "TR", "EN") shown at top of each half
  - Source links appear only in the English half
- **Country-coded colours**: Left border and background tint inspired by national flag colours
  - Saudi Arabia / UAE / Kuwait → green; Turkey / Spain / Morocco → red; Germany → dark; France / UK → blue
- **Single email send**: All recipients receive one bilingual email ("To" includes all addresses)
  - Eliminated per-receiver translation language grouping
  - Translation to English done once via SAP AI Core, then reused for the entire email
- **Simplified send_email()**: No longer groups receivers by language; single SMTP call
- **Admin UI**: Removed per-receiver "Translation Language" dropdown (no longer needed)
- **Monolingual fallback**: When profile language is English, standard single-language card is used

### Files Changed
-  — COUNTRY_COLORS, LANG_BADGES, bilingual build_email_body, simplified send_email
-  — Updated send_email calls
-  — Removed Translation Language column from Email Receivers table

### Twitter Pipeline Improvements
- **Removed 15-minute wait**: Eliminated artificial delay between Twitter fetches
  - Previous: 15-minute mandatory wait after each account
  - New: Immediate fetching (rate limits handled by API)
  - Speeds up multi-account Twitter collection

- **Error Flag System**: Persistent error tracking across runs
  - `set_twitter_error_flag(profile_id, error_msg, conn)` — Sets error state
  - `get_twitter_error_flag(profile_id, conn)` — Returns (error_msg, timestamp)
  - `clear_twitter_error_flag(profile_id, conn)` — Clears error state
  - Stored in SQLite settings table (key: `twitter_error_flag`)

- **Smart Pipeline Skip**: Agents controller checks error flag before Twitter fetch
  - If flag is set: Skips Twitter agent entirely
  - Prevents repeated failures when credentials are invalid
  - User must manually clear flag via Admin UI

- **Admin UI Error Banner**: Visual error status on profile page
  - Red banner: Shows error message + "Clear Error & Retry" button
  - Green banner: "Twitter API Status: OK" when no errors
  - Twitter section moved to top of profile page for visibility

- **POST Route**: `/admin/profiles/<id>/tweets/clear_error`
  - Clears error flag and allows retry
  - Redirects back to profile page
  - Enables quick recovery from transient errors

### UI/UX Improvements
- **Profile Page Reordering**: Twitter section moved to top (after Schedule)
  - New order: Language → Schedule → Twitter → RSS → URL Sources → Email → Monitor → Glossary
  - Emphasizes Twitter as primary news source

- **Removed Reset Quota Date**: Eliminated manual quota date picker
  - Previous: User had to manually set next reset date
  - New: Automatic error flag system handles quota issues
  - Simpler workflow: Just click "Clear Error & Retry"

- **Twitter Table Enhancement**: Added "Last Fetch" column
  - Shows ISO timestamp of last successful fetch
  - Displays "Never" for accounts not yet fetched
  - Helps diagnose stale accounts

### Additional Files Changed
- `agents/tweet_feed.py` — Error flags + removed 15-min wait
- `agents/agents_controller.py` — Check error flag before Twitter agent
- `admin/app.py` — Clear error route + pass flag to template
- `admin/templates/profile.html` — Reorder sections + error banner + table fixes

---

## v2.10 — 2026-04-20
### Twitter Error Flag System
- **Persistent Error Tracking**: Added error flag system to prevent repeated Twitter API failures
  - `set_twitter_error_flag(profile_id, error_msg, conn)` — Stores error state in settings table
  - `get_twitter_error_flag(profile_id, conn)` — Returns (error_msg, timestamp) tuple
  - `clear_twitter_error_flag(profile_id, conn)` — Clears error state (manual recovery)
  - Stored as JSON in settings table with key `twitter_error_flag`

- **Smart Pipeline Skip**: Agents controller checks error flag before running Twitter agent
  - If flag set: Skips Twitter fetch entirely, logs reason
  - Prevents wasted API calls when credentials are invalid
  - User must manually clear flag via Admin UI after fixing issue

- **Admin UI Error Banner**: Visual error status on profile page
  - Red banner: Shows error message + "Clear Error & Retry" button
  - Green banner: "Twitter API Status: OK" when no errors
  - POST route: `/admin/profiles/<id>/tweets/clear_error` to reset flag

### Files Changed
- `agents/tweet_feed.py` — Error flag functions + integration in search_tweets_multi_account()
- `agents/agents_controller.py` — Check error flag before Twitter agent execution
- `admin/app.py` — Clear error route + pass twitter_error_flag to template
- `admin/templates/profile.html` — Error banner UI component

---

## v2.9 — 2026-04-18
### Per-Source Date Tracking
- **Max Lookback Days**: Added `max_lookback_days` column to `rss_feeds` and `tweet_accounts` tables
  - Default: 7 days (configurable per source)
  - Acts as safety cap to prevent excessive backdating
  - Used by date filter to skip items older than lookback window

- **Last Fetch Date**: Added `last_fetch_date` column to track incremental fetching
  - Stored as ISO 8601 timestamp (e.g., "2026-04-18T14:30:00Z")
  - Updated after each successful fetch
  - First run: Fetches full lookback window
  - Subsequent runs: Fetches only items since last fetch (delta mode)

- **API Changes**: `list_rss_feeds()` and `list_tweet_accounts()` now return `List[Dict]`
  - Before: `List[str]` (just URLs/handles)
  - After: `List[Dict]` with keys: `{url/handle, max_lookback_days, last_fetch_date}`
  - Allows agents to make date-aware fetching decisions

- **Database Functions**: Added timestamp update functions
  - `update_rss_feed_last_fetch(profile_id, url, timestamp, conn)`
  - `update_tweet_account_last_fetch(profile_id, handle, timestamp, conn)`
  - Exported via `config_loader.py` for use by agents

### Twitter Improvements
- **Token Validation**: Added `validate_twitter_token()` pre-flight check
  - Tests bearer token before attempting fetches
  - Returns validation status message
  - Prevents wasted API calls with invalid credentials

- **402 Payment Required Handling**: Detects Twitter API credit depletion
  - Captures "Monthly credits depleted" error
  - Sets error flag to skip subsequent Twitter fetches
  - Displays error message in Admin UI

- **Rate Limit Awareness**: Enhanced rate limit detection
  - Logs `x-rate-limit-*` headers when 429 encountered
  - Shows remaining requests and reset time
  - Helps diagnose quota issues

### Files Changed
- `configurations/db.py` — Schema changes + new functions
- `configurations/config_loader.py` — Export timestamp update functions
- `agents/agents_controller.py` — Handle Dict format from RSS/tweet loaders
- `agents/tweet_feed.py` — Token validation + 402 handling + error flags
- `agents/date_filter.py` — Use max_lookback_days for filtering

---


## v2.8 — 2026-04-07
### Bug Fixes
- **Gmail Environment Variable**: Fixed incorrect environment variable name for Gmail sender
  - Changed from `LEGAL_EAGLE_GMAIL_EMAIL_SENDER` to `LEGAL_EAGLE_GMAIL_EMAIL`
  - Updated `configurations/config_loader.py` to read correct variable
  - Updated `.env` file with correct variable name
  - Updated SPEC.md documentation (Section 8.1)
  - Impact: "Resend Last Email" feature now works correctly
  - Simplified credential loading - removed unnecessary fallback logic

- **CRITICAL: Clear Historical News Fixed**: Resolved issue where clearing news baseline was clearing wrong profile's data
  - Root cause: `profile_id` parameter not passed to `clear_news_baseline()` function
  - Fix: Added `profile_id` parameter and passed through from route handler
  - Impact: Users can now safely clear historical news without affecting other profiles
  - Files modified: `admin/app.py`, `configurations/config_loader.py`, `configurations/db.py`

- **Auto-reload After Clear**: Page now automatically reloads after clearing historical news
  - Added JavaScript redirect after successful clear operation
  - Provides immediate feedback that operation completed
  - Eliminates need for manual page refresh

- **Force Run Now Working**: Removed 2-hour cooldown restriction on manual runs
  - Previous: Manual runs blocked if last run was < 2 hours ago
  - New: Manual runs always allowed (cooldown only for scheduled runs)
  - Rationale: Users should control when to run, not the system
  - Files modified: `agents/agents_controller.py`

### New Features
- **Resend Email from HTML Preview**: New "📧 Resend Last Email" button on Run page
  - Parses `email_preview.html` and sends to all configured receivers
  - Supports translation for each receiver's preferred language
  - Allows testing email delivery without running the full pipeline
  - Uses existing `send_email()` function with full translation support
  - New module: `scripts/resend_email_from_html.py` with HTML parser
  - Route: `/admin/profiles/<id>/resend_email` (POST)
  - Test script: `scripts/test_resend_email.py`

- **Skip Comparison Option**: Added checkbox to bypass news comparison during runs
  - Use case: When you want fresh baseline without comparing to old data
  - Location: Run page, appears before "Confirm Run" button
  - Behavior: When checked, skips `compare_news` agent (no deduplication/update detection)
  - All collected news treated as new items
  - Useful after clearing historical news or starting fresh

- **Improved Reset Button**: Enhanced "Clear Historical News" button with better labeling
  - New tooltip: "Clear all historical news from the baseline (last 7 days). Use before 'Skip comparison' to start completely fresh."
  - Clarifies relationship between Clear and Skip Comparison
  - Helps users understand the two-step reset workflow

### Security
- **Credentials Migration**: Removed all credentials from database storage
  - Verified no `credentials` table exists in SQLite database
  - All credentials now loaded exclusively from environment variables
  - Updated `.env` file with correct Gmail App Password
  - Tested email sending - working correctly
  - Updated SPEC.md with security note about environment-only credentials

### UI Improvements
- Better tooltips and help text for run controls
- Clearer separation between manual and scheduled run behaviors
- Improved user feedback for destructive operations

### Testing
- All bug fixes tested and verified working
- Email credentials tested with successful send
- Skip comparison tested with SA/HCM profile

## v2.7 — 2026-03-19
### Changed
- **Migrated from OpenAI to SAP AI Core** for all AI operations
  - Replaced personal OpenAI API key with SAP internal AI Core credentials
  - All agents now use SAP AI Core client with OAuth2 authentication
  - Uses gpt-4o model for chat completions (deployment: `d1555c6d43e6f446`)
  - Uses text-embedding-ada-002 for embeddings (deployment: `d987a899a829c105`)
  - Credentials stored securely in environment variables only

### Added
- New `agents/sap_ai_client.py` module providing OpenAI-compatible interface
- Automatic OAuth2 token management with caching and refresh
- Test scripts for SAP AI Core connection validation

### Security
- Removed hardcoded credential files
- All credentials now loaded from environment variables
- Updated BTP deployment guide with new environment variables

### Environment Variables (New)
- `LEGAL_EAGLE_SAP_AICORE_BASE_URL`
- `LEGAL_EAGLE_SAP_AICORE_AUTH_URL`
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_ID`
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET`
- `LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID`
- `LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID`

## v2.6 — 2026-03-10
### BTP Cloud Foundry Deployment
- **Full BTP Deployment Support**: Complete deployment to SAP BTP Cloud Foundry environment
  - Multi-buildpack configuration: apt-buildpack + python_buildpack
  - Playwright browser automation with Chromium system libraries
  - 1GB memory allocation for browser operations
  - 60-second timeout for slow government websites
  - Complete deployment guide: `BTP_DEPLOYMENT.md`

### Deployment Files Added
- `manifest.yaml` - Cloud Foundry deployment configuration
- `apt.yml` - System package dependencies for Chromium (23 libraries)
- `.profile` - Playwright browser auto-installation script
- `.cfignore` - Files to exclude from CF deployment
- `Procfile` - Gunicorn start command
- `runtime.txt` - Python 3.11 specification
- `requirements.txt` - Root-level Python dependencies

### Technical Improvements
- **Increased Timeout**: Dynamic rendering timeout increased from 20s to 60s
  - Modified: `agents/url_sources_runner.py`
  - Accommodates slow-loading government websites
  - Better success rate for JavaScript-heavy pages

- **System Libraries**: apt-buildpack installs Chromium dependencies
  - Libraries: libnspr4, libnss3, libgbm1, libxshmfence1, and 19 others
  - Prevents "cannot open shared object file" errors
  - Enables Playwright to run in Cloud Foundry environment

- **Auto-Installation**: Playwright browser installed on container startup
  - `.profile` script downloads Chromium (~167MB)
  - Cached in `/home/vcap/app/.cache/ms-playwright/`
  - No manual installation required

### Known Issue
- **Network Connectivity**: Some government websites unreachable from BTP network
  - Affected: Saudi government sites (e.g., `uqn.gov.sa`)
  - Working: RSS feeds, Twitter API, most other websites
  - Root cause: Cloud provider IP ranges may be blocked by government infrastructure
  - Workaround: Use hybrid architecture (BTP for RSS/Twitter, local for blocked sites)

### How to Deploy to BTP
1. Ensure BTP subaccount has Cloud Foundry enabled
2. Login: `cf login`
3. Deploy: `cf push`
4. Configure environment variables via `cf set-env`
5. Access Admin UI at your BTP route

### Testing
- Successfully deployed to BTP Cloud Foundry EU21 (Netherlands)
- Playwright browser operational with all dependencies
- RSS and Twitter sources working from BTP
- Dynamic rendering functional (except blocked government sites)

## v2.5.2 — 2026-02-25
### Bug Fix
- **Translation Variable Collision**: Fixed critical bug in `translate_grouped_summary()` function
  - Issue: Variable `translated_summary` was reused for two purposes (list and string)
  - Error: `'str' object has no attribute 'append'` when translating summaries
  - Fix: Renamed string variable to `translated_summary_text` to avoid collision
  - Impact: Translation now works correctly for all language pairs (TR→EN, AR→EN, ES→EN, etc.)

## v2.5 — 2026-02-23
### Turkey Official Gazette Support
- **Resmi Gazete Integration**: Added support for Turkey's Official Gazette as a URL source
  - Automatic detection when `resmigazete.gov.tr` is configured
  - Date-based gazette navigation (Last 7 days, Last 30 days)
  - Extracts gazette item titles with links to official documents
  - Works with TR/HCM glossary for relevance filtering
  - No PDF parsing required - user clicks links to read full documents

### How It Works
1. Configure URL source: `https://www.resmigazete.gov.tr/`
2. Set Date Scope: "Last 7 days" or "Last 30 days"
3. Add Turkish HCM glossary keywords (optional)
4. Run profile - receives daily digest with gazette items matching keywords
5. Click item links to view full legal documents on official site

### New Components
- `agents/resmi_gazete_scraper.py` - Specialized Resmi Gazete scraper module
  - `generate_date_urls()` - Generates daily gazette URLs from start date
  - `extract_gazette_items()` - Extracts titles and links from listing pages
  - `scrape_resmi_gazete()` - Main entry point with date range support
  - Automatically filters out navigation elements (PDF Görüntüle, Sonraki Sayı, etc.)

### Integration
- `agents/url_sources_runner.py` - Auto-detects Resmi Gazete URLs
  - When `resmigazete.gov.tr` detected, uses specialized scraper
  - Passes `start_date` (if configured) and `days_count` from `date_scope`
  - Falls back to today if no start_date provided
  - Bypasses generic static/dynamic crawlers

### Testing
- Test script: `scripts/test_resmi_gazete_august.py`
- Successfully tested with August 2024 dates (01.08.2024 - 03.08.2024)
- Verified extraction of 52 real gazette items across 3 days

### Technical Design
- Similar to GOSI scraper pattern: extract titles + links only
- No PDF parsing (reduces complexity, faster processing)
- Date-forward iteration (start_date → start_date + N days)
- Same-origin link filtering with detail pattern support
- Deduplicated by title to avoid navigation element duplicates

## v2.4 — 2026-02-19
### Translation & Language Features
- **Per-Receiver Translation Language**: Each email receiver can specify their preferred language
  - New `translation_lang` column in `email_receivers` table (default: 'en')
  - Admin UI displays language dropdown per receiver
  - Email sender groups receivers by language and caches translations
  - Supported languages: English, Arabic, Spanish, French, German, Chinese, Japanese, Korean, Portuguese, Russian, Turkish, Hindi, Italian, Dutch, Polish

- **Profile Analysis Language Editing**: Profile's default language now editable in Admin UI
  - New "🌍 Profile Language" section at top of configuration page
  - Dropdown with all supported languages
  - Language used by AI to read and analyze news sources
  - Separate from receiver translation languages

- **Email Subject Enhancement**: Subject line now includes profile identifier
  - Format: `🦅 Legal Eagle Daily Digest — SA/HCM — 2026-02-19`
  - Helps LPMs managing multiple countries distinguish emails

- **Translation Caching**: Email sender optimizes OpenAI API usage
  - Groups receivers by translation language
  - Translates once per language group
  - Caches translations to avoid redundant API calls
  - Significant cost savings for multiple receivers

### New Components
- `LANGUAGE_NAMES` constant in `config_loader.py` (15 languages)
- `load_email_receivers_with_lang()` in `config_loader.py`
- `upsert_email_receiver_with_lang()` in `db.py`
- `translate_grouped_summary()` in `email_sender.py`
- Route: `/admin/profiles/<id>/language/update` (update profile language)
- Route: `/admin/profiles/<id>/emails/update_language` (update receiver language)

### Admin UI Changes
- New "Profile Language" section shows current language with save button
- Email Receivers table now has "Translation Language" column with dropdown
- Both sections use same 15 language options
- Save buttons per row for immediate feedback

### Database Changes
- Migration script: `scripts/migrate_add_translation_lang.py`
- Sets default 'en' for all existing receivers

### Documentation Updates
- Updated SPEC.md to v2.4 with translation features
- Added Memory Bank Protocol to `.clinerules/rules.md`
- Updated all memory-bank files with v2.4.0 changes

## v2.3 — 2026-02-13
### Documentation
- Simplified versioning format from X.Y.Z to X.Y
- Updated all version references for consistency
- Consolidated documentation structure

## v2.2 — 2026-02-13
### Major Features
- **Monitor Updates Integration**: Law-to-Specification email monitoring
  - New agent: `agents/email_inbox_parser.py` 
  - Fetches "Monitor updates" emails from Gmail IMAP
  - Parses Law-to-Spec email format (report date, URL, changes)
  - Prevents duplicate processing via database tracking
  - Aggregates multiple emails into single report
  - Appears in daily digest as separate "Website Change Alerts" section

### New Features
- **Admin UI Toggle**: Profile-level enable/disable for monitor notifications
  - New setting: `monitor_updates_enabled` (per profile)
  - Toggle in profile configuration page
  - Help text explaining workflow
- **Email Section**: New "🔍 Website Change Alerts (Law-to-Spec)" in digest
  - Shows report date and monitored URL
  - Lists detected changes
  - Bilingual support (Arabic/English with RTL)
  - Empty state message when no changes detected

### Database Changes
- **New Table**: `monitor_updates_processed`
  - Tracks processed emails by Message-ID
  - Prevents re-processing on subsequent runs
  - Stores report date, URL, and changes JSON
  - Indexed by (profile_id, email_message_id)

### Technical Improvements
- Email matching: Handles "FW:" prefix in subject line
- Receiver matching: Checks ALL configured receivers (not just first)
- Email sender: Removed early return bug (monitor section always appears)
- Migration script: `scripts/migrate_add_monitor_updates.py`

### Workflow
1. LPM enables monitor notifications in profile configuration
2. Law-to-Spec sends "Monitor updates" email to LPM's inbox
3. LPM forwards email to Legal Eagle's Gmail
4. Legal Eagle processes email during next scheduled run
5. Email digest includes integrated "Website Change Alerts" section

### Testing
- Test script: `scripts/test_monitor_updates_fixed.py`
- Verified: Email parsing, database tracking, digest integration
- Confirmed: Works with empty grouped_summary (no news items)

## v2.1 — 2026-02-10
### Major Features
- **Twitter Search API Integration**: Replaced per-account timeline fetching with multi-account Search API
  - Fetches tweets from ALL accounts in a single API call (more efficient)
  - Removed round-robin account selection (no longer needed)
  - Deprecated `twitter_last_account_index` setting
  - Maintains 15-minute rate limit enforcement

### New Features
- **Profile-level Lookback Window**: Configurable news lookback period (default: 7 days)
  - Setting: `news_lookback_days` stored per profile
  - Applied to all sources: Twitter, RSS, URL crawls
  - Twitter Search API limited to max 7 days on free tier
- **Date Filtering Utility**: New `agents/date_filter.py` module
  - Filters RSS and URL source items by publication date
  - Fail-safe: keeps items without parseable dates
  - Supports multiple date formats (ISO 8601, simple YYYY-MM-DD)

### Improvements
- Unified date filtering across all news sources
- Better logging for Twitter API calls (shows all accounts being fetched)
- Enhanced Twitter status reporting in admin UI

### Technical Changes
- New function: `search_tweets_multi_account()` in `agents/tweet_feed.py`
- New module: `agents/date_filter.py` with `filter_items_by_date()`
- Updated `agents/agents_controller.py` to use Search API
- Legacy timeline functions marked as deprecated but kept for compatibility

### Testing
- Created `scripts/test_twitter_search.py` for testing multi-account Search API
- Verified: 14 tweets from 2 accounts in single API call
- Confirmed: Free tier rate limit is 1 request per 15 minutes for Search API

## v2.0 — 2026-01-27
### Documentation Refactor & Baseline
- Consolidated all technical documentation into SPEC.md
- Established baseline for future changelog entries
- Previous development history available in git commits
