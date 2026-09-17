# BTP Backup/Restore System (v3.34+)

## The Problem

BTP Cloud Foundry containers are **ephemeral**. When you run `cf push`, `cf restart`, or `cf restage`, a new container may be created with an **empty database**. All your configuration and production data is lost.

## The Solution

**Three steps before and after deployment:**

```bash
# Step 1: BACKUP before deployment
python3 scripts/btp_backup.py --secret prod-secure-secret-2026

# Step 2: Deploy to BTP
cf push

# Step 3: RESTORE after deployment
python3 scripts/btp_restore.py --file btp_backup_20260917_221500.json --secret prod-secure-secret-2026
```

## Setup

```bash
# Install dependencies
pip install requests

# Set environment variable (optional)
export LEGAL_EAGLE_ADMIN_SECRET="prod-secure-secret-2026"
```

## Usage

### Backup
```bash
python3 scripts/btp_backup.py --secret prod-secure-secret-2026
# Creates: btp_backup_20260917_221500.json
```

### Restore
```bash
python3 scripts/btp_restore.py --file btp_backup_20260917_221500.json --secret prod-secure-secret-2026
# Asks for confirmation, then imports data
```

## What Gets Backed Up

- ✅ All config tables (profiles, RSS feeds, glossary, etc.)
- ✅ All production tables (news items, runs, announcements, etc.)
- ✅ Workflow history and logs
- ❌ Credentials (stored in environment variables, not database)

## Full Deployment Workflow

```bash
# 1. Make code changes locally
vi admin/app.py

# 2. Test locally (optional)
python3 tests/run_harness.py

# 3. BACKUP your BTP data
python3 scripts/btp_backup.py --secret prod-secure-secret-2026

# 4. Commit and push to GitHub
git add .
git commit -m "v3.35: My feature"
git push origin main

# 5. Deploy to BTP
cf push

# 6. Wait for deployment to complete
# Monitor with:
watch "cf app legal-eagle-ui | grep state"

# 7. RESTORE your data from backup
python3 scripts/btp_restore.py --file btp_backup_*.json --secret prod-secure-secret-2026

# 8. Verify data is restored
# Open: https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com/admin
```

## API Endpoints (Advanced)

### Export All Data
```bash
GET /api/export-all?secret=prod-secure-secret-2026
```

### Import All Data
```bash
POST /api/import-all
Authorization: Bearer prod-secure-secret-2026
Content-Type: application/json

{...all database tables...}
```

## FAQ

**Q: Do backups include passwords?**
A: No! Only configuration. Credentials stay in environment variables.

**Q: Can I restore old backups?**
A: Yes, but it replaces current data (script asks for confirmation).

**Q: How large are backups?**
A: Typically 100-500 KB.

**Q: Must I backup every time?**
A: Yes, before any deployment operation.

## Documentation

- Full reference: `BTP_DEPLOYMENT_DIFFERENCES.md` (Section 14)
- Deployment workflow: `XANADU_DEPLOYMENT_STEPS.md`
- Script details: `scripts/btp_backup.py` and `scripts/btp_restore.py`

**Version:** v3.34  
**Status:** ✅ Production-ready
