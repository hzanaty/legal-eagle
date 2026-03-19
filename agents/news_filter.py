# agents/news_filter.py

import os
import json
import re
from datetime import datetime, timedelta, timezone
from agents.text_utils import normalize_arabic

# Import SAP AI Core client
from agents.sap_ai_client import SAPAICoreClient
from configurations.config_loader import creds

# Maximum age of news in days. Articles older than this will be discarded.
MAX_NEWS_AGE_DAYS = int(os.environ.get("LEGAL_EAGLE_MAX_NEWS_AGE_DAYS", "7"))

# AI client factory: Returns SAP AI Core client
def _get_ai_client():
    """Get SAP AI Core client from credentials."""
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"]
    )


def _parse_publication_date(date_str: str) -> datetime | None:
    """
    Attempt to parse a date string from various formats commonly found in news items.
    Returns a datetime object or None if parsing fails.
    """
    if not date_str:
        return None
    
    # Common date formats
    formats = [
        "%Y-%m-%dT%H:%M:%S",       # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",      # ISO 8601 with Z
        "%Y-%m-%d %H:%M:%S",       # Standard datetime
        "%Y-%m-%d",                 # Standard date
        "%d-%m-%Y",                 # European style
        "%m-%d-%Y",                 # US style
        "%d/%m/%Y",                 # European with slashes
        "%m/%d/%Y",                 # US with slashes
        "%a, %d %b %Y %H:%M:%S %z", # RFC 2822 (RSS standard)
        "%a, %d %b %Y %H:%M:%S %Z", # RFC 2822 with timezone name
    ]
    
    # Clean up the date string
    clean_str = date_str.strip()
    # Handle timezone offset like +00:00
    clean_str = re.sub(r'\+\d{2}:\d{2}$', '', clean_str)
    clean_str = re.sub(r'\.\d+$', '', clean_str)  # Remove microseconds
    
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
    
    # Try to extract date from content using regex (e.g., "01-11-2024")
    date_pattern = r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})'
    match = re.search(date_pattern, date_str)
    if match:
        day, month, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            # Try swapping day and month
            try:
                return datetime(int(year), int(day), int(month))
            except ValueError:
                pass
    
    return None


def is_news_too_old(item: dict, max_age_days: int = MAX_NEWS_AGE_DAYS) -> bool:
    """
    Check if a news item is older than the maximum allowed age.
    
    Args:
        item: News item dictionary with 'published', 'date', or 'published_at' field.
        max_age_days: Maximum age in days (default from environment or 7).
    
    Returns:
        True if the news is too old, False otherwise.
        If the date cannot be determined, returns False (let it through).
    """
    # Try different date fields
    date_str = item.get("published") or item.get("date") or item.get("published_at")
    
    if not date_str:
        return False
    
    pub_date = _parse_publication_date(str(date_str))
    
    if not pub_date:
        return False
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    
    return pub_date < cutoff_date


# 🧠 LLM-based Semantic Glossary Check
def semantic_glossary_check(item: dict, sap_ai_client, GLOSSARY: dict, LANGUAGE_PREFERENCE: str, lob: str) -> dict:
    """
    Uses an LLM to perform a semantic relevance check.
    The LLM understands the *meaning* of the glossary terms, not just keywords.
    This works across languages, comparing the meaning of the news content against
    the meaning of the glossary terms.

    Returns:
        dict: {"is_relevant": True/False, "reasoning": "...", "error": False}
              or {"error": True, "message": "..."}
    """
    title = item.get("title", "") or ""
    content = item.get("content", "") or ""
    text_to_analyze = f"Title: {title}\n\nContent: {content}".strip()

    if not text_to_analyze or len(text_to_analyze) < 20:
        return {"is_relevant": False, "reasoning": "Content too short to analyze.", "error": False}

    active_lob = "FIN" if (lob or "").upper() == "FIN" else "HCM"
    glossary_terms = GLOSSARY.get(active_lob, "") or ""

    prompt = f"""You are an expert legal policy analyst specializing in SAP Localization.
Your task is to determine if a news article is semantically relevant to a specific Line of Business (LoB).

**Line of Business (LoB):** {active_lob}
**Glossary of Relevant Topics for {active_lob}:**
{glossary_terms}

**News Article:**
---
{text_to_analyze}
---

**Instructions:**
1.  Analyze the core meaning and subject matter of the news article.
2.  Compare the article's subject matter against the **meaning and concepts** represented by the glossary terms. Do NOT just look for keyword matches. The article and glossary may be in different languages.
3.  Determine if the article discusses a topic that is *genuinely related* to the glossary for the {active_lob} LoB. A true legal or regulatory change impacting HR, Payroll, or Finance functions is relevant.
4.  Articles about general politics, international relations, diplomacy, trade deals, or other topics that do not directly affect {active_lob} functions should be marked as NOT relevant.

**Output Format:**
Respond ONLY with a valid JSON object in this exact format:
{{"is_relevant": true_or_false, "reasoning": "A one-sentence explanation in {LANGUAGE_PREFERENCE}."}}

Example for a relevant article:
{{"is_relevant": true, "reasoning": "The article discusses changes to social insurance contribution rates, which directly impacts payroll calculations."}}

Example for an irrelevant article:
{{"is_relevant": false, "reasoning": "The article is about a diplomatic meeting between two countries and does not concern HR, Payroll, or Finance regulations."}}
"""
    
    client = _get_ai_client()
    try:
        timeout_s = float(os.environ.get("LEGAL_EAGLE_OPENAI_TIMEOUT", "30"))
        response = client.chat.completions.create(
            model="gpt-4o",  # Model name ignored, uses configured deployment
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=timeout_s
        )
        reply = response.choices[0].message.content.strip()
        data = json.loads(reply)
        return {
            "is_relevant": data.get("is_relevant", False),
            "reasoning": data.get("reasoning", ""),
            "error": False
        }
    except json.JSONDecodeError as e:
        return {"error": True, "message": f"Invalid JSON from LLM: {e}"}
    except Exception as e:
        return {"error": True, "message": str(e)}


# 🔗 Semantic Similarity Check (for "Second Chance" against baseline)
def is_similar_to_baseline(item: dict, baseline_items: list, sap_ai_client, threshold: float = 0.85) -> bool:
    """
    Uses embeddings to check if a new item is semantically similar to any item
    in the high-score baseline.

    Args:
        item: The news item to check.
        baseline_items: A list of previously reviewed, high-score items.
        sap_ai_client: SAP AI Core client (deprecated parameter for compatibility).
        threshold: Cosine similarity threshold (default 0.85).

    Returns:
        True if the item is similar to any baseline item, False otherwise.
    """
    if not baseline_items:
        return False

    new_text = normalize_arabic(f"{item.get('title', '')} {item.get('content', '')}").strip()
    if not new_text:
        return False

    client = _get_ai_client()

    try:
        # Get embedding for the new item
        new_embedding_response = client.embeddings.create(
            model="text-embedding-ada-002",  # Model name ignored, uses configured deployment
            input=[new_text]
        )
        new_embedding = new_embedding_response.data[0].embedding

        # Get embeddings for baseline items
        baseline_texts = [
            normalize_arabic(f"{b.get('title', '')} {b.get('content', '')}").strip()
            for b in baseline_items
        ]
        baseline_texts = [t for t in baseline_texts if t]  # Filter empty strings

        if not baseline_texts:
            return False

        baseline_embedding_response = client.embeddings.create(
            model="text-embedding-ada-002",  # Model name ignored, uses configured deployment
            input=baseline_texts
        )

        # Compare using cosine similarity
        for baseline_data in baseline_embedding_response.data:
            baseline_embedding = baseline_data.embedding
            # Cosine similarity calculation
            dot_product = sum(a * b for a, b in zip(new_embedding, baseline_embedding))
            norm_new = sum(a * a for a in new_embedding) ** 0.5
            norm_baseline = sum(b * b for b in baseline_embedding) ** 0.5
            
            if norm_new > 0 and norm_baseline > 0:
                similarity = dot_product / (norm_new * norm_baseline)
                if similarity >= threshold:
                    return True
        
        return False

    except Exception:
        # On any error, fail open (don't rescue)
        return False


# ✅ Entry point: filter news items using LLM semantic check + high-score baseline rescue
def get_relevant_news(
    all_news_items: list,
    sap_ai_client,
    GLOSSARY: dict,
    LANGUAGE_PREFERENCE: str,
    lob: str,
    high_score_baseline: list = None,
    on_filtered=None
) -> dict:
    """
    Filter news items for relevance to the given LoB using a semantic LLM-based check.
    Items that fail the initial check get a "second chance" if they are similar to
    previously reviewed, high-scoring items.
    
    Args:
        all_news_items: List of news items to filter.
        sap_ai_client: SAP AI Core client (deprecated parameter for compatibility).
        GLOSSARY: Dictionary with HCM/FIN/OTHER term lists.
        LANGUAGE_PREFERENCE: Preferred output language.
        lob: Line of Business (HCM or FIN).
        high_score_baseline: List of items from the database with a human review score >= 4.
        on_filtered: Optional callback(item, reason) called for each filtered item.
    
    Returns:
        dict with 'items' (relevant), 'errors', and 'filtered'.
    """
    relevant = []
    errors = []
    filtered_items = []
    baseline = high_score_baseline or []

    for item in all_news_items:
        # --- Step 1: Age Gate ---
        if is_news_too_old(item):
            if on_filtered:
                on_filtered(item, "too_old")
            filtered_items.append({"item": item, "reason": "too_old"})
            continue

        # --- Step 2: Semantic Glossary Check (LLM) ---
        result = semantic_glossary_check(item, sap_ai_client, GLOSSARY, LANGUAGE_PREFERENCE, lob)

        if result.get("error"):
            errors.append({
                "error": True,
                "title": item.get("title", "Unknown"),
                "message": result.get("message", "LLM error")
            })
            continue

        if result.get("is_relevant"):
            item["filter_reasoning"] = result.get("reasoning", "")
            relevant.append(item)
        else:
            # --- Step 3: "Second Chance" against High-Score Baseline ---
            if is_similar_to_baseline(item, baseline, sap_ai_client):
                item["filter_reasoning"] = "Rescued: Similar to a previously reviewed high-score item."
                item["rescued"] = True
                relevant.append(item)
            else:
                if on_filtered:
                    on_filtered(item, "semantic_check_failed")
                filtered_items.append({
                    "item": item,
                    "reason": "semantic_check_failed",
                    "reasoning": result.get("reasoning", "")
                })

    return {
        "items": relevant,
        "errors": errors,
        "filtered": filtered_items
    }
