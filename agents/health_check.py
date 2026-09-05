"""
Health Check — pre-run reachability checks (v3.1, F2).

Runs dependency checks in parallel before a profile run so failures surface
immediately (in the Run tab log) instead of mid-pipeline. Severity model:

  - Database        → HARD  (can't run without it)
  - Gmail SMTP      → HARD  only when the run will actually send email
  - SAP AI Core     → WARN  (pipeline degrades to deterministic dedup if down;
                             skipped entirely in cache/offline mode)
  - Each source URL → WARN  (one unreachable feed shouldn't block the others)

A HARD failure aborts the run; WARN results are logged and the run proceeds.
"""
import os
import socket
import smtplib
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import requests

from configurations.config_loader import creds, load_rss_feeds, load_url_sources

OK, WARN, FAIL = "ok", "warn", "fail"


def _result(name: str, severity: str, status: str, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "severity": severity, "status": status, "detail": detail}


def _check_db() -> Dict[str, Any]:
    try:
        from configurations.db import get_connection, create_schema_if_needed
        conn = get_connection()
        create_schema_if_needed(conn)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return _result("Database", "hard", OK)
    except Exception as e:
        return _result("Database", "hard", FAIL, f"{type(e).__name__}: {e}")


def _check_ai_core() -> Dict[str, Any]:
    # Offline / cache mode: don't touch the network — embeddings replay from cache.
    if os.environ.get("LEGAL_EAGLE_AI_CACHE"):
        return _result("SAP AI Core", "warn", OK, "cache mode (offline)")
    try:
        sap = creds.get("sap_aicore", {})
        r = requests.post(
            f"{sap['auth_url'].rstrip('/')}/oauth/token",
            data={"grant_type": "client_credentials",
                  "client_id": sap["client_id"], "client_secret": sap["client_secret"]},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("access_token"):
            return _result("SAP AI Core", "warn", OK)
        return _result("SAP AI Core", "warn", WARN, f"auth HTTP {r.status_code}")
    except Exception as e:
        return _result("SAP AI Core", "warn", WARN, f"{type(e).__name__}: {e}")


def _check_gmail() -> Dict[str, Any]:
    try:
        g = creds.get("gmail", {})
        sender = g.get("email_sender")
        pw = g.get("app_password")
        if not sender or not pw:
            return _result("Gmail SMTP", "hard", FAIL, "missing credentials")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
            s.login(sender, pw)
        return _result("Gmail SMTP", "hard", OK)
    except Exception as e:
        return _result("Gmail SMTP", "hard", FAIL, f"{type(e).__name__}: {e}")


def _check_url(label: str, url: str) -> Dict[str, Any]:
    try:
        r = requests.get(url, timeout=8, stream=True)
        r.close()
        if r.status_code < 400:
            return _result(label, "warn", OK, f"HTTP {r.status_code}")
        return _result(label, "warn", WARN, f"HTTP {r.status_code}")
    except Exception as e:
        return _result(label, "warn", WARN, f"{type(e).__name__}")


def run_health_checks(profile_id: int, check_email: bool = True) -> List[Dict[str, Any]]:
    """Run all dependency checks in parallel and return a list of result dicts."""
    tasks = [("db", _check_db, ()), ("ai", _check_ai_core, ())]
    if check_email:
        tasks.append(("gmail", _check_gmail, ()))
    try:
        for f in load_rss_feeds(profile_id):
            url = f["url"] if isinstance(f, dict) else f
            tasks.append(("src", _check_url, (f"RSS: {url}", url)))
        for s in load_url_sources(profile_id):
            url = s.get("url")
            if url:
                tasks.append(("src", _check_url, (f"URL: {url}", url)))
    except Exception:
        pass

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(fn, *args) for _, fn, args in tasks]
        for fut in futs:
            try:
                results.append(fut.result())
            except Exception as e:
                results.append(_result("check", "warn", WARN, str(e)))
    return results


def summarize(results: List[Dict[str, Any]]) -> str:
    icon = {OK: "✅", WARN: "⚠️", FAIL: "❌"}
    lines = ["🩺 Pre-run health checks:"]
    for r in results:
        d = f" — {r['detail']}" if r.get("detail") else ""
        lines.append(f"   {icon.get(r['status'], '?')} [{r['severity']}] {r['name']}: {r['status']}{d}")
    return "\n".join(lines)


def hard_failures(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in results if r["severity"] == "hard" and r["status"] == FAIL]
