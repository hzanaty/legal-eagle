## Governance v1.0 adoption (2026-10-26) — Cline setup only

- Product Manager authorized the previously discussed Cline persistent-instruction setup; no implementation plan or product release is approved by this entry.
- Added `.clinerules/ai-governance.md` referencing `docs/AI_GOVERNANCE.md`, with role boundaries, human approval requirements, and conflict escalation.
- Preserved `.clinerules/rules.md` and the constitution; Claude's own instruction setup remains outside this task.
- Installed Cline 4.1.23 source supports Markdown discovery in `.clinerules/` and inclusion of enabled rules. A fresh-session prompt has not been observed.
- Added setup references to active context and specification, and an unreleased changelog entry as required by existing repository instructions. No production, schema, API, roadmap, or product-version changes; no application tests needed or run.
- Pending Product Decision: reconcile legacy implementation/documentation-write duties with governance ownership. No legacy rules were silently rewritten. Strategy catch-up is deferred.

## v3.34 (2026-09-17) — BTP Data Persistence: Backup/Restore System

**Problem Addressed:**
- BTP Cloud Foundry containers are ephemeral — SQLite database lost on every `cf push`, `cf restart`, or `cf restage`
- Users had to reconfigure everything after each deployment

**Solution:**
- New API endpoints for data export/import:
  - `GET /api/export-all?secret=<admin_secret>` — exports all tables (config + production) as JSON
  - `POST /api/import-all` — imports all tables from JSON, clears existing data first
  - Both protected by admin secret (query param or Bearer token)
- New CLI scripts (local):
  - `scripts/btp_backup.py` — exports BTP database to timestamped JSON file
  - `scripts/btp_restore.py` — imports JSON backup to BTP (requires confirmation)
  - Both read admin secret from env var or command-line arg

**Workflow:**
```bash
# Before any deployment operation
python scripts/btp_backup.py --secret prod-secure-secret-2026

# Do your deployment
cf push

# After deployment completes
python scripts/btp_restore.py --file btp_backup_20260917_221500.json --secret prod-secure-secret-2026
```

**Files Changed:**
- `admin/app.py` — `api_export_all()` + `api_import_all()` (143 lines)
- `scripts/btp_backup.py` — NEW (163 lines)
- `scripts/btp_restore.py` — NEW (160 lines)
- `BTP_DEPLOYMENT_DIFFERENCES.md` — Section 14: Backup/Restore workflow
- `CHANGELOG.md` — v3.34 entry
- `memory-bank/activeContext.md` — version bumped

---

## v3.0–v3.5 (2026-09-04 → 2026-09-05) — Pipeline Redesign (consolidated catch-up)

> **Consolidated entry.** The memory-bank drifted after v2.32 — v3.0–v3.5 were never recorded here while they shipped (tracked instead in `CHANGELOG.md`, `Roadmap/v3-pipeline-redesign.md`, `docs/lifecycle.html`, and auto-memory). This single entry brings `progress.md` current; per-version bullet detail + file lists live in `CHANGELOG.md`.

**v3.0 (2026-09-04) — Admin UI Overhaul + Source Attribution Config + Test Harness Foundation:**
- FCL 3-state Admin UI (Configure / Run / Review tabs); Run All Active UI button + per-profile pills; `authorities` table + Authorities CRUD; "Channel" rename in Review.
- Test Harness foundation (`tests/run_harness.py`, `reset_and_seed.py`, `assertions.py`) — v3.0 verifies schema only against the XN/HCM "Xanadu" imaginary profile. `docs/lifecycle.html` + `Roadmap/` added.

**v3.1 (2026-09-05) — First Pipeline-Touching Release (harness-first):**
- Structural fixes B1–B8 (age anchor, baseline anchor, category/OTHER, publish date, binary filter removed, hash dedup, translation decoupled); F1–F5 (per-source `last_successful_fetch`, health check, `runs.error_step`/`error_message`, immediate stop, force-fetch bounded by `date_scope`).
- Fixture server (`tests/server.py`, localhost:9999); Run All Active backend (SSE); ATTRIBUTE stage (`authority_attributor.py`, configured path). Harness 23/23.

**v3.2 (2026-09-05) — Ranking Engine + Attribution AI:**
- Three-tier ranker (`agents/news_ranker.py`): Tier 0 DUPLICATE passthrough (rank 0), Tier 1 deterministic `ranking_signals`, Tier 2 GPT-4o grounded by `ranking_grounding` (all AI via `ai_cache.py`). REPEATED tag + auto-elevation. AI authority inference (`authority_status='inferred'`).
- New columns: `significance_rank`, `rank_tier`, `rank_reasoning`, `repetition_tag`, `repetition_count`. New tables: `ranking_signals`, `ranking_grounding`. Review rank badges + ✦ inferred icon + override. Harness 19/19 (3 skipped — AI).

**v3.3 (2026-09-05) — Tagging + Email V2 digest:**
- `agents/news_tagger.py` deterministic glossary keyword tagging assigns `topic_label`, replacing AI grouping. Email gated on rank ≥ 3 (`email_eligible`). Email V2 digest (`agents/email_composer.py`) grouped by Authority → Topic; decoupled from run (`runs.email_status`). Review email filter + Sent/Unsent pills + manual send; run-status email bar + Resend.
- New: `glossary_terms` table; `topic_label`/`email_eligible`/`email_sent` columns; `news_aspects` table. Harness 24/24 (26/26 post-ship).

**v3.4 (2026-09-05) — Challenge + Grounding loop:**
- Inline Challenge (GPT-4o counter-argument) + confirm → writes `ranking_grounding` + `ranking_signals`; Re-rank action (F6). Review restructured into **Topic → Announcement → Sources** hierarchy; `news_aspects` renamed to `news_announcements`; announcement markdown rendered inline. V2 digest wired into pipeline. Xanadu demo profile added to `config.db` + `scripts/refresh_xanadu_demo.py`.
- New columns: `human_rank_override`, `human_override_reason`. Harness 32/32 (4 skipped — AI).

**v3.5 (2026-09-05) — Glossary Gap Alert:**
- `news_items.glossary_gap` column; `flag_glossary_gaps()` (`agents/news_tagger.py`) called after TAG stage — set when `rank ≥ 3` AND `topic_label = ["General"]`. Review `⚠ N glossary gaps` strip + gap badge + inline **+ Add to Glossary** panel (AI suggest → confirm → re-tag → clear). Routes `/glossary/suggest`, `/add-to-glossary`.
- Harness: A5 `workplace safety` (Tier-1 `min_rank=4`, deterministic) → `glossary_gap=1`; maternity leave → `glossary_gap=0`. **34/34** (4 skipped — AI). Lifecycle card corrected: RCM Publish → v3.6, Glossary Gap = v3.5.
- **Deferred v3.6:** Impact Analysis agent + RCM-branded publish/JIRA — open governance decision (no sanctioned L2S/RCM integration; direct JIRA-via-REST unsanctioned). Needs dedicated brainstorm.

---

## v2.32 (2026-06-28) — ANS Disabled + ANS OAuth Fix + Documentation Sync

**ANS Disabled** (BTP environment torn down):
- `agents/ans_sender.py` — full implementation commented out; stub always returns `None`/`False`
- `agents/email_sender.py` — ANS-first block commented out; Gmail SMTP is sole send path
- `admin/app.py` — ANS provisioning calls commented out; `ans_available` hardcoded `False`
- `admin/templates/profile.html` — Re-provision button visible but dimmed/disabled with tooltip

**ANS OAuth Fix** (`agents/ans_sender.py`):
- Token request changed to use HTTP Basic auth: `auth=(client_id, client_secret)` + `data={"grant_type": "client_credentials"}`
- Fixes 404 errors when provisioning ANS Actions via "Re-provision all" button
- SAP XSUAA requires credentials in Authorization header, not request body

**Gitignore Cleanup** (`.gitignore`):
- Added `.playwright-mcp/`, `.superpowers/`, `docs/superpowers/`, `server.pid`, `outputs/GR_HCM/`

**Documentation Sync**:
- `SPEC.md` updated from v2.26 to v2.32 — adds repo_nodes/repo_assets tables, Legal Repo routes, v2.31 enhancements, Greece profile section, Section 13
- `README.md` updated — Greece added to deployments, Legal Repository feature, v2.32 spec link
- `CHANGELOG.md` — v2.32 entry added
- All memory-bank files synced to v2.32

**Files Changed**:
- `agents/ans_sender.py` — ANS disabled (stub) + OAuth fix preserved in comments
- `agents/email_sender.py` — ANS-first block commented out
- `admin/app.py` — ANS provisioning commented out; `ans_available=False`
- `admin/templates/profile.html` — Re-provision button dimmed/disabled
- `.gitignore`
- `SPEC.md`, `README.md`, `CHANGELOG.md`, `BTP_DEPLOYMENT.md`
- `memory-bank/activeContext.md`, `memory-bank/progress.md`, `memory-bank/techContext.md`

---

## v2.31 (2026-06-01) — UI Fixes & Enhancements

**URL Source Editing Enhancement**:
- Edit form exposes all fields including URL rename (new_url field)
- If new_url differs, old row deleted and new row inserted preserving all config

**Auto-translate in Review** (`admin/templates/review_news.html`):
- Non-English profiles auto-translate visible items to English on page load
- SAP AI Core call via `POST /admin/profiles/<id>/review/translate`

**Pre-run Preflight Checklist** (`admin/templates/run_status.html`):
- `GET /admin/preflight` returns JSON checks + ready flag
- Start Run button disabled until all checks pass

**Legal Repo lifecycle bar colors** (`admin/templates/legal_repo.html`):
- completed=green, current=blue, future=dark grey

**Resources/ Flask Route** (`admin/app.py`):
- `GET /Resources/<path>` serves files from project Resources/ directory

**BTP Config Sync** (`admin/app.py`, `scripts/export_config.py`, `scripts/import_config.py`):
- Export/import DB config for BTP seeding via `/admin/export-config` and `/admin/import-config`

**Files Changed**:
- `admin/app.py`
- `admin/templates/profile.html`, `run_status.html`, `review_news.html`, `legal_repo.html`
- `scripts/export_config.py` (new), `scripts/import_config.py` (new)

---

## v2.30 (2026-06-01) — Legal Repository + Greece Profile

**Legal Repository** (new feature):
- New DB tables: `repo_nodes` + `repo_assets`
- Global `/admin/legal-repo` three-column page (countries / topic tree / node detail)
- Node lifecycle: NEW → SCOPING → ANALYZED → COMPLETE
- Asset types: jira_epic, jira_req, sap_note, prd, kba, mindmap, xml_schema, analysis, other
- L2S Prompt: create repo node from news item (`source_news_id` traceability)
- `📋 In Legal Repo` badge + `+ L2S Prompt` button on Review page
- `📚 Legal Repo` navbar link

**Greece Profile (GR/HCM)**:
- Language: el, 8 URL sources (ERGANI, Ministry of Labour, EFKA, TEKA×2, AADE, FEK, Gov.gr)
- 87 glossary terms (7 categories)
- 8 seed repo nodes: ERGANI II parent (ANALYZED) + 4 children + EFKA + TEKA + AADE
- ERGANI II MindMap v2 linked as mindmap asset

**Files Changed/Added**:
- `configurations/db.py` — repo_nodes + repo_assets schema + CRUD
- `admin/app.py` — Legal Repo routes + L2S Prompt
- `admin/templates/base.html` — Legal Repo navbar link
- `admin/templates/legal_repo.html` (new)
- `admin/templates/review_news.html` — L2S Prompt + badge
- `scripts/seed_greece_profile.py` (new)
- `scripts/seed_greece_repo.py` (new)
- `Resources/ERGANI_II_MindMap_v2.html`, `Greece_Glossary.md`, `Greece_URL_Resources`, `Legal_Repository_Strategy.md`

---

## v2.29 (2026-05-xx) — ANS Email Routing (merged into v2.26 documentation)

---

## v2.26 (2026-05-13) — Run Log Visualization + ANS Email + Per-Feed RSS Tracking

**Run Log Visualization** (`admin/templates/run_status.html` — major redesign):
- Two-panel layout: vertical 7-stage checklist (left) + per-stage log (right)
- Live state icons per stage + status summary (e.g. "55 collected", "4 relevant")
- Collecting stage breaks down into individual sub-items: RSS feed URLs, Twitter @handles, URL sources
- Clicking sub-items or stages filters the log panel to that source's lines
- All driven by SSE stream; no server changes required beyond per-feed RSS prints

**ANS Email** (`agents/ans_sender.py` — new):
- SAP BTP Alert Notification Service sender; Gmail SMTP fallback for local dev
- Auto-provisions ANS Action + Condition + Subscription per recipient (idempotent)
- `email_sender.py` updated: try ANS → fall back to Gmail SMTP on failure

**Per-Feed RSS Tracking** (`agents/agents_controller.py`):
- `↳ RSS: {url}: fetching...` / `↳ RSS: {url}: N items` prints in `run_single_profile()` RSS loop

**Files Changed**:
- `admin/templates/run_status.html`
- `agents/ans_sender.py` (new)
- `agents/email_sender.py`
- `agents/agents_controller.py`
- `BTP_DEPLOYMENT.md`

---

## v2.25 (2026-05-12) — BTP Stability + macOS Launcher

---

## v2.24 (2026-05-08) — Skip Grouping Run Option

**New Feature**: Skip grouping checkbox added to Run Options
- "Skip grouping (one item per email entry)" checkbox between Skip filtering and Test mode
- `skip_grouping: bool = False` param on `run_profile_once()`
- When checked: each item wrapped as single-item group dict (title, summary=content, category, links, etc.)
- Compatible with email_sender — no changes to downstream code needed
- State persisted in localStorage alongside other run options

**Files Changed**:
- `agents/agents_controller.py` — `skip_grouping` param + bypass/wrap logic
- `admin/app.py` — reads form field, passes through `_worker` and into `run_profile_once()`
- `admin/templates/run_status.html` — checkbox + localStorage save/restore

---

## v2.23 (2026-05-08) — Run-Level Lookback Override

**New Feature**: Per-run lookback override replacing force_run checkbox
- "Lookback" dropdown in Run modal (replaces "Force full fetch" checkbox)
- Options: Use profile default / Force full (re-fetch all) / Delta / Today / Last 7 / Last 30 days
- `lookback_override: Optional[str]` param on `run_profile_once()`; injects over `PROFILE_DATE_SCOPE`
- `force_full` removed from profile Default Lookback Window (available only as per-run override)
- Backward compat: DB profiles with `force_full` or `all` in date_scope show as Delta in UI

**Files Changed**:
- `agents/agents_controller.py` — `lookback_override` param
- `admin/app.py` — replaced `force_run` form read with `lookback_override`; allowed set updated
- `admin/templates/run_status.html` — select dropdown replacing checkbox
- `admin/templates/profile.html` — `force_full` option removed from dropdown

---

## v2.22 (2026-05-08) — Profile-Level Lookback Window

**New Feature**: Unified lookback control at profile level
- `profiles.date_scope` column: `delta`, `today`, `last_7_days`, `last_30_days`
- Both `run_controller()` and `run_profile_once()` load `PROFILE_DATE_SCOPE` and apply to all sources
- New "🗓 Default Lookback Window" card on profile config page
- Per-source Lookback Days removed from RSS/Twitter/URL tables and forms (UI cleanup)

**Bug Fixes**:
- `PROFILE_DATE_SCOPE` NameError in `run_profile_once()`: was never defined → caused silent crash on all manual runs
- `days=0` bug: `filter_items_by_date(days=0)` silently defaulted to 7 days; fixed by injecting `since_date=start_of_UTC_midnight`

**Files Changed**:
- `configurations/db.py` — `ALTER TABLE profiles ADD COLUMN date_scope`
- `configurations/config_loader.py` — `parse_date_scope()` updated; `load_profile_date_scope()`, `save_profile_date_scope()` added
- `agents/agents_controller.py` — both run functions use `PROFILE_DATE_SCOPE`; RSS + Twitter + URL sources all driven by it
- `admin/app.py` — new `POST /admin/profiles/<id>/date-scope/update` route; `date_scope` removed from URL source add/update
- `admin/templates/profile.html` — new Default Lookback Window card; per-source lookback columns/fields removed

---

## v2.21 (2026-05-08) — URL Date Control (Mechanism A + Delta)

**New Feature**: Post-scrape date filter for URL sources
- Controller injects `since_date` (delta/today) or `days` (fixed window) per URL source
- DELTA mode: fetch since `last_successful_fetch`; FULL mode: fetch full lookback window
- Mode printed in logs: `DELTA mode: since 2026-05-07T09:30:00 (max lookback: 7 days)`
- `force_full` override triggers FULL mode unconditionally

**Files Changed**:
- `agents/url_sources_runner.py` — Mechanism A post-scrape filter using injected params
- `agents/agents_controller.py` — per-source delta/full mode calculation

---

## v2.20 (2026-04-28) — Skip Filtering + Run Options Persistence

**New Features**:
1. **Skip Filtering Checkbox**: Added option to bypass LLM relevance check for testing purposes
2. **Run Options Persistence**: All 4 run option checkboxes now persist across sessions using localStorage

**Problem Solved**:
- Users had to re-select run options (force fetch, skip comparison, test mode) every time
- No way to bypass filtering for testing/debugging collected items

**Solution**:
1. **Skip Filtering Feature**:
   - Added new checkbox: "Skip filtering (accept all as relevant)"
   - When enabled, bypasses `news_filter.py` LLM relevance check
   - All collected items treated as relevant (useful for testing data collection)
   - Shows warning in logs: "⚠️ Skip filtering enabled: treating all items as relevant"

2. **localStorage Persistence**:
   - All 4 run options automatically saved to browser localStorage on change
   - Restored on page load (per profile ID)
   - Key format: `legal_eagle_run_options_profile_{id}`
   - Persisted options:
     - Force full fetch
     - Skip comparison (treat all as new)
     - Skip filtering (accept all as relevant) ← NEW
     - Test mode (skip emails)

**Files Changed**:
- `admin/templates/run_status.html`:
  - Added skip filtering checkbox in Run Options section
  - Added localStorage persistence JavaScript for all 4 checkboxes
  - Auto-saves on checkbox change, auto-restores on page load
- `admin/app.py`:
  - Captures `skip_filtering` form parameter (line 436)
  - Passes to worker thread as `skip_filt` (line 489)
  - Logs in audit trail (line 475)
- `agents/agents_controller.py`:
  - Added `skip_filter` parameter to `run_profile_once()` (line 264)
  - Added to mode indicators display (line 308)
  - Conditionally bypasses filtering when `skip_filter=True` (lines 482-502)
  - Shows warning log when filtering is skipped

**User Experience**:
- **Before**: Had to re-check "Test mode" every single run
- **After**: Checkbox states remembered automatically ✅
- **Before**: No way to see all collected items without filtering
- **After**: Can toggle "Skip filtering" for testing ✅

**Technical Implementation**:
```javascript
// localStorage persistence (per profile)
const optionsKey = 'legal_eagle_run_options_profile_' + PROFILE_ID;
localStorage.setItem(optionsKey, JSON.stringify({
  force_run: true/false,
  skip_comparison: true/false,
  skip_filtering: true/false,  // NEW
  skip_email: true/false
}));
```

```python
# Backend skip filtering logic
if skip_filter:
    print(f"\n⚠️ Skip filtering enabled: treating all items as relevant")
    filtered_items = all_news_items
    filtered_count = 0
else:
    # Normal filtering with LLM
    filter_result = get_relevant_news(...)
    filtered_items = filter_result.get("items", [])
```

---

## v2.19 (2026-04-28) — Source Selection Fix (Empty Selection = Run None)

**Problem**:
- When user unchecked all URL sources in Run page, the system ran ALL 4 URL sources instead of none
- Root cause: Empty checkbox list `[]` was converted to `None`, which meant "run all sources"
- This violated user intent: unchecked boxes should mean "run none", not "run all"

**Solution** (Option 1: Smart Detection):
- Added hidden flags to indicate UI sections exist (`has_rss_sources`, `has_twitter_sources`, `has_url_sources`)
- Backend logic now distinguishes between:
  - **Empty list `[]`**: User explicitly unchecked all → Run **none** (respects user choice)
  - **None**: No UI shown (API call) → Run **all** (backward compatibility)
- Maintains backward compatibility for scripts that call the API without form data

**How It Works**:
1. **When you use UI and uncheck all sources**:
   - Form sends: `selected_urls = []`, `has_url_sources = '1'`
   - Backend sees: "UI was shown, user wants none"
   - Result: 0 URL sources run ✅

2. **When a script calls API without UI**:
   - Form sends: no form data at all
   - Backend sees: "No UI, use default behavior"
   - Result: All URL sources run ✅ (backward compatible)

**Files Changed**:
- `admin/app.py` (lines 443-477) — Added smart detection logic with hidden flags
- `admin/templates/run_status.html` (lines 206, 222, 238) — Added hidden input flags
- `agents/agents_controller.py` — Verified: already handles empty lists correctly
- `CHANGELOG.md` — Added v2.19 entry
- `memory-bank/activeContext.md` — Updated to v2.19
- `memory-bank/progress.md` — This entry

**Technical Details**:
```python
# Before (broken):
selected_urls = request.form.getlist('selected_urls')  # [] if nothing checked
selected_urls = selected_urls if selected_urls else None  # [] becomes None
# None means "run all" → wrong!

# After (fixed):
selected_urls = request.form.getlist('selected_urls')
has_urls_ui = request.form.get('has_url_sources') == '1'

if has_urls_ui and not selected_urls:
    selected_urls = []  # Explicit empty = run none
elif not has_urls_ui:
    selected_urls = None  # No UI = run all (backward compatible)
```

**Testing**:
- Unchecking all URL sources now correctly runs 0 URL sources
- Checking some sources runs only those sources
- API calls without form data still run all sources (backward compatible)

---

## v2.18 (2026-04-28) — Twitter Status Compact Design

**Changes**:
- **Error-Only Display**: Twitter status card now only appears when there's an error
  - Removed large Twitter status card from Run page (saves ~100px vertical space)
  - Red error banner appears only when Twitter API has issues
  - Shows error message with "Clear Error & Retry" button
  - Consistent with profile page error flag system
  
**Rationale**:
- Reduces visual clutter on Run page
- "Show errors, hide success" design pattern
- Users only see Twitter status when action is needed
- Saves significant vertical space per profile

**Files Changed**:
- `admin/templates/run_status.html` — Replaced large card with compact error-only banner
- `admin/app.py` — Added twitter_error_flag to run_status template context
- `CHANGELOG.md` — Added v2.18 entry
- `memory-bank/activeContext.md` — Updated to v2.18
- `memory-bank/progress.md` — This entry

---

## v2.17 (2026-04-28) — Review UI Simplification & Cleanup

**Changes**:
- **Review Page UI Improvements**:
  - Removed redundant tab buttons (Accepted/Filtered/Reviewed tabs below stat cards)
  - Made stat cards clickable for direct navigation
  - Added hover effects (card lifts up with shadow)
  - Added active state styling (blue border + shadow glow on selected card)
  - Cleaner, more intuitive interface following card-based UI patterns
  
- **Run Page Cleanup**:
  - Removed "Clear Historical News (71)" button from Run Workflow page
  - Removed associated confirmation dialog modal
  - Removed JavaScript functions: `showClearDialog()`, `hideClearDialog()`, `handleClearSubmit()`
  - Users now manage history exclusively from Review page with granular controls:
    - "Clear All" button (clears everything)
    - "Clear Reviewed" button (clears only scored items)
  
- **Scoring Integration Documentation**:
  - Confirmed scoring is already integrated into `news_filter.py`
  - High-score rescue mechanism: items with `relevance_score >= 4` are used as baseline
  - Filtering pipeline priority documented:
    1. **Age Gate** (hard block, no rescue)
    2. **LLM Semantic Check** (uses glossary terms as context)
    3. **High-Score Rescue** (if LLM filtered out, check similarity to high-scored items)
  - When user scores filtered item 4-5, similar items get rescued in future runs

**Rationale**:
- Single source of truth for history management (Review page)
- Reduces duplicate functionality and UI clutter
- Card-based navigation is more intuitive than tabs
- Better visual hierarchy with hover/active states

**Files Changed**:
- `admin/templates/review_news.html` — Removed tab buttons, made cards clickable, added hover/active styles
- `admin/templates/run_status.html` — Removed clear button and modal
- `CHANGELOG.md` — Added v2.17 entry
- `memory-bank/activeContext.md` — Updated to v2.17
- `memory-bank/progress.md` — This entry

---

## v2.16 (2026-04-27) — Admin UI Fixes & Enhancements

**Changes**:
- **URL Source Last Fetch Display**: Added formatted timestamps to URL sources table
  - Relative time (e.g., "2h ago", "3d ago") for quick scanning
  - Absolute time (e.g., "Jan 5, 10:30 AM") on hover for precision
  - Shows "Never" for sources that haven't been fetched yet
  
- **Source Selection Persistence**: Run page now remembers your source selections
  - Selections saved to localStorage per profile
  - Automatically restored when you return to the page
  - Works across browser sessions
  - Separate storage per profile (doesn't mix selections)
  
- **UI Polish**:
  - Fixed checkbox alignment in source selection lists
  - Added collapsible source categories (click arrow to expand/collapse)
  - Improved visual hierarchy with better spacing
  - Added "All" checkbox for each category (select/deselect all at once)

**Files Changed**:
- `admin/app.py` — Added timestamp formatting logic for URL sources
- `admin/templates/run_status.html` — Added localStorage persistence and collapsible categories
- `admin/templates/profile.html` — Updated URL sources table display
- `CHANGELOG.md` — Added v2.16 entry
- `memory-bank/activeContext.md` — Updated to v2.16
- `memory-bank/progress.md` — This entry

---

## v2.15 (2026-04-27) — Source Selection UI

**Changes**:
- Added source selection interface to Run page
- Users can now select which sources to run:
  - RSS feeds (individual feed selection)
  - Twitter accounts (individual account selection)
  - URL sources (individual source selection)
- Backend accepts optional filters: `selected_rss_urls`, `selected_twitter_handles`, `selected_url_sources`
- If no selection provided, runs all sources (backward compatible)

**Implementation**:
- Form checkboxes for each source type
- Backend filters sources before passing to `run_profile_once()`
- Agents controller respects source filters throughout pipeline

**Files Changed**:
- `admin/templates/run_status.html` — Added source selection checkboxes
- `admin/app.py` — Added source filtering logic
- `agents/agents_controller.py` — Added optional source filter parameters
- `CHANGELOG.md` — Added v2.15 entry
- `memory-bank/activeContext.md` — Updated to v2.15
- `memory-bank/progress.md` — This entry

---

## v2.14 (2026-04-27) — Incremental URL Fetching (Delta Mode)

**Changes**:
- **Delta Fetching**: URL sources now fetch only new items since last successful run
  - Tracks `last_successful_fetch` timestamp per URL source
  - DELTA mode: fetches items published since last fetch
  - FULL mode: fetches entire lookback window (first run, force run, or after reset)
  - Safety cap: delta never exceeds `date_scope` max lookback window
  
- **Force Run Option**: New checkbox to override delta and fetch full window
  - Useful for testing, troubleshooting, or catching up after downtime
  - Ignores `last_successful_fetch` timestamps
  - Forces all sources to FULL mode
  
- **Reset Fetch Timestamp**: New button per URL source in profile config
  - Clears `last_successful_fetch` to force next run to FULL mode
  - Useful when source was down or had issues
  - Visible in URL sources table with timestamp display

**Implementation Details**:
- `url_sources` table: added `last_successful_fetch` column (TEXT, ISO timestamp)
- `url_sources_runner.py`: updated to accept `since_date` parameter for delta fetching
- `agents_controller.py`: calculates delta window per source, passes to runner
- Admin UI: added "Force full fetch" checkbox and "Reset Fetch" button

**Migration**:
- Schema auto-update adds `last_successful_fetch` column if missing
- Existing sources start with NULL (first run is FULL mode)

**Files Changed**:
- `configurations/db.py` — Added `last_successful_fetch` column
- `agents/url_sources_runner.py` — Added delta fetching logic
- `agents/agents_controller.py` — Added delta calculation per source
- `admin/app.py` — Added force run option and reset button
- `admin/templates/run_status.html` — Added force run checkbox
- `admin/templates/profile.html` — Added reset button and timestamp display
- `scripts/migrate_add_last_successful_fetch.py` — Migration script
- `CHANGELOG.md` — Added v2.14 entry
- `memory-bank/activeContext.md` — Updated to v2.14
- `memory-bank/progress.md` — This entry

---

## v2.13 (2026-04-27) — Date Scope Configuration

**Changes**:
- **Per-Source Date Scope**: Each URL source can now have its own lookback window
  - Values: `all` (no date filter), `7d`, `14d`, `30d`, `60d`, `90d`, `180d`, `365d`
  - Replaces global `news_lookback_days` setting for URL sources
  - RSS and Twitter still use global `news_lookback_days`
  
- **Smart Defaults**:
  - New sources default to `30d` (30 days lookback)
  - Existing sources migrated to `all` (preserve current behavior)
  
- **UI Updates**:
  - Profile page: dropdown for date scope per URL source
  - Shows current setting in URL sources table
  - Add/Edit forms include date scope selector

**Implementation**:
- `url_sources` table: added `date_scope` column (TEXT, default 'all')
- `config_loader.py`: added `parse_date_scope()` helper (converts "30d" → 30)
- Admin UI: added date scope dropdown to URL source forms

**Migration**:
- Schema auto-update adds `date_scope` column if missing
- Existing sources get `date_scope = 'all'` (preserve current behavior)

**Files Changed**:
- `configurations/db.py` — Added `date_scope` column
- `configurations/config_loader.py` — Added `parse_date_scope()` helper
- `admin/app.py` — Added date scope to add/update routes
- `admin/templates/profile.html` — Added date scope dropdown
- `scripts/migrate_add_date_scope.py` — Migration script
- `CHANGELOG.md` — Added v2.13 entry
- `memory-bank/activeContext.md` — Updated to v2.13
- `memory-bank/progress.md` — This entry

---

## v2.12 (2026-04-26) — Combined News Review (Accepted + Filtered)

**Problem**:
- Review page only showed filtered (rejected) items
- No way to review accepted items that made it into emails
- Users couldn't score items that passed initial filter
- High-score rescue mechanism couldn't learn from accepted items

**Solution**:
- Unified review interface showing both accepted and filtered items
- Three tabs: "Accepted" (passed filter), "Filtered" (rejected), "Reviewed" (scored)
- Same scoring UI for both types (1-5 stars)
- Backend stores scores in respective tables (`news_items.relevance_score` or `filtered_news.relevance_score`)

**Implementation**:
- New DB functions: `list_all_news_for_review()`, `count_all_news_for_review()`, `update_news_item_score()`, `delete_news_item()`
- Review page tabs use `source` parameter: `accepted`, `filtered`, or None (reviewed)
- Item IDs now include source: `"123:accepted"` or `"456:filtered"`
- Scoring/delete operations route to correct table based on source

**Files Changed**:
- `configurations/db.py` — Added combined review functions
- `admin/app.py` — Updated review routes to handle both sources
- `admin/templates/review_news.html` — Added tabs and source handling
- `CHANGELOG.md` — Added v2.12 entry
- `memory-bank/activeContext.md` — Updated to v2.12
- `memory-bank/progress.md` — This entry

---

## v2.11 (2026-04-26) — High-Score Rescue & Filtered News Review

**Changes**:
- **High-Score Rescue Mechanism**:
  - Items with `relevance_score >= 4` become baseline for similarity matching
  - If LLM filters out an item, check similarity to high-scored items
  - If semantic similarity > 0.75, rescue the item (treat as relevant)
  - Helps catch items the LLM incorrectly filtered
  
- **Filtered News Review UI**:
  - New "Review Filtered News" page accessible from profile runs page
  - Shows items that were filtered out (rejected by LLM)
  - Manual scoring: 1 (not relevant) to 5 (highly relevant)
  - Bulk actions: score multiple items at once, bulk delete
  - Clear reviewed items (items with scores)
  - Auto-prune: filtered items older than 30 days are deleted
  
- **Database Changes**:
  - New `filtered_news` table to store rejected items
  - Schema: id, profile_id, title, link, snippet, published_date, source, relevance_score, created_at
  - Indexed on profile_id for fast queries
  
- **Integration**:
  - `news_filter.py` now saves filtered items to database
  - High-score baseline loaded from `news_items` table (scored items)
  - Review page shows counts: total filtered, reviewed, pending review

**Files Changed**:
- `configurations/db.py` — Added filtered_news table and review functions
- `agents/news_filter.py` — Added high-score rescue and filtered news storage
- `admin/app.py` — Added filtered news review routes
- `admin/templates/review_news.html` — New review page
- `admin/templates/run_status.html` — Added review link
- `CHANGELOG.md` — Added v2.11 entry
- `memory-bank/activeContext.md` — Updated to v2.11
- `memory-bank/progress.md` — This entry

---

## v2.10 (2026-04-26) — Relevance Scoring in News Items

**Changes**:
- Added `relevance_score` column to `news_items` table (INTEGER, 1-5 scale, NULL = unscored)
- Enables manual feedback loop for filtering accuracy
- Future: high-scored items (4-5) can be used as positive examples for similarity matching

**Files Changed**:
- `configurations/db.py` — Added relevance_score column
- `scripts/migrate_add_news_items_score.py` — Migration script
- `memory-bank/activeContext.md` — Updated to v2.10
- `memory-bank/progress.md` — This entry

---

## v2.9 (2026-04-25) — Recursive Crawling with Depth Control

**Changes**:
- **Recursive Mode**: New crawling mode that follows links to discover nested content
  - Configurable max depth (default: 2 levels deep)
  - Domain filtering: restrict crawling to specific domains
  - Path filtering: only follow links matching regex pattern
  - Max results cap: stop after N items (default: 20)
  
- **URL Source Modes**: Expanded from 3 to 4 modes:
  1. `auto` — Smart detection (static → dynamic fallback)
  2. `force_static` — Force static scraping only
  3. `force_dynamic` — Force browser rendering only
  4. `recursive` — **NEW**: Recursive crawling with depth control
  
- **Configuration**:
  - `max_depth` (INTEGER, default 2): How many levels deep to crawl
  - `allowed_domains` (TEXT, optional): Comma-separated list of allowed domains
  - `path_filter` (TEXT, optional): Regex pattern for allowed paths
  - `max_results` (INTEGER, default 20): Stop after N items
  
- **Database Schema**:
  - Added 4 new columns to `url_sources` table
  - Migration script handles schema updates

**Use Cases**:
- Government portals with nested announcements (e.g., ministry → department → article)
- News sites with category pages (e.g., legal news section → individual articles)
- Documentation sites with hierarchical structure

**Files Changed**:
- `configurations/db.py` — Added recursive mode columns
- `agents/url_sources_runner.py` — Added recursive crawling logic
- `admin/app.py` — Added recursive mode UI
- `admin/templates/profile.html` — Added recursive mode form
- `scripts/migrate_add_recursive_crawl.py` — Migration script
- `CHANGELOG.md` — Added v2.9 entry
- `memory-bank/activeContext.md` — Updated to v2.9
- `memory-bank/progress.md` — This entry

---

## v2.8 (2026-04-25) — Crawl Version Selection (v1 vs v2)

**Changes**:
- **Dual Crawling Engines**: URL sources can now choose between two crawlers:
  - **v1** (default): Original crawler using BeautifulSoup + requests
  - **v2**: New crawler using Crawl4AI with better JavaScript handling
  
- **Per-Source Configuration**: Each URL source has independent crawl_version setting
  - Dropdown in Add/Edit URL Source forms
  - Defaults to v1 for backward compatibility
  - Can switch between versions without affecting other sources
  
- **Database Schema**:
  - Added `crawl_version` column to `url_sources` table (TEXT, default 'v1')
  - Migration script handles schema updates for existing sources

**Files Changed**:
- `configurations/db.py` — Added crawl_version column
- `agents/url_sources_runner.py` — Added version routing logic
- `admin/app.py` — Added crawl_version to add/update routes
- `admin/templates/profile.html` — Added crawl_version dropdown
- `scripts/migrate_add_crawl_version.py` — Migration script
- `CHANGELOG.md` — Added v2.8 entry
- `memory-bank/activeContext.md` — Updated to v2.8
- `memory-bank/progress.md` — This entry

---

## v2.7 (2026-04-25) — Proxy Support for URL Sources

**Changes**:
- Added proxy configuration support for URL sources (Bright Data integration)
- Environment variables for proxy credentials:
  - `PROXY_HOST`, `PROXY_PORT`, `PROXY_USERNAME`, `PROXY_PASSWORD`
- Proxy enabled when all 4 variables are set
- Used for both static and dynamic scraping modes

**Files Changed**:
- `agents/url_sources_runner.py` — Added proxy support
- `configurations/env_loader.py` — Added proxy env vars
- `scripts/migrate_add_proxy_support.py` — Documentation script
- `CHANGELOG.md` — Added v2.7 entry
- `memory-bank/activeContext.md` — Updated to v2.7
- `memory-bank/progress.md` — This entry

---

## v2.6 (2026-04-25) — Monitor Updates Email Feature

**Changes**:
- Added email monitoring for Law-to-Specification updates (GPM team inbox)
- Fetches monitor emails from configured inbox
- Parses structured update emails (regulation changes, new requirements)
- Appends monitor updates section to daily digest email
- Per-profile toggle: `monitor_updates_enabled` setting (default: false)

**Implementation**:
- New agent: `email_inbox_parser.py` (Gmail API integration)
- Fetches emails with label "Monitor-Updates" from last 7 days
- Parses email body for structured data (regulation, country, status, etc.)
- Formats updates as HTML section in email template
- Admin UI toggle on profile detail page

**Files Changed**:
- `agents/email_inbox_parser.py` — New agent for email monitoring
- `agents/agents_controller.py` — Integrated monitor updates into pipeline
- `agents/email_sender.py` — Added monitor updates section to email template
- `configurations/db.py` — Added monitor_updates_enabled setting
- `admin/app.py` — Added monitor toggle route
- `admin/templates/profile.html` — Added monitor toggle UI
- `scripts/migrate_add_monitor_updates.py` — Migration script
- `CHANGELOG.md` — Added v2.6 entry
- `memory-bank/activeContext.md` — Updated to v2.6
- `memory-bank/progress.md` — This entry

---

## v2.5 (2026-04-24) — Email Translation Support

**Changes**:
- Per-receiver email translation: each receiver can specify their preferred language
- New `email_receivers_with_lang` table stores email + translation_lang pairs
- Email sender now translates content for each receiver individually
- Supported languages: English (default), Spanish, German, Portuguese, Turkish, Arabic
- Admin UI: language dropdown per receiver in profile config

**Implementation**:
- Translation via SAP AI Core (GPT-4o) with specialized prompts
- Preserves HTML formatting, links, and structure
- Falls back to original language if translation fails
- Subject line also translated

**Files Changed**:
- `configurations/db.py` — Added email_receivers_with_lang table
- `agents/email_sender.py` — Added translation logic per receiver
- `admin/app.py` — Added language update route
- `admin/templates/profile.html` — Added language dropdown
- `scripts/migrate_add_translation_lang.py` — Migration script
- `CHANGELOG.md` — Added v2.5 entry
- `memory-bank/activeContext.md` — Updated to v2.5
- `memory-bank/progress.md` — This entry

---

## v2.4 (2026-04-23) — Resend Email from Preview

**Changes**:
- Added "Resend Last Email" button to Run page
- Parses `email_preview.html` file (generated during test runs)
- Extracts grouped news items and sends to all configured receivers
- Supports translation: each receiver gets email in their preferred language
- Useful for sending test emails after reviewing preview

**Implementation**:
- New script: `scripts/resend_email_from_html.py`
- Parses HTML to extract news items (title, link, snippet, source)
- Calls existing `send_email()` function with parsed data
- Button appears on Run page (disabled during active runs)

**Files Changed**:
- `scripts/resend_email_from_html.py` — New resend script
- `admin/app.py` — Added resend route
- `admin/templates/run_status.html` — Added resend button
- `CHANGELOG.md` — Added v2.4 entry
- `memory-bank/activeContext.md` — Updated to v2.4
- `memory-bank/progress.md` — This entry

---

## v2.3 (2026-04-22) — Run Logs with SSE Streaming

**Changes**:
- Real-time log streaming from backend to Admin UI
- Server-Sent Events (SSE) for live log updates
- Split-panel layout: left (controls + history), right (live logs)
- Terminal-style log viewer with auto-scroll
- Status badges update in real-time (Running → Success/Failed)

**Implementation**:
- New `runs` and `run_logs` tables in SQLite
- Background thread captures stdout and writes to DB
- SSE endpoint streams logs with 750ms polling
- JavaScript EventSource client handles streaming
- Logs persist after run completes (7-day retention)

**Files Changed**:
- `configurations/db.py` — Added runs and run_logs tables
- `admin/app.py` — Added SSE streaming endpoint
- `admin/templates/run_status.html` — New split-panel UI
- `CHANGELOG.md` — Added v2.3 entry
- `memory-bank/activeContext.md` — Updated to v2.3
- `memory-bank/progress.md` — This entry

---

## v2.2 (2026-04-21) — Unified URL Sources (Static + Dynamic)

**Changes**:
- Merged `crawl_urls` and `snap_urls` into single `url_sources` table
- Three modes: `auto` (smart detection), `force_static`, `force_dynamic`
- Auto mode tries static first, falls back to dynamic if needed
- Migration script converts existing URLs to unified format

**Implementation**:
- New `url_sources` table with `mode` column
- `url_sources_runner.py` handles all three modes
- Admin UI dropdown for mode selection
- Backward compatible: existing URLs migrated to `mode=auto`

**Files Changed**:
- `configurations/db.py` — Added url_sources table
- `agents/url_sources_runner.py` — New unified runner
- `admin/app.py` — Updated URL management routes
- `admin/templates/profile.html` — Updated URL forms
- `scripts/migrate_urls_to_unified.py` — Migration script
- `CHANGELOG.md` — Added v2.2 entry
- `memory-bank/activeContext.md` — Updated to v2.2
- `memory-bank/progress.md` — This entry

---

## v2.1 (2026-04-20) — Admin UI with Run Management

**Changes**:
- Flask-based Admin UI for profile management
- Manual run trigger with real-time progress
- Profile configuration (RSS, Twitter, Email, Glossary)
- Run history and status tracking
- Test mode (skip emails) for safe testing

**Features**:
- Dashboard: all profiles with last run time
- Profile detail: manage all sources and settings
- Run page: manual trigger + history + logs
- Settings: schedule day, language, Twitter quota reset

**Files Changed**:
- `admin/app.py` — Flask application
- `admin/templates/*.html` — UI templates
- `configurations/db.py` — SQLite schema
- `agents/agents_controller.py` — Added run_profile_once()
- `CHANGELOG.md` — Added v2.1 entry
- `memory-bank/activeContext.md` — Updated to v2.1
- `memory-bank/progress.md` — This entry

---

## v2.0 (2026-04-19) — Multi-Profile Architecture

**Changes**:
- SQLite database for configuration storage
- Support for multiple country/LoB profiles
- Per-profile settings: language, glossary, sources, schedule
- Migration from YAML/JSON config files to database

**Database Schema**:
- `profiles` — Country/LoB combinations
- `rss_feeds` — RSS sources per profile
- `tweet_accounts` — Twitter accounts per profile
- `email_receivers` — Email recipients per profile
- `glossary_terms` — Legal terms per profile
- `settings` — Key-value settings per profile

**Files Changed**:
- `configurations/db.py` — Database schema and helpers
- `configurations/config_loader.py` — Load config from DB
- `agents/agents_controller.py` — Multi-profile support
- `scripts/migrate_config_to_sqlite.py` — Migration script
- `CHANGELOG.md` — Added v2.0 entry
- `memory-bank/activeContext.md` — Updated to v2.0
- `memory-bank/progress.md` — This entry

---

## v1.0 (Initial Release)

**Features**:
- RSS feed monitoring
- Twitter feed monitoring (Search API)
- Static website crawling (BeautifulSoup)
- Dynamic website snapshots (Playwright)
- News filtering (SAP AI Core + GPT-4o)
- Semantic comparison (embeddings + cosine similarity)
- News grouping (clustering)
- Email digest generation (Gmail SMTP)
- YAML-based configuration

**Files**:
- `agents/` — Processing pipeline
- `configurations/` — Config loading
- `outputs/` — Generated files
- `README.md` — Project documentation