# CHANGELOG

## v2.0.1 — 2026-01-28
### Improvements
- Twitter API rate limit enforcement (15-minute rule per Free tier)
- Round-robin account rotation for fair Twitter monitoring coverage
- Resource skip optimization (2-hour rule for RSS/URLs to reduce unnecessary processing)
- Status cards on run page matching review page design style
- Backfill support for run timestamps from previous executions

### Bug Fixes
- Fixed Twitter max_results parameter (3 → 5, API minimum requirement)
- Fixed missing last_full_run_time setting from previous runs

### Documentation
- Added TWITTER_RATE_LIMIT_FIX.md with detailed implementation guide

## v2.0.0 — 2026-01-27
### Documentation Refactor & Baseline
- Consolidated all technical documentation into SPEC.md v2.0
- Established baseline for future changelog entries
- Previous development history available in git commits
