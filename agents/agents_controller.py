# agents/agents_controller.py

from agents.rss_parser import get_rss_items
from agents.tweet_feed import tricky_tweet_feed
from agents.news_filter import get_relevant_news
from configurations.agents_config import rss_urls, tweet_accounts

from datetime import datetime

def collect_rss_news():
    all_rss_news = []
    for url in rss_urls:
        print(f"🌐 Fetching RSS from: {url}")
        all_rss_news.extend(get_rss_items(url))
    return all_rss_news

def collect_tweets():
    # Determine account to fetch based on the day (odd/even)
    today_day = datetime.utcnow().day
    sorted_accounts = sorted(tweet_accounts.items())
    selected_index = today_day % len(sorted_accounts)
    selected_name, selected_id = sorted_accounts[selected_index]

    print(f"🐦 Today is day {today_day} → Selected account: @{selected_name}")
    return tricky_tweet_feed(user_id=selected_id, username=selected_name)

def run_controller():
    print("\n🚀 Starting Controller Agent\n" + "-"*40)

    # Step 1: Fetch RSS items
    rss_news = collect_rss_news()

    # Step 2: Fetch Tweets
    tweet_news = collect_tweets()

    # Step 3: Merge and filter news
    all_news = rss_news + tweet_news
    print(f"\n📦 Total news items collected: {len(all_news)}")
    relevant_news = get_relevant_news(all_news)
    print(f"✅ Relevant news after filtering: {len(relevant_news)}\n")

    # Optional: preview output
    for item in relevant_news:
        print(f"📌 {item['title']}")
        print(f"📝 {item['summary']}")
        print(f"🔗 {item['link']}\n")

    return relevant_news

if __name__ == "__main__":
    run_controller()
