# filter_agent.py

import openai
import os

# === Load OpenAI Key ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# === Glossary of Relevant Topics ===
GLOSSARY = """
Glossary of Relevant Topics:
- Labor Law
- Saudization (Nitaqat)
- Social Insurance (GOSI)
- HR regulations and policies
- Wage protection
- Iqama, work visa, and expat employment
- Employment contracts and termination rules
- Vacation, leave, overtime
- Payroll changes and contributions
- Any legal or government updates affecting employees or employers in Saudi Arabia
"""

# === Prompt Builder with Glossary ===
def build_prompt(content):
    return f"""
You are a legal policy analyst for HR in Saudi Arabia.

{GLOSSARY}

The following content may or may not relate to one of the above topics.

Your task is to check if the content is **relevant** to the glossary above.

Answer with "Yes" or "No".

Content:
\"\"\"
{content}
\"\"\"

Is this content relevant?
"""

# === Relevance Checker ===
def is_relevant(content):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You filter HR and legal content for relevance."},
                {"role": "user", "content": build_prompt(content)}
            ]
        )
        result = response.choices[0].message.content.strip().lower()
        return result.startswith("yes")
    except Exception as e:
        print(f"❌ Failed to filter content: {e}")
        return False

# === Main Filtering Function ===
def filter_relevant_items(items):
    print("🔎 Filtering relevant content...")
    relevant_items = []

    for item in items:
        print(f"🧾 Evaluating: {item[:100]}...")  # Print preview
        if is_relevant(item):
            print("✅ Marked as relevant.")
            relevant_items.append(item)
        else:
            print("❌ Irrelevant.")
    return relevant_items

# === Local Test ===
if __name__ == "__main__":
    sample_inputs = [
        "The Saudi GOSI introduced new parameters to calculate pension eligibility.",
        "Football match results from the Saudi Pro League.",
        "A new regulation requires employers to cover repatriation costs for expats upon contract termination.",
        "Weather in Riyadh expected to hit 45°C this week."
    ]

    relevant = filter_relevant_items(sample_inputs)

    print("\n🎯 Relevant Content Found:")
    for r in relevant:
        print(f"- {r}")
