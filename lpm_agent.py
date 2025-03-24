# lpm_agent.py
import os
import openai
from filter_agent import get_relevant_news

# Load OpenAI API key from environment variables (GitHub secrets)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

def analyze_legal_impact(content):
    prompt = f"""
System = Your role is “SAP HCM Localization Product Manager for Saudi Arabia” who takes care of localizing SAP HCM products such as SuccessFactors for Saudi Arabia.
User = Your daily job is to follow up news in Saudi Arabia and see what is relevant for localization
Input = We have this news from “Saudi Arabia” {content} I need you to do the following:

(1) Categorize the news, is it related to law/regulation, or event, or statistical
(2) if it is related to law/regulation then tell me if this is about issuing a new law or changing existing law
(3) In case it is new law/regulation then use the "deep research"  and get me the following info:
(a) Name of the law
(b) Link to complete law
(c) The authority issuing the law
(d) Reference for “أمر ملكي” and “قرار مجلس الوزراء”
(e) Publishing Date
(f) Effective Date
Search in the following portals (based on the authority in the news context) to get the above information:
- Ministry of Human Resources and Social Development = https://www.hrsd.gov.sa/knowledge-centre/decisions-and-regulations/ministerial-decisions AND https://www.hrsd.gov.sa/knowledge-centre/decisions-and-regulations/regulation-and-procedures
- Social Insurance GOSI = https://www.gosi.gov.sa/ar/SystemsAndRegulations
- Saudi Data & AI Authority (SDAIA) = https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx
- There are also general sources for all laws in Saudi Arabia = https://laws.boe.gov.sa/BoeLaws/Laws/Search AND https://saudipedia.com/en/ BUT sometimes they are not up-to-date so don’t get any information from there unless it is the latest (very close to the news publishing date)
(4) In case it is law/regulation changes then use the above "deep research" technique to find which articles were impacted by the law or regulation changes and brief for each article.
(5) if it is related to law/regulation then assess the impact on SAP SuccessFactors Employee Central, Time Tracking and Payroll. The impact you assess should be based on statements written in the law article (not guessing)
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Failed to analyze: {e}"

# ======= Run against filtered news ========
if __name__ == "__main__":
    print("🔍 Running Legal Policy Manager Agent on filtered content...")
    filtered_news = get_relevant_news()
    for item in filtered_news:
        print("📰 Input:", item)
        print("🧠 Analysis:")
        print(analyze_legal_impact(item))
        print("=" * 80)

def get_lpm_analysis():
    return investigate_news()
