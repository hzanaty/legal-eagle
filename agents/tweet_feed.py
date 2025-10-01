# agents/tweet_feed.py

import os
import requests
from dotenv import load_dotenv

load_dotenv()  # Load .env when running locally

X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

if not BEARER_TOKEN:
    raise ValueError("❌ Missing X_BEARER_TOKEN in environment variables.")


def fetch_recent_tweets(username, bearer_token, max_results=10):
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    params = {
        "query": f"from:{username}",
        "max_results": max_results,
        "tweet.fields": "created_at,text"
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        tweets = response.json().get("data", [])

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
        # Return structured error info for controller to handle/log
        return {
            "error": True,
            "status_code": response.status_code,
            "message": response.text,
            "username": username
        }
