## Current State: v2.8 (2026-04-07)

### Active Version: 2.8
**Status**: Production-ready with bug fixes and UX improvements

### Recent Major Changes

#### 1. Critical Bug Fixes (v2.8)
- **Gmail Environment Variable Fix** (2026-04-08): Corrected environment variable name
  - Changed from `LEGAL_EAGLE_GMAIL_EMAIL_SENDER` to `LEGAL_EAGLE_GMAIL_EMAIL`
  - Updated `configurations/config_loader.py` to read correct variable
  - Updated `.env` file with correct variable name
  - Impact: "Resend Last Email" feature now works correctly
  - Simplified credential loading - removed unnecessary fallback logic

- **Fixed Clear Historical News**: Resolved issue where clearing baseline cleared wrong profile's data
  - Added `profile_id` parameter throughout call chain (route → config_loader → db)
  - Users can now safely clear historical news without affecting other profiles
  - Auto-reload after clear operation for immediate feedback

- **Fixed Force Run**: Removed 2-hour cooldown restriction on manual runs
  - Manual runs now always allowed (cooldown only for scheduled runs)
  - Users have full control over when to run profiles
  - File: `agents/agents_controller.py`

- **Skip Comparison Option**: Added checkbox to bypass news comparison
  - Use case: Fresh baseline without comparing to old data
  - Location: Run page, before "Confirm Run" button
  - Skips `compare_news` agent when checked (all news treated as new)
  - Useful after clearing historical news or starting fresh

- **Improved Reset Button**: Enhanced "Clear Historical News" tooltip
  - Clarifies relationship between Clear and Skip Comparison
  - Helps users understand two-step reset workflow

- **Security**: Credentials migration complete
  - No credentials stored in database (verified no `credentials` table)
  - All credentials in environment variables only
  - Updated `.env` with Gmail App Password
  - Email sending tested and working

#### 2. BTP Cloud Foundry Deployment (v2.6.0)

#### 1. BTP Cloud Foundry Deployment (v2.6.0)
- **Full BTP Deployment Support**: Complete deployment to SAP BTP Cloud Foundry environment
  - Multi-buildpack configuration: apt-buildpack + python_buildpack
  - apt-buildpack installs Chromium system libraries (23 libraries)
  - .profile script auto-installs Playwright browser on container startup
  - 1GB memory allocation for Playwright operations
  - 60-second timeout for dynamic rendering (increased from 20s)

- **Deployment Files**:
  - `manifest.yaml` - CF deployment configuration (1GB memory, 2GB disk, routes)
  - `apt.yml` - System package dependencies for Chromium
  - `.profile` - Playwright browser installation script
  - `.cfignore` - Files to exclude from CF deployment
  - `Procfile` - Gunicorn start command
  - `runtime.txt` - Python 3.11 specification
  - `requirements.txt` - Root-level Python dependencies
  - `BTP_DEPLOYMENT.md` - Complete deployment guide

- **Known Issue**: Network connectivity limitations
  - Saudi government websites (uqn.gov.sa) unreachable from BTP network
  - Cloud provider IP ranges appear blocked by government infrastructure
  - RSS feeds and Twitter API work fine from BTP
  - Workaround: Hybrid architecture (BTP for RSS/Twitter, local for blocked sites)

#### 2. Translation Bug Fix (v2.5.2)
- **Fixed Variable Name Collision**: Resolved critical bug in `translate_grouped_summary()` function
  - Variable `translated_summary` was reused as both list and string
  - Caused error: `'str' object has no attribute 'append'`
  - Fixed by renaming string variable to `translated_summary_text`
  - Translation now works correctly for all language pairs (TR→EN, AR→EN, etc.)

#### 2. Turkey Official Gazette Support (v2.5.0)
- **Specialized Resmi Gazete Scraper**: Auto-detects and handles Turkey's official gazette
  - Inline functions in `agents/url_sources_runner.py`:
    - `_generate_gazette_date_urls()` - Generates date-based URLs
    - `_extract_gazette_items()` - Extracts titles + links from listing pages
  - Automatic detection when URL contains `resmigazete.gov.tr`
  - Date-based navigation via `date_scope` field (last_7_days, last_30_days)
  - Optional `start_date` parameter for historical scraping (DD.MM.YYYY)
  - Extracts titles + links (no PDF parsing required)
  - Filters out navigation elements automatically

- **Integration**: Seamless URL sources runner integration
  - Auto-bypasses generic static/dynamic crawlers
  - Passes date parameters from profile configuration
  - Works with TR/HCM glossary for relevance filtering
  - User clicks links to read full documents on official site

#### 2. Translation & Language Features (v2.4.0)

#### 1. Translation & Language Features (v2.4.0)
- **Per-Receiver Translation**: Each email receiver can set their preferred language
  - New `translation_lang` column in `email_receivers` table
  - 15 supported languages (English, Arabic, Spanish, French, German, etc.)
  - Email sender groups receivers by language and caches translations
  - Admin UI shows language dropdown per receiver

- **Profile Language Editing**: Profile's analysis language now editable
  - New "Profile Language" section in Admin UI
  - Dropdown with all supported languages
  - Separate from receiver translation languages
  - Used by AI to read and analyze news sources

- **Email Subject Enhancement**: Subject includes profile identifier
  - Format: `🦅 Legal Eagle Daily Digest — SA/HCM — 2026-02-19`
  - Helps LPMs managing multiple countries

- **Translation Caching**: Optimized OpenAI API usage
  - Groups receivers by language
  - Translates once per language group
  - Caches translations to avoid redundant calls

#### 2. Twitter Search API Integration (v2.1.0)
- **Migration**: Moved from per-account timeline API to multi-account Search API
- **Efficiency**: Fetches all monitored accounts in single API call
- **Endpoint**: `GET /2/tweets/search/recent` (replaces `GET /2/users/{id}/tweets`)
- **Benefits**:
  - More efficient (1 call vs N calls for N accounts)
  - No round-robin rotation needed
  - 15-minute rate limit enforcement remains
  - Max 100 tweets per request
  - 7-day lookback on Free tier

#### 2. Profile-Level Lookback Window
- **New Setting**: `news_lookback_days` (default: 7 days)
- **Scope**: Applied across ALL sources (RSS, Twitter, URL crawls)
- **Storage**: Per-profile in `settings` table
- **Purpose**: Configurable time window for news collection
- **Constraint**: Twitter Search API limited to max 7 days on Free tier

#### 3. Date Filtering Utility
- **New Module**: `agents/date_filter.py`
- **Purpose**: Unified date filtering across all news sources
- **Features**:
  - Filters items by publication date BEFORE relevance filtering
  - Fail-safe: keeps items without parseable dates
  - Supports multiple date formats (ISO 8601, YYYY-MM-DD)
  - Flexible field detection (date, published, published_at, pubDate, created_at)
- **Integration**: Called by controller after collection, before filtering

### Current Architecture

#### Agents (Processing Pipeline)
1. **Collection Layer**:
   - `rss_parser.py` - RSS/Atom feed parsing
   - `tweet_feed.py` - Twitter Search API (v2.1+)
   - `url_sources_runner.py` - Static/dynamic website scraping
   - `date_filter.py` - Date-based filtering (v2.1+)

2. **Processing Layer**:
   - `news_filter.py` - AI semantic relevance filtering
   - `compare_news.py` - Deduplication & update detection
   - `news_grouper.py` - AI topic grouping

3. **Delivery Layer**:
   - `email_sender.py` - Gmail SMTP delivery

#### Controller Flow (v2.1)
```
1. Load profile configuration
2. Collect from sources:
   - RSS feeds → parse
   - Twitter accounts → search_tweets_multi_account()
   - URL sources → scrape (static/dynamic)
3. Apply date filter (news_lookback_days)
4. Semantic filtering (GPT-4o-mini)
5. Compare & deduplicate (embeddings)
6. Group & summarize (GPT-4o-mini)
7. Send email digest
```

### Database Schema (v2.1)

#### New/Updated Settings
- `news_lookback_days`: Lookback window in days (default: 7)
- `twitter_last_fetch_time`: Last Twitter API call timestamp
- `twitter_last_account_index`: **DEPRECATED** (no longer used with Search API)

#### Existing Tables
- `profiles`, `settings`, `rss_feeds`, `tweet_accounts`, `url_sources`
- `email_receivers`, `glossary_terms`, `glossary_synonyms`, `glossary_patterns`
- `news_items`, `filtered_news`, `runs`, `run_logs`, `audit_log`

### Admin UI (SAP Fiori Design)

#### Current Pages
- **Dashboard**: Profile list with selection-based toolbar
- **Create Profile**: Dedicated page for profile creation (v2.1)
- **Profile Configuration**: Sources, glossary, schedule management
- **Run Status**: Live log streaming with history (split panel)
- **Review News**: Filtered item review with scoring

#### Design Standards (v2.1)
- SAP Fiori color palette and typography
- Selection-based actions (no inline buttons)
- Text-only button labels (no emoji icons)
- Semantic button colors (blue=primary, green=success, red=danger, orange=warning)
- Responsive layouts with mobile optimization

### Known Technical Constraints

#### Twitter API (Free Tier)
- Rate limit: 1 request per 15 minutes for Search API
- Lookback: Maximum 7 days
- Results: Maximum 100 tweets per request
- No pagination support on free tier

#### OpenAI API
- Model: GPT-4o-mini (filtering, grouping)
- Embeddings: text-embedding-3-small (deduplication)
- Timeout: 60 seconds (configurable via env var)
- Retries: 2 attempts with 1-second backoff

#### Playwright (Dynamic Rendering)
- Browser: Chromium headless
- Timeout: 60 seconds per page (configurable)
- Resource: Heavy on memory (consider limits in production)

### Next Steps (Future Versions)

#### v3.0 - Enhanced Intelligence (Q2 2026)
- Deep impact analysis on SAP modules
- Risk scoring and priority classification
- Multi-language translation support
- Trend detection across countries
- Predictive alerts for regional patterns

#### v4.0 - LOKA Integration (Q4 2026)
- Bidirectional sync with LOKA MCP
- Auto-linking legal changes to regulations
- JIRA requirement auto-creation
- End-to-end compliance workflow

### Development Guidelines

#### When Adding Features
1. Update agents in `agents/` directory
2. Update controller in `agents/agents_controller.py`
3. Update database schema if needed (with migration script)
4. Update Admin UI templates if needed
5. **Update SPEC.md** with technical details
6. **Update README.md** if user-facing
7. **Update CHANGELOG.md** with version entry
8. **Update memory-bank files** (progress.md, activeContext.md)

#### Version Numbering
- Major releases: v2.0, v3.0, v4.0 (significant features)
- Minor releases: v2.1, v2.2, v2.3 (new features, backwards compatible)
- Patch releases: v2.1.1, v2.1.2 (bug fixes only)

### Current Working Directory
`/Users/i077750/Documents/GitHub/legal-eagle`

### Key Environment Variables
- `LEGAL_EAGLE_SAP_AICORE_BASE_URL` - SAP AI Core API endpoint (required)
- `LEGAL_EAGLE_SAP_AICORE_AUTH_URL` - OAuth2 authentication endpoint (required)
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_ID` - OAuth2 client ID (required)
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET` - OAuth2 client secret (required)
- `LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID` - Chat model deployment ID (required)
- `LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID` - Embeddings model deployment ID (required)
- `LEGAL_EAGLE_TWITTER_BEARER_TOKEN` - Twitter API bearer token (required)
- `LEGAL_EAGLE_GMAIL_EMAIL_SENDER` - Gmail sender address (required)
- `LEGAL_EAGLE_GMAIL_APP_PASSWORD` - Gmail app password (required)

### Testing Approach
- Test scripts in `scripts/` directory
- Prefix with `test_` (e.g., `test_twitter_search.py`)
- Test outputs in `scripts/test_runs/` (gitignored)
- Use small, realistic samples (e.g., 10 items)
- Test individual components before integration
