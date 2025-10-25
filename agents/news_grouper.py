from openai import OpenAI
from datetime import datetime


def are_related(text1, text2, client: OpenAI):
    """Uses LLM to check if two texts refer to the same event."""
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


def group_news(items, client: OpenAI):
    """Groups related items together (within a single category)."""
    groups = []
    for item in items:
        matched = False
        for group in groups:
            result = are_related(item["content"], group[0]["content"], client)
            if isinstance(result, dict) and result.get("error"):
                continue
            if result:  # if "yes"
                group.append(item)
                matched = True
                break
        if not matched:
            groups.append([item])
    return groups


def summarize_group(group, client: OpenAI, LANGUAGE_PREFERENCE):
    """Summarizes all content in a group into 2–3 concise sentences."""
    combined_text = "\n\n".join([item["content"] for item in group])
    prompt = f"""
Summarize the following related news items in 2–3 concise sentences.
Focus on the legal/HR/Finance significance and avoid redundancy.
Write the summary in {LANGUAGE_PREFERENCE}.
Do NOT translate if the text is already in {LANGUAGE_PREFERENCE}, and do not distort the meaning.

Return your answer strictly as JSON with this format:
{{
  "title": "...",
  "summary": "..."
}}

News items:

{combined_text}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}  # ✅ structured output
        )
        reply = response.choices[0].message.content.strip()
        data = {}
        try:
            data = json.loads(reply)
        except Exception:
            # fallback: if not JSON, treat entire text as summary
            data["title"] = "Untitled Group"
            data["summary"] = reply
        return data
    except Exception as e:
        return {
            "title": "⚠️ Summary Error",
            "summary": f"Summary not available. Error: {e}"
        }

def format_group_output(group, summary, category, title):
    """Formats grouped items with metadata and summary."""
    return {
        "title": title,
        "summary": summary,
        "category": category,   # ✅ preserve HCM/FIN
        "titles": [item["title"] for item in group],
        "links": [item["link"] for item in group],
        "items": group,
        "group_size": len(group),
        "date_grouped": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


def group_and_summarize_news(items, OPENAI_API_KEY, LANGUAGE_PREFERENCE):
    """
    Orchestrates grouping + summarization for already filtered items.
    Groups are formed separately per category (HCM, FIN).
    HCM groups always appear first, followed by FIN, then others.
    """
    results = []
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Split items by category
    categories = {}
    for item in items:
        cat = item.get("category", "OTHER")
        categories.setdefault(cat, []).append(item)

    # Process categories in preferred order
    ordered_categories = ["HCM", "FIN"] + [
        c for c in categories.keys() if c not in ["HCM", "FIN"]
    ]

    for category in ordered_categories:
        if category not in categories:
            continue
        grouped = group_news(categories[category], client)
        for group in grouped:
            data = summarize_group(group, client, LANGUAGE_PREFERENCE)
            title = data.get("title", "Untitled Group")
            summary = data.get("summary", "")
            results.append(format_group_output(group, summary, category, title))

    return results
