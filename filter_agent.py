import os
from openai import OpenAI
from rss_parser import get_rss_items
from tweet_feed import tricky_tweet_feed
from dotenv import load_dotenv
import time
 
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def get_glossary():
    return (
        "Focus on topics related to labor contracts, iqama and visa, leaves, end of service, "
        "labor courts, social insurance (GOSI), labor disciplinary and violations, remote work, "
        "part-time, working hours, Saudization or Nitaqat, Wage Protection, labor law, income tax, "
        "paytoll, currency, data protection, data residency, service duration, calendar"
    )

def build_filter_prompt(glossary, content):
    return f"""
You are a legal policy analyst working in Human Capital Management (HCM). Your job is to assess whether the following news content is relevant to the HR domain based on this glossary of critical topics:

Glossary:
{glossary}

Content:
""" + content + """

Please respond with only "Yes" if the content relates to one or more topics from the glossary, or "No" if it does not.
"""

def is_relevant(text):
    glossary = get_glossary()
    prompt = build_filter_prompt(glossary, text)
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip().lower()
        return "yes" in reply
    except Exception as e:
        print(f"❌ Failed to check relevance: {e}")
        return False

def are_semantically_duplicate(text1, text2):
    prompt = f"""
Are the following two news snippets conveying the same or highly similar meaning, even if phrased differently?

Text 1: {text1}
Text 2: {text2}

Reply with only "Yes" or "No".
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip().lower()
        return "yes" in reply
    except Exception as e:
        print(f"❌ Failed to compare for duplication: {e}")
        return False

def remove_semantic_duplicates(items):
    unique_items = []
    for item in items:
        duplicate = False
        for existing in unique_items:
            if are_semantically_duplicate(item, existing):
                duplicate = True
                break
        if not duplicate:
            unique_items.append(item)
    return unique_items

def get_relevant_news(items):
    relevant = []
    for i, item in enumerate(items):
        print(f"🔍 Checking item {i+1}/{len(items)}...")
        try:
            if is_relevant(item["content"]):
                relevant.append(item["content"])
        except Exception as e:
            print(f"❌ Failed to filter item {i+1}: {e}")
    return relevant

def filtered_news():
    print("📡 Collecting items from RSS and Twitter...")
    rss_items = get_rss_items()
    tweet_items = tricky_tweet_feed()
    all_items = rss_items + tweet_items
    print(f"📦 Total items before deduplication: {len(all_items)}")

    start = time.time()
    unique_items = remove_semantic_duplicates(all_items)
    print(f"🧹 Deduplication done in {round(time.time() - start, 2)}s")

    start = time.time()
    relevant_items = get_relevant_news(unique_items)
    print(f"✅ Relevant items after filtering: {len(relevant_items)}")
    print(f"⏱️ Relevance filtering done in {round(time.time() - start, 2)}s")

    return relevant_items

if __name__ == "__main__":
    try:
        final_news = collect_and_filter_news()
        for item in final_news:
            print("📌", item, "\n")
    except Exception as e:
        print(f"💥 Script failed unexpectedly: {e}")

    except Exception as e:
        print(f"💥 Script failed unexpectedly: {e}")
