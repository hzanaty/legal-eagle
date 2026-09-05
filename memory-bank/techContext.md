## Update v3.5 (2026-09-05)

### v3 Pipeline (current)

The v3 line replaced the linear collect→filter→group→send flow with:
**HEALTH CHECK → FETCH (per-source anchor) → ANNOTATE (NEW/UPDATE/REPEATED/DUPLICATE) → RANK (3-tier) → TAG (glossary keywords + gap flag) → TRANSLATE → SAVE → EMAIL FILTER+SEND (decoupled)**.

**AI**: SAP AI Core — gpt-4o (chat/rank/attribution/digest) + text-embedding-3-small (embeddings deployment `dbfeb291d5081b88`; the earlier 404 was a stopped deployment id, not a token). All ranking/digest AI calls are wrapped by `agents/ai_cache.py` for deterministic harness replay.

**New agents (v3):**
- `agents/news_ranker.py` — three-tier ranking (Tier 0 DUPLICATE rank 0 / Tier 1 `ranking_signals` keyword+regex / Tier 2 gpt-4o grounded by `ranking_grounding`)
- `agents/news_tagger.py` — deterministic glossary keyword tagging (`topic_label`) + `flag_glossary_gaps()` (`glossary_gap`)
- `agents/news_translator.py` — post-save translation (extracted from email_sender)
- `agents/health_check.py` — parallel pre-run reachability checks
- `agents/authority_attributor.py` — publisher/authority stamping (configured + AI-inferred paths)
- `agents/source_simulator.py` — zero-config URL source discovery
- `agents/email_composer.py` — Email V2 digest (`generate_digest()`), grouped by Authority → Topic
- **Removed:** `agents/news_filter.py` (binary gate → ranker); `agents/news_grouper.py` (LLM grouping → tagger)

**Database**: SQLite — ~20 tables. v3 additions:
- `news_items` new columns: `significance_rank`, `rank_tier`, `rank_reasoning`, `repetition_tag`, `repetition_count`, `topic_label`, `email_eligible`, `email_sent`, `human_rank_override`, `human_override_reason`, `glossary_gap`, `publisher`, `authority_id`, `authority_status`, `dedup_status`, `published_at`, `canonical_fingerprint`, translation columns (`title_translated`/`content_translated`/`translation_lang`)
- New tables: `ranking_signals`, `ranking_grounding`, `news_announcements` (renamed from `news_aspects` in v3.4), `authorities`, `glossary_terms`
- `url_sources` simulator columns (`simulation_status`, `container_selector`, `field_selectors`, `pagination_*`, `requires_js`, …); `runs.error_step`/`error_message`/`email_status`

**Harness**: `python3 tests/run_harness.py --version v3.5` → 34/34 (4 skipped when embedding/AI cache absent). Test profile = Xanadu (XN/HCM).

---

## Update v2.32 (2026-06-28)

### Current Technical Stack

**Backend**: Python 3.11+ / Flask 3.0+ / SQLite 3 / Gunicorn (BTP)

**AI**: SAP AI Core — gpt-4o (chat/filter/group/translate) + text-embedding-ada-002

**Email Transport**:
- **Current**: Gmail SMTP only — ANS disabled (BTP environment not active)
- **BTP (when rebuilt)**: SAP Alert Notification Service (ANS) — `agents/ans_sender.py`
  - OAuth2 via HTTP Basic auth: `auth=(client_id, client_secret)`, `grant_type=client_credentials`
  - Reads credentials from `VCAP_SERVICES` (Cloud Foundry auto-injection)
  - Re-enable by uncommenting ANS blocks in `ans_sender.py`, `email_sender.py`, `admin/app.py`
- Gmail IMAP: still used for monitor-update inbox reading

**Database**: SQLite — 15 tables including `repo_nodes` + `repo_assets` (v2.30)

**Key Agents**:
- `agents/ans_sender.py` — ANS sender (disabled; stub only — re-enable for BTP)
- `agents/agents_controller.py` — main orchestrator
- `agents/email_sender.py` — Gmail SMTP (ANS-first block disabled)
- `agents/sap_ai_client.py` — SAP AI Core OAuth2 client

**Admin UI**: Flask + Jinja2 + SAP Fiori CSS tokens — port 8080 (configurable via `PORT` env var)

**Deployment**: SAP BTP Cloud Foundry (`cf push`) — manifest.yaml, Procfile, apt.yml, .profile

---

## Update v2.5.0 (2026-02-23)

### v2.5.0 — Turkey Official Gazette Support (2026-02-23)

**New Module**: `agents/resmi_gazete_scraper.py`

**Purpose**: Specialized scraper for Turkey's Official Gazette (Resmi Gazete)

**Key Functions**:
```python
def generate_date_urls(
    base_url: str, 
    start_date: str, 
    days_count: int = 7
) -> List[Tuple[str, str]]
# Generates Resmi Gazete URLs for date range
# Args:
#   base_url: Base gazette URL (e.g., https://www.resmigazete.gov.tr/)
#   start_date: Starting date in DD.MM.YYYY format (e.g., "01.08.2024")
#   days_count: How many days to process going forward (default: 7)
# Returns: List of (url, date_str) tuples
# Format: https://www.resmigazete.gov.tr/DD.MM.YYYY

def extract_gazette_items(
    url: str, 
    html: str, 
    date_str: str
) -> List[Dict]
# Extracts gazette items (title + link) from daily listing page
# Similar to GOSI pattern: extract visible items, not full content
# Filters out navigation elements automatically:
#   - T.C.CUMHURBAŞKANLIĞI, RESMÎ GAZETE
#   - Son Mükerrer, PDF Görüntüle
#   - Önceki Sayı, Sonraki Sayı, etc.
# Returns: List of items with title, link, date, source

def scrape_resmi_gazete(
    base_url: str, 
    start_date: str = None,
    days_count: int = 7
) -> Tuple[List[Dict], List[Dict]]
# Main entry point for Resmi Gazete scraping
# Args:
#   base_url: Base gazette URL
#   start_date: Starting date in DD.MM.YYYY (None = today)
#   days_count: How many days to process (default: 7)
# Returns: (items, errors) tuple
```

**Integration in url_sources_runner.py**:
```python
# Auto-detection (line ~2048)
if resmi_gazete_available and "resmigazete.gov.tr" in u.lower():
    # Determine start date and days count from date_scope
    start_date = src.get("start_date")  # Optional: DD.MM.YYYY format
    days_count = 7
    
    if date_scope == "last_7_days":
        days_count = 7
    elif date_scope == "last_30_days":
        days_count = 30
    
    # Call scraper with start_date (if provided) or None (defaults to today)
    its, errs = scrape_resmi_gazete(
        base_url=u,
        start_date=start_date,  # None means start from today
        days_count=days_count
    )
```

**URL Source Configuration**:
- **url**: `https://www.resmigazete.gov.tr/`
- **mode**: `auto` (scraper auto-detects, mode ignored)
- **date_scope**: `last_7_days` or `last_30_days`
- **start_date**: Optional field (DD.MM.YYYY) for historical scraping
- **sample_link**: Optional (not used by scraper)
- **read_more_label**: Optional (not used by scraper)

**Item Structure**:
```python
{
    "source": "resmigazete.gov.tr",
    "source_type": "URL_Static",
    "title": "7524 Vergi Kanunları ile Bazı Kanunlarda...",  # First 500 chars
    "link": "https://www.resmigazete.gov.tr/eskiler/2024/08/20240802-2.htm",
    "date": "02.08.2024",
    "content": ""  # Empty - user clicks link to read
}
```

**Design Pattern**:
- Similar to GOSI scraper: extract titles + links only
- No PDF parsing (reduces complexity, faster)
- User clicks links to view full documents
- Date-forward iteration (not backwards from today)
- Deduplication by title

**Test Script**: `scripts/test_resmi_gazete_august.py`

---

## Update v2.4.0 (2026-02-19)

### v2.4.0 — Translation & Language Features (2026-02-19)

**Database Schema Changes**:
- `email_receivers` table:
  - Added `translation_lang` column (TEXT, default 'en')
  - Stores preferred translation language per receiver
  - 15 supported languages: en, ar, es, fr, de, zh, ja, ko, pt, ru, tr, hi, it, nl, pl

**New Functions in config_loader.py**:
```python
# Language constant (15 languages)
LANGUAGE_NAMES = {
    "en": "English",
    "ar": "Arabic",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "tr": "Turkish",
    "hi": "Hindi",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish"
}

# Load receivers with translation language
def load_email_receivers_with_lang(profile_id: int) -> List[Dict[str, str]]
# Returns: [{"email": "user@example.com", "translation_lang": "en"}, ...]
```

**New Functions in db.py**:
```python
def upsert_email_receiver_with_lang(
    conn: sqlite3.Connection,
    profile_id: int,
    email: str,
    translation_lang: str = "en"
) -> None
# Inserts or updates email receiver with translation language preference
```

**Email Sender Changes** (email_sender.py):
```python
def translate_grouped_summary(
    grouped_summary: List[Dict],
    target_lang: str,
    api_key: str
) -> List[Dict]
# Translates grouped news summary to target language using GPT-4o-mini

# send_email() now:
# 1. Groups receivers by translation_lang
# 2. Caches translations per language
# 3. Sends one email per language group
# 4. Subject includes profile: "🦅 Legal Eagle Daily Digest — SA/HCM — 2026-02-19"
```

**Admin UI Routes** (admin/app.py):
```python
# Update profile's analysis language
@app.route("/admin/profiles/<int:profile_id>/language/update", methods=["POST"])
def update_profile_language(profile_id: int)

# Update receiver's translation language
@app.route("/admin/profiles/<int:profile_id>/emails/update_language", methods=["POST"])
def update_email_receiver_language(profile_id: int)
```

**Admin UI Templates**:
- `profile.html`:
  - New "Profile Language" section (top of page)
  - Email Receivers table has translation language column with dropdown
  - Both use LANGUAGE_NAMES for language options

**Migration Script**:
- `scripts/migrate_add_translation_lang.py`
- Adds `translation_lang` column to `email_receivers`
- Sets default value 'en' for existing receivers

---

## Previous Updates

### v2.4.0 (2026-01-13 18:49:55Z) [Internal Development]

- Admin UI
  - New Run page (split layout): left pane has Confirm Run and 7-day Run History; right pane streams live logs via SSE and displays historical logs.
  - Cancel button: cooperative termination; finishes current step, sends email with collected results, marks status=Canceled.
  - Dashboard/Profile: Run buttons redirect to the Run page.
  - Bulk delete added for all sections: RSS, URL Sources, Twitter Accounts, Email Receivers, Glossary.
  - Email Receivers simplified: single email add field, per-row delete, and multi-select delete; legacy textarea path hidden.
  - Glossary simplified: terms list with single add + bulk add (one-per-line); controller auto-maps terms to profile LoB.
  - Global Credentials page enhanced: shows openai_api_key, full Gmail OAuth/App fields, and SMTP; values merge from DB + credentials.json (fallbacks).

- Controller & Agents
  - Controller refactored to unified URL sources runner (auto static with dynamic fallback; force_static/force_dynamic modes; optional sample_link).
  - Added run_profile_once(profile_id) for single-run execution used by Admin Run page.
  - stdout tee to DB for live log streaming; finish records status and email result.

- DB Schema & Helpers (SQLite)
  - New tables: runs (history/status/metrics), run_logs (sequenced log lines).
  - Helpers: create_run, start_run, finish_run, append_run_log, list_runs_for_profile, get_run, list_run_logs, set_cancel_requested, is_cancel_requested, prune_old_runs(days=7).
  - Existing tables in use: url_sources, global_credentials, audit_log.

- Retention
  - Automatic cleanup of runs and logs older than 7 days on dashboard access.

- UX Notes
  - Live logs via SSE with auto-scroll.
  - History list shows Status, Started/Finished times; selecting a run shows its logs on the right pane.
  - Simple design (no filters/search) per requirement.
