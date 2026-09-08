"""
RCM Reference Titles sync (v3.13).

The LOKA call itself is made by a Claude Code command (LOKA MCP, native), NOT by
Flask — see .claude/commands/sync-rcm-titles.md. This module is the persistence
helper the command pipes results into: it upserts parsed regulation rows into the
per-profile rcm_reference_titles cache, which grounds announcement title generation.

CLI:
    python -m agents.rcm_reference_sync <profile_id> [json_path]
    # json_path (or stdin) is a JSON array of:
    #   {"jira_key": "...", "regulation_title": "...", "country": "...", "effective_date": "..."}
"""

import json
import sys
from typing import Any, Dict, List

from configurations.db import get_connection, create_schema_if_needed


def upsert_reference_titles(
    conn, profile_id: int, regulations: List[Dict[str, Any]]
) -> int:
    """Upsert regulation reference rows for a profile. Returns count written."""
    n = 0
    with conn:
        for reg in regulations:
            title = (reg.get("regulation_title") or reg.get("title") or "").strip()
            if not title:
                continue
            jira_key = (reg.get("jira_key") or reg.get("key") or "").strip() or None
            country = (reg.get("country") or "").strip() or None
            eff = (reg.get("effective_date") or reg.get("due_date") or "").strip() or None
            # Upsert on (profile_id, jira_key). Rows with no jira_key just insert.
            existing = None
            if jira_key:
                existing = conn.execute(
                    "SELECT id FROM rcm_reference_titles WHERE profile_id=? AND jira_key=?",
                    (profile_id, jira_key),
                ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE rcm_reference_titles SET regulation_title=?, country=?, "
                    "effective_date=?, synced_at=datetime('now') WHERE id=?",
                    (title, country, eff, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO rcm_reference_titles(profile_id, jira_key, regulation_title, "
                    "country, effective_date) VALUES(?,?,?,?,?)",
                    (profile_id, jira_key, title, country, eff),
                )
            n += 1
    return n


def last_synced(conn, profile_id: int) -> str | None:
    row = conn.execute(
        "SELECT MAX(synced_at) AS ts FROM rcm_reference_titles WHERE profile_id=?",
        (profile_id,),
    ).fetchone()
    return row["ts"] if row and row["ts"] else None


def _main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m agents.rcm_reference_sync <profile_id> [json_path]", file=sys.stderr)
        return 2
    profile_id = int(argv[1])
    raw = open(argv[2], encoding="utf-8").read() if len(argv) > 2 else sys.stdin.read()
    regulations = json.loads(raw)
    if not isinstance(regulations, list):
        print("input must be a JSON array of regulation objects", file=sys.stderr)
        return 2
    conn = get_connection()
    create_schema_if_needed(conn)
    written = upsert_reference_titles(conn, profile_id, regulations)
    print(f"✅ Synced {written} RCM reference titles for profile {profile_id} "
          f"(last synced: {last_synced(conn, profile_id)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
