# CHANGELOG

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
