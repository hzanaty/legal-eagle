# BTP Deployment Plan — Legal Eagle v3.33

**Date:** 2026-09-17  
**Version:** v3.33  
**Status:** Ready for Implementation

---

## Executive Summary

This document provides the **complete step-by-step deployment plan** for Legal Eagle on SAP BTP Cloud Foundry. All decisions have been finalized, and code changes are in place.

### Deployment Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Database** | Config-only export/import | Ephemeral container; config tables deployed, production data starts fresh |
| **Scheduling** | Manual triggers via Admin UI | No Job Scheduler service; runs triggered via "Run" button |
| **Email** | Disabled with feature flag | Compliance: Gmail blocked on BTP; can enable ANS later |
| **Xanadu Site** | GitHub Pages | Public HTTPS URL; separate from BTP infrastructure |

---

## Part 1: Pre-Deployment Checklist

### 1.1 Install BTP CLI (macOS)

```bash
# Option A: Using Homebrew
brew install sap-btp-cli

# Option B: Manual installation
# Download from: https://github.com/SAP/btp-cli/releases
# Extract and add to PATH
```

Verify installation:
```bash
btp --version
```

### 1.2 CF CLI Status

```bash
cf --version
# Expected: cf version 8.18.0 or later (already installed)
```

### 1.3 Authenticate to BTP Cloud Foundry

```bash
cf login --sso -a https://api.cf.eu21.hana.ondemand.com
# When prompted:
# - Organization: gpm-chat_legal-eagle-bfrzhqe2
# - Space: prod
```

Verify login:
```bash
cf target
# Should show: Space: prod
```

---

## Part 2: Local Setup & Config Export

### 2.1 Export Configuration Data

**Step 1:** Export your local database configuration

```bash
python scripts/export_config.py \
  --db configurations/config.db \
  --output scripts/test_runs/config_export.json
```

**Expected Output:**
```
📊 Exporting configuration from: configurations/config.db
💾 Output file: scripts/test_runs/config_export.json
  ✅ profiles: N rows
  ✅ rss_feeds: N rows
  ✅ glossary_terms: N rows
  ✅ authorities: N rows
  ✅ url_sources: N rows
  ...
✅ Export complete!
```

**Step 2:** Review the export file (optional but recommended)

```bash
# Preview first 100 lines
head -100 scripts/test_runs/config_export.json

# Check summary
grep -A 10 '"metadata"' scripts/test_runs/config_export.json
```

This file contains:
- ✅ All profiles (XN/HCM, SA/FIN, etc.)
- ✅ RSS feeds, Twitter accounts, URL sources
- ✅ Glossary terms and labels
- ✅ Authorities, law references
- ❌ NO production data (news items, runs, etc.)

### 2.2 Commit and Push (Optional)

```bash
git add BTP_DEPLOYMENT_DIFFERENCES.md
git add BTP_DEPLOYMENT_PLAN.md
git add scripts/export_config.py
git add scripts/import_config.py
git commit -m "v3.33: Add BTP deployment scripts and documentation"
git push origin main
```

---

## Part 3: BTP Deployment

### 3.1 Deploy Legal Eagle Application

**Step 1:** Deploy the app with `cf push`

```bash
cf push
```

**Expected Output:**
```
Pushing app legal-eagle-ui to org gpm-chat_legal-eagle-bfrzhqe2 / space prod...
...
Waiting for app legal-eagle-ui to start...
name:              legal-eagle-ui
requested state:   started
instances:         1/1
routes:            legal-eagle-ui.cfapps.eu21.hana.ondemand.com
memory:            900M
disk:              2G
```

**Step 2:** Verify deployment status

```bash
cf app legal-eagle-ui
```

### 3.2 Set Environment Variables

**Step 1:** Configure SAP AI Core credentials

```bash
cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_BASE_URL \
  "https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com"

cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_AUTH_URL \
  "https://sapaicore-vkibf89l.authentication.sap.hana.ondemand.com"

cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_CLIENT_ID \
  "your-client-id-here"

cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET \
  "your-client-secret-here"

cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID \
  "d1555c6d43e6f446"

cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID \
  "d987a899a829c105"
```

**Step 2:** Configure email (disabled for BTP)

```bash
# Email is disabled for compliance - this flag makes it official
cf set-env legal-eagle-ui LEGAL_EAGLE_EMAIL_ENABLED "false"
```

**Step 3:** Set admin secret

```bash
cf set-env legal-eagle-ui LEGAL_EAGLE_ADMIN_SECRET \
  "your-secure-random-string-here"
```

**Step 4:** Restage application to apply environment variables

```bash
cf restage legal-eagle-ui
```

**Step 5:** Verify environment variables

```bash
cf env legal-eagle-ui | grep LEGAL_EAGLE
```

### 3.3 Access Admin UI

```bash
# Get the route
cf app legal-eagle-ui | grep routes

# Open in browser
open https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com
```

You should see the Legal Eagle login page.

---

## Part 4: Import Configuration Data

### 4.1 Copy Export File to BTP Container (if needed)

If the export file is too large for direct import, use this workaround:

```bash
# Option A: Push file within app directory
cp scripts/test_runs/config_export.json .
# Then push again with cf push

# Option B: SSH into container and download
cf ssh legal-eagle-ui
wget https://path-to-export-file/config_export.json
```

### 4.2 Run Import Script on BTP

```bash
# SSH into the BTP container
cf ssh legal-eagle-ui

# Navigate to app directory
cd app

# Run import (inside container)
python scripts/import_config.py \
  --input config_export.json \
  --db configurations/config.db

# Expected output:
# 📖 Importing configuration from: config_export.json
# 📊 Target database: configurations/config.db
# ✅ Schema validation passed
# 📥 Importing tables:
#   ✅ profiles: N rows inserted
#   ✅ rss_feeds: N rows inserted
#   ...
# ✅ Import complete!
```

### 4.3 Verify Import in Admin UI

```bash
# 1. Reload Admin UI (refresh browser)
# 2. Navigate to "Configure" tab
# 3. Check that profiles appear
# 4. Verify sources, glossary, authorities are present
```

---

## Part 5: Test Deployment

### 5.1 Verify Admin UI Access

1. Navigate to: `https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com`
2. Check that the app loads without errors
3. Verify the Dashboard tab shows your profiles

### 5.2 Run Manual Test

1. Click the **"Run"** button in the Dashboard
2. Select a profile
3. Choose your sources (RSS, URLs, etc.)
4. Click **"Start Run"**
5. Monitor the pipeline in real-time
6. Verify no email sending attempts in logs

### 5.3 Check Logs

```bash
# View recent logs
cf logs legal-eagle-ui --recent

# Watch logs in real-time
cf logs legal-eagle-ui
```

**Look for:**
- ✅ `[EMAIL] Email sending disabled on this environment` — correct, email is disabled
- ✅ Pipeline stages completing successfully
- ❌ No Gmail/SMTP connection errors

### 5.4 Review Results

1. Refresh Admin UI "Review" tab
2. Verify news items appear
3. Check "Announcements" tab for grouped results
4. Verify no email was sent (intentional)

---

## Part 6: Xanadu Gov Website (GitHub Pages)

### 6.1 Create GitHub Pages Branch

If not already done:

```bash
# From your legal-eagle repository root
git checkout --orphan gh-pages
git reset --hard
git commit --allow-empty -m "Initial gh-pages branch"
```

### 6.2 Copy Xanadu Site Files

```bash
# Copy the entire xanadu-gov-site/public directory to gh-pages branch
cp -r Roadmap/v3/xanadu-gov-site/public/* .
git add .
git commit -m "Deploy Xanadu Gov site to GitHub Pages"
git push origin gh-pages
```

### 6.3 Get Public URL

Your Xanadu site will be available at:
```
https://i077750.github.io/legal-eagle/
```

Or with custom domain (if configured):
```
https://your-domain.com/legal-eagle/
```

### 6.4 Update Legal Eagle Sources (Optional)

If you want Legal Eagle to fetch from the Xanadu site:

1. Admin UI → Configure tab
2. Add URL source: `https://i077750.github.io/legal-eagle/xanadu-gov-site/`
3. Or update RSS feed: `https://i077750.github.io/legal-eagle/xanadu-gov-site/feed.xml` (if available)

---

## Part 7: CI/CD Workflow for Future Updates

### When You Find a Bug

**Workflow:**

```bash
# 1. Fix the bug locally
# (edit code in agents/, admin/, configurations/, etc.)

# 2. Test locally
python tests/run_harness.py
# or use Admin UI locally

# 3. Commit to GitHub
git add .
git commit -m "v3.34: Fix [bug description]"
git push origin main

# 4. Deploy to BTP (simple one-liner)
cf push

# 5. Set environment variables again (they persist, but good practice)
cf set-env legal-eagle-ui LEGAL_EAGLE_EMAIL_ENABLED "false"
cf restage legal-eagle-ui

# 6. Verify
cf logs legal-eagle-ui --recent
# Open Admin UI and test
```

### Key Points

- **Database:** Already has your config (persists across pushes)
- **Production data:** Accumulated on BTP (not overwritten)
- **Environment variables:** Persist across `cf push` (no need to reset them every time)
- **Email:** Remains disabled (configured via `LEGAL_EAGLE_EMAIL_ENABLED=false`)

---

## Part 8: Troubleshooting

### Issue: App won't start after cf push

```bash
# Check logs
cf logs legal-eagle-ui --recent

# Common causes:
# - Missing environment variables → Set them with cf set-env
# - Schema error → Check database.log in container
# - Dependency error → Check requirements.txt
```

### Issue: Admin UI shows "Database locked"

```bash
# SQLite has concurrency issues. Restart the app:
cf restart legal-eagle-ui
```

### Issue: Import failed - schema not found

```bash
# Schema is created on first cf push
# If it fails, ensure:
# 1. cf push completed successfully
# 2. App is running: cf app legal-eagle-ui
# 3. Try import again
```

### Issue: Email buttons showing but shouldn't

```bash
# Check environment variable
cf env legal-eagle-ui | grep EMAIL_ENABLED

# Should show: LEGAL_EAGLE_EMAIL_ENABLED: false
# If not set, run: cf set-env legal-eagle-ui LEGAL_EAGLE_EMAIL_ENABLED "false"
```

---

## Part 9: Reference Files

### New/Updated Files in This Deployment

| File | Purpose |
|------|---------|
| `BTP_DEPLOYMENT_DIFFERENCES.md` | Complete reference of local vs BTP differences |
| `BTP_DEPLOYMENT_PLAN.md` | This document — step-by-step deployment guide |
| `scripts/export_config.py` | Export config tables from local database |
| `scripts/import_config.py` | Import config tables into BTP database |
| `agents/email_sender.py` | Updated with EMAIL_ENABLED flag |
| `manifest.yaml` | Already configured for BTP |
| `Procfile` | Already configured with Gunicorn |
| `runtime.txt` | Already configured for Python 3.11 |
| `.cfignore` | Already configured to exclude .git, __pycache__, etc. |

### Existing BTP Documentation

- `BTP_DEPLOYMENT.md` — Original BTP deployment guide (still valid)

---

## Part 10: Deployment Checklist

### Pre-Deployment

- [ ] BTP CLI installed (`btp --version`)
- [ ] CF CLI authenticated (`cf target`)
- [ ] Local database exported (`scripts/export_config.py`)
- [ ] Export file validated (contains profiles, sources, glossary)
- [ ] Code committed to GitHub (`git push origin main`)

### Deployment

- [ ] App deployed (`cf push`)
- [ ] Environment variables set (SAP AI Core, admin secret, email flag)
- [ ] App restarted/restaged (`cf restage`)
- [ ] Admin UI accessible (`https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com`)

### Post-Deployment

- [ ] Config imported into BTP database
- [ ] Profiles visible in Admin UI
- [ ] Manual run completed successfully
- [ ] Email disabled (logs show `[EMAIL] Email sending disabled`)
- [ ] Results visible in Review/Announcements tabs
- [ ] Xanadu site deployed to GitHub Pages

### Ongoing

- [ ] Bug fixes: Edit code → commit → `cf push`
- [ ] Environment variables persist (no need to reset)
- [ ] Monitor logs: `cf logs legal-eagle-ui --recent`
- [ ] Database backup strategy planned (if needed)

---

## Part 11: Support & Questions

For issues during deployment:

1. **Check logs first:**
   ```bash
   cf logs legal-eagle-ui --recent
   ```

2. **Review documentation:**
   - `BTP_DEPLOYMENT_DIFFERENCES.md` — local vs BTP differences
   - `BTP_DEPLOYMENT.md` — original guide
   - `SPEC.md` — technical specification

3. **Common issues:**
   - Email disabled? → Check `LEGAL_EAGLE_EMAIL_ENABLED` env var
   - Database error? → Restart app with `cf restart`
   - Import failed? → Ensure schema exists (`cf push` first)

---

## Part 12: Future Enhancements

### Email Re-enablement (Future)

When ready to enable email on BTP:

1. Set up SAP Alert Notification Service (ANS)
2. Create ANS service binding in `manifest.yaml`
3. Set `LEGAL_EAGLE_EMAIL_ENABLED=true`
4. Uncomment ANS code in `agents/ans_sender.py`
5. Deploy with `cf push`

### Job Scheduler (Future)

For automated daily runs:

1. Create BTP Job Scheduler service
2. Configure scheduled HTTP POST to `/api/trigger`
3. No code changes needed

### Database Persistence (Future)

For production stability:

1. Migrate from SQLite to BTP PostgreSQL service
2. Update `configurations/db.py` connection string
3. Run schema migration
4. Deploy with `cf push`

---

**Deployment Plan Version:** v3.33  
**Last Updated:** 2026-09-17  
**Status:** ✅ Ready for Implementation