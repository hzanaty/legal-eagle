import datetime
print("✅ Agent controller is starting...")

from configurations.agents_config import RSS_FEED_URLS, TWEET_ACCOUNTS, MONITOR_URLS, EMAIL_RECEIVERS
from configurations.config_loader import creds
print("✅ Config and creds imported")

from agents.rss_parser import parse_rss_feed
from agents.tweet_feed import fetch_recent_tweets
from agents.url_monitor import scrape_all_monitor_urls
from agents.news_filter import get_relevant_news
from agents.news_grouper import group_and_summarize_news
from agents.email_sender import send_email

def run_controller():
    print("🧠 Starting Legal Eagle Controller...\n")

    # --- Credentials loaded once here ---
    OPENAI_API_KEY = creds["openai_api_key"]
    X_BEARER_TOKEN = creds["twitter"]["x_bearer_token"]
    GMAIL_CREDS = creds["gmail"]

    # 1. RSS Agent
    rss_items = []
    print("📰 Running RSS Parser Agent...")
    for url in RSS_FEED_URLS:
        items = parse_rss_feed(url)
        rss_items.extend(items)
    print(f"✅ Total RSS items collected: {len(rss_items)}")

    for item in rss_items:
        print(f"\n🔹 Title: {item['title']}")
        print(f"🔗 Link: {item['link']}")
        print(f"🗓️ Date: {item['date']}")
        print(f"📄 Content: {item['content']}\n")

    # 2. Tweet Feed Agent (daily rotation)
    today_index = datetime.datetime.utcnow().day % len(TWEET_ACCOUNTS)
    account_name = TWEET_ACCOUNTS[today_index]
    print(f"\n🐦 Running Tweet Feed Agent for @{account_name}...")
    tweet_items = fetch_recent_tweets(account_name, X_BEARER_TOKEN)

    if isinstance(tweet_items, dict) and tweet_items.get("error"):
        print(f"❌ Tweet fetch failed for @{account_name}: {tweet_items}")
        tweet_items = []
    print(f"✅ Total tweets collected from @{account_name}: {len(tweet_items)}")

    for tweet in tweet_items:
        print(f"\n🔹 Title: {tweet['title']}")
        print(f"🔗 Link: {tweet['link']}")
        print(f"🗓️ Date: {tweet['date']}")
        print(f"📄 Content: {tweet['content']}\n")

    # 3. URL Monitor Agent
    print("\n🕵️‍♂️ Running URL Monitor Agent...")
    url_result = scrape_all_monitor_urls(MONITOR_URLS)
    url_items = url_result.get("items", [])
    url_errors = url_result.get("errors", [])

    print(f"✅ Total monitored site items collected: {len(url_items)}")
    if url_errors:
        print(f"⚠️ {len(url_errors)} errors while scraping:")
        for err in url_errors:
            print(f"   - {err}")

    for item in url_items:
        print(f"\n🔹 Title: {item['title']}")
        print(f"🔗 Link: {item['link']}")
        print(f"🗓️ Date: {item['date']}")
        print(f"📄 Content:\n{item['content']}\n")
        print("=" * 60)

    # 4. Combine all items
    all_news_items = rss_items + tweet_items + url_items
    print(f"\n📦 Total collected items (pre-filter): {len(all_news_items)}")

    # 5. News Filter Agent
    print("\n🧹 Filtering for relevance...")
    filter_result = get_relevant_news(all_news_items, OPENAI_API_KEY)
    filtered_items = filter_result.get("items", [])
    filter_errors = filter_result.get("errors", [])

    print(f"✅ Relevant items after filtering: {len(filtered_items)}")
    if filter_errors:
        print(f"⚠️ {len(filter_errors)} filtering errors:")
        for err in filter_errors:
            print(f"   - {err}")

    for item in filtered_items:
        print(f"\n🔹 Title: {item['title']}")
        print(f"🔗 Link: {item['link']}")
        print(f"🗓️ Date: {item['date']}")
        print(f"📄 Content: {item['content']}\n")

    # 6. News Grouper Agent
    print("\n🧠 Grouping similar news items...")
    grouped_summary = group_and_summarize_news(filtered_items, OPENAI_API_KEY)
    print(f"✅ Grouped summary ready with {len(grouped_summary)} entries.")

    for i, group in enumerate(grouped_summary, 1):
        category = group.get("category", "Uncategorized")
        print(f"\n📚 Group {i} ({category}, {group['group_size']} items)")
        print(f"📝 Summary: {group['summary']}")
        print("🔗 Sources:")
        for link in group["links"]:
            print(f"   - {link}")

    # 7. Email Composer Agent
    print("📧 Sending summary email...")
    subject = "🦅 Legal Eagle Daily Digest"
    body = build_email_body(grouped_summary)
    send_email(
        sender="hanyzanaty@gmail.com", 
        receivers=EMAIL_RECEIVERS,
        subject=subject,
        body=body,
        gmail_creds=GMAIL_CREDS
    )
    print("✅ Email sent to stakeholders.\n")

if __name__ == "__main__":
    run_controller()
