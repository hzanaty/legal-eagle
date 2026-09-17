# BTP Deployment Differences — Legal Eagle v3.33+

## Overview

This document details all **code and configuration differences** between the local development environment and the BTP production deployment. These differences ensure compliance, security, and operational safety on BTP.

---

## 1. Email & Gmail Integration

### LOCAL DEVELOPMENT

| Feature | Status | Details |
|---------|--------|---------|
| Gmail SMTP Sending | ✅ **ENABLED** | Sends digest emails via Gmail App Password |
| Gmail IMAP Reading | ✅ **ENABLED** | Reads forwarded monitor-update emails from Gmail |
| Environment Variable | Required | `LEGAL_EAGLE_GMAIL_EMAIL_SENDER` |
| Environment Variable | Required | `LEGAL_EAGLE_GMAIL_APP_PASSWORD` |
| Email Feature Flag | N/A | Not used in local development |

**Code Files Affected:**
- `agents/email_sender.py` — full email composition and SMTP sending
- `agents/email_inbox_parser.py` — Gmail IMAP reading
- `agents/agents_controller.py` — email sending in run pipeline
- `admin/app.py` — email UI elements and endpoints

---

### BTP PRODUCTION

| Feature | Status | Details |
|---------|--------|---------|
| Gmail SMTP Sending | ❌ **DISABLED** | Cloud IPs blocked by Gmail; compliance risk |
| Gmail IMAP Reading | ❌ **DISABLED** | No Gmail App Password set on BTP |
| ANS (Alert Notification Service) | ❌ **NOT USED** | Can be enabled in future; not in v3.33 deployment |
| Environment Variable | NOT SET | `LEGAL_EAGLE_EMAIL_ENABLED` = `false` |
| Email Feature Flag | ✅ **ACTIVE** | Controls all email code paths |

**What is Disabled:**
1. **Email sending** — No outbound SMTP calls
2. **Email reading** — No IMAP connections to Gmail
3. **Email UI** — Send buttons and email configuration hidden
4. **Email API endpoints** — `/api/send-email` returns disabled message

**Why:**
- **Compliance** — Previous deployment triggered SAP security warning for 3P API calls from BTP
- **Security** — Gmail blocks cloud provider IPs by default
- **Architecture** — Email can be re-enabled later via ANS without code changes

---

## 2. Configuration

### Environment Variables — BTP Only

```bash
# Email disabled flag (NEW for BTP)
LEGAL_EAGLE_EMAIL_ENABLED=false

# Required for all deployments
LEGAL_EAGLE_SAP_AICORE_BASE_URL=https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com
LEGAL_EAGLE_SAP_AICORE_AUTH_URL=https://sapaicore-vkibf89l.authentication.sap.hana.ondemand.com
LEGAL_EAGLE_SAP_AICORE_CLIENT_ID=<your-client-id>
LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET=<your-client-secret>
LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID=d1555c6d43e6f446
LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID=d987a899a829c105

# Admin secret
LEGAL_EAGLE_ADMIN_SECRET=<your-secure-random-string>

# NOT set on BTP (email disabled)
# LEGAL_EAGLE_GMAIL_EMAIL_SENDER=<not-set>
# LEGAL_EAGLE_GMAIL_APP_PASSWORD=<not-set>
```

### Environment Variables — LOCAL ONLY

```bash
# Local development can use Gmail
LEGAL_EAGLE_EMAIL_ENABLED=true
LEGAL_EAGLE_GMAIL_EMAIL_SENDER=your-email@sap.com
LEGAL_EAGLE_GMAIL_APP_PASSWORD=your-gmail-app-password
```

---

## 3. Database

### LOCAL DEVELOPMENT

| Aspect | Details |
|--------|---------|
| Location | `configurations/config.db` (local SQLite) |
| Persistence | ✅ Persistent across sessions |
| Contains | Config + production data mixed |
| Backup | Manual (git-ignored by default) |

---

### BTP PRODUCTION

| Aspect | Details |
|--------|---------|
| Location | Container ephemeral filesystem |
| Persistence | ❌ Lost on redeployment/restart |
| Strategy | **Config-only export/import** |
| Contains | **Only configuration** (profiles, glossary, sources, etc.) |
| Production Data | **Starts empty** — accumulates from real runs |

**Deployment Process:**
1. Export config tables from local DB (script: `scripts/export_config.py`)
2. Deploy clean BTP instance with schema only
3. Import config tables into BTP DB (script: `scripts/import_config.py`)
4. Production data (news_items, runs, announcements) accumulates fresh on BTP

---

## 4. Job Scheduling

### LOCAL DEVELOPMENT

| Aspect | Details |
|--------|---------|
| Scheduler | `launchctl` daemon or manual |
| Frequency | Manual trigger via Dev Server |
| Automation | Optional (not required) |

---

### BTP PRODUCTION

| Aspect | Details |
|--------|---------|
| Scheduler | **Manual trigger only** |
| Frequency | Via Admin UI "Run" button |
| Job Scheduler Service | Not configured (future option) |
| API Endpoint | `POST /api/trigger` — not exposed to external scheduler |

**Note:** If automated scheduling is needed in future, BTP Job Scheduler Service can be added without code changes.

---

## 5. Code Feature Flags

### Email Disable Pattern

**Location:** `agents/email_sender.py`, `agents/email_inbox_parser.py`, `agents/agents_controller.py`, `admin/app.py`

**Pattern:**
```python
import os

# Feature flag at module load
EMAIL_ENABLED = os.environ.get("LEGAL_EAGLE_EMAIL_ENABLED", "true").lower() == "true"

# Usage in functions
def send_email(...):
    if not EMAIL_ENABLED:
        print("[EMAIL] Email sending disabled on this environment")
        return False
    
    # Rest of implementation
    ...

# In Admin UI templates
{% if email_enabled %}
    <button>Send Email</button>
{% else %}
    <p class="disabled">Email sending disabled on BTP</p>
{% endif %}
```

**Benefits:**
- ✅ Single codebase for local and BTP
- ✅ No code divergence
- ✅ Easy to enable later
- ✅ Clear documentation in code

---

## 6. Xanadu Gov Site

### LOCAL DEVELOPMENT

| Aspect | Details |
|--------|---------|
| Location | `Roadmap/v3/xanadu-gov-site/public/` |
| Hosting | Local file:// URLs for testing |
| Accessibility | Developer machine only |

---

### BTP PRODUCTION

| Aspect | Details |
|--------|---------|
| Location | GitHub Pages (separate from BTP) |
| Hosting | Public HTTPS URL |
| Accessibility | Legal Eagle RSS sources point to GitHub URLs |
| Repository | `https://github.tools.sap/i077750/legal-eagle` (gh-pages branch) |
| URL Format | `https://i077750.github.io/legal-eagle/xanadu-gov-site/` (or similar) |

---

## 7. Admin UI Differences

### Email Configuration Panel

**LOCAL:**
- Email Receivers section fully visible
- "Configure Emails" form enabled
- Send digest button available

**BTP:**
- Email Receivers section hidden/disabled
- Configuration form shows: "Email disabled on this environment"
- Send digest button disabled with tooltip

---

## 8. Code Changes Summary

### Files with Email Disable Logic

1. **`agents/email_sender.py`**
   - Add: `EMAIL_ENABLED` flag at top
   - Wrap: `send_email()` function with flag check
   - Return: `False` if disabled

2. **`agents/email_inbox_parser.py`**
   - Add: `EMAIL_ENABLED` flag at top
   - Wrap: `fetch_monitor_updates()` with flag check
   - Return: Empty dict if disabled

3. **`agents/agents_controller.py`**
   - Add: `EMAIL_ENABLED` flag import
   - Conditional: Skip email sending stage if flag is `false`
   - Log: "[EMAIL] Email sending skipped on this environment"

4. **`admin/app.py`**
   - Add: `EMAIL_ENABLED` flag to template context
   - Hide: Email configuration section based on flag
   - Disable: Email-related routes if flag is `false`

5. **`admin/templates/base.html`**
   - Add: Conditional rendering for email UI elements
   - Show: Info message when email disabled

### New Files

1. **`BTP_DEPLOYMENT_DIFFERENCES.md`** (this file)
   - Complete reference of local vs BTP differences
   
2. **`scripts/export_config.py`** (new script)
   - Export configuration tables from local DB
   - Output: JSON format for easy review

3. **`scripts/import_config.py`** (new script)
   - Import configuration tables into BTP DB
   - Safety: Validate schema exists first

---

## 9. Testing Differences

### LOCAL DEVELOPMENT

**Test Commands:**
```bash
# Full pipeline with email
python tests/run_harness.py

# With AI cache for faster testing
LEGAL_EAGLE_AI_CACHE=1 python tests/run_harness.py
```

---

### BTP PRODUCTION

**Testing:**
- Use Admin UI for all testing
- Manual runs via "Run" button
- Review results in "Review" and "Announcements" tabs
- Check logs in `cf logs legal-eagle-ui --recent`

**Email Bypass:**
- Email features are skipped silently
- Pipeline completes successfully
- Results visible in Admin UI

---

## 10. Migration Path: Future Email Re-enablement

### If you want to enable email in the future:

1. **Option A: Use ANS (Recommended for BTP)**
   - Uncomment ANS service binding in `manifest.yaml`
   - Re-enable `ans_sender.py` code
   - Set `LEGAL_EAGLE_EMAIL_ENABLED=true`
   - Set ANS credentials in environment
   - No other code changes needed

2. **Option B: Use different cloud provider**
   - Switch from Gmail to AWS SES / SendGrid
   - Only swap SMTP implementation
   - Rest of pipeline remains unchanged

---

## 11. Compliance & Security Notes

### Why Email is Disabled on BTP

**Historical Issue:**
- Previous deployment flagged by SAP security
- Concern: 3P API calls (Gmail) from BTP
- Resolution: Use SAP's native ANS service instead

**Current State (v3.33):**
- No external email services enabled
- No 3P API keys on BTP
- All email code disabled via flag
- Compliant with security policies

**Future:**
- ANS integration available when needed
- ANS is SAP-native service (no compliance risk)
- Code already prepared for re-enablement

---

## 12. Troubleshooting Differences

### Issue: Email not sending on BTP

**Expected Behavior:**
- Check `cf logs legal-eagle-ui --recent`
- Look for: `[EMAIL] Email sending disabled on this environment`
- This is **normal** — email is intentionally disabled
- Results are still visible in Admin UI

### Issue: Email works locally but not on BTP

**Root Cause:**
- Local has `LEGAL_EAGLE_EMAIL_ENABLED=true`
- BTP has `LEGAL_EAGLE_EMAIL_ENABLED=false`
- This is by design

**Solution:**
- If you need email on BTP, implement ANS integration
- Contact LPMx team for ANS service binding

---

## 13. Quick Reference Checklist

### Before BTP Deployment

- [ ] Local `.env` has `LEGAL_EAGLE_EMAIL_ENABLED=true` (local only)
- [ ] BTP environment will have `LEGAL_EAGLE_EMAIL_ENABLED=false`
- [ ] Config export script tested locally
- [ ] Config import script validated with test DB
- [ ] Xanadu site pushed to GitHub Pages
- [ ] `BTP_DEPLOYMENT_DIFFERENCES.md` reviewed

### After BTP Deployment

- [ ] Admin UI loads without errors
- [ ] Email configuration panel shows "disabled" message
- [ ] Manual run completes successfully
- [ ] Results visible in Review tab
- [ ] No email sending attempts in logs

---

## Contact & Support

For questions about these differences:
- Check this document first
- Review code comments in `agents/email_sender.py`
- Consult `BTP_DEPLOYMENT.md` for deployment process
- Ask in Legal Eagle project wiki/docs

---

## 14. BTP Data Backup/Restore (v3.34)

### The Problem (Ephemeral Database)

When `cf restart`, `cf restage`, or `cf push` is executed on BTP:
- The container may be recreated on a different Diego Cell
- SQLite database file (`config.db`) is local to that container
- New container = **brand new empty database**
- **All config and production data is lost**

### The Solution: Backup Before, Restore After

**Three-step workflow:**

```bash
# Step 1: Before any restart/restage/push
python scripts/btp_backup.py --secret <admin-secret>
# Creates: btp_backup_20260917_221500.json

# Step 2: Do your restart/restage/push
cf restart legal-eagle-ui
# or
cf push

# Step 3: After app is running again
python scripts/btp_restore.py --file btp_backup_20260917_221500.json --secret <admin-secret>
# Restores all data from backup
```

### New API Endpoints

Both endpoints are protected by admin secret (query parameter or Bearer token):

**Export All Data:**
```bash
GET /api/export-all?secret=<admin-secret>
# or
curl -H "Authorization: Bearer <admin-secret>" https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com/api/export-all

# Returns:
{
  "profiles": [...],
  "rss_feeds": [...],
  "news_items": [...],
  "runs": [...],
  "_metadata": {
    "export_timestamp": "2026-09-17T22:15:00.000000",
    "version": "v3.34"
  }
}
```

**Import All Data:**
```bash
POST /api/import-all
Content-Type: application/json
Authorization: Bearer <admin-secret>

{
  "profiles": [...],
  "rss_feeds": [...],
  ...same as export format...
}

# Returns:
{
  "status": "success",
  "rows_imported": 1234
}
```

### Local Scripts

**`scripts/btp_backup.py`**
```bash
python scripts/btp_backup.py \
  --url https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com \
  --secret prod-secure-secret-2026 \
  --output my_backup.json
```

**`scripts/btp_restore.py`**
```bash
python scripts/btp_restore.py \
  --file my_backup.json \
  --url https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com \
  --secret prod-secure-secret-2026
```

Both scripts can read admin secret from `LEGAL_EAGLE_ADMIN_SECRET` environment variable.

### What Gets Backed Up?

**Config tables (preserved across environments):**
- profiles, settings, authorities
- rss_feeds, tweet_accounts, url_sources, email_receivers
- glossary_labels, glossary_terms, glossary_synonyms, glossary_patterns
- law_refs, ranking_signals, ranking_grounding, rcm_reference_titles

**Production tables (workflow data):**
- news_items, filtered_news, news_announcements
- runs, run_logs, audit_log

### When to Use

| Scenario | Action |
|----------|--------|
| **Before `cf push`** | Run `btp_backup.py` |
| **Before `cf restart`** | Run `btp_backup.py` |
| **Before `cf restage`** | Run `btp_backup.py` |
| **After any restart/push** | Run `btp_restore.py` if needed |
| **Regular backups** | Add to scheduled tasks / cron |

---

**Last Updated:** 2026-09-17  
**Version:** v3.34  
**Scope:** Legal Eagle BTP Deployment