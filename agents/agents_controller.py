import os
from agents.rss_parser import get_rss_items
from agents.tweet_feed import tricky_tweet_feed
from agents.news_filter import get_relevant_news
from agents.news_grouper import group_news_items
from configurations.agents_config import rss_sources, tweet_accounts
from datetime import datetime
from configurations.agents_config import MONITOR_URLS

def run_controller():
    print("🤖 Starting Legal Eagle Controller")

    # Step 1: Collect from all RSS sources
    all_rss = []
    for url in rss_sources:
        print(f"🔗 Reading RSS: {url}")
        items = get_rss_items(url)
        all_rss.extend(items)

    # Step 2: Fetch tweets from selected account based on date
    today = datetime.utcnow().day
    sorted_accounts = sorted(tweet_accounts.items())  # [(name, id), ...]
    selected = sorted_accounts[today % len(sorted_accounts)]
    account_name, account_id = selected
    print(f"🐦 Today is day {today} → Reading tweets from @{account_name}")
    tweet_items = tricky_tweet_feed(account_name, account_id)

    # Step 3: Filter relevant content
    all_items = all_rss + tweet_items
    print(f"📦 Total items collected: {len(all_items)}")
    relevant_items = get_relevant_news(all_items)
    print(f"✅ Filtered relevant items: {len(relevant_items)}")

    # Step 4: Group similar news items
    grouped_items = group_news_items(relevant_items)
    print(f"🧩 Grouped items: {len(grouped_items)}")

    # Preview grouped result
    for i, group in enumerate(grouped_items):
        print(f"\n🧵 Group {i+1}: {group['summary']}")
        for source in group['sources']:
            print(f"   • {source['title']} ({source['link']})")

if __name__ == "__main__":
    run_controller()
