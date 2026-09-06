# Legal Eagle

**From Regulatory Intelligence to Virtual Localization Product Manager**

> AI-powered platform that monitors legal changes, interprets their meaning, and helps SAP Localization teams respond faster with higher intelligence.

**Current version: v3.7** — Deprecate Legal Repository · [CHANGELOG](CHANGELOG.md)

---

## 🎯 The Vision

Legal Eagle is evolving through strategic stages to become a complete **Localization Intelligence Platform**:

**Stage 1: Journalist** → **Stage 2: Lawyer** → **Stage 3: SAP Consultant** → **Stage 4: Virtual LPM** → **Stage 5: Executive Advisor**

Starting from a solid foundation as a Regulatory Intelligence Engine, Legal Eagle will progressively gain the ability to not just report legal changes, but interpret them, connect them to SAP systems, and ultimately assist LPMs like a virtual team member.

This isn't a future dream—**Stage 1 is operational today**. Each subsequent stage builds on this working foundation through modular expansion, not rewrites.

📄 **Full Strategic Vision**: See [Big_Picture.md](Big_Picture.md) for the complete evolution roadmap

---

## ✅ Current Status: Stage 1 — Journalist (Ready Now)

Legal Eagle Core is **operational today** as a Regulatory Intelligence Engine, monitoring legal and regulatory changes across multiple countries and delivering actionable intelligence to Localization Product Managers.

### What It Does

Legal Eagle automatically:
- 🔍 **Monitors** government sources, official gazettes, RSS feeds, and social media
- 🤖 **Filters** using AI semantic understanding (not keyword matching)
- 🔄 **Detects** both new regulations and updates to existing ones
- 📊 **Groups** related changes by theme for easy scanning
- 📧 **Delivers** daily actionable digests with direct links to sources
- 🗄️ **Maintains** searchable historical intelligence baseline

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **Multi-Source Collection** | RSS feeds, Twitter/X, government websites (static + dynamic), email monitoring |
| **AI-Powered Filtering** | SAP AI Core (GPT-4o) semantic relevance evaluation |
| **Smart Deduplication** | Detects duplicate news and updates to previously reported items; REPEATED tag for persistent signals |
| **Three-Tier Ranking Engine** | Deterministic rules (Tier 1) + GPT-4o AI scoring (Tier 2); 1=Noise → 5=Urgent; REPEATED tag elevates rank for recurring topics |
| **Source Attribution** | Publisher + Authority stamped per item from feed config; AI inference for unconfigured feeds; ✦ icon + manual override UI |
| **Intelligent Grouping** | AI clusters related news by regulatory theme (replaced by keyword tagging, shipped v3.3) |
| **Multi-Profile Support** | Country + Line of Business combinations (SA/HCM, TR/HCM, ES/HCM, GR/HCM, etc.) |
| **Bilingual Digests** | Native language + English translation in single email |
| **Human-in-the-Loop** | Review/score workflow continuously improves accuracy |
| **Specialized Scrapers** | Custom support for Turkey Official Gazette, Saudi GOSI, and more |
| **Legal Repository** | ~~Global knowledge base linking regulations → SAP delivery artifacts~~ — *deprecated v3.7* |
| **Test Harness** | Deterministic integration tests (XN/HCM imaginary profile, localhost fixture server, AI cache replay) |
| **BTP Email via ANS** | SAP Alert Notification Service handles outbound email on BTP Cloud Foundry *(disabled — re-enable on next BTP deployment)* |

### Supported Regions & Domains

| Line of Business | Focus Areas |
|------------------|-------------|
| **HCM** | HR, Payroll, Social Insurance, Labor Law, Pensions, Benefits |
| **FIN** | Tax, E-Invoicing, Financial Reporting, Accounting Standards |

**Current Deployments**: Saudi Arabia, Turkey, Spain, UAE, Greece (more countries being added)

📋 **Technical Details**: See [SPEC.md](SPEC.md) for complete technical architecture

---

## 🗺️ Evolution Roadmap

### Stage 2 — Lawyer (Next)

Build **Legal Analyzer** capability to interpret legal text:
- Explain what changed vs previous wording
- Identify linked articles and dependencies
- Detect obligations, penalties, exceptions
- Translate legal language into business meaning

**Strategic Importance**: Bridges the gap between raw legal text and business/system impact.

---

### Stage 3 — SAP Consultant

Build **Taxonomy MCP integration** to translate legal changes into SAP solution impact:
- Map legal changes to affected SAP products (HCM, Payroll, SuccessFactors, S/4HANA)
- Identify impacted SAP objects, processes, and functional areas
- Determine if changes require standard configuration or custom enhancement
- Generate draft PRD outlines for implementation
- Provide business-term-to-SAP-object mapping

**Strategic Importance**: Bridges the gap between legal interpretation and implementable SAP requirements. Answers "What SAP systems are affected and how?"

---

### Stage 4 — Smart Legal Eagle MCP

Upgrade to **MCP protocol** with analyzer-powered services:
- `latest_news()` - Recent regulatory updates
- `daily_digest()` - Summarized intelligence
- `search_news()` - Historical search
- `analyze_article()` - Deep legal interpretation
- `explain_change()` - Change impact analysis
- `compare_old_new()` - Article comparison

---

### Stage 5 — Virtual LPM (Orchestrator)

Connect **external enterprise capabilities** into Legal Eagle:
- **LOKA** (JIRA / RCM / historical changes / documentation)
- **Taxonomy** (SAP functional area mapping)
- **Documentation repositories**
- **Future MCP servers and APIs**

**Intelligent Flow Example**:
1. Detect new legal change
2. Interpret it using Legal Analyzer
3. Search precedents in LOKA
4. Map SAP impact through Taxonomy
5. Return structured LPM briefing

**Strategic Role**: Behaves like a **Virtual Localization Product Manager** assisting human LPMs.

---

### Stage 6 — Executive Advisor

Future **management-oriented capabilities**:
- Prioritize legal changes by urgency and impact
- Estimate delivery complexity
- Suggest JIRA requirement drafts
- Suggest RCM entry drafts
- Cross-country compliance dashboards
- Readiness and risk reporting

---

## 🔧 Platform Modernization

### UI5/Fiori Migration

**Status**: Planned  
**Approach**: Hybrid Architecture (Flask + SAPUI5)

Transform the current Flask/Jinja2 admin UI to a modern SAPUI5 application while keeping the Python backend intact.

**Key Benefits**:
- True SAP Fiori user experience with native UI5 controls
- Modern, responsive design with SAP design system
- Better integration with SAP ecosystem
- Improved maintainability and developer experience

**Timeline**: 5-week migration with page-by-page incremental approach

📄 **Migration Plan**: See [UI5_MIGRATION_ROADMAP.md](UI5_MIGRATION_ROADMAP.md)

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **API Keys / Credentials**:
  - SAP AI Core credentials (for AI filtering, grouping, translation)
  - Twitter/X Bearer Token (for social media monitoring)
  - Gmail App Password (for sending email digests)

### Quick Setup

1. **Clone the repository**
   ```bash
   git clone https://github.tools.sap/I077750/legal-eagle.git
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
# SAP AI Core (required for AI filtering, grouping, translation)
LEGAL_EAGLE_SAP_AICORE_BASE_URL=https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com
LEGAL_EAGLE_SAP_AICORE_AUTH_URL=https://auth.ai.prod.eu-central-1.aws.ml.hana.ondemand.com/oauth/token
LEGAL_EAGLE_SAP_AICORE_CLIENT_ID=<client-id>
LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET=<client-secret>
LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID=<deployment-id>
LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID=<deployment-id>

# Twitter/X (required for social media monitoring)
LEGAL_EAGLE_TWITTER_BEARER_TOKEN=<bearer-token>

# Gmail (required for sending email digests)
LEGAL_EAGLE_GMAIL_EMAIL=<gmail-address>
LEGAL_EAGLE_GMAIL_APP_PASSWORD=<app-password>
```

---

## 🖥️ Admin UI Overview

### Dashboard
- View all configured profiles (Country + LoB combinations)
- Quick access to run executions and configuration
- Status indicators for active/inactive profiles

### Profile Configuration
Each profile allows you to configure:
- **Data Sources**: RSS feeds, Twitter accounts, government websites
- **Default Lookback Window**: How far back to collect per run (Delta / Today / 7 days / 30 days)
- **Email Recipients**: LPMs who receive daily digests
- **Glossary**: Domain-specific terms for relevance filtering
- **Monitor Settings**: Email inbox monitoring for Law-to-Spec updates

### Run Execution
- Manual execution with live log streaming
- **Stage visualization**: 7-stage checklist with live state icons and per-stage status summaries
- **Source breakdown**: Collecting stage shows individual RSS feeds, Twitter @handles, and URL sources as clickable sub-items
- **Run Options**: Per-run overrides for lookback window, skip comparison/filtering/grouping, test mode
- View run history and metrics
- Cancel running executions cooperatively

### Review Filtered News
- Score filtered-out items for continuous improvement
- Approve items to add to baseline
- High-scored items become "rescue baseline" for future filtering
- **Auto-translate**: non-English profiles show items translated to English inline
- **L2S Prompt**: create Legal Repository node directly from a news item

### Legal Repository
- Global knowledge base at `/admin/legal-repo`
- Three-column layout: countries → topic tree → node detail
- Track regulations through lifecycle: NEW → SCOPING → ANALYZED → COMPLETE
- Link SAP delivery artifacts per node: JIRA EPICs/Reqs, SAP Notes, PRDs, MindMaps
- Full traceability from news item → repo node → SAP delivery

---

## ⚙️ How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     LEGAL EAGLE PIPELINE                         │
└─────────────────────────────────────────────────────────────────┘

1. COLLECT
   ├─> RSS Feeds (government announcements)
   ├─> Twitter/X (official accounts)
   ├─> Websites (static + dynamic with Playwright)
   └─> Email Inbox (Law-to-Spec monitoring)

2. ATTRIBUTE
   └─> Publisher + Authority stamped from feed config or AI inference

3. COMPARE (Deduplication)
   └─> Match against baseline
       Detect: new items, updated items, repeated (×3+), duplicates

4. RANK
   └─> Three-tier engine: Tier 0 duplicate (rank 0), Tier 1 keyword rules,
       Tier 2 GPT-4o AI scoring (1=Noise → 5=Urgent)

5. GROUP (AI)
   └─> Cluster related items by theme (replaced by keyword tagging, shipped v3.3)

6. EMAIL (Conditional)
   └─> Bilingual HTML digest (native + English)
       Skip if no new/updated items

7. BASELINE UPDATE
   └─> Store new items for future comparison
```

---

## 📖 Documentation

### Strategic & Planning
- **[Big_Picture.md](Big_Picture.md)** — Strategic evolution plan (Journalist → Executive Advisor)
- **[UI5_MIGRATION_ROADMAP.md](UI5_MIGRATION_ROADMAP.md)** — UI5/Fiori migration detailed plan

### Technical & Operations
- **[SPEC.md](SPEC.md)** — Technical specification (v2.32 current architecture)
- **[CHANGELOG.md](CHANGELOG.md)** — Version history and release notes
- **[BTP_DEPLOYMENT.md](BTP_DEPLOYMENT.md)** — SAP BTP Cloud Foundry deployment guide

### User Guide
- **README.md** (this file) — Vision, current capabilities, getting started

---

## 🌐 Deployment Options

### Local Development
```bash
python admin/app.py
```

### Production (macOS/Linux)
```bash
# Using launchd (macOS) or systemd (Linux)
# See scripts/launchd/ and scripts/systemd/ for templates
```

### SAP BTP Cloud Foundry
```bash
cf push
```
See [BTP_DEPLOYMENT.md](BTP_DEPLOYMENT.md) for complete deployment guide.

---

## 📁 Project Structure

```
legal-eagle/
├── agents/                   # Processing pipeline (collect, filter, group, email)
├── admin/                    # Flask Admin UI + templates
├── configurations/           # Database, config loader, environment variables
├── scripts/                  # Utilities, migrations, admin launchers
├── outputs/                  # Generated artifacts (JSON, HTML, logs)
├── memory-bank/              # Project memory and documentation
├── Big_Picture.md            # Strategic evolution roadmap
├── README.md                 # This file
├── SPEC.md                   # Technical specification
└── UI5_MIGRATION_ROADMAP.md  # UI5/Fiori migration plan
```

---

## 🤝 Support & Feedback

For issues, questions, or feature requests:
- Open an issue on GitHub
- Contact the SAP Globalization team

---

## 📜 License

Proprietary — Internal SAP project.

---

## 🎯 End Goal

A scalable internal AI platform helping SAP localization teams react faster to legal change, reuse knowledge better, and operate globally with higher intelligence.

**Legal Eagle Core is live today. The journey to Virtual LPM starts now.**