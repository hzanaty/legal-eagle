import feedparser
from datetime import datetime

from agents.date_filter import parse_date_string

def parse_rss_feed(url):
    feed = feedparser.parse(url)
    rss_items = []
    skipped_no_date = 0

    for entry in feed.entries:
        title = entry.title
        link = entry.link
        description = entry.get("description", "")
        pub_date = entry.get("published", "")
        summary = description  # or later you can add GPT summarization

        # Normalise the publication date to ISO-8601 so the date filter (which
        # only understands ISO / YYYY-MM-DD) can compare it. feedparser exposes
        # a parsed struct_time for RFC822 pubDates; fall back to the raw string.
        pub_iso = pub_date
        parsed = entry.get("published_parsed")
        if parsed:
            try:
                pub_iso = datetime(*parsed[:6]).isoformat()
            except Exception:
                pub_iso = pub_date

        # Publish date is required — reject items whose date is missing or unparseable
        # (a publish date is a crucial piece of info; we do not capture undated news).
        if parse_date_string(pub_iso) is None:
            skipped_no_date += 1
            print(f'❌ RSS: skipped item — no/invalid publish date: "{title}"')
            continue

        guid = entry.get("id") or entry.get("guid") or None
        item = {
            "source": "RSS",
            "source_type": "RSS",
            "title": title,
            "summary": summary,
            "link": link,
            "date": pub_iso,
            "guid": guid,
            "feed_url": url,  # v3.1: trace item back to its feed for attribution
            "content": f"{title}\n{summary}\n{link}\n{pub_date}"
        }
        rss_items.append(item)
    if skipped_no_date:
        print(f"❌ RSS: rejected {skipped_no_date} item(s) with missing/invalid publish date from {url}")
    #print(f"✅ {len(items)} items fetched from {rss_url}")
    return rss_items
