# agents/news_grouper.py

import os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)


def are_related(text1, text2):
    """
    Uses LLM to check if two texts refer to the same event.
    """
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
        return {"error": True, "message": f"Similarity check failed: {e}"}


def group_news(items):
    """
    Groups related items together.
    """
    groups = []

    for item in items:
        matched = False
        for group in groups:
            result = are_related(item["content"], group[0]["content"])
            if isinstance(result, dict) and result.get("error"):
                # if similarity check failed, skip gracefully
                continue
            if result:  # if "yes"
                group.append(item)
                matched = True
                break
        if not matched:
            groups.append([item])

    return groups


def summarize_group(group):
    """
    Summarizes all content in a group into 2–3 concise sentences.
    """
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
        return f"⚠️ Summary not available. Error: {e}"


def format_group_output(group, summary):
    """
    Formats grouped items with metadata and summary.
    """
    return {
        "summary": summary,
        "titles": [item["title"] for item in group],
        "links": [item["link"] for item in group],
        "items": group,
        "group_size": len(group),
        "date_grouped": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


def group_and_summarize_news(items):
    """
    Orchestrates grouping + summarization for already filtered items.
    """
    groups = group_news(items)
    result = []

    for group in groups:
        summary = summarize_group(group)
        result.append(format_group_output(group, summary))

    return result
