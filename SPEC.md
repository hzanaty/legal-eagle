# Legal Eagle 3.8 — Technical Specification

**Version:** 3.8 (Analyzing stage = glossary tagging merged into ranking; authority name on Review card; URL textual-date capture; publish-date enforcement; effective-date rank-5)  
**Last Updated:** 2026-09-07

This document provides the technical specification for Legal Eagle, an AI-powered regulatory compliance monitoring system for SAP Localization.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Architecture Overview](#2-architecture-overview)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Agents (Processing Pipeline)](#5-agents-processing-pipeline)
6. [Controller Logic](#6-controller-logic)
7. [Admin UI](#7-admin-ui)
8. [Configuration](#8-configuration)
9. [Data Flow](#9-data-flow)
10. [API Reference](#10-api-reference)
11. [File Structure](#11-file-structure)
12. [Outputs & Artifacts](#12-outputs--artifacts)

---

## 1. Introduction

### 1.1 Purpose

Legal Eagle monitors government sources for legal updates in chosen countries and Lines of Business (LoB), evaluates impacts on SAP localized products, and delivers daily actionable digests to Localization Product Managers (LPMs).

### 1.2 Scope

- **Coverage**: One country + LoB per profile (e.g., `SA/HCM`, `AE/FIN`)
- **Sources**: RSS feeds, Twitter/X accounts, government websites (static and dynamic)
- **Products**: SAP HCM, SAP Payroll, SAP SuccessFactors, SAP S/4HANA localized features
- **Output**: Daily email digest with new/updated legal changes

### 1.3 Key Design Principles

- **Multi-profile**: Each profile is a Country + LoB combination with isolated configuration
- **Four-dimensional item model** (v3): every news item carries four independent dimensions, stored in the DB and shown in the Review UI:
  - **Significance Rank (1–5)** — how legally important, assigned by the three-tier ranking engine (`significance_rank`; DUPLICATEs carry the special value 0, outside the 1–5 scale)
  - **LoB Relevance** — matched glossary terms (or blank → glossary gap alert)
  - **Topic Label** — what the item is about, from glossary keyword tagging (`topic_label`, JSON array; `["General"]` when no term matches)
  - **Repetition Tag** — NEW · UPDATE · REPEATED · DUPLICATE, from cross-run frequency counting (`repetition_tag` / `repetition_count`)
  These dimensions are independent: a rank-4 item with blank LoB Relevance is valid — it means the ranker found a significant item the current glossary cannot explain, which raises a Glossary Gap Alert (v3.5).
- **Ranking as the quality gate** (v3): the old binary relevance filter is gone; noise is Rank 1 and simply not emailed. Email is gated on rank ≥ 3 (configurable per profile).
- **Confirm-not-author human loop** (v3): the human never writes rules. On Challenge → override → confirm, the AI re-evaluates, auto-populates the reason, reflects the understood signal back, and a single confirmation writes both a Tier-2 grounding example (`ranking_grounding`) and a Tier-1 deterministic rule (`ranking_signals`) — so the system gets faster and smarter from every interaction.
- **Environment-based secrets**: No credentials in database or code

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LEGAL EAGLE 3.5 ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         DATA SOURCES                                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  ┌──────────┐   │   │
│  │  │ RSS Feeds   │  │ Twitter/X   │  │   Websites    │  │  Email   │   │   │
│  │  │ rss_parser  │  │ tweet_feed  │  │ url_sources_  │  │  Inbox   │   │   │
│  │  │             │  │             │  │    runner     │  │(Law2Spec)│   │   │
│  │  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘  └────┬─────┘   │   │
│  └─────────┼────────────────┼────────────────┼──────────────────┼─────────┘  │
│            │                │                │                  │            │
│            └────────────────┼────────────────┘                  │            │
│                             ▼                                   │            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                   PROCESSING PIPELINE (v3)                            │   │
│  │                                                                       │   │
│  │  HEALTH CHECK ─▶ FETCH ─▶ ATTRIBUTE ─▶ ANNOTATE ─▶ RANK ─▶ TAG ─▶    │   │
│  │  TRANSLATE ─▶ SAVE ──────────────────────────────────────────────┐   │   │
│  │                                                                   │   │   │
│  │  health_check  authority_     compare_news   news_ranker          │   │   │
│  │  (hard/warn)   attributor     (NEW/UPDATE/    (3-tier: Tier1 kw    │   │   │
│  │                (publisher +   REPEATED/       /regex → Tier2 gpt-4o│   │   │
│  │                authority)     DUPLICATE→rank0) grounded)           │   │   │
│  │                                                                   │   │   │
│  │  news_tagger (topic_label + glossary_gap) · news_translator       │   │   │
│  │                                                                   │   │   │
│  │  ┌──────────────────────┐                                        │   │   │
│  │  │ email_inbox_parser   │ (Monitor Updates from Law-to-Spec)      │   │   │
│  │  │ (Gmail IMAP)         │                                         │   │   │
│  │  └──────────────────────┘                                        │   │   │
│  │                                                                   │   │   │
│  │  EMAIL FILTER + SEND (decoupled — after run marks SUCCESS)        │◀──┘   │   │
│  │  email_composer.generate_digest() → email_sender.send_digest()   │       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                   ▼                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         OUTPUT                                        │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐   │   │
│  │  │  email_sender   │    │  JSON Snapshots │    │  SQLite DB      │   │   │
│  │  │ (Daily Digest)  │    │ (outputs/)      │    │ (Baseline)      │   │   │
│  │  │ + Monitor Alerts│    │                 │    │                 │   │   │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         ADMIN UI (Flask)                              │   │
│  │  • Profile Management    • Source Configuration    • Run Execution   │   │
│  │  • Glossary Management   • Filtered News Review    • Live Logs       │   │
│  │  • Monitor Notifications Toggle                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     CONFIGURATION (SQLite)                            │   │
│  │  • Profiles    • RSS Feeds    • Twitter Accounts    • URL Sources    │   │
│  │  • Glossary    • Email Receivers    • Settings    • Audit Log        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

### 3.1 Backend

- **Language**: Python 3.11+
- **Framework**: Flask 3.0+ (Admin UI)
- **Database**: SQLite 3 (configuration storage)
- **AI/LLM**: SAP AI Core (gpt-4o for chat/ranking/attribution, text-embedding-3-small for embeddings). All chat + embedding calls are wrapped by `agents/ai_cache.py` for deterministic replay in the test harness.

### 3.2 Frontend (Current)

- **Templates**: Jinja2 (server-side rendering)
- **Styling**: Custom CSS with SAP Fiori design tokens
- **JavaScript**: Vanilla JS (minimal, for interactive features)

### 3.3 Data Sources

- **RSS**: feedparser library
- **Twitter/X**: Twitter API v2 (bearer token authentication)
- **Web Scraping**: requests + BeautifulSoup4
- **Email**: imaplib (Gmail IMAP)

### 3.4 Deployment

- **Platform**: SAP Business Technology Platform (Cloud Foundry)
- **Buildpack**: Python buildpack
- **Process**: Gunicorn WSGI server

---

## 4. Database Schema

### 4.1 SQLite Database: `configurations/config.db`

#### Table: `profiles`

Stores country/LoB profile configurations.

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_code TEXT NOT NULL,
    lob TEXT NOT NULL,
    name TEXT,
    active INTEGER DEFAULT 1,
    language TEXT DEFAULT 'en',
    date_scope TEXT DEFAULT 'delta',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(country_code, lob)
);
```

**Columns:**
- `id`: Auto-increment primary key
- `country_code`: ISO country code (e.g., 'SA', 'AE', 'TR')
- `lob`: Line of Business ('HCM' or 'FIN')
- `name`: Optional human-readable name
- `active`: 1 = active, 0 = inactive
- `language`: Analysis language (default: 'en')
- `date_scope`: Default lookback window for all sources ('delta', 'today', 'last_7_days', 'last_30_days')
- `created_at`: ISO 8601 timestamp

#### Table: `rss_feeds`

RSS feed sources per profile.

```sql
CREATE TABLE rss_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    max_lookback_days INTEGER DEFAULT 7,
    last_fetch_date TEXT,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, url)
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `url`: RSS feed URL
- `max_lookback_days`: Legacy — kept in schema, superseded by `profiles.date_scope` (v2.22)
- `last_fetch_date`: ISO 8601 timestamp of last successful fetch

#### Table: `tweet_accounts`

Twitter/X accounts to monitor per profile.

```sql
CREATE TABLE tweet_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    handle TEXT NOT NULL,
    max_lookback_days INTEGER DEFAULT 7,
    last_fetch_date TEXT,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, handle)
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `handle`: Twitter handle (without @)
- `max_lookback_days`: Legacy — kept in schema, superseded by `profiles.date_scope` (v2.22)
- `last_fetch_date`: ISO 8601 timestamp of last successful fetch

#### Table: `url_sources`

Website sources (static and dynamic crawling).

```sql
CREATE TABLE url_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    mode TEXT DEFAULT 'auto',
    date_scope TEXT DEFAULT 'last_7_days',
    sample_link TEXT,
    read_more_label TEXT,
    recursive_crawl INTEGER DEFAULT 0,
    crawl_version TEXT DEFAULT 'v1',
    last_successful_fetch TEXT,
    use_proxy INTEGER DEFAULT 0,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `url`: Website URL
- `mode`: Crawl mode ('auto', 'force_static', 'force_dynamic', 'recursive')
- `date_scope`: Legacy per-source date filter — superseded by `profiles.date_scope` (v2.22); kept for backward compat
- `sample_link`: Optional sample link for pattern detection
- `read_more_label`: Optional "read more" button text
- `recursive_crawl`: 1 = crawl subpages, 0 = single page only
- `crawl_version`: Crawl engine version ('v1' or 'v2')
- `last_successful_fetch`: ISO 8601 timestamp of last successful fetch (used for delta mode)
- `use_proxy`: 1 = use BrightData proxy, 0 = direct connection

**Source Simulator columns (v3.1, F9)** — added via `ALTER TABLE`; populated by `agents/source_simulator.py` and read by the runtime scraper so selectors are discovered once, not per run:
- `simulation_status` (`pending` \| `success` \| `failed`, default `pending`), `simulated_at`
- `container_selector`, `field_selectors` (JSON), `read_more_selector`
- `pagination_type`, `pagination_selector`, `depth_level`, `requires_js`

#### Table: `email_receivers`

Email recipients for daily digest per profile.

```sql
CREATE TABLE email_receivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    translation_lang TEXT DEFAULT 'en',
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, email)
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `email`: Recipient email address
- `translation_lang`: Preferred language for email translation (default: 'en')

#### Table: `glossary`

Custom terms/keywords per profile for filtering.

```sql
CREATE TABLE glossary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, term)
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `term`: Custom term or keyword

#### Table: `settings`

Key-value configuration storage per profile.

```sql
CREATE TABLE settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, key)
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `key`: Setting key (e.g., 'monitor_updates', 'twitter_error_flag')
- `value`: Setting value (JSON string or plain text)

#### Table: `news_items`

Baseline store for accepted items and the four-dimensional v3 item model. The base columns are created by `create_schema_if_needed()`; v3 dimensions are added idempotently via `ALTER TABLE`.

```sql
CREATE TABLE news_items (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,          -- rss | tweet | crawl | snap
    source_id TEXT,                     -- rss: guid, tweet: tweet_id
    url TEXT,
    domain TEXT,
    title TEXT,
    content TEXT,
    published_at TEXT,                  -- ISO timestamp if available
    first_seen_at TEXT NOT NULL,        -- ISO now() on insert
    last_seen_at TEXT NOT NULL,         -- ISO now() updated on repeat/update
    hash_signature TEXT NOT NULL,       -- normalized text hash for quick fuzzy match
    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);
```

**Base columns:** `source_type` (rss/tweet/crawl/snap), `source_id`, `url`, `domain`, `title`, `content`, `published_at` (publication date), `first_seen_at` / `last_seen_at` (fetch bookkeeping), `hash_signature` (exact-dedup fingerprint; a unique index on `(profile_id, source_type, hash_signature)` enforces exact dedup).

**v3 columns added by `ALTER TABLE` (idempotent):**

| Column | Added | Meaning |
|--------|-------|---------|
| `publisher` | v3.1 | Display name of the source (stamped by ATTRIBUTE) |
| `authority_id` | v3.1 | FK to `authorities` |
| `authority_status` | v3.1 | `configured` \| `inferred` (AI, v3.2+) \| `unknown` |
| `dedup_status` | v3.1 | `new` \| `update` \| `duplicate` (set by `compare_news`; duplicates never dropped) |
| `significance_rank` | v3.2 | 0 = duplicate (not evaluated), 1–5 = ranked significance |
| `rank_tier` | v3.2 | `tier1` \| `tier2` \| `duplicate` |
| `rank_reasoning` | v3.2 | One-line rationale from the ranker |
| `repetition_tag` | v3.2 | `new` \| `update` \| `repeated` \| `duplicate` |
| `repetition_count` | v3.2 | Times same entity fingerprint seen across runs |
| `topic_label` | v3.3 | JSON array of matched glossary terms (`["General"]` if none) |
| `email_eligible` | v3.3 | 1 if `significance_rank ≥ threshold` and not duplicate |
| `email_sent` | v3.3 | 1 once included in a sent digest |
| `human_rank_override` | v3.4 | Manual rank set via confirm-challenge (NULL if not overridden) |
| `human_override_reason` | v3.4 | Reason text captured with the override |
| `glossary_gap` | v3.5 | 1 when `significance_rank ≥ 3` AND `topic_label == ["General"]` |

> **Note:** the same v3 attribution/dedup columns (`publisher`, `authority_id`, `authority_status`, `dedup_status`) are also added to `filtered_news`. There is no `canonical_fingerprint` column — exact dedup uses `hash_signature`. Translation is rendered at send time (see `news_translator.py`); translated text is not persisted as `news_items` columns.

#### Table: `filtered_news`

Filtered news items awaiting review.

```sql
CREATE TABLE filtered_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_type TEXT,
    title TEXT NOT NULL,
    link TEXT,
    date TEXT,
    content TEXT,
    score REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `source`: Source name
- `source_type`: Type ('RSS', 'Twitter', 'URL_Static', 'URL_Dynamic')
- `title`: News item title
- `link`: URL to full article
- `date`: Publication date (ISO 8601)
- `content`: Article content or summary
- `score`: Relevance score from AI filter (0.0-1.0)
- `created_at`: Timestamp when filtered

#### Table: `runs`

Execution history for profile runs.

```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    status TEXT DEFAULT 'Pending',
    started_at TEXT,
    finished_at TEXT,
    duration_seconds REAL,
    items_collected INTEGER DEFAULT 0,
    items_filtered INTEGER DEFAULT 0,
    items_new INTEGER DEFAULT 0,
    items_updated INTEGER DEFAULT 0,
    email_sent INTEGER DEFAULT 0,
    error_message TEXT,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `status`: Run status ('Pending', 'Running', 'Completed', 'Failed', 'Canceled')
- `started_at`: ISO 8601 timestamp
- `finished_at`: ISO 8601 timestamp
- `duration_seconds`: Execution duration
- `items_collected`: Total items collected from sources
- `items_filtered`: Items passing AI filter
- `items_new`: New items (not in baseline)
- `items_updated`: Updated items
- `email_sent`: 1 = email sent, 0 = not sent
- `error_message`: Error details if failed

> **v3 columns** (added via `ALTER TABLE`): `origin` (`manual` \| default), `error_step` and `error_message` (F3 — the specific failing pipeline step + human-readable reason, surfaced in the run status UI), and `email_status` (`PENDING → SENDING → SENT / FAILED / SKIPPED`, tracking the decoupled digest stage). The live schema also uses `duration_ms`, `rss_count`, `tweet_count`, `url_count`, `filtered_count`, `grouped_count`, and `cancel_requested`.

#### Table: `run_logs`

Log entries for each run.

```sql
CREATE TABLE run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp TEXT DEFAULT (datetime('now')),
    message TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);
```

**Columns:**
- `id`: Auto-increment primary key
- `run_id`: Foreign key to runs table
- `sequence`: Log line number (for ordering)
- `timestamp`: ISO 8601 timestamp
- `message`: Log message text

#### Table: `global_credentials`

```sql
CREATE TABLE global_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT
);
```

**Columns:**
- `id`: Auto-increment primary key
- `key`: Credential key
- `value`: Credential value (deprecated - use environment variables)

#### Table: `audit_log`

Audit trail for admin UI actions.

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    action TEXT NOT NULL,
    details TEXT
);
```

**Columns:**
- `id`: Auto-increment primary key
- `timestamp`: ISO 8601 timestamp
- `action`: Action performed (e.g., 'create_profile', 'delete_rss_feed')
- `details`: JSON string with action details

#### Table: `authorities` (v3.0)

Legislative bodies per profile; targets of the `authority_id` FK on feeds and news items.

```sql
CREATE TABLE authorities (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT,
    UNIQUE(profile_id, name),
    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);
```

#### Table: `glossary_terms` (+ `glossary_synonyms`, `glossary_patterns`)

Normalized per-profile glossary. `glossary_terms` holds the term (`term`, `lang`, `category`, `product`, `weight`, `notes`); `glossary_synonyms` and `glossary_patterns` hold child synonym strings and regex patterns keyed by `term_id`. The glossary tagger and the Glossary Gap enrichment flow both read/write this table. (Supersedes the flat `glossary` table.)

#### Table: `ranking_signals` (v3.2)

Tier-1 deterministic ranking rules per profile — grown by the confirm-challenge loop.

```sql
CREATE TABLE ranking_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER,
    signal_type TEXT,        -- e.g. gazette_number, human_confirmed
    pattern TEXT,            -- keyword/regex
    min_rank INTEGER,
    confidence REAL,
    created_from TEXT        -- initial_setup | challenge_modal
);
```
> `insert_ranking_signal()` also adds `reason` and `created_at` columns idempotently.

#### Table: `ranking_grounding` (v3.2)

Tier-2 few-shot grounding examples per profile (capped at the 10 most recent when building the prompt).

```sql
CREATE TABLE ranking_grounding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER,
    rank INTEGER,
    summary TEXT,            -- AI-confirmed understanding of the override
    source_item_id INTEGER   -- item that triggered this grounding
);
```
> `insert_ranking_grounding()` also adds `source_label` and `created_at` columns idempotently.

#### Table: `news_announcements` (v3.4 — renamed from `news_aspects`)

One row per AI-detected announcement per run; backs the Topic → Announcement → Sources hierarchy in the Review tab.

```sql
CREATE TABLE news_announcements (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER NOT NULL REFERENCES runs(id),
    topic_label        TEXT NOT NULL,
    title              TEXT NOT NULL,
    announcement_md    TEXT NOT NULL,      -- Law2Spec-aligned markdown, rendered inline
    impact_analysis_md TEXT,               -- populated in v3.6
    first_published    TEXT,
    source_links_json  TEXT NOT NULL,
    item_ids_json      TEXT NOT NULL,      -- backing news_items ids (Level 3 = Sources)
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
```
> A migration renames any legacy `news_aspects` table to `news_announcements` on schema init.

#### Table Count

`create_schema_if_needed()` creates 20 tables (`profiles`, `settings`, `rss_feeds`, `tweet_accounts`, `crawl_urls`, `snap_urls`, `email_receivers`, `glossary_terms`, `glossary_synonyms`, `glossary_patterns`, `news_items`, `url_sources`, `audit_log`, `filtered_news`, `runs`, `run_logs`, `authorities`, `ranking_signals`, `ranking_grounding`, `news_announcements`). A 21st, `monitor_updates_processed`, is created by the monitor-updates migration script.

---

## 5. Agents (Processing Pipeline)

### 5.1 RSS Parser (`agents/rss_parser.py`)

**Purpose**: Fetch and parse RSS feeds.

**Key Functions**:
```python
def parse_rss_feeds(
    feeds: List[Dict],
    max_lookback_days: int = 7
) -> Tuple[List[Dict], List[Dict]]
```

**Input**:
- `feeds`: List of feed dicts with `url`, `max_lookback_days`, `last_fetch_date`
- `max_lookback_days`: Default lookback (overridden by per-feed setting)

**Output**:
- Tuple of (items, errors)
- Items: List of dicts with `source`, `source_type`, `title`, `link`, `date`, `content`

**Date Filtering**:
- Uses per-feed `last_fetch_date` if available
- Falls back to `max_lookback_days` calculation
- Updates `last_fetch_date` after successful fetch

---

### 5.2 Tweet Feed (`agents/tweet_feed.py`)

**Purpose**: Fetch tweets from specified Twitter/X accounts.

**Key Functions**:
```python
def search_tweets_multi_account(
    handles: List[Dict],
    bearer_token: str,
    max_lookback_days: int = 7
) -> Tuple[List[Dict], List[Dict]]
```

**Input**:
- `handles`: List of handle dicts with `handle`, `max_lookback_days`, `last_fetch_date`
- `bearer_token`: Twitter API bearer token
- `max_lookback_days`: Default lookback (overridden by per-handle setting)

**Output**:
- Tuple of (items, errors)
- Items: List of dicts with `source`, `source_type`, `title`, `link`, `date`, `content`

**Error Handling**:
- Pre-flight token validation with `validate_twitter_token()`
- Sets error flag on 402/401/403 responses
- Clears error flag on successful 200 response
- Controller skips Twitter if error flag is set

**Error Flag Functions**:
```python
def set_twitter_error_flag(profile_id: int, error_msg: str) -> None
def get_twitter_error_flag(profile_id: int) -> Optional[Dict]
def clear_twitter_error_flag(profile_id: int) -> None
```

---

### 5.3 URL Sources Runner (`agents/url_sources_runner.py`)

**Purpose**: Crawl and extract content from websites.

**Key Functions**:
```python
def run_url_sources(
    profile_id: int,
    sources: List[Dict],
    date_scope: str = "last_7_days"
) -> Tuple[List[Dict], List[Dict]]
```

**Input**:
- `profile_id`: Profile ID
- `sources`: List of URL source dicts
- `date_scope`: Date filtering ('last_7_days', 'last_30_days', 'all')

**Output**:
- Tuple of (items, errors)
- Items: List of dicts with `source`, `source_type`, `title`, `link`, `date`, `content`

**Modes**:
- `auto`: Try static scraping first, fallback to dynamic (Playwright)
- `force_static`: Static only (faster, no JavaScript)
- `force_dynamic`: Dynamic only (Playwright, JavaScript execution)

**Specialized Scrapers**:
- **GOSI** (gosi.gov.sa): Custom scraper for Saudi Arabia GOSI
- **Resmi Gazete** (resmigazete.gov.tr): Custom scraper for Turkey Official Gazette

**Proxy Support**:
- BrightData proxy integration for blocked sites
- Enabled via `use_proxy` flag on URL source

---

### 5.4 Email Inbox Parser (`agents/email_inbox_parser.py`)

**Purpose**: Monitor Gmail inbox for Law-to-Spec updates.

**Key Functions**:
```python
def check_inbox_for_updates(
    profile_id: int,
    gmail_email: str,
    gmail_password: str,
    days_back: int = 7
) -> List[Dict]
```

**Input**:
- `profile_id`: Profile ID
- `gmail_email`: Gmail address
- `gmail_password`: Gmail app password
- `days_back`: Days to look back for emails

**Output**:
- List of update dicts with `title`, `content`, `date`, `link`

**Filter Logic**:
- Subject contains profile country code
- Sender is from Law-to-Spec team
- Email received within lookback period

---

### 5.5 News Filter (`agents/news_filter.py`) — REMOVED (v3.1)

**Status:** Deleted in v3.1 (bug B6). The binary keep/drop relevance filter was the sole quality gate and let noise through while dropping useful items. It is replaced by the three-tier ranker, where **Rank 1 = Noise** is the quality gate (noise is scored, saved, and simply not emailed — never deleted).

Useful pieces were migrated: publication-date parsing → `agents/text_utils.py`; the age gate → the ANNOTATE step in `compare_news.py` (driven by per-source `last_successful_fetch`, not a hardcoded constant); the cross-language semantic prompt structure → the `news_ranker.py` Tier-2 prompt. The `skip_filter` controller parameter is retained for API compatibility but is now a no-op.

### 5.6 Compare News (`agents/compare_news.py`)

**Purpose**: Deduplicate and detect updates against baseline.

**Key Functions**:
```python
def compare_with_baseline(
    new_items: List[Dict],
    baseline_items: List[Dict]
) -> Dict[str, List[Dict]]
```

**Input**:
- `new_items`: Filtered items from current run
- `baseline_items`: Historical items from database

**Output**:
- Dict with keys: `new`, `updated`, `unchanged`
- `new`: Items not in baseline
- `updated`: Items with content changes
- `unchanged`: Duplicate items

**Comparison Logic**:
- Title-based matching (fuzzy similarity)
- Content hash comparison for updates
- Link matching as fallback

**v3 role — ANNOTATE stage:** `compare_news.py` is the annotator. It classifies every item as **NEW / UPDATE (with delta) / REPEATED (with count) / DUPLICATE** and stamps `dedup_status`. DUPLICATE items are **never dropped** — they are saved with `significance_rank = 0` and shown in a collapsed section of the Review UI (F7). Items whose fingerprint has recurred across runs get `repetition_tag='repeated'` / `repetition_count`, feeding the ranker's REPEATED elevation rules. The age gate migrated here from the deleted `news_filter.py`, anchored to each source's `last_successful_fetch`. The controller invokes it via `run_compare_news_agent(...)`, which returns `new_items` and `update_items`.

---

### 5.7 News Grouper (`agents/news_grouper.py`) — REPLACED by News Tagger (v3.3)

**Status:** Superseded in v3.3. LLM theme-grouping obscured individual items and their ranks, and assigned OTHER/wrong-LoB categories (bugs B3/B4). It is replaced by deterministic glossary tagging (`news_tagger.py`) plus the AI digest composer (`email_composer.py`). The file still exists and `group_and_summarize_news()` is reachable only through the legacy `skip_grouping`/preview path in the controller; it is no longer part of the v3 pipeline. Email organization is now structural (by Topic Label), not editorial.

---

### 5.7a News Ranker (`agents/news_ranker.py`) — NEW (v3.2)

**Purpose**: Assign `significance_rank` (0–5) via a three-tier engine. `rank_items(items, profile_id, db_conn)` mutates each item in place with `significance_rank`, `rank_tier`, `rank_reasoning`.

- **Tier 0 — DUPLICATE passthrough**: items with `dedup_status='duplicate'` are stamped rank 0, `rank_tier='duplicate'`, and skip both tiers.
- **Tier 1 — Deterministic**: keyword/regex rules loaded from `ranking_signals` (ordered by `min_rank` DESC). No AI call; fully explainable. A Tier-1 match at rank ≥ 4 short-circuits and skips Tier 2.
- **Tier 2 — AI**: gpt-4o via `sap_ai_client`, fired when Tier 1 gives rank < 4 or no match. The prompt includes up to 10 `ranking_grounding` summaries as few-shot examples (plus profile bootstrap examples). The call is wrapped in `ai_cache` for offline harness determinism. Falls back to rank 2 on AI-unavailable/parse error.
- **REPEATED elevation** (`_apply_boosts`): REPEATED ×3+ with rank ≥ 2 auto-elevates +1 (cap 5); rank-1 noise is not elevated.
- **Re-rank (F6)**: `rerank_items_for_profile(profile_id, db_conn)` re-runs the ranker over existing DB rows without re-fetching, updating the rank columns.

---

### 5.7b News Tagger (`agents/news_tagger.py`) — NEW (v3.3)

**Purpose**: Deterministic glossary-keyword tagging (no LLM). 

- `tag_items(items, conn, profile_id)`: matches item text against profile glossary terms and sets `topic_label` to a JSON array of matched terms, or `["General"]` when none match.
- `save_topic_labels(items, conn, profile_id)`: persists `topic_label` to `news_items`, resolving each row by id → source_id → url → hash_signature fallback.
- `flag_glossary_gaps(items, conn, profile_id)` (v3.5): runs after `save_topic_labels`; sets `glossary_gap = 1` for items with `significance_rank ≥ 3` AND `topic_label == ["General"]` (a rank-significant item the glossary cannot explain). NULL `topic_label` (never tagged) is not flagged. Same id/source_id/url/hash fallback persistence.

---

### 5.7c News Translator (`agents/news_translator.py`) — NEW (v3)

**Purpose**: Translation extracted out of the email sender (bug B8) into its own step. `translate_grouped_summary(...)` translates title + content for non-English profiles via SAP AI Core, wrapped in `ai_cache`. The email sender renders only; it no longer makes translation calls.

---

### 5.7d Health Check (`agents/health_check.py`) — NEW (v3.1, F2)

**Purpose**: Parallel pre-run reachability checks that complete in seconds, before any fetching. `run_health_checks(profile_id, check_email=True)` returns a list of results; `summarize()` renders them; `hard_failures()` extracts blockers.

- **Hard blocks** (abort the run): DB writability, SAP AI Core, and Gmail SMTP (when actually sending).
- **Warnings** (log + proceed/skip): per-URL and per-RSS HTTP HEAD reachability, Twitter auth (`GET /2/users/me`, zero quota cost).

---

### 5.7e Authority Attributor (`agents/authority_attributor.py`) — NEW (v3.1)

**Purpose**: The ATTRIBUTE stage — stamp `publisher`, `authority_id`, `authority_status` onto items. `build_feed_config(rss_feeds)` maps feeds to publisher/authority; `attribute_items(items, feed_cfg, db_conn, profile_id)` stamps `authority_status='configured'` from feed config (no AI). Feeds with no configured authority take the v3.2 **inferred** path: gpt-4o picks the best match from the profile's authorities list (`authority_status='inferred'`, ✦ spark icon in Review), wrapped in `ai_cache`.

---

### 5.7f Source Simulator (`agents/source_simulator.py`) — NEW (v3.1, F9)

**Purpose**: One-time, AI-assisted auto-discovery of a URL source's structure so the add form is a single URL field. `run_simulation(url, ai_client, max_depth=5)` fetches (static → Playwright fallback), detects repeating containers, maps title/link/date field selectors, detects read-more buttons and pagination, follows nav links a level deeper via LLM when needed, and captures a proof article. Results are saved to the `url_sources` simulator columns (`simulation_status='success'`, `container_selector`, `field_selectors`, etc.) and read at runtime by `scrape_url_source_with_config()`.

---

### 5.8 Email Sender (`agents/email_sender.py`)

**Purpose**: Send daily digest emails with grouped news.

**Key Functions**:
```python
def send_email(
    profile_id: int,
    country_code: str,
    lob: str,
    grouped_summary: List[Dict],
    receivers: List[Dict],
    gmail_email: str,
    gmail_password: str,
    api_key: str,
    profile_language: str = "en"
) -> bool
```

**Input**:
- `profile_id`: Profile ID
- `country_code`: Profile country code
- `lob`: Profile Line of Business
- `grouped_summary`: Grouped news from news_grouper
- `receivers`: List of receiver dicts with `email`, `translation_lang`
- `gmail_email`: Sender Gmail address
- `gmail_password`: Gmail app password
- `api_key`: SAP AI Core API key (for translation)
- `profile_language`: Profile analysis language

**Output**:
- Boolean: True if email sent successfully

**Email Features**:
- **Bilingual**: Single email with profile language + English translation
- **Country-specific styling**: Color-coded by country
- **Language badges**: Visual indicators for each language section
- **Grouped format**: News items organized by theme
- **HTML template**: Responsive design with SAP Fiori styling

**Translation Logic**:
- Groups receivers by `translation_lang`
- Caches translations per language
- Sends one email per language group
- Subject includes profile: "🦅 Legal Eagle Daily Digest — SA/HCM — 2026-04-24"

**v3 role — render + SMTP only:** `send_email()` (the legacy bilingual grouped-summary path) remains for the preview/`skip_grouping` flow, but the v3 pipeline uses **`send_digest(profile_id, run_id, item_ids, db_conn, gmail_creds)`**. `send_digest()` selects email-eligible items (or explicit `item_ids` for manual/Resend), calls `email_composer.generate_digest()` to build the HTML, sends via Gmail SMTP, sets `email_sent = 1` on included items, and updates `runs.email_status` (PENDING → SENDING → SENT / FAILED / SKIPPED). All AI/translation calls were removed from this module (bug B8).

---

### 5.8a Email Composer (`agents/email_composer.py`) — NEW (v3.3)

**Purpose**: Build the V2 AI digest. `generate_digest(items, profile_id, db_conn, run_id, profile_name)` groups items by **Authority → Topic Label**, makes one cached AI call per group to detect distinct announcements (title + 2–4 sentence Law2Spec-aligned summary + first publish date + source links), writes one `news_announcements` row per announcement, and returns SAP-Blue inline-CSS HTML with per-item rank badges. Existing announcements for the run are cleared first (Resend idempotency).

---

### 5.9 SAP AI Client (`agents/sap_ai_client.py`)

**Purpose**: Unified client for SAP AI Core API calls.

**Key Functions**:
```python
def get_chat_completion(
    messages: List[Dict],
    deployment_id: str,
    base_url: str,
    auth_url: str,
    client_id: str,
    client_secret: str,
    temperature: float = 0.7,
    max_tokens: int = 4000
) -> str

def get_embeddings(
    texts: List[str],
    deployment_id: str,
    base_url: str,
    auth_url: str,
    client_id: str,
    client_secret: str
) -> List[List[float]]
```

**Authentication**:
- OAuth2 client credentials flow
- Token caching with expiration handling
- Automatic token refresh

**Error Handling**:
- Retry logic for transient failures
- Detailed error messages
- Rate limiting awareness

---

## 6. Controller Logic

### 6.1 Agents Controller (`agents/agents_controller.py`)

**Purpose**: Orchestrate the entire processing pipeline.

**Key Functions**:
```python
def run_profile_once(
    profile_id: int,
    force_run: bool = False,
    skip_comparison: bool = False,
    skip_email: bool = False,
    skip_filter: bool = False,
    skip_grouping: bool = False,
    selected_rss_urls: Optional[List[str]] = None,
    selected_twitter_handles: Optional[List[str]] = None,
    selected_url_sources: Optional[List[str]] = None,
    lookback_override: Optional[str] = None,
) -> bool
```

**Parameters**:
- `profile_id`: Profile to run
- `force_run`: Force execution even if no new items
- `skip_comparison`: Skip baseline comparison (force all items as new)
- `skip_email`: Skip email sending (dry run)
- `skip_filter`: Skip AI relevance filtering (treat all collected items as relevant)
- `skip_grouping`: Skip AI grouping (each item becomes its own email entry)
- `selected_rss_urls`: Optional list of RSS feed URLs to fetch (None = all)
- `selected_twitter_handles`: Optional list of Twitter handles to fetch (None = all)
- `selected_url_sources`: Optional list of URL sources to crawl (None = all)
- `lookback_override`: Per-run date_scope override ('force_full', 'delta', 'today', 'last_7_days', 'last_30_days')

**Execution Flow (v3 pipeline)**:
1. **Load Configuration**: Profile, sources, receivers, glossary; resolve `date_scope` (+ `lookback_override`)
2. **HEALTH CHECK** (v3.1, F2): parallel reachability checks; hard-fail on DB / AI Core / Gmail aborts before any fetch
3. **FETCH**: RSS, tweets, URL sources — each source anchored to its own `last_successful_fetch` (null → fall back to `date_scope` window); force-fetch treats the anchor as null but stays bounded by `date_scope`; anchor written immediately on each source's success (F1/F4/F5)
4. **ATTRIBUTE** (`authority_attributor.py`): stamp `publisher` / `authority_id` / `authority_status` (configured, else AI-inferred)
5. **ANNOTATE** (`compare_news.py`): classify NEW / UPDATE / REPEATED / DUPLICATE; DUPLICATEs saved (rank 0), never dropped
6. **RANK** (`news_ranker.py`): three-tier engine scores all items 1–5 (duplicates stay 0); rank fields upserted to DB
7. **TAG** (`news_tagger.py`): glossary keyword matching → `topic_label`; `flag_glossary_gaps()` sets `glossary_gap` for rank ≥ 3 items with no match (v3.5)
8. **EMAIL RANK GATE**: `email_eligible = 1` for rank ≥ threshold (default 3) non-duplicate items
9. **TRANSLATE** (`news_translator.py`): non-English profiles, rendered at send time
10. **SAVE**: all four dimensions persisted; items available immediately in Review UI
11. **Finish run** as SUCCESS, then **EMAIL FILTER + SEND (decoupled)**: a follow-on digest thread calls `send_digest()` → `email_composer.generate_digest()` (skipped in test mode; Resend on FAILED)

> The binary relevance filter is gone (v3.1, B6). `skip_filter` is a retained no-op. The legacy `group_and_summarize_news()` runs only in the `skip_grouping`/preview path, not the v3 send path.

**Skip Flags**:
- `skip_filter`: Bypass LLM relevance check — all collected items treated as relevant
- `skip_comparison`: Skip baseline comparison — force all items as new
- `skip_grouping`: Bypass LLM grouping — each item becomes its own email entry
- `skip_email`: Skip email sending — dry run only
- `force_run`: Force execution even if no new items found

**Lookback Modes** (controlled by `profiles.date_scope` or `lookback_override`):
- `delta`: Fetch only items since `last_successful_fetch` (full window on first run)
- `today`: Items from UTC midnight today only
- `last_7_days` / `last_30_days`: Fixed rolling window
- `force_full`: Bypass delta tracking — always fetch full window

**URL Sources Delta Logic**:
- Per source: compare current time with `last_successful_fetch`
- DELTA mode: `since_date = last_successful_fetch` (injected into runner)
- FULL mode: `days = max_lookback_days` (injected into runner)
- Triggers FULL mode when: first run, `force_full` date_scope, `force_run=True`, or `lookback_override='force_full'`

**Source Selection** (v2.14+):
- When selection parameters are `None`, all sources are fetched (default behavior)
- When selection parameters are provided as lists, only those sources are fetched
- Useful for testing single sources or excluding problematic sources

**Cooperative Cancellation**:
- Checks `is_cancel_requested(run_id)` after each step
- Finishes current step gracefully
- Sends email with collected results
- Marks run status as 'Canceled'

---

## 7. Admin UI

### 7.1 Flask Application (`admin/app.py`)

**Server Configuration**:
- **Default Port**: 8080
- **Host**: 0.0.0.0 (accepts connections from any interface)
- **Port Configuration**: Configurable via `PORT` environment variable
  - Example: `PORT=5000 python admin/app.py` runs on port 5000
  - BTP-compatible: Cloud Foundry sets `PORT` automatically
- **Debug Mode**: Enabled when `FLASK_ENV != "production"`
- **Reloader**: Disabled (`use_reloader=False`) to prevent orphan processes
- **Access URL**: `http://localhost:8080/admin` (local development)

**Routes**:

#### Dashboard
- `GET /admin/` - List all profiles with status

#### Profile Management
- `GET /admin/create` - Create new profile form
- `POST /admin/create` - Submit new profile
- `GET /admin/profiles/<id>` - Profile configuration page
- `POST /admin/profiles/<id>/language/update` - Update profile language
- `POST /admin/profiles/<id>/date-scope/update` - Update profile default lookback window (v2.22)
- `POST /admin/profiles/<id>/delete` - Delete profile

#### RSS Feeds
- `POST /admin/profiles/<id>/rss/add` - Add RSS feed
- `POST /admin/profiles/<id>/rss/delete` - Delete RSS feed
- `POST /admin/profiles/<id>/rss/bulk_delete` - Bulk delete RSS feeds

#### Twitter Accounts
- `POST /admin/profiles/<id>/tweets/add` - Add Twitter account
- `POST /admin/profiles/<id>/tweets/delete` - Delete Twitter account
- `POST /admin/profiles/<id>/tweets/bulk_delete` - Bulk delete Twitter accounts
- `POST /admin/profiles/<id>/tweets/clear_error` - Clear Twitter error flag

#### URL Sources
- `POST /admin/profiles/<id>/urls/add` - Add URL source
- `POST /admin/profiles/<id>/urls/delete` - Delete URL source
- `POST /admin/profiles/<id>/urls/bulk_delete` - Bulk delete URL sources

#### Email Receivers
- `POST /admin/profiles/<id>/emails/add` - Add email receiver
- `POST /admin/profiles/<id>/emails/update_language` - Update receiver language
- `POST /admin/profiles/<id>/emails/delete` - Delete email receiver
- `POST /admin/profiles/<id>/emails/bulk_delete` - Bulk delete email receivers

#### Glossary
- `POST /admin/profiles/<id>/glossary/add` - Add glossary term
- `POST /admin/profiles/<id>/glossary/bulk_add` - Bulk add glossary terms
- `POST /admin/profiles/<id>/glossary/delete` - Delete glossary term
- `POST /admin/profiles/<id>/glossary/bulk_delete` - Bulk delete glossary terms

#### Monitor Updates
- `POST /admin/profiles/<id>/monitor/toggle` - Toggle email inbox monitoring

#### Run Execution
- `GET /admin/profiles/<id>/run` - Run status page
- `POST /admin/profiles/<id>/run/start` - Start profile execution
- `POST /admin/profiles/<id>/run/cancel` - Cancel running execution
- `GET /admin/profiles/<id>/run/<run_id>/logs` - Stream execution logs (SSE)

#### Review News
- `GET /admin/profiles/<id>/review` - Review filtered news items
- `POST /admin/profiles/<id>/review/<item_id>/approve` - Approve filtered item
- `POST /admin/profiles/<id>/review/<item_id>/reject` - Reject filtered item
- `POST /admin/profiles/<id>/review/<item_id>/score` - Update relevance score
- `POST /admin/profiles/<id>/review/clear` - Clear all filtered news

#### v3 Pipeline Redesign Routes (verified)
- `POST /admin/run-all` · `GET /admin/run-all/status` · `GET /admin/run-all/stream` — Run All Active (background sequential runner + SSE)
- `POST /admin/profiles/<id>/urls/simulate` · `POST /admin/profiles/<id>/urls/simulate/save` — Source Simulator (⚡) discover + persist (v3.1, F9)
- `POST /admin/profiles/<id>/news/<item_id>/authority` — authority override on inferred items (v3.2)
- `POST /admin/send-email` — send digest for `item_ids` (manual) or `run_id` (Resend) (v3.3)
- `POST /admin/news/<item_id>/challenge` · `POST /admin/news/<item_id>/confirm-challenge` — Challenge modal + confirm (writes `human_rank_override`, `ranking_grounding`, `ranking_signals`) (v3.4)
- `POST /admin/news/<item_id>/rerank` · `POST /admin/profiles/<id>/rerank-all` — Re-rank one / all items (F6)
- `POST /admin/profiles/<id>/glossary/suggest` — AI keyword suggestions (regex fallback) (v3.5)
- `POST /admin/news/<item_id>/add-to-glossary` — add term + re-tag + clear gap flag (v3.5)

#### ANS Email (v2.26+, currently disabled)
- `POST /admin/profiles/<id>/ans/provision` - Re-provision ANS Actions for all receivers — **route disabled; re-enable for BTP deployment**

#### v2.31 Routes
- `GET /admin/preflight` - Pre-run checklist JSON (checks, ready)
- `POST /admin/profiles/<id>/review/translate` - Batch translate review items to English
- `GET /Resources/<path>` - Serve files from project Resources/ directory

#### BTP Config Sync (v2.31)
- `GET /admin/export-config` - Export DB config to JSON
- `POST /admin/import-config` - Import config from JSON (BTP DB seeding)

### 7.2 Templates (`admin/templates/`)

**Current Templates** (Jinja2 + Custom CSS):
- `base.html` - Base template with Fiori styling (CSS variables)
- `dashboard.html` - Profile list and overview
- `create_profile.html` - Create new profile form
- `profile.html` - Profile configuration (Configure tab)
- `run_status.html` - Run execution and logs (Run tab)
- `review_news.html` - Filtered news review (Review tab)

**Design System**:
- SAP Fiori color palette (CSS variables)
- Fiori shell bar pattern
- Object page pattern for profile navigation
- Card-based layout
- Semantic button styles (Emphasized, Accept, Reject, etc.)

### 7.3 Run Options (v2.24)

The Run modal exposes the following per-run controls:

**Lookback (dropdown)** — Override the profile's default lookback window for this run only:
- `(empty)` — Use profile default (no override)
- `force_full` — Force full re-fetch, ignoring `last_successful_fetch` timestamps
- `delta` — Delta since last fetch
- `today` — Today only (UTC midnight anchor)
- `last_7_days` / `last_30_days` — Fixed rolling window

**Skip comparison** — Bypass baseline deduplication; treat all items as new

**Skip filtering** — Bypass LLM relevance check; treat all items as relevant

**Skip grouping** — Bypass LLM clustering; each item becomes its own email entry

**Test mode (skip emails)** — Run full pipeline without sending emails

All checkbox states are persisted per profile in browser localStorage and restored on next page load.

### 7.4 Profile Configuration — Default Lookback Window (v2.22)

The "🗓 Default Lookback Window" card on the profile configuration page sets the `date_scope` for all sources in the profile:

| Option | Value | Behaviour |
|--------|-------|-----------|
| Delta (since last fetch) | `delta` | Full window on first run; incremental since last successful fetch on subsequent runs |
| Today only | `today` | Items from UTC midnight today |
| Last 7 days | `last_7_days` | Rolling 7-day window |
| Last 30 days | `last_30_days` | Rolling 30-day window |

> **Note**: Per-source "Lookback Days" columns and fields were removed from RSS Feeds, Twitter Accounts, and URL Sources in v2.22. Use the profile-level Default Lookback Window instead.

### 7.5 Run Log Visualization (v2.26)

`run_status.html` replaces the raw terminal log with a two-panel layout:

**Left panel — Stage checklist** (7 pipeline stages):

| Stage | Icon | Trigger pattern |
|-------|------|-----------------|
| Starting | 🚀 | `Running single profile` |
| Collecting | 📰 | `Running RSS Parser Agent \| Tweet Feed Agent \| URL Sources Runner` |
| Filtering | 🧹 | `Filtering for relevance \| Skip filtering enabled` |
| Comparing | 🔍 | `Relevant items after filtering` |
| Grouping | 🧠 | `Grouping similar news items \| Skipping grouping` |
| Sending | 📧 | `Sending summary email \| Generating email preview` |
| Done | ✅ | `event: done` (SSE terminal event) |

Each stage shows a status icon (idle `·` / active `⟳` / done `✓` / skipped `⏭` / failed `✗`) and a summary extracted from the log (e.g. `55 collected`, `4 relevant`, `0 new · 0 updated`).

**Collecting sub-items** — the Collecting stage expands to show individual source rows:

- **RSS feeds**: one row per feed URL, detected from `↳ RSS: {url}: fetching...` / `↳ RSS: {url}: N items`
- **Twitter accounts**: one row per `@handle`, detected from `↳ Fetching from N accounts: @h1, @h2, …`
- **URL sources**: one row per URL, detected from `↳ {url}: TODAY|FULL|DELTA mode` (pre-register) then `[Source N/M] url={url}` (activate)

Each sub-item shows its own state icon and item count when complete. Clicking any sub-item or stage switches the right panel to that source's log lines.

**Right panel — Log lines**: filtered to the selected stage or sub-source; auto-follows the active source during a live run.

**Implementation**: entirely in `admin/templates/run_status.html` (inline CSS + JS). Log lines stream via SSE from `/admin/profiles/<id>/run/<run_id>/logs`. Each line is routed to the owning stage bucket and optionally to a sub-source slice.

### 7.6 ANS Email Integration (v2.26, currently disabled)

> **Status (v2.32):** ANS is disabled — BTP environment not active. Gmail SMTP is the sole email transport. ANS code is preserved (commented out) for re-activation on next BTP deployment. The "Re-provision all" button is visible in the admin UI but dimmed/non-clickable.

On SAP BTP, Gmail App Passwords are blocked by Google from cloud IPs. Legal Eagle uses **SAP BTP Alert Notification Service (ANS)** as the primary email transport on BTP, with Gmail SMTP for local/non-BTP operation.

**File**: `agents/ans_sender.py` (implementation commented out; stub returns `None`)

**Detection**: `get_ans_sender()` reads `VCAP_SERVICES` for an ANS binding. Returns `None` when absent or disabled (current state → Gmail SMTP used directly).

**Provisioning** (idempotent per recipient):
1. Creates one ANS **Action** (SMTP endpoint) per email address
2. Creates one ANS **Condition** (filter matching the profile slug label)
3. Creates one ANS **Subscription** linking Action ↔ Condition

**Sending**: `send_digest_via_ans(profile_slug, subject, body, emails)` fires one resource event per recipient per digest run.

**Current send path** in `agents/email_sender.py` (ANS block disabled):
```
Gmail SMTP directly (ANS-first block commented out)
```

**OAuth2 Token Request** (v2.32 fix — preserved in comments):
```python
resp = requests.post(
    self._oauth_url,
    auth=(self._client_id, self._client_secret),  # HTTP Basic auth
    data={"grant_type": "client_credentials"},
    timeout=30,
)
```
Credentials go in the `Authorization: Basic` header (not the request body) — required by SAP XSUAA.

**ANS Provisioning UI:**
- "Re-provision all" button visible on profile page, dimmed and non-clickable (disabled) when ANS unavailable
- Route `POST /admin/profiles/<id>/ans/provision` commented out; auto-provision on add/save email also disabled
- To re-enable: uncomment `agents/ans_sender.py`, `admin/app.py` ANS blocks, `agents/email_sender.py` ANS-first block

### 7.8 v2.31 Enhancements

**URL Source Rename:**
- Edit form exposes all fields including URL identity rename
- `new_url` form field: if different from original `url`, old row is deleted and new row inserted
- Preserves all other fields (mode, sample_link, read_more_label, etc.)

**Auto-translate in Review:**
- Non-English profiles auto-translate all visible news items to English on page load
- Uses SAP AI Core (gpt-4o) via `POST /admin/profiles/<id>/review/translate`
- Translation shown inline below original text
- Response format: `{"translations": {"<id>": {"title_en": "...", "content_en": "..."}}}`

**Pre-run Preflight Checklist:**
- `GET /admin/preflight?profile_id=<id>` returns JSON `{checks: [...], ready: bool}`
- Checks: at least one source configured, email receiver configured, AI Core credentials set, Twitter token valid (if Twitter accounts exist)
- Start Run button is disabled in UI until all checks pass

**Lifecycle Bar Colors:**
- Completed stages: green
- Current stage: blue
- Future stages: dark grey

**Resources/ Flask Route:**
- `GET /Resources/<path>` serves any file from the project's `Resources/` directory
- Enables MindMap HTML files and other static assets to be served directly

**BTP Config Sync:**
- `GET /admin/export-config` — exports full DB config to JSON (for BTP seeding)
- `POST /admin/import-config` — imports config from JSON (idempotent, used on BTP cold start)

### 7.9 UI Enhancements History

#### v2.16 — Table Consistency
- Added "Lookback Days", "Sample Link", "Read More Label" columns to tables (later superseded by v2.22)
- Enabled `TEMPLATES_AUTO_RELOAD` for faster template iteration during development

#### v2.17 — Review UI Simplification
- Removed redundant tab buttons; stat cards are now clickable for navigation
- Removed "Clear Historical News" button from Run page (use Review page instead)

#### v2.18 — Twitter Status Compact Design
- Twitter status card hidden in normal operation; error-only banner shown when API has issues

#### v2.19 — Source Selection Fix
- Empty source selection (all unchecked) correctly runs 0 sources instead of all sources

#### v2.20 — Skip Filtering + Run Options Persistence
- Added "Skip filtering" checkbox to Run Options
- All run option states persisted in localStorage per profile

### 7.10 v3 Review UI (Pipeline Redesign)

The Review tab (`admin/templates/review_news.html`) is the human surface for the four-dimensional item model:

- **Rank badges**: colour-coded 0–5 circles (0 = grey DUPLICATE, 3 = yellow, 4 = orange, 5 = red). DUPLICATE items sit in a collapsed section — never dropped.
- **Attribution**: Channel / Publisher / Authority columns; ✦ spark icon on AI-inferred authority items with an inline authority-override dropdown.
- **Challenge + Re-rank** (v3.4/F6): a Challenge button re-evaluates an item with full grounding context and auto-populates an override reason; confirm writes the override plus a Tier-2 grounding example and a Tier-1 rule simultaneously. Re-rank re-runs the ranker on existing items (no re-fetch), per-item or profile-wide.
- **Topic → Announcement → Sources hierarchy** (v3.4): Level 1 = Topic (`topic_label`), Level 2 = Announcement (`news_announcements`), Level 3 = Sources (backing `news_items` via `item_ids_json`). Clicking an Announcement renders `announcement_md` inline as markdown.
- **Glossary Gap Alert** (v3.5): a `⚠ N glossary gaps` toolbar strip with a "Show only gaps" filter, and a `⚠ Gap — no LoB match` badge per flagged card (driven by `item.is_gap`). An inline **+ Add to Glossary** panel AI-suggests keywords; confirming a term + LoB saves the term, re-tags the item, and clears the gap flag with no navigation away.
- **Email controls** (v3.3): All / Unsent-only filter chip, ✉ Unsent / ✓ Sent pill per item, and a "✉ Send Email (N)" toolbar button. Publish dates surface on every card.

### 7.11 Run All Active (v3.0 UI / v3.1 backend)

Dashboard one-click multi-profile runner. `POST /admin/run-all` spawns a background thread that runs each active profile sequentially (skip-on-failure), pushing live status pills to profile rows via `GET /admin/run-all/stream` (SSE); `GET /admin/run-all/status` supports reconnect recovery after reload.

### 7.12 Source Simulator (v3.1, F9)

The URL-source add form is a single URL field. A saved source shows a `⏳ Pending` badge and a **⚡ Simulate** button; clicking it calls `POST /admin/profiles/<id>/urls/simulate` (SSE progress through fetch → container detect → depth loop → field map → button/pagination detect → sample capture) and `.../simulate/save` persists discovered selectors to the `url_sources` simulator columns. The runtime scraper then reads stored selectors instead of re-discovering.

---

## 8. Configuration

> **v3 lookback change:** the unbounded `date_scope` values `all` / `full` / `unlimited` were removed. `parse_date_scope()` resolves only `delta` / `today` / `last_7_days` / `last_30_days`, and **force-fetch is bounded by `date_scope`** — it treats each source's `last_successful_fetch` as null for the run but never fetches beyond the profile window. (Legacy `all`/`force_full` rows are still tolerated for backward compatibility.)

### 8.1 Environment Variables

All sensitive credentials stored in environment variables (not in database).

**Required Variables**:
```bash
# SAP AI Core
LEGAL_EAGLE_SAP_AICORE_BASE_URL=https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com
LEGAL_EAGLE_SAP_AICORE_AUTH_URL=https://auth.ai.prod.eu-central-1.aws.ml.hana.ondemand.com/oauth/token
LEGAL_EAGLE_SAP_AICORE_CLIENT_ID=<client-id>
LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET=<client-secret>
LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID=<deployment-id>
LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID=<deployment-id>

# Gmail
LEGAL_EAGLE_GMAIL_EMAIL=<gmail-address>
LEGAL_EAGLE_GMAIL_APP_PASSWORD=<app-password>

# Twitter/X
LEGAL_EAGLE_TWITTER_BEARER_TOKEN=<bearer-token>

# BrightData Proxy (Optional)
LEGAL_EAGLE_BRIGHTDATA_HOST=<proxy-host>
LEGAL_EAGLE_BRIGHTDATA_PORT=<proxy-port>
LEGAL_EAGLE_BRIGHTDATA_USERNAME=<username>
LEGAL_EAGLE_BRIGHTDATA_PASSWORD=<password>

# Admin UI
LEGAL_EAGLE_ADMIN_SECRET=<secret-key>
```

### 8.2 Configuration Loader (`configurations/config_loader.py`)

**Purpose**: Centralized configuration access layer.

**Key Functions**:
```python
# Profile Management
def list_active_profiles() -> List[Dict]
def resolve_profile(country_code: str, lob: str) -> Optional[Dict]
def load_language(profile_id: int) -> str

# Date Scope (v2.22)
def load_profile_date_scope(profile_id: int) -> str          # Returns 'delta', 'today', etc.
def save_profile_date_scope(profile_id: int, date_scope: str) -> None
def parse_date_scope(date_scope: str) -> Optional[int]       # 'today'→0, '7d'→7, 'delta'→None

# Source Loading
def load_rss_feeds(profile_id: int) -> List[Dict]
def load_tweet_accounts(profile_id: int) -> List[Dict]
def load_url_sources(profile_id: int) -> List[Dict]

# Email & Glossary
def load_email_receivers(profile_id: int) -> List[str]
def load_email_receivers_with_lang(profile_id: int) -> List[Dict]
def load_glossary(profile_id: int) -> List[str]

# Settings
def get_setting_value(profile_id: int, key: str) -> Optional[str]
def set_setting_value(profile_id: int, key: str, value: str) -> None

# Baseline
def add_news_item(profile_id: int, item: Dict) -> None
def get_weekly_baseline(profile_id: int, days: int = 7) -> List[Dict]

# Global Credentials (Legacy)
def load_global_credentials() -> Dict[str, str]
```

---

## 9. Data Flow

### 9.1 Daily Digest Flow (v3)

```
┌─────────────────────────────────────────────────────────────────┐
│                    DAILY DIGEST FLOW (v3)                        │
└─────────────────────────────────────────────────────────────────┘

1. TRIGGER (Manual, Run All Active, or External Scheduler)
   └─> agents_controller.run_profile_once(profile_id)

2. HEALTH CHECK  (health_check.run_health_checks)
   └─> DB / AI Core / Gmail hard-block; source + Twitter warnings

3. FETCH  (per-source last_successful_fetch anchor)
   ├─> RSS Parser · Tweet Feed · URL Sources (simulated + legacy)
   └─> Email Inbox (Monitor Updates)

4. ATTRIBUTE  (authority_attributor.attribute_items)
   └─> publisher / authority_id / authority_status (configured | inferred)

5. ANNOTATE  (compare_news → run_compare_news_agent)
   └─> NEW | UPDATE | REPEATED | DUPLICATE (rank 0, never dropped)

6. RANK  (news_ranker.rank_items)
   └─> Tier 0 duplicate → Tier 1 signals → Tier 2 gpt-4o (grounded)
       significance_rank 1–5, REPEATED elevation

7. TAG  (news_tagger)
   └─> topic_label + flag_glossary_gaps (glossary_gap)

8. EMAIL RANK GATE
   └─> email_eligible = 1 for rank ≥ threshold (default 3), non-duplicate

9. TRANSLATE (news_translator) + SAVE TO DB
   └─> all four dimensions persisted; visible in Review UI immediately

10. FINISH RUN = SUCCESS  →  EMAIL FILTER + SEND (decoupled thread)
    └─> email_sender.send_digest() → email_composer.generate_digest()
        writes news_announcements, sets email_sent, updates runs.email_status
        (SKIPPED in test mode; Resend on FAILED)

Human review is ASYNC — it happens after the email, never blocking the run.
Challenge → confirm feeds ranking_grounding + ranking_signals for the next run.
```

### 9.2 Monitor Updates Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      MONITOR UPDATES FLOW                        │
└─────────────────────────────────────────────────────────────────┘

1. CHECK SETTING
   └─> get_setting_value(profile_id, 'monitor_updates')
       └─> If 'true', proceed

2. CHECK INBOX
   └─> email_inbox_parser.check_inbox_for_updates()
       ├─> Connect to Gmail IMAP
       ├─> Search for emails from Law-to-Spec
       ├─> Filter by profile country code
       └─> Extract updates (last 7 days)
   
   Result: List[Dict] updates

3. SEND ALERT EMAIL
   └─> email_sender.send_monitor_alert()
       ├─> Format updates as HTML
       ├─> Send to profile receivers
       └─> Subject: "⚠️ Legal Eagle Monitor Alert — SA/HCM"
   
   Result: Boolean (alert sent)
```

---

## 10. API Reference

### 10.1 Database API (`configurations/db.py`)

**Connection Management**:
```python
def get_connection() -> sqlite3.Connection
def create_schema_if_needed(conn: sqlite3.Connection) -> None
```

**Profile Operations**:
```python
def create_profile(
    conn: sqlite3.Connection,
    country_code: str,
    lob: str,
    name: str = None,
    active: int = 1,
    language: str = "en"
) -> int

def update_profile_language(
    conn: sqlite3.Connection,
    profile_id: int,
    language: str
) -> None
```

**Source Management**:
```python
def upsert_rss_feed(
    conn: sqlite3.Connection,
    profile_id: int,
    url: str,
    max_lookback_days: int = 7
) -> None

def update_rss_feed_last_fetch(
    conn: sqlite3.Connection,
    profile_id: int,
    url: str,
    last_fetch_date: str
) -> None

def upsert_tweet_account(
    conn: sqlite3.Connection,
    profile_id: int,
    handle: str,
    max_lookback_days: int = 7
) -> None

def update_tweet_account_last_fetch(
    conn: sqlite3.Connection,
    profile_id: int,
    handle: str,
    last_fetch_date: str
) -> None

def upsert_url_source(
    conn: sqlite3.Connection,
    profile_id: int,
    url: str,
    mode: str = "auto",
    date_scope: str = "last_7_days",
    sample_link: str = None,
    read_more_label: str = None,
    recursive_crawl: int = 0,
    crawl_version: str = "v1",
    use_proxy: int = 0
) -> None

def delete_url_source(
    conn: sqlite3.Connection,
    source_id: int
) -> None
```

**Email & Glossary**:
```python
def upsert_email_receiver(
    conn: sqlite3.Connection,
    profile_id: int,
    email: str
) -> None

def upsert_email_receiver_with_lang(
    conn: sqlite3.Connection,
    profile_id: int,
    email: str,
    translation_lang: str = "en"
) -> None
```

**Run Management**:
```python
def create_run(
    conn: sqlite3.Connection,
    profile_id: int
) -> int

def start_run(
    conn: sqlite3.Connection,
    run_id: int
) -> None

def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    items_collected: int = 0,
    items_filtered: int = 0,
    items_new: int = 0,
    items_updated: int = 0,
    email_sent: int = 0,
    error_message: str = None
) -> None

def append_run_log(
    conn: sqlite3.Connection,
    run_id: int,
    message: str
) -> None

def list_runs_for_profile(
    conn: sqlite3.Connection,
    profile_id: int,
    limit: int = 10
) -> List[Dict]

def get_run(
    conn: sqlite3.Connection,
    run_id: int
) -> Optional[Dict]

def list_run_logs(
    conn: sqlite3.Connection,
    run_id: int
) -> List[Dict]

def set_cancel_requested(
    conn: sqlite3.Connection,
    run_id: int
) -> None

def is_cancel_requested(
    conn: sqlite3.Connection,
    run_id: int
) -> bool

def prune_old_runs(
    conn: sqlite3.Connection,
    days: int = 7
) -> int
```

**Filtered News**:
```python
def list_filtered_news(
    conn: sqlite3.Connection,
    profile_id: int,
    limit: int = 100,
    offset: int = 0
) -> List[Dict]

def count_filtered_news(
    conn: sqlite3.Connection,
    profile_id: int
) -> int

def update_filtered_news_score(
    conn: sqlite3.Connection,
    item_id: int,
    score: float
) -> None

def delete_filtered_news(
    conn: sqlite3.Connection,
    item_id: int
) -> None

def clear_filtered_news(
    conn: sqlite3.Connection,
    profile_id: int
) -> int

def prune_old_filtered_news(
    conn: sqlite3.Connection,
    days: int = 30
) -> int
```

### 10.2 v3 Database Functions (`configurations/db.py`, verified)

```python
# Authorities (v3.0)
def create_authority(conn, profile_id, name, aliases="") -> int
def list_authorities(conn, profile_id) -> List[Dict]
def get_authority(conn, authority_id) -> Optional[Dict]
def update_authority(conn, authority_id, name, aliases="") -> None
def delete_authority(conn, authority_id) -> None

# Glossary
def add_glossary_term(conn, profile_id, term, lang="en", category=None,
                      product=None, weight=1.0, notes=None) -> int
def list_glossary_terms(conn, profile_id) -> List[Dict]

# Review (both news_items + filtered_news; sets item['is_gap'] from glossary_gap)
def list_all_news_for_review(conn, profile_id, source=None, reviewed=None,
                             limit=50, offset=0) -> List[Dict]
def count_all_news_for_review(conn, profile_id, source=None, reviewed=None) -> int

# Source Simulator (v3.1, F9)
def save_simulation_result(conn, profile_id, url, *, sample_link=None,
    container_selector=None, field_selectors=None, read_more_selector=None,
    pagination_type=None, pagination_selector=None, depth_level=None,
    requires_js=0, simulation_status="success") -> None
def update_url_source_last_fetch(conn, profile_id, url, timestamp) -> None

# Ranking engine (v3.2 / self-improving loop v3.4)
def insert_ranking_signal(conn, profile_id, pattern, rank, reason=None) -> int
def insert_ranking_grounding(conn, profile_id, item_id, example_md,
                             source_label=None) -> int

# Announcements (v3.4) — Level 2/3 of the Review hierarchy
def get_announcements_for_run_with_sources(conn, run_id) -> List[Dict]
def reset_review_data(conn, profile_id=None) -> Dict[str, int]

# Audit + runs (finish_run takes a metrics dict in v3)
def add_audit_log(conn, entity, action, details=None, profile_id=None) -> None
def create_run(conn, profile_id, origin="manual") -> int
def start_run(conn, run_id) -> None
def finish_run(conn, run_id, status, metrics=None) -> None
```

---

## 11. File Structure

```
legal-eagle/
├── agents/                          # Processing pipeline
│   ├── __init__.py
│   ├── agents_controller.py         # Main orchestrator (v3 stage sequence)
│   ├── health_check.py              # Pre-run reachability checks (v3.1, F2)
│   ├── rss_parser.py                # RSS feed parser
│   ├── tweet_feed.py                # Twitter/X integration
│   ├── url_sources_runner.py        # Website crawler (+ scrape_url_source_with_config)
│   ├── source_simulator.py          # Zero-config URL source auto-discovery (v3.1, F9)
│   ├── email_inbox_parser.py        # Gmail inbox monitor
│   ├── date_filter.py               # Publication-date windowing
│   ├── authority_attributor.py      # ATTRIBUTE stage: publisher/authority (v3.1/3.2)
│   ├── compare_news.py              # ANNOTATE: NEW/UPDATE/REPEATED/DUPLICATE
│   ├── news_ranker.py               # Three-tier ranking engine (v3.2)
│   ├── news_tagger.py               # Glossary tagging + flag_glossary_gaps (v3.3/3.5)
│   ├── news_translator.py           # Post-save translation step (v3)
│   ├── news_filter.py               # DELETED in v3.1 (replaced by ranker Rank 1 = Noise)
│   ├── news_grouper.py              # LEGACY — replaced by news_tagger (v3.3)
│   ├── email_composer.py            # V2 AI digest → news_announcements (v3.3)
│   ├── email_sender.py              # Render + SMTP (send_digest / legacy send_email)
│   ├── ai_cache.py                  # Deterministic chat/embedding cache for the harness
│   ├── rcm_checker.py               # RCM lookup helper
│   ├── ans_sender.py                # SAP BTP ANS email sender (v2.26, disabled — re-enable for BTP)
│   ├── sap_ai_client.py             # SAP AI Core client
│   ├── mcp_client.py                # MCP protocol client
│   └── text_utils.py                # Text utilities (+ publication-date parsing)
│
├── tests/                           # Deterministic integration harness (v3.0+)
│   ├── run_harness.py               # Entry point — python tests/run_harness.py --version vX.Y
│   ├── reset_and_seed.py            # Seeds Xanadu (XN/HCM) profile + ranking_signals
│   ├── assertions.py                # Assertion runner
│   ├── server.py                    # localhost:9999 fixture feed server
│   ├── ai_cache/                    # Recorded chat/embedding responses for replay
│   └── fixtures/                    # feeds/ · articles/ · seed/ · expected/vX.Y.json
│
├── admin/                           # Flask admin UI
│   ├── app.py                       # Flask application
│   ├── templates/                   # Jinja2 templates
│   │   ├── base.html                # Base template (Fiori CSS)
│   │   ├── dashboard.html           # Profile list
│   │   ├── create_profile.html      # Create profile
│   │   ├── profile.html             # Configure tab
│   │   ├── run_status.html          # Run tab
│   │   └── review_news.html         # Review tab
│   └── outputs/                     # Symlink to ../outputs/
│
├── configurations/                  # Configuration layer
│   ├── __init__.py
│   ├── config_loader.py             # Unified config API
│   ├── db.py                        # SQLite operations
│   ├── env_loader.py                # Environment variables
│   ├── config.db                    # SQLite database
│   └── requirements.txt             # Config dependencies
│
├── scripts/                         # Utility scripts
│   ├── launch_admin.py              # Admin UI launcher
│   ├── start_admin.sh               # Admin UI startup
│   ├── start_admin_nohup.sh         # Background admin
│   ├── start_admin_launchd.sh       # macOS launchd
│   ├── start_admin_on_login.sh      # Login startup
│   ├── start_admin_with_autoreload.sh  # Dev mode
│   ├── restart_admin.sh             # Restart admin
│   ├── migrate_*.py                 # Database migrations
│   ├── setup_*.py                   # Profile setup scripts
│   ├── resend_email_from_html.py    # Email resend utility
│   ├── load_harness_run.py         # Copy latest harness run → config.db for manual testing, remap IDs (renamed from refresh_xanadu_demo.py)
│   ├── prep_xanadu_demo.py          # Demo prep: reset Xanadu review data + seed REPEATED baseline (Xanadu-only guard)
│   ├── export_config.py             # Export DB config to JSON (v2.31)
│   ├── import_config.py             # Import DB config from JSON (v2.31)
│   ├── launchd/                     # macOS launchd configs
│   │   └── com.legaleagle.admin.plist
│   └── systemd/                     # Linux systemd configs
│       ├── legal-eagle.service
│       └── legal-eagle.timer
│
├── outputs/                         # Generated artifacts
│   ├── {COUNTRY}_{LOB}/             # Per-profile outputs
│   │   ├── all_news.json            # All collected items
│   │   ├── filtered_news.json       # Filtered items
│   │   ├── email_preview.html       # Email preview
│   │   └── *.png                    # Screenshots
│   ├── cache/                       # Crawler cache
│   │   └── listings/                # Cached listings
│   └── admin.pid                    # Admin UI PID file
│
├── memory-bank/                     # Project memory
│   ├── activeContext.md             # Current state
│   ├── progress.md                  # Version history
│   ├── techContext.md               # Technical details
│   ├── productContext.md            # Product vision
│   ├── systemPatterns.md            # Design patterns
│   └── projectbrief.md              # Project overview
│
├── docs/                            # Documentation
│   ├── README.md                    # User guide
│   └── lifecycle.html               # Pipeline lifecycle diagram (updated each version)
│
├── Resources/                       # Static assets served via /Resources/<path>
│   ├── ERGANI_II_MindMap_v2.html    # Greece ERGANI II MindMap (v2.30)
│   ├── Greece_Glossary.md           # Greece glossary source (87 terms, v2.30)
│   └── Greece_URL_Resources         # Greece URL source list (v2.30)
│
├── .cfignore                        # Cloud Foundry ignore
├── .gitignore                       # Git ignore
├── .profile                         # BTP startup script
├── apt.yml                          # BTP apt packages
├── manifest.yaml                    # BTP deployment config
├── Procfile                         # BTP process config
├── requirements.txt                 # Python dependencies
├── runtime.txt                      # Python version
├── README.md                        # Project README
├── CHANGELOG.md                     # Version history
├── SPEC.md                          # Technical spec (this file)
└── BTP_DEPLOYMENT.md                # Deployment guide
```

---

## 12. Outputs & Artifacts

### 12.1 Per-Profile Outputs (`outputs/{COUNTRY}_{LOB}/`)

**Generated Files**:
- `all_news.json` - All collected items (raw + filtered)
- `filtered_news.json` - Items passing AI filter
- `email_preview.html` - Preview of sent email
- `*.png` - Screenshots from browser actions

**JSON Structure**:
```json
{
  "profile": {
    "country_code": "SA",
    "lob": "HCM",
    "language": "en"
  },
  "timestamp": "2026-04-24T00:30:00Z",
  "items": [
    {
      "source": "https://www.gosi.gov.sa/rss",
      "source_type": "RSS",
      "title": "New GOSI Regulation on Wage Protection",
      "link": "https://www.gosi.gov.sa/news/123",
      "date": "2026-04-23",
      "content": "Full article text...",
      "score": 0.85
    }
  ]
}
```

### 12.2 Email Artifacts

**Preview File** (`email_preview.html`):
- Saved copy of sent email
- Includes all HTML/CSS styling
- Useful for debugging email rendering

**Email Structure**:
- Subject: "🦅 Legal Eagle Daily Digest — {COUNTRY}/{LOB} — {DATE}"
- From: LEGAL_EAGLE_GMAIL_EMAIL
- To: Profile receivers
- Format: HTML (responsive design)
- Sections:
  - Header (country-colored banner)
  - Summary statistics
  - Grouped news items (by theme)
  - Footer (profile details)

### 12.3 Database Snapshots

**Baseline** (`news_items` table):
- Rolling 7-day window
- Used for deduplication
- Pruned automatically

**Filtered News** (`filtered_news` table):
- Items awaiting review
- Scored by AI filter
- Can be approved/rejected in Review tab

**Run History** (`runs` + `run_logs` tables):
- Last 7 days of execution logs
- Metrics per run (items collected, filtered, etc.)
- Status tracking (Pending, Running, Completed, Failed, Canceled)

---

## Future Plans

For information about planned UI5/Fiori migration and other strategic initiatives, see:
- **[UI5_MIGRATION_ROADMAP.md](UI5_MIGRATION_ROADMAP.md)** — Detailed UI5/Fiori migration plan
- **[README.md](README.md)** — Roadmap section for all planned enhancements

---

## 13. Greece Profile (v2.30)

### 13.1 Profile Configuration

| Field | Value |
|-------|-------|
| Country Code | `GR` |
| LoB | `HCM` |
| Name | Default GR/HCM |
| Language | `el` (Greek) |

### 13.2 URL Sources (8)

| Source | URL | Mode |
|--------|-----|------|
| ERGANI | https://www.ergani.gov.gr | auto |
| Ministry of Labour | https://www.ypergasias.gov.gr | auto |
| EFKA | https://www.efka.gov.gr | auto |
| TEKA | https://www.teka.gov.gr | auto |
| TEKA eServices | https://www.tekaservices.gr | auto |
| AADE | https://www.aade.gr | auto |
| FEK (Official Gazette) | https://www.et.gr | auto |
| Gov.gr | https://www.gov.gr | auto |

### 13.3 Glossary

87 Greek legal terms seeded from `Resources/Greece_Glossary.md` across 7 categories:
- Employment Law, Social Insurance, Tax/Finance, Labor Relations, Digital Systems, Pension/Benefits, Health & Safety

### 13.4 Seeding Script

Idempotent (safe to re-run):
- `scripts/seed_greece_profile.py` — creates profile, URL sources, glossary

---

*End of Technical Specification*
