# === rss_parser.py ===
# This script handles only RSS parsing and OpenAI summarization

import feedparser
import openai
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === Function to summarize using OpenAI ===
def summarize_text(text):
    openai.api_key = OPENAI_API_KEY
    prompt = f"Summarize the following news article in one simple line using same language used in the article:\n\n{text}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ OpenAI Error: {e}")
        return "Summary failed."

# === Parse RSS feed ===
def fetch_and_summarize_articles():
    feed_url = "https://saudigazette.com.sa/rssFeed/0"
    feed = feedparser.parse(feed_url)
    all_summaries = []

    for entry in feed.entries:
        title = entry.title
        link = entry.link
        description = entry.description
        summary = summarize_text(description)
        all_summaries.append(f"<b>{title}</b><br>{summary}<br><a href='{link}'>{link}</a><br><br>")

    return all_summaries

if __name__ == "__main__":
    summaries = fetch_and_summarize_articles()
    for item in summaries:
        print(item)
