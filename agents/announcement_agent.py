"""
Announcement Agent (v3.13) — owns structure-building for the Announcement tab.

Title-first, English-normalized, incremental clustering. Runs ONLY on items in
announce_state='pending' (new or re-ranked/re-matched), so cost tracks the delta,
never the whole corpus.

Pipeline of one-word functions:
    Select → Title → Embed → Cluster → Assign → Compose → Persist

- Title  (PASS 1): per item, an English title grounded in L2 + RCM reference titles.
- Cluster: cosine on titles, guarded by act_ref (primary) and date proximity (fallback).
- Assign: join a draft announcement / attach to a frozen one (added_after_publish) /
          form a new draft with peers / new standalone.
- Compose (PASS 2): per resolved cluster, unified title + RCM body JSON.
- Persist: write news_announcements + update news_items membership/state.

Announcements are profile-scoped and persistent — 'done' (published) ones are frozen.
"""

import json
import re
from datetime import datetime

from agents.ai_cache import cached_chat
from agents.embeddings_util import get_embeddings, cosine
from agents.legal_event import same_legal_event, STRONG_SIM, _date_close as _event_date_close
from configurations import db

TITLE_COSINE_THRESHOLD = 0.85       # RCM-history title match (tracked vs net-new)
DATE_WINDOW_DAYS = 183              # ~6 months

# Verbatim 4th Introduction bullet mandated by the RCM template.
_DISCLAIMER = (
    "This information is based on legislation and regulations which could be subject "
    "to change at any time by the respective authorities. The information will be "
    "updated if required."
)


def _get_ai_client():
    from configurations.config_loader import creds
    from agents.sap_ai_client import SAPAICoreClient
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
    )


def _chat(prompt: str) -> str:
    def _call():
        client = _get_ai_client()
        r = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}], timeout=30.0
        )
        return r.choices[0].message.content.strip()
    raw = cached_chat(prompt, _call)
    raw = re.sub(r"^```json?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    return raw


# ---- reference titles ----

def _reference_titles(conn, profile_id: int, limit: int = 5) -> list[str]:
    rows = conn.execute(
        "SELECT regulation_title FROM rcm_reference_titles WHERE profile_id=? "
        "ORDER BY synced_at DESC LIMIT ?",
        (profile_id, limit),
    ).fetchall()
    return [r[0] for r in rows if r[0]]


# ---- PASS 1: English title ----

def _english_title(item: dict, ref_titles: list[str]) -> str:
    examples = "\n".join(f"- {t}" for t in ref_titles) or "(none available)"
    prompt = (
        "Produce a concise ENGLISH title (max 12 words) for this regulatory news item. "
        "Derive it from the specific act/regulation named in the content; do NOT invent "
        "generic phrases like 'New changes to...'. Follow the style of these official SAP "
        f"RCM titles:\n{examples}\n\n"
        f"Title: {item.get('title','')}\n"
        f"Summary: {(item.get('l2_summary') or item.get('content') or '')[:600]}\n"
        f"Act ref: {item.get('act_ref') or '(none)'}\n\n"
        'Return STRICT JSON only: {"title": "..."}'
    )
    try:
        parsed = json.loads(_chat(prompt))
        t = (parsed.get("title") or "").strip()
        if t:
            return t
    except Exception as e:
        print(f"    ⚠️  english_title failed: {e}")
    return (item.get("title") or "")[:120]


# ---- RCM Match (v3.17): pipeline-time entry point ----
# Per item, generate the RCM-grounded English title (PASS 1, moved earlier so Review
# grouping reuses it) and match it against the cached RCM reference titles to flag
# whether this regulation is already tracked in RCM.

def _persist_rcm(conn, items: list[dict], profile_id: int | None) -> None:
    """Persist english_title / proposed_rcm_title / rcm_match_status to news_items."""
    for it in items:
        vals = (it.get("english_title"), it.get("proposed_rcm_title"), it.get("rcm_match_status"))
        item_id = it.get("id")
        if item_id:
            conn.execute(
                "UPDATE news_items SET english_title=?, proposed_rcm_title=?, rcm_match_status=? WHERE id=?",
                (*vals, item_id),
            )
            continue
        src_type = it.get("source_type", "RSS")
        src_id = it.get("source_id") or it.get("guid") or it.get("tweet_id")
        url = it.get("url") or it.get("link")
        hash_sig = it.get("hash_signature")
        pid = it.get("profile_id") or profile_id
        if src_id and pid:
            conn.execute(
                "UPDATE news_items SET english_title=?, proposed_rcm_title=?, rcm_match_status=? "
                "WHERE profile_id=? AND source_type=? AND source_id=?",
                (*vals, pid, src_type, src_id),
            )
        elif url and pid:
            conn.execute(
                "UPDATE news_items SET english_title=?, proposed_rcm_title=?, rcm_match_status=? "
                "WHERE profile_id=? AND source_type=? AND url=?",
                (*vals, pid, src_type, url),
            )
        elif hash_sig and pid:
            conn.execute(
                "UPDATE news_items SET english_title=?, proposed_rcm_title=?, rcm_match_status=? "
                "WHERE profile_id=? AND source_type=? AND hash_signature=?",
                (*vals, pid, src_type, hash_sig),
            )
    conn.commit()


def match_rcm_titles(conn, profile_id: int, items: list[dict]) -> dict:
    """Per-item RCM Match: proposed_rcm_title (PASS 1) + tracked/net-new against cached titles.

    Runs in the pipeline (after Reconcile). Persists english_title / proposed_rcm_title /
    rcm_match_status so Review-time grouping reuses the titles instead of recomputing.
    """
    if not items:
        return {"matched": 0}
    ref_titles = _reference_titles(conn, profile_id, limit=50)
    for it in items:
        et = _english_title(it, ref_titles[:5])
        it["english_title"] = et
        it["proposed_rcm_title"] = et
    if ref_titles:
        ref_vecs = get_embeddings(ref_titles)
        item_vecs = get_embeddings([it["english_title"] for it in items])
        for it, iv in zip(items, item_vecs):
            best = max((cosine(iv, rv) for rv in ref_vecs), default=0.0)
            it["rcm_match_status"] = "tracked" if best >= TITLE_COSINE_THRESHOLD else "net-new"
    else:
        for it in items:
            it["rcm_match_status"] = None
    _persist_rcm(conn, items, profile_id)
    return {"matched": len(items)}


# ---- clustering guards ----

def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def _date_close(a: dict, b: dict) -> bool:
    da = _parse_date(a.get("effective_date") or a.get("published_at"))
    d_b = _parse_date(b.get("effective_date") or b.get("published_at"))
    if not da or not d_b:
        return True  # no date signal → don't block on date
    return abs((da - d_b).days) <= DATE_WINDOW_DAYS


def _same_group(item_a: dict, vec_a, item_b: dict, vec_b) -> bool:
    """Candidate → confirm (v3.29). `vec_*` are L2-summary embeddings.

    `law_id`/`act_ref` only NARROW candidates; `same_legal_event()` (L2 semantic core +
    corroborating article/date/authority) confirms they describe the same underlying event.
    Same law but different events → NOT grouped. When neither shares a law identity, fall
    back to a strong pure-semantic match + date proximity.
    """
    sim = cosine(vec_a, vec_b)
    la, lb = item_a.get("law_id"), item_b.get("law_id")
    ref_a = (item_a.get("act_ref") or "").strip().lower()
    ref_b = (item_b.get("act_ref") or "").strip().lower()
    candidate = (la is not None and la == lb) or (ref_a and ref_a == ref_b)
    if candidate:
        return same_legal_event(item_a, item_b, sim)   # confirm same event
    # No shared law identity → require a strong semantic match AND date proximity.
    return sim >= STRONG_SIM and _event_date_close(item_a, item_b)


# ---- PASS 2: RCM body ----

def _compose_rcm(cluster_items: list[dict], ref_titles: list[str]) -> dict:
    examples = "\n".join(f"- {t}" for t in ref_titles) or "(none available)"
    src_text = "\n".join(
        f"- {it.get('title','')}: {(it.get('l2_summary') or it.get('content') or '')[:400]} "
        f"[{it.get('publisher','')}, {(it.get('published_at') or '')[:10]}, ref={it.get('act_ref') or ''}]"
        for it in cluster_items
    )
    prompt = (
        "You are an SAP legal-compliance RCM editor. These news items describe the SAME "
        "regulatory change. Produce ONE announcement.\n"
        f"Reference RCM titles for naming style:\n{examples}\n\n"
        f"Items:\n{src_text}\n\n"
        "Return STRICT JSON only (no fences):\n"
        '{"title": "<unified English title, act-name based>", '
        '"introduction": ["This announcement contains information about the legal change '
        '<name> published on <date> by <authority>.", "The legal change is '
        '<mandatory|in draft phase|postponed>.", "The effective date is <date>.", '
        f'"{_DISCLAIMER}"], '
        '"business_background": ["<impacted business process / document / transaction type>"]}\n'
        "Rules: fill every angle bracket from the items; the 4th introduction bullet must be "
        "copied EXACTLY verbatim; business_background 1-3 concise bullets."
    )
    try:
        result = json.loads(_chat(prompt))
        if "introduction" not in result:
            raise ValueError("missing introduction")
        result.setdefault("business_background", [])
        if not (result.get("title") or "").strip():
            result["title"] = cluster_items[0].get("english_title") or cluster_items[0].get("title", "")
        return result
    except Exception as e:
        print(f"    ⚠️  compose_rcm failed: {e} — fallback")
        return {
            "title": cluster_items[0].get("english_title") or cluster_items[0].get("title", ""),
            "introduction": [(cluster_items[0].get("l2_summary") or "")],
            "business_background": [],
        }


def _source_links(cluster_items: list[dict]) -> list[dict]:
    return [
        {"text": it.get("publisher") or it.get("title") or "Source", "url": it.get("url") or ""}
        for it in cluster_items
    ]


def _first_published(cluster_items: list[dict]) -> str:
    dates = [(it.get("published_at") or "")[:10] for it in cluster_items if it.get("published_at")]
    return min(dates) if dates else ""


def _l2_text(it: dict) -> str:
    """Text used for the semantic-event embedding — the L2 summary (falls back to title)."""
    return (it.get("l2_summary") or it.get("english_title") or it.get("title") or "").strip()


def _compose_group_title(members: list[dict], ref_titles: list[str]) -> str:
    """AI: ONE unified English title for a confirmed same-event group. Title only (no body)."""
    examples = "\n".join(f"- {t}" for t in ref_titles) or "(none available)"
    src = "\n".join(
        f"- {m.get('english_title') or m.get('title','')}: {(m.get('l2_summary') or '')[:200]}"
        for m in members
    )
    prompt = (
        "You are an SAP legal-compliance RCM editor. These news items describe the SAME legal event. "
        "Produce ONE unified, act-name-based English title. Follow the style of these RCM titles:\n"
        f"{examples}\n\nItems:\n{src}\n\n"
        'Return STRICT JSON only: {"title": "..."}'
    )
    try:
        parsed = json.loads(_chat(prompt))
        t = (parsed.get("title") or "").strip()
        if t:
            return t
    except Exception as e:
        print(f"    ⚠️  compose_group_title failed: {e}")
    return members[0].get("english_title") or members[0].get("title", "")


def _ann_pseudo(conn, a: dict) -> dict:
    """Represent an existing announcement as a pseudo-item for `_same_group` (from a member row)."""
    try:
        ids = json.loads(a.get("item_ids_json") or "[]")
    except Exception:
        ids = []
    act, pub, law_id, l2, cited, auth = "", "", None, "", None, None
    if ids:
        ph = ",".join("?" * len(ids))
        r = conn.execute(
            f"SELECT act_ref, law_id, published_at, l2_summary, cited_article, authority_id "
            f"FROM news_items WHERE id IN ({ph}) LIMIT 1", ids
        ).fetchone()
        if r:
            act = r["act_ref"] or ""
            law_id = r["law_id"]
            pub = r["published_at"] or ""
            l2 = r["l2_summary"] or ""
            cited = r["cited_article"]
            auth = r["authority_id"]
    return {"act_ref": act, "law_id": law_id, "published_at": pub,
            "effective_date": a.get("first_published"), "l2_summary": l2,
            "cited_article": cited, "authority_id": auth}


# ---- main entry ----

def build(conn, profile_id: int, run_id: int) -> dict:
    """Incrementally process pending items into persistent announcements.

    Returns {processed, new_announcements, joined_draft, joined_frozen}.
    """
    pending = db.get_pending_announce_items(conn, profile_id)
    stats = {"processed": len(pending), "new_announcements": 0,
             "joined_draft": 0, "joined_frozen": 0}
    if not pending:
        return stats

    ref_titles = _reference_titles(conn, profile_id)

    # PASS 1 — English title per pending item (persisted as the clustering fingerprint).
    # v3.17: reuse the title the RCM Match pipeline step already produced; only compute
    # here for items that somehow lack one (e.g. older rows).
    for it in pending:
        if not it.get("english_title"):
            it["english_title"] = _english_title(it, ref_titles)
            if it.get("id"):
                conn.execute("UPDATE news_items SET english_title=? WHERE id=?",
                             (it["english_title"], int(it["id"])))

    # Grouping vectors = L2-SUMMARY embeddings (the semantic-event core), not titles.
    pending_vecs = get_embeddings([_l2_text(it) for it in pending])

    drafts = db.get_draft_announcements(conn, profile_id)
    done = db.get_done_announcements(conn, profile_id)
    existing = drafts + done
    pseudos = [_ann_pseudo(conn, a) for a in existing]
    existing_vecs = get_embeddings(
        [(pseudos[i].get("l2_summary") or existing[i].get("title") or "") for i in range(len(existing))]
    ) if existing else []

    assigned = [False] * len(pending)

    # Assign each pending item to an existing announcement it belongs to (candidate → confirm
    # via _same_group). Among multiple confirmed matches, pick the highest-cosine one.
    for i, it in enumerate(pending):
        best_idx, best_cos = -1, -1.0
        for j, p in enumerate(pseudos):
            if _same_group(it, pending_vecs[i], p, existing_vecs[j]):
                c = cosine(pending_vecs[i], existing_vecs[j])
                if c > best_cos:
                    best_cos, best_idx = c, j
        if best_idx >= 0:
            a = existing[best_idx]
            is_done = a.get("status") == "done"
            db.append_item_to_announcement(conn, int(a["id"]), int(it["id"]), added_after_publish=is_done)
            if is_done:
                stats["joined_frozen"] += 1
            else:
                _regenerate_draft(conn, profile_id, int(a["id"]), ref_titles)
                stats["joined_draft"] += 1
            assigned[i] = True

    # Cluster the still-unassigned pending items among themselves (same candidate→confirm rule)
    remaining = [(i, it) for i, it in enumerate(pending) if not assigned[i]]
    clusters: list[list[int]] = []
    for i, it in remaining:
        placed = False
        for cl in clusters:
            rep_i = cl[0]
            if _same_group(it, pending_vecs[i], pending[rep_i], pending_vecs[rep_i]):
                cl.append(i)
                placed = True
                break
        if not placed:
            clusters.append([i])

    for cl in clusters:
        cluster_items = [pending[i] for i in cl]
        title = _compose_group_title(cluster_items, ref_titles)   # AI title only
        item_ids = [int(it["id"]) for it in cluster_items if it.get("id")]
        ann_id = db.insert_announcement(
            conn, profile_id, run_id,
            topic_label=_topic_label(cluster_items),
            title=title,
            rcm_json="",   # v3.29: RCM body deferred — generated on-demand at "Preview for RCM"
            first_published=_first_published(cluster_items),
            source_links=_source_links(cluster_items),
            item_ids=item_ids,
        )
        for iid in item_ids:
            db.set_item_assigned(conn, iid, ann_id)
        stats["new_announcements"] += 1

    conn.commit()
    return stats


def _topic_label(cluster_items: list[dict]) -> str:
    """Pick a display topic label from the cluster's glossary matches (first non-General)."""
    for it in cluster_items:
        try:
            labels = json.loads(it.get("topic_label") or "[]")
        except Exception:
            labels = []
        for lbl in labels:
            if lbl and lbl != "General":
                return lbl
    return "General"


def _regenerate_draft(conn, profile_id: int, announcement_id: int, ref_titles: list[str]) -> None:
    """Recompute a draft announcement's unified TITLE from full membership (body deferred to Preview)."""
    row = conn.execute(
        "SELECT item_ids_json FROM news_announcements WHERE id=?", (announcement_id,)
    ).fetchone()
    try:
        ids = json.loads(row["item_ids_json"]) if row else []
    except Exception:
        ids = []
    if not ids:
        return
    ph = ",".join("?" * len(ids))
    members = [dict(r) for r in conn.execute(
        f"SELECT * FROM news_items WHERE id IN ({ph})", ids
    ).fetchall()]
    title = _compose_group_title(members, ref_titles)
    db.update_announcement_content(
        conn, announcement_id,
        title=title,
        rcm_json="",   # v3.29: body regenerated on-demand at Preview, not here
        source_links=_source_links(members),
        item_ids=ids,
        first_published=_first_published(members),
    )
