import feedparser

RSS_FEED_URL = "https://saudigazette.com.sa/rssFeed/74"

def get_rss_items():
    print("🌐 Fetching RSS feed...")
    feed = feedparser.parse(RSS_FEED_URL)

    if not feed.entries:
        print("⚠️ No entries found in the RSS feed.")
        return []

    rss_items = []
    print(f"📄 Found {len(feed.entries)} items in the RSS feed.")

    for i, entry in enumerate(feed.entries):
        title = entry.title
        link = entry.link
        description = entry.get("description", "")
        pub_date = entry.get("published", "")

        item = {
            "source": "RSS",
            "title": title,
            "summary": description,
            "link": link,
            "date": pub_date,
            "content": f"{title}\n{description}\n{link}\n{pub_date}"
        }

        print(f"📰 Item {i+1}: {title}")
        rss_items.append(item)

    print(f"✅ Total parsed RSS items: {len(rss_items)}")
    return rss_items
