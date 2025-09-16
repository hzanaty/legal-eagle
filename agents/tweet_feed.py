# agents/tweet_feed.py

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
print(f"🔐 Bearer Token used: {BEARER_TOKEN[:10]}...")  # print only first 10 chars for safety

def fetch_recent_tweets(user_id, username, max_results=5):
    print(f"📥 Fetching tweets for @{username}...")

    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": max_results,
        "tweet.fields": "created_at,text",
    }
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        tweets = response.json().get("data", [])
        print(f"✅ Retrieved {len(tweets)} tweet(s) from @{username}")

        tweet_items = []
        for tweet in tweets:
            created_at = tweet["created_at"]
            tweet_text = tweet["text"]
            tweet_id = tweet["id"]
            tweet_link = f"https://x.com/{username}/status/{tweet_id}"

            item = {
                "source": "Twitter",
                "title": f"Tweet from @{username}",
                "summary": tweet_text,
                "link": tweet_link,
                "date": created_at.split("T")[0],
                "content": f"{tweet_text}\n{tweet_link}\n{created_at}"
            }
            tweet_items.append(item)

        return tweet_items

    else:
        print(f"❌ Failed to fetch tweets for @{username}: {response.status_code} → {response.text}")
        return []
