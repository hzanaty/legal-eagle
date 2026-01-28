from openai import OpenAI
from datetime import datetime
import json


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


def format_update_output(update_item, category):
    """
    Create a single-entry group dict for an Update item with delta bullets.
    """
    title = f"Update: {update_item.get('title') or 'Untitled'}"
    # Build summary from delta lines (if available)
    delta_lines = update_item.get("delta") or []
    if delta_lines:
        # Join as plain text; email renderer may enhance with bullets
        summary = "\n".join([f"- {d}" for d in delta_lines])
    else:
        summary = update_item.get("content", "") or ""
    group = [update_item]
    return {
        "title": title,
        "summary": summary,
        "category": category,
        "titles": [update_item.get("title") or "Untitled"],
        "links": [update_item.get("link") or update_item.get("url") or ""],
        "items": group,
        "group_size": 1,
        "date_grouped": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "is_update_section": True,
        "delta": delta_lines,
    }


def group_and_summarize_news(items, OPENAI_API_KEY, LANGUAGE_PREFERENCE):
    """
    Orchestrates grouping + summarization for already filtered items.
    Produces separate sections per category: New (grouped by similarity) and Updates (one per item with deltas).
    HCM groups appear first, then FIN, then others.
    """
    results = []
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Split items by category and by update flag
    new_by_cat = {}
    upd_by_cat = {}
    for item in items:
        cat = item.get("category", "OTHER")
        if item.get("is_update"):
            upd_by_cat.setdefault(cat, []).append(item)
        else:
            new_by_cat.setdefault(cat, []).append(item)

    ordered_categories = ["HCM", "FIN"] + [
        c for c in set(list(new_by_cat.keys()) + list(upd_by_cat.keys())) if c not in ["HCM", "FIN"]
    ]

    for category in ordered_categories:
        # 1) New items: group via LLM-based relatedness
        if category in new_by_cat:
            grouped = group_news(new_by_cat[category], client)
            for group in grouped:
                data = summarize_group(group, client, LANGUAGE_PREFERENCE)
                title = data.get("title", "Untitled Group")
                summary = data.get("summary", "")
                entry = format_group_output(group, summary, category, title)
                entry["is_update_section"] = False
                results.append(entry)

        # 2) Updates: one entry per update item with delta bullets
        if category in upd_by_cat:
            for upd in upd_by_cat[category]:
                results.append(format_update_output(upd, category))

    return results
