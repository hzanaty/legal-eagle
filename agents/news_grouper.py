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
            model="gpt-4o",
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
    prompt = f"Summarize the following related news items in 2-3 concise sentences:\n\n{combined_text}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Failed to summarize group: {e}")
        return "⚠️ Summary not available."


def format_group_output(group, summary):
    return {
        "summary": summary,
        "items": group,
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


if __name__ == "__main__":
    grouped_results = group_and_summarize_news()
    print(f"📦 Total Groups Formed: {len(grouped_results)}")

    for i, group in enumerate(grouped_results, 1):
        print(f"\n📚 Group {i} ({group['group_size']} items)")
        print(f"📝 Summary: {group['summary']}")
        for item in group["items"]:
            print(f"🔗 {item['title']} — {item['link']}")
