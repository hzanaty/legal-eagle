# Legal Eagle 2.0

**AI-powered regulatory compliance monitoring for SAP Localization**

Legal Eagle automatically monitors government sources for legal and regulatory changes, evaluates their impact on SAP localized products, and delivers daily actionable digests to Localization Product Managers (LPMs).

---

## 🎯 The Why

Localization Product Managers face a constant challenge: staying on top of legal and regulatory changes across multiple countries and domains. Manual monitoring is:

- **Time-consuming**: Checking dozens of government websites, RSS feeds, and social media accounts daily
- **Error-prone**: Easy to miss critical updates buried in lengthy documents
- **Language barriers**: Many sources publish in local languages only
- **Inconsistent**: Different team members may interpret relevance differently

**Legal Eagle solves this** by providing an automated, AI-powered monitoring system that:

- ✅ Continuously scans authoritative sources (government websites, RSS feeds, Twitter/X)
- ✅ Uses AI to understand the *meaning* of content, not just keywords
- ✅ Filters for genuine legal relevance to HR/Payroll (HCM) or Finance (FIN) domains
- ✅ Detects both new regulations and updates to existing ones
- ✅ Delivers a concise, actionable daily email digest

---

## 🔍 What It Does

Legal Eagle monitors regulatory changes for a specific **Country** and **Line of Business (LoB)**:

| LoB | Focus Areas |
|-----|-------------|
| **HCM** | HR, Payroll, Social Insurance, Labor Law, Pensions, Benefits |
| **FIN** | Tax, E-Invoicing, Financial Reporting, Accounting Standards |

### Supported Source Types

| Source | Description |
|--------|-------------|
| **RSS Feeds** | Government news feeds, ministry announcements |
| **Twitter/X** | Official government and ministry accounts |
| **Websites** | Dynamic government portals (rendered with headless browser) |

### Output

A daily email digest containing:
- 📰 **New** legal changes detected
- 🔄 **Updates** to previously reported items (with change highlights)
- 🏷️ Grouped by topic for easy scanning
- 🔗 Direct links to source documents

---

## ⚙️ How It Works

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LEGAL EAGLE PIPELINE                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────┐   ┌─────────┐   ┌─────────┐                              │
│   │   RSS   │   │ Twitter │   │ Website │   ← Data Sources             │
│   └────┬────┘   └────┬────┘   └────┬────┘                              │
│        │             │             │                                    │
│        └─────────────┼─────────────┘                                    │
│                      ▼                                                  │
│              ┌───────────────┐                                          │
│              │   COLLECT     │  ← Gather all news items                 │
│              └───────┬───────┘                                          │
│                      ▼                                                  │
│              ┌───────────────┐                                          │
│              │    FILTER     │  ← AI semantic relevance check           │
│              └───────┬───────┘                                          │
│                      ▼                                                  │
│              ┌───────────────┐                                          │
│              │   COMPARE     │  ← Deduplicate + detect updates          │
│              └───────┬───────┘                                          │
│                      ▼                                                  │
│              ┌───────────────┐                                          │
│              │    GROUP      │  ← AI-powered topic grouping             │
│              └───────┬───────┘                                          │
│                      ▼                                                  │
│              ┌───────────────┐                                          │
│              │    EMAIL      │  ← Send daily digest                     │
│              └───────────────┘                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Multi-Profile Support

Legal Eagle supports multiple **profiles**, each representing a Country + LoB combination:

- `SA/HCM` — Saudi Arabia, HR & Payroll
- `AE/FIN` — UAE, Finance
- `DE/HCM` — Germany, HR & Payroll

Each profile has its own:
- Data sources (RSS feeds, Twitter accounts, websites)
- Glossary of relevant terms
- Email recipients
- Schedule (which day of the week to run)

---

## ✨ Key Features

### 🧠 AI-Powered Semantic Filtering
Unlike keyword-based systems, Legal Eagle uses GPT-4o-mini to understand the *meaning* of content. It can:
- Match Arabic news against English glossary terms
- Distinguish between genuinely relevant legal changes and tangentially related news
- Filter out general politics, diplomacy, and trade news

### 🔄 Smart Deduplication
Uses embeddings (text-embedding-3-small) to:
- Detect duplicate news from different sources
- Identify updates to previously reported items
- Extract and highlight what changed

### 📋 Human-in-the-Loop Feedback
The **Review News** feature allows LPMs to:
- Score filtered-out items (1-5 relevance)
- High-scored items become a "rescue baseline" for future filtering
- Continuously improves accuracy over time

### 🖥️ Web-Based Admin UI
A Flask-based dashboard for:
- Managing profiles and sources
- Running jobs manually with live log streaming
- Reviewing filtered news
- Monitoring run history

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **API Keys**:
  - OpenAI API key (for GPT-4o-mini and embeddings)
  - Twitter/X Bearer Token (for timeline access)
  - Gmail App Password (for sending emails)

### Quick Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/hzanaty/legal-eagle.git
   cd legal-eagle
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Install dependencies**
   ```bash
   pip install -r configurations/requirements.txt
   playwright install chromium
   ```

4. **Initialize the database**
   ```bash
   python scripts/migrate_config_to_sqlite.py
   ```

5. **Start the Admin UI**
   ```bash
   python admin/app.py
   ```
   Open http://127.0.0.1:8080/admin in your browser.

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
LEGAL_EAGLE_OPENAI_API_KEY=sk-...
LEGAL_EAGLE_TWITTER_BEARER_TOKEN=AAAAAAAA...
LEGAL_EAGLE_GMAIL_EMAIL_SENDER=your-email@gmail.com
LEGAL_EAGLE_GMAIL_APP_PASSWORD=your-app-password

# Optional (for Gmail OAuth - not required for App Password)
LEGAL_EAGLE_GMAIL_CLIENT_ID=
LEGAL_EAGLE_GMAIL_CLIENT_SECRET=
LEGAL_EAGLE_GMAIL_REFRESH_TOKEN=
```

---

## 🖥️ Admin UI Guide

### Dashboard

The main dashboard shows all configured profiles with their status:
- **Active/Inactive** toggle
- **Run** button to execute immediately
- **Create Profile** to add new Country/LoB combinations

### Profile Configuration

Each profile page allows you to configure:

| Section | Description |
|---------|-------------|
| **Schedule** | Day of week to run (or Unset to skip) |
| **RSS Feeds** | URLs of RSS/Atom feeds to monitor |
| **URL Sources** | Websites to scrape (static or dynamic) |
| **Twitter Accounts** | @handles to monitor |
| **Email Receivers** | Recipients for the daily digest |
| **Glossary** | Terms that define relevance for this LoB |

### URL Sources Configuration

For each website, you can configure:
- **Mode**: `auto` (try static, fallback to dynamic), `force_static`, or `force_dynamic`
- **Sample Link**: An example detail page URL to help derive the URL pattern
- **Read More Label**: Text of the "read more" button (for dynamic sites)

### Running Jobs

1. Navigate to a profile's **Run** page
2. Click **Confirm Run**
3. Watch live logs stream in the right panel
4. View run history and past logs

### Reviewing Filtered News

The **Review News** page shows items that were filtered out:
1. Score each item 1-5 based on actual relevance
2. Items scored 4-5 become part of the "rescue baseline"
3. Future similar items will be rescued from filtering

---

## 🌐 Deployment Options

### Local Development

Run the Admin UI locally:
```bash
python admin/app.py
```

### GitHub Actions (Automated Daily Runs)

1. **Configure Repository Secrets**
   
   Go to your repository → Settings → Secrets and variables → Actions → New repository secret
   
   Add these secrets:
   - `LEGAL_EAGLE_OPENAI_API_KEY`
   - `LEGAL_EAGLE_TWITTER_BEARER_TOKEN`
   - `LEGAL_EAGLE_GMAIL_EMAIL_SENDER`
   - `LEGAL_EAGLE_GMAIL_APP_PASSWORD`

2. **Create Workflow File**
   
   Create `.github/workflows/daily-run.yml`:
   ```yaml
   name: Legal Eagle Daily Run
   on:
     schedule:
       - cron: '0 3 * * *'  # 3 AM UTC daily
     workflow_dispatch:  # Manual trigger
   
   jobs:
     run:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: '3.11'
         - name: Install dependencies
           run: |
             pip install -r configurations/requirements.txt
             playwright install chromium
         - name: Initialize DB
           run: python scripts/migrate_config_to_sqlite.py
         - name: Run Legal Eagle
           env:
             LEGAL_EAGLE_OPENAI_API_KEY: ${{ secrets.LEGAL_EAGLE_OPENAI_API_KEY }}
             LEGAL_EAGLE_TWITTER_BEARER_TOKEN: ${{ secrets.LEGAL_EAGLE_TWITTER_BEARER_TOKEN }}
             LEGAL_EAGLE_GMAIL_EMAIL_SENDER: ${{ secrets.LEGAL_EAGLE_GMAIL_EMAIL_SENDER }}
             LEGAL_EAGLE_GMAIL_APP_PASSWORD: ${{ secrets.LEGAL_EAGLE_GMAIL_APP_PASSWORD }}
           run: python scripts/schedule_runner.py --ignore-schedule
   ```

### Hosting the Admin UI

For persistent Admin UI access, you can deploy the Flask app:

**Option 1: Local Server (macOS/Linux)**
```bash
# Using launchd (macOS) or systemd (Linux)
# See scripts/launchd/ and scripts/systemd/ for templates
```

**Option 2: Cloud Hosting**
- Deploy to any Python-compatible platform (Heroku, Railway, Render, etc.)
- Set environment variables in the platform's dashboard
- The SQLite database will be created automatically

**Option 3: Docker** (coming soon)

---

## 📁 Project Structure

```
legal-eagle/
├── admin/                    # Flask Admin UI
│   ├── app.py               # Main Flask application
│   └── templates/           # HTML templates
├── agents/                   # Processing pipeline agents
│   ├── agents_controller.py # Main orchestrator
│   ├── rss_parser.py        # RSS feed collection
│   ├── tweet_feed.py        # Twitter/X collection
│   ├── url_sources_runner.py# Website scraping
│   ├── news_filter.py       # AI relevance filtering
│   ├── compare_news.py      # Deduplication & updates
│   ├── news_grouper.py      # Topic grouping
│   └── email_sender.py      # Email delivery
├── configurations/           # Config and database
│   ├── config_loader.py     # Configuration API
│   ├── db.py                # SQLite helpers
│   └── requirements.txt     # Python dependencies
├── scripts/                  # Utilities and schedulers
│   ├── schedule_runner.py   # CLI runner for scheduling
│   ├── migrate_config_to_sqlite.py
│   └── launchd/, systemd/   # OS scheduler templates
├── outputs/                  # Generated output files
├── .env.example             # Environment template
├── README.md                # This file
└── SPEC.md                  # Technical specification
```

---

## 📖 Documentation

- **README.md** (this file) — Project overview and user guide
- **[SPEC.md](SPEC.md)** — Technical specification for developers

---

## 🤝 Support & Feedback

For issues, questions, or feature requests:
- Open an issue on GitHub
- Contact the SAP Globalization team

---

## 📜 License

Proprietary — Internal SAP project.
