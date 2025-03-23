import feedparser
import openai
import os

# Load OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

RSS_FEED_URL = "https://saudigazette.com.sa/rssFeed/0"

def summarize_text(text):
    prompt = f"Summarize the following news article in one simple line using same language used in the article:\n\n{text}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Failed to summarize: {e}")
        return "⚠️ Summary unavailable."

def get_rss_summaries():
    feed = feedparser.parse(RSS_FEED_URL)
    summaries = []

    for entry in feed.entries:
        title = entry.title
        link = entry.link
        description = entry.description
        pub_date = entry.published

        summary = summarize_text(description)

        summaries.append(f"<p><b>{title}</b><br><i>{pub_date}</i><br>{summary}<br><a href='{link}'>Read more</a></p>")

    return "<hr>".join(summaries)
