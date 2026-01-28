# Legal Eagle 2.1 — Technical Specification

**Version:** 2.1 (SAP Fiori Design)  
**Last Updated:** 2026-01-28

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
- **AI-first filtering**: Semantic understanding via LLM, not keyword matching
- **Human-in-the-loop**: Reviewed items improve future filtering accuracy
- **Environment-based secrets**: No credentials in database or code

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LEGAL EAGLE 2.0 ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         DATA SOURCES                                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐   │   │
│  │  │ RSS Feeds   │  │ Twitter/X   │  │ Websites (Static/Dynamic)   │   │   │
│  │  │ rss_parser  │  │ tweet_feed  │  │ url_sources_runner          │   │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────────────┬──────────────┘   │   │
│  └─────────┼────────────────┼────────────────────────┼──────────────────┘   │
│            │                │                        │                       │
│            └────────────────┼────────────────────────┘                       │
│                             ▼                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      PROCESSING PIPELINE                              │   │
│  │                                                                       │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐   │   │
│  │  │   news_filter   │───▶│  compare_news   │───▶│  news_grouper   │   │   │
│  │  │ (AI Relevance)  │    │ (Dedup/Updates) │    │ (AI Grouping)   │   │   │
│  │  └─────────────────┘    └─────────────────┘    └────────┬────────┘   │   │
│  │                                                          │            │   │
│  └──────────────────────────────────────────────────────────┼────────────┘   │
│                                                              ▼               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         OUTPUT                                        │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐   │   │
│  │  │  email_sender   │    │  JSON Snapshots │    │  SQLite DB      │   │   │
│  │  │ (Daily Digest)  │    │ (outputs/)      │    │ (Baseline)      │   │   │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         ADMIN UI (Flask)                              │   │
│  │  • Profile Management    • Source Configuration    • Run Execution   │   │
│  │  • Glossary Management   • Filtered News Review    • Live Logs       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         STORAGE                                       │   │
│  │  ┌─────────────────┐    ┌─────────────────┐                          │   │
│  │  │ SQLite DB       │    │ Environment     │                          │   │
│  │  │ (config.db)     │    │ Variables       │                          │   │
│  │  │ - Profiles      │    │ - API Keys      │                          │   │
│  │  │ - Sources       │    │ - Credentials   │                          │   │
│  │  │ - Glossary      │    │                 │                          │   │
│  │  │ - News Baseline │    │                 │                          │   │
│  │  │ - Runs/Logs     │    │                 │                          │   │
│  │  └─────────────────┘    └─────────────────┘                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

### 3.1 Runtime

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Primary language |
| SQLite | 3.x | Configuration and baseline storage |
| Playwright | Latest | Headless browser for dynamic sites |

### 3.2 Python Dependencies

| Package | Purpose |
|---------|---------|
| `feedparser` | RSS/Atom feed parsing |
| `openai` | GPT-4o-mini (filtering, grouping) and embeddings |
| `requests` | HTTP requests for static content |
| `beautifulsoup4` | HTML parsing |
| `playwright` | Dynamic website rendering |
| `numpy` | Numerical operations (cosine similarity) |
| `httpx` | HTTP client for OpenAI (HTTP/2 disabled) |
| `flask` | Admin UI web framework |
| `python-dotenv` | Environment variable loading |

### 3.3 External Services

| Service | Model/Endpoint | Purpose |
|---------|----------------|---------|
| OpenAI | `gpt-4o-mini` | Semantic filtering and grouping |
| OpenAI | `text-embedding-3-small` | Semantic similarity for deduplication |
| Twitter/X API | `GET /2/users/{id}/tweets` | Timeline monitoring |
| Gmail SMTP | `smtp.gmail.com:587` | Email delivery |

---

## 4. Database Schema

Database file: `configurations/config.db` (SQLite)

### 4.1 Core Tables

#### `profiles`
Defines Country + LoB combinations.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `country_code` | TEXT | ISO alpha-2 country code (e.g., `SA`, `AE`) |
| `lob` | TEXT | Line of Business (`HCM` or `FIN`) |
| `name` | TEXT | Optional display name |
| `language` | TEXT | Output language (default: `en`) |
| `active` | INTEGER | 1 = active, 0 = inactive |
| `schedule_day` | TEXT | Day of week to run (e.g., `Sunday`) |

**Unique constraint**: `(country_code, lob, name)`

#### `settings`
Per-profile key-value settings.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `key` | TEXT | Setting key |
| `value` | TEXT | Setting value |

**Unique constraint**: `(profile_id, key)`

### 4.2 Source Tables

#### `rss_feeds`
RSS/Atom feed URLs per profile.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `url` | TEXT | Feed URL |

#### `tweet_accounts`
Twitter/X handles to monitor.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `handle` | TEXT | Twitter handle (without @) |

#### `url_sources`
Websites to scrape (unified static/dynamic).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `url` | TEXT | Listing page URL |
| `mode` | TEXT | `auto`, `force_static`, or `force_dynamic` |
| `sample_link` | TEXT | Example detail page URL (for pattern derivation) |
| `read_more_label` | TEXT | Text of "read more" button (for dynamic sites) |
| `crawl_version` | TEXT | `v1` or `v2` (runner version) |
| `created_at` | TEXT | ISO timestamp |

#### `email_receivers`
Email recipients for daily digest.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `email` | TEXT | Email address |

### 4.3 Glossary Tables

#### `glossary_terms`
Terms that define relevance for a profile's LoB.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `term` | TEXT | The glossary term |
| `lang` | TEXT | Language code (default: `en`) |
| `category` | TEXT | `HCM`, `FIN`, or NULL |
| `product` | TEXT | Optional product association |
| `weight` | REAL | Term weight (default: 1.0) |
| `notes` | TEXT | Optional notes |

#### `glossary_synonyms`
Synonyms for glossary terms.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `term_id` | INTEGER FK | References `glossary_terms(id)` |
| `synonym` | TEXT | Synonym text |

#### `glossary_patterns`
Regex patterns for glossary terms.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `term_id` | INTEGER FK | References `glossary_terms(id)` |
| `regex` | TEXT | Regular expression pattern |

### 4.4 News Baseline Tables

#### `news_items`
Rolling 7-day baseline for deduplication and update detection.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `source_type` | TEXT | `RSS`, `Tweet`, `URL_Static`, `URL_Dynamic` |
| `source_id` | TEXT | Unique ID from source (guid, tweet_id) |
| `url` | TEXT | Article URL |
| `domain` | TEXT | Source domain |
| `title` | TEXT | Article title |
| `content` | TEXT | Article content/summary |
| `published_at` | TEXT | Publication date (ISO) |
| `first_seen_at` | TEXT | First seen timestamp (ISO) |
| `last_seen_at` | TEXT | Last seen timestamp (ISO) |
| `hash_signature` | TEXT | Normalized text hash |

**Indexes**: `(profile_id, first_seen_at)`, `(profile_id, last_seen_at)`, `(profile_id, url)`, `(profile_id, source_type, source_id)`

#### `filtered_news`
Items filtered out, available for manual review.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `run_id` | INTEGER FK | References `runs(id)` (nullable) |
| `source_type` | TEXT | Source type |
| `url` | TEXT | Article URL |
| `title` | TEXT | Article title |
| `content` | TEXT | Article content |
| `filter_reason` | TEXT | `too_old`, `semantic_check_failed` |
| `relevance_score` | INTEGER | Manual score 1-5 (NULL until reviewed) |
| `reviewed_at` | TEXT | Review timestamp (ISO) |
| `published_at` | TEXT | Publication date |
| `created_at` | TEXT | Created timestamp |

### 4.5 Run History Tables

#### `runs`
Execution history for each profile.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` |
| `status` | TEXT | `Queued`, `Running`, `Success`, `Failed`, `Canceled` |
| `origin` | TEXT | `manual` or `scheduled` |
| `started_at` | TEXT | Start timestamp (ISO) |
| `finished_at` | TEXT | Finish timestamp (ISO) |
| `duration_ms` | INTEGER | Duration in milliseconds |
| `rss_count` | INTEGER | RSS items collected |
| `tweet_count` | INTEGER | Tweets collected |
| `url_count` | INTEGER | URL items collected |
| `filtered_count` | INTEGER | Items after filtering |
| `grouped_count` | INTEGER | Groups in email |
| `email_status` | TEXT | `Sent` or `Failed` |
| `cancel_requested` | INTEGER | 1 if cancel requested |
| `created_at` | TEXT | Created timestamp |

#### `run_logs`
Log lines for each run (for live streaming).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `run_id` | INTEGER FK | References `runs(id)` |
| `ts` | TEXT | Timestamp (ISO) |
| `level` | TEXT | `INFO`, `WARN`, `ERROR` |
| `line` | TEXT | Log message |
| `seq` | INTEGER | Sequence number |

### 4.6 Audit Table

#### `audit_log`
Tracks admin actions for accountability.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment ID |
| `profile_id` | INTEGER FK | References `profiles(id)` (nullable) |
| `entity` | TEXT | Entity type (e.g., `profiles`, `rss_feeds`) |
| `action` | TEXT | Action performed (e.g., `create`, `delete`) |
| `details` | TEXT | Additional details |
| `created_at` | TEXT | Timestamp |

---

## 5. Agents (Processing Pipeline)

### 5.1 RSS Parser (`agents/rss_parser.py`)

**Purpose**: Collect news items from RSS/Atom feeds.

**Input**: List of feed URLs

**Output**: List of news items with:
- `source`: Feed domain
- `source_type`: `"RSS"`
- `title`: Entry title
- `link`: Entry URL
- `date`: Publication date
- `content`: Entry summary/description
- `guid`: Entry ID (for deduplication)

**Key Function**:
```python
def parse_rss_feed(url: str) -> List[Dict]
```

### 5.2 Tweet Feed (`agents/tweet_feed.py`)

**Purpose**: Collect tweets from monitored Twitter/X accounts.

**Input**: Account handle, bearer token, profile_id

**Output**: List of tweet items with:
- `source`: `"Twitter"`
- `source_type`: `"Tweet"`
- `title`: Tweet text (truncated)
- `link`: Tweet URL
- `date`: Tweet timestamp
- `content`: Full tweet text
- `tweet_id`: Tweet ID (for deduplication)

**Key Features**:
- Uses timeline endpoint `GET /2/users/{id}/tweets`
- Caches `user_id` and `last_seen_id` per handle in SQLite settings
- Uses `since_id` for incremental fetching
- Hard cap: `max_results=3` per request
- No retries on 429 (rate limit)

**Key Function**:
```python
def fetch_recent_tweets(account_name: str, bearer_token: str, profile_id: int) -> List[Dict]
```

### 5.3 URL Sources Runner (`agents/url_sources_runner.py`)

**Purpose**: Scrape news from government websites (static and dynamic).

**Input**: List of URL source configurations

**Output**: List of news items with:
- `source`: Website domain
- `source_type`: `"URL_Static"` or `"URL_Dynamic"`
- `title`: Article title
- `link`: Article URL
- `date`: Publication date
- `content`: Article content

**Modes**:
| Mode | Behavior |
|------|----------|
| `auto` | Try static first, fallback to dynamic if < 1 item |
| `force_static` | Static only (HTTP GET + BeautifulSoup) |
| `force_dynamic` | Dynamic only (Playwright headless browser) |

**Static Pipeline**:
1. HTTP GET listing page
2. RSS autodiscovery (if available)
3. Extract listing links using heuristics
4. Fetch and parse detail pages

**Dynamic Pipeline**:
1. Render listing page with Playwright (Chromium)
2. Wait for site-specific selectors (e.g., `#newsList` for GOSI)
3. Progressive scrolling to trigger lazy loading
4. Collect links via:
   - Anchor `href` attributes
   - SPA attributes (`routerlink`, `ng-reflect-router-link`, `data-href`)
   - `onclick` URL patterns
   - Label-based discovery (e.g., "اقرأ المزيد")
5. Fetch and parse detail pages
6. Fallback: Extract listing cards if detail links unavailable

**Key Function**:
```python
def run_unified_sources(url_sources: List[Dict], profile_slug: str) -> Dict
```

### 5.4 News Filter (`agents/news_filter.py`)

**Purpose**: Filter news items for relevance to the profile's LoB using AI.

**Input**: 
- All collected news items
- OpenAI API key
- Glossary (HCM/FIN terms)
- Language preference
- LoB (`HCM` or `FIN`)
- High-score baseline (for "second chance" rescue)

**Output**: 
- `items`: Relevant items
- `errors`: Processing errors
- `filtered`: Filtered-out items with reasons

**Filter Pipeline**:

1. **Age Gate**: Discard items older than 7 days (configurable via `LEGAL_EAGLE_MAX_NEWS_AGE_DAYS`)

2. **Semantic Glossary Check**: 
   - Uses GPT-4o-mini to analyze content meaning
   - Compares against glossary terms semantically (not keyword matching)
   - Works across languages (e.g., Arabic content vs English glossary)
   - Returns `is_relevant` boolean and `reasoning`

3. **"Second Chance" Rescue**:
   - Items that fail semantic check are compared against high-score baseline
   - Uses `text-embedding-3-small` for semantic similarity
   - Cosine similarity threshold: 0.85
   - Rescued items marked with `rescued=True`

**Filter Reasons**:
| Reason | Description |
|--------|-------------|
| `too_old` | Publication date > 7 days ago |
| `semantic_check_failed` | LLM determined not relevant |

**Key Function**:
```python
def get_relevant_news(
    all_news_items: list,
    OPENAI_API_KEY: str,
    GLOSSARY: dict,
    LANGUAGE_PREFERENCE: str,
    lob: str,
    high_score_baseline: list = None,
    on_filtered = None
) -> dict
```

### 5.5 Compare News (`agents/compare_news.py`)

**Purpose**: Deduplicate items and detect updates to previously seen news.

**Input**:
- Filtered news items
- Output directory
- Glossary
- Language

**Output**:
- `new_items`: Genuinely new items
- `update_items`: Updates to existing items (with delta highlights)

**Comparison Pipeline**:

1. **Load Weekly Baseline**: Items from last 7 days in `news_items` table

2. **Persist Current Items**: Upsert to database for future baseline

3. **Exact Match Check**: Skip if `source_id`, `url`, or `hash_signature` matches

4. **Semantic Comparison**:
   - Generate embeddings for all items
   - Compute cosine similarity against baseline
   - Compute Jaccard token overlap

5. **Classification**:
   | Cosine | Jaccard | Classification |
   |--------|---------|----------------|
   | ≥ 0.92 | ≥ 0.70 | Duplicate (skip) |
   | ≥ 0.85 | 0.40-0.70 | Update candidate |
   | < 0.85 | any | New item |

6. **Delta Extraction** (for updates):
   - Split into sentences
   - Find sentences with low overlap to baseline
   - Require glossary term presence for meaningful delta
   - Extract 2-4 delta bullets

**Thresholds**:
```python
DEDUP_COSINE_DUP = 0.92
DEDUP_COSINE_UPDATE = 0.85
JACCARD_DUP_MIN = 0.70
JACCARD_UPDATE_MIN = 0.40
WEEKLY_BASELINE_DAYS = 7
```

**Key Function**:
```python
def run_compare_news_agent(
    current_items: List[Dict],
    outputs_dir: str = "outputs",
    glossary: Dict = None,
    language: str = "en"
) -> Dict
```

### 5.6 News Grouper (`agents/news_grouper.py`)

**Purpose**: Group similar news items and generate summaries using AI.

**Input**:
- Final items (new + updates)
- OpenAI API key
- Language preference

**Output**: List of grouped summaries for email

**Key Function**:
```python
def group_and_summarize_news(items: List[Dict], api_key: str, language: str) -> List[Dict]
```

### 5.7 Email Sender (`agents/email_sender.py`)

**Purpose**: Send the daily digest email to configured recipients.

**Input**:
- Grouped summary
- Email receivers list
- Gmail credentials
- Language preference

**Output**: Boolean success status

**Features**:
- Gmail SMTP with App Password
- STARTTLS with SSL fallback
- Retry on transient errors
- HTML formatted email

**Key Function**:
```python
def send_email(
    grouped_summary: List[Dict],
    receivers: List[str],
    gmail_creds: Dict,
    language: str
) -> bool
```

---

## 6. Controller Logic

### 6.1 Main Controller (`agents/agents_controller.py`)

**Purpose**: Orchestrate the full pipeline for all active profiles.

**Entry Points**:
- `run_controller()`: Run all active profiles (respects schedule_day)
- `run_profile_once(profile_id)`: Run a single profile (used by Admin UI)

**Execution Flow**:

```
1. Load credentials from environment
2. List active profiles from database
3. For each profile:
   a. Check schedule_day matches today (Asia/Dubai timezone)
   b. Load profile configuration:
      - Language, RSS feeds, Twitter accounts
      - URL sources, email receivers, glossary
   c. Run RSS Parser Agent
   d. Run Tweet Feed Agent (if not disabled/blocked)
   e. Run URL Sources Runner
   f. Combine all items
   g. Load high-score baseline for rescue
   h. Run News Filter Agent
   i. Run Compare News Agent
   j. Run News Grouper Agent
   k. Run Email Sender Agent
4. Log completion
```

**Schedule Enforcement**:
- Profiles have a `schedule_day` (e.g., "Sunday")
- Controller compares against current day in Asia/Dubai timezone
- Profiles without schedule_day or mismatched day are skipped

**Tweet Quota Reset**:
- Setting `tweets_reset_quota_date` blocks tweets until that date
- Comparison: `today_dubai < reset_date` → skip tweets

### 6.2 Schedule Runner (`scripts/schedule_runner.py`)

**Purpose**: CLI runner for OS schedulers (launchd, systemd, cron).

**Usage**:
```bash
# Run all active profiles scheduled for today
python scripts/schedule_runner.py

# Run single profile (respects schedule_day)
python scripts/schedule_runner.py --profile-id 1

# Run all active profiles ignoring schedule_day
python scripts/schedule_runner.py --ignore-schedule
```

**Features**:
- Creates `runs` entries in database
- Captures stdout to `run_logs` table
- Visible in Admin UI run history

---

## 7. Admin UI

### 7.1 Overview

The Admin UI is a Flask web application built with **SAP Fiori Design System** for managing Legal Eagle configuration and monitoring runs.

**File**: `admin/app.py`  
**Port**: 8080 (default)  
**URL**: http://127.0.0.1:8080/admin  
**Design Version**: 2.1 (SAP Fiori)

### 7.2 SAP Fiori Design System

#### 7.2.1 Design Philosophy

Legal Eagle admin UI follows SAP Fiori design principles for a professional, enterprise-grade experience:
- **Consistent**: Unified look across all pages matching SAP Launchpad
- **Role-based**: Optimized for Localization Product Managers (LPMs)
- **Efficient**: Selection-based actions, no button repetition
- **Accessible**: Keyboard navigation, semantic HTML, proper focus states
- **Responsive**: Mobile-friendly layouts with adaptive breakpoints

#### 7.2.2 Color Palette

**CSS Variables** (defined in `base.html`):
```css
/* Brand Colors */
--sapBrandColor: #0a6ed1;        /* SAP Blue (primary actions) */
--sapHighlightColor: #0854a0;    /* Darker blue (hover states) */
--sapShellColor: #354a5f;        /* Dark blue-gray (shell bar) */

/* Background Colors */
--sapBackgroundColor: #f7f7f7;   /* Page background */
--sapTileBackground: #ffffff;    /* Card/tile background */
--sapBaseColor: #ffffff;         /* Base white */

/* Semantic Colors */
--sapPositiveColor: #107e3e;     /* Success/green */
--sapNegativeColor: #b00;        /* Error/red */
--sapCriticalColor: #e9730c;     /* Warning/orange */
--sapNeutralColor: #6a6d70;      /* Neutral/gray */

/* Text Colors */
--sapTextColor: #32363a;         /* Primary text */
--sapLinkColor: #0a6ed1;         /* Links */
```

**Usage**:
- **Blue**: Primary actions (Configure, Create, Update)
- **Green**: Success actions (Run, Add, Start)
- **Red**: Destructive actions (Delete, Clear)
- **Orange**: Warning actions (Cancel, Deactivate)
- **Gray**: Secondary/neutral actions

#### 7.2.3 Typography

**Font Family**: `"72", "72full", Arial, Helvetica, sans-serif`
- SAP's official font family with graceful fallbacks

**Size Scale**:
```css
--sapFontSmallSize: 0.75rem;    /* 12px - Buttons, labels */
--sapFontSize: 0.875rem;        /* 14px - Body text (Fiori standard) */
--sapFontLargeSize: 1rem;       /* 16px - Emphasized text */
--sapFontHeader3Size: 1.25rem;  /* 20px - Section headers */
--sapFontHeader2Size: 1.5rem;   /* 24px - Page headers */
--sapFontHeader1Size: 2rem;     /* 32px - Main headers */
```

**Line Height**: 1.4 (optimal for readability)

#### 7.2.4 Spacing System

**Base Unit**: 16px (1rem)

**Scale**:
```css
--sapSpacingXS: 0.25rem;   /* 4px - Tight spacing */
--sapSpacingS: 0.5rem;     /* 8px - Small gaps */
--sapSpacingM: 1rem;       /* 16px - Standard spacing */
--sapSpacingL: 1.5rem;     /* 24px - Large spacing */
--sapSpacingXL: 2rem;      /* 32px - Extra large spacing */
```

**Application**:
- Card padding: `--sapSpacingM` (16px)
- Section gaps: `--sapSpacingL` (24px)
- Button gaps: `--sapSpacingS` (8px)
- Form field margins: `--sapSpacingM` (16px)

#### 7.2.5 Components Library

**Shell Bar**:
```html
<header class="sapShellBar">
  <div class="sapShellBar-top">
    <!-- SAP logo, search, utilities -->
  </div>
  <div class="sapShellBar-subtitle">
    Legal Eagle - Compliance Management
  </div>
</header>
```
- Two-row design: Logo/search/icons + subtitle
- Fixed positioning with z-index: 1000
- 76px total height (44px + 32px)

**Cards**:
```html
<div class="sapCard">
  <div class="sapCard-header">Title</div>
  <div class="sapCard-content">Content</div>
</div>
```
- White background with subtle shadow
- 1px border (#d9d9d9)
- 0.25rem border radius

**Buttons**:
| Class | Style | Usage |
|-------|-------|-------|
| `.sapBtn-emphasized` | Blue, filled | Primary actions (Configure, Save) |
| `.sapBtn-accept` | Green, filled | Success actions (Run, Add, Start) |
| `.sapBtn-reject` | Red, filled | Destructive actions (Delete, Clear) |
| `.sapBtn-attention` | Orange, filled | Warning actions (Review, Cancel) |
| `.sapBtn-default` | Gray, outlined | Secondary actions (Create, Cancel) |
| `.sapBtn-transparent` | No background | Tertiary actions (Toggle) |
| `.sapBtn-sm` | Small size | Toolbar buttons (12px font) |

**Button Color Guidelines** (v2.1):
- **Configure** = Blue (`.sapBtn-emphasized`) - Primary configuration action
- **Run/Start** = Green (`.sapBtn-accept`) - Success/execution action
- **Review** = Orange (`.sapBtn-attention`) - Warning/review action
- **Create** = Gray (`.sapBtn-default`) - Secondary creation action
- **Delete/Clear** = Red (`.sapBtn-reject`) - Destructive action
- **Cancel** = Gray (`.sapBtn-default`) - Secondary cancel action

**Button Design Standards**:
- **No emoji icons**: Buttons use text-only labels without decorative icons
- **Clear labels**: Descriptive text like "Configure", "Delete Selected", "Save Schedule"
- **Semantic colors**: Button colors convey meaning (blue=primary, green=success, red=danger, orange=warning, gray=secondary)
- **Consistency**: Same actions use same colors across all pages
- **Accessibility**: Text-only buttons are screen-reader friendly
- **Example**: `<button class="sapBtn sapBtn-accept">Run</button>` (not "▶️ Run")

**Badges**:
```html
<span class="sapBadge sapBadge-positive">● Active</span>
<span class="sapBadge sapBadge-negative">✗ Failed</span>
<span class="sapBadge sapBadge-critical">⚠️ Warning</span>
<span class="sapBadge sapBadge-neutral">○ Inactive</span>
```

**Tables with Selection**:
```html
<div class="sapTable-toolbar">
  <button class="sapBtn sapBtn-emphasized sapBtn-sm">Configure</button>
  <button class="sapBtn sapBtn-accept sapBtn-sm">Run</button>
</div>
<table class="sapTable">
  <thead>
    <tr>
      <th class="sapTable-selection"></th>
      <th>Column 1</th>
    </tr>
  </thead>
  <tbody>
    <tr onclick="selectRow(this)">
      <td><input type="radio" name="selection"></td>
      <td>Data</td>
    </tr>
  </tbody>
</table>
```
- **Selection column**: 40px width, radio/checkbox
- **Toolbar**: Action buttons enabled/disabled by selection
- **No inline buttons**: Clean, scalable design

**Forms**:
```html
<div class="sapForm-group">
  <label class="sapForm-label">Field Label</label>
  <input class="sapForm-input" placeholder="...">
  <span class="sapForm-help">Help text</span>
</div>
```

**Message Strips**:
```html
<div class="sapMessageStrip sapMessageStrip-success">
  <span>Success message</span>
  <button class="sapMessageStrip-close">×</button>
</div>
```
Types: `success`, `error`, `warning`, `info`

#### 7.2.6 Selection-Based Action Pattern

**Fiori Standard**: Actions in toolbar, not repeated on every row.

**Before (Non-Fiori)**:
```
┌──────────────────────────────────────────────────────────┐
│ ID | Country | [Configure] [Run] [Review] [Toggle]     │ ← Repeated
│ 1  | SA      | [Configure] [Run] [Review] [Toggle]     │ ← Repeated
│ 2  | AE      | [Configure] [Run] [Review] [Toggle]     │ ← Repeated
└──────────────────────────────────────────────────────────┘
```

**After (Fiori)**:
```
┌──────────────────────────────────────────────────────────┐
│ [Configure] [Run] [Review] [Toggle]                      │ ← Toolbar
├──────────────────────────────────────────────────────────┤
│ ○ | ID | Country | LoB | Status                         │
│ ○ | 1  | SA      | HCM | ● Active                       │
│ ● | 2  | AE      | FIN | ● Active  ← Selected           │
└──────────────────────────────────────────────────────────┘
```

**Benefits**:
- Scalable with 2 or 200 records
- Cleaner visual hierarchy
- Reduced horizontal space usage
- Standard enterprise UX pattern

#### 7.2.7 Responsive Design

**Breakpoints**:
```css
@media (max-width: 768px) {
  .sapShellBar-center { display: none; }      /* Hide search */
  .sapContainer { padding: var(--sapSpacingM); } /* Reduce padding */
  .sapObjectPage-nav { flex-direction: column; } /* Stack nav */
  .sapGrid-2col { grid-template-columns: 1fr; } /* Single column */
  .sapSplitPanel { grid-template-columns: 1fr; } /* Stack panels */
}
```

**Mobile Optimizations**:
- Shell bar utilities remain visible
- Object page navigation stacks vertically
- Grid layouts become single column
- Tables scroll horizontally

### 7.3 Navigation

#### 7.3.1 Shell Bar

**SAP Fiori Shell Bar** (top of every page):
- **Row 1**: SAP logo (left) + Search (center) + Utilities (right)
- **Row 2**: "Legal Eagle - Compliance Management" subtitle
- **Color**: SAP Shell Blue (#354a5f)
- **Fixed positioning**: Always visible when scrolling

**Components**:
- ☰ **Menu button**: Returns to dashboard
- **Search**: Quick profile search (placeholder)
- 🔔 **Notifications**: Alert center (placeholder)
- 👤 **User**: User profile (placeholder)
- ⚙️ **Settings**: System settings (placeholder)

#### 7.3.2 Object Page Navigation

**Profile-specific navigation** (appears when profile is selected):
- Shows profile title: `SA/HCM - Default SA/HCM` with status badge
- Three tabs: **Configure**, **Run**, **Review**
- Each tab has semantic color when active:
  - **Configure** = Blue (primary configuration)
  - **Run** = Green (success/execution)
  - **Review** = Orange (warning/review)
- No icons in tab labels (clean text-only design)
- Hover states show the tab's semantic color
- Active tab has filled background with white text
- Consistent across all profile pages
- Responsive (stacks on mobile)

**Implementation**: Defined in `base.html`, rendered when `{% if profile %}` is true

### 7.4 Page Designs

#### 7.4.1 Dashboard (`dashboard.html`)

**Layout**: Single column (full width)

**Profiles Card**:
- **Card header** with profile count and "Create" button (top-right, emphasized/blue)
- **Selection-based toolbar** with action buttons
- Radio button selection (single selection)
- Columns: ID, Country, LoB, Name, Language, Status
- Clean rows without inline buttons
- Toolbar buttons: Configure, Run, Review, Toggle Active
- Empty state: Icon + message when no profiles

**Create Button Behavior**:
- Navigates to dedicated `/admin/profiles/create` page (GET)
- Follows Fiori pattern: list pages show data, create actions navigate to separate pages
- Button placement: Top-right in card header (standard Fiori action placement)

**Key Features**:
- Click anywhere on row to select it
- Toolbar buttons enable/disable based on selection
- Toggle button text changes based on selected profile status
- Clean separation: Dashboard for listing, dedicated page for creation

#### 7.4.2 Create Profile Page (`create_profile.html`)

**Layout**: Centered form (max-width: 600px)

**Components**:
1. **Breadcrumb Navigation**: Dashboard › Create Profile
2. **Page Header**: 
   - Title: "Create Profile"
   - Subtitle: "Set up a new monitoring profile for a country and line of business"
3. **Profile Configuration Card**:
   - Country (ISO alpha-2) - required field with datalist
   - Line of Business (HCM/FIN) - radio buttons with visual selection
   - Display Name - optional text input
   - Language - text input (default: "en")
4. **Form Actions**:
   - "Create Profile" button (emphasized/blue, full width)
   - "Cancel" button (default/gray, full width, returns to dashboard)
5. **Quick Start Guide Card**: 5-step onboarding instructions

**Key Features**:
- Dedicated page for profile creation (Fiori pattern)
- Auto-uppercase country code input
- Form validation with inline feedback
- Loading state on submit ("⏳ Creating Profile...")
- Enhanced radio button styling with hover/selection states
- Required field indicators (red asterisk)
- Cancel functionality returns to dashboard
- POST to existing `/admin/profiles/create` route
- After creation, redirects to profile detail page

**Navigation Flow**:
```
Dashboard → [Create Button] → Create Profile Page
                               ↓ [Submit]
                          Profile Detail Page (new profile)
                               
Create Profile Page → [Cancel Button] → Dashboard
```

#### 7.4.3 Profile Configuration (`profile.html`)

**Layout**: Single column with multiple cards

**Cards**:
1. **🗓️ Schedule**: Day of week selector with save button
2. **📡 RSS Feeds**: Selection table + add form
3. **🌐 URL Sources**: Editable table with inline form fields
4. **🐦 Twitter Accounts**: Selection table + add form + quota reset
5. **📧 Email Receivers**: Add form + selection table
6. **📖 Glossary**: Term items + add form + bulk add

**Pattern**:
- Each section is a Fiori card with header
- Tables have selection checkboxes + toolbar for bulk delete
- Add forms at bottom of each card
- Empty states with icons when no items
- Icon emojis for visual identification

#### 7.4.4 Run Status (`run_status.html`)

**Layout**: Split panel (320px / flexible)

**Left Panel**:
- **Run Controls Card**: Start/Cancel buttons, Clear history
- **History Card**: Compact table of last 7 days
  - Columns: ID, Status, Started
  - Status badges with icons (✓ ✗ ⏸ ⟳)
  - Clickable rows navigate to run logs

**Right Panel**:
- **Log Viewer Card**: Terminal-style dark theme
  - 500px height
  - Real-time streaming via SSE
  - Auto-scroll to bottom
  - Status badge in header

**Key Features**:
- Real-time log updates during execution
- Run history with semantic status colors
- Cancel button appears only when run is active
- Dark terminal aesthetic for logs

#### 7.4.5 Review News (`review_news.html`)

**Layout**: Single column with progressive disclosure

**Components**:
1. **Stat Cards** (3-column grid):
   - Total (gray border)
   - Pending Review (orange border)
   - Reviewed (green border)
   - Large numbers (3rem font)

2. **Segmented Buttons**: All / Pending / Reviewed filters

3. **Bulk Actions Card**:
   - Toolbar: Clear All, Clear Reviewed
   - Actions: Bulk Score, Apply, Select All, Delete Selected
   - Horizontal layout with flexbox

4. **News Items Table**:
   - Checkboxes for multi-selection
   - Columns: Source, Title/Content, Filter Reason, Score, Dates, Actions
   - Inline scoring dropdown + submit button
   - Inline delete button
   - Semantic badges for filter reasons

5. **Pagination**: Fiori-style with Previous/Next + page numbers

6. **Help Card**: Scoring guide + filter reasons

**Key Features**:
- Quick scoring with inline dropdown
- Bulk operations via selection
- Semantic color coding (badges)
- Link to glossary for improvement

### 7.3 Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/admin` | GET | Dashboard (list all profiles) |
| `/admin/profiles/create` | GET | Show create profile page (new in v2.1) |
| `/admin/profiles/create` | POST | Create new profile |
| `/admin/profiles/<id>` | GET | Profile detail/configuration |
| `/admin/profiles/<id>/toggle` | POST | Toggle active status |
| `/admin/profiles/<id>/runs` | GET | Run page (history + live logs) |
| `/admin/profiles/<id>/runs/start` | POST | Start a new run |
| `/admin/profiles/<id>/review` | GET | Review filtered news |
| `/admin/profiles/<id>/news/clear` | POST | Clear historical news baseline |
| `/admin/runs/<id>/stream` | GET | SSE stream for live logs |
| `/admin/runs/<id>/cancel` | POST | Request run cancellation |

### 7.3 Templates

| Template | Purpose |
|----------|---------|
| `base.html` | Base layout with SAP Fiori shell bar and navigation |
| `dashboard.html` | Profile list with selection-based toolbar (v2.1: single column) |
| `create_profile.html` | Dedicated profile creation page (new in v2.1) |
| `profile.html` | Profile configuration (sources, glossary, etc.) |
| `run_status.html` | Run execution and history with live log streaming |
| `review_news.html` | Filtered news review interface |

### 7.4 Live Log Streaming

- Uses Server-Sent Events (SSE)
- Endpoint: `/admin/runs/<id>/stream`
- Polls `run_logs` table every 750ms
- Sends `done` event when run completes

### 7.5 Run Execution

1. User clicks "Confirm Run"
2. Server creates `runs` entry with status `Queued`
3. Background thread starts:
   - Updates status to `Running`
   - Redirects stdout to `_DBLogger` (writes to `run_logs`)
   - Calls `run_profile_once(profile_id)`
   - Updates status to `Success`/`Failed`/`Canceled`
4. Frontend streams logs via SSE

---

## 8. Configuration

### 8.1 Environment Variables

**Required**:
| Variable | Description |
|----------|-------------|
| `LEGAL_EAGLE_OPENAI_API_KEY` | OpenAI API key |
| `LEGAL_EAGLE_TWITTER_BEARER_TOKEN` | Twitter/X API bearer token |
| `LEGAL_EAGLE_GMAIL_EMAIL_SENDER` | Gmail sender address |
| `LEGAL_EAGLE_GMAIL_APP_PASSWORD` | Gmail App Password |

**Optional**:
| Variable | Default | Description |
|----------|---------|-------------|
| `LEGAL_EAGLE_MAX_NEWS_AGE_DAYS` | `7` | Max age of news in days |
| `LEGAL_EAGLE_OPENAI_TIMEOUT` | `60` | OpenAI API timeout (seconds) |
| `LEGAL_EAGLE_OPENAI_BASE_URL` | - | Custom OpenAI base URL |
| `LEGAL_EAGLE_EMBEDDINGS_RETRIES` | `2` | Embedding retry count |
| `LEGAL_EAGLE_EMBEDDINGS_BACKOFF` | `1.0` | Embedding retry backoff (seconds) |
| `LEGAL_EAGLE_RENDER_TIMEOUT_MS` | `60000` | Playwright render timeout |
| `LEGAL_EAGLE_DETAIL_TIMEOUT_MS` | `60000` | Detail page fetch timeout |
| `DISABLE_TWEETS` | - | Set to disable tweet collection |

**Gmail OAuth (optional, not required for App Password)**:
| Variable | Description |
|----------|-------------|
| `LEGAL_EAGLE_GMAIL_CLIENT_ID` | OAuth client ID |
| `LEGAL_EAGLE_GMAIL_CLIENT_SECRET` | OAuth client secret |
| `LEGAL_EAGLE_GMAIL_REFRESH_TOKEN` | OAuth refresh token |
| `LEGAL_EAGLE_GMAIL_SCOPE` | OAuth scope |
| `LEGAL_EAGLE_GMAIL_TOKEN_URI` | OAuth token URI |

### 8.2 Configuration Loader (`configurations/config_loader.py`)

**Key Functions**:
```python
# Profile management
list_active_profiles() -> List[Dict]
resolve_profile(country_code, lob) -> Optional[int]

# Per-profile configuration
load_language(profile_id) -> str
load_rss_feeds(profile_id) -> List[str]
load_tweet_accounts(profile_id) -> List[str]
load_url_sources(profile_id) -> List[Dict]
load_email_receivers(profile_id) -> List[str]
load_glossary(profile_id) -> Dict

# Settings
get_setting_value(profile_id, key, default) -> Optional[str]
set_setting_value(profile_id, key, value) -> None

# News baseline
add_news_item(profile_id, item) -> int
get_weekly_baseline(profile_id, days) -> List[Dict]
get_reviewed_baseline(profile_id, min_score) -> List[Dict]

# Global credentials
load_global_credentials() -> Dict
```

---

## 9. Data Flow

### 9.1 Provenance Tracking

Each news item carries a `source_type` field that tracks its origin:

| source_type | Set By | Description |
|-------------|--------|-------------|
| `RSS` | `rss_parser.py` | Items from RSS/Atom feeds |
| `Tweet` | `tweet_feed.py` | Items from Twitter/X timeline |
| `URL_Static` | `url_sources_runner.py` | Items from static HTTP scraping |
| `URL_Dynamic` | `url_sources_runner.py` | Items from Playwright rendering |

**Enforcement**: `compare_news.py` validates that `source_type` is one of the allowed values; no fallback inference.

### 9.2 Pipeline Execution Order

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE EXECUTION ORDER                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. COLLECTION (parallel-capable, currently sequential)         │
│     ├── RSS Parser ──────────────▶ rss_items[]                  │
│     ├── Tweet Feed ──────────────▶ tweet_items[]                │
│     └── URL Sources Runner ──────▶ url_items[]                  │
│                                                                  │
│  2. MERGE                                                        │
│     └── all_news_items = rss + tweets + urls                    │
│                                                                  │
│  3. FILTER (before comparison for efficiency)                   │
│     ├── Load high-score baseline from filtered_news             │
│     ├── Age gate (7 days)                                       │
│     ├── Semantic check (GPT-4o-mini)                            │
│     ├── Rescue check (embeddings vs baseline)                   │
│     └── Save filtered items to filtered_news table              │
│                                                                  │
│  4. COMPARE (only relevant items)                               │
│     ├── Load weekly baseline from news_items                    │
│     ├── Persist current items to news_items                     │
│     ├── Exact match deduplication                               │
│     ├── Semantic deduplication (embeddings)                     │
│     ├── Update detection (cosine + Jaccard)                     │
│     └── Delta extraction for updates                            │
│                                                                  │
│  5. GROUP                                                        │
│     └── AI-powered topic grouping (GPT-4o-mini)                 │
│                                                                  │
│  6. EMAIL                                                        │
│     └── Send HTML digest via Gmail SMTP                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. API Reference

### 10.1 Database Helpers (`configurations/db.py`)

**Connection**:
```python
get_connection(db_path: str = None) -> sqlite3.Connection
create_schema_if_needed(conn: sqlite3.Connection) -> None
```

**Profiles**:
```python
list_profiles(conn, active_only: bool = True) -> List[sqlite3.Row]
get_profile(conn, country_code: str, lob: str) -> Optional[sqlite3.Row]
create_profile(conn, country_code, lob, name, language, active) -> int
```

**Sources**:
```python
list_rss_feeds(conn, profile_id: int) -> List[str]
list_tweet_accounts(conn, profile_id: int) -> List[str]
list_url_sources(conn, profile_id: int) -> List[Dict]
list_email_receivers(conn, profile_id: int) -> List[str]

upsert_rss_feed(conn, profile_id: int, url: str) -> None
upsert_tweet_account(conn, profile_id: int, handle: str) -> None
upsert_url_source(conn, profile_id, url, mode, sample_link, read_more_label, crawl_version) -> None
upsert_email_receiver(conn, profile_id: int, email: str) -> None
```

**Glossary**:
```python
list_glossary_terms(conn, profile_id: int) -> List[Dict]
add_glossary_term(conn, profile_id, term, lang, category, product, weight, notes) -> int
add_glossary_synonym(conn, term_id: int, synonym: str) -> None
add_glossary_pattern(conn, term_id: int, regex: str) -> None
flatten_glossary_for_prompt(glossary_rows: List[Dict]) -> Dict
```

**News Baseline**:
```python
upsert_news_item(conn, profile_id: int, item: Dict) -> int
update_last_seen(conn, news_id: int) -> None
list_baseline_items(conn, profile_id: int, days: int = 7) -> List[Dict]
```

**Filtered News**:
```python
insert_filtered_news(conn, profile_id, item, filter_reason, run_id) -> int
list_filtered_news(conn, profile_id, reviewed, limit, offset) -> List[Dict]
count_filtered_news(conn, profile_id, reviewed) -> int
update_filtered_news_score(conn, item_id: int, relevance_score: int) -> None
delete_filtered_news(conn, item_id: int) -> None
clear_filtered_news(conn, profile_id, reviewed_only: bool) -> int
get_reviewed_news_baseline(conn, profile_id, min_score: int = 4) -> List[Dict]
```

**Runs & Logs**:
```python
create_run(conn, profile_id: int, origin: str = "manual") -> int
start_run(conn, run_id: int) -> None
finish_run(conn, run_id: int, status: str, metrics: Dict = None) -> None
append_run_log(conn, run_id: int, level: str, line: str) -> int
list_runs_for_profile(conn, profile_id: int, limit: int = 30) -> List[Dict]
get_run(conn, run_id: int) -> Optional[Dict]
list_run_logs(conn, run_id: int, after_seq: int = None, limit: int = 1000) -> List[Dict]
set_cancel_requested(conn, run_id: int) -> None
is_cancel_requested(conn, run_id: int) -> bool
prune_old_runs(conn, days: int = 7) -> None
```

**Audit**:
```python
add_audit_log(conn, entity: str, action: str, details: str = None, profile_id: int = None) -> None
```

---

## 11. File Structure

```
legal-eagle/
├── admin/                          # Flask Admin UI
│   ├── app.py                      # Main Flask application (routes, SSE, run execution)
│   ├── outputs/                    # Admin-specific outputs (if any)
│   └── templates/                  # Jinja2 HTML templates
│       ├── base.html               # Base layout
│       ├── dashboard.html          # Profile list
│       ├── profile.html            # Profile configuration
│       ├── run_status.html         # Run execution & history
│       └── review_news.html        # Filtered news review
│
├── agents/                         # Processing pipeline agents
│   ├── __init__.py
│   ├── agents_controller.py        # Main orchestrator
│   ├── rss_parser.py               # RSS/Atom feed collection
│   ├── tweet_feed.py               # Twitter/X timeline collection
│   ├── url_sources_runner.py       # Website scraping (static/dynamic)
│   ├── news_filter.py              # AI relevance filtering
│   ├── compare_news.py             # Deduplication & update detection
│   ├── news_grouper.py             # AI topic grouping
│   ├── email_sender.py             # Gmail SMTP delivery
│   └── text_utils.py               # Text normalization utilities
│
├── configurations/                 # Configuration and database
│   ├── __init__.py
│   ├── config_loader.py            # High-level configuration API
│   ├── db.py                       # SQLite database helpers
│   ├── env_loader.py               # Environment variable loading
│   ├── config.db                   # SQLite database (gitignored)
│   └── requirements.txt            # Python dependencies
│
├── scripts/                        # Utilities and schedulers
│   ├── schedule_runner.py          # CLI runner for OS schedulers
│   ├── scheduler_entry.sh          # Shell wrapper for schedulers
│   ├── migrate_config_to_sqlite.py # Initial DB seeding
│   ├── migrate_env_to_sqlite.py    # Environment migration
│   ├── launchd/                    # macOS launchd templates
│   │   └── legal.eagle.scheduler.plist
│   ├── systemd/                    # Linux systemd templates
│   │   ├── legal-eagle.service
│   │   └── legal-eagle.timer
│   └── test_runs/                  # Test output directory (gitignored)
│
├── outputs/                        # Generated output files
│   └── {country}_{lob}/            # Per-profile outputs
│       └── all_news.json           # Rolling news snapshot
│
├── snapshots/                      # Dynamic rendering snapshots (gitignored)
│   └── {country}_{lob}/
│       └── snap_output_YYYY-MM-DD.json
│
├── archive/                        # Archived/deprecated modules
│
├── memory-bank/                    # Project context files
│
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignore rules
├── README.md                       # User guide (LPMs/PMs)
├── SPEC.md                         # Technical specification (this file)
├── CHANGELOG.md                    # Version history
└── run_local_tests.sh              # Local development script
```

---

## 12. Outputs & Artifacts

### 12.1 Per-Profile Outputs

| Path | Description |
|------|-------------|
| `outputs/{country}_{lob}/all_news.json` | Rolling snapshot of all collected news |

**Naming Convention**: ISO-2 country code + underscore + LoB (e.g., `SA_HCM`, `AE_FIN`)

### 12.2 Snapshots

| Path | Description |
|------|-------------|
| `snapshots/{country}_{lob}/snap_output_YYYY-MM-DD.json` | Daily snapshot from dynamic rendering |

**Retention**: Keep last 30 daily snapshots per profile.

### 12.3 Database

| Path | Description |
|------|-------------|
| `configurations/config.db` | SQLite database (gitignored) |

**Contains**: Profiles, sources, glossary, news baseline, runs, logs, audit trail.

### 12.4 Logs

| Location | Description |
|----------|-------------|
| `runs` table | Run execution history |
| `run_logs` table | Per-run log lines (for live streaming) |
| `outputs/launchd-stdout.log` | macOS launchd stdout (if configured) |
| `outputs/launchd-stderr.log` | macOS launchd stderr (if configured) |

---

## Appendix A: Glossary of Terms

| Term | Definition |
|------|------------|
| **Profile** | A Country + LoB combination with isolated configuration |
| **LoB** | Line of Business (HCM or FIN) |
| **HCM** | Human Capital Management (HR, Payroll, Benefits) |
| **FIN** | Finance (Tax, E-Invoicing, Accounting) |
| **LPM** | Localization Product Manager |
| **Baseline** | Rolling 7-day window of previously seen news items |
| **Rescue** | "Second chance" mechanism for items similar to high-scored reviewed items |
| **Delta** | Meaningful changes detected between an update and its baseline version |

---

## Appendix B: Troubleshooting

### B.1 Common Issues

| Issue | Solution |
|-------|----------|
| Twitter 429 Too Many Requests | Wait for rate limit reset; check X-Rate-Limit headers |
| Playwright timeouts | Increase `LEGAL_EAGLE_RENDER_TIMEOUT_MS`; check site availability |
| OpenAI API errors | Check API key; increase `LEGAL_EAGLE_OPENAI_TIMEOUT` |
| Empty email digest | Check filter settings; review filtered_news for false negatives |
| No active profiles | Run migration script or create profile in Admin UI |

### B.2 Debug Mode

Enable verbose logging by setting environment variables:
```bash
export LEGAL_EAGLE_DEBUG=1
```

### B.3 Database Reset

To reset the database and start fresh:
```bash
rm configurations/config.db
python scripts/migrate_config_to_sqlite.py
```

---

*End of Technical Specification*
