# agents/news_filter.py

import os
from openai import OpenAI

# 🧠 Build filtering prompt dynamically from glossary categories
def build_filter_prompt(content, GLOSSARY):
    categories_text = "\n".join([f"- {k}: {v}" for k, v in GLOSSARY.items()])
    return f"""
You are a legal policy analyst. Classify the following news content into exactly ONE category
based on the glossary provided.

Glossary Categories:
{categories_text}

Content:
{content}

⚠️ Important instructions:
- Only classify as HCM or FIN if the content directly concerns those topics.
- Do NOT classify general political, diplomatic, international relations, cabinet meetings, 
  government reshuffles, foreign policy, or purely economic/trade deals as HCM or FIN.
- If the content is unrelated to HCM or FIN, classify it as OTHER.

Respond ONLY in strict JSON format:
{{ "category": "HCM" }}
{{ "category": "FIN" }}
{{ "category": "OTHER" }}
"""


# 🔍 Classify a single news item
def classify_item(item, OPENAI_API_KEY, GLOSSARY):
    prompt = build_filter_prompt(item["content"], GLOSSARY)
    client = OpenAI(api_key=OPENAI_API_KEY)
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
def get_relevant_news(all_news_items, OPENAI_API_KEY, GLOSSARY):
    relevant = []
    errors = []

    for item in all_news_items:
        result = classify_item(item, OPENAI_API_KEY, GLOSSARY)

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
