"""
RCM Checker Agent - Checks if news items are already published in SAP RCM.

This agent uses a two-stage AI-powered approach:
1. AI Query Generator: Extracts key terms (law numbers, topics) from news
2. RCM Search: Searches RCM via Loka MCP for relevant regulations
3. AI Match Verifier: Intelligently compares news against RCM results

The agent enriches news items with RCM metadata:
- rcm_checked: Whether the check was performed
- rcm_published: Whether a match was found in RCM
- rcm_regulation_id: The matching RCM regulation ID (e.g., GSREQSE-15267)
- rcm_confidence: Confidence score (0.0-1.0)
- rcm_reasoning: AI explanation of why it matched
- rcm_checked_at: Timestamp of the check
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

from agents.sap_ai_client import SAPAICoreClient


def _generate_search_query(news_item: Dict, sap_ai_client: SAPAICoreClient) -> Dict:
    """
    Stage 1: AI Query Generator
    
    Analyzes news content and extracts the most relevant search terms for RCM:
    - Law/decree numbers (e.g., "09903", "Law 7524")
    - Key legal topics (e.g., "social security", "minimum wage")
    - Government institutions (e.g., "SGK", "Ministry of Finance")
    - Effective dates
    
    Args:
        news_item: News item dictionary with 'title' and 'content'
        sap_ai_client: SAP AI Core client
    
    Returns:
        Dict with extracted terms and generated search query:
        {
            "law_numbers": ["09903", "19903"],
            "topics": ["social security premium", "employer contribution"],
            "institutions": ["SGK"],
            "dates": ["2026-01-01"],
            "search_query": "social security premium employer share 09903 19903"
        }
    """
    title = news_item.get("title", "")
    content = news_item.get("content", "")
    text = f"Title: {title}\n\nContent: {content}".strip()
    
    if not text or len(text) < 20:
        return {
            "law_numbers": [],
            "topics": [],
            "institutions": [],
            "dates": [],
            "search_query": ""
        }
    
    prompt = f"""You are an expert at extracting key legal information from news articles.

**News Article:**
---
{text}
---

**Task:**
Extract the following information to help search for related regulations:

1. **Law/Decree Numbers**: Any law, decree, or regulation numbers mentioned (e.g., "09903", "Law 7524", "Decree 9903")
2. **Key Topics**: Main legal topics (e.g., "social security", "tax", "minimum wage", "payroll")
3. **Institutions**: Government institutions mentioned (e.g., "SGK", "Ministry of Finance", "Tax Authority")
4. **Dates**: Important dates mentioned (in YYYY-MM-DD format)

Then create a concise search query (5-10 words) combining the most important terms.

**Output Format:**
Respond ONLY with valid JSON:
{{
  "law_numbers": ["list of law/decree numbers"],
  "topics": ["list of 2-3 main topics"],
  "institutions": ["list of institutions"],
  "dates": ["YYYY-MM-DD format dates"],
  "search_query": "concise search query combining key terms"
}}

Example:
{{
  "law_numbers": ["09903", "19903", "29903"],
  "topics": ["social security premium", "employer contribution", "investment incentive"],
  "institutions": ["SGK"],
  "dates": ["2026-01-01", "2025-12-31"],
  "search_query": "social security premium employer share 09903 19903"
}}
"""
    
    try:
        timeout_s = float(os.environ.get("LEGAL_EAGLE_OPENAI_TIMEOUT", "30"))
        response = sap_ai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=timeout_s
        )
        reply = response.choices[0].message.content.strip()
        data = json.loads(reply)
        
        return {
            "law_numbers": data.get("law_numbers", []),
            "topics": data.get("topics", []),
            "institutions": data.get("institutions", []),
            "dates": data.get("dates", []),
            "search_query": data.get("search_query", "")
        }
    except Exception as e:
        print(f"⚠️  AI query generation failed: {e}")
        return {
            "law_numbers": [],
            "topics": [],
            "institutions": [],
            "dates": [],
            "search_query": ""
        }


def _search_rcm_regulations(
    search_query: str,
    country: str,
    product: str,
    loka_response: Optional[str] = None
) -> List[Dict]:
    """
    Stage 2: Search RCM via Loka Agent
    
    Searches RCM for regulations matching the generated query.
    Returns top 5-10 most relevant regulations.
    
    Args:
        search_query: Generated search query
        country: Country name (e.g., "Turkey")
        product: SAP product (e.g., "SAP HCM")
        loka_response: Optional Loka MCP response text (injected by orchestrator)
    
    Returns:
        List of RCM regulation dictionaries with id, title, summary, etc.
        Each dict contains: id, title, summary, country, status
    
    Integration:
        This function uses the Loka Agent to handle RCM search.
        The orchestrator calls Loka MCP and passes the response here.
        
        Orchestrator workflow:
        1. RCM Checker calls this function with query
        2. If loka_response is None, Loka Agent returns empty list
        3. Orchestrator detects empty list, calls Loka MCP
        4. Orchestrator calls this function again with loka_response
        5. Loka Agent parses response and returns structured data
    """
    try:
        from agents.loka_agent import get_loka_agent
        
        # Get Loka Agent instance
        loka = get_loka_agent()
        
        # Search RCM (will parse loka_response if provided)
        regulations = loka.search_rcm(
            country=country,
            query=search_query,
            max_results=10,
            loka_response=loka_response
        )
        
        return regulations
        
    except Exception as e:
        print(f"   ⚠️  RCM search error: {e}")
        return []


def _verify_match(
    news_item: Dict,
    rcm_regulation: Dict,
    sap_ai_client: SAPAICoreClient
) -> Dict:
    """
    Stage 3: AI Match Verifier
    
    Uses AI to intelligently compare news against RCM regulation.
    Considers law numbers, topics, dates, and context to determine if they
    describe the SAME legal change.
    
    Args:
        news_item: News item dictionary
        rcm_regulation: RCM regulation dictionary
        sap_ai_client: SAP AI Core client
    
    Returns:
        Dict with match decision:
        {
            "is_match": True/False,
            "confidence": 0.0-1.0,
            "reasoning": "Explanation of why they match or don't match",
            "matching_indicators": ["law number 09903", "same topic", ...]
        }
    """
    news_title = news_item.get("title", "")
    news_content = news_item.get("content", "")
    news_text = f"Title: {news_title}\n\nContent: {news_content[:500]}".strip()
    
    rcm_id = rcm_regulation.get("id", "")
    rcm_title = rcm_regulation.get("title", "")
    rcm_summary = rcm_regulation.get("summary", "")
    rcm_law_numbers = rcm_regulation.get("law_numbers", [])
    
    prompt = f"""You are an expert at matching legal news to existing regulations in SAP's Regulatory Change Management (RCM) system.

**NEWS ITEM:**
{news_text}

**RCM REGULATION:**
ID: {rcm_id}
Title: {rcm_title}
Summary: {rcm_summary}
Law Numbers: {', '.join(rcm_law_numbers) if rcm_law_numbers else 'None'}

**Task:**
Determine if this news item is about the SAME underlying legal change as the RCM regulation.

**IMPORTANT CONTEXT:**
- News often contains IMPLEMENTATION DETAILS (specific law numbers, amounts, dates)
- RCM regulations often have GENERAL TITLES describing the overall change
- Example: News "Law 09903 employer premium support" → RCM "SGK Premium Support Changes"
- They're the SAME regulation even if one has more details than the other

**Matching Logic:**
1. **Topic Match** (REQUIRED): Same legal subject (e.g., both about minimum wage, tax, social security)
2. **Geographic Match** (REQUIRED): Same country/region
3. **Time Period Match** (STRONG): Same year or effective period (e.g., 2025, 2026)
4. **Institution Match** (STRONG): Same government body (e.g., SGK, Ministry of Finance)
5. **Law Numbers** (BONUS): If present in both, exact matches are very strong evidence

**Key Principle:**
If the news is announcing/implementing a change that the RCM regulation already tracks, they MATCH.
The news may have MORE detail (specific law numbers, amounts) than the RCM title, but that's normal.

**Output Format:**
Respond ONLY with valid JSON:
{{
  "is_match": true_or_false,
  "confidence": 0.0_to_1.0,
  "reasoning": "One sentence explaining why they match or don't match",
  "matching_indicators": ["list of specific reasons"]
}}

Example for a match:
{{
  "is_match": true,
  "confidence": 0.95,
  "reasoning": "Both reference law numbers 09903, 19903, 29903, 39903 regarding employer share social security premium support",
  "matching_indicators": ["Law number 09903 (exact match)", "Law number 19903 (exact match)", "Social security premium topic (match)", "Employer contribution focus (match)"]
}}

Example for no match:
{{
  "is_match": false,
  "confidence": 0.85,
  "reasoning": "While both are about social security, the news discusses unemployment insurance rates while RCM is about premium support incentives",
  "matching_indicators": ["Social security topic (related)", "Different law numbers", "Different scope"]
}}
"""
    
    try:
        timeout_s = float(os.environ.get("LEGAL_EAGLE_OPENAI_TIMEOUT", "30"))
        response = sap_ai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=timeout_s
        )
        reply = response.choices[0].message.content.strip()
        data = json.loads(reply)
        
        return {
            "is_match": data.get("is_match", False),
            "confidence": data.get("confidence", 0.0),
            "reasoning": data.get("reasoning", ""),
            "matching_indicators": data.get("matching_indicators", [])
        }
    except Exception as e:
        print(f"⚠️  AI match verification failed: {e}")
        return {
            "is_match": False,
            "confidence": 0.0,
            "reasoning": f"Error during verification: {e}",
            "matching_indicators": []
        }


def check_rcm_status(
    items: List[Dict],
    profile_country: str,
    profile_lob: str,
    sap_ai_client: SAPAICoreClient
) -> List[Dict]:
    """
    Main entry point: Check all items against RCM.
    
    For each news item:
    1. Generate smart search query using AI
    2. Search RCM for relevant regulations
    3. Verify matches using AI reasoning
    4. Add RCM metadata to item
    
    Args:
        items: List of news item dictionaries
        profile_country: Country name (e.g., "Turkey")
        profile_lob: Line of Business - "HCM" or "FIN"
        sap_ai_client: SAP AI Core client
    
    Returns:
        List of items with RCM metadata added:
        - rcm_checked: True
        - rcm_published: True if match found, False otherwise
        - rcm_regulation_id: RCM regulation ID (if match found)
        - rcm_confidence: Confidence score 0.0-1.0 (if match found)
        - rcm_reasoning: AI explanation (if match found)
        - rcm_checked_at: ISO timestamp
    """
    # Map LoB to SAP product
    product_map = {
        "HCM": "SAP HCM",
        "FIN": "SAP S/4HANA"
    }
    product = product_map.get(profile_lob.upper(), "SAP HCM")
    
    enriched_items = []
    
    for item in items:
        print(f"\n🔍 Checking RCM for: {item.get('title', 'Untitled')[:60]}...")
        
        # Stage 1: Generate search query
        query_data = _generate_search_query(item, sap_ai_client)
        search_query = query_data.get("search_query", "")
        
        if not search_query:
            print("   ⚠️  Could not generate search query")
            item["rcm_checked"] = True
            item["rcm_published"] = False
            item["rcm_checked_at"] = datetime.utcnow().isoformat()
            enriched_items.append(item)
            continue
        
        print(f"   📝 Generated query: {search_query}")
        
        # Stage 2: Search RCM
        rcm_results = _search_rcm_regulations(search_query, profile_country, product)
        
        if not rcm_results:
            print("   ℹ️  No RCM regulations found")
            item["rcm_checked"] = True
            item["rcm_published"] = False
            item["rcm_checked_at"] = datetime.utcnow().isoformat()
            enriched_items.append(item)
            continue
        
        print(f"   📋 Found {len(rcm_results)} RCM regulation(s)")
        
        # Stage 3: Verify each result
        best_match = None
        best_confidence = 0.0
        
        for rcm_reg in rcm_results:
            match_result = _verify_match(item, rcm_reg, sap_ai_client)
            
            if match_result["is_match"] and match_result["confidence"] > best_confidence:
                best_match = {
                    "regulation_id": rcm_reg.get("id", ""),
                    "confidence": match_result["confidence"],
                    "reasoning": match_result["reasoning"]
                }
                best_confidence = match_result["confidence"]
        
        # Add RCM metadata
        if best_match:
            print(f"   ✅ Match found: {best_match['regulation_id']} ({best_match['confidence']:.0%})")
            item["rcm_checked"] = True
            item["rcm_published"] = True
            item["rcm_regulation_id"] = best_match["regulation_id"]
            item["rcm_confidence"] = best_match["confidence"]
            item["rcm_reasoning"] = best_match["reasoning"]
            item["rcm_checked_at"] = datetime.utcnow().isoformat()
        else:
            print("   🆕 No match - this is new")
            item["rcm_checked"] = True
            item["rcm_published"] = False
            item["rcm_checked_at"] = datetime.utcnow().isoformat()
        
        enriched_items.append(item)
    
    return enriched_items