#!/usr/bin/env python3
"""
Twitter Multi-Account Search Test

Tests fetching tweets from multiple accounts using a single API call
via the Twitter Search endpoint (GET /2/tweets/search/recent).

Usage:
    python scripts/test_twitter_search.py
"""
import sys
import os
from datetime import datetime, timedelta

# Ensure project root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Load environment variables
try:
    from dotenv import load_dotenv, find_dotenv
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
except Exception:
    pass

import requests
from configurations.db import get_connection, create_schema_if_needed


def get_all_twitter_accounts():
    """
    Fetch all Twitter accounts from the database across all profiles.
    Returns: List of tuples (handle, profile_id, country_code, lob)
    """
    conn = get_connection()
    create_schema_if_needed(conn)
    
    rows = conn.execute("""
        SELECT 
            ta.handle,
            ta.profile_id,
            p.country_code,
            p.lob
        FROM tweet_accounts ta
        JOIN profiles p ON ta.profile_id = p.id
        ORDER BY ta.handle
    """).fetchall()
    
    conn.close()
    
    accounts = [(r["handle"], r["profile_id"], r["country_code"], r["lob"]) for r in rows]
    return accounts


def format_rate_limit_info(headers):
    """
    Parse and format rate limit headers from Twitter API response.
    """
    remaining = headers.get("x-rate-limit-remaining", "?")
    limit = headers.get("x-rate-limit-limit", "?")
    reset_ts = headers.get("x-rate-limit-reset", None)
    
    reset_str = "unknown"
    if reset_ts:
        try:
            reset_dt = datetime.fromtimestamp(int(reset_ts))
            now = datetime.now()
            delta = reset_dt - now
            minutes = int(delta.total_seconds() / 60)
            reset_str = f"{reset_dt.strftime('%I:%M %p')} (in {minutes} minutes)"
        except Exception:
            pass
    
    return {
        "remaining": remaining,
        "limit": limit,
        "reset": reset_str
    }


def test_twitter_search():
    """
    Main test function: Fetch tweets from multiple accounts using search endpoint.
    """
    print("🐦 Twitter Multi-Account Search Test")
    print("=" * 60)
    print()
    
    # Get Bearer Token
    bearer_token = os.environ.get("LEGAL_EAGLE_TWITTER_BEARER_TOKEN")
    if not bearer_token:
        print("❌ Error: LEGAL_EAGLE_TWITTER_BEARER_TOKEN not found in environment")
        print("   Please ensure .env file exists with this variable set")
        return False
    
    print(f"✅ Bearer Token loaded (length: {len(bearer_token)} chars)")
    print()
    
    # Get Twitter accounts from database
    accounts = get_all_twitter_accounts()
    
    if not accounts:
        print("❌ No Twitter accounts found in database")
        print("   Please add Twitter accounts via the Admin UI")
        return False
    
    print(f"📋 Found {len(accounts)} Twitter account(s) in database:")
    for handle, profile_id, country, lob in accounts:
        print(f"   - @{handle} (Profile: {country}_{lob}, ID: {profile_id})")
    print()
    
    # Build search query
    # Strip @ if present and build OR query
    handles = [h.lstrip("@") for h, _, _, _ in accounts]
    query = " OR ".join([f"from:{h}" for h in handles])
    
    # Wrap in parentheses for proper OR grouping
    if len(handles) > 1:
        query = f"({query})"
    
    print("🔍 Search Query:")
    print(f"   {query}")
    print()
    
    # Make API call
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "LegalEagleBot/1.0"
    }
    params = {
        "query": query,
        "max_results": 100,  # Max allowed per request
        "tweet.fields": "created_at,author_id,text"
    }
    
    print("📡 Making API call to /2/tweets/search/recent...")
    print(f"   Max results: {params['max_results']}")
    print()
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        print("✅ API Response:")
        print(f"   Status: {response.status_code} {response.reason}")
        print()
        
        # Parse rate limit headers
        rate_limit = format_rate_limit_info(response.headers)
        
        if response.status_code == 200:
            data = response.json()
            tweets = data.get("data", [])
            meta = data.get("meta", {})
            
            print(f"📰 Tweets Found: {len(tweets)}")
            print(f"   Result count: {meta.get('result_count', 0)}")
            print()
            
            if tweets:
                # Group tweets by author_id
                tweets_by_author = {}
                for tweet in tweets:
                    author_id = tweet.get("author_id", "unknown")
                    if author_id not in tweets_by_author:
                        tweets_by_author[author_id] = []
                    tweets_by_author[author_id].append(tweet)
                
                print("📊 Tweets by Author ID:")
                for author_id, author_tweets in tweets_by_author.items():
                    print(f"\n   Author ID: {author_id} ({len(author_tweets)} tweets)")
                    for i, tweet in enumerate(author_tweets[:3], 1):  # Show first 3
                        text = tweet.get("text", "")
                        date = tweet.get("created_at", "")
                        # Truncate long tweets
                        if len(text) > 80:
                            text = text[:77] + "..."
                        date_str = date.split("T")[0] if date else "?"
                        print(f"      {i}. [{date_str}] {text}")
                    if len(author_tweets) > 3:
                        print(f"      ... and {len(author_tweets) - 3} more")
                print()
            else:
                print("ℹ️  No tweets found in the last 7 days")
                print("   (Search endpoint only returns tweets from last 7 days)")
                print()
            
        elif response.status_code == 429:
            print("⚠️  Rate Limit Exceeded (429)")
            print("   You've hit the API rate limit for this endpoint")
            print()
        else:
            print(f"❌ Error Response:")
            try:
                error_data = response.json()
                print(f"   {error_data}")
            except Exception:
                print(f"   {response.text}")
            print()
        
        # Always show rate limit info
        print("📊 Rate Limit Status:")
        print(f"   Remaining: {rate_limit['remaining']} / {rate_limit['limit']}")
        print(f"   Resets: {rate_limit['reset']}")
        print()
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Exception during API call:")
        print(f"   {type(e).__name__}: {e}")
        print()
        return False


def main():
    print()
    success = test_twitter_search()
    print()
    print("=" * 60)
    if success:
        print("✅ Test completed successfully!")
        print()
        print("💡 Next Steps:")
        print("   1. Check the rate limit status above")
        print("   2. If successful, we can integrate this into the main pipeline")
        print("   3. This approach fetches ALL accounts in ONE API call")
    else:
        print("❌ Test failed. See error messages above.")
        print()
        print("💡 Common Issues:")
        print("   - Invalid Bearer Token")
        print("   - Rate limit exceeded (wait 15 minutes)")
        print("   - No tweets in last 7 days")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
