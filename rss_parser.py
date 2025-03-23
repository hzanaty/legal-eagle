import feedparser
import openai
import os

# === Load OpenAI API Key ===
openai.api_key = os.getenv("OPENAI_API_KEY")

# === RSS Feed URL ===
RSS_FEED_URL = "https://saudigazette.com.sa/rssFeed/0"

# === Summarize with OpenAI ===
def summarize_text(text):
    prompt = f"Summarize the following news article in one simple line using same language used in the article:\n\n{text}"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Failed to summarize: {e}")
        return "⚠️ Summary unavailable."

# === Parse and summarize RSS ===
def get_rss_summaries():
    feed = feedparser.parse(RSS_FEED_URL)
    summaries = []

    for entry in feed.entries:
        title = entry.get("title", "No Title")
        link = entry.get("link", "#")
        description = entry.get("description", "No Description")
        pub_date = entry.get("published", "No Date")

        print(f"🔎 Summarizing: {title}")
        summary = summarize_text(description)

        article_html = f"""
        <p><strong>{title}</strong> <br/>
        📅 {pub_date} <br/>
        🔗 <a href="{link}">Read more</a> <br/>
        📝 {summary}</p>
        <hr/>
        """
        summaries.append(article_html)

    return "\n".join(summaries)
