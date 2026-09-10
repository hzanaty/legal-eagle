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
        # v3.2: repetition tracking
        "repetition_status": item.get("repetition_status"),
        "repetition_count": item.get("repetition_count"),
        # v3.2: rank fields (populated by news_ranker after compare; upsert updates them)
        "significance_rank": item.get("significance_rank"),
        "rank_tier": item.get("rank_tier"),
        "rank_reasoning": item.get("rank_reasoning"),
        # v3.8: effective date (populated by news_ranker; upsert updates it)
        "effective_date": item.get("effective_date"),
        # v3.13: L2 deep-fetch fields (populated by l2_fetcher; act_ref may also come from glossary_match)
        "l2_summary": item.get("l2_summary"),
        "l2_fetched_at": item.get("l2_fetched_at"),
        "act_ref": item.get("act_ref"),
        "law_primary": item.get("law_primary"),
        "law_secondary": item.get("law_secondary"),
        "law_reference": item.get("law_reference"),
    }


def _find_matched_baseline(item, by_source_id, by_url, by_sig, by_fp):
    """Return the matched baseline row for a classified item, or None."""
    source_id = item.get("tweet_id") or item.get("guid") or item.get("id")
    url = item.get("link") or item.get("url")
    curr_sig = hash_signature(item.get("title", ""), item.get("content", ""))
    curr_fp = entity_fingerprint(item.get("title", ""), item.get("content", ""))
    if source_id and str(source_id) in by_source_id:
        return by_source_id[str(source_id)]
    if url and str(url) in by_url:
        return by_url[str(url)]
    if curr_sig and curr_sig in by_sig:
        return by_sig[curr_sig]
    if curr_fp and curr_fp in by_fp:
        return by_fp[curr_fp]
    return None


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


def _norm_act_ref(s: Optional[str]) -> str:
    """Normalize an act/gazette reference for language-independent comparison."""
    return (s or "").strip().lower()


def reconcile_by_act_ref(items, conn, profile_id, days: int = WEEKLY_BASELINE_DAYS):
    """Post-L2/Law-Match dedup reconciliation (v3.15 → generalized v3.16).

    Identity is language-independent but only known after L2 + Law Match, so this runs
    late. The primary key is the resolved **law_id** (registry law); ``act_ref`` is the
    fallback when no law resolved. Compare runs *before* L2/Law-Match, so a Turkish and
    an English article about the same law both pass as ``new`` there. Here:

    - A ``new`` item whose identity matches a **prior-run baseline** item → re-classified
      ``update`` (recurring change), inheriting repetition_count + 1 so it can reach
      ``repeated`` (>= 3).
    - A ``new`` item whose identity matches only an **earlier item this run** (e.g. another
      language) → re-classified ``duplicate``.

    Only UPGRADES items Compare left as ``new`` — never downgrades. Mutates in place.
    Returns {"reconciled": n}.
    """
    # Baseline identities from PRIOR rows in the window. Current-run items were persisted
    # by Compare with law_id=NULL and act_ref=NULL (Law Match / L2 had not run yet), so
    # neither filter can return them — no item can match itself.
    window_iso = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT act_ref, law_id, repetition_count
           FROM news_items
           WHERE profile_id=? AND (law_id IS NOT NULL OR COALESCE(act_ref,'')!='')
             AND (first_seen_at >= ? OR last_seen_at >= ?)""",
        (profile_id, window_iso, window_iso),
    ).fetchall()
    baseline_by_law: Dict[Any, Any] = {}
    baseline_by_ref: Dict[str, Any] = {}
    for r in rows:
        if r["law_id"] is not None and r["law_id"] not in baseline_by_law:
            baseline_by_law[r["law_id"]] = dict(r)
        ref = _norm_act_ref(r["act_ref"])
        if ref and ref not in baseline_by_ref:
            baseline_by_ref[ref] = dict(r)

    def _identity(it):
        lid = it.get("law_id")
        ref = _norm_act_ref(it.get("act_ref"))
        return lid, ref

    # Deterministic order so "first sighting this run" is stable: published_at, then index.
    order = sorted(range(len(items)), key=lambda i: ((items[i].get("published_at") or ""), i))
    seen_law: Dict[Any, Any] = {}
    seen_ref: Dict[str, Any] = {}
    reconciled = 0

    def _register(it, lid, ref):
        if lid is not None:
            seen_law.setdefault(lid, it)
        if ref:
            seen_ref.setdefault(ref, it)

    for idx in order:
        it = items[idx]
        lid, ref = _identity(it)
        if lid is None and not ref:
            continue
        status = it.get("dedup_status") or "new"
        if status != "new":
            _register(it, lid, ref)
            continue

        baseline = (baseline_by_law.get(lid) if lid is not None else None) or \
                   (baseline_by_ref.get(ref) if ref else None)
        run_owner = (seen_law.get(lid) if lid is not None else None) or \
                    (seen_ref.get(ref) if ref else None)

        if baseline is not None:
            prior = int(baseline.get("repetition_count") or 0) + 1
            it["dedup_status"] = "update"
            it["repetition_count"] = prior
            it["repetition_status"] = "repeated" if prior >= 3 else "update"
            reconciled += 1
        elif run_owner is not None:
            owner_count = int(run_owner.get("repetition_count") or 0)
            it["dedup_status"] = "duplicate"
            it["repetition_count"] = owner_count
            it["repetition_status"] = "repeated" if owner_count >= 3 else "duplicate"
            reconciled += 1
        _register(it, lid, ref)

    if reconciled:
        print(f"↺ identity reconciliation: {reconciled} cross-language item(s) re-classified (law_id/act_ref)")
    return {"reconciled": reconciled}


def run_compare_news_agent(
    current_items: List[Dict[str, Any]],
    outputs_dir: Optional[str] = "outputs",
    glossary: Optional[Dict[str, str]] = None,
    language: Optional[str] = "en",
    skip_comparison: bool = False,
    skip_persist: bool = False,
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
        
        # Still persist items to DB for future baseline (unless dry-run)
        for item in current_items:
            item["dedup_status"] = "new"
        if not skip_persist:
            print("🗃️ Persisting current items to DB baseline...")
            for item in current_items:
                try:
                    rec = _build_item_record(item)
                    add_news_item(item.get("profile_id") or 1, rec)
                except Exception as e:
                    print(f"⚠️ Failed to upsert news item to DB: {e}")
        else:
            print("🧪 Dry-run: skipping DB persistence.")
        
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
        semantic_prior_count = 0  # repetition carried from a cosine-matched (reworded) prior
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
                    # A reworded re-announcement of a recurring change is a REPEAT, not a
                    # fresh update. Carry the matched prior's repetition_count so the ranker's
                    # REPEATED elevation can fire on a semantic (non-exact-key) match.
                    if 0 <= best_j < len(baseline_emb):
                        semantic_prior_count = int(
                            (baseline_items[best_j] or {}).get("repetition_count") or 0
                        )
                else:
                    classification = "new"

        item["dedup_status"] = classification
        # v3.2: REPEATED status — set based on how many times this entity has appeared.
        # Exact-key match (guid/url/hash/fingerprint) OR a semantic re-announcement both count.
        matched = _find_matched_baseline(item, by_source_id, by_url, by_sig, by_fp)
        exact_prior_count = int((matched or {}).get("repetition_count") or 0)
        prior_count = max(exact_prior_count, semantic_prior_count)
        item["repetition_count"] = prior_count
        if prior_count >= 3:
            item["repetition_status"] = "repeated"
        elif classification == "duplicate":
            item["repetition_status"] = "duplicate"
        elif classification == "update":
            item["repetition_status"] = "update"
        else:
            item["repetition_status"] = "new"
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
    if not skip_persist:
        print("🗃️ Persisting current items to DB baseline (with dedup_status)...")
        for item in current_items:
            try:
                rec = _build_item_record(item)
                add_news_item(item.get("profile_id") or 1, rec)
            except Exception as e:
                print(f"⚠️ Failed to upsert news item to DB: {e}")
    else:
        print("🧪 Dry-run: skipping DB persistence (nothing saved to news_items).")

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
