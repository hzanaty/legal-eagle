#!/usr/bin/env python3
"""
Legal Eagle Scheduler Runner (no GitHub required)

Run scheduled profiles once by creating DB 'run' entries and capturing logs,
reusing the same run/logging model as the Admin UI. Intended to be invoked by
OS schedulers (launchd/systemd/cron) or manually.

Usage examples:
  - Run all active profiles that match today's schedule:
      python scripts/schedule_runner.py

  - Run a single profile (respecting schedule_day unless --ignore-schedule is set):
      python scripts/schedule_runner.py --profile-id 1

  - Run all active profiles ignoring schedule_day:
      python scripts/schedule_runner.py --ignore-schedule
"""
import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Ensure project root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from configurations.db import (
    get_connection,
    create_schema_if_needed,
    create_run,
    start_run,
    finish_run,
    append_run_log,
)
from agents.agents_controller import run_profile_once


def _today_name_dubai() -> str:
    # Match agents_controller logic: UTC + 4 hours
    return (datetime.utcnow() + timedelta(hours=4)).strftime("%A")


def _get_active_profiles() -> List[Dict[str, Any]]:
    conn = get_connection()
    create_schema_if_needed(conn)
    rows = conn.execute(
        "SELECT id, country_code, lob, name, language, active, schedule_day "
        "FROM profiles WHERE active = 1 ORDER BY country_code, lob, COALESCE(name,'')"
    ).fetchall()
    conn.close()
    return [{k: r[k] for k in r.keys()} for r in rows]


def _get_profile(profile_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    create_schema_if_needed(conn)
    r = conn.execute(
        "SELECT id, country_code, lob, name, language, active, schedule_day "
        "FROM profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    conn.close()
    return ({k: r[k] for k in r.keys()} if r else None)


class _DBLogger:
    """
    Capture stdout and mirror to runs.run_logs (line-buffered).
    Mirrors the Admin UI background worker logger.
    """
    def __init__(self, run_id: int):
        self.run_id = run_id
        self.buf = ""
        self.orig = sys.stdout

    def write(self, s: str):
        try:
            self.buf += s
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                conn_i = get_connection()
                create_schema_if_needed(conn_i)
                append_run_log(conn_i, self.run_id, "INFO", line)
                conn_i.close()
                self.orig.write(line + "\n")
        except Exception as e:
            self.orig.write(f"[log error] {e}\n")

    def flush(self):
        try:
            if self.buf:
                conn_i = get_connection()
                create_schema_if_needed(conn_i)
                append_run_log(conn_i, self.run_id, "INFO", self.buf)
                conn_i.close()
                self.orig.write(self.buf)
                self.buf = ""
            self.orig.flush()
        except Exception:
            pass


def run_profile_with_db_logging(profile_id: int) -> str:
    """
    Create a run, capture stdout to DB, execute run_profile_once(profile_id),
    and finalize run status. Returns final status string.
    """
    # Create run
    conn = get_connection()
    create_schema_if_needed(conn)
    run_id = create_run(conn, profile_id, origin="scheduled")
    start_run(conn, run_id)
    append_run_log(conn, run_id, "INFO", f"▶️ Run {run_id} started for profile {profile_id}")
    conn.close()

    # Redirect stdout to DB logger
    logger = _DBLogger(run_id)
    saved_stdout = sys.stdout
    sys.stdout = logger

    status_final = "Success"
    email_status = "Failed"
    try:
        ok = run_profile_once(profile_id)
        status_final = "Success" if ok else "Failed"
        email_status = "Sent" if ok else "Failed"
    except Exception as e:
        status_final = "Failed"
        conn_e = get_connection()
        create_schema_if_needed(conn_e)
        append_run_log(conn_e, run_id, "ERROR", f"Exception: {e}")
        conn_e.close()
    finally:
        try:
            sys.stdout.flush()
        except Exception:
            pass
        sys.stdout = saved_stdout
        fconn = get_connection()
        create_schema_if_needed(fconn)
        finish_run(fconn, run_id, status_final, metrics={"email_status": email_status})
        append_run_log(fconn, run_id, "INFO", f"🏁 Run {run_id} finished with status {status_final}")
        fconn.close()

    return status_final


def main():
    parser = argparse.ArgumentParser(description="Legal Eagle scheduled runner (DB-logged).")
    parser.add_argument("--profile-id", type=int, help="Run a single profile by id.")
    parser.add_argument("--ignore-schedule", action="store_true", help="Ignore schedule_day filter.")
    args = parser.parse_args()

    today_name = _today_name_dubai()
    print(f"🗓️  Scheduler tick — Today (Dubai): {today_name}")

    if args.profile_id:
        prof = _get_profile(args.profile_id)
        if not prof:
            print(f"❌ Profile id {args.profile_id} not found.")
            sys.exit(1)
        if not args.ignore_schedule and prof.get("schedule_day") and prof["schedule_day"] != today_name:
            print(f"⏭️ Skipping profile {prof['country_code']}/{prof['lob']} (schedule_day={prof['schedule_day']}, today={today_name})")
            return
        print(f"▶️ Running single profile {prof['country_code']}/{prof['lob']} (id={prof['id']})")
        status = run_profile_with_db_logging(prof["id"])
        print(f"✅ Single profile finished: {status}")
        return

    # Else run all active profiles that match today's schedule_day
    profiles = _get_active_profiles()
    if not profiles:
        print("⚠️ No active profiles found. Exiting.")
        return

    any_run = False
    for p in profiles:
        sched = p.get("schedule_day")
        if args.ignore_schedule or (sched and sched == today_name):
            any_run = True
            print(f"\n===== ▶️ Running profile {p['country_code']}/{p['lob']} (id={p['id']}) =====")
            status = run_profile_with_db_logging(int(p["id"]))
            print(f"✅ Finished with status: {status}")
        else:
            print(f"⏭️ Skipping profile {p['country_code']}/{p['lob']} (schedule_day={sched}, today={today_name})")

    if not any_run:
        print("ℹ️ No profiles scheduled for today.")


if __name__ == "__main__":
    main()
