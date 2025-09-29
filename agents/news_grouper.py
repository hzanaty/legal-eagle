# agents/news_grouper.py

import os
from agents.news_filter import filtered_news
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)


def are_related(text1, text2):
    prompt = f"""
Are the following two news items about the same topic or event, even if written differently?

Text 1: {text1}
Text 2: {text2}

Reply with only "Yes" or "No".
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content.strip().lower()
        return "yes" in reply
    except Exception as e:
        print(f"⚠️ Failed similarity check: {e}")
        return False


def group_news(items):
    groups = []

    for item in items:
        matched = False
        for group in groups:
            if are_related(item["content"], group[0]["content"]):
                group.append(item)
                matched = True
                break
        if not matched:
            groups.append([item])

    return groups


def summarize_group(group):
    combined_text = "\n\n".join([item["content"] for item in group])
    prompt = f"""
Summarize the following related news items in 2–3 concise sentences. 
Focus on the legal/HR significance and avoid redundancy.

{combined_text}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Failed to summarize group: {e}")
        return "⚠️ Summary not available."


def format_group_output(group, summary):
    return {
        "summary": summary,
        "titles": [item["title"] for item in group],  # quick reference
        "links": [item["link"] for item in group],   # all sources preserved
        "items": group,                              # keep full details
        "group_size": len(group),
        "date_grouped": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


def group_and_summarize_news():
    relevant_items = filtered_news()
    groups = group_news(relevant_items)
    result = []

    for group in groups:
        summary = summarize_group(group)
        result.append(format_group_output(group, summary))

    return result
