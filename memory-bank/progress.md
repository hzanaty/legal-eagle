## v2.11 (2026-04-22) — Bilingual Email Body

**Changes**:
- `agents/email_sender.py`: Added `COUNTRY_COLORS` and `LANG_BADGES` dicts with flag-inspired colours per country.
- `agents/email_sender.py`: `build_email_body()` now accepts `english_summary` and `country_code` params.
  - Bilingual mode: renders ONE card per news group with TWO halves (native top + English bottom) separated by thin divider.
  - Top half uses flag-inspired left border + tinted background (green for SA/AE, red for TR/ES, etc.)
  - Bottom half uses gray left border (#9ca3af) + light gray background (#f9fafb)
  - Language badge (e.g. "TR", "EN") at top of each half
  - Source links appear only in English half
  - Monolingual fallback when profile lang = English
- `agents/email_sender.py`: `send_email()` simplified — translates once to English, builds ONE bilingual body, sends to ALL receivers in single SMTP call.
- `agents/agents_controller.py`: Updated both `run_controller()` and `run_profile_once()` to use new simplified `send_email()` call.
- `admin/templates/profile.html`: Removed per-receiver "Translation Language" column and dropdown.
- `CHANGELOG.md`: Added v2.11 entry.

**Result**: Emails are now bilingual by default for non-English profiles. All recipients get the same email with both languages. Per-receiver language preference is no longer needed.

**Files Changed**:
- `agents/email_sender.py`
- `agents/agents_controller.py`
- `admin/templates/profile.html`
- `CHANGELOG.md`
- `memory-bank/progress.md`, `memory-bank/activeContext.md`

---

## Update v2.8 (2026-04-07)

### v2.8 — Bug Fixes, Security, and UX Improvements (2026-04-07)

**Additional Bug Fix** (2026-04-08):
- **Gmail Environment Variable**: Fixed incorrect environment variable name for Gmail sender
  - Changed from `LEGAL_EAGLE_GMAIL_EMAIL_SENDER` to `LEGAL_EAGLE_GMAIL_EMAIL`
  - Updated `configurations/config_loader.py` to read correct variable
  - Updated `.env` file with correct variable name
  - Updated SPEC.md documentation (Section 8.1)
  - Impact: "Resend Last Email" feature now works correctly
  - Simplified credential loading - removed unnecessary fallback logic


**Critical Bug Fixes**:
- **Fixed Clear Historical News**: Resolved issue where clearing news baseline was clearing wrong profile's data
  - Root cause: `profile_id` parameter not passed to `clear_news_baseline()` function
  - Added `profile_id` parameter throughout call chain: route → config_loader → db
  - Impact: Users can now safely clear historical news without affecting other profiles
  - Files: `admin/app.py`, `configurations/config_loader.py`, `configurations/db.py`

- **Auto-reload After Clear**: Page now automatically reloads after clearing historical news
  - Added JavaScript redirect after successful clear operation
  - Provides immediate feedback that operation completed
  - Eliminates need for manual page refresh

- **Force Run Now Working**: Removed 2-hour cooldown restriction on manual runs
  - Previous: Manual runs blocked if last run was < 2 hours ago
  - New: Manual runs always allowed (cooldown only applies to scheduled runs)
  - Rationale: Users should control when to run, not the system
  - File: `agents/agents_controller.py`

**New Features**:
- **Skip Comparison Option**: Added checkbox to bypass news comparison during runs
  - Use case: When you want fresh baseline without comparing to old data
  - Location: Run page, appears before "Confirm Run" button
  - Behavior: When checked, skips `compare_news` agent (no deduplication/update detection)
  - All collected news treated as new items
  - Useful after clearing historical news or starting fresh
  - File: `admin/templates/run_status.html`

- **Improved Reset Button**: Enhanced "Clear Historical News" button with better labeling
  - New tooltip: "Clear all historical news from the baseline (last 7 days). Use before 'Skip comparison' to start completely fresh."
  - Clarifies relationship between Clear and Skip Comparison
  - Helps users understand the two-step reset workflow

**Security Improvements**:
- **Credentials Migration**: Removed all credentials from database storage
  - Verified no `credentials` table exists in SQLite database
  - All credentials now loaded exclusively from environment variables
  - Updated `.env` file with correct Gmail App Password (16-character code)
  - Tested email sending - working correctly
  - Updated SPEC.md with security note about environment-only credentials
  - Files: `.env`, `SPEC.md` (Section 8.1)

**Testing**:
- All bug fixes tested and verified working
- Email credentials tested with successful SMTP send to hanyzanaty@gmail.com
- Skip comparison tested with SA/HCM profile
- Clear historical news tested with correct profile isolation

**Documentation Updated**:
- CHANGELOG.md → Added v2.8 entry with all changes
- SPEC.md → Added security note to Section 8.1 (Environment Variables)
- memory-bank/progress.md → Added v2.8 entry
- memory-bank/activeContext.md → Updated to v2.8

**Files Modified**:
- `admin/app.py` - Fixed clear route, added skip_comparison parameter
- `admin/templates/run_status.html` - Added skip comparison checkbox
- `configurations/config_loader.py` - Added profile_id to clear_news_baseline()
- `configurations/db.py` - Added profile_id to clear_news_baseline()
- `agents/agents_controller.py` - Removed 2-hour cooldown, added skip_comparison logic
- `.env` - Updated Gmail credentials
- `SPEC.md` - Added security note
- `CHANGELOG.md` - Added v2.8 entry

---

## Update v2.7 (2026-03-19)

### v2.7 — SAP AI Core Integration (2026-03-19)

**Major Changes**:
- **SAP AI Core Integration**: Replaced OpenAI API with SAP AI Core for all AI operations
  - New module: `agents/sap_ai_client.py` - SAP AI Core client with OAuth2 authentication
  - Credentials stored in environment variables (no personal API keys)
  - Chat completions (GPT-4o-mini equivalent) for filtering and grouping
  - Text embeddings (text-embedding-3-small equivalent) for similarity
  - Automatic token refresh and error handling

**Environment Variables** (New):
- `LEGAL_EAGLE_SAP_AICORE_BASE_URL` - AI Core API endpoint
- `LEGAL_EAGLE_SAP_AICORE_AUTH_URL` - OAuth2 authentication endpoint
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_ID` - OAuth2 client ID
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET` - OAuth2 client secret
- `LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID` - Chat model deployment ID
- `LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID` - Embeddings model deployment ID

**Environment Variables** (Deprecated):
- `LEGAL_EAGLE_OPENAI_API_KEY` - No longer used (replaced by SAP AI Core credentials)

**Code Changes**:
- Created: `agents/sap_ai_client.py` - SAP AI Core client with OAuth2 flow
- Modified: `agents/news_filter.py` - Uses `_get_ai_client()` for SAP AI Core
- Modified: `agents/news_grouper.py` - Uses `_get_ai_client()` for SAP AI Core
- Modified: `agents/compare_news.py` - Uses `_get_ai_client()` for SAP AI Core
- Modified: `agents/email_sender.py` - Uses `_get_ai_client()` for SAP AI Core
- Modified: `configurations/env_loader.py` - Loads SAP AI Core credentials
- Modified: `configurations/config_loader.py` - Provides SAP AI Core config
- Updated: `.env.example` - Added SAP AI Core variables
- Updated: `BTP_DEPLOYMENT.md` - SAP AI Core deployment instructions

**Admin UI Changes**:
- Fixed: "Clear Historical News" button now clears both `news_items` and `filtered_news` tables
- Shows detailed feedback: "Cleared 262 items (0 baseline + 262 filtered)."

**Testing**:
- Created: `scripts/test_sap_aicore.py` - Test script for SAP AI Core connection
- Created: `scripts/list_sap_aicore_deployments.py` - List available models
- Verified: Filtering, grouping, translation, and embeddings work correctly
- Tested: TR/HCM profile run completed successfully with SAP AI Core

**Documentation Updated**:
- SPEC.md → v2.7 (updated version, date, SAP AI Core integration)
- CHANGELOG.md → Added v2.7 entry
- BTP_DEPLOYMENT.md → SAP AI Core environment variables section
- memory-bank/progress.md → Added v2.7 entry
- memory-bank/activeContext.md → Updated to v2.7
- memory-bank/techContext.md → SAP AI Core technical details

**Security Improvements**:
- Removed personal OpenAI API keys from codebase
- Credentials managed via environment variables
- OAuth2 token refresh handled automatically
- No API keys stored in database or configuration files

---

## Update v2.6.0 (2026-03-10)

### v2.6.0 — BTP Cloud Foundry Deployment (2026-03-10)

**Major Features**:
- **BTP Cloud Foundry Deployment Support**: Full deployment to SAP BTP Cloud Foundry environment
  - Multi-buildpack configuration: apt-buildpack + python_buildpack
  - apt-buildpack installs Chromium system libraries (libnspr4, libnss3, libgbm1, etc.)
  - .profile script auto-installs Playwright browser on container startup
  - 1GB memory allocation for Playwright operations
  - 60-second timeout for dynamic rendering (increased from 20s)

**Deployment Files Added**:
- `manifest.yaml` - Cloud Foundry deployment configuration (1GB memory, 2GB disk, routes)
- `apt.yml` - System package dependencies for Chromium (23 libraries)
- `.profile` - Playwright browser installation script (runs on startup)
- `.cfignore` - Files to exclude from CF deployment
- `Procfile` - Gunicorn start command
- `runtime.txt` - Python 3.11 specification
- `requirements.txt` - Root-level Python dependencies (Flask, Playwright, etc.)
- `BTP_DEPLOYMENT.md` - Complete deployment guide

**Code Changes**:
- Modified: `agents/url_sources_runner.py` (timeout increased from 20s to 60s)

**Known Issues**:
- **Network Connectivity**: Saudi government websites (uqn.gov.sa) unreachable from BTP network
  - Cloud provider IP ranges appear blocked by government infrastructure
  - RSS feeds and Twitter API work fine
  - Workaround: Hybrid architecture (BTP for RSS/Twitter, local for blocked sites)

**Testing**:
- Deployment successful on BTP Cloud Foundry EU21 (Netherlands)
- Playwright browser installed and operational
- System libraries correctly installed via apt-buildpack
- RSS and Twitter sources working
- Dynamic rendering functional (but blocked sites timeout)

**Documentation Updated**:
- BTP_DEPLOYMENT.md → Added Playwright section, known issues
- memory-bank/progress.md → Added v2.6.0 entry
- Deleted: BTP_QUOTA_ISSUE.md (obsolete after quota resolution)

---

## Update v2.5.2 (2026-02-25)

### v2.5.2 — Translation Bug Fix (2026-02-25)

**Bug Fix**:
- **Fixed Variable Name Collision in Translation**: Resolved critical bug in `translate_grouped_summary()` function
  - **Issue**: Variable `translated_summary` was reused for two purposes:
    - As a list to collect translated groups (line 44)
    - As a string to hold translated summary text (line 91)
  - **Error**: When trying to `append()` to the list, it was actually a string: `'str' object has no attribute 'append'`
  - **Fix**: Renamed string variable to `translated_summary_text` to avoid collision
  - **Impact**: Translation now works correctly for all language pairs

**Files Changed**:
- Modified: `agents/email_sender.py` (lines 91-94)
- Updated: `memory-bank/progress.md`

**Testing**:
- Verified fix resolves TR/HCM translation errors
- Translation from Turkish to English now completes successfully

---

## Update v2.5.1 (2026-02-23)

### v2.5.1 — Code Consolidation: Resmi Gazete Inline Integration (2026-02-23)

**Refactoring**:
- **Consolidated Resmi Gazete Logic**: Merged specialized scraper into unified URL sources runner
  - Removed `agents/resmi_gazete_scraper.py` (external module)
  - Moved all functions inline to `agents/url_sources_runner.py`:
    - `_generate_gazette_date_urls()` - Internal function for date URL generation
    - `_extract_gazette_items()` - Internal function for item extraction
    - Inline scraping logic in `run_unified_sources()`
  - Removed external import dependency
  - Deleted test script `scripts/test_resmi_gazete_august.py` (referenced external module)

**Benefits**:
- Simpler architecture: All URL scraping logic in one unified module
- No external module dependencies for specialized scrapers
- Easier maintenance: One place to update scraping logic
- Consistent with project architecture pattern

**Functionality Unchanged**:
- Turkey Official Gazette support remains fully functional
- Same auto-detection when `resmigazete.gov.tr` URL is configured
- Same date-based navigation via `date_scope` (last_7_days, last_30_days)
- Same optional `start_date` parameter for historical scraping
- Same title + link extraction (no PDF parsing)

**Files Changed**:
- Modified: `agents/url_sources_runner.py` (added inline functions, removed import)
- Deleted: `agents/resmi_gazete_scraper.py`
- Deleted: `scripts/test_resmi_gazete_august.py`
- Updated: `memory-bank/progress.md`, `memory-bank/activeContext.md`

---

## Update v2.5.0 (2026-02-23)

### v2.5.0 — Turkey Official Gazette Support (2026-02-23)

**Major Features**:
- **Turkey Official Gazette (Resmi Gazete) Support**: Added specialized handling for Turkey's official legal gazette
  - Automatic detection when `resmigazete.gov.tr` URL is configured
  - Date-based navigation (Last 7 days, Last 30 days via `date_scope`)
  - Optional `start_date` parameter for historical scraping (DD.MM.YYYY format)
  - Extracts gazette item titles with direct links to official documents
  - Works with TR/HCM glossary for relevance filtering
  - No PDF parsing required - user clicks links to read full documents

**Key Components** (Note: Consolidated in v2.5.1):
- Inline functions in `agents/url_sources_runner.py`:
  - `_generate_gazette_date_urls()` - Generates daily gazette URLs from start date
  - `_extract_gazette_items()` - Extracts titles and links from listing pages
  - Inline scraping logic - Main entry point with date range support
  - Filters out navigation elements automatically (PDF Görüntüle, Sonraki Sayı, etc.)

**Integration**:
- `agents/url_sources_runner.py` - Auto-detects Resmi Gazete URLs
  - When `resmigazete.gov.tr` detected, uses inline scraping logic
  - Passes `start_date` (if configured) and `days_count` from `date_scope`
  - Falls back to today if no start_date provided
  - Bypasses generic static/dynamic crawlers

**User Workflow**:
1. Configure Resmi Gazete URL in Admin UI: `https://www.resmigazete.gov.tr/`
2. Set Date Scope: "Last 7 days" or "Last 30 days"
3. Optionally add Turkish HCM glossary keywords
4. Run profile - receives daily digest with gazette items matching keywords
5. Click item links to view full legal documents on official site

**Technical Design**:
- Similar to GOSI scraper pattern: extract titles + links only
- No PDF parsing (reduces complexity, faster processing)
- Date-forward iteration (start_date → start_date + N days)
- Same-origin link filtering with detail pattern support
- Deduplicated by title to avoid navigation element duplicates

**Documentation Updated**:
- memory-bank/progress.md → Added v2.5.0 entry
- memory-bank/activeContext.md → Updated to v2.5.0
- memory-bank/techContext.md → Added Resmi Gazete technical details
- CHANGELOG.md → Added v2.5.0 user-facing changes

---

## Update v2.4.0 (2026-02-19)

### v2.4.0 — Translation & Language Features (2026-02-19)

**Major Features**:
- **Per-Receiver Translation Language**: Each email receiver can specify their preferred language
  - New `translation_lang` column in `email_receivers` table (default: 'en')
  - Admin UI displays language dropdown per receiver
  - Email sender groups receivers by language and caches translations
  - Supported languages: English, Arabic, Spanish, French, German, Chinese, Japanese, Korean, Portuguese, Russian, Turkish, Hindi, Italian, Dutch, Polish

- **Profile Analysis Language Editing**: Profile's default language now editable in Admin UI
  - New "Profile Language" section at top of configuration page
  - Dropdown with all supported languages
  - Language used by AI to read and analyze news sources
  - Separate from receiver translation languages

- **Email Subject Includes Profile**: Subject line now shows country/LoB for multi-profile LPMs
  - Format: `🦅 Legal Eagle Daily Digest — SA/HCM — 2026-02-19`
  - Helps LPMs managing multiple countries distinguish emails

- **Translation Caching**: Email sender optimizes OpenAI API calls
  - Groups receivers by translation language
  - Translates once per language group
  - Caches translations to avoid redundant API calls
  - Significant cost savings for multiple receivers

**Key Components Added**:
- `LANGUAGE_NAMES` constant in `config_loader.py` (15 languages)
- `load_email_receivers_with_lang()` in `config_loader.py`
- `upsert_email_receiver_with_lang()` in `db.py`
- `translate_grouped_summary()` in `email_sender.py`
- `update_profile_language()` route in `admin/app.py`
- `update_email_receiver_language()` route in `admin/app.py`

**Database Changes**:
- `email_receivers` table: Added `translation_lang` column (TEXT, default 'en')
- Migration script: `scripts/migrate_add_translation_lang.py`

**Admin UI Changes**:
- New "Profile Language" section in profile configuration page
- Email Receivers table now shows translation language column with dropdown
- Language selection with save button per receiver
- Both changes use same language options (LANGUAGE_NAMES)

**Testing**:
- Tested with multiple receivers in different languages
- Verified translation caching works correctly
- Confirmed email subject includes profile identifier

**Documentation Updated**:
- SPEC.md → v2.4 (added translation features, database schema, routes)
- .clinerules/rules.md → Added Memory Bank Protocol section
- memory-bank/ files updated with v2.4.0 changes

---

## Update v2.1.0 (2026-02-10)

### v2.1.0 — Twitter Search API, Date Filtering, and Lookback Window (2026-02-10)

**Major Features**:
- **Twitter Search API Integration**: Replaced per-account timeline fetching with multi-account Search API
  - Fetches tweets from ALL accounts in a single API call (more efficient)
  - Uses `GET /2/tweets/search/recent` endpoint
  - Removed round-robin account selection (no longer needed)
  - Deprecated `twitter_last_account_index` setting
  - Maintains 15-minute rate limit enforcement
  - Max 100 tweets per request, 7-day lookback on Free tier

- **Profile-level Lookback Window**: Configurable news lookback period
  - New setting: `news_lookback_days` (default: 7 days)
  - Applied to all sources: Twitter, RSS, URL crawls
  - Stored per profile in `settings` table
  - Twitter Search API limited to max 7 days on Free tier

- **Date Filtering Utility**: New `agents/date_filter.py` module
  - Unified date filtering across RSS, Twitter, and URL sources
  - Filters items by publication date before relevance filtering
  - Fail-safe: keeps items without parseable dates
  - Supports multiple date formats (ISO 8601, simple YYYY-MM-DD)
  - Flexible field detection (tries `date`, `published`, `published_at`, `pubDate`, `created_at`)

**Key Functions Added**:
- `search_tweets_multi_account()` in `agents/tweet_feed.py`
- `filter_items_by_date()` in `agents/date_filter.py`
- `parse_item_date()` in `agents/date_filter.py`
- `check_twitter_rate_limit()` in `agents/tweet_feed.py` (enforces 15-min rule)

**Testing**:
- Created `scripts/test_twitter_search.py` for testing multi-account Search API
- Verified: 14 tweets from 2 accounts in single API call
- Confirmed: Free tier rate limit is 1 request per 15 minutes for Search API

**Documentation Updated**:
- SPEC.md → v2.1 (added date_filter.py, updated Twitter API sections, settings table)
- README.md → Added v2.1.0 to Recent Improvements
- CHANGELOG.md → Already up-to-date with v2.1.0 entry

**Legacy Code (Deprecated but Kept)**:
- `fetch_recent_tweets()` - single account timeline endpoint
- `select_next_twitter_account()` - round-robin rotation
- Timeline-based functions marked as deprecated in code comments

---

## Previous Updates

### v2.0.1 (2026-01-28)
- Twitter API rate limit enforcement (15-minute rule per Free tier)
- Round-robin account rotation for fair Twitter monitoring coverage
- Resource skip optimization (2-hour rule for RSS/URLs to reduce unnecessary processing)
- Status cards on run page matching review page design style
- Backfill support for run timestamps from previous executions

### v2.0.0 (2026-01-27)
- Documentation refactor & baseline
- Consolidated all technical documentation into SPEC.md v2.0
- Established baseline for future changelog entries

### v2.4.0 (2026-01-13 18:49:55Z) [Internal Development]
**Note**: This was an internal version number used during development. Official releases follow v2.0 → v2.0.1 → v2.1.0 pattern.

- Admin UI enhancements:
  - New Run page (split layout with live logs via SSE)
  - Bulk delete for all sections
  - Simplified Email Receivers and Glossary management
  - Global Credentials page
- Controller refactored for unified URL sources runner
- New DB tables: runs, run_logs
- Automatic cleanup of runs and logs older than 7 days
