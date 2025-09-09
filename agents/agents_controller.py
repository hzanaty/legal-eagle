import os
import datetime
from agents.rss_parser import get_rss_items
from agents.tweet_feed import fetch_recent_tweets
from configurations.agents_config import AGENTS_CONFIG


def run_rss_parser():
    print("📡 Running RSS Parser Agent...")
    all_rss_items = []
    for url in AGENTS_CONFIG["rss_urls"]:
        print(f"🌐 Parsing RSS feed: {url}")
        rss_items = get_rss_items(url)
        all_rss_items.extend(rss_items)
    print(f"📦 Total RSS items collected: {len(all_rss_items)}\n")
    return all_rss_items


def run_tweet_feed():
    print("🐦 Running Tweet Feed Agent...")
    tweet_accounts = AGENTS_CONFIG["tweet_accounts"]
    total_accounts = len(tweet_accounts)

    # Use day of week (0 = Monday, 6 = Sunday) to select account
    today = datetime.datetime.utcnow().weekday()
    selected_index = today % total_accounts
    selected_account = list(tweet_accounts.items())[selected_index]  # (username, user_id)

    username, user_id = selected_account
    print(f"🗓️ Today is {datetime.date.today()} → Selected account: @{username}")

    tweets = fetch_recent_tweets(user_id, username)
    return tweets


if __name__ == "__main__":
    rss_items = run_rss_parser()
    tweet_items = run_tweet_feed()

    # Placeholder for combining and passing to next agent
    all_items = rss_items + tweet_items
    print(f"🧠 Combined items ready for filtering: {len(all_items)}")
