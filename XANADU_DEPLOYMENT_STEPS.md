# BTP Deployment Workflow — Data Backup/Restore (v3.34+)

> **NEW:** Starting from v3.34, always backup before deploying to preserve your data!

## 📋 Quick Workflow (v3.34+)

```bash
# ✅ BEFORE any cf push/restart/restage
python3 scripts/btp_backup.py --secret prod-secure-secret-2026

# 🚀 DO your deployment
cf push
# or
cf restart legal-eagle-ui

# ✅ AFTER deployment completes
python3 scripts/btp_restore.py --file btp_backup_20260917_221500.json --secret prod-secure-secret-2026
```

**Why?** BTP containers are ephemeral — SQLite database is lost on every deployment. The backup/restore scripts preserve your configuration and workflow data.

---

## ✅ What's Been Done (Xanadu Setup)

1. **Xanadu Gov Site Deployed to GitHub Pages**
   - Location: `/docs` folder in legal-eagle repo
   - URL: `https://pages.github.tools.sap/I077750/legal-eagle/xanadu.html`
   - Status: Live and accessible ✅

2. **GitHub Pages Enabled**
   - Branch: main
   - Source: / (root, serves /docs folder)
   - Status: Configured ✅

3. **Script Created to Update URL Sources**
   - Location: `scripts/update_url_sources_to_github_pages.py`
   - Purpose: Updates local database to use GitHub Pages URL instead of `file://` paths
   - Status: Ready to run ✅

## 🔧 Steps You Need to Complete (Locally)

### Step 1: Update URL Sources in Local Database
Run this command in your terminal:
```bash
cd /Users/i077750/Documents/GitHub/legal-eagle
python3 scripts/update_url_sources_to_github_pages.py
```

**Expected output:**
```
✅ Updated profile_id X:
   FROM: file:///Users/i077750/Documents/GitHub/legal-eagle/Roadmap/v3/xanadu-gov-site/public/index.html
   TO:   https://pages.github.tools.sap/I077750/legal-eagle/xanadu.html

📊 Summary: Updated N URL source(s)
```

### Step 2: Push Updated Config to GitHub
```bash
cd /Users/i077750/Documents/GitHub/legal-eagle
git add .
git commit -m "Update URL sources to use GitHub Pages for Xanadu site"
git push origin main
```

### Step 3: Deploy to BTP
```bash
cd /Users/i077750/Documents/GitHub/legal-eagle
cf push
```

This will:
- Deploy updated app to BTP
- Use the new GitHub Pages URL for Xanadu sources
- Keep the configuration from your local database (which now has the correct URLs)

## 📋 Summary

| Component | Status | Location |
|-----------|--------|----------|
| Xanadu Site | ✅ Deployed | `https://pages.github.tools.sap/I077750/legal-eagle/xanadu.html` |
| Legal Eagle App | ✅ On BTP | `https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com` |
| URL Sources | ⏳ Pending | Update locally, then push to GitHub |
| BTP Deployment | ⏳ Pending | `cf push` after updating |

## 🚀 After Deployment

- BTP will fetch news from `https://pages.github.tools.sap/I077750/legal-eagle/xanadu.html` (public URL)
- No more `file://` paths from local filesystem
- Admin UI will show live news from Xanadu Government website