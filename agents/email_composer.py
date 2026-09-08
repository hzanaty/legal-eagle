"""
Email Composer — V2 digest formatter (v3.13).

PURE FORMATTER: reads persistent announcements from news_announcements (built by
announcement_agent) and renders the HTML digest. It no longer does AI grouping or
title/body generation — that moved to agents/announcement_agent.py.

generate_digest() ensures pending items are processed (announcement_agent.build),
then renders the profile's draft (unpublished) announcements.
"""

import json
import sqlite3
from datetime import datetime, timezone

from configurations import db


def _rcm_body_text(ann: dict) -> str:
    """Extract a short rendered body from the announcement's RCM JSON (intro bullets)."""
    raw = ann.get("announcement_rcm_json")
    if raw:
        try:
            rcm = json.loads(raw)
            intro = rcm.get("introduction") or []
            biz = rcm.get("business_background") or []
            bullets = list(intro) + list(biz)
            if bullets:
                return "".join(f"• {b}<br>" for b in bullets)
        except Exception:
            pass
    return ann.get("announcement_md") or ""


def _render_announcement_block(ann: dict) -> str:
    label = ann.get("topic_label") or "General"
    header = (
        '<div style="background:#0070b1;color:#ffffff;padding:8px 14px;'
        'border-radius:4px 4px 0 0;font-weight:700;font-size:13px;letter-spacing:0.5px;">'
        f"{label}</div>"
    )
    try:
        links = json.loads(ann.get("source_links_json") or "[]")
    except Exception:
        links = []
    links_html = "".join(
        f'<a href="{s.get("url","")}" style="color:#0070b1;margin-right:8px;text-decoration:none;">'
        f'{s.get("text","Source")} ↗</a>'
        for s in links
    )
    body = (
        '<div style="border:1px solid #cccccc;border-top:none;padding:14px;background:#f9f9f9;">'
        f'<div style="font-weight:700;font-size:14px;color:#0070b1;margin-bottom:4px;">{ann.get("title","")}</div>'
        f'<div style="color:#333333;margin-bottom:8px;">{_rcm_body_text(ann)}</div>'
        f'<div style="font-size:11px;color:#666666;margin-bottom:6px;">First published: {ann.get("first_published","")}</div>'
        f'<div style="font-size:12px;"><span style="font-weight:600;color:#555555;">Sources: </span>{links_html}</div>'
        "</div>"
    )
    return f'<div style="margin-bottom:20px;">{header}{body}</div>'


def generate_digest(
    items: list[dict],
    profile_id: int,
    conn: sqlite3.Connection,
    run_id: int,
    profile_name: str | None = None,
) -> str:
    """Render the V2 HTML digest from persistent announcements (pure formatter).

    First ensures pending items are grouped (announcement_agent.build), then renders
    the profile's draft (unpublished) announcements. Does NOT do AI grouping itself.
    """
    from agents import announcement_agent

    if not profile_name:
        row = conn.execute("SELECT name FROM profiles WHERE id=?", (profile_id,)).fetchone()
        profile_name = row["name"] if row else "Digest"
    send_date = datetime.now(timezone.utc).strftime("%-d %B %Y")

    # Build/refresh announcements from any pending items (idempotent, delta-only).
    try:
        announcement_agent.build(conn, profile_id, run_id)
    except Exception as e:
        print(f"  ⚠️  announcement_agent.build failed: {e}")

    # Render draft (unpublished) announcements for this profile, highest-rank topics first.
    anns = [a for a in db.get_announcements_for_profile_with_sources(conn, profile_id)
            if (a.get("status") or "draft") != "done"]
    topic_blocks_html = "".join(_render_announcement_block(a) for a in anns)

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
        f"{header_html}{topic_blocks_html}{footer_html}</div>"
    )
