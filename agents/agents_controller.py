from datetime import datetime, timedelta
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
    update_url_source_fetch_timestamp,
)
print("✅ Config and creds imported")
from configurations.db import get_connection, create_schema_if_needed, insert_filtered_news

from agents.rss_parser import parse_rss_feed
from agents.tweet_feed import search_tweets_multi_account, check_twitter_rate_limit
from agents.url_sources_runner import run_unified_sources
from agents.compare_news import run_compare_news_agent
from agents.news_filter import get_relevant_news
from agents.news_grouper import group_and_summarize_news
from agents.email_sender import send_email
from agents.date_filter import filter_items_by_date
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

        # Unified URL sources (auto/force_static/force_dynamic)
        URL_SOURCES = load_url_sources(profile_id)

        # 1. RSS Agent
        rss_items = []
        print("📰 Running RSS Parser Agent...")
        for url in RSS_FEED_URLS:
            items = parse_rss_feed(url)
            rss_items.extend(items)
        print(f"✅ Total RSS items collected: {len(rss_items)}")

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
            print("\n🐦 Running Tweet Feed Agent...")
            for account_name in TWEET_ACCOUNTS:
                print(f"   ↳ @{account_name}")
                items = fetch_recent_tweets(account_name, X_BEARER_TOKEN, profile_id)
                if isinstance(items, dict) and items.get("error"):
                    print(f"   ❌ Tweet fetch failed for @{account_name}: {items}")
                    continue
                tweet_items.extend(items)
            print(f"✅ Total tweets collected across {len(TWEET_ACCOUNTS)} accounts: {len(tweet_items)}")
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

        # 5.1. Filter FIRST (optimization: reduces items before expensive comparison)
        # Load high-score baseline for "second chance" rescue in filter
        high_score_baseline = get_reviewed_baseline(profile_id, min_score=4)
        print(f"\n🧹 Filtering for relevance (before comparison)... (high-score baseline: {len(high_score_baseline)} items)")
        filter_result = get_relevant_news(
            all_news_items, "", GLOSSARY, LANGUAGE_PREFERENCE, lob,
            high_score_baseline=high_score_baseline
        )
        filtered_items = filter_result.get("items", [])
        filter_errors = filter_result.get("errors", [])
        print(f"✅ Relevant items after filtering: {len(filtered_items)}")
        if filter_errors:
            print(f"⚠️ {len(filter_errors)} filtering errors:")
            for err in filter_errors:
                print(f"   - {err}")

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

        # 6. News Grouper Agent
        print("\n🧠 Grouping similar news items...")
        grouped_summary = group_and_summarize_news(final_items, "", LANGUAGE_PREFERENCE)
        print(f"✅ Grouped summary ready with {len(grouped_summary)} entries.")

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


def run_profile_once(profile_id: int, force_run: bool = False, skip_email: bool = False, skip_comparison: bool = False) -> bool:
    """
    Run the full workflow for a single profile id (even if inactive).
    Used by the Admin UI 'Run' button. Logs progress and sends the email.
    
    Args:
        profile_id: The profile ID to run
        force_run: If True, force FULL fetch mode (ignore delta timestamps)
        skip_email: If True, run pipeline but don't send emails (test mode)
        skip_comparison: If True, bypass duplicate detection (treat all as new)
    
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

        # Credentials
        # SAP AI Core credentials are loaded directly by agents via config_loader
        X_BEARER_TOKEN = creds["twitter"]["x_bearer_token"]
        GMAIL_CREDS = creds["gmail"]

        # Load lookback window (default: 7 days)
        lookback_days = int(get_setting_value(profile_id, 'news_lookback_days', '7'))
        print(f"📅 News lookback window: {lookback_days} days")

        conn = get_connection()
        create_schema_if_needed(conn)
        
        # 1) RSS Agent (always runs)
        rss_items = []
        print("📰 Running RSS Parser Agent...")
        for url in RSS_FEED_URLS:
            rss_items.extend(parse_rss_feed(url))
        print(f"✅ Total RSS items collected: {len(rss_items)}")
        # Apply date filter
        rss_items = filter_items_by_date(rss_items, days=lookback_days)

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
                print(f"   ↳ Fetching from {len(TWEET_ACCOUNTS)} accounts: {', '.join('@' + a.lstrip('@') for a in TWEET_ACCOUNTS)}")
                
                tweet_items = search_tweets_multi_account(
                    TWEET_ACCOUNTS, 
                    X_BEARER_TOKEN, 
                    profile_id, 
                    conn, 
                    days=lookback_days
                )
                print(f"✅ Total tweets collected from all accounts: {len(tweet_items)}")

        # 3) URL sources with incremental fetching
        url_items = []
        print("\n🕵️‍♂️ Running URL Sources Runner...")
        
        # Calculate delta window for each URL source (max lookback acts as safety cap)
        url_sources_with_delta = []
        for source in URL_SOURCES:
            source_copy = source.copy()
            last_fetch = source.get('last_successful_fetch')
            date_scope = source.get('date_scope', 'all')
            max_lookback_days = parse_date_scope(date_scope)
            
            if force_run or not last_fetch:
                # FULL mode: force run OR first run OR after reset
                source_copy['days'] = max_lookback_days
                mode_reason = "force run" if force_run else "first run"
                print(f"   ↳ {source['url']}: FULL mode ({mode_reason}, max lookback: {max_lookback_days} days)")
            else:
                # DELTA mode: fetch since last successful run
                try:
                    since_date = datetime.fromisoformat(last_fetch)
                    # Apply safety cap: don't exceed max lookback window
                    max_lookback = datetime.utcnow() - timedelta(days=max_lookback_days)
                    since_date = max(since_date, max_lookback)
                    source_copy['since_date'] = since_date
                    print(f"   ↳ {source['url']}: DELTA mode (since {since_date.strftime('%Y-%m-%d %H:%M')})")
                except Exception as e:
                    # Fallback to full window on parse error
                    source_copy['days'] = max_lookback_days
                    print(f"   ↳ {source['url']}: FULL mode (parse error: {e})")
            
            url_sources_with_delta.append(source_copy)
        
        # Run unified sources with delta information
        url_result = run_unified_sources(url_sources_with_delta, profile_slug=profile_slug)
        url_items = url_result.get("items", [])
        url_errors = url_result.get("errors", [])
        
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

        # Filter FIRST (optimization: reduces items before expensive comparison)
        # Load high-score baseline for "second chance" rescue in filter
        # Save filtered items to DB for manual review
        high_score_baseline = get_reviewed_baseline(profile_id, min_score=4)
        print(f"\n🧹 Filtering for relevance (before comparison)... (high-score baseline: {len(high_score_baseline)} items)")
        
        def _save_filtered_item(item, reason):
            """Callback to save filtered items to DB for manual review."""
            try:
                conn_f = get_connection()
                create_schema_if_needed(conn_f)
                insert_filtered_news(conn_f, profile_id, item, reason)
                conn_f.close()
            except Exception as e:
                print(f"   ⚠️ Failed to save filtered item: {e}")
        
        filter_result = get_relevant_news(
            all_news_items, "", GLOSSARY, LANGUAGE_PREFERENCE, lob,
            high_score_baseline=high_score_baseline, on_filtered=_save_filtered_item
        )
        filtered_items = filter_result.get("items", [])
        filtered_count = len(filter_result.get("filtered", []))
        print(f"✅ Relevant items after filtering: {len(filtered_items)}")
        print(f"📋 Saved {filtered_count} filtered items for manual review")

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
            skip_comparison=skip_comparison
        )
        new_items = compare_result.get("new_items", [])
        update_items = compare_result.get("update_items", [])
        print(f"✅ {len(new_items)} new items and {len(update_items)} updates after semantic comparison.")

        # Combine new and updates for the next stage
        final_items = new_items + update_items

        # Group
        print("\n🧠 Grouping similar news items...")
        grouped_summary = group_and_summarize_news(final_items, "", LANGUAGE_PREFERENCE)
        print(f"✅ Grouped summary ready with {len(grouped_summary)} entries.")

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
            print("\n📧 [TEST MODE] Generating email preview...")
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
            print(f"⚠️  No emails sent (test mode active)\n")
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
