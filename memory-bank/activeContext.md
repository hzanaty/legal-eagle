## Current State: v2.16 — Admin UI Fixes & Enhancements (2026-04-28)

### ✅ v2.16 COMPLETE - Admin UI Fixes & Enhancements
**Status**: All UI consistency improvements complete. Tables, forms, and recursive fields working correctly.

**Completion Date**: 2026-04-28 02:19 UTC+3

### Scheduler Removal (v2.15):

#### ✅ Files Deleted:
- **scripts/schedule_runner.py** (194 lines) - APScheduler daemon script
- **scripts/scheduler_entry.sh** (34 lines) - Cron/launchd wrapper script  
- **scripts/launchd/legal.eagle.scheduler.plist** (63 lines) - macOS launchd config
- **Total**: 291 lines of unused code removed

#### ✅ UI Changes:
- **Removed Schedule section from profile.html**
  - Eliminated misleading day-of-week dropdown
  - Removed "Save Schedule" button
  - Removed "Profiles with Unset are skipped by the controller" help text
  - Section order now: Language → Twitter → RSS → URL Sources → Email → Monitor → Glossary

#### ✅ Documentation Updates:
- **SPEC.md** - Removed scheduler from technology stack, updated data flow diagram, removed scheduler files from file structure
- **README.md** - Updated scripts/ description from "schedulers" to "migrations, admin launchers"
- **BTP_DEPLOYMENT.md** - Updated architecture diagram, kept Job Scheduler section (it's an external option)
- **CHANGELOG.md** - Added v2.15 entry with rationale and external scheduling options

### Rationale:
- Built-in scheduler was incomplete and non-functional
- Schedule UI was misleading (showed settings that didn't work)
- Prefer external scheduling for better flexibility and platform integration
- Cleaner codebase with one less system to maintain
- Eliminates confusion about how scheduling actually works

### External Scheduling Options:
Users can schedule runs via:
1. **BTP Job Scheduler** (for cloud deployments)
   - Create job in BTP Cockpit
   - Configure HTTP endpoint to call Admin UI or API
   - Set cron schedule (e.g., `0 6 * * *` for daily at 6 AM)

2. **Cron** (for Linux/macOS)
   ```bash
   0 9 * * * cd /path/to/legal-eagle && python3 agents/agents_controller.py --profile-id 1
   ```

3. **Windows Task Scheduler** (for Windows)
   - Create scheduled task
   - Run Python script with profile ID

4. **Manual runs** via Admin UI (always available)
   - No cooldown restrictions on manual runs
   - Full control over when to execute

### Previous Update: v2.14 — Selective Source Execution & Bug Fixes (2026-04-28)

### ✅ v2.14 COMPLETE - Selective Source Execution & Bug Fixes
**Status**: All features working. Users can now select specific sources to run, with multiple critical bug fixes.

**Completion Date**: 2026-04-28 00:43 UTC+3

### Selective Source Execution (v2.14):

#### ✅ UI Enhancement - Source Selection:
- **Run page now includes source selection panel**
  - Individual checkboxes for RSS feeds, Twitter accounts, and URL sources
  - Collapsible sections with expand/collapse buttons
  - Source counts displayed in section headers (e.g., "RSS Feeds (1)")
  - Selection state persisted in browser localStorage
  - Default behavior: all sources selected (opt-out model)
  - Clean, SAP Fiori-styled UI matching existing design system

#### ✅ Backend Implementation:
- **Enhanced `run_profile_once()` function** (`agents/agents_controller.py`)
  - New optional parameters: `selected_rss_urls`, `selected_twitter_handles`, `selected_url_sources`
  - Filters sources before fetching based on user selection
  - None value = run all sources (backwards compatible)
  - Logs show filtered counts: "📰 Filtered RSS feeds: 1 selected out of 1"

- **Updated `admin_start_run()` route** (`admin/app.py`)
  - Extracts selected sources from form data using `getlist()`
  - Passes selections to `run_profile_once()`
  - Empty list converted to None (meaning "run all")

#### ✅ Critical Bug Fixes:
1. **Missing Python imports** (`agents/agents_controller.py` line 2)
   - Added: `from typing import Optional, List`
   - Fixed: `name 'Optional' is not defined` error

2. **Twitter account dict/string handling** (`agents/agents_controller.py` line 406-407)
   - `load_tweet_accounts()` returns `List[Dict]` with keys: handle, max_lookback_days, last_fetch_date
   - `search_tweets_multi_account()` expects `List[str]` (just handles)
   - Fixed: Extract handles before API call: `handles_only = [a['handle'] if isinstance(a, dict) else str(a) for a in TWEET_ACCOUNTS]`
   - Fixed: `'dict' object has no attribute 'lstrip'` error

3. **Email sender variable typos** (`agents/email_sender.py` line 268-269)
   - Fixed: `nbg` → `native_bg`
   - Fixed: `nb` → `native_border`
   - Fixed: `badge` → `native_badge`
   - Fixed: `name 'nbg' is not defined` error

4. **Missing template variables** (`admin/app.py` line 401-414)
   - Added: `total_history = news_count + filtered_news_count`
   - Added: `disable_clear = run_active or total_history == 0`
   - Fixed: Buttons not rendering correctly in UI

5. **Stale run detection** (Database cleanup)
   - Fixed: Run #19 stuck in "Running" status causing buttons to be disabled
   - Solution: Mark stale runs as "Failed" when detected

### Previous Update: v2.13 — Admin UI Stability Fix (2026-04-27)

### ✅ v2.13 COMPLETE - Admin UI Crash Recovery & Port Documentation
**Status**: All features working. Admin UI crash recovery implemented and port configuration documented.

**Completion Date**: 2026-04-27 22:57 UTC+3

### Admin UI Fix (v2.13.1):

#### ✅ Stale PID File Recovery:
- **Enhanced startup script** (`scripts/start_admin.sh`)
  - Automatic detection of stale PID files
  - Checks if process is actually running before claiming "already running"
  - Removes orphaned PID files automatically
  - Prevents restart failures after crashes

#### ✅ Port Documentation:
- **Default Port: 8080** (not 5001)
  - Configurable via `PORT` environment variable
  - BTP-compatible design (Cloud Foundry compatibility)
  - Updated SPEC.md Section 7.1 with full server configuration
  - Updated memory-bank/techContext.md with port details

### Previous Update: v2.13 — Strategic Roadmap Update Complete (2026-04-24)

### ✅ v2.13 COMPLETE - 6-Stage Evolution & AI4GPM Submission
**Status**: All features working. Strategic roadmap expanded to 6 stages with AI4GPM idea submitted.

**Completion Date**: 2026-04-24 05:35 UTC+3

### Strategic Changes (v2.13):

#### ✅ Evolution Roadmap Expanded:
- **Added Stage 3 — SAP Consultant** to strategic evolution
  - Bridges gap between legal interpretation and SAP solution impact
  - Taxonomy MCP integration for product mapping
  - Maps legal changes to affected SAP products (HCM, Payroll, SuccessFactors, S/4HANA)
  - Identifies impacted SAP objects, processes, and functional areas
  - Determines configuration vs enhancement requirements
  - New sequence: Journalist → Lawyer → **SAP Consultant** → Smart MCP → Virtual LPM → Executive Advisor

#### ✅ AI4GPM Idea Submitted:
- **GSIDEAS-457** created in production JIRA
  - Title: "Legal Eagle: From Regulatory Intelligence to Virtual Localization Product Manager"
  - Complete 6-stage evolution roadmap with quantifiable benefits
  - User story includes all 5 personas (Journalist, Lawyer, SAP Consultant, Virtual LPM, Executive Advisor)
  - Submitted to AI4GPM evaluation pipeline
  - URL: https://jira.tools.sap/browse/GSIDEAS-457

#### ✅ Documentation Cleanup:
- **Renamed docs/README.md → docs/INDEX.md**
  - Eliminated naming conflict with root README.md
  - Updated header to "Legal Eagle Documentation Index"
  - Clarified purpose as navigation/index file

### Documentation Changes (v2.13):

#### ✅ Files Updated:
- **README.md** - Updated vision with 6-stage evolution
  - Added Stage 3 (SAP Consultant) description
  - Updated evolution sequence throughout
  - Stage numbering corrected (Virtual LPM → Stage 5, Executive Advisor → Stage 6)
  
- **docs/INDEX.md** - Renamed from docs/README.md
  - Updated header to reflect purpose
  - No broken references (verified via search)

- **CHANGELOG.md** - Added v2.13 entry
  - Strategic roadmap update details
  - AI4GPM submission information
  - Documentation cleanup notes

- **memory-bank/activeContext.md** - This update
- **memory-bank/progress.md** - Added v2.13 entry

#### ✅ Source of Truth:
- **Big_Picture.md** - Already contained v4 with 6-stage roadmap
  - No changes needed (was already correct)
  - Serves as reference for README.md updates

### Previous Documentation Changes (v2.12):

#### ✅ New Files Created:
- **UI5_MIGRATION_ROADMAP.md** - Comprehensive standalone roadmap (828 lines)
  - 12 detailed sections covering migration strategy
  - MCP server configuration (UI5 MCP, SAPUI5 MCP, Fiori Elements Brain)
  - SAP MCP Server Registry link for additional resources
  - 5-week implementation timeline with phases
  - Hybrid architecture approach (Flask + SAPUI5)
  - REST API conversion guide with examples
  - Testing strategy and deployment considerations

#### ✅ Files Updated:
- **README.md** - Enhanced with strategic roadmap
  - Version bumped to 2.12
  - Added "Major Initiatives" section under Roadmap
  - UI5/Fiori Migration initiative with high-level overview
  - Updated documentation links section
  - Cleaner separation: current features vs future plans
  
- **SPEC.md** - Cleaned up technical specification
  - Removed Section 13 (UI5/Fiori Migration)
  - Updated Table of Contents (now ends at Section 12)
  - Added "Future Plans" section with links to roadmap files
  - Kept focused on current v2.12 architecture only

### Rationale for Changes:
- **Separation of Concerns**: Current technical spec vs future strategic plans
- **Scalability**: Can now add more roadmap initiatives without cluttering SPEC.md
- **Maintainability**: Easier to update migration plan independently
- **Clarity**: README shows high-level vision, detailed plans in dedicated files

### ✅ All v2.12 Features Still Present:

#### Documentation Structure (v2.12)
- ✅ UI5_MIGRATION_ROADMAP.md - Comprehensive standalone roadmap (828 lines)
- ✅ README.md enhanced with strategic roadmap
- ✅ SPEC.md cleaned up (removed Section 13, focused on current architecture)

#### Server Stability (v2.12)
- ✅ Flask reloader disabled (`use_reloader=False`)
- ✅ Auto-reload with Watchdog (`scripts/start_admin_with_autoreload.sh`)
- ✅ Fixed Admin UI Dict error on run page

### ✅ All v2.11 Features Still Present:

#### Core Infrastructure (v2.7-v2.8)
- ✅ SAP AI Core integration (`agents/sap_ai_client.py`, all agents)
- ✅ Clear History button fix (both tables, JS fix, profile isolation)
- ✅ Resend Last Email from HTML (`scripts/resend_email_from_html.py`, route in `app.py`)
- ✅ Skip Comparison / Force Run / Skip Email in `agents_controller.py`
- ✅ `last_successful_fetch` on url_sources table
- ✅ Bilingual email body (`COUNTRY_COLORS`, `LANG_BADGES` in `email_sender.py`)
- ✅ Per-receiver Translation Language removed from profile.html

#### Per-Source Date Tracking (v2.9)
- ✅ `max_lookback_days` + `last_fetch_date` columns on `rss_feeds` table
- ✅ `max_lookback_days` + `last_fetch_date` columns on `tweet_accounts` table
- ✅ `list_rss_feeds()` returns `List[Dict]` with `{url, max_lookback_days, last_fetch_date}`
- ✅ `list_tweet_accounts()` returns `List[Dict]` with `{handle, max_lookback_days, last_fetch_date}`
- ✅ `update_rss_feed_last_fetch()` function in db.py
- ✅ `update_tweet_account_last_fetch()` function in db.py
- ✅ Timestamp functions exported via config_loader.py

#### Twitter Error Handling (v2.10/v2.11)
- ✅ `validate_twitter_token()` in tweet_feed.py (pre-flight check)
- ✅ `set_twitter_error_flag()` in tweet_feed.py
- ✅ `get_twitter_error_flag()` in tweet_feed.py
- ✅ `clear_twitter_error_flag()` in tweet_feed.py
- ✅ Error flag integration in `search_tweets_multi_account()` (402/401/403 → set flag, 200 → clear flag)
- ✅ Error flag check in `agents_controller.py` before running tweets
- ✅ `POST /admin/profiles/<id>/tweets/clear_error` route in app.py
- ✅ Twitter error flag/timestamp passed to profile template
- ✅ Smart error banner (🔴 Red with "Clear Error & Retry" / 🟢 Green "API Status: OK") in profile.html
- ✅ Twitter section moved to top of profile page (after Language, before RSS)
- ✅ Twitter table shows "Last Fetch" column with timestamps
- ✅ Removed old "Reset Quota Date" picker (replaced by error flag system)

#### Admin UI Improvements (v2.11)
- ✅ Profile page section order: Language → Twitter → RSS → URL Sources → Email → Monitor → Glossary
- ✅ RSS table handles Dict format: `{{ u.url if u is mapping else u }}`
- ✅ Twitter table handles Dict format: `{{ h.handle if h is mapping else h }}`

### Documentation Structure (v2.15):
```
Root Level:
├── README.md                      # User guide + 6-stage strategic vision
├── Big_Picture.md                 # Detailed 6-stage evolution roadmap (v4)
├── SPEC.md                        # Current v2.15 technical specification
├── UI5_MIGRATION_ROADMAP.md       # Detailed UI5/Fiori migration plan
├── CHANGELOG.md                   # Version history
└── BTP_DEPLOYMENT.md              # Deployment guide

docs/:
└── INDEX.md                       # Documentation navigation (renamed from README.md)

memory-bank/:
├── activeContext.md               # Current state (this file)
├── progress.md                    # Detailed version history
├── techContext.md                 # Technical deep dive
├── productContext.md              # Product vision
├── systemPatterns.md              # Design patterns
└── projectbrief.md                # Project overview
```

### Next Steps (Optional):
1. **Test external scheduling**: Set up BTP Job Scheduler or cron to verify scheduling works
2. **Monitor for issues**: Ensure no code depends on deleted scheduler files
3. **Future Stages**: Begin planning Stage 2 (Legal Analyzer) implementation

### Key Rules (from project conventions):
- **NEVER use X.Y.Z versions** — always X.Y only (e.g., v2.9, v2.10, v2.11, v2.12, v2.13, v2.14, v2.15)
- **Always update memory-bank** after any significant change
- **Always use write_to_file or replace_in_file** for file edits, NOT shell sed/awk
- **requires_approval: false** for read-only commands (grep, cat, wc, python3 diagnostics)
- **requires_approval: true** for destructive operations (rm, git push, cf push)

### Current Architecture (v2.15):
- RSS feeds: `load_rss_feeds()` → `List[Dict]` with `url`, `max_lookback_days`, `last_fetch_date`
- Tweet accounts: `load_tweet_accounts()` → `List[Dict]` with `handle`, `max_lookback_days`, `last_fetch_date`
- Twitter: pre-flight token validation, error flags for 402/401/403, auto-skip when flag set
- Profile page order: Language → Twitter → RSS → URL Sources → Email → Monitor → Glossary
- Email: Bilingual single-send model (profile lang + English translation)
- Documentation: Modular structure with separate roadmap files
- **Scheduling**: External only (BTP Job Scheduler, cron, manual runs)

### Working Directory
`/Users/i077750/Documents/GitHub/legal-eagle`

### Key Environment Variables
- `LEGAL_EAGLE_SAP_AICORE_BASE_URL` — SAP AI Core API endpoint
- `LEGAL_EAGLE_SAP_AICORE_AUTH_URL` — OAuth2 auth endpoint
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_ID` — OAuth2 client ID
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET` — OAuth2 client secret
- `LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID` — Chat model (gpt-4o)
- `LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID` — Embeddings model
- `LEGAL_EAGLE_TWITTER_BEARER_TOKEN` — Twitter API bearer token
- `LEGAL_EAGLE_GMAIL_EMAIL` — Gmail sender address (note: GMAIL_EMAIL not GMAIL_EMAIL_SENDER)
- `LEGAL_EAGLE_GMAIL_APP_PASSWORD` — Gmail app password