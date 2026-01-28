#!/usr/bin/env python3
"""
Seed SQLite global_credentials from environment variables (LEGAL_EAGLE_*).

- Backs up configurations/config.db to configurations/config.db.bak-<timestamp>
- Creates schema if not exists
- Upserts singleton row id=1 in global_credentials with values derived from env:
    twitter_api_key         ← LEGAL_EAGLE_TWITTER_API_KEY (optional; usually not set)
    twitter_api_secret      ← LEGAL_EAGLE_TWITTER_API_SECRET (optional; usually not set)
    twitter_bearer_token    ← LEGAL_EAGLE_TWITTER_BEARER_TOKEN
    smtp_host               ← LEGAL_EAGLE_SMTP_HOST (default: smtp.gmail.com)
    smtp_port               ← LEGAL_EAGLE_SMTP_PORT (default: 587)
    smtp_username           ← LEGAL_EAGLE_GMAIL_EMAIL_SENDER
    smtp_password           ← LEGAL_EAGLE_GMAIL_APP_PASSWORD
    smtp_use_tls            ← LEGAL_EAGLE_SMTP_USE_TLS (default: 1)
    global_sender_email     ← LEGAL_EAGLE_GLOBAL_SENDER_EMAIL (default: LEGAL_EAGLE_GMAIL_EMAIL_SENDER)

This script does NOT print secret values to stdout.
"""

import os
import sys
import shutil
from datetime import datetime

# Ensure project root on sys.path so we can import configurations.db
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from configurations.db import get_connection, create_schema_if_needed, set_global_credentials  # type: ignore


def timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def backup_file(src_path: str, dst_prefix: str) -> str:
    """
    Backup a file if it exists. Returns backup path or '' if src missing.
    """
    if not os.path.exists(src_path):
        return ""
    bak_path = f"{dst_prefix}.{timestamp()}"
    shutil.copy2(src_path, bak_path)
    return bak_path


def compose_db_values_from_env() -> dict:
    """
    Compose global_credentials payload from environment variables with sensible defaults.
    Avoid printing secrets.
    """
    env = os.environ

    twitter_api_key = env.get("LEGAL_EAGLE_TWITTER_API_KEY")
    twitter_api_secret = env.get("LEGAL_EAGLE_TWITTER_API_SECRET")
    twitter_bearer_token = env.get("LEGAL_EAGLE_TWITTER_BEARER_TOKEN")

    # SMTP synthesis from Gmail env; allow overrides
    smtp_host = env.get("LEGAL_EAGLE_SMTP_HOST") or "smtp.gmail.com"
    try:
        smtp_port = int(env.get("LEGAL_EAGLE_SMTP_PORT") or 587)
    except ValueError:
        smtp_port = 587

    smtp_username = env.get("LEGAL_EAGLE_GMAIL_EMAIL_SENDER")
    smtp_password = env.get("LEGAL_EAGLE_GMAIL_APP_PASSWORD")

    try:
        smtp_use_tls = int(env.get("LEGAL_EAGLE_SMTP_USE_TLS") or 1)
    except ValueError:
        smtp_use_tls = 1

    global_sender_email = env.get("LEGAL_EAGLE_GLOBAL_SENDER_EMAIL") or smtp_username

    return {
        "twitter_api_key": twitter_api_key,
        "twitter_api_secret": twitter_api_secret,
        "twitter_bearer_token": twitter_bearer_token,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_password": smtp_password,
        "smtp_use_tls": smtp_use_tls,
        "global_sender_email": global_sender_email,
    }


def main() -> None:
    # Backup DB if present
    db_path = os.path.join(BASE_DIR, "configurations", "config.db")
    db_bak = backup_file(db_path, os.path.join(BASE_DIR, "configurations", "config.db.bak"))

    # Compose data from env
    payload = compose_db_values_from_env()

    # Write to DB
    conn = get_connection()
    create_schema_if_needed(conn)
    set_global_credentials(conn, payload)
    conn.close()

    print("✅ global_credentials seeded from environment.")
    if db_bak:
        print(f"🗄️ DB backup: {db_bak}")
    # Presence summary without revealing values
    def _set(k: str) -> bool:
        v = payload.get(k)
        return v is not None and str(v) != ""
    print("Presence (True means set/non-empty):")
    for k in [
        "twitter_bearer_token",
        "smtp_username",
        "smtp_password",
        "global_sender_email",
    ]:
        print(f"  - {k}: {_set(k)}")
    if not _set("smtp_username") or not _set("smtp_password"):
        print("Note: smtp_username/password not set. Ensure LEGAL_EAGLE_GMAIL_EMAIL_SENDER and LEGAL_EAGLE_GMAIL_APP_PASSWORD are present in environment or in .env.")

if __name__ == "__main__":
    main()
