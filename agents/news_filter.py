# agents/news_filter.py

import os
from openai import OpenAI
from dotenv import load_dotenv
from configurations.agents_config import glossary

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# 🧠 Build filtering prompt for the model
def build_filter_prompt(glossary, content):
    return f"""
You are a legal policy analyst working in Human Capital Management (HCM). Your job is to assess whether the following news content is relevant to the HR domain based on this glossary of critical topics:

Glossary:
{glossary}

Content:
{content}

Please respond with only "Yes" if the content relates to one or more topics from the glossary, or "No" if it does not.
"""

# 🔍 Check if a single news item is relevant
def is_relevant(item):
    prompt = build_filter_prompt(glossary, item["content"])
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip().lower()
        return "yes" in reply
    except Exception as e:
        print(f"❌ Failed to check relevance for item '{item.get('title', '')}': {e}")
        return False

# ✅ Entry point: receives a list of items and filters only the relevant ones
def get_relevant_news(items):
    relevant = []
    for i, item in enumerate(items):
        print(f"🔍 Checking item {i+1}/{len(items)} → {item['title'][:80]}...")
        if is_relevant(item):
            relevant.append(item)
    return relevant

# 🧪 For standalone testing
if __name__ == "__main__":
    print("⚠️ This agent must be called from the controller with a list of items.")
