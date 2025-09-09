import os
import time
from openai import OpenAI
from dotenv import load_dotenv
from rss_parser import get_rss_items
from tweet_feed import tricky_tweet_feed

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def get_glossary():
    return (
        "Focus on topics related to labor contracts, iqama and visa, leaves, end of service, "
        "labor courts, social insurance (GOSI), health insurance, labor disciplinary and violations, remote work, "
        "part-time, working hours, Saudization or Nitaqat, Wage Protection, labor law, income tax, "
        "payroll, currency, data protection, data residency, service duration, calendar"
    )

def build_filter_prompt(glossary, content):
    return f"""
You are a legal policy analyst working in Human Capital Management (HCM). Your job is to assess whether the following news content is relevant to the HR domain based on this glossary of critical topics:

Glossary:
{glossary}

Content:
{content}

Please respond with only "Yes" if the content relates to one or more topics from the glossary, or "No" if it does not.
"""

def is_relevant(item):
    prompt = build_filter_prompt(get_glossary(), item["content"])
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip().lower()
        return "yes" in reply
    except Exception as e:
        print(f"❌ Failed to check relevance for item '{item['title']}': {e}")
        return False

def get_relevant_news(items):
    relevant = []
    for i, item in enumerate(items):
        print(f"🔍 Checking item {i+1}/{len(items)} → {item['title'][:80]}...")
        if is_relevant(item):
            relevant.append(item)
    return relevant

def filtered_news():
    print("🧠 Running News Filter Agent...")
    start = time.time()

    rss_items = get_rss_items()
    tweet_items = tricky_tweet_feed()
    all_items = rss_items + tweet_items
    print(f"📦 Total collected items: {len(all_items)}")

    relevant_items = get_relevant_news(all_items)
    print(f"✅ Relevant items after filtering: {len(relevant_items)}")
    print(f"⏱️ Done in {round(time.time() - start, 2)} seconds.\n")
    return relevant_items

if __name__ == "__main__":
    try:
        for item in filtered_news():
            print("📌", item, "\n")
    except Exception as e:
        print(f"💥 Script failed unexpectedly: {e}")
