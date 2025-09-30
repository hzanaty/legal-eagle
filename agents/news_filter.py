# agents/news_filter.py

import os
from openai import OpenAI
from dotenv import load_dotenv
from configurations.agents_config import GLOSSARY

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)


# 🧠 Build filtering prompt dynamically from glossary categories
def build_filter_prompt(glossary, content):
    categories_text = "\n".join([f"- {k}: {v}" for k, v in glossary.items()])
    return f"""
You are a legal policy analyst. Classify the following news content into exactly ONE category
based on the glossary provided.

Glossary Categories:
{categories_text}

Content:
{content}

Respond ONLY in strict JSON format:
{{ "category": "HCM" }}
{{ "category": "FIN" }}
{{ "category": "OTHER" }}
"""


# 🔍 Classify a single news item
def classify_item(item):
    prompt = build_filter_prompt(GLOSSARY, item["content"])
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}  # ✅ enforce structured JSON
        )
        reply = response.choices[0].message.content.strip()

        # Expected reply: { "category": "HCM" } or FIN / OTHER
        if '"HCM"' in reply:
            return {"category": "HCM"}
        elif '"FIN"' in reply:
            return {"category": "FIN"}
        else:
            return {"category": "OTHER"}

    except Exception as e:
        return {
            "error": True,
            "title": item.get("title", "Unknown"),
            "message": str(e)
        }


# ✅ Entry point: classify and filter items
def get_relevant_news(items):
    relevant = []
    errors = []

    for item in items:
        result = classify_item(item)

        if isinstance(result, dict) and result.get("error"):
            errors.append(result)
        else:
            category = result["category"]
            if category in ["HCM", "FIN"]:  # drop OTHER
                item["category"] = category
                relevant.append(item)

    return {
        "items": relevant,
        "errors": errors
    }
