# lpm_agent.py
import os
import openai
import json
from filter_agent import get_relevant_news
from collections import defaultdict

# Load OpenAI API key from environment variables (GitHub secrets)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

def analyze_legal_impact(content):
    prompt = f"""
System = Your role is “SAP HCM Localization Product Manager for Saudi Arabia” who takes care of localizing SAP HCM products such as SuccessFactors for Saudi Arabia.
User = Your daily job is to follow up news in Saudi Arabia and see what is relevant for localization then assess the impact.
Input = We have these News: {content} from “Saudi Arabia” I need you to follow these instructions:

1. Categorize the news as one of: legal_change, new_law, event, workshop, statistical, other
2. If it's legal_change or new_law:
   a. Is it a new law or a change to existing one?
   b. Provide details using deep research from "trusted Saudi legal sources" provided below based on the authority in the news context.
   c. In case it is a chnage then find which articles were impacted by the changes and brief about each article.
   d. Assess impact on SAP SuccessFactors: Employee Central, Time Tracking, Payroll. The impact you assess should be based on statements written in the law article (not guessing)
3. Return a final result in JSON format with these fields:
   - html_analysis: Full analysis as HTML block with following 8 elements:
   (a) Short title of the news
   (b) Link to the news
   (c) Link to complete law
   (d) The authority issuing the law
   (e) Reference for “أمر ملكي” and “قرار مجلس الوزراء”
   (f) Publishing Date
   (g) Effective Date
   (h) Full analysis
   - category: One of legal_change, new_law, event, workshop, statistical, other
   - score: Confidence score from 1 to 10 (as a number)
4. "Trusted Saudi legal sources" (based on the authority in the news context) are:
- Ministry of Human Resources and Social Development = "https://www.hrsd.gov.sa/knowledge-centre/decisions-and-regulations/ministerial-decisions" AND "https://www.hrsd.gov.sa/knowledge-centre/decisions-and-regulations/regulation-and-procedures"
- Social Insurance GOSI = "https://www.gosi.gov.sa/ar/SystemsAndRegulations"
- Saudi Data & AI Authority (SDAIA) = "https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx"
- There are also general sources for all laws in Saudi Arabia BUT sometimes they are not up-to-date so don’t get any information from there unless it is the latest (very close to the news publishing date), these sources are:
"https://laws.boe.gov.sa/BoeLaws/Laws/Search" AND "https://saudipedia.com/en/ AND https://uqn.gov.sa/DecisionsAndSystems"

Use HTML formatting inside the "html_analysis" field only.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ]
        )
        result_str = response.choices[0].message.content.strip()
        try:
            result = json.loads(result_str)
        except json.JSONDecodeError as e:
            print("⚠️ JSON parsing failed. Raw output:\n", result_str)
            return {"category": "other", "html_analysis": f"<p>⚠️ Failed to parse JSON: {e}</p>", "score": 0}
        return result
    except Exception as e:
        return {"category": "other", "html_analysis": f"<p>❌ Failed to analyze: {e}</p>", "score": 0}
        
# ======= Sorting based on priority ========
def sort_and_concatenate(results):
    priority_order = ["legal_change", "law_event", "statistical", "other"]
    grouped = defaultdict(list)

    # Group by category
    for item in results:
        cat = item.get("category", "other")
        grouped[cat].append(item)

    # Sort within each category by score descending
    for cat in grouped:
        grouped[cat].sort(key=lambda x: x.get("score", 0), reverse=True)

    # Concatenate HTML in order
    final_html_output = ""
    for cat in priority_order:
        for item in grouped.get(cat, []):
            final_html_output += item.get("html_analysis", "") + "\n<hr/>\n"

    return final_html_output

# ======= Run against filtered news ========
if __name__ == "__main__":
    print("🔍 Running Legal Policy Manager Agent on filtered content...")
    filtered_news = get_relevant_news()
    results = []

    for item in filtered_news:
        print("📰 Input:", item)
        result = analyze_legal_impact(item)
        results.append(result)

    final_html = sort_and_concatenate(results)
    print("✅ Final Combined Analysis:")
    print(final_html)
