import feedparser
import openai
import os

# Load API key from GitHub secrets
openai.api_key = os.getenv("OPENAI_API_KEY")

def summarize_text(text):
    prompt = f"Summarize the following news article in one line, using the same language:\n\n{text}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Failed to summarize: {e}"

def get_rss_summaries():
    rss_url = "https://saudigazette.com.sa/rssFeed/0"
    feed = feedparser.parse(rss_url)

    summaries = []
    for entry in feed.entries:
        title = entry.title
        link = entry.link
        description = entry.description
        pub_date = entry.published

        summary = summarize_text(description)

        article_html = f"""
        <p><strong>{title}</strong><br>
        <em>{pub_date}</em><br>
        {summary}<br>
        <a href="{link}">Read more</a></p>
        <hr>
        """
        summaries.append(article_html)

    html_output = f"<h2>📰 Daily News Summary</h2>{''.join(summaries)}"
    return html_output
