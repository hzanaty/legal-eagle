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
You are a legal policy analyst working in Human Capital Management (HCM). 
Your task is to assess whether the following news content is relevant to HR, Payroll, GOSI, or labor law topics 
based on this glossary of critical terms:

Glossary:
{glossary}

Content:
{content}

Respond ONLY in strict JSON format:
{{ "relevant": true }}   ← if related
{{ "relevant": false }}  ← if not related
"""

# 🔍 Check if a single news item is relevant
def is_relevant(item):
    prompt = build_filter_prompt(glossary, item["content"])
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # ⚡ faster + smarter
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json"}  # enforce JSON output
        )
        reply = response.choices[0].message.content.strip().lower()
        return '"true"' in reply
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
