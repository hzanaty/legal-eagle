import feedparser
import os
from openai import OpenAI
from openai import OpenAIError

# Load OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

RSS_FEED_URL = "https://saudigazette.com.sa/rssFeed/0"

def summarize_text(text):
    prompt = f"Summarize the following news article in one simple line using same language used in the article:\n\n{text}"
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except OpenAIError as e:
        print(f"❌ Failed to summarize: {e}")
        return "⚠️ Summary unavailable."

def get_rss_summaries():
    feed = feedparser.parse(RSS_FEED_URL)
    summaries = []

    for entry in feed.entries:
        title = entry.title
        link = entry.link
        description = entry.get("description", "")
        pub_date = entry.get("published", "")
        summary = summarize_text(description)
        summaries.append(f"<b>{title}</b><br>{summary}<br><a href='{link}'>Read more</a><br><i>{pub_date}</i><br><br>")

    return "".join(summaries)
