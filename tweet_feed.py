# tweet_feed.py

import os
import requests
from datetime import datetime
import time

# ========================
# Configuration
# ========================
BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
users = {
    "SaudiGOSI": "877253528",
    "HRSD_SA": "880244007258562560"
}

# ========================
# Helper Functions
# ========================
def fetch_recent_tweets(user_id, username):
    print(f"📥 Fetching tweets for @{username}...")
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 5,
        "tweet.fields": "created_at,text",
        # you can add filtering later if needed
    }
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        tweets = response.json().get("data", [])
        print(f"✅ Retrieved {len(tweets)} tweet(s) from @{username}")
        return [
            f"🕒 {datetime.strptime(tweet['created_at']}<br>💬 {tweet['text']}<br>🔗 https://x.com/{username}/status/{tweet['id']}<br><br>"
            for tweet in tweets
        ]
    else:
        print(f"❌ Failed to fetch tweets for @{username}: {response.text}")
        return []

# ========================
# Main Crazy Algorithm
# ========================
def crazy_tweet_agent():
    print("🌀 Starting CRAZY Tweet Feed Agent...")
    today = datetime.utcnow().day
    selected_user = "HRSD_SA" if today % 2 != 0 else "SaudiGOSI"
    user_id = users[selected_user]
    print(f"🗓️ Today is {'odd' if today % 2 != 0 else 'even'} → Picking @{selected_user}")
    return fetch_recent_tweets(user_id, selected_user)

# ========================
# Local test block
# ========================
if __name__ == "__main__":
    print("🧪 Running local tweet test...")
    tweets = crazy_tweet_agent()
    if tweets:
        print("📄 Tweets:\n")
        for tweet in tweets:
            print(tweet)
    else:
        print("⚠️ No tweets found.")
