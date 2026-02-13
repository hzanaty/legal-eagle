# agents/tweet_feed.py

import time
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

from configurations.config_loader import get_setting_value, set_setting_value
try:
    from configurations.db import get_setting as db_get_setting, set_setting as db_set_setting
except Exception:
    db_get_setting = None
    db_set_setting = None


def _build_items(username: str, tweets: list[dict]) -> list[dict]:
    items = []
    for t in tweets:
        created_at = t.get("created_at", "")
        text = t.get("text", "")
        tid = t.get("id", "")
        link = f"https://x.com/{username}/status/{tid}" if tid else ""
        items.append(
            {
                "source": "Twitter",
                "source_type": "Tweet",
                "tweet_id": tid,
                "title": f"Tweet from @{username}",
                "summary": text,
                "link": link,
                "date": (created_at.split("T")[0] if created_at else ""),
                "content": f"{text}\n{link}\n{created_at}",
            }
        )
    return items


def _log_rate_limit_headers(resp: requests.Response) -> None:
    try:
        rem = resp.headers.get("x-rate-limit-remaining")
        lim = resp.headers.get("x-rate-limit-limit")
        reset = resp.headers.get("x-rate-limit-reset")
        print(f"RateLimit headers: remaining={rem}, limit={lim}, reset={reset}")
        if reset:
            try:
                reset_ts = int(reset)
                now = int(datetime.utcnow().timestamp())
                wait_sec = max(0, reset_ts - now)
                print(f"Approx. wait until reset: {wait_sec} seconds")
            except Exception:
                pass
    except Exception:
        pass


def check_twitter_rate_limit(profile_id: int, conn=None) -> Tuple[bool, int]:
    """
    Check if Twitter API can be called based on 15-minute rate limit.
    
    Returns:
        (can_run: bool, minutes_to_wait: int)
    """
    def _get_set(key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            if conn and db_get_setting:
                return db_get_setting(conn, profile_id, key, default)
            return get_setting_value(profile_id, key, default)
        except Exception:
            return default
    
    last_fetch = _get_set('twitter_last_fetch_time')
    if not last_fetch:
        return True, 0
    
    try:
        last_dt = datetime.fromisoformat(last_fetch)
        now = datetime.utcnow()
        elapsed = (now - last_dt).total_seconds() / 60  # minutes
        
        if elapsed < 15:
            wait_mins = int(15 - elapsed) + 1
            return False, wait_mins
        
        return True, 0
    except Exception:
        # If parsing fails, allow fetch
        return True, 0


def search_tweets_multi_account(
    accounts: List[str],
    bearer_token: str,
    profile_id: int,
    conn=None,
    days: int = 7,
    max_results: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetch tweets from multiple accounts using Twitter Search API (one call).
    
    Args:
        accounts: List of Twitter handles (with or without @)
        bearer_token: Twitter API Bearer Token
        profile_id: Profile ID for settings storage
        conn: Optional database connection
        days: Lookback window in days (max 7 for free tier)
        max_results: Max tweets to return (max 100 per request)
    
    Returns:
        List of tweet items formatted for pipeline, or empty list on error
    """
    if not accounts:
        print("⚠️ No Twitter accounts provided")
        return []
    
    # Enforce free tier limits
    if days > 7:
        print(f"⚠️ Twitter Search API limited to 7 days on free tier. Using 7 instead of {days}")
        days = 7
    
    if max_results > 100:
        max_results = 100
    
    def _set(key: str, value: str) -> None:
        try:
            if conn and db_set_setting:
                db_set_setting(conn, profile_id, key, value)
            else:
                set_setting_value(profile_id, key, value)
        except Exception:
            pass
    
    # Build search query
    handles = [h.lstrip("@") for h in accounts]
    query = " OR ".join([f"from:{h}" for h in handles])
    if len(handles) > 1:
        query = f"({query})"
    
    # Calculate start_time for lookback window
    start_time = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
    
    # Make API call
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "LegalEagleBot/1.0"
    }
    params = {
        "query": query,
        "start_time": start_time,
        "max_results": max_results,
        "tweet.fields": "created_at,author_id,text"
    }
    
    print(f"🐦 Searching tweets from {len(accounts)} accounts (last {days} days)...")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        # Update last fetch time
        _set('twitter_last_fetch_time', datetime.utcnow().isoformat())
        
        if response.status_code == 200:
            data = response.json()
            tweets = data.get("data", [])
            print(f"✅ Found {len(tweets)} tweets from Search API")
            
            # Convert to pipeline format
            # Note: We need to map author_id back to username for proper formatting
            # For now, we'll use a generic format. In future, could cache author_id->username mapping
            items = []
            for tweet in tweets:
                text = tweet.get("text", "")
                created_at = tweet.get("created_at", "")
                tid = tweet.get("id", "")
                author_id = tweet.get("author_id", "")
                
                # Try to find the username from the query accounts (best effort)
                # In practice, all tweets will be from our monitored accounts
                username = f"user_{author_id}"  # Fallback
                
                link = f"https://x.com/i/web/status/{tid}" if tid else ""
                
                items.append({
                    "source": "Twitter",
                    "source_type": "Tweet",
                    "tweet_id": tid,
                    "title": f"Tweet from Twitter",
                    "summary": text,
                    "link": link,
                    "date": (created_at.split("T")[0] if created_at else ""),
                    "content": f"{text}\n{link}\n{created_at}",
                    "author_id": author_id,
                })
            
            return items
            
        elif response.status_code == 429:
            print("⚠️ Rate limit hit on Search API")
            _log_rate_limit_headers(response)
            return []
        else:
            print(f"❌ Twitter Search API error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data}")
            except Exception:
                print(f"   Response: {response.text}")
            return []
            
    except Exception as e:
        print(f"❌ Exception calling Twitter Search API: {e}")
        return []


# ========================================
# LEGACY FUNCTIONS (Timeline API)
# Kept for backward compatibility
# ========================================

def _get_user_id(username: str, token: str) -> tuple[bool, str | dict]:
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "LegalEagleBot/1.0",
    }
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200:
        data = r.json()
        uid = data.get("data", {}).get("id")
        if uid:
            return True, uid
        return False, {"error": True, "status_code": 200, "message": "No user id in response", "username": username}
    elif r.status_code == 429:
        print("User lookup hit 429.")
        _log_rate_limit_headers(r)
        return False, {"error": True, "status_code": 429, "message": "Rate limited on user lookup", "username": username}
    else:
        return False, {"error": True, "status_code": r.status_code, "message": r.text, "username": username}


def select_next_twitter_account(profile_id: int, accounts: list[str], conn=None) -> Tuple[str, int]:
    """
    DEPRECATED: Use search_tweets_multi_account() instead.
    
    Select next account using round-robin rotation.
    Updates state in database.
    
    Returns:
        (selected_account: str, account_index: int)
    """
    if not accounts:
        raise ValueError("No Twitter accounts configured")
    
    def _get_set(key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            if conn and db_get_setting:
                return db_get_setting(conn, profile_id, key, default)
            return get_setting_value(profile_id, key, default)
        except Exception:
            return default
    
    def _set(key: str, value: str) -> None:
        try:
            if conn and db_set_setting:
                db_set_setting(conn, profile_id, key, value)
            else:
                set_setting_value(profile_id, key, value)
        except Exception:
            pass
    
    # Get last index
    last_idx = _get_set('twitter_last_account_index', '0')
    try:
        last_idx = int(last_idx)
    except ValueError:
        last_idx = 0
    
    # Select next account (round-robin)
    next_idx = (last_idx + 1) % len(accounts)
    selected = accounts[next_idx]
    
    # Update settings
    _set('twitter_last_account_index', str(next_idx))
    _set('twitter_last_fetch_time', datetime.utcnow().isoformat())
    
    return selected, next_idx


def fetch_recent_tweets(username, X_BEARER_TOKEN, profile_id, conn=None, max_results=5):
    """
    DEPRECATED: Use search_tweets_multi_account() instead.
    
    Fetch tweets for a known account using timeline endpoint only.
    - Caches user_id and last_seen_id in SQLite settings per profile.
    - Uses since_id to pull only new tweets.
    - No retries; returns immediately on any error.
    """
    handle = (str(username or "")).lstrip("@").lower()
    if not handle:
        return {"error": True, "status_code": 400, "message": "Empty username"}

    def _get_set(key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            if conn and db_get_setting:
                return db_get_setting(conn, profile_id, key, default)
            return get_setting_value(profile_id, key, default)
        except Exception:
            return default

    def _set(key: str, value: str) -> None:
        try:
            if conn and db_set_setting:
                db_set_setting(conn, profile_id, key, value)
            else:
                set_setting_value(profile_id, key, value)
        except Exception:
            pass

    # Reset quota date enforcement — disable until date; resume on date inclusive
    reset_str = _get_set('tweets_reset_quota_date', None)
    if reset_str:
        try:
            # Align to Asia/Dubai date by adding +4h to UTC
            today_dubai = (datetime.utcnow() + timedelta(hours=4)).date()
            block_until = datetime.fromisoformat(reset_str).date()
            if today_dubai < block_until:
                print(f"🐦 Tweet Agent disabled until {reset_str}. Skipping @{handle}.")
                return []
        except Exception:
            # If parsing fails, ignore and proceed
            pass

    headers = {
        "Authorization": f"Bearer {X_BEARER_TOKEN}",
        "User-Agent": "LegalEagleBot/1.0",
    }

    uid_key = f"twitter_userid:{handle}"
    last_key = f"twitter_last_seen_id:{handle}"

    # Resolve user_id from cache or lookup once
    user_id = _get_set(uid_key, None)
    requests_made = 0
    if not user_id:
        ok, uid_or_err = _get_user_id(handle, X_BEARER_TOKEN)
        requests_made += 1
        if not ok:
            return uid_or_err
        user_id = uid_or_err
        _set(uid_key, str(user_id))
        print(f"🐦 Cached user_id for @{handle}: {user_id}")
    else:
        print(f"🐦 Cache hit for user_id of @{handle}: {user_id}")

    # since_id to pull only new tweets
    since_id = _get_set(last_key, None)
    params = {
        "max_results": max_results,
        "tweet.fields": "created_at,text",
    }
    if since_id:
        params["since_id"] = since_id
        print(f"🐦 Using since_id for @{handle}: {since_id}")

    timeline_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    try:
        r = requests.get(timeline_url, headers=headers, params=params, timeout=30)
        requests_made += 1
    except Exception as e:
        return {"error": True, "message": f"Request failed: {e}", "username": handle}

    if r.status_code == 200:
        data = r.json()
        tweets = data.get("data", []) or []
        posts_pulled = len(tweets)
        print(f"🐦 @{handle}: requests={requests_made}, posts_pulled={posts_pulled}")

        if tweets:
            # Update last_seen_id to the highest tweet id
            try:
                max_id = str(max(int(t.get("id", "0")) for t in tweets if t.get("id")))
            except Exception:
                # Fallback lexicographic max
                max_id = max((t.get("id") for t in tweets if t.get("id")), default=None)
            if max_id:
                _set(last_key, max_id)
                print(f"🐦 Updated last_seen_id for @{handle} -> {max_id}")
        else:
            print(f"🐦 No new tweets for @{handle}. last_seen_id unchanged.")

        return _build_items(handle, tweets)

    if r.status_code == 429:
        print(f"🐦 Rate limit hit for @{handle} on timeline.")
        _log_rate_limit_headers(r)
        return {
            "error": True,
            "status_code": 429,
            "message": "Rate limited on timeline endpoint",
            "username": handle,
        }

    return {
        "error": True,
        "status_code": r.status_code,
        "message": r.text,
        "username": handle,
    }
