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