import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from configurations.config_loader import creds, add_news_item, get_weekly_baseline
from agents.sap_ai_client import SAPAICoreClient
import numpy as np
import os
import time

from agents.text_utils import (
    normalize_arabic,
    tokenize,
    jaccard,
    sentence_split,
    hash_signature,
)

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

# Embedding request safety: truncate texts and batch to avoid 8k token limit per request
MAX_CHARS_PER_ITEM = 1000  # ~250 tokens heuristic
BATCH_SIZE = 10            # smaller batches reduce TLS/frame issues on strict networks

# Fixed thresholds (as agreed)
DEDUP_COSINE_DUP = 0.92
DEDUP_COSINE_UPDATE = 0.85
JACCARD_DUP_MIN = 0.70
JACCARD_UPDATE_MIN = 0.40
WEEKLY_BASELINE_DAYS = 7


def _truncate_text(s: str, max_chars: int = MAX_CHARS_PER_ITEM) -> str:
    if not s:
        return ""
    return s[:max_chars]


def _embed_texts(texts, client, model: str = "text-embedding-3-small"):
    """
    Create embeddings with truncation and batching to respect context limits.
    Returns a flat list of OpenAI embedding data items (each has .embedding).
    """
    embeddings = []
    timeout_s = float(os.environ.get("LEGAL_EAGLE_OPENAI_TIMEOUT", "60"))
    retries = int(os.environ.get("LEGAL_EAGLE_EMBEDDINGS_RETRIES", "2"))
    backoff = float(os.environ.get("LEGAL_EAGLE_EMBEDDINGS_BACKOFF", "1.0"))
    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i:i + BATCH_SIZE]
        chunk = [_truncate_text(t) for t in chunk]
        attempt = 0
        while True:
            try:
                resp = client.embeddings.create(input=chunk, model=model, timeout=timeout_s)
                embeddings.extend(resp.data)
                break
            except Exception as e:
                print(f"❌ Embeddings call failed: {type(e).__name__}: {e}")
                if attempt >= retries:
                    raise
                sleep_s = backoff * (2 ** attempt)
                print(f"⏳ Retrying embeddings in {sleep_s:.1f}s (attempt {attempt+1}/{retries})...")
                time.sleep(sleep_s)
                attempt += 1
    return embeddings


def _get_text_signature(item: Dict[str, Any]) -> str:
    return f"{item.get('title', '')} {item.get('content', '')}".strip()


def _parse_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None


def _extract_glossary_terms(glossary: Optional[Dict[str, str]]) -> List[str]:
    """
    Glossary provided is a dict: {"HCM": "comma,separated,...", "FIN": "...", "OTHER": "..."}
    Extract normalized term list from HCM and FIN only.
    """
    if not glossary:
        return []
    terms = []
    for k in ("HCM", "FIN"):
        block = glossary.get(k) or ""
        for raw in block.split(","):
            t = normalize_arabic(raw.strip())
            if t:
                terms.append(t)
    # unique terms
    return sorted(set(terms))


def _has_meaningful_delta(sent: str, glossary_terms: List[str]) -> bool:
    """
    Stricter heuristic: a delta sentence is meaningful ONLY if:
    - it contains at least one glossary term (normalized substring).
    Numbers/dates alone are insufficient to qualify as meaningful deltas.
    """
    norm = normalize_arabic(sent)
    if not norm:
        return False
    # Require glossary presence
    for gt in glossary_terms:
        if gt and gt in norm:
            return True
    return False


def _compute_delta(current_text: str, baseline_text: str, glossary_terms: List[str]) -> List[str]:
    """
    Extract 2–4 concise delta sentences from current_text compared to baseline_text.
    """
    deltas: List[str] = []
    curr_sents = sentence_split(current_text)
    base_tokens = tokenize(baseline_text)

    for s in curr_sents:
        # Novelty by token overlap
        s_tokens = tokenize(s)
        sim = jaccard(s_tokens, base_tokens)
        if sim < 0.30:  # sufficiently new vs baseline
            if _has_meaningful_delta(s, glossary_terms):
                deltas.append(s.strip())
        if len(deltas) >= 4:
            break
    return deltas


def _build_item_record(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construct record for DB insertion.
    """
    url = item.get("link") or item.get("url")
    title = item.get("title")
    content = item.get("content")
    # Enforce explicit source_type from ingestors (no fallback here)
    source_type = item.get("source_type")
    allowed_types = {"RSS", "Tweet", "URL_Static", "URL_Dynamic"}
    if source_type not in allowed_types:
        raise ValueError(f"Invalid or missing source_type: {source_type}")
    source_id = item.get("tweet_id") or item.get("guid") or item.get("id")
    domain = _parse_domain(url)
    published_at = item.get("published") or item.get("date")

    return {
        "source_type": source_type,
        "source_id": source_id,
        "url": url,
        "domain": domain,
        "title": title,
        "content": content,
        "published_at": published_at,
        "hash_signature": hash_signature(title or "", content or ""),
    }


def run_compare_news_agent(
    current_items: List[Dict[str, Any]],
    outputs_dir: Optional[str] = "outputs",
    glossary: Optional[Dict[str, str]] = None,
    language: Optional[str] = "en",
    skip_comparison: bool = False,
):
    """
    DB-backed compare agent:
    - Persist current items to news_items (weekly baseline storage)
    - Load weekly baseline (last 7 days)
    - Classify each current item as New, Update, or Duplicate using:
      exact keys -> fuzzy -> embeddings cosine + Jaccard
    - For Update: extract delta sentences and include in result
    
    Args:
        skip_comparison: If True, bypass comparison and treat all items as new
    
    Returns:
      {"new_items": [...], "update_items": [...]}
    Also keeps latest/daily snapshots for manual inspection.
    """

    print("🧠 Running Compare News Agent...")
    
    # Skip comparison mode: treat all items as new
    if skip_comparison:
        print("⏭️ Skip comparison mode: Treating all items as new (bypassing duplicate detection)")
        
        out_dir = Path(outputs_dir or "outputs")
        out_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = out_dir / "all_news.json"
        
        # Still persist items to DB for future baseline
        print("🗃️ Persisting current items to DB baseline...")
        for item in current_items:
            try:
                rec = _build_item_record(item)
                add_news_item(item.get("profile_id") or 1, rec)
            except Exception as e:
                print(f"⚠️ Failed to upsert news item to DB: {e}")
        
        # Save snapshot
        try:
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(current_items, f, ensure_ascii=False, indent=2)
            print(f"💾 Updated snapshot → {snapshot_path}")
        except Exception as e:
            print(f"⚠️ Failed to write snapshot: {e}")
        
        return {"new_items": list(current_items), "update_items": []}

    out_dir = Path(outputs_dir or "outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = out_dir / "all_news.json"

    # Load weekly baseline FIRST (before persisting current items)
    # This ensures we can detect a truly empty baseline for the "no history" shortcut
    profile_id = current_items[0].get("profile_id") or 1 if current_items else 1
    baseline_items = get_weekly_baseline(profile_id, days=WEEKLY_BASELINE_DAYS)
    print(f"📚 Weekly baseline size: {len(baseline_items)} (profile_id={profile_id}, days={WEEKLY_BASELINE_DAYS})")
    
    # DEBUG: Log first 3 baseline items to understand what's being loaded
    if baseline_items:
        print(f"🔍 DEBUG: First baseline item: source_type={baseline_items[0].get('source_type')}, title={baseline_items[0].get('title', '')[:50]}")
        if len(baseline_items) > 1:
            print(f"🔍 DEBUG: Baseline item sources: {[b.get('source_type') for b in baseline_items[:5]]}")

    # NOTE: Reviewed items from filtered_news are NOT merged into the deduplication baseline.
    # They are only used in news_filter.py for the "second chance" rescue mechanism.
    # Merging them here would cause incoming items to be marked as duplicates of themselves.

    # Persist current items to DB (upsert) - these become part of next run's baseline
    print("🗃️ Persisting current items to DB baseline...")
    for item in current_items:
        try:
            rec = _build_item_record(item)
            add_news_item(item.get("profile_id") or 1, rec)
        except Exception as e:
            print(f"⚠️ Failed to upsert news item to DB: {e}")

    # Build quick lookup maps for exact/fuzzy
    by_source_id: Dict[str, Dict[str, Any]] = {}
    by_url: Dict[str, Dict[str, Any]] = {}
    by_sig: Dict[str, Dict[str, Any]] = {}

    for b in baseline_items:
        if b.get("source_id"):
            by_source_id[str(b["source_id"])] = b
        if b.get("url"):
            by_url[str(b["url"])] = b
        if b.get("hash_signature"):
            by_sig[str(b["hash_signature"])] = b

    # --- Optimization: Skip embeddings entirely if no baseline history ---
    if not baseline_items:
        print("📭 No baseline history found. Treating all items as new (skipping embeddings).")
        # Save snapshot for manual inspection
        try:
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(current_items, f, ensure_ascii=False, indent=2)
            print(f"💾 Updated snapshot → {snapshot_path}")
        except Exception as e:
            print(f"⚠️ Failed to write snapshot: {e}")
        return {"new_items": list(current_items), "update_items": []}

    # --- Full comparison path (baseline exists) ---
    # Prepare semantic structures
    baseline_texts = [_get_text_signature(b) for b in baseline_items]
    curr_texts = [_get_text_signature(i) for i in current_items]

    # Token sets for Jaccard
    baseline_tokens = [tokenize(t) for t in baseline_texts]

    # Embeddings for cosine similarity
    print("🔍 Generating embeddings for semantic comparison (weekly baseline)...")
    client = _get_ai_client()
    baseline_emb = _embed_texts(baseline_texts, client)
    curr_emb = _embed_texts(curr_texts, client)

    new_items: List[Dict[str, Any]] = []
    update_items: List[Dict[str, Any]] = []
    glossary_terms = _extract_glossary_terms(glossary)

    for i, item in enumerate(current_items):
        curr_text = curr_texts[i]
        curr_sig = hash_signature(item.get("title", ""), item.get("content", ""))
        url = item.get("link") or item.get("url")
        source_id = item.get("tweet_id") or item.get("guid") or item.get("id")

        # Exact checks (skip duplicates)
        if source_id and source_id in by_source_id:
            continue
        if url and url in by_url:
            continue
        if curr_sig and curr_sig in by_sig:
            continue

        # Compute best semantic match against baseline
        curr_vec = np.array(curr_emb[i].embedding)
        best_cos = -1.0
        best_idx = -1
        for j, b in enumerate(baseline_emb):
            b_vec = np.array(b.embedding)
            # cosine similarity
            cos_sim = float(np.dot(curr_vec, b_vec) / (np.linalg.norm(curr_vec) * np.linalg.norm(b_vec)))
            if cos_sim > best_cos:
                best_cos = cos_sim
                best_idx = j

        # Jaccard token overlap vs best baseline item
        jac_sim = 0.0
        if best_idx >= 0 and best_idx < len(baseline_tokens):
            jac_sim = jaccard(tokenize(curr_text), baseline_tokens[best_idx])

        # Classification
        if best_cos >= DEDUP_COSINE_DUP and jac_sim >= JACCARD_DUP_MIN:
            # Duplicate
            continue
        elif (best_cos >= DEDUP_COSINE_UPDATE) and (JACCARD_UPDATE_MIN <= jac_sim < JACCARD_DUP_MIN):
            # Update candidate: extract delta sentences
            baseline_text = baseline_texts[best_idx] if (best_idx >= 0) else ""
            deltas = _compute_delta(curr_text, baseline_text, glossary_terms)
            if deltas:
                item["is_update"] = True
                item["delta"] = deltas
                update_items.append(item)
            else:
                # No meaningful delta → treat as repeat (omit)
                continue
        else:
            # New item
            new_items.append(item)

    print(f"✅ New items: {len(new_items)} | Updates: {len(update_items)} (thresholds: cosine dup={DEDUP_COSINE_DUP}, update={DEDUP_COSINE_UPDATE})")

    # Save single rolling snapshot for manual inspection
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(current_items, f, ensure_ascii=False, indent=2)
        print(f"💾 Updated snapshot → {snapshot_path}")
    except Exception as e:
        print(f"⚠️ Failed to write snapshot: {e}")

    return {"new_items": new_items, "update_items": update_items}
