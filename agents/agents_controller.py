import datetime
from configurations.agents_config import RSS_FEED_URLS, TWEET_ACCOUNTS, MONITOR_URLS
from agents.rss_parser import parse_rss_feed
from agents.tweet_feed import fetch_recent_tweets
#from agents.url_monitor import scrape_all_monitor_urls
#from agents.news_filter import get_relevant_news
#from agents.news_grouper import group_similar_news
#from agents.email_sender import send_summary_email

def run_controller():
    print("🧠 Starting Legal Eagle Controller...\n")

    # 1. RSS Agent
    rss_items = []
    print("📰 Running RSS Parser Agent...")
    for url in RSS_FEED_URLS:
        rss_items.extend(parse_rss_feed(url))
    print(f"✅ Total RSS items collected: {len(rss_items)}\n")
    # Optional preview
    for item in rss_items[:5]:
        print("🔹 Title:", item["title"])
        print("🔗 Link:", item["link"])
        print("🗓️ Date:", item["date"])
        print("📄 Content:", item["content"][:100], "...\n")

    # 2. Tweet Feed Agent (daily rotation)
    today_index = datetime.datetime.utcnow().day % len(TWEET_ACCOUNTS)
    account_name, account_id = list(TWEET_ACCOUNTS.items())[today_index]
    tweet_items = fetch_recent_tweets(account_id, account_name)
    print(f"✅ Total tweets collected from @{account_name}: {len(tweet_items)}\n")

    # ===========================
    # 🔒 Other agents are skipped
    # ===========================

    # 3. URL Monitor Agent
    #print("🕵️‍♂️ Running URL Monitor Agent...")
    #url_items = scrape_all_monitor_urls()
    #print(f"✅ Total monitored site items collected: {len(url_items)}\n")

    # 4. Combine all items
    #all_news_items = rss_items + tweet_items + url_items
    #print(f"📦 Total collected items (pre-filter): {len(all_news_items)}\n")

    # 5. News Filter Agent
    #print("🧹 Filtering for relevance...")
    #filtered_items = get_relevant_news(all_news_items)
    #print(f"✅ Total relevant items after filtering: {len(filtered_items)}\n")

    # 6. News Grouper Agent
    #print("🧠 Grouping similar news items...")
    #grouped_summary = group_similar_news(filtered_items)
    #print(f"✅ Grouped summary ready with {len(grouped_summary)} entries.\n")

    # 7. Email Composer Agent
    #print("📧 Sending summary email...")
    #send_summary_email(grouped_summary)
    #print("✅ Email sent to stakeholders.\n")

if __name__ == "__main__":
    run_controller()
