# tweet_feed.py
import os
import requests
from datetime import datetime, timedelta

# Load your bearer token from GitHub Secrets
BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

# Set the target usernames (without the @)
TARGET_USERS = ["SaudiGOSI"]
YESTERDAY = (datetime.utcnow() - timedelta(days=1)).date().isoformat()

def create_headers(token):
    return {"Authorization": f"Bearer {token}"}

def get_user_id(username, headers):
    url = f"https://api.twitter.com/2/users/by/username/{username}"
    response = requests.get(url, headers=headers)
    return response.json().get("data", {}).get("id")

def get_yesterday_tweets(user_id, headers):
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": 20,
        "tweet.fields": "created_at",
        "exclude": "retweets,replies",
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"❌ Failed to fetch tweets: {response.text}")
        return []

    tweets = response.json().get("data", [])
    yesterday_tweets = [
        tweet for tweet in tweets
        if tweet["created_at"].startswith(YESTERDAY)
    ]
    return yesterday_tweets

def fetch_all_tweets():
    headers = create_headers(BEARER_TOKEN)
    all_tweets = []

    for username in TARGET_USERS:
        user_id = get_user_id(username, headers)
        if not user_id:
            print(f"❌ Failed to get user ID for {username}")
            continue

        tweets = get_yesterday_tweets(user_id, headers)
        if tweets:
            all_tweets.append(f"\n📌 Tweets from @{username} on {YESTERDAY}:")
            for tweet in tweets:
                all_tweets.append(f"- {tweet['text']}")

    return "\n".join(all_tweets)

# If you want to test locally
if __name__ == "__main__":
    result = fetch_all_tweets()
    print(result if result else "No tweets found.")
