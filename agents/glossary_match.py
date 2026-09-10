"""
Glossary Match stage (part of the Analyze phase).

Deterministic glossary-keyword matcher. Assigns topic_label (JSON array) to each item
by matching glossary terms against item title + content. No AI calls.

Topic label format: JSON array of matching glossary term strings, e.g. '["Labour Law", "Pension"]'.
Items with no glossary match receive '["General"]'.
"""

import json
import re
import sqlite3


# v3.13: best-effort law/act/gazette reference extraction from L1 text (title + description).
# L2 fetch is the PRIMARY source of act_ref; this only catches references that already
# appear in the headline/description (e.g. "Law No. 7555", "OVP 2027-2029",
# "Official Gazette No. 32765"), so clustering has an early key when L2 confirms.
_ACT_REF_PATTERNS = [
    r"\b(?:Law|Act|Decree|Regulation|Directive)\s+No\.?\s*\d+[\w/-]*",
    r"\b(?:Official\s+Gazette)\s+No\.?\s*\d+[\w/-]*",
    r"\b\d{3,5}\s+Say[ıi]l[ıi]\b[\w\s.]*",     # Turkish "NNNN Sayılı ..." act reference
    r"\b[A-ZÇĞİÖŞÜ]{2,6}\s*\(\s*\d{4}\s*[–-]\s*\d{4}\s*\)",  # e.g. OVP (2027-2029)
]


def extract_act_ref(text: str) -> str:
    """Return the first law/act/gazette reference found in text, or "" if none."""
    if not text:
        return ""
    for pat in _ACT_REF_PATTERNS:
        m = re.search(pat, text)
        if m:
            return m.group(0).strip()
    return ""


def _load_match_rules(conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    """Return match rules as [{match: str, is_regex: bool, label: str}].

    The `label` is the term's canonical Glossary Label name when it has one, else the
    term itself (unlabeled terms match on themselves). Covers each term, its synonyms,
    and its regex patterns — all inheriting the term's label.
    """
    rows = conn.execute(
        """SELECT t.id AS term_id, t.term AS term, l.name AS label_name
           FROM glossary_terms t
           LEFT JOIN glossary_labels l ON l.id = t.label_id
           WHERE t.profile_id=?""",
        (profile_id,),
    ).fetchall()
    rules: list[dict] = []
    for r in rows:
        label = r["label_name"] or r["term"]
        rules.append({"match": r["term"], "is_regex": False, "label": label})
        for syn in conn.execute(
            "SELECT synonym FROM glossary_synonyms WHERE term_id=?", (r["term_id"],)
        ).fetchall():
            rules.append({"match": syn["synonym"], "is_regex": False, "label": label})
        for pat in conn.execute(
            "SELECT regex FROM glossary_patterns WHERE term_id=?", (r["term_id"],)
        ).fetchall():
            rules.append({"match": pat["regex"], "is_regex": True, "label": label})
    return rules


def _norm(s: str) -> str:
    """Lowercase for case-insensitive matching, Turkish-safe.

    Python's ``'İ'.lower()`` yields ``'i' + U+0307`` (combining dot above), so a
    glossary term like ``istihdam`` would never match text containing ``İstihdam``.
    Stripping U+0307 fixes that; it is safe for English and ü/ş/ğ/ç/ö, none of
    which contain that combining mark.
    """
    return s.lower().replace("̇", "")


def match_glossary(items: list[dict], conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    """Assign topic_label to each item via glossary matching.

    Matching is case-insensitive substring (or regex) on title + content. Each item can
    match terms across several labels; the DISTINCT canonical **label names** are stored
    (not the raw terms), so any language/spelling of a term collapses to one label and
    announcements about the same entity group together.
    """
    rules = _load_match_rules(conn, profile_id)
    for item in items:
        # v3.16: Glossary Match now runs AFTER L2 Fetch, so match against the full-article
        # summary too (not just the headline/snippet) for far better coverage.
        raw = f"{item.get('title', '')} {item.get('content', '')} {item.get('l2_summary', '') or ''}"
        text = _norm(raw)
        labels: list[str] = []
        for rule in rules:
            hit = False
            if rule["is_regex"]:
                try:
                    hit = re.search(rule["match"], raw, re.IGNORECASE) is not None
                except re.error:
                    hit = False
            else:
                hit = _norm(rule["match"]) in text
            if hit and rule["label"] not in labels:
                labels.append(rule["label"])
        item["topic_label"] = json.dumps(labels) if labels else json.dumps(["General"])
        # v3.13: best-effort act_ref from L1 (title + description). Only set when found —
        # L2 fetch is the primary source and must not be overwritten by an empty result.
        ref = extract_act_ref(raw)
        if ref:
            item["act_ref"] = ref
    return items


def save_topic_labels(items: list[dict], conn: sqlite3.Connection, profile_id: int | None = None) -> None:
    """Persist topic_label for each item to news_items.

    Items from the pipeline may not carry a DB `id`; fall back to
    source_id / url / hash_signature identifiers (same strategy as rank persist).
    """
    for item in items:
        label = item.get("topic_label")
        if label is None:
            continue
        item_id = item.get("id")
        if item_id:
            conn.execute("UPDATE news_items SET topic_label=? WHERE id=?", (label, item_id))
            continue
        src_type = item.get("source_type", "RSS")
        src_id   = item.get("source_id") or item.get("guid") or item.get("tweet_id")
        url      = item.get("url") or item.get("link")
        hash_sig = item.get("hash_signature")
        pid      = item.get("profile_id") or profile_id
        if src_id and pid:
            conn.execute(
                "UPDATE news_items SET topic_label=? WHERE profile_id=? AND source_type=? AND source_id=?",
                (label, pid, src_type, src_id),
            )
        elif url and pid:
            conn.execute(
                "UPDATE news_items SET topic_label=? WHERE profile_id=? AND source_type=? AND url=?",
                (label, pid, src_type, url),
            )
        elif hash_sig and pid:
            conn.execute(
                "UPDATE news_items SET topic_label=? WHERE profile_id=? AND source_type=? AND hash_signature=?",
                (label, pid, src_type, hash_sig),
            )
    conn.commit()


def flag_glossary_gaps(items: list[dict], conn: sqlite3.Connection, profile_id: int | None = None) -> None:
    """Set glossary_gap=1 for items with significance_rank >= 3 and no real glossary match.

    topic_label == '["General"]' means the tagger found zero glossary term matches.
    NULL topic_label (item was never tagged) is never flagged. Uses the same
    id / source_id / url / hash_signature fallback persistence as save_topic_labels().
    """
    GENERAL = json.dumps(["General"])
    for item in items:
        rank = int(item.get("significance_rank") or 0)
        label = item.get("topic_label")
        is_gap = 1 if (rank >= 3 and label == GENERAL) else 0
        item["glossary_gap"] = is_gap

        item_id = item.get("id")
        src_type = item.get("source_type", "RSS")
        src_id   = item.get("source_id") or item.get("guid") or item.get("tweet_id")
        url      = item.get("url") or item.get("link")
        hash_sig = item.get("hash_signature")
        pid      = item.get("profile_id") or profile_id

        if item_id:
            conn.execute("UPDATE news_items SET glossary_gap=? WHERE id=?", (is_gap, item_id))
        elif src_id and pid:
            conn.execute(
                "UPDATE news_items SET glossary_gap=? WHERE profile_id=? AND source_type=? AND source_id=?",
                (is_gap, pid, src_type, src_id),
            )
        elif url and pid:
            conn.execute(
                "UPDATE news_items SET glossary_gap=? WHERE profile_id=? AND source_type=? AND url=?",
                (is_gap, pid, src_type, url),
            )
        elif hash_sig and pid:
            conn.execute(
                "UPDATE news_items SET glossary_gap=? WHERE profile_id=? AND source_type=? AND hash_signature=?",
                (is_gap, pid, src_type, hash_sig),
            )
    conn.commit()


def rematch_items_for_profile(conn: sqlite3.Connection, profile_id: int) -> int:
    """Re-run Glossary Match over ALL of a profile's news_items and rewrite topic_label.

    Used after seeding/editing Glossary Labels so existing items carry canonical labels.
    Re-flags glossary gaps and marks changed items pending for announcement regrouping.
    Returns the number of items re-matched.
    """
    rows = conn.execute(
        "SELECT * FROM news_items WHERE profile_id=?", (profile_id,)
    ).fetchall()
    if not rows:
        return 0
    items = [dict(r) for r in rows]
    match_glossary(items, conn, profile_id)
    save_topic_labels(items, conn, profile_id)
    flag_glossary_gaps(items, conn, profile_id)
    from configurations.db import mark_items_pending
    mark_items_pending(conn, [it["id"] for it in items if it.get("id")])
    conn.commit()
    return len(items)
