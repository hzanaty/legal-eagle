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
