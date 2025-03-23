# rss_parser.py
import feedparser
import openai
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

RSS_FEED_URL = "https://saudigazette.com.sa/rssFeed/0"

def summarize_text(text):
    prompt = f"Summarize the following news article in one simple line using same language used in the article:\n\n{text}"
    try:
        response = openai.chatcompletions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Failed to summarize: {e}")
        return "⚠️ Summary unavailable."

def get_rss_summaries():
    feed = feedparser.parse(RSS_FEED_URL)
    articles = feed.entries
    html = "<h2>📰 Saudi Gazette Headlines</h2><ul>"

    for entry in articles:
        title = entry.get("title", "No title")
        link = entry.get("link", "#")
        description = entry.get("description", "")
        pub_date = entry.get("published", "")

        summary = summarize_text(description)
        html += f"<li><strong>{title}</strong> ({pub_date})<br>"
        html += f"{summary}<br><a href='{link}'>Read more</a></li><br>"

    html += "</ul>"
    return html
