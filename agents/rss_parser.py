import feedparser

def parse_rss_feed(url):
    feed = feedparser.parse(url)
    rss_items = []

    for entry in feed.entries:
        title = entry.title
        link = entry.link
        description = entry.get("description", "")
        pub_date = entry.get("published", "")
        summary = description  # or later you can add GPT summarization

        guid = entry.get("id") or entry.get("guid") or None
        item = {
            "source": "RSS",
            "source_type": "RSS",
            "title": title,
            "summary": summary,
            "link": link,
            "date": pub_date,
            "guid": guid,
            "content": f"{title}\n{summary}\n{link}\n{pub_date}"
        }
        rss_items.append(item)
    #print(f"✅ {len(items)} items fetched from {rss_url}")
    return rss_items
