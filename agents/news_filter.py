# agents/news_filter.py

import os
from openai import OpenAI
from dotenv import load_dotenv
from configurations.agents_config import GLOSSARY

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# 🧠 Build filtering prompt for the model
def build_filter_prompt(GLOSSARY, content):
    return f"""
You are a legal policy analyst working in Human Capital Management (HCM). 
Your task is to assess whether the following news content is relevant to HR, Payroll, GOSI, or labor law topics 
based on this GLOSSARY of critical terms:

GLOSSARY:
{GLOSSARY}

Content:
{content}

Respond ONLY in strict JSON format:
{{ "relevant": true }}   ← if related
{{ "relevant": false }}  ← if not related
"""

# 🔍 Check if a single news item is relevant
def is_relevant(item):
    prompt = build_filter_prompt(GLOSSARY, item["content"])
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # ⚡ faster + smarter
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        reply = response.choices[0].message.content.strip().lower()
        return '"true"' in reply
    except Exception as e:
        # Return False but include error details for controller if needed
        return {
            "error": True,
            "title": item.get("title", "Unknown"),
            "message": str(e)
        }

# ✅ Entry point: receives a list of items and filters only the relevant ones
def get_relevant_news(items):
    relevant = []
    errors = []

    for item in items:
        result = is_relevant(item)
        if isinstance(result, dict) and result.get("error"):  # error case
            errors.append(result)
        elif result:  # relevant = True
            relevant.append(item)

    return {
        "items": relevant,
        "errors": errors
    }
