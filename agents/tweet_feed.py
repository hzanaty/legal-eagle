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


# ========================================
# Twitter Error Flag Constants (v2.10+)
# ========================================

TWITTER_ERROR_FLAG_KEY = "twitter_error_flag"
TWITTER_ERROR_TS_KEY = "twitter_error_timestamp"


def set_twitter_error_flag(profile_id: int, error_msg: str, conn=None) -> None:
    """
    Persist a Twitter error flag so the UI can display it and the pipeline can skip.
    Called when 401, 402, or 403 errors occur.
    
    Args:
        profile_id: Profile ID
        error_msg: Human-readable error description
        conn: Optional DB connection
    """
    ts = datetime.utcnow().isoformat()
    try:
        if conn and db_set_setting:
            db_set_setting(conn, profile_id, TWITTER_ERROR_FLAG_KEY, error_msg)
            db_set_setting(conn, profile_id, TWITTER_ERROR_TS_KEY, ts)
        else:
            set_setting_value(profile_id, TWITTER_ERROR_FLAG_KEY, error_msg)
            set_setting_value(profile_id, TWITTER_ERROR_TS_KEY, ts)
    except Exception as e:
        print(f"⚠️ Failed to set Twitter error flag: {e}")


def clear_twitter_error_flag(profile_id: int, conn=None) -> None:
    """
    Clear the Twitter error flag (called on successful fetch or from UI 'Clear & Retry' action).
    
    Args:
        profile_id: Profile ID
        conn: Optional DB connection
    """
    try:
        if conn and db_set_setting:
            db_set_setting(conn, profile_id, TWITTER_ERROR_FLAG_KEY, "")
            db_set_setting(conn, profile_id, TWITTER_ERROR_TS_KEY, "")
        else:
            set_setting_value(profile_id, TWITTER_ERROR_FLAG_KEY, "")
            set_setting_value(profile_id, TWITTER_ERROR_TS_KEY, "")
    except Exception as e:
        print(f"⚠️ Failed to clear Twitter error flag: {e}")


def get_twitter_error_flag(profile_id: int, conn=None) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (error_msg, timestamp) or (None, None) if no active error flag is set.
    
    Args:
        profile_id: Profile ID
        conn: Optional DB connection
    
    Returns:
        Tuple of (error_message, timestamp) or (None, None) if no error
    """
    try:
        if conn and db_get_setting:
            error_msg = db_get_setting(conn, profile_id, TWITTER_ERROR_FLAG_KEY, "")
            error_ts = db_get_setting(conn, profile_id, TWITTER_ERROR_TS_KEY, "")
        else:
            error_msg = get_setting_value(profile_id, TWITTER_ERROR_FLAG_KEY, "")
            error_ts = get_setting_value(profile_id, TWITTER_ERROR_TS_KEY, "")
        
        if error_msg:
            return error_msg, error_ts
        return None, None
    except Exception:
        return None, None


def validate_twitter_token(bearer_token: str) -> str:
    """
    Pre-flight check of the Twitter bearer token before making API calls.
    
    Returns one of:
    - "OK": Token appears valid
    - "MISSING": No token provided
    - "PLACEHOLDER": Token looks like a placeholder value  
    - "CREDITS_DEPLETED": API returned 402 Payment Required
    - "UNAUTHORIZED": API returned 401 Unauthorized
    - "ERROR": Other error
    """
    if not bearer_token:
        return "MISSING"
    
    # Check for placeholder/empty values
    placeholder_values = [
        "YOUR_TWITTER_BEARER_TOKEN",
        "your-twitter-bearer-token",
        "placeholder",
        "changeme",
        "xxxx",
        "XXXX",
    ]
    if bearer_token in placeholder_values or len(bearer_token) < 20:
        return "PLACEHOLDER"
    
    # Quick validation call - check a simple endpoint
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "LegalEagleBot/1.0"
    }
    params = {"query": "from:twitter", "max_results": 10}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            return "OK"
        elif response.status_code == 401:
            return "UNAUTHORIZED"
        elif response.status_code == 402:
            return "CREDITS_DEPLETED"
        elif response.status_code == 429:
            # Rate limited but token is valid
            return "OK"
        else:
            return "ERROR"
    except requests.exceptions.Timeout:
        return "ERROR"
    except Exception:
        return "ERROR"


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
    
    NOTE: This function is kept for backward compatibility but the 15-minute
    self-imposed wait has been removed in v2.10. Twitter now uses pay-per-use
    billing and the real platform rate limit (450 req/15-min) is enforced via
    HTTP 429, which the pipeline handles gracefully.
    
    Returns:
        (can_run: bool, minutes_to_wait: int) — always returns (True, 0)
    """
    # Rate limit guard removed in v2.10 (pay-per-use billing)
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
    
    Automatically sets/clears Twitter error flags based on API response:
    - 402 Payment Required → sets flag "402 Payment Required: Monthly API credits depleted"
    - 401 Unauthorized → sets flag "401 Unauthorized: Invalid or expired bearer token"
    - 403 Forbidden → sets flag "403 Forbidden: Access denied"
    - 200 OK → clears any existing error flag
    
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
    
    # Pre-flight token validation
    token_status = validate_twitter_token(bearer_token)
    if token_status == "MISSING":
        msg = "Twitter bearer token is not configured. Set LEGAL_EAGLE_TWITTER_BEARER_TOKEN."
        print(f"❌ {msg}")
        set_twitter_error_flag(profile_id, msg, conn)
        return []
    elif token_status == "PLACEHOLDER":
        msg = "Twitter bearer token appears to be a placeholder. Set a real token."
        print(f"❌ {msg}")
        set_twitter_error_flag(profile_id, msg, conn)
        return []
    elif token_status == "UNAUTHORIZED":
        msg = "401 Unauthorized: Twitter bearer token is invalid or expired."
        print(f"❌ {msg}")
        set_twitter_error_flag(profile_id, msg, conn)
        return []
    elif token_status == "CREDITS_DEPLETED":
        msg = "402 Payment Required: Monthly Twitter API credits depleted."
        print(f"⚠️ {msg}")
        set_twitter_error_flag(profile_id, msg, conn)
        return []
    
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
            
            # Clear any existing error flag on success
            clear_twitter_error_flag(profile_id, conn)
            
            # Convert to pipeline format
            items = []
            for tweet in tweets:
                text = tweet.get("text", "")
                created_at = tweet.get("created_at", "")
                tid = tweet.get("id", "")
                author_id = tweet.get("author_id", "")
                
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
            
        elif response.status_code == 401:
            msg = "401 Unauthorized: Twitter bearer token is invalid or expired."
            print(f"❌ {msg}")
            set_twitter_error_flag(profile_id, msg, conn)
            return []
            
        elif response.status_code == 402:
            msg = "402 Payment Required: Monthly Twitter API credits depleted."
            print(f"⚠️ {msg}")
            try:
                error_data = response.json()
                print(f"   Error details: {error_data}")
            except Exception:
                pass
            set_twitter_error_flag(profile_id, msg, conn)
            return []
            
        elif response.status_code == 403:
            msg = "403 Forbidden: Twitter API access denied."
            print(f"❌ {msg}")
            set_twitter_error_flag(profile_id, msg, conn)
            return []
            
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

def _get_user_id(username: str, token: str) -> tuple:
    """Get Twitter user ID from username. Returns (success, user_id_or_error)."""
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


def select_next_twitter_account(profile_id: int, accounts: list, conn=None) -> tuple:
    """DEPRECATED: Use search_tweets_multi_account() instead."""
    if not accounts:
        raise ValueError("No Twitter accounts configured")
    
    # Just return first account for compatibility
    selected = accounts[0]
    handle = selected.get('handle', '') if isinstance(selected, dict) else str(selected)
    return handle, 0


def fetch_recent_tweets(username, X_BEARER_TOKEN, profile_id, conn=None, max_results=5):
    """DEPRECATED: Use search_tweets_multi_account() instead."""
    return []
