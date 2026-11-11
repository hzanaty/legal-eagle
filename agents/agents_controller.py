from datetime import datetime, timedelta
from typing import Optional, List

dubai_time = datetime.utcnow() + timedelta(hours=4)

print("✅ Agent controller is starting...")

import os

# Helper: safe ISO parse (returns None on failure)
def _parse_iso(s: str):
    try:
        return datetime.fromisoformat(s) if s else None
    except Exception:
        return None

from configurations.config_loader import (
    creds,
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
    load_url_sources,
    get_reviewed_baseline,
    parse_date_scope,
    load_profile_date_scope,
    update_url_source_fetch_timestamp,
    update_rss_feed_last_fetch_timestamp,
    update_tweet_account_last_fetch_timestamp,
)
print("✅ Config and creds imported")
from configurations.db import get_connection, create_schema_if_needed, insert_filtered_news

from agents.rss_parser import parse_rss_feed
from agents.tweet_feed import search_tweets_multi_account, check_twitter_rate_limit
from agents.url_sources_runner import run_unified_sources, scrape_url_source_with_config
from agents.compare_news import run_compare_news_agent
from agents.authority_attributor import build_feed_config, build_url_config, attribute_items
from agents.health_check import run_health_checks, summarize, hard_failures
from agents.news_ranker import rank_items
from agents.email_sender import send_email
from agents.news_filter import filter_items_by_date, filter_source_items
from agents.email_inbox_parser import fetch_monitor_updates, format_monitor_updates_for_email
from urllib.parse import urlparse


def _build_category_glossary_text(glossary_flat: dict, lob: str) -> dict:
    """
    Convert flattened glossary into the legacy dict used by news_filter.

    Category-aware rules:
    - Respect per-term categories (HCM/FIN) when building the lists.
    - If a term has no category, default it to the current profile's LoB (to keep coverage).
    - Include synonyms in the same category list for better coverage.
    """
    groups = {"HCM": [], "FIN": []}
    active_lob = "FIN" if (lob or "").upper() == "FIN" else "HCM"

    for term in glossary_flat.get("terms", []):
        name = (term.get("term") or "").strip()
        if not name:
            continue
        cat = (term.get("category") or "").upper()
        if cat not in ("HCM", "FIN"):
            cat = active_lob
        groups[cat].append(name)
        # include synonyms as terms for better coverage in the same category
        for s in (term.get("synonyms") or []):
            s_name = (s or "").strip()
            if s_name:
                groups[cat].append(s_name)

    hcm_text = ", ".join(sorted(set(groups["HCM"]))) if groups["HCM"] else ""
    fin_text = ", ".join(sorted(set(groups["FIN"]))) if groups["FIN"] else ""
    other_text = "Any content not related to HCM or FIN"

    return {
        "HCM": hcm_text,
        "FIN": fin_text,
        "OTHER": other_text
    }


def run_controller():
    print("🧠 Starting Legal Eagle Controller...\n")

    # --- Credentials loaded once here ---
    # SAP AI Core credentials are loaded directly by agents via config_loader
    X_BEARER_TOKEN = creds["twitter"]["x_bearer_token"]
    GMAIL_CREDS = creds["gmail"]

    profiles = list_active_profiles()
    if not profiles:
        print("⚠️ No active profiles found. Did you run the migration script?")
        return

    for p in profiles:
        country = p["country_code"]
        lob = p["lob"]
        profile_id = p["id"]
        profile_slug = f"{country}_{lob}"

        # Schedule filter (Asia/Dubai day-of-week)
        try:
            today_name = (datetime.utcnow() + timedelta(hours=4)).strftime("%A")
            conn_sched = get_connection()
            create_schema_if_needed(conn_sched)
            row_sched = conn_sched.execute("SELECT schedule_day FROM profiles WHERE id = ?", (profile_id,)).fetchone()
            conn_sched.close()
            sched = row_sched["schedule_day"] if row_sched else None
            if not sched or sched != today_name:
                print(f"⏭️ Skipping profile {country}/{lob} (schedule_day={sched}, today={today_name})")
                continue
        except Exception as e:
            print(f"⚠️ Schedule check failed, skipping profile {country}/{lob}: {e}")
            continue

        print(f"\n===== ▶️ Running profile {country}/{lob} (id={profile_id}) =====")

        # Load per-profile config from DB
        LANGUAGE_PREFERENCE = load_language(profile_id)
        RSS_FEED_URLS = load_rss_feeds(profile_id)
        TWEET_ACCOUNTS = load_tweet_accounts(profile_id)
        EMAIL_RECEIVERS = load_email_receivers(profile_id)
        glossary_flat = load_glossary(profile_id)
        GLOSSARY = _build_category_glossary_text(glossary_flat, lob)
        PROFILE_DATE_SCOPE = load_profile_date_scope(profile_id)

        # Unified URL sources (auto/force_static/force_dynamic)
        URL_SOURCES = load_url_sources(profile_id)

        # 1. RSS Agent
        rss_items = []
        print("📰 Running RSS Parser Agent...")
        for feed in RSS_FEED_URLS:
            feed_url = feed["url"] if isinstance(feed, dict) else feed
            rss_items.extend(parse_rss_feed(feed_url))
        print(f"✅ Total RSS items collected: {len(rss_items)}")
        # Apply profile-level date filter to RSS
        _rss_days = parse_date_scope(PROFILE_DATE_SCOPE)
        if _rss_days == 0:
            _rss_since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            rss_items = filter_items_by_date(rss_items, since_date=_rss_since)
        elif _rss_days is not None:
            rss_items = filter_items_by_date(rss_items, days=_rss_days)
        # Update last_fetch_date for each RSS feed
        now_ts = datetime.utcnow().isoformat()
        for feed in RSS_FEED_URLS:
            try:
                feed_url = feed["url"] if isinstance(feed, dict) else feed
                update_rss_feed_last_fetch_timestamp(profile_id, feed_url, now_ts)
            except Exception:
                pass

        # 2. Tweet Feed Agent (timeline-only, iterate all accounts; no throttle)
        disable_tweets = os.environ.get("DISABLE_TWEETS")
        # Reset quota date enforcement — disable until date; resume on date inclusive
        reset_str = get_setting_value(profile_id, 'tweets_reset_quota_date')
        block_until = _parse_iso(reset_str)
        today_dubai = (datetime.utcnow() + timedelta(hours=4)).date()
        is_blocked = False
        if block_until:
            try:
                is_blocked = today_dubai < block_until.date()
            except Exception:
                is_blocked = False
        tweet_items = []
        if disable_tweets:
            print("\n🐦 Tweet Agent disabled via DISABLE_TWEETS env. Skipping.")
        elif is_blocked:
            print(f"\n🐦 Tweet Agent disabled until {reset_str}. Skipping.")
        elif TWEET_ACCOUNTS:
            _tw_handles = [a["handle"].lstrip("@") if isinstance(a, dict) else str(a).lstrip("@") for a in TWEET_ACCOUNTS]
            _tw_profile_days = parse_date_scope(PROFILE_DATE_SCOPE)
            tw_days = max(_tw_profile_days, 1) if _tw_profile_days is not None else 7
            print("")
            print(f"Tweet Feed Agent (Search API): {len(_tw_handles)} account(s)")
            _conn_tw2 = get_connection()
            create_schema_if_needed(_conn_tw2)
            tweet_items = search_tweets_multi_account(_tw_handles, X_BEARER_TOKEN, profile_id, _conn_tw2, days=tw_days)
            _conn_tw2.close()
            print(f"Total tweets collected from all accounts: {len(tweet_items)}")
            # Update last_fetch_date for each Twitter account
            for account in TWEET_ACCOUNTS:
                try:
                    handle = account["handle"] if isinstance(account, dict) else str(account)
                    update_tweet_account_last_fetch_timestamp(profile_id, handle, now_ts)
                except Exception:
                    pass
        else:
            print("⚠️ No tweet accounts configured for this profile.")

        # 3. URL Sources Runner (static auto-detect with dynamic fallback)
        print("\n🕵️‍♂️ Running URL Sources Runner (auto/static/dynamic)...")
        url_result = run_unified_sources(URL_SOURCES, profile_slug=profile_slug)
        url_items = url_result.get("items", [])
        url_errors = url_result.get("errors", [])

        print(f"✅ Total monitored site items collected: {len(url_items)}")
        if url_errors:
            print(f"⚠️ {len(url_errors)} errors while scraping:")
            for err in url_errors:
                print(f"   - {err}")

        # 4. Snapshot websites (dynamic path handled by unified runner)
        snap_items = []

        # 5. Combine all items
        all_news_items = rss_items + tweet_items + url_items + snap_items
        print(f"\n📦 Total collected items (pre-filter): {len(all_news_items)}")
        print(f"📅 Filtering: date window applied per source → {len(all_news_items)} items")

        # 5.1. ATTRIBUTE stage (v3.1): stamp publisher / authority from feed config.
        try:
            attribute_items(all_news_items, build_feed_config(RSS_FEED_URLS))
        except Exception as e:
            print(f"⚠️ Attribution stage failed: {e}")

        # 5.2. Relevance filter DELETED in v3.1 (B6) — all in-date items pass through.
        filtered_items = all_news_items
        print(f"🧹 {len(filtered_items)} items passed to pipeline stages")

        # 5.2. Compare AFTER filtering (only relevant items are processed)
        outputs_dir = f"outputs/{profile_slug}"
        compare_result = run_compare_news_agent(filtered_items, outputs_dir=outputs_dir, glossary=GLOSSARY, language=LANGUAGE_PREFERENCE)
        new_items = compare_result.get("new_items", [])
        update_items = compare_result.get("update_items", [])
        print(f"✅ {len(new_items)} new items and {len(update_items)} updates after semantic comparison.")

        # Combine new and updates for the next stage
        final_items = new_items + update_items
        updates_count = sum(1 for it in final_items if it.get("is_update"))
        print(f"ℹ️ Updates in final set: {updates_count}")

        # 6. Grouping (v3.13: legacy news_grouper retired → archived; each item is its own
        #    group for the v1 email path. Structured announcements come from announcement_agent.)
        grouped_summary = [
            {
                "title": it.get("title", ""),
                "summary": it.get("content", it.get("summary", "")),
                "category": it.get("category", ""),
                "titles": [it.get("title", "")],
                "links": [it.get("link", it.get("url", ""))],
                "items": [it],
                "group_size": 1,
                "date_grouped": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                "is_update_section": it.get("is_update", False),
                "delta": it.get("delta", None),
            }
            for it in final_items
        ]

        # 7. Email Composer Agent
        print("📧 Sending summary email...")
        EMAIL_RECEIVERS_WITH_LANG = load_email_receivers_with_lang(profile_id)
        ok = send_email(
            grouped_summary,
            EMAIL_RECEIVERS,
            GMAIL_CREDS,
            LANGUAGE_PREFERENCE,
            country,
            lob
        )
        if ok:
            print(f"✅ Email sent to stakeholders for {country}/{lob}.\n")
        else:
            print(f"❌ Email send failed for {country}/{lob}. See logs above for details.\n")

    print("✅ All active profiles processed.\n")


def run_profile_once(
    profile_id: int,
    force_run: bool = False,
    skip_email: bool = False,
    skip_comparison: bool = False,
    skip_filter: bool = False,
    selected_rss_urls: Optional[List[str]] = None,
    selected_twitter_handles: Optional[List[str]] = None,
    selected_url_sources: Optional[List[str]] = None,
    lookback_override: Optional[str] = None,
    skip_grouping: bool = False,
    should_cancel: Optional[callable] = None,
    dry_run: bool = False,
) -> bool:
    """
    Run the full workflow for a single profile id (even if inactive).
    Used by the Admin UI 'Run' button. Logs progress and sends the email.
    
    Args:
        profile_id: The profile ID to run
        force_run: If True, force FULL fetch mode (ignore delta timestamps)
        skip_email: If True, run pipeline but don't send emails (test mode)
        skip_comparison: If True, bypass duplicate detection (treat all as new)
        skip_filter: If True, bypass LLM relevance check (accept all as relevant)
        selected_rss_urls: Optional list of RSS URLs to fetch (None = all)
        selected_twitter_handles: Optional list of Twitter handles to fetch (None = all)
        selected_url_sources: Optional list of URL sources to fetch (None = all)
    
    Returns True on success, False on error.
    """
    try:
        # Fetch profile row directly from DB
        from configurations.db import get_connection, create_schema_if_needed
        conn = get_connection()
        create_schema_if_needed(conn)
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        conn.close()
        if not row:
            print(f"❌ Profile id {profile_id} not found.")
            return False

        country = row["country_code"]
        lob = row["lob"]
        profile_slug = f"{country}_{lob}"
        
        # Show run mode indicators
        mode_indicators = []
        if force_run:
            mode_indicators.append("FORCE RUN")
        if skip_comparison:
            mode_indicators.append("SKIP COMPARISON")
        if skip_filter:
            mode_indicators.append("SKIP FILTERING")
        if skip_email:
            mode_indicators.append("TEST MODE")
        
        mode_str = f" ({' + '.join(mode_indicators)})" if mode_indicators else ""
        print(f"\n===== ▶️ Running single profile {country}/{lob} (id={profile_id}){mode_str} =====")
        
        if force_run:
            print("🔄 Force run: Fetching full lookback window (ignoring delta)")
        if skip_comparison:
            print("⏭️ Skip comparison: All items will be treated as new")
        if skip_email:
            print("🧪 Test mode: Emails will NOT be sent")

        # Load per-profile config from DB
        LANGUAGE_PREFERENCE = load_language(profile_id)
        RSS_FEED_URLS = load_rss_feeds(profile_id)
        TWEET_ACCOUNTS = load_tweet_accounts(profile_id)
        EMAIL_RECEIVERS = load_email_receivers(profile_id)
        glossary_flat = load_glossary(profile_id)
        GLOSSARY = _build_category_glossary_text(glossary_flat, lob)
        URL_SOURCES = load_url_sources(profile_id)
        PROFILE_DATE_SCOPE = load_profile_date_scope(profile_id)
        if lookback_override:
            print(f"⚡ Lookback override: {lookback_override} (profile default: {PROFILE_DATE_SCOPE})")
            PROFILE_DATE_SCOPE = lookback_override

        # Filter sources based on selections (if provided)
        if selected_rss_urls is not None:
            RSS_FEED_URLS = [feed for feed in RSS_FEED_URLS if feed.get("url") in selected_rss_urls]
            print(f"📰 Filtered RSS feeds: {len(RSS_FEED_URLS)} selected out of {len(load_rss_feeds(profile_id))}")
        
        if selected_twitter_handles is not None:
            TWEET_ACCOUNTS = [acc for acc in TWEET_ACCOUNTS if acc.get("handle") in selected_twitter_handles]
            print(f"🐦 Filtered Twitter accounts: {len(TWEET_ACCOUNTS)} selected out of {len(load_tweet_accounts(profile_id))}")
        
        if selected_url_sources is not None:
            URL_SOURCES = [src for src in URL_SOURCES if src.get("url") in selected_url_sources]
            print(f"🕵️ Filtered URL sources: {len(URL_SOURCES)} selected out of {len(load_url_sources(profile_id))}")

        # Credentials
        # SAP AI Core credentials are loaded directly by agents via config_loader
        X_BEARER_TOKEN = creds["twitter"]["x_bearer_token"]
        GMAIL_CREDS = creds["gmail"]

        # Load lookback window from profile date_scope
        _profile_days = parse_date_scope(PROFILE_DATE_SCOPE)
        print(f"📅 News lookback window: {PROFILE_DATE_SCOPE} → {_profile_days} days")

        # 0) HEALTH CHECK stage (v3.1, F2): parallel pre-run reachability checks.
        # A HARD failure (DB, or Gmail when actually sending) aborts before fetch.
        # AI Core / source warnings are logged and the run proceeds.
        _sel_urls = [f["url"] if isinstance(f, dict) else f for f in RSS_FEED_URLS] + \
                    [s["url"] for s in URL_SOURCES if s.get("url")]
        health = run_health_checks(profile_id, check_email=not skip_email, selected_urls=_sel_urls)
        print(summarize(health))
        _hard = hard_failures(health)
        if _hard:
            print("❌ Aborting run — hard dependency check failed: "
                  + ", ".join(f"{h['name']} ({h['detail']})" for h in _hard))
            return False

        conn = get_connection()
        create_schema_if_needed(conn)

        # 1) RSS Agent (always runs) — F1 per-source anchor + F4 per-source save + F5 force redefine.
        # Each feed's lookback anchors to its own last_fetch_date; new feeds (or force_run)
        # fall back to the profile date_scope window. The anchor is written immediately after
        # each feed succeeds, so a mid-run stop still records completed feeds.
        rss_items = []
        print("📰 Running RSS Parser Agent...")
        _now_iso = datetime.utcnow().isoformat()
        for feed in RSS_FEED_URLS:
            if should_cancel and should_cancel():
                print("⛔ Stop requested — halting before next RSS feed.")
                break
            feed_url = feed["url"] if isinstance(feed, dict) else feed
            last_fetch = feed.get("last_fetch_date") if isinstance(feed, dict) else None
            print(f"   ↳ RSS: {feed_url}: fetching...")
            try:
                feed_items = parse_rss_feed(feed_url)
            except Exception as e:
                print(f"   ⚠️ RSS: {feed_url}: fetch failed ({e}); anchor left intact")
                continue

            # Determine this feed's since-date (F1/F5)
            if _profile_days == 0:
                since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                feed_items = filter_items_by_date(feed_items, since_date=since)
            elif force_run or not last_fetch:
                # Force run OR new feed → bounded by profile date_scope (never unlimited)
                if _profile_days is not None:
                    feed_items = filter_items_by_date(feed_items, days=_profile_days)
            else:
                # DELTA: anchor to this feed's last successful fetch, capped at date_scope
                try:
                    since = datetime.fromisoformat(last_fetch)
                    if _profile_days is not None:
                        since = max(since, datetime.utcnow() - timedelta(days=_profile_days))
                    feed_items = filter_items_by_date(feed_items, since_date=since)
                except Exception:
                    if _profile_days is not None:
                        feed_items = filter_items_by_date(feed_items, days=_profile_days)

            print(f"   ↳ RSS: {feed_url}: {len(feed_items)} items in window")
            rss_items.extend(feed_items)
            # F4: write anchor immediately on this feed's success
            try:
                update_rss_feed_last_fetch_timestamp(profile_id, feed_url, _now_iso)
            except Exception:
                pass
        print(f"✅ Total RSS items collected: {len(rss_items)}")

        # 2) Tweets (with 15-minute rate limit, Search API for all accounts)
        disable_tweets = os.environ.get("DISABLE_TWEETS")
        # Reset quota date enforcement
        reset_str = get_setting_value(profile_id, 'tweets_reset_quota_date')
        block_until = _parse_iso(reset_str)
        today_dubai = (datetime.utcnow() + timedelta(hours=4)).date()
        is_blocked = False
        if block_until:
            try:
                is_blocked = today_dubai < block_until.date()
            except Exception:
                is_blocked = False
        
        tweet_items = []
        if disable_tweets:
            print("\n🐦 Tweet Agent disabled via DISABLE_TWEETS env. Skipping.")
        elif is_blocked:
            print(f"\n🐦 Tweet Agent disabled until {reset_str}. Skipping.")
        elif not TWEET_ACCOUNTS:
            print("⚠️ No tweet accounts configured for this profile.")
        else:
            # Check rate limit
            can_fetch, wait_mins = check_twitter_rate_limit(profile_id, conn)
            
            if not can_fetch:
                print(f"\n⚠️ Twitter Rate Limit Active")
                print(f"   ↳ Last fetch: {15 - wait_mins} minutes ago")
                print(f"   ↳ Please wait: {wait_mins} minutes")
                # Calculate next available time
                last_fetch = get_setting_value(profile_id, 'twitter_last_fetch_time')
                if last_fetch:
                    try:
                        last_dt = datetime.fromisoformat(last_fetch)
                        next_available = last_dt + timedelta(minutes=15)
                        next_available_local = next_available + timedelta(hours=4)  # Dubai time
                        print(f"   ↳ Next available: {next_available_local.strftime('%I:%M %p')}")
                    except Exception:
                        pass
                print("🐦 Skipping Tweet Agent this run")
            else:
                # Use Search API to fetch from ALL accounts in one call
                print("\n🐦 Running Tweet Feed Agent (Search API)...")
                print(f"   ↳ Fetching from {len(TWEET_ACCOUNTS)} accounts: {', '.join('@' + (a['handle'].lstrip('@') if isinstance(a, dict) else str(a).lstrip('@')) for a in TWEET_ACCOUNTS)}")
                
                # Extract just the handles (search_tweets_multi_account expects List[str])
                handles_only = [a['handle'] if isinstance(a, dict) else str(a) for a in TWEET_ACCOUNTS]
                
                tweet_items = search_tweets_multi_account(
                    handles_only, 
                    X_BEARER_TOKEN, 
                    profile_id, 
                    conn, 
                    days=max(_profile_days, 1) if _profile_days is not None else 7
                )
                print(f"✅ Total tweets collected from all accounts: {len(tweet_items)}")

        # 3) URL sources with incremental fetching
        url_items = []
        print("\n🕵️‍♂️ Running URL Sources Runner...")
        
        # Calculate delta window for each URL source (max lookback from profile date_scope)
        url_sources_with_delta = []
        max_lookback_days = parse_date_scope(PROFILE_DATE_SCOPE)
        for source in URL_SOURCES:
            source_copy = source.copy()
            last_fetch = source.get('last_successful_fetch')

            if max_lookback_days == 0:
                # "Today only" — anchor to start of UTC day regardless of last fetch
                start_of_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                source_copy['since_date'] = start_of_today
                print(f"   ↳ {source['url']}: TODAY mode (since {start_of_today.strftime('%Y-%m-%d %H:%M')} UTC)")
            elif PROFILE_DATE_SCOPE in ("force_full", "all") or force_run or not last_fetch:
                # FULL mode: profile set to force full, or forced run, or first run
                source_copy['days'] = max_lookback_days
                if PROFILE_DATE_SCOPE in ("force_full", "all"):
                    mode_reason = "force full (profile)"
                elif force_run:
                    mode_reason = "force run"
                else:
                    mode_reason = "first run"
                print(f"   ↳ {source['url']}: FULL mode ({mode_reason}, max lookback: {max_lookback_days} days)")
            else:
                # DELTA mode: fetch since last successful run
                try:
                    since_date = datetime.fromisoformat(last_fetch)
                    # Apply safety cap only when max_lookback_days is set (not None = unlimited)
                    if max_lookback_days is not None:
                        max_lookback = datetime.utcnow() - timedelta(days=max_lookback_days)
                        since_date = max(since_date, max_lookback)
                    source_copy['since_date'] = since_date
                    print(f"   ↳ {source['url']}: DELTA mode (since {since_date.strftime('%Y-%m-%d %H:%M')})")
                except Exception as e:
                    # Fallback to full window on parse error
                    source_copy['days'] = max_lookback_days
                    print(f"   ↳ {source['url']}: FULL mode (parse error: {e})")

            url_sources_with_delta.append(source_copy)

        # v3.1 (F9): route simulated sources (stored selectors) to the fast config
        # scraper; un-simulated sources fall through to the legacy unified runner.
        simulated = [s for s in url_sources_with_delta
                     if s.get("simulation_status") == "success" and s.get("container_selector")]
        legacy = [s for s in url_sources_with_delta if s not in simulated]
        url_items = []
        url_errors = []
        for s in simulated:
            try:
                got = scrape_url_source_with_config(s)
                got = filter_source_items(got, s)
                print(f"   ↳ {s['url']}: simulated scrape → {len(got)} items in window")
                url_items.extend(got)
            except Exception as e:
                url_errors.append(f"{s['url']}: {e}")

        # Run unified (legacy) sources with delta information
        url_result = run_unified_sources(legacy, profile_slug=profile_slug)
        url_items.extend(url_result.get("items", []))
        url_errors.extend(url_result.get("errors", []))
        
        print(f"✅ Total monitored site items collected: {len(url_items)}")
        if url_errors:
            print(f"⚠️ {len(url_errors)} errors while scraping:")
            for err in url_errors:
                print(f"   - {err}")
        
        # Update last_successful_fetch timestamp for each source after successful fetch
        now_timestamp = datetime.utcnow().isoformat()
        for source in URL_SOURCES:
            try:
                update_url_source_fetch_timestamp(profile_id, source['url'], now_timestamp)
            except Exception as e:
                print(f"   ⚠️ Failed to update timestamp for {source['url']}: {e}")
        
        conn.close()

        # 4) Combine and process
        all_news_items = rss_items + tweet_items + url_items
        print(f"\n📦 Total collected items (pre-filter): {len(all_news_items)}")
        print(f"📅 Filtering: date window applied per source → {len(all_news_items)} items")

        # 4.1) ATTRIBUTE stage (v3.2): stamp publisher / authority_id / authority_status.
        # Configured path: authority comes from feed config (no AI call).
        # Inferred path (v3.2): feeds without a configured authority_id → AI picks best
        # match from profile authorities list (wrapped in ai_cache for harness replay).
        try:
            feed_cfg = build_feed_config(RSS_FEED_URLS)
            url_cfg = build_url_config(URL_SOURCES)
            attr_conn = get_connection()
            attribute_items(all_news_items, feed_cfg, db_conn=attr_conn, profile_id=profile_id, url_config=url_cfg)
            attr_conn.close()
            print(f"🏷️  Attribution stamped ({len(feed_cfg)} configured feed(s), {len(url_cfg)} URL host(s), AI inference enabled)")
        except Exception as e:
            print(f"⚠️ Attribution stage failed: {e}")

        # Relevance filter DELETED in v3.1 (B6): the binary keep/drop filter is
        # replaced by the ranker in v3.2. Until then every fetched, in-date item
        # flows to comparison and on to Review. `skip_filter` is retained in the
        # signature for API compatibility but is now a no-op.
        filtered_items = all_news_items
        filtered_count = 0
        print(f"\n🧹 Relevance filter removed (v3.1) — {len(filtered_items)} items pass to comparison")

        # F4: cancel checkpoint before the expensive comparison/embedding stage.
        if should_cancel and should_cancel():
            print("⛔ Stop requested — halting before comparison. Fetched sources were saved.")
            return False

        # Compare AFTER filtering (only relevant items are processed)
        # CRITICAL: Attach profile_id to all items so compare_news loads the correct baseline
        for item in filtered_items:
            item["profile_id"] = profile_id
        
        outputs_dir = f"outputs/{profile_slug}"
        compare_result = run_compare_news_agent(
            filtered_items,
            outputs_dir=outputs_dir,
            glossary=GLOSSARY,
            language=LANGUAGE_PREFERENCE,
            skip_comparison=skip_comparison,
            skip_persist=dry_run,
        )
        new_items = compare_result.get("new_items", [])
        print(f"✅ {len(new_items)} new item(s) after semantic comparison (duplicates kept in DB, bypassed here).")

        # Only NEW items enter the expensive downstream stages.
        # DUPLICATE items were already persisted by compare_news and remain
        # visible in News Review, but must not consume AI quota.
        final_items = new_items

        # v3.16: ANALYZING stage, re-ordered so every semantic step sees the FULL article.
        # L2 Fetch → Glossary Match → Law Match → Reconcile → Rank. Lifecycle tags come
        # from Compare (exact dedup); Reconcile upgrades cross-language 'new' items by law_id.
        # v3.91 (Task 4B): only NEW items enter this block; DUPLICATE items were already
        # persisted by compare_news and remain visible in News Review.
        if not new_items:
            print(f"ℹ️  All {len(filtered_items)} collected item(s) are duplicate — skipping analysis stages.")
        else:
            try:
                from agents.glossary_match import match_glossary, save_topic_labels, flag_glossary_gaps
                from agents.law_ref_matcher import match_law_refs, save_law_matches
                from agents.news_ranker import rank_items
                # Reads only (glossary/law terms + ranking signals/grounding); mutate items in memory.
                an_conn = get_connection()
                # v3.13/v3.16: L2 Deep Fetch — MANDATORY, now runs FIRST (before Glossary/Law/Rank)
                # so all downstream stages work on the full-article summary, not the headline.
                # Grounded with the profile's registered laws for consistent law extraction.
                print(f"🌐 L2 Fetch: {len(new_items)} item(s) — article-grounded call (summary + laws + refs + evidence + authority)…")
                from agents.l2_fetcher import run_l2_fetch
                _law_rows = an_conn.execute(
                    "SELECT name_en, name_native, law_number FROM law_refs WHERE profile_id=?",
                    (profile_id,),
                ).fetchall()
                _known_laws = [
                    (f"{r['name_en']} (No. {r['law_number']})" if r["law_number"] else r["name_en"])
                    for r in _law_rows
                ]
                _known_authorities = [r["name"] for r in an_conn.execute(
                    "SELECT name FROM authorities WHERE profile_id=? ORDER BY name", (profile_id,)
                ).fetchall()]
                run_l2_fetch(new_items, known_laws=_known_laws, known_authorities=_known_authorities)
                # Persist the new structured L2 fields (references / impact evidence / primary_authority).
                if not dry_run:
                    from configurations.db import update_news_fields as _upd
                    for _it in new_items:
                        _upd(an_conn, _it, {
                            "law_references_json": _it.get("law_references_json"),
                            "impact_evidence_json": _it.get("impact_evidence_json"),
                            "primary_authority": _it.get("primary_authority"),
                        }, profile_id)
                    an_conn.commit()
                # v3.26: resolve the responsible authority — map L2's primary_authority (AI subject-owner)
                # to a registered authority. Publisher stays source-derived; Law Match never sets authority.
                try:
                    from agents.authority_attributor import resolve_primary_authority
                    resolve_primary_authority(new_items, an_conn, profile_id)
                except Exception as e:
                    print(f"⚠️ Authority resolution skipped: {type(e).__name__}: {e}")
                print(f"🔖 Glossary Match: {len(new_items)} item(s)…")
                match_glossary(new_items, an_conn, profile_id)  # now sees l2_summary
                print(f"⚖ Law Match: {len(new_items)} item(s)…")
                match_law_refs(new_items, an_conn, profile_id)
                # Reconcile: cross-language dedup keyed on law_id (act_ref fallback), post-Law-Match.
                print(f"↺ Reconcile: {len(new_items)} item(s)…")
                from agents.compare_news import reconcile_by_act_ref
                reconcile_by_act_ref(new_items, an_conn, profile_id)
                # v3.17: RCM Match — per-item proposed RCM title (announcement_agent pipeline entry),
                # matched against cached RCM reference titles. All items in new_items are non-duplicate.
                try:
                    from agents.announcement_agent import match_rcm_titles
                    if new_items:
                        print("🏷️ RCM Match: proposing RCM titles + tracked/net-new…")
                        match_rcm_titles(an_conn, profile_id, new_items)
                except Exception as e:
                    print(f"⚠️ RCM Match skipped: {type(e).__name__}: {e}")
                # v3.18: Impact gate — relevance + change assessment (+ effective_date) over
                # the L2 summary, grounded by the per-profile rubric.
                try:
                    from agents.impact_gate import assess_impact
                    if new_items:
                        print("🎯 Impact: assessing operational impact + change signals…")
                        assess_impact(new_items, an_conn, profile_id)
                except Exception as e:
                    print(f"⚠️ Impact gate skipped: {type(e).__name__}: {e}")
                # v3.19: Timing — deterministic timing_class + timing_signal (0-2) from
                # effective_date + law status. Feeds the Rank gate. No AI call.
                try:
                    from agents.timing import apply_timing
                    if new_items:
                        print("🕒 Timing: classifying effective dates…")
                        apply_timing(new_items, an_conn, profile_id)
                except Exception as e:
                    print(f"⚠️ Timing skipped: {type(e).__name__}: {e}")
                print("📊 Rank: deterministic signal-fusion (significance 1–5)…")
                rank_items(new_items, profile_id, an_conn)      # sees topic_label + L2 + law
                an_conn.close()
                if not dry_run:
                    # Persist rank fields + effective_date (upsert on source_id/url/hash_signature).
                    from configurations.config_loader import add_news_item as _add_item
                    from agents.compare_news import _build_item_record
                    for _it in new_items:
                        try:
                            _rec = _build_item_record(_it)
                            _add_item(_it.get("profile_id") or profile_id, _rec)
                        except Exception:
                            pass
                    # Persist topic_label + law matches, then flag glossary gaps.
                    w_conn = get_connection()
                    save_topic_labels(new_items, w_conn, profile_id)
                    save_law_matches(new_items, w_conn, profile_id)
                    flag_glossary_gaps(new_items, w_conn, profile_id)
                    w_conn.close()
                ranked = sum(1 for i in new_items if (i.get("significance_rank") or 0) > 0)
                tagged = sum(1 for i in new_items if i.get("topic_label") and i["topic_label"] != '["General"]')
                gaps = sum(1 for i in new_items if i.get("glossary_gap"))
                print(f"📊 Rank stage complete — {tagged}/{len(new_items)} glossary-matched · {ranked}/{len(new_items)} ranked > 0")
                if gaps:
                    print(f"⚠️  Glossary gap check — {gaps}/{len(new_items)} rank≥3 item(s) had NO glossary match (candidates to add)")
                else:
                    print(f"✅ Glossary gap check — 0 gaps (all rank≥3 items matched a glossary term)")
            except Exception as e:
                from agents.l2_fetcher import L2FetchError
                if isinstance(e, L2FetchError):
                    # L2 is mandatory — do not swallow. Abort the run loudly.
                    print(f"❌ L2 Fetch failed (run aborted): {e}")
                    raise
                print(f"⚠️ Analyzing stage failed: {e}")


        # v3.3: EMAIL RANK GATE — set email_eligible=1 for items with rank >= threshold.
        # Only NEW items are in scope; DUPLICATE items are never email-eligible.
        try:
            email_threshold = int(get_setting_value(profile_id, "email_rank_threshold", "3") or 3)
            gate_conn = get_connection()
            for _it in new_items:
                _rank = int(_it.get("significance_rank") or 0)
                _tier = (_it.get("rank_tier") or "").lower()
                _eligible = 1 if (_rank >= email_threshold and _tier != "duplicate") else 0
                _it["email_eligible"] = _eligible
                # Update by source_id / url / hash_signature — items may not have DB id in memory
                _src_type = _it.get("source_type", "RSS")
                _src_id   = _it.get("source_id") or _it.get("guid") or _it.get("tweet_id")
                _url      = _it.get("url") or _it.get("link")
                _hash     = _it.get("hash_signature")
                if _src_id:
                    gate_conn.execute(
                        "UPDATE news_items SET email_eligible=? WHERE profile_id=? AND source_type=? AND source_id=?",
                        (_eligible, profile_id, _src_type, _src_id),
                    )
                elif _url:
                    gate_conn.execute(
                        "UPDATE news_items SET email_eligible=? WHERE profile_id=? AND source_type=? AND url=?",
                        (_eligible, profile_id, _src_type, _url),
                    )
                elif _hash:
                    gate_conn.execute(
                        "UPDATE news_items SET email_eligible=? WHERE profile_id=? AND source_type=? AND hash_signature=?",
                        (_eligible, profile_id, _src_type, _hash),
                    )
            gate_conn.commit()
            gate_conn.close()
            eligible_count = sum(1 for i in new_items if i.get("email_eligible"))
            print(f"✉️  Email gate complete — {eligible_count}/{len(new_items)} new item(s) email-eligible (rank ≥ {email_threshold})")
        except Exception as e:
            print(f"⚠️ Email gate failed: {e}")

        # v3.13: legacy semantic grouper (news_grouper) retired → archived. The v1 preview/send
        # path below now treats each item as its own group; real Topic→Announcement→Sources
        # structure is built by announcement_agent into news_announcements (Announcement tab).
        grouped_summary = [
            {
                "title": it.get("title", ""),
                "summary": it.get("content", it.get("summary", "")),
                "category": it.get("category", ""),
                "titles": [it.get("title", "")],
                "links": [it.get("link", it.get("url", ""))],
                "items": [it],
                "group_size": 1,
                "date_grouped": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                "is_update_section": it.get("is_update", False),
                "delta": it.get("delta", None),
            }
            for it in final_items
        ]

        # Monitor Updates (Law-to-Specification email integration)
        monitor_updates_data = None
        monitor_enabled = get_setting_value(profile_id, 'monitor_updates_enabled', 'false')
        
        if monitor_enabled == 'true' and EMAIL_RECEIVERS:
            print("\n🔍 Fetching Monitor Updates from email inbox...")
            try:
                # Pass all email receivers (any of them can forward monitor emails)
                print(f"   ↳ Checking emails from: {', '.join(EMAIL_RECEIVERS)}")
                
                conn_monitor = get_connection()
                create_schema_if_needed(conn_monitor)
                
                monitor_updates = fetch_monitor_updates(
                    profile_id,
                    EMAIL_RECEIVERS,  # Pass all receivers, not just first
                    GMAIL_CREDS['email_sender'],
                    GMAIL_CREDS['app_password'],
                    conn_monitor
                )
                
                conn_monitor.close()
                
                if monitor_updates:
                    monitor_updates_data = format_monitor_updates_for_email(monitor_updates)
                    print(f"✅ Found {len(monitor_updates)} monitor update email(s)")
                    print(f"   ↳ Total changes: {monitor_updates_data['count'] if monitor_updates_data else 0}")
                else:
                    print("ℹ️ No new monitor updates found")
            except Exception as e:
                print(f"⚠️ Error fetching monitor updates: {e}")
                monitor_updates_data = None
        elif monitor_enabled == 'true' and not EMAIL_RECEIVERS:
            print("\n⚠️ Monitor updates enabled but no email receivers configured")

        # Email (or save preview in test mode)
        if skip_email:
            print("\n📧 Email preview generated (sending is handled by the digest step, not the pipeline).")
            # Save email preview to file
            import json
            preview_path = f"outputs/{profile_slug}/email_preview.html"
            os.makedirs(f"outputs/{profile_slug}", exist_ok=True)
            
            # Generate email HTML (without sending)
            from agents.email_sender import generate_email_html
            email_html = generate_email_html(
                grouped_summary,
                LANGUAGE_PREFERENCE,
                country,
                lob,
                monitor_updates=monitor_updates_data
            )
            
            with open(preview_path, 'w', encoding='utf-8') as f:
                f.write(email_html)
            
            print(f"📁 Email preview saved to: {preview_path}")
            print(f"👀 Open file to review before sending")
            print(f"ℹ️  No email sent from the pipeline (the digest step handles sending).\n")
            return True
        else:
            print("\n📧 Sending summary email...")
            ok = send_email(
                grouped_summary,
                EMAIL_RECEIVERS,
                GMAIL_CREDS,
                LANGUAGE_PREFERENCE,
                country,
                lob,
                monitor_updates=monitor_updates_data
            )
            if ok:
                print(f"✅ Email sent to stakeholders for {country}/{lob}.\n")
                return True
            else:
                print(f"❌ Email send failed for {country}/{lob}. See logs above for details.\n")
                return False
    except Exception as e:
        print(f"❌ Exception during single profile run: {e}")
        return False


if __name__ == "__main__":
    run_controller()
