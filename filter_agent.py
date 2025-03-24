import os
from openai import OpenAI
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv("key.env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === Initialize OpenAI client ===
client = OpenAI(api_key=OPENAI_API_KEY)

# === Define your glossary of keywords ===
GLOSSARY = [
    "GOSI", "social insurance", "MOL", "HRSD", "visa fees", "article 77",
    "contract termination", "saudization", "termination", "repatriation",
    "labor law", "tickets", "iqama", "end of service", "vacation", "expat"
]

# === Build prompt dynamically ===
def build_prompt(text):
    glossary_text = ", ".join(GLOSSARY)
    return f"""
You are a legal assistant working in the domain of Human Capital Management (HCM) and localization.

The following is a glossary of keywords relevant to legal and policy updates:
{glossary_text}

Analyze the following content and answer with only YES or NO: 
Is the content relevant to the glossary topics?

Content:
{text}
"""

# === Check if text is relevant ===
def is_relevant(text):
    prompt = build_prompt(text)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content.strip().upper()
        return answer == "YES"
    except Exception as e:
        print(f"❌ Error checking relevance: {e}")
        return False

# === Example usage for local test ===
if __name__ == "__main__":
    sample_items = [
        "GOSI announces new policy on expat social insurance.",
        "Apple releases new iPhone 16 with titanium body.",
        "HRSD updates guidelines for Saudization compliance.",
        "Weather forecast for Riyadh shows heavy rain next week."
    ]

    print("🔎 Filtering relevant content...\n")
    for item in sample_items:
        relevant = is_relevant(item)
        print(f"✅ Relevant: {item}" if relevant else f"❌ Irrelevant: {item}")
