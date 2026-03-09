# CHANGELOG

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
