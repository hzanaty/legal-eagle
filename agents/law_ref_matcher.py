"""
Law Match stage (v3.16) — deterministic resolver of a news item's cited law to the
per-profile Law Reference registry.

Runs AFTER L2 Fetch (which produces `law_primary`) and Glossary Match, BEFORE Reconcile.
For each item it resolves the cited law → a registry `law_id` (number-first, then
name_en/name_native), the specific `cited_article` (metadata), authority (from the
matched law), and a `law_ref_status`:
    - 'registered' : resolved to a law in the registry
    - 'suggested'  : a law was cited but is not registered (the law-ref gap signal)
    - None         : no law cited (e.g. a program/decision-only item)

`law_id` becomes the primary cross-language grouping identity used by Reconcile and
the announcement agent. No AI calls — fully deterministic. Mirrors glossary_match.py.
"""

import re
import sqlite3

from agents.glossary_match import _norm  # Turkish-safe lowercasing

# Article/provision phrase inside a law citation (English — law_primary is English).
_ARTICLE_RE = re.compile(r"((?:temporary\s+|provisional\s+)?article\s+\d+)", re.IGNORECASE)
# First significant law number (3–5 digits) — law numbers, not article numbers (which are small).
_NUMBER_RE = re.compile(r"\b(\d{3,5})\b")


def _extract_number(text: str) -> str:
    m = _NUMBER_RE.search(text or "")
    return m.group(1) if m else ""


def _extract_article(text: str) -> str:
    m = _ARTICLE_RE.search(text or "")
    return m.group(1).strip() if m else ""


def _load_laws(conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name_en, name_native, law_number, authority_id "
        "FROM law_refs WHERE profile_id=?",
        (profile_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def match_law_refs(items: list[dict], conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    """Resolve each item's cited law → law_id (+ authority, cited_article, law_ref_status)."""
    laws = _load_laws(conn, profile_id)
    by_number = {str(l["law_number"]).strip(): l for l in laws if l.get("law_number")}
    # (law, normalized name_en, normalized name_native) for the name-fallback pass.
    named = [(l, _norm(l.get("name_en") or ""), _norm(l.get("name_native") or "")) for l in laws]

    for item in items:
        cited = (item.get("law_primary") or item.get("act_ref") or "").strip()
        item["cited_article"] = _extract_article(cited)
        law = None
        if cited:
            num = _extract_number(cited)
            if num and num in by_number:
                law = by_number[num]
            if law is None:
                nc = _norm(cited)
                for l, nen, nnat in named:
                    if (nen and nen in nc) or (nnat and nnat in nc):
                        law = l
                        break
        if law is not None:
            item["law_id"] = law["id"]
            item["law_ref_status"] = "registered"
            if law.get("authority_id"):
                # Law-derived authority wins (more reliable than feed inference).
                item["authority_id"] = law["authority_id"]
                item["authority_status"] = "law"
        elif cited:
            item["law_id"] = None
            item["law_ref_status"] = "suggested"   # cited but unregistered → law-ref gap
        else:
            item["law_id"] = None
            item["law_ref_status"] = None
    return items


def save_law_matches(items: list[dict], conn: sqlite3.Connection, profile_id: int | None = None) -> None:
    """Persist law_id / law_ref_status / cited_article to news_items.

    Uses the same id / source_id / url / hash fallback as glossary_match.save_topic_labels
    (pipeline items may not carry a DB id yet).
    """
    for item in items:
        if "law_ref_status" not in item and "law_id" not in item:
            continue
        law_id = item.get("law_id")
        status = item.get("law_ref_status")
        article = item.get("cited_article")
        item_id = item.get("id")
        if item_id:
            conn.execute(
                "UPDATE news_items SET law_id=?, law_ref_status=?, cited_article=? WHERE id=?",
                (law_id, status, article, item_id),
            )
            continue
        src_type = item.get("source_type", "RSS")
        src_id = item.get("source_id") or item.get("guid") or item.get("tweet_id")
        url = item.get("url") or item.get("link")
        hash_sig = item.get("hash_signature")
        pid = item.get("profile_id") or profile_id
        if src_id and pid:
            conn.execute(
                "UPDATE news_items SET law_id=?, law_ref_status=?, cited_article=? "
                "WHERE profile_id=? AND source_type=? AND source_id=?",
                (law_id, status, article, pid, src_type, src_id),
            )
        elif url and pid:
            conn.execute(
                "UPDATE news_items SET law_id=?, law_ref_status=?, cited_article=? "
                "WHERE profile_id=? AND source_type=? AND url=?",
                (law_id, status, article, pid, src_type, url),
            )
        elif hash_sig and pid:
            conn.execute(
                "UPDATE news_items SET law_id=?, law_ref_status=?, cited_article=? "
                "WHERE profile_id=? AND source_type=? AND hash_signature=?",
                (law_id, status, article, pid, src_type, hash_sig),
            )
    conn.commit()
