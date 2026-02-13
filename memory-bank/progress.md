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
