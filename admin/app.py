import os
import re
import threading
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
from flask import Response, stream_with_context
from flask import send_from_directory
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

# Ensure project root is on sys.path for module imports (configurations, agents)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Load .env from project root so credentials are available when launched via
# launchd (which doesn't inherit the shell environment).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
except ImportError:
    pass
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
    load_profile_date_scope,
    save_profile_date_scope,
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
    # combined news review (baseline + filtered)
    list_all_news_for_review,
    count_all_news_for_review,
    update_news_item_score,
    delete_news_item,
    # legal repo
    create_repo_node,
    update_repo_node,
    delete_repo_node,
    get_repo_node,
    list_repo_countries,
    list_repo_tree,
    list_repo_nodes,
    get_repo_node_by_news,
    add_repo_asset,
    list_repo_assets,
    delete_repo_asset,
    advance_repo_node_status,
    STATUS_PROGRESSION,
    # source attribution (v3.0)
    create_authority,
    list_authorities,
    get_authority,
    update_authority,
    delete_authority,
    reset_review_data,
)

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("LEGAL_EAGLE_ADMIN_SECRET", "local-only-admin")
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Auto-reload templates without server restart

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


def render_md(text: str) -> str:
    try:
        import markdown as _md
        from markupsafe import Markup
        return Markup(_md.markdown(text or "", extensions=["extra", "nl2br"]))
    except Exception:
        from markupsafe import Markup, escape
        return Markup("<pre>" + escape(text or "") + "</pre>")


app.jinja_env.filters["render_md"] = render_md

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ensure_schema():
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.close()


@app.route("/")
def root():
    return redirect(url_for("admin_dashboard"))


def _fmt_last_run(iso_ts):
    """Relative 'x ago' string for a run timestamp; 'Never run' when absent."""
    if not iso_ts:
        return "Never run"
    try:
        last_dt = datetime.fromisoformat(iso_ts)
        mins = int((datetime.utcnow() - last_dt).total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins} min ago"
        if mins < 1440:
            h = mins // 60
            return f"{h} hour{'s' if h != 1 else ''} ago"
        d = mins // 1440
        return f"{d} day{'s' if d != 1 else ''} ago"
    except Exception:
        return "Never run"


def _shell_context(conn, selected_id=None):
    """Build the FCL shell context (profile list + summary aggregates + selected meta)
    shared by the dashboard/configure/run/review routes."""
    def src_count(pid):
        return conn.execute(
            "SELECT (SELECT COUNT(*) FROM rss_feeds WHERE profile_id=?) "
            "+ (SELECT COUNT(*) FROM tweet_accounts WHERE profile_id=?) "
            "+ (SELECT COUNT(*) FROM url_sources WHERE profile_id=?)",
            (pid, pid, pid),
        ).fetchone()[0]

    rows = conn.execute(
        "SELECT id, country_code, lob, name, active, language FROM profiles ORDER BY country_code, lob"
    ).fetchall()
    plist = []
    for r in rows:
        pid = int(r["id"])
        last = conn.execute(
            "SELECT started_at FROM runs WHERE profile_id=? AND started_at IS NOT NULL "
            "ORDER BY started_at DESC LIMIT 1", (pid,)
        ).fetchone()
        lt = last["started_at"] if last and last["started_at"] else None
        d = dict(r)
        d["last_run_time"] = lt
        d["last_run_display"] = _fmt_last_run(lt)
        d["review_count"] = count_all_news_for_review(conn, pid)
        d["source_count"] = src_count(pid)
        plist.append(d)

    total = len(plist)
    review_total = sum(p["review_count"] for p in plist)
    recent = sum(1 for p in plist if p["last_run_time"])
    return {
        "profiles_list": plist,
        "profiles_total": total,
        "review_total": review_total,
        "recently_run_count": recent,
        "never_run_count": total - recent,
        "selected_meta": next((p for p in plist if p["id"] == selected_id), None),
    }


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
        
        # Review count + source count for the summary strip and profile rows
        review_count = count_all_news_for_review(conn, profile_id)
        source_count = conn.execute(
            "SELECT (SELECT COUNT(*) FROM rss_feeds WHERE profile_id=?) "
            "+ (SELECT COUNT(*) FROM tweet_accounts WHERE profile_id=?) "
            "+ (SELECT COUNT(*) FROM url_sources WHERE profile_id=?)",
            (profile_id, profile_id, profile_id),
        ).fetchone()[0]

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
            "review_count": review_count,
            "source_count": source_count,
        })

    # Sort by last run (never/oldest first), then by country/lob as secondary sort
    profiles.sort(key=lambda p: (p["last_run_sort_key"], p["country_code"], p["lob"]))

    conn.close()

    # Summary-strip aggregates
    profiles_total = len(profiles)
    review_total = sum(p["review_count"] for p in profiles)
    recently_run_count = sum(1 for p in profiles if p["last_run_time"])
    never_run_count = profiles_total - recently_run_count

    return render_template("dashboard.html", profiles=profiles,
                           selected_profile=None, active_tab="configure",
                           review_badge_count=0,
                           profiles_total=profiles_total,
                           review_total=review_total,
                           recently_run_count=recently_run_count,
                           never_run_count=never_run_count)


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
    shell = _shell_context(conn, profile_id)
    profiles_list = shell["profiles_list"]
    _sel = shell["selected_meta"]
    profile["source_count"] = _sel["source_count"] if _sel else 0
    profile["last_run_display"] = _sel["last_run_display"] if _sel else "Never run"
    profile["language_name"] = LANGUAGE_NAMES.get(profile["language"], profile["language"])
    review_badge_count = count_all_news_for_review(conn, profile_id)
    # Compute news count and whether a run is currently active for this profile
    try:
        row_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM news_items WHERE profile_id = ?", (profile_id,)).fetchone()
        news_count = int(row_cnt["cnt"] or 0)
    except Exception:
        news_count = 0
    
    # Also check filtered_news count (items awaiting manual review)
    try:
        row_filtered = conn.execute("SELECT COUNT(*) AS cnt FROM filtered_news WHERE profile_id = ?", (profile_id,)).fetchone()
        filtered_news_count = int(row_filtered["cnt"] or 0)
    except Exception:
        filtered_news_count = 0
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
        account_list = ", ".join([f"@{(a['handle'] if isinstance(a, dict) else str(a)).lstrip('@')}" for a in twitter_accounts])
        
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

    # Load sources for the profile (for source selection UI)
    import json
    rss_feeds = load_rss_feeds(profile_id)
    twitter_accounts = load_tweet_accounts(profile_id)
    url_sources = load_url_sources(profile_id)
    
    # Convert to simple lists for JavaScript
    rss_urls = [feed["url"] if isinstance(feed, dict) else feed for feed in rss_feeds]
    twitter_handles = [acc["handle"] if isinstance(acc, dict) else acc for acc in twitter_accounts]
    url_source_urls = [src["url"] for src in url_sources]
    
    sources_json = json.dumps({
        "rss": rss_urls,
        "twitter": twitter_handles,
        "urls": url_source_urls
    })
    
    # Calculate total history count and disable_clear flag
    total_history = news_count + filtered_news_count
    disable_clear = run_active or total_history == 0
    
    # Get Twitter error flag (if any)
    conn = get_connection()
    twitter_error_flag = db_get_setting(conn, profile_id, 'twitter_error_flag')
    conn.close()

    return render_template(
        "run_status.html",
        profile=profile,
        selected_profile=profile,
        profiles=profiles_list,
        active_tab='run',
        review_badge_count=review_badge_count,
        runs=runs,
        selected_run=selected_run,
        news_count=news_count,
        filtered_news_count=filtered_news_count,
        total_history=total_history,
        disable_clear=disable_clear,
        run_active=run_active,
        twitter_status=twitter_status,
        twitter_error_flag=twitter_error_flag,
        resource_status=resource_status,
        sources_json=sources_json,
        rss_feeds=rss_feeds,
        tweets=twitter_accounts,
        url_sources=url_sources,
        profiles_total=shell["profiles_total"],
        review_total=shell["review_total"],
        recently_run_count=shell["recently_run_count"],
        never_run_count=shell["never_run_count"],
    )


# DISABLED: ANS provision route — re-enable for BTP deployment
# @app.route("/admin/profiles/<int:profile_id>/ans/provision", methods=["POST"])
# def admin_ans_provision(profile_id: int):
#     from agents.ans_sender import get_ans_sender
#     receivers = load_email_receivers_with_lang(profile_id)
#     emails = [r["email"] for r in receivers]
#     sender = get_ans_sender()
#     if not sender:
#         flash("ANS not bound — cannot provision.", "error")
#         return redirect(url_for("admin_profile_detail", profile_id=profile_id))
#     errors = []
#     ok_count = 0
#     for email in emails:
#         try:
#             sender.ensure_provisioned(email)
#             ok_count += 1
#         except Exception as e:
#             errors.append(f"{email}: {str(e)[:120]}")
#     if errors:
#         flash("ANS provision errors: " + " | ".join(errors), "error")
#     else:
#         flash(f"ANS: {ok_count} recipient(s) provisioned successfully.", "success")
#     return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# Confirm run → create, start, redirect to same page with run_id so right pane streams logs
@app.route("/admin/profiles/<int:profile_id>/runs/start", methods=["POST"])
def admin_start_run(profile_id: int):
    _ensure_schema()

    # Get run options from form
    lookback_override = request.form.get('lookback_override', '').strip() or None
    force_run = (lookback_override == 'force_full')  # map force_full override → force_run flag
    test_mode = request.form.get('test_mode') == '1'
    skip_comparison = request.form.get('skip_comparison') == '1'
    skip_filtering = request.form.get('skip_filtering') == '1'
    skip_email = (request.form.get('skip_email') == '1') or test_mode
    skip_grouping = request.form.get('skip_grouping') == '1'
    if test_mode:
        lookback_override = '7'
    
    # Get source selections from form (getlist returns [] if not present)
    selected_rss = request.form.getlist('selected_rss')
    selected_twitter = request.form.getlist('selected_twitter')
    selected_urls = request.form.getlist('selected_urls')
    
    # Smart detection: check if UI sections were rendered (hidden flags)
    # If flag exists but list is empty → user wants none (explicit empty selection)
    # If flag doesn't exist → user wants all (backward compatibility for API calls)
    has_rss_ui = request.form.get('has_rss_sources') == '1'
    has_twitter_ui = request.form.get('has_twitter_sources') == '1'
    has_urls_ui = request.form.get('has_url_sources') == '1'
    
    # Apply smart logic: empty list means "none" if UI was shown, "all" if no UI
    # None = run all (backward compatibility), [] = run none (explicit), [items] = run selected
    if has_rss_ui and not selected_rss:
        selected_rss = []  # Explicit empty selection
    elif not has_rss_ui:
        selected_rss = None  # No UI shown, run all
    # else: keep selected_rss as-is (has items)
    
    if has_twitter_ui and not selected_twitter:
        selected_twitter = []  # Explicit empty selection
    elif not has_twitter_ui:
        selected_twitter = None  # No UI shown, run all
    # else: keep selected_twitter as-is (has items)
    
    if has_urls_ui and not selected_urls:
        selected_urls = []  # Explicit empty selection
    elif not has_urls_ui:
        selected_urls = None  # No UI shown, run all
    # else: keep selected_urls as-is (has items)
    
    conn = get_connection()
    create_schema_if_needed(conn)
    # Audit request with options
    run_details = f"manual run from run page (force_run={force_run}, skip_comparison={skip_comparison}, skip_filtering={skip_filtering}, skip_email={skip_email}, skip_grouping={skip_grouping}, rss={len(selected_rss) if selected_rss else 'all'}, twitter={len(selected_twitter) if selected_twitter else 'all'}, urls={len(selected_urls) if selected_urls else 'all'})"
    add_audit_log(conn, entity="profiles", action="run_requested", details=run_details, profile_id=profile_id)
    run_id = create_run(conn, profile_id, origin="manual")
    conn.close()

    # Background worker
    def _worker(pid: int, rid: int, force: bool, skip_comp: bool, skip_filt: bool, skip_mail: bool, skip_grp: bool, sel_rss, sel_twitter, sel_urls):
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
                        self.orig.write(f"[RUN-{self.run_id}] {line}\n")
                except Exception as e:
                    self.orig.write(f"[log error] {e}\n")
            def flush(self):
                try:
                    if self.buf:
                        conn_i = get_connection()
                        create_schema_if_needed(conn_i)
                        append_run_log(conn_i, self.run_id, "INFO", self.buf)
                        conn_i.close()
                        self.orig.write(f"[RUN-{self.run_id}] {self.buf}")
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
        error_step = None
        error_message = None
        try:
            from agents.agents_controller import run_profile_once

            # cancel checker
            def _cancel() -> bool:
                cconn = get_connection()
                create_schema_if_needed(cconn)
                flag = is_cancel_requested(cconn, rid)
                cconn.close()
                return flag

            ok = run_profile_once(pid, force_run=force, skip_comparison=skip_comp, skip_filter=skip_filt, skip_email=skip_mail,
                                selected_rss_urls=sel_rss, selected_twitter_handles=sel_twitter,
                                selected_url_sources=sel_urls,
                                lookback_override=lookback_override if lookback_override != 'force_full' else None,
                                skip_grouping=skip_grp, should_cancel=_cancel)
            status_final = "Success" if ok else "Failed"
            # v3.3: email lifecycle — PENDING (follow-on thread will update to SENT/FAILED)
            if skip_mail:
                email_status = "SKIPPED"
            elif ok:
                email_status = "PENDING"
            else:
                email_status = "FAILED"
        except Exception as e:
            status_final = "Failed"
            error_step = "pipeline"
            error_message = f"{type(e).__name__}: {e}"[:500]
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
            # F3: record structured failure info (surfaced in run status UI)
            _metrics = {"email_status": email_status}
            if status_mark == "Failed":
                _metrics["error_step"] = error_step or "pipeline"
                _metrics["error_message"] = error_message or "Run returned failure — see log above."
            finish_run(fconn, rid, status_mark, metrics=_metrics)
            append_run_log(fconn, rid, "INFO", f"🏁 Run {rid} finished with status {status_mark}")
            fconn.close()

            # v3.3: follow-on digest thread (normal mode only, run succeeded)
            if status_mark == "Success" and not skip_mail:
                def _digest_worker(run_id_d=rid, pid_d=pid):
                    try:
                        from agents.email_sender import send_digest
                        from configurations.creds import creds as _creds
                        d_conn = get_connection()
                        create_schema_if_needed(d_conn)
                        send_digest(pid_d, run_id_d, None, d_conn, _creds.get("gmail", {}))
                        d_conn.close()
                    except Exception as _de:
                        print(f"⚠️ Digest worker exception: {_de}")
                        try:
                            _ec = get_connection()
                            _ec.execute("UPDATE runs SET email_status='FAILED' WHERE id=?", (run_id_d,))
                            _ec.commit()
                            _ec.close()
                        except Exception:
                            pass
                threading.Thread(target=_digest_worker, daemon=True).start()

    threading.Thread(target=_worker, args=(profile_id, run_id, force_run, skip_comparison, skip_filtering, skip_email, skip_grouping, selected_rss, selected_twitter, selected_urls), daemon=True).start()
    return redirect(url_for("admin_profile_runs", profile_id=profile_id, run_id=run_id))


# SSE stream for logs
@app.route("/admin/runs/<int:run_id>/stream")
def stream_run_logs(run_id: int):
    _ensure_schema()
    def _event_stream():
        last_seq = request.headers.get("Last-Event-ID")
        last_seq = int(last_seq) if last_seq else None
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
                yield f"id: {last_seq}\ndata: {payload}\n\n"
            # check status
            if run_row and run_row.get("status") in ("Success", "Failed", "Canceled"):
                # send terminal event
                yield f"event: done\ndata: {run_row['status']}\n\n"
                finished = True
                break
            time.sleep(0.75)
    return Response(stream_with_context(_event_stream()), mimetype="text/event-stream")


# ── Run All Active (v3.1, Group 7) ─────────────────────────────────────────
# Sequentially runs every active profile in a background thread. Skip-on-failure:
# a failed profile is recorded and the next one starts immediately. One session at
# a time. Live state is held in memory and pushed via SSE (run_all_status).
_run_all_lock = threading.Lock()
_run_all_state: Dict[str, Any] = {
    "running": False, "total": 0, "done": 0, "current_pid": None,
    "started_at": None, "finished_at": None, "profiles": {},
}


def _run_all_worker(profiles: List[Dict[str, Any]]):
    try:
        from agents.agents_controller import run_profile_once
        for p in profiles:
            pid = int(p["id"])
            with _run_all_lock:
                _run_all_state["current_pid"] = pid
                _run_all_state["profiles"][str(pid)]["status"] = "running"
            ok = False
            detail = ""
            try:
                ok = run_profile_once(pid, force_run=False, skip_email=False)
                if not ok:
                    detail = "run returned failure"
            except Exception as e:
                detail = f"{type(e).__name__}: {e}"[:200]
                ok = False
            with _run_all_lock:
                _run_all_state["profiles"][str(pid)]["status"] = "success" if ok else "failed"
                _run_all_state["profiles"][str(pid)]["detail"] = detail
                _run_all_state["done"] += 1
    finally:
        with _run_all_lock:
            _run_all_state["running"] = False
            _run_all_state["current_pid"] = None
            _run_all_state["finished_at"] = datetime.utcnow().isoformat()


@app.route("/admin/run-all", methods=["POST"])
def admin_run_all():
    _ensure_schema()
    with _run_all_lock:
        if _run_all_state["running"]:
            flash("A Run-All session is already in progress.", "error")
            return redirect(url_for("admin_dashboard"))
        profiles = list_active_profiles() or []
        if not profiles:
            flash("No active profiles to run.", "error")
            return redirect(url_for("admin_dashboard"))
        _run_all_state.update({
            "running": True, "total": len(profiles), "done": 0, "current_pid": None,
            "started_at": datetime.utcnow().isoformat(), "finished_at": None,
            "profiles": {
                str(int(p["id"])): {
                    "name": p.get("name") or f'{p.get("country_code")}/{p.get("lob")}',
                    "status": "pending", "detail": "",
                } for p in profiles
            },
        })
        snapshot = list(profiles)
    try:
        conn = get_connection(); create_schema_if_needed(conn)
        add_audit_log(conn, entity="profiles", action="run_all_requested",
                      details=f"{len(snapshot)} active profile(s)", profile_id=None)
        conn.close()
    except Exception:
        pass
    threading.Thread(target=_run_all_worker, args=(snapshot,), daemon=True).start()
    flash(f"Run-All started for {len(snapshot)} active profile(s).", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/run-all/status")
def admin_run_all_status():
    from flask import jsonify
    with _run_all_lock:
        return jsonify(dict(_run_all_state))


@app.route("/admin/run-all/stream")
def admin_run_all_stream():
    import json as _json
    def _stream():
        while True:
            with _run_all_lock:
                st = dict(_run_all_state)
            yield f"data: {_json.dumps(st)}\n\n"
            if not st["running"]:
                yield "event: done\ndata: end\n\n"
                break
            time.sleep(1.0)
    return Response(stream_with_context(_stream()), mimetype="text/event-stream")

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
    active_tab = request.args.get("tab", "configure")
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
        "date_scope": prof["date_scope"] if "date_scope" in prof.keys() else "all",
    }

    # FCL shell context (profile list + summary aggregates + selected meta)
    shell = _shell_context(conn, profile_id)
    profiles_list = shell["profiles_list"]
    profiles_total = shell["profiles_total"]
    review_total = shell["review_total"]
    recently_run_count = shell["recently_run_count"]
    never_run_count = shell["never_run_count"]
    sel = shell["selected_meta"]
    profile["source_count"] = sel["source_count"] if sel else 0
    profile["last_run_display"] = sel["last_run_display"] if sel else "Never run"
    profile["language_name"] = LANGUAGE_NAMES.get(profile["language"], profile["language"])

    authorities = list_authorities(conn, profile_id)
    review_badge_count = count_all_news_for_review(conn, profile_id)
    conn.close()

    rss = load_rss_feeds(profile_id)
    urls = load_url_sources(profile_id)
    
    # Enhance URL sources with formatted timestamps
    for s in urls:
        if s.get('last_successful_fetch'):
            try:
                dt = datetime.fromisoformat(s['last_successful_fetch'])
                now = datetime.utcnow()
                delta = now - dt
                
                # Relative time (e.g., "2 hours ago")
                if delta.days > 0:
                    s['last_successful_fetch_relative'] = f"{delta.days}d ago"
                elif delta.seconds >= 3600:
                    s['last_successful_fetch_relative'] = f"{delta.seconds // 3600}h ago"
                else:
                    s['last_successful_fetch_relative'] = f"{delta.seconds // 60}m ago"
                
                # Absolute time (e.g., "Jan 5, 10:30 AM")
                s['last_successful_fetch_formatted'] = dt.strftime("%b %d, %I:%M %p")
            except Exception:
                s['last_successful_fetch_relative'] = "Unknown"
                s['last_successful_fetch_formatted'] = s['last_successful_fetch']
    
    tweets = load_tweet_accounts(profile_id)
    receivers = load_email_receivers(profile_id)
    receivers_semicolon = "; ".join(receivers) if receivers else ""
    receivers_with_lang = load_email_receivers_with_lang(profile_id)

    glossary = load_glossary(profile_id)
    reset_quota_date = get_setting_value(profile_id, 'tweets_reset_quota_date')
    monitor_enabled = get_setting_value(profile_id, 'monitor_updates_enabled', 'false') == 'true'

    # DISABLED: ANS check — re-enable for BTP deployment
    # from agents.ans_sender import get_ans_sender
    # try:
    #     ans_available = bool(get_ans_sender())
    # except Exception:
    #     ans_available = False
    ans_available = False

    return render_template(
        "profile.html",
        profile=profile,
        selected_profile=profile,
        profiles=profiles_list,
        active_tab=active_tab,
        authorities=authorities,
        review_badge_count=review_badge_count,
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
        ans_available=ans_available,
        profiles_total=profiles_total,
        review_total=review_total,
        recently_run_count=recently_run_count,
        never_run_count=never_run_count,
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


@app.route("/admin/profiles/<int:profile_id>/date-scope/update", methods=["POST"])
def update_profile_date_scope(profile_id: int):
    """Update the default lookback window for a profile."""
    date_scope = (request.form.get("date_scope", "") or "").strip()
    allowed = ("all", "delta", "last_7_days", "last_30_days", "today", "")
    if date_scope not in allowed:
        flash("Invalid lookback window value.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    save_profile_date_scope(profile_id, date_scope or "all")
    conn = get_connection()
    create_schema_if_needed(conn)
    add_audit_log(conn, entity="profiles", action="update_date_scope", details=f"date_scope={date_scope or 'all'}", profile_id=profile_id)
    conn.close()

    label_map = {"all": "N/A (no limit)", "last_7_days": "Last 7 days", "last_30_days": "Last 30 days"}
    flash(f"Default lookback window updated to: {label_map.get(date_scope or 'all', date_scope)}.", "success")
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
    publisher_name = request.form.get("publisher_name", "").strip() or None
    auth_raw = request.form.get("authority_id", "").strip()
    authority_id = int(auth_raw) if auth_raw.isdigit() else None
    conn = get_connection()
    create_schema_if_needed(conn)
    upsert_rss_feed(conn, profile_id, url, publisher_name=publisher_name, authority_id=authority_id)
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
    url_date_template = request.form.get("url_date_template", "").strip() or None

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
                     path_filter=path_filter, max_results=max_results,
                     url_date_template=url_date_template)
    add_audit_log(conn, entity="url_sources", action="add", details=f"url={url} mode={mode}", profile_id=profile_id)
    conn.close()
    flash("URL source added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


# ── Source Simulator (v3.1, F9) ─────────────────────────────────────────────
@app.route("/admin/profiles/<int:profile_id>/urls/simulate", methods=["POST"])
def simulate_url_source(profile_id: int):
    """SSE endpoint — streams Source Simulator progress events as JSON lines.
    action: 'start' (fetch + depth loop → containers_found) or 'confirm'
    (map fields → buttons → pagination → sample → complete)."""
    import json as _json
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "start")
    url = data.get("url", "")

    from agents.source_simulator import run_simulation, run_simulation_from_confirmed_container
    try:
        from agents.sap_ai_client import create_sap_aicore_client
        ai_client = create_sap_aicore_client()
    except Exception:
        ai_client = None

    def generate():
        if action == "confirm":
            gen = run_simulation_from_confirmed_container(
                html=data.get("html", ""), url=url,
                container_selector=data.get("container_selector", ""),
                depth_level=data.get("depth_level", 0),
                requires_js=bool(data.get("requires_js", False)),
                ai_client=ai_client,
            )
        else:
            gen = run_simulation(url, ai_client=ai_client, max_depth=data.get("max_depth", 5))
        for event in gen:
            yield f"data: {_json.dumps(event)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/admin/profiles/<int:profile_id>/urls/simulate/save", methods=["POST"])
def save_url_simulation(profile_id: int):
    """Persist a completed simulation result onto the url_source row."""
    from flask import jsonify
    from configurations.db import save_simulation_result
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "")
    if not url:
        return jsonify({"error": "url required"}), 400
    conn = get_connection()
    create_schema_if_needed(conn)
    save_simulation_result(
        conn, profile_id, url,
        sample_link=data.get("sample_link"),
        container_selector=data.get("container_selector"),
        field_selectors=data.get("field_selectors"),
        read_more_selector=data.get("read_more_selector"),
        pagination_type=data.get("pagination_type"),
        pagination_selector=data.get("pagination_selector"),
        depth_level=data.get("depth_level"),
        requires_js=int(bool(data.get("requires_js", False))),
    )
    add_audit_log(conn, entity="url_sources", action="simulate", details=f"url={url}", profile_id=profile_id)
    conn.close()
    return jsonify({"ok": True})


@app.route("/admin/profiles/<int:profile_id>/urls/update", methods=["POST"])
def update_url_source_route(profile_id: int):
    url = request.form.get("url", "").strip()          # original URL (identity key)
    new_url = request.form.get("new_url", "").strip()  # updated URL (may differ)
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
    url_date_template = request.form.get("url_date_template", "").strip() or None

    if not url:
        flash("URL is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    if mode and mode not in ("auto", "force_static", "force_dynamic", "recursive"):
        flash("Invalid mode.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))

    # Use new_url if provided and different, otherwise keep original
    target_url = new_url if new_url else url

    conn = get_connection()
    create_schema_if_needed(conn)
    # If URL was changed, delete old row first then insert new
    if target_url != url:
        conn.execute("DELETE FROM url_sources WHERE profile_id=? AND url=?", (profile_id, url))
        conn.commit()
    upsert_url_source(conn, profile_id, url=target_url, mode=mode or "auto", sample_link=sample_link,
                     read_more_label=read_more_label, crawl_version=(crawl_version or "v1"),
                     max_depth=max_depth, allowed_domains=allowed_domains,
                     path_filter=path_filter, max_results=max_results,
                     url_date_template=url_date_template)
    add_audit_log(conn, entity="url_sources", action="update", details=f"url={target_url} mode={mode}", profile_id=profile_id)
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


@app.route("/admin/profiles/<int:profile_id>/url-sources/reset-fetch", methods=["POST"])
def reset_url_source_fetch(profile_id: int):
    """
    Reset last_successful_fetch timestamp for a URL source.
    Forces the next run to do a full scan instead of delta.
    """
    url = request.form.get("url", "").strip()
    if not url:
        flash("URL is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute(
        "UPDATE url_sources SET last_successful_fetch = NULL WHERE profile_id = ? AND url = ?",
        (profile_id, url)
    )
    add_audit_log(conn, entity="url_sources", action="reset_fetch", details=f"url={url}", profile_id=profile_id)
    conn.close()
    
    flash(f"Reset fetch timestamp for {url}. Next run will do a full scan.", "success")
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


@app.route("/admin/profiles/<int:profile_id>/tweets/clear-error", methods=["POST"])
def clear_twitter_error_flag_route(profile_id: int):
    from configurations.db import set_setting
    conn = get_connection()
    create_schema_if_needed(conn)
    set_setting(conn, profile_id, "twitter_error_flag", "")
    add_audit_log(conn, entity="tweet_accounts", action="clear_error", details="", profile_id=profile_id)
    conn.close()
    flash("Twitter error flag cleared.", "success")
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
    # DISABLED: ANS auto-provisioning — re-enable for BTP deployment
    # from agents.ans_sender import get_ans_sender
    # sender = get_ans_sender()
    # if sender:
    #     try:
    #         sender.ensure_provisioned(email)
    #     except Exception as e:
    #         flash(f"Email added, but ANS provisioning failed: {str(e)[:120]}", "error")
    #         return redirect(url_for("admin_profile_detail", profile_id=profile_id))
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
    # DISABLED: ANS auto-provisioning — re-enable for BTP deployment
    # from agents.ans_sender import get_ans_sender
    # sender = get_ans_sender()
    # if sender:
    #     ans_errors = []
    #     for e in emails:
    #         try:
    #             sender.ensure_provisioned(e)
    #         except Exception as ex:
    #             ans_errors.append(f"{e}: {str(ex)[:80]}")
    #     if ans_errors:
    #         flash("Emails saved, but ANS provisioning failed for: " + ", ".join(ans_errors), "error")
    #         return redirect(url_for("admin_profile_detail", profile_id=profile_id))
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


# -----------------------
# Authority CRUD (v3.0)
# -----------------------

@app.route("/admin/profiles/<int:profile_id>/authorities.json")
def list_authorities_json(profile_id: int):
    from flask import jsonify
    conn = get_connection()
    create_schema_if_needed(conn)
    auths = list_authorities(conn, profile_id)
    conn.close()
    return jsonify({"authorities": auths})


@app.route("/admin/profiles/<int:profile_id>/authorities/add", methods=["POST"])
def add_authority_route(profile_id: int):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Authority name is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    aliases = request.form.get("aliases", "").strip()
    conn = get_connection()
    create_schema_if_needed(conn)
    create_authority(conn, profile_id, name, aliases)
    add_audit_log(conn, entity="authorities", action="add", details=name, profile_id=profile_id)
    conn.close()
    flash(f"Authority '{name}' added.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/authorities/<int:auth_id>/update", methods=["POST"])
def update_authority_route(profile_id: int, auth_id: int):
    name = request.form.get("name", "").strip()
    if not name:
        flash("Authority name is required.", "error")
        return redirect(url_for("admin_profile_detail", profile_id=profile_id))
    conn = get_connection()
    create_schema_if_needed(conn)
    update_authority(conn, auth_id, name, request.form.get("aliases", "").strip())
    add_audit_log(conn, entity="authorities", action="update", details=f"id={auth_id}", profile_id=profile_id)
    conn.close()
    flash("Authority updated.", "success")
    return redirect(url_for("admin_profile_detail", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/authorities/<int:auth_id>/delete", methods=["POST"])
def delete_authority_route(profile_id: int, auth_id: int):
    conn = get_connection()
    create_schema_if_needed(conn)
    delete_authority(conn, auth_id)
    add_audit_log(conn, entity="authorities", action="delete", details=f"id={auth_id}", profile_id=profile_id)
    conn.close()
    flash("Authority deleted.", "success")
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
    
    # Count both tables
    row_news = conn.execute("SELECT COUNT(*) AS cnt FROM news_items WHERE profile_id = ?", (profile_id,)).fetchone()
    news_count = int(row_news["cnt"] or 0)
    
    row_filtered = conn.execute("SELECT COUNT(*) AS cnt FROM filtered_news WHERE profile_id = ?", (profile_id,)).fetchone()
    filtered_count = int(row_filtered["cnt"] or 0)
    
    total_count = news_count + filtered_count
    
    if total_count > 0:
        # Clear both tables (wrapped in transaction for commit)
        with conn:
            if news_count > 0:
                conn.execute("DELETE FROM news_items WHERE profile_id = ?", (profile_id,))
            if filtered_count > 0:
                conn.execute("DELETE FROM filtered_news WHERE profile_id = ?", (profile_id,))
            
            add_audit_log(conn, entity="news_history", action="clear_all", 
                         details=f"baseline={news_count} filtered={filtered_count} total={total_count}", 
                         profile_id=profile_id)
        conn.close()
        flash(f"Cleared {total_count} items ({news_count} baseline + {filtered_count} filtered).", "success")
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
    Review ALL news items (accepted + filtered) for a profile.
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
    filter_source = request.args.get("source")  # 'accepted', 'filtered', or None (all)
    filter_reviewed = request.args.get("reviewed")  # 'yes', 'no', or None (all)
    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page
    
    # Parse filters - enforce unscored for Accepted/Filtered tabs
    source = None
    reviewed = None
    
    if filter_source == "accepted":
        source = "accepted"
        # Force unscored for Accepted tab (unless explicitly viewing reviewed)
        if filter_reviewed != "yes":
            reviewed = False
    elif filter_source == "filtered":
        source = "filtered"
        # Force unscored for Filtered tab (unless explicitly viewing reviewed)
        if filter_reviewed != "yes":
            reviewed = False
    
    if filter_reviewed == "yes":
        reviewed = True
        source = None  # Reviewed tab shows all sources
    
    # Get counts for the 3 stats cards
    accepted_unscored_count = count_all_news_for_review(conn, profile_id, source="accepted", reviewed=False)
    filtered_unscored_count = count_all_news_for_review(conn, profile_id, source="filtered", reviewed=False)
    reviewed_count = count_all_news_for_review(conn, profile_id, source=None, reviewed=True)
    
    # Get news items with combined view
    items = list_all_news_for_review(conn, profile_id, source=source, reviewed=reviewed, limit=per_page, offset=offset)
    
    # Calculate pagination
    filtered_count_for_pagination = count_all_news_for_review(conn, profile_id, source=source, reviewed=reviewed)
    total_pages = (filtered_count_for_pagination + per_page - 1) // per_page

    # Build repo node map: news_id -> repo_node_id (for badge display)
    repo_node_map = {}
    for row in conn.execute("SELECT id, source_news_id FROM repo_nodes WHERE source_news_id IS NOT NULL").fetchall():
        repo_node_map[row["source_news_id"]] = row["id"]

    # Parent options for L2S Prompt modal dropdown
    repo_parent_options = list_repo_nodes(conn, profile["country_code"])

    # FCL shell context (list + summary aggregates + selected meta)
    shell = _shell_context(conn, profile_id)
    profiles_list = shell["profiles_list"]
    _sel = shell["selected_meta"]
    profile["source_count"] = _sel["source_count"] if _sel else 0
    profile["last_run_display"] = _sel["last_run_display"] if _sel else "Never run"
    profile["language_name"] = LANGUAGE_NAMES.get(profile["language"], profile["language"])
    review_badge_count = count_all_news_for_review(conn, profile_id)

    # v3.4: Build Topic→Announcement→Sources hierarchy from latest run
    from configurations.db import get_announcements_for_run_with_sources
    topics = []
    latest_run_id = None
    latest_run_row = conn.execute(
        "SELECT id FROM runs WHERE profile_id=? ORDER BY id DESC LIMIT 1",
        (profile_id,),
    ).fetchone()
    if latest_run_row:
        latest_run_id = latest_run_row["id"]
        announcements = get_announcements_for_run_with_sources(conn, latest_run_id)
        # Group by topic_label
        topic_map: dict = {}
        for ann in announcements:
            lbl = ann.get("topic_label") or "General"
            topic_map.setdefault(lbl, []).append(ann)
        for lbl, anns in topic_map.items():
            topics.append({
                "topic_label": lbl,
                "announcements": anns,
                "source_count": sum(len(a.get("sources", [])) for a in anns),
            })

    # v3.2: authority list for inferred-authority override dropdown
    authorities_for_override = list_authorities(conn, profile_id)

    conn.close()

    return render_template(
        "review_news.html",
        profile=profile,
        selected_profile=profile,
        profiles=profiles_list,
        active_tab='review',
        review_badge_count=review_badge_count,
        items=items,
        accepted_unscored_count=accepted_unscored_count,
        filtered_unscored_count=filtered_unscored_count,
        reviewed_count=reviewed_count,
        filter_source=filter_source,
        filter_reviewed=filter_reviewed,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        repo_node_map=repo_node_map,
        repo_parent_options=repo_parent_options,
        profiles_total=shell["profiles_total"],
        review_total=shell["review_total"],
        recently_run_count=shell["recently_run_count"],
        never_run_count=shell["never_run_count"],
        authorities_for_override=authorities_for_override,
        profile_id=profile_id,
        topics=topics,
        latest_run_id=latest_run_id,
    )


@app.route("/admin/profiles/<int:profile_id>/news/<int:item_id>/authority", methods=["POST"])
def set_news_item_authority(profile_id: int, item_id: int):
    """v3.2: Override authority attribution for an inferred-status news item."""
    auth_raw = request.form.get("authority_id", "").strip()
    authority_id = int(auth_raw) if auth_raw.isdigit() else None
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE news_items SET authority_id=?, authority_status='manual' WHERE id=? AND profile_id=?",
            (authority_id, item_id, profile_id),
        )
    conn.close()
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/review/score", methods=["POST"])
def score_filtered_news(profile_id: int):
    item_id_str = request.form.get("item_id", "").strip()
    item_source = request.form.get("item_source", "").strip()  # Optional explicit source
    score = request.form.get("score", "").strip()
    
    # Parse item_id:source format
    if ":" in item_id_str:
        parts = item_id_str.split(":", 1)
        item_id = parts[0]
        item_source = parts[1]
    else:
        item_id = item_id_str
        # Default to filtered for backwards compatibility
        if not item_source:
            item_source = "filtered"
    
    if not item_id.isdigit():
        flash("Invalid item ID.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    if not score.isdigit() or int(score) < 1 or int(score) > 5:
        flash("Score must be between 1 and 5.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    update_news_item_score(conn, int(item_id), item_source, int(score))
    add_audit_log(conn, entity="news_review", action="score", 
                  details=f"item_id={item_id} source={item_source} score={score}", profile_id=profile_id)
    conn.close()
    
    flash(f"Score updated to {score}.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/review/delete", methods=["POST"])
def delete_filtered_news_item(profile_id: int):
    """
    Delete a single news item (accepted or filtered).
    Format: item_id can be "123" (legacy) or "123:source" (new format)
    """
    item_id_str = request.form.get("item_id", "").strip()
    item_source = request.form.get("item_source", "").strip()  # Optional explicit source
    
    # Parse item_id:source format
    if ":" in item_id_str:
        parts = item_id_str.split(":", 1)
        item_id = parts[0]
        item_source = parts[1]
    else:
        item_id = item_id_str
        # Default to filtered for backwards compatibility
        if not item_source:
            item_source = "filtered"
    
    if not item_id.isdigit():
        flash("Invalid item ID.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    delete_news_item(conn, int(item_id), item_source)
    add_audit_log(conn, entity="news_review", action="delete", 
                  details=f"item_id={item_id} source={item_source}", profile_id=profile_id)
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
    Bulk score multiple news items (accepted or filtered).
    Format: item_ids can be ["123", "456"] (legacy) or ["123:accepted", "456:filtered"] (new)
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
    for item_id_str in item_ids:
        # Parse "id:source" format
        if ":" in item_id_str:
            parts = item_id_str.split(":", 1)
            item_id = parts[0]
            item_source = parts[1]
        else:
            item_id = item_id_str
            item_source = "filtered"  # Backwards compatibility
        
        if item_id.isdigit():
            update_news_item_score(conn, int(item_id), item_source, int(score))
            count += 1
    
    add_audit_log(conn, entity="news_review", action="bulk_score", details=f"count={count} score={score}", profile_id=profile_id)
    conn.close()
    
    flash(f"Updated {count} items with score {score}.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/admin/profiles/<int:profile_id>/review/bulk_delete", methods=["POST"])
def bulk_delete_filtered_news(profile_id: int):
    """
    Bulk delete multiple news items (accepted or filtered).
    Format: item_ids can be ["123", "456"] (legacy) or ["123:accepted", "456:filtered"] (new)
    """
    item_ids = request.form.getlist("item_ids")
    
    if not item_ids:
        flash("No items selected.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))
    
    conn = get_connection()
    create_schema_if_needed(conn)
    count = 0
    for item_id_str in item_ids:
        # Parse "id:source" format
        if ":" in item_id_str:
            parts = item_id_str.split(":", 1)
            item_id = parts[0]
            item_source = parts[1]
        else:
            item_id = item_id_str
            item_source = "filtered"  # Backwards compatibility
        
        if item_id.isdigit():
            delete_news_item(conn, int(item_id), item_source)
            count += 1
    
    add_audit_log(conn, entity="news_review", action="bulk_delete", details=f"count={count}", profile_id=profile_id)
    conn.close()
    
    flash(f"Deleted {count} items.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


# Email preview route
@app.route("/admin/profiles/<int:profile_id>/email_preview")
def serve_email_preview(profile_id: int):
    """
    Serve the email preview HTML file generated during test mode runs.
    """
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    prof = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    conn.close()
    
    if not prof:
        flash("Profile not found.", "error")
        return redirect(url_for("admin_dashboard"))
    
    country_code = prof["country_code"]
    lob = prof["lob"]
    profile_slug = f"{country_code}_{lob}"
    
    preview_path = os.path.join(BASE_DIR, "outputs", profile_slug, "email_preview.html")
    
    if not os.path.exists(preview_path):
        flash("No email preview available. Run the profile in test mode first.", "error")
        return redirect(url_for("admin_profile_runs", profile_id=profile_id))
    
    try:
        with open(preview_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        from flask import Response
        return Response(html_content, mimetype='text/html')
    except Exception as e:
        flash(f"Error loading email preview: {e}", "error")
        return redirect(url_for("admin_profile_runs", profile_id=profile_id))


# Resend email from HTML preview
@app.route("/admin/profiles/<int:profile_id>/resend_email", methods=["POST"])
def resend_email_from_preview(profile_id: int):
    """
    Resend email from HTML preview file with translation support.
    Parses email_preview.html and sends to all configured receivers.
    """
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    prof = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    
    if not prof:
        conn.close()
        flash("Profile not found.", "error")
        return redirect(url_for("admin_dashboard"))
    
    country_code = prof["country_code"]
    lob = prof["lob"]
    profile_slug = f"{country_code}_{lob}"
    
    # Check if email preview exists
    preview_path = os.path.join(BASE_DIR, "outputs", profile_slug, "email_preview.html")
    if not os.path.exists(preview_path):
        conn.close()
        flash("No email preview available. Run the profile first.", "error")
        return redirect(url_for("admin_profile_runs", profile_id=profile_id))
    
    add_audit_log(conn, entity="email", action="resend_from_preview", details=f"profile={profile_slug}", profile_id=profile_id)
    conn.close()
    
    # Import the resend function
    from scripts.resend_email_from_html import resend_email_from_html
    
    try:
        success = resend_email_from_html(profile_id, country_code, lob)
        if success:
            flash("Email sent successfully to all receivers with translation!", "success")
        else:
            flash("Email sending failed. Check logs for details.", "error")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Resend email error:\n{error_details}")
        flash(f"Error: {str(e)}", "error")
    
    return redirect(url_for("admin_profile_runs", profile_id=profile_id))


# v3.3: V2 Digest send API
@app.route("/admin/send-email", methods=["POST"])
def send_email_v2():
    """Send V2 AI digest.

    Body (JSON):
      Option A — manual from Review: {"item_ids": [1,2,3], "profile_id": 42}
      Option B — Resend from run log: {"run_id": 17, "profile_id": 42}

    Returns: {"status": "sent"|"error", "items_sent": N, "message": "..."}
    """
    _ensure_schema()
    data = request.get_json(silent=True) or {}
    profile_id_req = data.get("profile_id")
    run_id_req = data.get("run_id")
    item_ids_req = data.get("item_ids")

    if not profile_id_req:
        return jsonify({"status": "error", "message": "profile_id required"}), 400

    conn = get_connection()
    create_schema_if_needed(conn)

    # Validate profile exists
    prof = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id_req,)).fetchone()
    if not prof:
        conn.close()
        return jsonify({"status": "error", "message": "Profile not found"}), 404

    # Determine run_id: use supplied or create a synthetic one
    if run_id_req:
        run_row = conn.execute(
            "SELECT id FROM runs WHERE id=? AND profile_id=?", (run_id_req, profile_id_req)
        ).fetchone()
        if not run_row:
            conn.close()
            return jsonify({"status": "error", "message": "Run not found for this profile"}), 404
        effective_run_id = run_id_req
    else:
        # Manual send: create a virtual run record
        conn.execute(
            "INSERT INTO runs(profile_id, status, email_status, created_at) VALUES(?,?,?,datetime('now'))",
            (profile_id_req, "Success", "SENDING"),
        )
        conn.commit()
        effective_run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    try:
        from agents.email_sender import send_digest
        from configurations.creds import creds as _creds
        ok = send_digest(
            profile_id_req, effective_run_id,
            [int(i) for i in item_ids_req] if item_ids_req else None,
            conn, _creds.get("gmail", {})
        )
        items_sent = len(item_ids_req) if item_ids_req else 0
        conn.close()
        if ok:
            return jsonify({"status": "sent", "items_sent": items_sent})
        else:
            return jsonify({"status": "error", "message": "Send failed — check server logs"}), 500
    except Exception as e:
        conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Legal Repo ──────────────────────────────────────────────────────────────

@app.route("/admin/legal-repo")
def admin_legal_repo():
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    countries = list_repo_countries(conn)
    country = request.args.get("country", countries[0] if countries else None)
    domain = request.args.get("domain")
    subdomain = request.args.get("subdomain")
    node_id = request.args.get("node_id", type=int)

    tree = list_repo_tree(conn, country) if country else []
    nodes = list_repo_nodes(conn, country, domain, subdomain) if country else []

    selected_node = None
    assets = []
    if node_id:
        selected_node = get_repo_node(conn, node_id)
        if selected_node:
            assets = list_repo_assets(conn, node_id)

    parent_options = list_repo_nodes(conn, country) if country else []
    conn.close()
    return render_template(
        "legal_repo.html",
        countries=countries,
        selected_country=country,
        selected_domain=domain,
        selected_subdomain=subdomain,
        tree=tree,
        nodes=nodes,
        selected_node=selected_node,
        assets=assets,
        parent_options=parent_options,
        status_progression=STATUS_PROGRESSION,
    )


@app.route("/admin/legal-repo/nodes/create", methods=["POST"])
def admin_legal_repo_node_create():
    _ensure_schema()
    from datetime import date as _date
    country = request.form.get("country_code", "").strip().upper()
    domain = request.form.get("domain", "").strip()
    subdomain = request.form.get("subdomain", "").strip()
    topic = request.form.get("topic", "").strip()
    authority = request.form.get("authority", "").strip() or None
    law_reference = request.form.get("law_reference", "").strip() or None
    official_url = request.form.get("official_url", "").strip() or None
    summary = request.form.get("summary", "").strip() or None
    effective_date = request.form.get("effective_date", "").strip() or None
    parent_node_id = request.form.get("parent_node_id", type=int) or None

    if not all([country, domain, subdomain, topic]):
        flash("Country, domain, subdomain, and topic are required.", "error")
        return redirect(url_for("admin_legal_repo", country=country))

    conn = get_connection()
    create_schema_if_needed(conn)
    nid = create_repo_node(
        conn, country, domain, subdomain, topic,
        authority=authority, law_reference=law_reference,
        official_url=official_url, summary=summary,
        effective_date=effective_date,
        date_detected=_date.today().isoformat(),
        parent_node_id=parent_node_id,
    )
    add_audit_log(conn, entity="repo_nodes", action="create",
                  details=f"{country}/{domain}/{subdomain}/{topic}", profile_id=None)
    conn.close()
    flash("Node created.", "success")
    return redirect(url_for("admin_legal_repo", country=country, node_id=nid))


@app.route("/admin/legal-repo/nodes/<int:node_id>/update", methods=["POST"])
def admin_legal_repo_node_update(node_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    node = get_repo_node(conn, node_id)
    if not node:
        conn.close()
        flash("Node not found.", "error")
        return redirect(url_for("admin_legal_repo"))

    fields = {}
    for f in ["domain", "subdomain", "topic", "authority", "law_reference",
              "official_url", "summary", "effective_date"]:
        val = request.form.get(f, "").strip() or None
        fields[f] = val
    fields["parent_node_id"] = request.form.get("parent_node_id", type=int) or None

    update_repo_node(conn, node_id, **fields)
    add_audit_log(conn, entity="repo_nodes", action="update",
                  details=f"node_id={node_id}", profile_id=None)
    conn.close()
    flash("Node updated.", "success")
    return redirect(url_for("admin_legal_repo", country=node["country_code"], node_id=node_id))


@app.route("/admin/legal-repo/nodes/<int:node_id>/delete", methods=["POST"])
def admin_legal_repo_node_delete(node_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    node = get_repo_node(conn, node_id)
    if not node:
        conn.close()
        flash("Node not found.", "error")
        return redirect(url_for("admin_legal_repo"))
    country = node["country_code"]
    delete_repo_node(conn, node_id)
    add_audit_log(conn, entity="repo_nodes", action="delete",
                  details=f"node_id={node_id}", profile_id=None)
    conn.close()
    flash("Node deleted.", "success")
    return redirect(url_for("admin_legal_repo", country=country))


@app.route("/admin/legal-repo/nodes/<int:node_id>/advance-status", methods=["POST"])
def admin_legal_repo_node_advance(node_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    node = get_repo_node(conn, node_id)
    if not node:
        conn.close()
        flash("Node not found.", "error")
        return redirect(url_for("admin_legal_repo"))
    country = node["country_code"]
    new_status = advance_repo_node_status(conn, node_id)
    conn.close()
    if new_status:
        flash(f"Status advanced to {new_status}.", "success")
    else:
        flash("Already at final status (COMPLETE).", "info")
    return redirect(url_for("admin_legal_repo", country=country, node_id=node_id))


@app.route("/admin/legal-repo/nodes/<int:node_id>/assets/add", methods=["POST"])
def admin_legal_repo_asset_add(node_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    node = get_repo_node(conn, node_id)
    if not node:
        conn.close()
        flash("Node not found.", "error")
        return redirect(url_for("admin_legal_repo"))
    asset_type = request.form.get("asset_type", "").strip()
    title = request.form.get("title", "").strip()
    reference = request.form.get("reference", "").strip() or None
    url = request.form.get("url", "").strip() or None
    if not asset_type or not title:
        conn.close()
        flash("Asset type and title are required.", "error")
        return redirect(url_for("admin_legal_repo", country=node["country_code"], node_id=node_id))
    add_repo_asset(conn, node_id, asset_type, title, reference, url)
    add_audit_log(conn, entity="repo_assets", action="add",
                  details=f"node_id={node_id} type={asset_type}", profile_id=None)
    conn.close()
    flash("Asset linked.", "success")
    return redirect(url_for("admin_legal_repo", country=node["country_code"], node_id=node_id))


@app.route("/admin/legal-repo/assets/<int:asset_id>/delete", methods=["POST"])
def admin_legal_repo_asset_delete(asset_id: int):
    _ensure_schema()
    conn = get_connection()
    create_schema_if_needed(conn)
    asset = conn.execute("SELECT * FROM repo_assets WHERE id=?", (asset_id,)).fetchone()
    if not asset:
        conn.close()
        flash("Asset not found.", "error")
        return redirect(url_for("admin_legal_repo"))
    node = get_repo_node(conn, asset["node_id"])
    country = node["country_code"] if node else None
    node_id = asset["node_id"]
    delete_repo_asset(conn, asset_id)
    conn.close()
    flash("Asset removed.", "success")
    return redirect(url_for("admin_legal_repo", country=country, node_id=node_id))


# ── L2S Prompt (from Review page) ───────────────────────────────────────────

@app.route("/admin/profiles/<int:profile_id>/news/<int:news_id>/to-legal-repo", methods=["POST"])
def admin_news_to_legal_repo(profile_id: int, news_id: int):
    _ensure_schema()
    from datetime import date as _date
    conn = get_connection()
    create_schema_if_needed(conn)

    existing = get_repo_node_by_news(conn, news_id)
    if existing:
        conn.close()
        flash("This news item is already linked to a repo node.", "info")
        return redirect(url_for("admin_review_news", profile_id=profile_id))

    prof = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
    country = prof["country_code"] if prof else ""

    domain = request.form.get("domain", "").strip()
    subdomain = request.form.get("subdomain", "").strip()
    topic = request.form.get("topic", "").strip()
    authority = request.form.get("authority", "").strip() or None
    law_reference = request.form.get("law_reference", "").strip() or None
    official_url = request.form.get("official_url", "").strip() or None
    parent_node_id = request.form.get("parent_node_id", type=int) or None

    if not all([domain, subdomain, topic]):
        conn.close()
        flash("Domain, subdomain, and topic are required.", "error")
        return redirect(url_for("admin_review_news", profile_id=profile_id))

    nid = create_repo_node(
        conn, country, domain, subdomain, topic,
        authority=authority, law_reference=law_reference,
        official_url=official_url, source_news_id=news_id,
        date_detected=_date.today().isoformat(),
        parent_node_id=parent_node_id,
    )
    add_audit_log(conn, entity="repo_nodes", action="create_from_news",
                  details=f"news_id={news_id} node_id={nid}", profile_id=profile_id)
    conn.close()
    flash("Node created in Legal Repo.", "success")
    return redirect(url_for("admin_review_news", profile_id=profile_id))


@app.route("/Resources/<path:filename>")
def serve_resource_file(filename: str):
    resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Resources")
    return send_from_directory(resources_dir, filename)


@app.route("/admin/import-config", methods=["POST"])
def admin_import_config():
    """Import BTP seed data from btp_seed_data.json. Protected by admin secret."""
    secret = request.form.get("secret", "").strip()
    expected = os.environ.get("LEGAL_EAGLE_ADMIN_SECRET", "")
    if not expected or secret != expected:
        from flask import abort
        abort(403)

    seed_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "btp_seed_data.json")
    if not os.path.exists(seed_file):
        flash("btp_seed_data.json not found — run export_config.py locally and cf push first.", "error")
        return redirect(url_for("admin_dashboard"))

    import json as _json
    with open(seed_file, "r", encoding="utf-8") as f:
        data = _json.load(f)

    tables = [
        "profiles", "url_sources", "rss_feeds", "tweet_accounts", "email_receivers",
        "glossary_terms", "glossary_synonyms", "glossary_patterns", "repo_nodes", "repo_assets",
    ]

    conn = get_connection()
    create_schema_if_needed(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in reversed(tables):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")

    total = 0
    for table in tables:
        rows = data.get(table, [])
        if not rows:
            continue
        cols = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        for row in rows:
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
        conn.commit()
        total += len(rows)

    conn.close()
    flash(f"Config imported: {total} rows across {len(tables)} tables.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/profiles/<int:profile_id>/preflight")
def admin_preflight(profile_id: int):
    """Pre-run checklist — returns JSON {checks: [{label, ok, message}], ready: bool}."""
    _ensure_schema()
    import json as _json
    conn = get_connection()
    create_schema_if_needed(conn)

    from configurations.db import list_rss_feeds, list_tweet_accounts, list_email_receivers_with_lang
    from configurations.db import list_url_sources

    rss = list_rss_feeds(conn, profile_id)
    tweets = list_tweet_accounts(conn, profile_id)
    urls = list_url_sources(conn, profile_id)
    emails = list_email_receivers_with_lang(conn, profile_id)
    has_sources = bool(rss or tweets or urls)

    checks = []

    # 1. At least one source
    checks.append({
        "label": "At least one source configured (RSS, URL, or Twitter)",
        "ok": has_sources,
        "message": "" if has_sources else "Add at least one RSS feed, URL source, or Twitter account in Configure.",
    })

    # 2. Email receiver
    checks.append({
        "label": "Email receiver configured",
        "ok": bool(emails),
        "message": "" if emails else "Add at least one email receiver in Configure.",
    })

    # 3. AI Core credentials
    ai_vars = [
        "LEGAL_EAGLE_SAP_AICORE_BASE_URL",
        "LEGAL_EAGLE_SAP_AICORE_CLIENT_ID",
        "LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET",
        "LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID",
    ]
    missing_ai = [v for v in ai_vars if not os.environ.get(v)]
    checks.append({
        "label": "SAP AI Core credentials set",
        "ok": not missing_ai,
        "message": "" if not missing_ai else f"Missing env vars: {', '.join(missing_ai)}",
    })

    # 4. Twitter token — only if profile has Twitter accounts
    if tweets:
        twitter_token = os.environ.get("LEGAL_EAGLE_TWITTER_BEARER_TOKEN", "")
        try:
            from agents.tweet_feed import get_twitter_error_flag
            tw_error, _ = get_twitter_error_flag(profile_id, conn)
        except Exception:
            tw_error = None
        twitter_ok = bool(twitter_token) and not tw_error
        msg = ""
        if not twitter_token:
            msg = "LEGAL_EAGLE_TWITTER_BEARER_TOKEN env var is not set."
        elif tw_error:
            msg = f"Twitter API error flagged: {tw_error}"
        checks.append({
            "label": "Twitter API token valid",
            "ok": twitter_ok,
            "message": msg,
        })

    conn.close()
    ready = all(c["ok"] for c in checks)
    from flask import jsonify
    return jsonify({"checks": checks, "ready": ready})


@app.route("/admin/profiles/<int:profile_id>/review/translate", methods=["POST"])
def admin_review_translate(profile_id: int):
    """Batch-translate review items to English via SAP AI Core."""
    from flask import jsonify, request as _req
    data = _req.get_json(force=True, silent=True) or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"translations": {}})

    # Build compact batch for the prompt (id + title + first 300 chars of content)
    batch = []
    for it in items:
        batch.append({
            "id": str(it.get("id", "")),
            "source": str(it.get("item_source", "")),
            "title": (it.get("title") or "")[:200],
            "content": (it.get("content") or "")[:300],
        })

    import json as _json
    prompt_content = _json.dumps(batch, ensure_ascii=False)
    system_msg = (
        "You are a professional legal translator. Translate the given items to English. "
        "Return a JSON object with key 'translations', whose value is an array of objects, "
        "each with: id (string), title_en (string), content_en (string). "
        "Keep translations concise and accurate. Preserve proper nouns."
    )

    try:
        from agents.email_sender import _get_ai_client
        client = _get_ai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt_content},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        result_text = response.choices[0].message.content.strip()
        result = _json.loads(result_text)
        # Normalise to {id: {title_en, content_en}} dict
        translations = {}
        for t in result.get("translations", []):
            translations[str(t.get("id", ""))] = {
                "title_en": t.get("title_en", ""),
                "content_en": t.get("content_en", ""),
            }
        return jsonify({"translations": translations})
    except Exception as e:
        return jsonify({"translations": {}, "error": str(e)}), 200


@app.route("/admin/reset-review-data", methods=["POST"])
def reset_review_data_route():
    profile_id = request.json.get("profile_id") if request.json else None
    conn = get_connection()
    try:
        counts = reset_review_data(conn, profile_id)
        conn.commit()
        return jsonify({"ok": True, "deleted": counts})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


# Run Flask
if __name__ == "__main__":
    _ensure_schema()
    # Auto-migrate legacy crawl_urls/snap_urls into unified url_sources (idempotent)
    try:
        migrate_urls_to_unified(profile_id=None)
    except Exception as e:
        # Do not block server start on migration errors
        print(f"⚠️ Auto-migration skipped or failed: {e}")
    
    # BTP-compatible configuration: use PORT env var or default to 8080
    port = int(os.environ.get("PORT", 8080))
    # Enable debug mode for local development (auto-reload on code changes)
    # But NEVER use reloader when running in background (causes orphan processes)
    debug = os.environ.get("FLASK_ENV") != "production"
    # Always disable reloader to prevent port conflicts and orphan processes
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
