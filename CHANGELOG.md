# CHANGELOG

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
