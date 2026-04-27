# Legal Eagle 2.16 — Technical Specification

**Version:** 2.16 (Admin UI Fixes & Enhancements)  
**Last Updated:** 2026-04-28

This document provides the technical specification for Legal Eagle, an AI-powered regulatory compliance mr onitoring system for SAP Localization.

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
- **AI-first filtering**: Semantic understanding via LLM, not keyword matching
- **Human-in-the-loop**: Reviewed items improve future filtering accuracy
- **Environment-based secrets**: No credentials in database or code

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LEGAL EAGLE 2.2 ARCHITECTURE                       │
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
│  │                      PROCESSING PIPELINE                              │   │
│  │                                                                       │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐   │   │
│  │  │   news_filter   │───▶│  compare_news   │───▶│  news_grouper   │   │   │
│  │  │ (AI Relevance)  │    │ (Dedup/Updates) │    │ (AI Grouping)   │   │   │
│  │  └─────────────────┘    └─────────────────┘    └────────┬────────┘   │   │
│  │                                                          │            │   │
│  │  ┌──────────────────────────────────────────────────────┘            │   │
│  │  │                                                                    │   │
│  │  │  ┌──────────────────────┐                                         │   │
│  │  └─▶│ email_inbox_parser   │ (Monitor Updates from Law-to-Spec)      │   │
│  │     │ (Gmail IMAP)         │                                         │   │
│  │     └──────────┬───────────┘                                         │   │
│  │                │                                                     │   │
│  └────────────────┼─────────────────────────────────────────────────────┘   │
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
- **AI/LLM**: SAP AI Core (gpt-4o, text-embedding-ada-002)

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
- `max_lookback_days`: Maximum days to look back for articles (default: 7)
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
- `max_lookback_days`: Maximum days to look back for tweets (default: 7)
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
- `mode`: Crawl mode ('auto', 'force_static', 'force_dynamic')
- `date_scope`: Date filtering ('last_7_days', 'last_30_days', 'all')
- `sample_link`: Optional sample link for pattern detection
- `read_more_label`: Optional "read more" button text
- `recursive_crawl`: 1 = crawl subpages, 0 = single page only
- `crawl_version`: Crawl engine version ('v1' or 'v2')
- `last_successful_fetch`: ISO 8601 timestamp of last successful fetch
- `use_proxy`: 1 = use BrightData proxy, 0 = direct connection

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

Historical news items (weekly baseline).

```sql
CREATE TABLE news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_type TEXT,
    title TEXT NOT NULL,
    link TEXT,
    date TEXT,
    content TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);
```

**Columns:**
- `id`: Auto-increment primary key
- `profile_id`: Foreign key to profiles table
- `source`: Source name (e.g., RSS feed URL, Twitter handle)
- `source_type`: Type ('RSS', 'Twitter', 'URL_Static', 'URL_Dynamic')
- `title`: News item title
- `link`: URL to full article
- `date`: Publication date (ISO 8601)
- `content`: Article content or summary
- `created_at`: Timestamp when added to database

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

Global credentials (legacy, mostly moved to environment variables).

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

### 5.5 News Filter (`agents/news_filter.py`)

**Purpose**: AI-powered relevance filtering using LLM.

**Key Functions**:
```python
def filter_news_items(
    items: List[Dict],
    country_code: str,
    lob: str,
    glossary: List[str],
    api_key: str,
    language: str = "en"
) -> Tuple[List[Dict], List[Dict]]
```

**Input**:
- `items`: Raw news items from sources
- `country_code`: Profile country code
- `lob`: Profile Line of Business
- `glossary`: Custom terms for context
- `api_key`: SAP AI Core API key
- `language`: Analysis language

**Output**:
- Tuple of (filtered_items, rejected_items)
- Filtered items include `score` field (0.0-1.0)

**AI Prompt**:
- Evaluates legal relevance to country/LoB
- Considers SAP product scope (HCM, Payroll, SuccessFactors, S/4HANA)
- Uses glossary terms for domain context
- Returns structured JSON with score and reasoning

---

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

---

### 5.7 News Grouper (`agents/news_grouper.py`)

**Purpose**: Group related news items using AI clustering.

**Key Functions**:
```python
def group_news_items(
    items: List[Dict],
    api_key: str,
    language: str = "en"
) -> List[Dict]
```

**Input**:
- `items`: New/updated items to group
- `api_key`: SAP AI Core API key
- `language`: Analysis language

**Output**:
- List of group dicts with `theme`, `items`, `summary`

**AI Prompt**:
- Identifies common themes across items
- Groups related items together
- Generates concise summary per group
- Returns structured JSON

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
    selected_rss_urls: Optional[List[str]] = None,
    selected_twitter_handles: Optional[List[str]] = None,
    selected_url_sources: Optional[List[str]] = None
) -> Dict
```

**Parameters**:
- `profile_id`: Profile to run
- `force_run`: Force execution even if no new items
- `skip_comparison`: Skip baseline comparison (force all items as new)
- `skip_email`: Skip email sending (dry run)
- `selected_rss_urls`: Optional list of RSS feed URLs to fetch (None = all)
- `selected_twitter_handles`: Optional list of Twitter handles to fetch (None = all)
- `selected_url_sources`: Optional list of URL sources to crawl (None = all)

**Execution Flow**:
1. **Load Configuration**: Profile, sources, receivers, glossary
2. **Filter Sources** (v2.14): Apply source selection filters if provided
   - Filter RSS feeds to selected URLs only
   - Filter Twitter accounts to selected handles only
   - Filter URL sources to selected URLs only
   - Log filtered counts: "📰 Filtered RSS feeds: 1 selected out of 3"
3. **Validate Twitter**: Pre-flight check, skip if error flag set
4. **Collect Data**: RSS feeds, tweets, URL sources, email inbox
5. **Filter**: AI-powered relevance filtering
6. **Compare**: Deduplicate and detect updates against baseline
7. **Group**: AI clustering of related items
8. **Email**: Send digest to receivers (if new/updated items found)
9. **Update Baseline**: Store new items in database
10. **Log**: Record execution metrics and logs

**Skip Flags**:
- `skip_comparison`: Skip baseline comparison (force all items as new)
- `force_run`: Force execution even if no new items
- `skip_email`: Skip email sending (dry run)

**Source Selection** (v2.14):
- When selection parameters are `None`, all sources are fetched (default behavior)
- When selection parameters are provided as lists, only those sources are fetched
- Empty list `[]` is converted to `None` by the Admin UI (meaning "run all")
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

### 7.3 UI Enhancements (v2.16)

**Table Consistency Improvements**:
- **RSS Feeds Table**: Added "Lookback Days" column showing max_lookback_days per feed
- **Twitter Accounts Table**: Added "Lookback Days" column showing max_lookback_days per account
- **URL Sources Table**: Added "Lookback Days", "Sample Link", and "Read More Label" columns
- All tables now display complete configuration at a glance without requiring Edit mode

**Form Field Ordering**:
- **Add Form**: Fields reordered to match table column sequence
  - Order: Lookback Days → Sample Link → Read More Label → Crawl Type
- **Edit Form**: Fields reordered to match table column sequence (same order as Add form)
- Consistent left-to-right flow improves usability and reduces cognitive load

**Section Reordering**:
Profile page sections now follow pipeline execution order:
1. Profile Language (analysis language for AI)
2. RSS Feeds (first data source)
3. Twitter Accounts (second data source)
4. URL Sources (third data source)
5. Email Receivers (output configuration)
6. Monitor Notifications (Law-to-Spec integration)
7. Glossary (filtering context)

**Recursive Fields Toggle**:
- **Add Form**: Recursive fields now show/hide correctly when selecting "Recursive" mode
- **Edit Form**: Added recursive fields toggle for non-recursive sources
  - Dynamic IDs per row: `edit1UrlMode`, `edit2UrlMode`, etc.
  - JavaScript function `toggleRecursiveFields(prefix)` handles both Add and Edit contexts
- Both forms now have identical behavior and field structure

**Developer Experience**:
- Flask `TEMPLATES_AUTO_RELOAD = True` enabled for faster template iteration
- Templates reload automatically without server restart during development

---

## 8. Configuration

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

### 9.1 Daily Digest Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        DAILY DIGEST FLOW                         │
└─────────────────────────────────────────────────────────────────┘

1. TRIGGER (Manual or External Scheduler)
   └─> agents_controller.run_profile_once(profile_id)

2. LOAD CONFIGURATION
   ├─> Profile settings (country, LoB, language)
   ├─> Data sources (RSS, Twitter, URLs)
   ├─> Email receivers
   └─> Glossary terms

3. COLLECT DATA (Parallel)
   ├─> RSS Parser → parse_rss_feeds()
   ├─> Tweet Feed → search_tweets_multi_account()
   ├─> URL Sources → run_url_sources()
   └─> Email Inbox → check_inbox_for_updates()
   
   Result: List[Dict] raw items

4. FILTER (AI)
   └─> news_filter.filter_news_items()
       ├─> LLM evaluates relevance (0.0-1.0)
       ├─> Uses country/LoB context
       └─> Applies glossary terms
   
   Result: List[Dict] filtered items (score >= 0.6)

5. COMPARE (Deduplication)
   └─> compare_news.compare_with_baseline()
       ├─> Load 7-day baseline from DB
       ├─> Match by title/link
       └─> Detect content updates
   
   Result: {new: [], updated: [], unchanged: []}

6. GROUP (AI)
   └─> news_grouper.group_news_items()
       ├─> LLM identifies themes
       ├─> Clusters related items
       └─> Generates summaries
   
   Result: List[Dict] grouped items

7. EMAIL (Conditional)
   └─> email_sender.send_email()
       ├─> Skip if no new/updated items
       ├─> Translate per receiver language
       ├─> Send bilingual HTML email
       └─> Log sent status
   
   Result: Boolean (email sent)

8. UPDATE BASELINE
   └─> Add new items to news_items table

9. RECORD METRICS
   └─> Update runs table with stats
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

---

## 11. File Structure

```
legal-eagle/
├── agents/                          # Processing pipeline
│   ├── __init__.py
│   ├── agents_controller.py         # Main orchestrator
│   ├── rss_parser.py                # RSS feed parser
│   ├── tweet_feed.py                # Twitter/X integration
│   ├── url_sources_runner.py        # Website crawler
│   ├── email_inbox_parser.py        # Gmail inbox monitor
│   ├── news_filter.py               # AI relevance filter
│   ├── compare_news.py              # Deduplication
│   ├── news_grouper.py              # AI clustering
│   ├── email_sender.py              # Email delivery
│   ├── sap_ai_client.py             # SAP AI Core client
│   ├── loka_agent.py                # LOKA integration
│   ├── loka_client.py               # LOKA HTTP client
│   ├── mcp_client.py                # MCP protocol client
│   └── text_utils.py                # Text utilities
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
│   └── README.md                    # User guide
│
├── Resources/                       # Test resources
│   └── *.pdf                        # Sample documents
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

*End of Technical Specification*
