import os
import requests
from datetime import datetime, timedelta

# ========================
# Configuration
# ========================
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
username = "SaudiGOSI"  # Set the target Twitter username here

# ========================
# Helper Functions
# ========================
def get_user_id(username):
    print(f"🔍 Getting user ID for @{username}...")
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        user_id = response.json()["data"]["id"]
        print(f"✅ User ID for @{username} is {user_id}")
        return user_id
    else:
        print(f"❌ Failed to get user ID for {username}: {response.text}")
        return None

def fetch_recent_tweets(user_id):
    print("📅 Calculating time range for yesterday's tweets...")
    yesterday = datetime.utcnow() - timedelta(days=1)
    start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat("T") + "Z"
    print(f"⏱️ Start time: {start_time}")

    print("📥 Fetching tweets...")
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 10,
        "tweet.fields": "created_at,text",
        "start_time": start_time
    }
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        tweets = response.json().get("data", [])
        print(f"✅ {len(tweets)} tweet(s) retrieved.")
        return tweets
    else:
        print(f"❌ Failed to fetch tweets: {response.text}")
        return []

def fetch_all_tweets():
    print("🚀 Starting Tweet Feed Agent...")
    user_id = get_user_id(username)
    if not user_id:
        return []
    return fetch_recent_tweets(user_id)

# ========================
# Local Test Block
# ========================
if __name__ == "__main__":
    print(f"🧪 Testing Twitter API access for: @{username}")
    tweets = fetch_all_tweets()
    if tweets:
        print(f"📄 Printing {len(tweets)} tweet(s):\n")
        for tweet in tweets:
            print(f"🕒 {tweet['created_at']}")
            print(f"💬 {tweet['text']}\n")
    else:
        print("⚠️ No tweets found.")
