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
from configurations import db

TITLE_COSINE_THRESHOLD = 0.85       # merge if titles are at least this similar
DATE_WINDOW_DAYS = 183              # ~6 months, fallback guard when act_ref is absent

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
    """Merge guard: act-identity is primary, title cosine + date is the fallback.

    If both items carry an act_ref, that reference IS the identity signal — equal
    act_ref merges them (this is what makes cross-language items group: same law,
    different language/title wording). Only when an act_ref is missing do we fall
    back to requiring title cosine >= threshold AND date proximity.
    """
    ref_a = (item_a.get("act_ref") or "").strip().lower()
    ref_b = (item_b.get("act_ref") or "").strip().lower()
    if ref_a and ref_b:
        return ref_a == ref_b          # PRIMARY: same act → same group (title wording irrelevant)
    # FALLBACK: no act identifier on one side → need similar titles AND close dates.
    if cosine(vec_a, vec_b) < TITLE_COSINE_THRESHOLD:
        return False
    return _date_close(item_a, item_b)


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

    # PASS 1 — English title per pending item (persisted as the clustering fingerprint)
    for it in pending:
        it["english_title"] = _english_title(it, ref_titles)
        if it.get("id"):
            conn.execute("UPDATE news_items SET english_title=? WHERE id=?",
                         (it["english_title"], int(it["id"])))

    # Embed pending titles + existing announcement titles
    pending_vecs = get_embeddings([it["english_title"] for it in pending])

    drafts = db.get_draft_announcements(conn, profile_id)
    done = db.get_done_announcements(conn, profile_id)
    existing = drafts + done
    existing_vecs = get_embeddings([a.get("title") or "" for a in existing]) if existing else []

    # Represent each existing announcement as a pseudo-item for the guard (act_ref from any member)
    def _ann_pseudo(a: dict) -> dict:
        try:
            ids = json.loads(a.get("item_ids_json") or "[]")
        except Exception:
            ids = []
        act = ""
        pub = ""
        if ids:
            ph = ",".join("?" * len(ids))
            r = conn.execute(
                f"SELECT act_ref, published_at FROM news_items WHERE id IN ({ph}) "
                "AND act_ref IS NOT NULL LIMIT 1", ids
            ).fetchone()
            if r:
                act, pub = r["act_ref"] or "", r["published_at"] or ""
        return {"act_ref": act, "published_at": pub, "effective_date": a.get("first_published")}

    assigned = [False] * len(pending)

    # Assign each pending item to an existing announcement if it matches one.
    # _same_group already encodes the merge policy (act-identity primary); among
    # multiple matches pick the highest-cosine one, but do not re-impose a floor.
    for i, it in enumerate(pending):
        best_idx, best_cos = -1, -1.0
        for j, a in enumerate(existing):
            if _same_group(it, pending_vecs[i], _ann_pseudo(a), existing_vecs[j]):
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
                # draft grew → regenerate its title/body from full membership
                _regenerate_draft(conn, profile_id, int(a["id"]), ref_titles)
                stats["joined_draft"] += 1
            assigned[i] = True

    # Cluster the still-unassigned pending items among themselves
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
        rcm = _compose_rcm(cluster_items, ref_titles)
        item_ids = [int(it["id"]) for it in cluster_items if it.get("id")]
        ann_id = db.insert_announcement(
            conn, profile_id, run_id,
            topic_label=_topic_label(cluster_items),
            title=rcm.get("title", ""),
            rcm_json=json.dumps(rcm),
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
    """Recompute a draft announcement's title + RCM body from its full current membership."""
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
    rcm = _compose_rcm(members, ref_titles)
    db.update_announcement_content(
        conn, announcement_id,
        title=rcm.get("title", ""),
        rcm_json=json.dumps(rcm),
        source_links=_source_links(members),
        item_ids=ids,
        first_published=_first_published(members),
    )
