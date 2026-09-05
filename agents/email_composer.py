"""
Email Composer — V2 AI Digest (v3.3)

Generates an HTML digest email from email_eligible news items.
Grouping: Authority (outer) → Topic Label (inner).
One AI call per authority+topic group to detect announcements.
Writes rows to news_announcements table.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from agents.ai_cache import cached_chat


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


def _call_ai_for_group(items: list[dict], language: str) -> list[dict]:
    """Ask AI to detect aspects within a topic group.

    Returns list of aspect dicts:
      {title, summary, first_publish_date, source_links: [{text, url}]}
    Falls back to a single synthetic aspect if AI unavailable.
    """
    items_text = ""
    for i, it in enumerate(items, 1):
        pub = it.get("published_at") or it.get("first_seen_at") or ""
        items_text += (
            f'{i}. Title: "{it.get("title", "")}"\n'
            f'   Content: "{(it.get("content") or "")[:400]}"\n'
            f'   URL: {it.get("url") or ""}\n'
            f'   Published: {pub[:10] if pub else "unknown"}\n\n'
        )

    prompt = (
        f"You are a legal compliance newsletter editor. "
        f"Write in {language}.\n\n"
        "The following news items all belong to the same regulatory topic. "
        "Detect distinct legal aspects (sub-topics) and for each aspect write:\n"
        "  - A concise title (max 12 words)\n"
        "  - A 2–4 sentence announcement summary covering: what changed, why it matters, any deadline or effective date\n"
        "  - The earliest publish date among items in this aspect\n"
        "  - The source links relevant to this aspect\n\n"
        f"Items:\n{items_text}"
        "Respond with valid JSON only — no markdown fences:\n"
        '{"aspects": [{"title": "...", "summary": "...", "first_publish_date": "YYYY-MM-DD or empty string", '
        '"source_links": [{"text": "...", "url": "..."}]}]}'
    )

    def _call():
        client = _get_ai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        return response.choices[0].message.content.strip()


    try:
        raw = cached_chat(prompt, _call)
        # Strip optional markdown fences
        raw = re.sub(r"^```json?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        parsed = json.loads(raw)
        aspects = parsed.get("aspects") or []
        if aspects:
            return aspects
    except Exception as e:
        print(f"    ⚠️  AI aspect call failed: {e}")

    # Fallback: single aspect from first item
    first = items[0]
    pub = (first.get("published_at") or first.get("first_seen_at") or "")[:10]
    return [
        {
            "title": first.get("title", ""),
            "summary": first.get("content", ""),
            "first_publish_date": pub,
            "source_links": [{"text": first.get("publisher") or "Source", "url": first.get("url") or ""}],
        }
    ]


def _get_authority_name(conn: sqlite3.Connection, authority_id: int | None) -> str:
    if not authority_id:
        return "Other"
    row = conn.execute(
        "SELECT name FROM authorities WHERE id=?", (authority_id,)
    ).fetchone()
    return row["name"] if row else "Other"


def _get_profile_language(conn: sqlite3.Connection, profile_id: int) -> str:
    row = conn.execute(
        "SELECT language FROM profiles WHERE id=?", (profile_id,)
    ).fetchone()
    return (row["language"] if row else "en") or "en"


def _save_announcement(
    conn: sqlite3.Connection,
    run_id: int,
    topic_label: str,
    aspect: dict,
    item_ids: list[int],
) -> None:
    conn.execute(
        """
        INSERT INTO news_announcements(run_id, topic_label, title, announcement_md,
                                 first_published, source_links_json, item_ids_json)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            run_id,
            topic_label,
            aspect.get("title", ""),
            aspect.get("summary", ""),
            aspect.get("first_publish_date", ""),
            json.dumps(aspect.get("source_links") or []),
            json.dumps(item_ids),
        ),
    )


def _render_authority_row(name: str, is_inferred: bool) -> str:
    inferred_badge = (
        '<span style="font-size:9px;font-weight:400;color:#aaaaaa;'
        'margin-left:6px;text-transform:none;">(authority inferred ✦)</span>'
        if is_inferred
        else ""
    )
    return (
        '<div style="font-size:10px;font-weight:700;letter-spacing:1.5px;'
        "text-transform:uppercase;color:#888888;"
        'border-bottom:1px solid #dddddd;padding-bottom:6px;margin-bottom:14px;">'
        f"{name}{inferred_badge}"
        "</div>"
    )


def _rank_badge(rank: int) -> str:
    if rank >= 4:
        return (' &nbsp;·&nbsp; <span style="background:#e8f5e9;color:#107e3e;'
                'padding:1px 6px;border-radius:8px;font-size:10px;font-weight:600;">'
                f'Rank {rank}</span>')
    if rank == 3:
        return (' &nbsp;·&nbsp; <span style="background:#fff3cd;color:#856404;'
                'padding:1px 6px;border-radius:8px;font-size:10px;font-weight:600;">'
                f'Rank {rank}</span>')
    return ""


def _render_topic_block(label: str, aspects: list[dict], max_rank: int = 0) -> str:
    header = (
        '<div style="background:#0070b1;color:#ffffff;padding:8px 14px;'
        'border-radius:4px 4px 0 0;font-weight:700;font-size:13px;letter-spacing:0.5px;">'
        f"{label}</div>"
    )
    aspect_html = ""
    for i, asp in enumerate(aspects):
        if i > 0:
            aspect_html += '<hr style="border:none;border-top:1px solid #dddddd;margin:12px 0;">'
        margin = 'style="margin-bottom:16px;"' if i < len(aspects) - 1 else ""
        links_html = "".join(
            f'<a href="{s.get("url","")}" style="color:#0070b1;margin-right:8px;text-decoration:none;">'
            f'{s.get("text","Source")} ↗</a>'
            for s in (asp.get("source_links") or [])
        )
        aspect_html += f"""
        <div {margin}>
          <div style="font-weight:700;font-size:14px;color:#0070b1;margin-bottom:4px;">{asp.get("title","")}</div>
          <div style="color:#333333;margin-bottom:8px;">{asp.get("summary","")}</div>
          <div style="font-size:11px;color:#666666;margin-bottom:6px;">First published: {asp.get("first_publish_date","")}{_rank_badge(max_rank)}</div>
          <div style="font-size:12px;"><span style="font-weight:600;color:#555555;">Sources: </span>{links_html}</div>
        </div>"""

    body = (
        '<div style="border:1px solid #cccccc;border-top:none;padding:14px;background:#f9f9f9;">'
        f"{aspect_html}</div>"
    )
    return f'<div style="margin-bottom:20px;">{header}{body}</div>'


def generate_digest(
    items: list[dict],
    profile_id: int,
    conn: sqlite3.Connection,
    run_id: int,
    profile_name: str | None = None,
) -> str:
    """Generate the V2 HTML email digest.

    Grouping: authority → topic_label → AI-detected announcements.
    Writes news_announcements rows. Returns rendered HTML string.
    """
    language = _get_profile_language(conn, profile_id)
    if not profile_name:
        row = conn.execute("SELECT name FROM profiles WHERE id=?", (profile_id,)).fetchone()
        profile_name = row["name"] if row else "Digest"

    send_date = datetime.now(timezone.utc).strftime("%-d %B %Y")

    # Build authority → {topic_label → [item]}
    authority_groups: dict[int | None, dict[str, list[dict]]] = {}
    for it in items:
        aid = it.get("authority_id")
        labels_raw = it.get("topic_label") or '["General"]'
        try:
            labels = json.loads(labels_raw)
        except Exception:
            labels = ["General"]
        for lbl in labels:
            authority_groups.setdefault(aid, {}).setdefault(lbl, []).append(it)

    # Delete any existing announcements for this run (supports Resend idempotency)
    conn.execute("DELETE FROM news_announcements WHERE run_id=?", (run_id,))

    authority_blocks_html = ""
    for aid, topic_map in authority_groups.items():
        auth_name = _get_authority_name(conn, aid)
        # Check if any item under this authority is inferred
        is_inferred = any(
            (it.get("authority_status") or "") == "inferred"
            for topic_items in topic_map.values()
            for it in topic_items
        )
        authority_block = _render_authority_row(auth_name, is_inferred)

        # Sort topics by max rank desc
        sorted_topics = sorted(
            topic_map.items(),
            key=lambda kv: max((int(i.get("significance_rank") or 0) for i in kv[1]), default=0),
            reverse=True,
        )

        for topic_label, topic_items in sorted_topics:
            if not any(it.get("email_eligible") for it in topic_items):
                continue  # no eligible anchor — skip announcement and HTML block
            print(f"  🤖 Composing: {auth_name} / {topic_label} ({len(topic_items)} items)…")
            aspects = _call_ai_for_group(topic_items, language)

            item_ids = [int(it["id"]) for it in topic_items if it.get("id")]
            for asp in aspects:
                _save_announcement(conn, run_id, topic_label, asp, item_ids)

            max_rank = max((int(it.get("significance_rank") or 0) for it in topic_items), default=0)
            authority_block += _render_topic_block(topic_label, aspects, max_rank=max_rank)

        authority_blocks_html += f'<div style="margin-bottom:16px;">{authority_block}</div>'

    conn.commit()

    header_html = f"""
    <div style="text-align:center;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid #0070b1;">
      <div style="font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase;color:#0070b1;margin-bottom:4px;">Legal Eagle Digest</div>
      <div style="font-size:20px;font-weight:700;color:#1a1a1a;">{profile_name}</div>
      <div style="font-size:11px;color:#666666;margin-top:4px;">{send_date}</div>
    </div>"""

    footer_html = (
        '<div style="text-align:center;font-size:11px;color:#888888;'
        'border-top:1px solid #dddddd;padding-top:12px;">'
        "Legal Eagle · SAP Internal · Auto-generated digest</div>"
    )

    return (
        '<div style="font-family:sans-serif;font-size:13px;line-height:1.6;'
        'max-width:640px;background:#ffffff;padding:20px;">'
        f"{header_html}{authority_blocks_html}{footer_html}</div>"
    )
