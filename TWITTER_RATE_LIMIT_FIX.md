# Twitter Rate Limit Fix - Implementation Summary

## Date: 2026-01-28

## Problem Statement

Twitter API Free tier failures due to:
1. **Invalid `max_results` parameter**: Code used `max_results=3`, but Twitter requires minimum 5
2. **Severe rate limiting**: Free tier allows only 1 request per 15 minutes per endpoint
3. **Multiple accounts**: Trying to fetch 2 accounts in one run caused immediate rate limit errors

## Solution Implemented

### 1. Fixed `max_results` Bug ✅
**File**: `agents/tweet_feed.py`
- Changed default from `max_results=3` to `max_results=5`
- Complies with Twitter API v2 requirements

### 2. Added Rate Limit Checking ✅
**File**: `agents/tweet_feed.py`
- New function: `check_twitter_rate_limit(profile_id, conn)`
  - Returns `(can_run: bool, minutes_to_wait: int)`
  - Checks if 15 minutes have elapsed since last fetch
  - Reads from SQLite setting: `twitter_last_fetch_time`

### 3. Implemented Round-Robin Account Selection ✅
**File**: `agents/tweet_feed.py`
- New function: `select_next_twitter_account(profile_id, accounts, conn)`
  - Selects ONE account per run using round-robin rotation
  - Stores state in SQLite: `twitter_last_account_index`
  - Updates `twitter_last_fetch_time` when account is selected
  - Returns `(selected_account: str, account_index: int)`

### 4. Added 2-Hour Resource Skip Optimization ✅
**File**: `agents/agents_controller.py`
- New function: `should_skip_resources(profile_id, conn)`
  - Checks if last full run was < 2 hours ago
  - Reads from SQLite setting: `last_full_run_time`
  - Skips RSS and URL sources if too recent (saves processing time)

### 5. Updated Main Run Logic ✅
**File**: `agents/agents_controller.py` → `run_profile_once()`

**New Behavior**:
```python
# Before Twitter fetch:
1. Check rate limit (15-minute rule)
2. If blocked:
   - Log wait time
   - Show next available time
   - Skip Twitter agent this run
3. If allowed:
   - Select next account (round-robin)
   - Fetch only that account
   - Update last fetch time

# For RSS/URL sources:
1. Check if last full run < 2 hours
2. If yes: Skip (optimization)
3. If no: Run full collection + update timestamp
```

## Expected User Experience

### Scenario 1: First Run (No Rate Limit)
```
✅ RSS Agent: 50 items
✅ Tweet Agent: @HRSD_SA (5 tweets) [#1/2]
✅ URL Sources: 10 items
Result: 65 total items
```

### Scenario 2: Quick Re-run (< 15 minutes)
```
⏭️ Skipping RSS Agent (last run 8 minutes ago)
⚠️ Twitter Rate Limit Active
   ↳ Last fetch: 8 minutes ago
   ↳ Please wait: 7 minutes
   ↳ Next available: 11:23 PM
🐦 Skipping Tweet Agent this run
⏭️ Skipping URL Sources (last run 8 minutes ago)
Result: No new items (too soon)
```

### Scenario 3: After 15 Minutes (Account Rotation)
```
⏭️ Skipping RSS Agent (last run 20 minutes ago)
✅ Tweet Agent: @SaudiGOSI (3 tweets) [#2/2]
⏭️ Skipping URL Sources (last run 20 minutes ago)
Result: 3 new tweets
```

### Scenario 4: After 2+ Hours (Full Collection)
```
✅ RSS Agent: 15 items
✅ Tweet Agent: @HRSD_SA (5 tweets) [#1/2]
✅ URL Sources: 8 items
Result: 28 total items
```

## SQLite Settings Used

### Per Profile:
- `twitter_last_fetch_time`: ISO timestamp of last Twitter API call
- `twitter_last_account_index`: Index of last fetched account (0, 1, 2...)
- `last_full_run_time`: ISO timestamp of last full RSS+URL collection
- `twitter_userid:{handle}`: Cached Twitter user ID (existing)
- `twitter_last_seen_id:{handle}`: Last seen tweet ID (existing)

## Rate Limit Strategy

### Free Tier Constraints:
- **Timeline endpoint**: 1 request per 15 minutes per app
- **Accounts**: 2 (@HRSD_SA, @SaudiGOSI)

### Solution:
- Fetch **1 account per run** (alternating)
- Wait **minimum 15 minutes** between fetches
- Use `since_id` for incremental updates (only new tweets)

### Daily Capacity:
- 96 runs per day (every 15 mins)
- 48 fetches per account per day
- **240 tweets/day per account** (48 × 5)
- **480 tweets/day total** (both accounts)

## Files Modified

1. ✅ `agents/tweet_feed.py`
   - Fixed max_results (3 → 5)
   - Added `check_twitter_rate_limit()`
   - Added `select_next_twitter_account()`

2. ✅ `agents/agents_controller.py`
   - Imported new functions
   - Added `should_skip_resources()`
   - Updated `run_profile_once()` with rate limit logic
   - Updated `run_profile_once()` with resource skip logic

## Next Steps (Not Implemented Yet)

### UI Updates (Planned):
1. Update `admin/app.py` routes to show rate limit status
2. Update `admin/templates/run_status.html` with status cards
3. Update `admin/templates/profile.html` with Twitter status section
4. Add visual feedback for:
   - ✓ Ready to run
   - ⏰ Wait X minutes
   - ⏭️ Skipped (< 2 hours)
   - Next account in rotation

### Documentation:
- Update SPEC.md with new behavior
- Document SQLite settings schema

## Testing Recommendations

1. **First test**: Run immediately (should work, select account 1)
2. **Second test**: Run after 5 minutes (should show "wait 10 minutes")
3. **Third test**: Run after 15 minutes (should work, select account 2)
4. **Fourth test**: Run after 30 minutes (should work, select account 1)
5. **Fifth test**: Check logs for round-robin pattern
6. **Sixth test**: Verify RSS/URL skip when < 2 hours

## Benefits

✅ **No more rate limit errors** (respects 15-min rule)  
✅ **Automatic account rotation** (fair coverage of both accounts)  
✅ **Resource optimization** (skips RSS/URL when unnecessary)  
✅ **Clear user feedback** (shows wait times and status)  
✅ **Maximizes Free tier value** (480 tweets/day possible)  
✅ **Works reliably long-term** (respects all API limits)

## Technical Notes

- All timestamps stored in UTC (ISO format)
- Display times converted to Asia/Dubai timezone (+4h)
- Round-robin index wraps: `(last_idx + 1) % len(accounts)`
- Settings persist across runs (SQLite `settings` table)
- No manual configuration needed (automatic state management)

---

**Implementation Status**: ✅ Core Logic Complete  
**UI Updates**: ⏳ Pending  
**Testing**: ⏳ Ready for user testing
