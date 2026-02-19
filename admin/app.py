import os
import re
import threading
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from flask import Response, stream_with_context

from flask import Flask, render_template, request, redirect, url_for, flash

# Ensure project root is on sys.path for module imports (configurations, agents)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Ensure we can import from project modules
from configurations.config_loader import (
    list_active_profiles,
    resolve_profile,
    load_language,
    load_rss_feeds,
    load_tweet_accounts,
    load_email_receivers,
    load_email_receivers_with_lang,
    load_glossary,
    get_setting_value,
    set_setting_value,
    add_news_item,
    get_weekly_baseline,
    load_url_sources,
    load_global_credentials,
    migrate_urls_to_unified,
    LANGUAGE_NAMES,
)
from configurations.db import (
    get_connection,
    create_schema_if_needed,
    create_profile,
    upsert_rss_feed,
    upsert_tweet_account,
    upsert_email_receiver,
    upsert_email_receiver_with_lang,
    upsert_url_source,
    delete_url_source,
    add_audit_log,
    # runs + logs
    create_run,
    start_run,
    finish_run,
    append_run_log,
    list_runs_for_profile,
    get_run,
    list_run_logs,
    set_cancel_requested,
    is_cancel_requested,
    prune_old_runs,
    # filtered news
    list_filtered_news,
    count_filtered_news,
    update_filtered_news_score,
    delete_filtered_news,
    clear_filtered_news,
    prune_old_filtered_news,
)

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("LEGAL_EAGLE_ADMIN_SECRET", "local-only-admin")

# Timestamp formatting (UTC -> local) filter for Jinja
from zoneinfo import ZoneInfo

def format_ts(value: str, tz_name: str = "Asia/Dubai", fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """
    Convert ISO 8601 UTC string to local timezone display.
    Stored timestamps are naive UTC strings (datetime.utcnow().isoformat()).
    """
    try:
        if not value:
            return ""
        dt = datetime.fromisoformat(value)
        # Attach UTC if naive, then convert to target tz
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(ZoneInfo(tz_name))
        return local.strftime(fmt)
    except Exception:
        # Fallback: show raw value if parsing fails
        return value


def format_date(value: str, tz_name: str = "Asia/Dubai") -> str:
    """
    Convert ISO 8601 UTC string to local date only (no time).
    Returns format: YYYY-MM-DD
    """
    try:
        if not value:
            return ""
        dt = datetime.fromisoformat(value)
        # Attach UTC if naive, then convert to target tz
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(ZoneInfo(tz_name))
        return local.strftime("%Y-%m-%d")
    except Exception:
        # Fallback: try to extract date portion from raw value
        try:
            return value[:10] if len(value) >= 10 else value
        except Exception:
            return value

# Register filters
app.jinja_env.filters["format_ts"] = format_ts
app.jinja_env.filters["format_date"] = format_date

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ensure_schema():
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.close()


@app.route("/")
def root():
    return redirect(url_for("admin_dashboard"))


@app.route("/admin")
def admin_dashboard():
    _ensure_schema()
    # retention cleanup (7 days)
    try:
        conn = get_connection()
        create_schema_if_needed(conn)
        prune_old_runs(conn, days=7)
        conn.close()
    except Exception as e:
        print(f"⚠️ Retention cleanup skipped: {e}")
    # Show all profiles (active and inactive) with last run time
    # Sorted by last run (never/oldest first, newest last)
    conn = get_connection()
    rows = conn.execute("SELECT * FROM profiles").fetchall()
    
    profiles = []
    for r in rows:
        profile_id = int(r["id"])
        
        # Get last run time for this profile
        last_run_row = conn.execute(
            "SELECT started_at FROM runs WHERE profile_id = ? AND started_at IS NOT NULL ORDER BY started_at DESC LIMIT 1",
            (profile_id,)
        ).fetchone()
        
        last_run_time = None
        last_run_display = "—"
        last_run_sort_key = ""  # Empty string sorts before any date
        
        if last_run_row and last_run_row["started_at"]:
            try:
                last_dt = datetime.fromisoformat(last_run_row["started_at"])
                now = datetime.utcnow()
                elapsed_mins = int((now - last_dt).total_seconds() / 60)
                
                if elapsed_mins < 1:
                    last_run_display = "just now"
                elif elapsed_mins < 60:
                    last_run_display = f"{elapsed_mins} min ago"
                elif elapsed_mins < 1440:
                    hours = elapsed_mins // 60
                    last_run_display = f"{hours} hour{'s' if hours != 1 else ''} ago"
                else:
                    days = elapsed_mins // 1440
                    last_run_display = f"{days} day{'s' if days != 1 else ''} ago"
                
                last_run_time = last_run_row["started_at"]
                last_run_sort_key = last_run_time  # ISO format sorts correctly
            except Exception:
                pass
        
        profiles.append({
            "id": profile_id,
            "country_code": r["country_code"],
            "lob": r["lob"],
            "name": r["name"],
            "language": r["language"],
            "active": int(r["active"] or 0),
            "last_run_time": last_run_time,
            "last_run_display": last_run_display,
            "last_run_sort_key": last_run_sort_key,
        })
    
    # Sort by last run (never/oldest first), then by country/lob as secondary sort
    profiles.sort(key=lambda p: (p["last_run_sort_key"], p["country_code"], p["lob"]))
    
    conn.close()
    return render_template("dashboard.html", profiles=profiles)


@app.route("/admin/profiles/create", methods=["GET"])
def show_create_profile_page():
    """
    Display the create profile form page.
    """
    _ensure_schema()
    return render_template("create_profile.html")


@app.route("/admin/profiles/create", methods=["POST"])
def create_profile_route():
    country_code = request.form.get("country_code", "").strip().upper()
    lob = request.form.get("lob", "").strip().upper()  # HCM|FIN
    name = request.form.get("name") or None
    language = request.form.get("language", "en").strip() or "en"

    if not country_code or len(country_code) != 2:
        flash("Invalid country code. Please select a valid ISO alpha-2 code.", "error")
        return redirect(url_for("admin_dashboard"))
    if lob not in ("HCM", "FIN"):
        flash("Invalid LoB. Choose HCM or FIN.", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_connection()
    create_schema_if_needed(conn)
    pid = create_profile(conn, country_code=country_code, lob=lob, name=name, language=language, active=1)
    add_audit_log(conn, entity="profiles", action="create", details=f"{country_code}-{lob} name={name} lang={language}", profile_id=pid)
    conn.close()

    flash("Profile created.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=pid))


@app.route("/admin/profiles/<int:profile_id>/toggle", methods=["POST"])
def toggle_profile_active(profile_id: int):
    conn = get_connection()
    create_schema_if_needed(conn)
    row = conn.execute("SELECT active FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if not row:
        conn.close()
        flash("Profile not found.", "error")
        return redirect(url_for("admin_dashboard"))
    new_active = 0 if int(row["active"] or 0) == 1 else 1
    conn.execute("UPDATE profiles SET active = ? WHERE id = ?", (new_active, profile_id))
    add_audit_log(conn, entity="profiles", action="toggle", details=f"active={new_active}", profile_id=profile_id)
    conn.close()
    flash("Profile status updated.", "success")
    return redirect(url_for("admin_dashboard"))


# Run page (split layout): left = confirm + history, right = logs (empty until run selected/started)
@app.route("/admin/profiles/<int:profile_id>/runs")
def admin_profile_runs(profile_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    prof = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if not prof:
        conn.close()
        flash("Profile not found.", "error")
        return redirect(url_for("admin_dashboard"))
    profile = {
        "id": int(prof["id"]),
        "country_code": prof["country_code"],
        "lob": prof["lob"],
        "name": prof["name"],
        "language": prof["language"],
        "active": int(prof["active"] or 0),
        "schedule_day": prof["schedule_day"],
    }
    runs = list_runs_for_profile(conn, profile_id, limit=50)
    # Compute news count and whether a run is currently active for this profile
    try:
        row_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM news_items WHERE profile_id = ?", (profile_id,)).fetchone()
        news_count = int(row_cnt["cnt"] or 0)
    except Exception:
        news_count = 0
    run_active_row = conn.execute("SELECT 1 FROM runs WHERE profile_id = ? AND status = 'Running' LIMIT 1", (profile_id,)).fetchone()
    run_active = bool(run_active_row)

    # Twitter status calculation (Search API - all accounts fetched together)
    from agents.tweet_feed import check_twitter_rate_limit
    from configurations.db import get_setting as db_get_setting
    
    twitter_accounts = load_tweet_accounts(profile_id)
    twitter_status = None
    
    if twitter_accounts:
        can_fetch, minutes_to_wait = check_twitter_rate_limit(profile_id, conn)
        
        # Get last fetch time
        last_fetch_str = db_get_setting(conn, profile_id, 'twitter_last_fetch_time')
        last_fetch_time = None
        next_available_time = None
        time_ago_str = "Never"
        
        if last_fetch_str:
            try:
                last_dt = datetime.fromisoformat(last_fetch_str)
                now = datetime.utcnow()
                elapsed_mins = int((now - last_dt).total_seconds() / 60)
                
                if elapsed_mins < 60:
                    time_ago_str = f"{elapsed_mins} minute{'s' if elapsed_mins != 1 else ''} ago"
                elif elapsed_mins < 1440:
                    hours = elapsed_mins // 60
                    time_ago_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
                else:
                    days = elapsed_mins // 1440
                    time_ago_str = f"{days} day{'s' if days != 1 else ''} ago"
                
                last_fetch_time = last_fetch_str
                
                if not can_fetch:
                    next_dt = last_dt + timedelta(minutes=15)
                    next_available_time = next_dt.isoformat()
            except Exception:
                pass
        
        # Format account list for display
        account_list = ", ".join([f"@{a.lstrip('@')}" for a in twitter_accounts])
        
        twitter_status = {
            'can_fetch': can_fetch,
            'minutes_to_wait': minutes_to_wait,
            'time_ago': time_ago_str,
            'last_fetch_time': last_fetch_time,
            'next_available_time': next_available_time,
            'total_accounts': len(twitter_accounts),
            'account_list': account_list,
        }
    
    # Resource status calculation
    last_full_str = db_get_setting(conn, profile_id, 'last_full_run_time')
    will_skip = False
    resource_time_ago = "Never"
    
    if last_full_str:
        try:
            last_dt = datetime.fromisoformat(last_full_str)
            now = datetime.utcnow()
            elapsed_hours = (now - last_dt).total_seconds() / 3600
            elapsed_mins = int((now - last_dt).total_seconds() / 60)
            
            will_skip = elapsed_hours < 2
            
            if elapsed_mins < 60:
                resource_time_ago = f"{elapsed_mins} minute{'s' if elapsed_mins != 1 else ''} ago"
            elif elapsed_mins < 1440:
                hours = int(elapsed_hours)
                resource_time_ago = f"{hours} hour{'s' if hours != 1 else ''} ago"
            else:
                days = elapsed_mins // 1440
                resource_time_ago = f"{days} day{'s' if days != 1 else ''} ago"
        except Exception:
            pass
    
    resource_status = {
        'last_full_run_time': last_full_str,
        'will_skip_resources': will_skip,
        'time_ago': resource_time_ago,
    }
    
    conn.close()

    # Optional run selection via query param
    run_id = request.args.get("run_id")
    selected_run = None
    if run_id and run_id.isdigit():
        conn = get_connection()
        create_schema_if_needed(conn)
        selected_run = get_run(conn, int(run_id))
        conn.close()

    return render_template(
        "run_status.html",
        profile=profile,
        runs=runs,
        selected_run=selected_run,
        news_count=news_count,
        run_active=run_active,
        twitter_status=twitter_status,
        resource_status=resource_status,
    )


# Confirm run → create, start, redirect to same page with run_id so right pane streams logs
@app.route("/admin/profiles/<int:profile_id>/runs/start", methods=["POST"])
def admin_start_run(profile_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    # Audit request
    add_audit_log(conn, entity="profiles", action="run_requested", details="manual run from run page", profile_id=profile_id)
    run_id = create_run(conn, profile_id, origin="manual")
    conn.close()

    # Background worker
    def _worker(pid: int, rid: int):
        # hook stdout to DB logs with line buffering
        class _DBLogger:
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

        # start run
        conn_i = get_connection()
        create_schema_if_needed(conn_i)
        start_run(conn_i, rid)
        append_run_log(conn_i, rid, "INFO", f"▶️ Run {rid} started for profile {pid}")
        conn_i.close()

        # replace stdout
        logger = _DBLogger(rid)
        saved_stdout = sys.stdout
        sys.stdout = logger
        email_status = "Failed"
        metrics: Dict[str, Any] = {}
        status_final = "Success"
        try:
            from agents.agents_controller import run_profile_once

            # cancel checker
            def _cancel() -> bool:
                cconn = get_connection()
                create_schema_if_needed(cconn)
                flag = is_cancel_requested(cconn, rid)
                cconn.close()
                return flag

            ok = run_profile_once(pid)  # leverage existing prints which are captured
            status_final = "Success" if ok else "Failed"
            email_status = "Sent" if ok else "Failed"
        except Exception as e:
            status_final = "Failed"
            conn_e = get_connection()
            create_schema_if_needed(conn_e)
            append_run_log(conn_e, rid, "ERROR", f"Exception: {e}")
            conn_e.close()
        finally:
            try:
                sys.stdout.flush()
            except Exception:
                pass
            sys.stdout = saved_stdout
            # finish
            fconn = get_connection()
            create_schema_if_needed(fconn)
            # If cancel was requested mark as Canceled (but email was still attempted by the run)
            status_mark = status_final
            if is_cancel_requested(fconn, rid) and status_final == "Success":
                status_mark = "Canceled"
            finish_run(fconn, rid, status_mark, metrics={"email_status": email_status})
            append_run_log(fconn, rid, "INFO", f"🏁 Run {rid} finished with status {status_mark}")
            fconn.close()

    threading.Thread(target=_worker, args=(profile_id, run_id), daemon=True).start()
    return redirect(url_for("admin_profile_runs", profile_id=profile_id, run_id=run_id))


# SSE stream for logs
@app.route("/admin/runs/<int:run_id>/stream")
def stream_run_logs(run_id: int):
    _ensure_schema()
    def _event_stream():
        last_seq = None
        finished = False
        while not finished:
            conn = get_connection()
            create_schema_if_needed(conn)
            logs = list_run_logs(conn, run_id, after_seq=last_seq, limit=500)
            run_row = get_run(conn, run_id)
            conn.close()
            for entry in logs:
                last_seq = entry["seq"]
                payload = f"{entry['ts']} [{entry['level']}] {entry['line']}"
                yield f"data: {payload}\n\n"
            # check status
            if run_row and run_row.get("status") in ("Success", "Failed", "Canceled"):
                # send terminal event
                yield f"event: done\ndata: {run_row['status']}\n\n"
                finished = True
                break
            time.sleep(0.75)
    return Response(stream_with_context(_event_stream()), mimetype="text/event-stream")


# Cancel a run (cooperative)
@app.route("/admin/runs/<int:run_id>/cancel", methods=["POST"])
def cancel_run(run_id: int):
    conn = get_connection()
    create_schema_if_needed(conn)
    set_cancel_requested(conn, run_id)
    append_run_log(conn, run_id, "WARN", "⛔ Cancel requested. Will stop after current step and send partial email.")
    run_row = get_run(conn, run_id)
    conn.close()
    if run_row:
        flash("Cancel requested. The run will stop after the current step and send email.", "success")
        return redirect(url_for("admin_profile_runs", profile_id=int(run_row["profile_id"]), run_id=run_id))
    flash("Cancel requested.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/profiles/<int:profile_id>")
def admin_profile_detail(profile_id: int):
    _ensure_schema()
    conn = get_connection()
    prof = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if not prof:
        conn.close()
        flash("Profile not found.", "error")
        return redirect(url_for("admin_dashboard"))

    profile = {
        "id": int(prof["id"]),
        "country_code": prof["country_code"],
        "lob": prof["lob"],
        "name": prof["name"],
        "language": prof["language"],
        "active": int(prof["active"] or 0),
        "schedule_day": prof["schedule_day"],
    }
    conn.close()

    rss = load_rss_feeds(profile_id)
    urls = load_url_sources(profile_id)
    tweets = load_tweet_accounts(profile_id)
    receivers = load_email_receivers(profile_id)
    receivers_semicolon = "; ".join(receivers) if receivers else ""
    receivers_with_lang = load_email_receivers_with_lang(profile_id)

    glossary = load_glossary(profile_id)
    reset_quota_date = get_setting_value(profile_id, 'tweets_reset_quota_date')
    monitor_enabled = get_setting_value(profile_id, 'monitor_updates_enabled', 'false') == 'true'

    return render_template(
        "profile.html",
        profile=profile,
        rss=rss,
        urls=urls,
        tweets=tweets,
        receivers_semicolon=receivers_semicolon,
        receivers=receivers,
        receivers_with_lang=receivers_with_lang,
        glossary=glossary,
        reset_quota_date=reset_quota_date,
        monitor_enabled=monitor_enabled,
        language_names=LANGUAGE_NAMES,
    )


@app.route("/admin/profiles/<int:profile_id>/language/update", methods=["POST"])
def update_profile_language(profile_id: int):
    """
    Update the analysis language for a profile.
    """
    language = (request.form.get("language", "") or "").strip()
    
    if not language:
        flash("Language is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    
    # Validate language code
    if language not in LANGUAGE_NAMES:
        flash(f"Invalid language code: {language}", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("UPDATE profiles SET language = ? WHERE id = ?", (language, profile_id))
    add_audit_log(conn, entity="profiles", action="update_language", details=f"language={language}", profile_id=profile_id)
    conn.close()
    
    lang_name = LANGUAGE_NAMES.get(language, language)
    flash(f"Profile language updated to {lang_name}.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/schedule/update", methods=["POST"])
def update_profile_schedule_day(profile_id: int):
    """
    Update day-of-week scheduling for a profile. Allowed values:
    Sunday, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday.
    Empty/unset clears scheduling (profile will be skipped by controller).
    """
    day = (request.form.get("schedule_day", "") or "").strip()
    allowed = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

    conn = get_connection()
    create_schema_if_needed(conn)

    value = None
    if day:
        if day not in allowed:
            conn.close()
            flash("Invalid schedule day. Please choose a valid day.", "error")
            return redirect(url_for("admin_profile_detail", profile_id=profile_id))
        value = day

    conn.execute("UPDATE profiles SET schedule_day = ? WHERE id = ?", (value, profile_id))
    add_audit_log(conn, entity="profiles", action="update_schedule_day", details=f"schedule_day={value}", profile_id=profile_id)
    conn.close()
    flash("Schedule day updated.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/monitor-toggle", methods=["POST"])
def toggle_monitor_updates(profile_id: int):
    """
    Toggle monitor_updates_enabled setting for a profile.
    Enables/disables Law-to-Specification email monitoring.
    """
    enabled = request.form.get("enabled") == "true"
    value = "true" if enabled else "false"
    
    conn = get_connection()
    create_schema_if_needed(conn)
    set_setting_value(profile_id, "monitor_updates_enabled", value)
    add_audit_log(conn, entity="settings", action="toggle_monitor_updates", details=f"enabled={value}", profile_id=profile_id)
    conn.close()
    
    status = "enabled" if enabled else "disabled"
    flash(f"Monitor notifications {status}.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))

# RSS management
@app.route("/admin/profiles/<int:profile_id>/rss/add", methods=["POST"])
def add_rss(profile_id: int):
    url = request.form.get("url", "").strip()
    if not url:
        flash("RSS URL is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    upsert_rss_feed(conn, profile_id, url)
    add_audit_log(conn, entity="rss_feeds", action="add", details=url, profile_id=profile_id)
    conn.close()
    flash("RSS feed added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/rss/delete", methods=["POST"])
def delete_rss(profile_id: int):
    url = request.form.get("url", "").strip()
    if not url:
        flash("RSS URL is required to delete.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("DELETE FROM rss_feeds WHERE profile_id = ? AND url = ?", (profile_id, url))
    add_audit_log(conn, entity="rss_feeds", action="delete", details=url, profile_id=profile_id)
    conn.close()
    flash("RSS feed removed.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/rss/bulk_delete", methods=["POST"])
def bulk_delete_rss(profile_id: int):
    urls = request.form.getlist("urls")
    if not urls:
        flash("No RSS URLs selected.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for u in urls:
        conn.execute("DELETE FROM rss_feeds WHERE profile_id = ? AND url = ?", (profile_id, u))
        count += 1
    add_audit_log(conn, entity="rss_feeds", action="bulk_delete", details=f"count={count}", profile_id=profile_id)
    conn.close()
    flash(f"Deleted {count} RSS URLs.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# URL sources management
@app.route("/admin/profiles/<int:profile_id>/urls/add", methods=["POST"])
def add_url_source_route(profile_id: int):
    url = request.form.get("url", "").strip()
    mode = request.form.get("mode", "auto").strip()
    sample_link = request.form.get("sample_link", "").strip() or None
    read_more_label = request.form.get("read_more_label", "").strip() or None
    crawl_version = (request.form.get("crawl_version", "v1") or "v1").strip()
    if crawl_version not in ("v1", "v2"):
        crawl_version = "v1"
    
    # Recursive mode parameters
    max_depth = int(request.form.get("max_depth", "2") or "2")
    allowed_domains = request.form.get("allowed_domains", "").strip() or None
    path_filter = request.form.get("path_filter", "").strip() or None
    max_results = int(request.form.get("max_results", "20") or "20")
    date_scope = request.form.get("date_scope", "all").strip() or "all"
    
    if not url:
        flash("URL is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    if mode not in ("auto", "force_static", "force_dynamic", "recursive"):
        flash("Invalid mode.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    upsert_url_source(conn, profile_id, url=url, mode=mode, sample_link=sample_link, read_more_label=read_more_label, 
                     crawl_version=crawl_version, max_depth=max_depth, allowed_domains=allowed_domains, 
                     path_filter=path_filter, max_results=max_results, date_scope=date_scope)
    add_audit_log(conn, entity="url_sources", action="add", details=f"url={url} mode={mode}", profile_id=profile_id)
    conn.close()
    flash("URL source added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/urls/update", methods=["POST"])
def update_url_source_route(profile_id: int):
    url = request.form.get("url", "").strip()
    mode = request.form.get("mode", "").strip()
    sample_link = request.form.get("sample_link", "").strip() or None
    read_more_label = request.form.get("read_more_label", "").strip() or None
    crawl_version = (request.form.get("crawl_version", "").strip() or None)
    if crawl_version and crawl_version not in ("v1", "v2"):
        crawl_version = "v1"
    
    # Recursive mode parameters
    max_depth = int(request.form.get("max_depth", "2") or "2")
    allowed_domains = request.form.get("allowed_domains", "").strip() or None
    path_filter = request.form.get("path_filter", "").strip() or None
    max_results = int(request.form.get("max_results", "20") or "20")
    date_scope = request.form.get("date_scope", "all").strip() or "all"
    
    if not url:
        flash("URL is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    if mode and mode not in ("auto", "force_static", "force_dynamic", "recursive"):
        flash("Invalid mode.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    # Use upsert to update all fields
    upsert_url_source(conn, profile_id, url=url, mode=mode or "auto", sample_link=sample_link, read_more_label=read_more_label, 
                     crawl_version=(crawl_version or "v1"), max_depth=max_depth, allowed_domains=allowed_domains, 
                     path_filter=path_filter, max_results=max_results, date_scope=date_scope)
    add_audit_log(conn, entity="url_sources", action="update", details=f"url={url} mode={mode}", profile_id=profile_id)
    conn.close()
    flash("URL source updated.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/urls/delete", methods=["POST"])
def delete_url_source_route(profile_id: int):
    url = request.form.get("url", "").strip()
    if not url:
        flash("URL is required to delete.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    delete_url_source(conn, profile_id, url=url)
    add_audit_log(conn, entity="url_sources", action="delete", details=url, profile_id=profile_id)
    conn.close()
    flash("URL source removed.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/urls/bulk_delete", methods=["POST"])
def bulk_delete_url_sources(profile_id: int):
    urls = request.form.getlist("urls")
    if not urls:
        flash("No URL sources selected.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for u in urls:
        conn.execute("DELETE FROM url_sources WHERE profile_id = ? AND url = ?", (profile_id, u))
        count += 1
    add_audit_log(conn, entity="url_sources", action="bulk_delete", details=f"count={count}", profile_id=profile_id)
    conn.close()
    flash(f"Deleted {count} URL sources.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# Tweet accounts management
@app.route("/admin/profiles/<int:profile_id>/tweets/add", methods=["POST"])
def add_tweet_account_route(profile_id: int):
    handle = request.form.get("handle", "").strip()
    if not handle:
        flash("Twitter handle is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    upsert_tweet_account(conn, profile_id, handle=handle)
    add_audit_log(conn, entity="tweet_accounts", action="add", details=handle, profile_id=profile_id)
    conn.close()
    flash("Twitter account added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/tweets/delete", methods=["POST"])
def delete_tweet_account_route(profile_id: int):
    handle = request.form.get("handle", "").strip()
    if not handle:
        flash("Twitter handle is required to delete.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("DELETE FROM tweet_accounts WHERE profile_id = ? AND handle = ?", (profile_id, handle))
    add_audit_log(conn, entity="tweet_accounts", action="delete", details=handle, profile_id=profile_id)
    conn.close()
    flash("Twitter account removed.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/tweets/bulk_delete", methods=["POST"])
def bulk_delete_tweet_accounts(profile_id: int):
    handles = request.form.getlist("handles")
    if not handles:
        flash("No Twitter accounts selected.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for h in handles:
        conn.execute("DELETE FROM tweet_accounts WHERE profile_id = ? AND handle = ?", (profile_id, h))
        count += 1
    add_audit_log(conn, entity="tweet_accounts", action="bulk_delete", details=f"count={count}", profile_id=profile_id)
    conn.close()
    flash(f"Deleted {count} Twitter accounts.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/tweets/reset_quota_date/save", methods=["POST"])
def save_tweet_reset_quota_date(profile_id: int):
    date_str = (request.form.get("reset_quota_date", "") or "").strip()
    clear = request.form.get("clear")
    conn = get_connection()
    create_schema_if_needed(conn)
    try:
        if clear or not date_str:
            conn.execute("DELETE FROM settings WHERE profile_id = ? AND key = 'tweets_reset_quota_date'", (profile_id,))
            add_audit_log(conn, entity="tweet_settings", action="set_reset_quota_date", details="date=cleared", profile_id=profile_id)
            flash("Reset quota date cleared.", "success")
        else:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                flash("Invalid date format. Use YYYY-MM-DD.", "error")
                return redirect(url_for("admin_profile_detail", profile_id=profile_id))
            set_setting_value(profile_id, "tweets_reset_quota_date", date_str)
            add_audit_log(conn, entity="tweet_settings", action="set_reset_quota_date", details=f"date={date_str}", profile_id=profile_id)
            flash("Reset quota date saved.", "success")
    finally:
        conn.close()
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# Email receivers management

# Simple add (one at a time)
@app.route("/admin/profiles/<int:profile_id>/emails/add", methods=["POST"])
def add_email_receiver_route(profile_id: int):
    email = request.form.get("email", "").strip()
    if not email or not EMAIL_REGEX.match(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    upsert_email_receiver(conn, profile_id, email=email)
    add_audit_log(conn, entity="email_receivers", action="add", details=email, profile_id=profile_id)
    conn.close()
    flash("Email receiver added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))

# Legacy textarea save (kept for compatibility; hidden in UI)
@app.route("/admin/profiles/<int:profile_id>/emails/save", methods=["POST"])
def save_email_receivers_route(profile_id: int):
    emails_str = request.form.get("emails", "").strip()
    emails = [e.strip() for e in emails_str.split(";") if e.strip()]
    invalid = [e for e in emails if not EMAIL_REGEX.match(e)]
    if invalid:
        flash(f"Invalid emails: {', '.join(invalid)}", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    # Clear existing receivers for profile, then insert the new list
    conn.execute("DELETE FROM email_receivers WHERE profile_id = ?", (profile_id,))
    for e in emails:
        upsert_email_receiver(conn, profile_id, email=e)
    add_audit_log(conn, entity="email_receivers", action="save", details=f"count={len(emails)}", profile_id=profile_id)
    conn.close()

    flash("Email receivers saved.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))

# Single delete
@app.route("/admin/profiles/<int:profile_id>/emails/delete", methods=["POST"])
def delete_email_receiver_route(profile_id: int):
    email = request.form.get("email", "").strip()
    if not email:
        flash("Email is required to delete.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("DELETE FROM email_receivers WHERE profile_id = ? AND email = ?", (profile_id, email))
    add_audit_log(conn, entity="email_receivers", action="delete", details=email, profile_id=profile_id)
    conn.close()
    flash("Email receiver removed.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/emails/bulk_delete", methods=["POST"])
def bulk_delete_email_receivers(profile_id: int):
    emails = request.form.getlist("emails")
    if not emails:
        flash("No email receivers selected.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for e in emails:
        conn.execute("DELETE FROM email_receivers WHERE profile_id = ? AND email = ?", (profile_id, e))
        count += 1
    add_audit_log(conn, entity="email_receivers", action="bulk_delete", details=f"count={count}", profile_id=profile_id)
    conn.close()
    flash(f"Deleted {count} email receivers.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# Update receiver translation language
@app.route("/admin/profiles/<int:profile_id>/emails/update_language", methods=["POST"])
def update_email_receiver_language(profile_id: int):
    email = request.form.get("email", "").strip()
    translation_lang = request.form.get("translation_lang", "en").strip()
    
    if not email:
        flash("Email is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    
    # Validate language code
    if translation_lang not in LANGUAGE_NAMES:
        flash(f"Invalid language code: {translation_lang}", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    upsert_email_receiver_with_lang(conn, profile_id, email, translation_lang)
    add_audit_log(conn, entity="email_receivers", action="update_language", 
                  details=f"email={email} lang={translation_lang}", profile_id=profile_id)
    conn.close()
    
    lang_name = LANGUAGE_NAMES.get(translation_lang, translation_lang)
    flash(f"Translation language updated to {lang_name}.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# Glossary management (basic CRUD)
@app.route("/admin/profiles/<int:profile_id>/glossary/terms/add", methods=["POST"])
def add_glossary_term_route(profile_id: int):
    term = request.form.get("term", "").strip()
    lang = request.form.get("lang", "en").strip() or "en"
    category = request.form.get("category") or None
    product = request.form.get("product") or None
    weight = request.form.get("weight", "1.0").strip()
    notes = request.form.get("notes") or None

    if not term:
        flash("Term is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    try:
        weight_val = float(weight)
    except ValueError:
        flash("Weight must be a number.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    # Reuse existing helper
    from configurations.db import add_glossary_term as add_term_helper
    term_id = add_term_helper(conn, profile_id, term, lang, category, product, weight_val, notes)
    add_audit_log(conn, entity="glossary_terms", action="add", details=f"id={term_id} term={term}", profile_id=profile_id)
    conn.close()
    flash("Glossary term added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/glossary/terms/delete", methods=["POST"])
def delete_glossary_term_route(profile_id: int):
    term_id = request.form.get("term_id", "").strip()
    if not term_id.isdigit():
        flash("Invalid term id.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("DELETE FROM glossary_terms WHERE id = ? AND profile_id = ?", (int(term_id), profile_id))
    add_audit_log(conn, entity="glossary_terms", action="delete", details=f"id={term_id}", profile_id=profile_id)
    conn.close()
    flash("Glossary term deleted.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/glossary/terms/bulk_delete", methods=["POST"])
def bulk_delete_glossary_terms_route(profile_id: int):
    ids = request.form.getlist("term_ids")
    if not ids:
        flash("No terms selected.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for tid in ids:
        if tid.isdigit():
            conn.execute("DELETE FROM glossary_terms WHERE id = ? AND profile_id = ?", (int(tid), profile_id))
            count += 1
    add_audit_log(conn, entity="glossary_terms", action="bulk_delete", details=f"count={count}", profile_id=profile_id)
    conn.close()
    flash(f"Deleted {count} terms.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/glossary/synonyms/add", methods=["POST"])
def add_glossary_synonym_route(profile_id: int):
    term_id = request.form.get("term_id", "").strip()
    synonym = request.form.get("synonym", "").strip()
    if not term_id.isdigit() or not synonym:
        flash("Term id and synonym are required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    from configurations.db import add_glossary_synonym as add_syn_helper
    add_syn_helper(conn, int(term_id), synonym)
    add_audit_log(conn, entity="glossary_synonyms", action="add", details=f"term_id={term_id} synonym={synonym}", profile_id=profile_id)
    conn.close()
    flash("Synonym added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/glossary/synonyms/delete", methods=["POST"])
def delete_glossary_synonym_route(profile_id: int):
    term_id = request.form.get("term_id", "").strip()
    synonym = request.form.get("synonym", "").strip()
    if not term_id.isdigit() or not synonym:
        flash("Term id and synonym are required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("DELETE FROM glossary_synonyms WHERE term_id = ? AND synonym = ?", (int(term_id), synonym))
    add_audit_log(conn, entity="glossary_synonyms", action="delete", details=f"term_id={term_id} synonym={synonym}", profile_id=profile_id)
    conn.close()
    flash("Synonym removed.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/glossary/patterns/add", methods=["POST"])
def add_glossary_pattern_route(profile_id: int):
    term_id = request.form.get("term_id", "").strip()
    regex = request.form.get("regex", "").strip()
    if not term_id.isdigit() or not regex:
        flash("Term id and regex are required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    # Validate regex is compilable
    try:
        re.compile(regex)
    except re.error:
        flash("Invalid regex pattern.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    from configurations.db import add_glossary_pattern as add_pat_helper
    add_pat_helper(conn, int(term_id), regex)
    add_audit_log(conn, entity="glossary_patterns", action="add", details=f"term_id={term_id} regex={regex}", profile_id=profile_id)
    conn.close()
    flash("Pattern added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/glossary/patterns/delete", methods=["POST"])
def delete_glossary_pattern_route(profile_id: int):
    term_id = request.form.get("term_id", "").strip()
    regex = request.form.get("regex", "").strip()
    if not term_id.isdigit() or not regex:
        flash("Term id and regex are required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("DELETE FROM glossary_patterns WHERE term_id = ? AND regex = ?", (int(term_id), regex))
    add_audit_log(conn, entity="glossary_patterns", action="delete", details=f"term_id={term_id} regex={regex}", profile_id=profile_id)
    conn.close()
    flash("Pattern removed.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# Simplified Glossary: add single term
@app.route("/admin/profiles/<int:profile_id>/glossary/term/add_simple", methods=["POST"])
def add_glossary_term_simple_route(profile_id: int):
    term = request.form.get("term", "").strip()
    if not term:
        flash("Term is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    from configurations.db import add_glossary_term as add_term_helper
    term_id = add_term_helper(conn, profile_id, term, "en", None, None, 1.0, None)
    add_audit_log(conn, entity="glossary_terms", action="add_simple", details=f"id={term_id} term={term}", profile_id=profile_id)
    conn.close()
    flash("Term added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# Simplified Glossary: bulk add (one term per line)
@app.route("/admin/profiles/<int:profile_id>/glossary/term/bulk_add", methods=["POST"])
def add_glossary_term_bulk_route(profile_id: int):
    bulk_text = request.form.get("bulk_terms", "") or ""
    lines = [ln.strip() for ln in bulk_text.splitlines() if ln.strip()]
    if not lines:
        flash("No terms provided.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    conn = get_connection()
    create_schema_if_needed(conn)
    from configurations.db import add_glossary_term as add_term_helper
    count = 0
    for t in lines:
        add_term_helper(conn, profile_id, t, "en", None, None, 1.0, None)
        count += 1
    add_audit_log(conn, entity="glossary_terms", action="bulk_add", details=f"count={count}", profile_id=profile_id)
    conn.close()
    flash(f"Added {count} terms.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))




# Historical news clear (per profile)
@app.route("/admin/profiles/<int:profile_id>/news/clear", methods=["POST"])
def clear_profile_news(profile_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    # Block if a run is currently active for this profile
    running = conn.execute("SELECT 1 FROM runs WHERE profile_id = ? AND status = 'Running' LIMIT 1", (profile_id,)).fetchone()
    if running:
        conn.close()
        flash("Cannot clear while a run is active.", "error")
        return redirect(url_for("admin_profile_runs", profile_id=profile_id))
    # Count and clear
    row = conn.execute("SELECT COUNT(*) AS cnt FROM news_items WHERE profile_id = ?", (profile_id,)).fetchone()
    count = int(row["cnt"] or 0)
    if count > 0:
        conn.execute("DELETE FROM news_items WHERE profile_id = ?", (profile_id,))
        add_audit_log(conn, entity="news_items", action="clear_all", details=f"count={count}", profile_id=profile_id)
        conn.close()
        flash(f"Cleared {count} news items for this profile.", "success")
    else:
        conn.close()
        flash("No historical news to clear.", "info")
    return redirect(url_for("admin_profile_runs", profile_id=profile_id))

# Manual migration utility
@app.route("/admin/migrate_urls", methods=["POST"])
def admin_migrate_urls():
    count = migrate_urls_to_unified(profile_id=None)
    flash(f"Migrated {count} URLs to unified url_sources (mode=auto).", "success")
    return redirect(url_for("admin_dashboard"))


# -----------------------
# Filtered News Review (for glossary enhancement)
# -----------------------

@app.route("/admin/profiles/<int:profile_id>/review")
def admin_review_news(profile_id: int):
    """
    Review filtered news items for a profile.
    Allows manual scoring to improve glossary/filtering accuracy.
    """
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    
    # Prune old filtered news (30 days retention)
    try:
        prune_old_filtered_news(conn, days=30)
    except Exception:
        pass
    
    prof = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if not prof:
        conn.close()
        flash("Profile not found.", "error")
        return redirect(url_for("admin_dashboard"))
    
    profile = {
        "id": int(prof["id"]),
        "country_code": prof["country_code"],
        "lob": prof["lob"],
        "name": prof["name"],
        "language": prof["language"],
        "active": int(prof["active"] or 0),
    }
    
    # Filter parameters
    filter_reviewed = request.args.get("reviewed")
    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page
    
    reviewed = None
    if filter_reviewed == "yes":
        reviewed = True
    elif filter_reviewed == "no":
        reviewed = False
    
    # Get counts
    total_count = count_filtered_news(conn, profile_id, reviewed=None)
    pending_count = count_filtered_news(conn, profile_id, reviewed=False)
    reviewed_count = count_filtered_news(conn, profile_id, reviewed=True)
    
    # Get filtered news items
    items = list_filtered_news(conn, profile_id, reviewed=reviewed, limit=per_page, offset=offset)
    
    # Calculate pagination
    filtered_count = count_filtered_news(conn, profile_id, reviewed=reviewed)
    total_pages = (filtered_count + per_page - 1) // per_page
    
    conn.close()
    
    return render_template(
        "review_news.html",
        profile=profile,
        items=items,
        total_count=total_count,
        pending_count=pending_count,
        reviewed_count=reviewed_count,
        filter_reviewed=filter_reviewed,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
    )


@app.route("/admin/profiles/<int:profile_id>/review/score", methods=["POST"])
def score_filtered_news(profile_id: int):
    """
    Update the relevance score for a filtered news item.
    Score scale: 1 (not relevant) to 5 (highly relevant)
    """
    item_id = request.form.get("item_id", "").strip()
    score = request.form.get("score", "").strip()
    
    if not item_id.isdigit():
        flash("Invalid item ID.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    if not score.isdigit() or int(score) < 1 or int(score) > 5:
        flash("Score must be between 1 and 5.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    update_filtered_news_score(conn, int(item_id), int(score))
    add_audit_log(conn, entity="filtered_news", action="score", details=f"item_id={item_id} score={score}", profile_id=profile_id)
    conn.close()
    
    flash(f"Score updated to {score}.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/review/delete", methods=["POST"])
def delete_filtered_news_item(profile_id: int):
    """
    Delete a single filtered news item.
    """
    item_id = request.form.get("item_id", "").strip()
    
    if not item_id.isdigit():
        flash("Invalid item ID.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    delete_filtered_news(conn, int(item_id))
    add_audit_log(conn, entity="filtered_news", action="delete", details=f"item_id={item_id}", profile_id=profile_id)
    conn.close()
    
    flash("Item deleted.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/review/clear", methods=["POST"])
def clear_filtered_news_route(profile_id: int):
    """
    Clear filtered news items for a profile.
    Can clear all or only reviewed items.
    """
    clear_type = request.form.get("clear_type", "all")
    reviewed_only = (clear_type == "reviewed")
    
    conn = get_connection()
    create_schema_if_needed(conn)
    count = clear_filtered_news(conn, profile_id, reviewed_only=reviewed_only)
    
    action_detail = "reviewed only" if reviewed_only else "all"
    add_audit_log(conn, entity="filtered_news", action="clear", details=f"type={action_detail} count={count}", profile_id=profile_id)
    conn.close()
    
    if count > 0:
        flash(f"Cleared {count} filtered news items ({action_detail}).", "success")
    else:
        flash("No items to clear.", "info")
    
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/review/bulk_score", methods=["POST"])
def bulk_score_filtered_news(profile_id: int):
    """
    Bulk score multiple filtered news items.
    """
    item_ids = request.form.getlist("item_ids")
    score = request.form.get("bulk_score", "").strip()
    
    if not item_ids:
        flash("No items selected.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    if not score.isdigit() or int(score) < 1 or int(score) > 5:
        flash("Score must be between 1 and 5.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for item_id in item_ids:
        if item_id.isdigit():
            update_filtered_news_score(conn, int(item_id), int(score))
            count += 1
    
    add_audit_log(conn, entity="filtered_news", action="bulk_score", details=f"count={count} score={score}", profile_id=profile_id)
    conn.close()
    
    flash(f"Updated {count} items with score {score}.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/review/bulk_delete", methods=["POST"])
def bulk_delete_filtered_news(profile_id: int):
    """
    Bulk delete multiple filtered news items.
    """
    item_ids = request.form.getlist("item_ids")
    
    if not item_ids:
        flash("No items selected.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for item_id in item_ids:
        if item_id.isdigit():
            delete_filtered_news(conn, int(item_id))
            count += 1
    
    add_audit_log(conn, entity="filtered_news", action="bulk_delete", details=f"count={count}", profile_id=profile_id)
    conn.close()
    
    flash(f"Deleted {count} items.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


# Run Flask
if __name__ == "__main__":
    _ensure_schema()
    # Auto-migrate legacy crawl_urls/snap_urls into unified url_sources (idempotent)
    try:
        migrate_urls_to_unified(profile_id=None)
    except Exception as e:
        # Do not block server start on migration errors
        print(f"⚠️ Auto-migration skipped or failed: {e}")
    app.run(host="127.0.0.1", port=8080, debug=True)
