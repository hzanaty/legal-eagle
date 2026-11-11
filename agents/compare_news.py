import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from configurations.config_loader import creds, add_news_item, get_weekly_baseline, get_baseline_days
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
_BASELINE_DAYS_DEFAULT = 7  # fallback; per-profile override via settings key "baseline_days"


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


def reconcile_by_act_ref(items, conn, profile_id, days: int = None):
    """Post-L2/Law-Match repetition reconciliation (v3.91).

    Identity is language-independent but only known after L2 + Law Match, so this runs
    late. The primary key is the resolved **law_id** (registry law); ``act_ref`` is the
    fallback when no law resolved. Compare runs *before* L2/Law-Match, so a Turkish and
    an English article about the same law both pass as ``new`` there. Here:

    - law_id/act_ref match narrows candidates; ``same_legal_event()`` confirms the same
      underlying legal development via L2 semantic similarity + corroborators.
    - A confirmed match → ``repetition_status = "repeated"`` immediately, regardless of
      prior occurrence count.
    - ``dedup_status`` is never changed; only ``repetition_status`` is updated.
    - If embeddings are unavailable, NEW is preserved — no false repetition on AI outage.
    - All candidates under the same law_id/act_ref are checked, not just the first, so
      distinct legal developments under the same law can each be recognized.

    Only upgrades items Compare left as ``new`` — never downgrades. Mutates in place.
    Returns {"reconciled": n}.
    """
    if days is None:
        from configurations.db import get_setting as _gs
        try:
            days = max(1, int(_gs(conn, profile_id, "baseline_days", "7") or 7))
        except (TypeError, ValueError):
            days = _BASELINE_DAYS_DEFAULT
    # Baseline identities from PRIOR rows in the window. Current-run items were persisted
    # by Compare with law_id=NULL and act_ref=NULL (Law Match / L2 had not run yet), so
    # neither filter can return them — no item can match itself.
    window_iso = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT act_ref, law_id, repetition_count, l2_summary, cited_article,
                  authority_id, published_at, effective_date, title
           FROM news_items
           WHERE profile_id=? AND (law_id IS NOT NULL OR COALESCE(act_ref,'')!='')
             AND (first_seen_at >= ? OR last_seen_at >= ?)""",
        (profile_id, window_iso, window_iso),
    ).fetchall()
    # Keep ALL candidates per law_id / act_ref so distinct events under the same law
    # can each be recognized separately; share the dict object for O(1) dedup below.
    baseline_by_law: Dict[Any, List] = {}
    baseline_by_ref: Dict[str, List] = {}
    for r in rows:
        d = dict(r)
        if r["law_id"] is not None:
            baseline_by_law.setdefault(r["law_id"], []).append(d)
        ref = _norm_act_ref(r["act_ref"])
        if ref:
            baseline_by_ref.setdefault(ref, []).append(d)

    def _identity(it):
        lid = it.get("law_id")
        ref = _norm_act_ref(it.get("act_ref"))
        return lid, ref

    # law_id/act_ref only NARROW candidates; confirm same legal event via L2 semantic
    # similarity (core) + corroborators. Embed once.
    from agents.legal_event import same_legal_event
    from agents.embeddings_util import get_embeddings, cosine as _cos
    _base_dicts: List = []
    _seen_ids: set = set()
    for _lst in list(baseline_by_law.values()) + list(baseline_by_ref.values()):
        for _d in _lst:
            if id(_d) not in _seen_ids:
                _seen_ids.add(id(_d))
                _base_dicts.append(_d)
    _l2 = lambda d: (d.get("l2_summary") or d.get("title") or "").strip()
    _have_vecs = False
    try:
        _embs = get_embeddings([_l2(it) for it in items] + [_l2(b) for b in _base_dicts])
        for _i, _it in enumerate(items):
            _it["_l2vec"] = _embs[_i]
        for _k, _b in enumerate(_base_dicts):
            _b["_l2vec"] = _embs[len(items) + _k]
        _have_vecs = True
    except Exception as _e:
        print(f"    ⚠️  reconcile embeddings unavailable ({type(_e).__name__}); preserving NEW (no false repetition on AI outage)")

    def _confirm(a, b) -> bool:
        va, vb = a.get("_l2vec"), b.get("_l2vec")
        if not _have_vecs or va is None or vb is None:
            return False  # embeddings unavailable → preserve NEW (rule 8)
        return same_legal_event(a, b, _cos(va, vb))

    def _first_confirmed(it, candidates) -> bool:
        """Return True when any candidate confirms the same legal event."""
        for c in candidates:
            if _confirm(it, c):
                return True
        return False

    # Deterministic order so "first sighting this run" is stable: published_at, then index.
    order = sorted(range(len(items)), key=lambda i: ((items[i].get("published_at") or ""), i))
    seen_law: Dict[Any, List] = {}
    seen_ref: Dict[str, List] = {}
    reconciled = 0

    def _register(it, lid, ref):
        if lid is not None:
            seen_law.setdefault(lid, []).append(it)
        if ref:
            seen_ref.setdefault(ref, []).append(it)

    for idx in order:
        it = items[idx]
        lid, ref = _identity(it)
        if lid is None and not ref:
            continue
        status = it.get("dedup_status") or "new"
        if status != "new":
            _register(it, lid, ref)
            continue

        # Gather unique baseline candidates (prior runs within window)
        _seen_cid: set = set()
        base_candidates: List = []
        for _c in (baseline_by_law.get(lid) or []) + (baseline_by_ref.get(ref) or [] if ref else []):
            if id(_c) not in _seen_cid:
                _seen_cid.add(id(_c))
                base_candidates.append(_c)

        # Gather unique same-run candidates
        _seen_rid: set = set()
        run_candidates: List = []
        for _c in (seen_law.get(lid) or []) + (seen_ref.get(ref) or [] if ref else []):
            if id(_c) not in _seen_rid:
                _seen_rid.add(id(_c))
                run_candidates.append(_c)

        if _first_confirmed(it, base_candidates):
            # Prior-run confirmed same legal event → REPEATED immediately (rule 4)
            # dedup_status stays "new" per rule 6; no occurrence-count threshold
            it["repetition_status"] = "repeated"
            reconciled += 1
        elif _first_confirmed(it, run_candidates):
            # Same-run confirmed same legal event → REPEATED (rule 4)
            # dedup_status stays "new" per rule 6
            it["repetition_status"] = "repeated"
            it["_repeated_followup"] = True
            reconciled += 1

        _register(it, lid, ref)

    # Clean the transient embedding vectors off the items.
    for _it in items:
        _it.pop("_l2vec", None)

    if reconciled:
        print(f"↺ identity reconciliation: {reconciled} same-event item(s) re-classified as REPEATED (law_id/act_ref → confirmed)")
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

    # Load baseline FIRST (before persisting current items)
    # This ensures we can detect a truly empty baseline for the "no history" shortcut
    profile_id = current_items[0].get("profile_id") or 1 if current_items else 1
    _baseline_days = get_baseline_days(profile_id)
    baseline_items = get_weekly_baseline(profile_id, days=_baseline_days)
    print(f"📚 Baseline size: {len(baseline_items)} (profile_id={profile_id}, days={_baseline_days})")
    
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

    # Sort oldest-first so the original article is processed before follow-ups.
    # This ensures the earlier article is registered as NEW and the later article
    # is correctly identified as a follow-up (REPEATED) rather than a duplicate.
    try:
        from agents.news_filter import parse_date_string as _pds
        from datetime import datetime as _dt_cls
        current_items.sort(
            key=lambda it: _pds(it.get("published_at") or it.get("date") or "") or _dt_cls.min
        )
    except Exception:
        pass

    # v3.91 (Task 4A): Step 4 classifies strictly as NEW or DUPLICATE using reliable
    # technical identity only (source_id, URL, content hash). Cosine similarity and
    # entity fingerprinting are intentionally excluded — legal-event identity belongs
    # to Reconcile (Step 8). REPEATED is never assigned here.
    new_items: List[Dict[str, Any]] = []
    update_items: List[Dict[str, Any]] = []  # always empty; preserved for Task 4B controller compat

    # Same-run dedup sets — initialised from baseline keys so a same-run re-submission
    # of a previously-seen article is still caught by source identity / URL / hash.
    seen_source_ids = set(by_source_id.keys())
    seen_urls = set(by_url.keys())
    seen_sigs = set(by_sig.keys())

    for i, item in enumerate(current_items):
        curr_sig = hash_signature(item.get("title", ""), item.get("content", ""))
        curr_fp = entity_fingerprint(item.get("title", ""), item.get("content", ""))
        url = item.get("link") or item.get("url")
        source_id = item.get("tweet_id") or item.get("guid") or item.get("id")

        is_dup = (
            (source_id and str(source_id) in seen_source_ids)
            or (url and str(url) in seen_urls)
            or (curr_sig and curr_sig in seen_sigs)
        )

        classification = "duplicate" if is_dup else "new"
        item["dedup_status"] = classification

        matched = _find_matched_baseline(item, by_source_id, by_url, by_sig, by_fp)
        item["repetition_count"] = int((matched or {}).get("repetition_count") or 0)
        item["repetition_status"] = "duplicate" if classification == "duplicate" else "new"

        if classification == "new":
            new_items.append(item)
            seen_source_ids.add(str(source_id)) if source_id else None
            seen_urls.add(str(url)) if url else None
            seen_sigs.add(curr_sig) if curr_sig else None

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
    print(f"✅ New: {len(new_items)} | Duplicates (kept): {dup_count}")

    # Save single rolling snapshot for manual inspection
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(current_items, f, ensure_ascii=False, indent=2)
        print(f"💾 Updated snapshot → {snapshot_path}")
    except Exception as e:
        print(f"⚠️ Failed to write snapshot: {e}")

    return {"new_items": new_items, "update_items": update_items}
