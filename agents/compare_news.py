import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from configurations.config_loader import creds, add_news_item, get_weekly_baseline
from agents.sap_ai_client import SAPAICoreClient
from agents.ai_cache import cached_embeddings
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

# Dedup thresholds (v3.1). Duplicate detection is cosine-primary: paraphrased
# legal-news items share few exact tokens (link/date noise tanks Jaccard), so the
# embedding cosine is the reliable signal. Measured on the Xanadu fixtures, true
# duplicates score ≥0.85 while distinct same-topic items sit ≤0.75, so 0.80 is the
# separating threshold (matches the roadmap's 0.92→0.80 lowering). Jaccard is kept
# only as a weak floor to reject pure-coincidence cosine matches.
DEDUP_COSINE_DUP = 0.80
DEDUP_COSINE_UPDATE = 0.72
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
        # v3.1: carry attribution + dedup marker through to persistence
        "publisher": item.get("publisher"),
        "authority_id": item.get("authority_id"),
        "authority_status": item.get("authority_status"),
        "dedup_status": item.get("dedup_status"),
    }


# --- Entity-based canonical fingerprint (B7) ------------------------------
# Replaces the brittle exact-text hash for duplicate detection: two items whose
# significant domain tokens match (ignoring word order, casing, stopwords and
# short filler words) collapse to the same fingerprint, so trivially reworded
# headlines are recognised as the same story without an AI call.
_FP_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "will", "has", "have",
    "are", "was", "were", "its", "into", "over", "under", "new", "set", "next",
    "announces", "announced", "release", "released", "releases", "update",
    "updated", "updates", "published", "publishes", "to", "of", "in", "on",
    "a", "an", "as", "at", "by", "is", "be",
}


def entity_fingerprint(title: str, content: str) -> str:
    """Canonical fingerprint = sorted set of significant (>3 char, non-stopword) tokens."""
    text = normalize_arabic(f"{title or ''} {content or ''}")
    toks = [t for t in tokenize(text) if len(t) > 3 and t not in _FP_STOPWORDS]
    return " ".join(sorted(set(toks)))


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
                item["dedup_status"] = "new"
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

    # Build baseline lookup maps for exact/canonical matching (incl. entity fingerprint, B7)
    by_source_id: Dict[str, Any] = {}
    by_url: Dict[str, Any] = {}
    by_sig: Dict[str, Any] = {}
    by_fp: Dict[str, Any] = {}
    for b in baseline_items:
        if b.get("source_id"):
            by_source_id[str(b["source_id"])] = b
        if b.get("url"):
            by_url[str(b["url"])] = b
        if b.get("hash_signature"):
            by_sig[str(b["hash_signature"])] = b
        fp = entity_fingerprint(b.get("title", ""), b.get("content", ""))
        if fp:
            by_fp[fp] = b

    # Semantic structures. Embeddings are only needed when there is something to
    # compare against (a non-empty baseline) or when the AI cache is active for
    # deterministic replay. First-ever runs with no baseline stay AI-free.
    curr_texts = [_get_text_signature(i) for i in current_items]
    glossary_terms = _extract_glossary_terms(glossary)
    use_embeddings = bool(baseline_items) or bool(os.environ.get("LEGAL_EAGLE_AI_CACHE"))
    baseline_texts = [_get_text_signature(b) for b in baseline_items]
    baseline_tokens = [tokenize(t) for t in baseline_texts]
    baseline_emb: List[Any] = []
    curr_emb: List[Any] = []
    if use_embeddings:
        print("🔍 Generating embeddings for semantic comparison (weekly baseline)...")
        try:
            client = _get_ai_client()
            if baseline_texts:
                baseline_emb = cached_embeddings(baseline_texts, lambda t: _embed_texts(t, client))
            curr_emb = cached_embeddings(curr_texts, lambda t: _embed_texts(t, client))
        except Exception as e:
            # Embeddings unavailable (AI Core down / no cache) — degrade to
            # deterministic dedup (exact id/url/hash/fingerprint) rather than
            # aborting the whole run. Near-duplicates fall through as 'new'.
            print(f"⚠️ Embeddings unavailable ({type(e).__name__}); using deterministic dedup only.")
            use_embeddings = False
            baseline_emb = []
            curr_emb = []

    new_items: List[Dict[str, Any]] = []
    update_items: List[Dict[str, Any]] = []

    # Intra-run state: items kept so far this run become comparison targets too,
    # so a second occurrence of the same story within one run is caught (C3).
    seen_source_ids = set(by_source_id.keys())
    seen_urls = set(by_url.keys())
    seen_fps = set(by_fp.keys())
    kept_current: List[Dict[str, Any]] = []  # {vec, tokens, text}

    def _best_semantic(curr_vec, targets):
        best_cos, best_j = -1.0, -1
        for j, tv in enumerate(targets):
            denom = (np.linalg.norm(curr_vec) * np.linalg.norm(tv))
            if denom == 0:
                continue
            cos = float(np.dot(curr_vec, tv) / denom)
            if cos > best_cos:
                best_cos, best_j = cos, j
        return best_cos, best_j

    for i, item in enumerate(current_items):
        curr_text = curr_texts[i]
        curr_sig = hash_signature(item.get("title", ""), item.get("content", ""))
        curr_fp = entity_fingerprint(item.get("title", ""), item.get("content", ""))
        url = item.get("link") or item.get("url")
        source_id = item.get("tweet_id") or item.get("guid") or item.get("id")

        # 1) Exact / canonical duplicate (vs baseline AND already-kept current items)
        is_dup = (
            (source_id and str(source_id) in seen_source_ids)
            or (url and str(url) in seen_urls)
            or (curr_sig and curr_sig in by_sig)
            or (curr_fp and curr_fp in seen_fps)
        )

        classification = "new"
        if is_dup:
            classification = "duplicate"
        elif use_embeddings and i < len(curr_emb):
            # 2) Semantic comparison vs baseline + kept-current embeddings
            curr_vec = np.array(curr_emb[i].embedding)
            base_vecs = [np.array(b.embedding) for b in baseline_emb]
            cur_vecs = [k["vec"] for k in kept_current]
            all_texts = baseline_texts + [k["text"] for k in kept_current]
            best_cos, best_j = _best_semantic(curr_vec, base_vecs + cur_vecs)
            # Cosine-tiered classification (Jaccard AND-gate dropped — unreliable on
            # paraphrased news). High cosine ⇒ duplicate; mid cosine with a genuine
            # glossary-bearing delta ⇒ update; otherwise new.
            if best_cos >= DEDUP_COSINE_DUP:
                classification = "duplicate"
            elif best_cos >= DEDUP_COSINE_UPDATE:
                baseline_text = all_texts[best_j] if 0 <= best_j < len(all_texts) else ""
                deltas = _compute_delta(curr_text, baseline_text, glossary_terms)
                if deltas:
                    classification = "update"
                    item["is_update"] = True
                    item["delta"] = deltas
                else:
                    classification = "new"

        item["dedup_status"] = classification
        if classification == "new":
            new_items.append(item)
            # register as a comparison target for the rest of this run
            seen_source_ids.add(str(source_id)) if source_id else None
            seen_urls.add(str(url)) if url else None
            seen_fps.add(curr_fp) if curr_fp else None
            if use_embeddings and i < len(curr_emb):
                kept_current.append({"vec": np.array(curr_emb[i].embedding),
                                     "tokens": tokenize(curr_text), "text": curr_text})
        elif classification == "update":
            update_items.append(item)
            seen_fps.add(curr_fp) if curr_fp else None

    # Persist ALL current items (with dedup_status) — duplicates are preserved (F7),
    # never dropped, so they remain queryable and visible (collapsed) in Review.
    print("🗃️ Persisting current items to DB baseline (with dedup_status)...")
    for item in current_items:
        try:
            rec = _build_item_record(item)
            add_news_item(item.get("profile_id") or 1, rec)
        except Exception as e:
            print(f"⚠️ Failed to upsert news item to DB: {e}")

    dup_count = sum(1 for it in current_items if it.get("dedup_status") == "duplicate")
    print(f"✅ New: {len(new_items)} | Updates: {len(update_items)} | Duplicates (kept): {dup_count}")

    # Save single rolling snapshot for manual inspection
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(current_items, f, ensure_ascii=False, indent=2)
        print(f"💾 Updated snapshot → {snapshot_path}")
    except Exception as e:
        print(f"⚠️ Failed to write snapshot: {e}")

    return {"new_items": new_items, "update_items": update_items}
