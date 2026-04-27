# Legal Eagle - BTP Cloud Foundry Deployment Guide

## Overview
This guide walks through deploying Legal Eagle to SAP BTP Cloud Foundry environment.

## Prerequisites
- ✅ BTP Subaccount with Cloud Foundry enabled
- ✅ CF CLI installed (`cf version 8.18.0+`)
- ✅ Logged into CF CLI (`cf login`)
- ✅ Space created (e.g., `prod`)

## Architecture on BTP

```
┌─────────────────────────────────────────────────────────┐
│                BTP Cloud Foundry (prod)                  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────┐                                   │
│  │  legal-eagle-ui  │                                   │
│  │  (Flask Admin)   │                                   │
│  │  - Gunicorn      │                                   │
│  │  - Playwright    │                                   │
│  │  - 1GB Memory    │                                   │
│  └────────┬─────────┘                                   │
│           │                                              │
│           │                                              │
│  ┌────────▼─────────┐                                   │
│  │   SQLite DB      │                                   │
│  │(persistent disk) │                                   │
│  └──────────────────┘                                   │
│                                                          │
│  Note: Use external schedulers (BTP Job Scheduler,      │
│        cron, etc.) to trigger runs via Admin UI or API  │
└─────────────────────────────────────────────────────────┘
```

## Key Features

- **Dynamic Rendering**: Playwright browser automation for JavaScript-heavy government websites
- **System Libraries**: apt-buildpack installs required Chromium dependencies
- **Memory**: 1GB allocated for Playwright browser operations
- **Timeout**: 60-second page load timeout for slow government sites

## Step 1: Set Environment Variables

Before deploying, you need to configure environment variables for your application.

### Required Environment Variables

1. Go to BTP Cockpit → Cloud Foundry → Spaces → `prod`
2. After first deployment, set these variables via:
   ```bash
   # SAP AI Core credentials (replaces OpenAI)
   cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_BASE_URL "https://api.ai.internalprod.eu-central-1.aws.ml.hana.ondemand.com"
   cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_AUTH_URL "https://sapaicore-vkibf89l.authentication.sap.hana.ondemand.com"
   cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_CLIENT_ID "your-client-id"
   cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET "your-client-secret"
   cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID "d1555c6d43e6f446"
   cf set-env legal-eagle-ui LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID "d987a899a829c105"
   
   # Twitter/X
   cf set-env legal-eagle-ui LEGAL_EAGLE_TWITTER_BEARER_TOKEN "your-twitter-token"
   
   # Gmail
   cf set-env legal-eagle-ui LEGAL_EAGLE_GMAIL_EMAIL_SENDER "your-email@sap.com"
   cf set-env legal-eagle-ui LEGAL_EAGLE_GMAIL_APP_PASSWORD "your-gmail-app-password"
   
   # Admin secret
   cf set-env legal-eagle-ui LEGAL_EAGLE_ADMIN_SECRET "your-secure-random-string"
   ```

3. Restart the app:
   ```bash
   cf restage legal-eagle-ui
   ```

## Step 2: Deploy Application

From your project root directory:

```bash
cf push
```

This command:
- Reads `manifest.yaml` for configuration
- Uploads application code (excluding `.cfignore` files)
- Installs Python dependencies from `configurations/requirements.txt`
- Starts the app using `Procfile` command

Expected output:
```
Pushing app legal-eagle-ui to org gpm-chat_legal-eagle-bfrzhqe2 / space prod...
...
Waiting for app legal-eagle-ui to start...
name:              legal-eagle-ui
requested state:   started
routes:            legal-eagle-ui.cfapps.eu21.hana.ondemand.com
...
     state     since                  cpu    memory        disk
#0   running   2026-03-09T17:35:23Z   0.0%   128M of 512M   256M of 1G
```

## Step 3: Verify Deployment

1. **Access the Admin UI**:
   ```
   https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com
   ```

2. **Check application logs**:
   ```bash
   cf logs legal-eagle-ui --recent
   ```

3. **Check application status**:
   ```bash
   cf app legal-eagle-ui
   ```

## Step 4: Configure Job Scheduler Service (Optional)

For automated daily runs, set up SAP Job Scheduler:

### 4.1 Create Job Scheduler Service Instance

```bash
cf create-service jobscheduler standard legal-eagle-scheduler
```

### 4.2 Bind Service to Application

```bash
cf bind-service legal-eagle-ui legal-eagle-scheduler
cf restage legal-eagle-ui
```

### 4.3 Configure Jobs

Use the Job Scheduler Dashboard in BTP Cockpit to create jobs:

1. Go to: Space → Service Instances → `legal-eagle-scheduler` → Dashboard
2. Create a new job:
   - **Name**: `legal-eagle-daily-run`
   - **Action**: HTTP Endpoint
   - **URL**: `https://legal-eagle-ui.cfapps.eu21.hana.ondemand.com/api/trigger`
   - **Method**: POST
   - **Schedule**: `0 6 * * *` (daily at 6 AM UTC)
   - **Time Zone**: UTC

## Deployment Files Reference

### manifest.yaml
Defines Cloud Foundry deployment configuration:
- Application name, memory, instances
- Buildpack (Python)
- Start command (Gunicorn)
- Service bindings
- Routes

### Procfile
Defines the process to start the application:
```
web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 admin.app:app
```

### runtime.txt
Specifies Python version:
```
python-3.11.x
```

### .cfignore
Lists files/directories to exclude from deployment (similar to .gitignore)

## Common Commands

### View logs (real-time)
```bash
cf logs legal-eagle-ui
```

### View recent logs
```bash
cf logs legal-eagle-ui --recent
```

### Restart application
```bash
cf restart legal-eagle-ui
```

### Scale application
```bash
cf scale legal-eagle-ui -m 1G  # Increase memory
cf scale legal-eagle-ui -i 2   # Scale to 2 instances
```

### SSH into application container
```bash
cf ssh legal-eagle-ui
```

### Check environment variables
```bash
cf env legal-eagle-ui
```

### Update environment variable
```bash
cf set-env legal-eagle-ui VAR_NAME "value"
cf restage legal-eagle-ui
```

## Database Persistence

The SQLite database (`legal_eagle.db`) is stored in the application container. 

**Important**: By default, container filesystems are ephemeral. Data is lost when:
- App is restarted
- App is re-deployed
- Container crashes

For production, consider:
1. Using a persistent volume service on BTP
2. Migrating to a managed database service (PostgreSQL, HANA)
3. Regular database backups via scheduled jobs

## Troubleshooting

### App won't start
```bash
cf logs legal-eagle-ui --recent
```
Check for:
- Missing environment variables
- Python dependency errors
- Port binding issues

### Out of memory
```bash
cf scale legal-eagle-ui -m 1G
```

### Database locked errors
SQLite has limitations with concurrent writes. Consider:
- Using a managed database service
- Reducing concurrent job runs

### Cannot access admin UI
1. Check route is correct:
   ```bash
   cf app legal-eagle-ui
   ```
2. Check application is running:
   ```bash
   cf app legal-eagle-ui
   ```
3. Check logs for errors:
   ```bash
   cf logs legal-eagle-ui --recent
   ```

## Next Steps

1. ✅ Deploy application
2. ✅ Configure environment variables
3. ✅ Test admin UI access
4. ✅ Create profiles and configure sources
5. ✅ Set up Job Scheduler service
6. ✅ Configure scheduled jobs
7. ✅ Monitor first automated run
8. ✅ Set up database backup strategy

## Playwright Dynamic Rendering

Legal Eagle uses Playwright for dynamic rendering of JavaScript-heavy government websites.

### Components

1. **apt-buildpack**: Installs system libraries required by Chromium
   - Configuration file: `apt.yml`
   - Libraries: libnspr4, libnss3, libgbm1, etc.

2. **.profile Script**: Auto-installs Playwright browser on startup
   - Runs once per container start
   - Downloads Chromium browser (~167MB)
   - Caches in `/home/vcap/app/.cache/ms-playwright/`

3. **Memory**: 1GB allocated
   - Chromium requires significant memory
   - Deployment fails with 512MB

4. **Timeout**: 60 seconds
   - Increased from default 20s
   - Accommodates slow government websites

### Known Issue: Network Connectivity

**Problem**: Some government websites are unreachable from BTP Cloud Foundry network.

**Affected Sources**:
- Saudi government sites (e.g., `uqn.gov.sa`)
- Timeouts occur on both static HTTP and dynamic Playwright requests

**Root Cause**: Cloud provider IP ranges may be blocked by government infrastructure.

**Working Sources**:
- RSS feeds ✅
- Twitter API ✅
- Most other websites ✅

**Workaround**: Use hybrid architecture where BTP handles RSS/Twitter while local scheduler handles blocked sites.

## Support

For issues:
- Check CF logs: `cf logs legal-eagle-ui`
- Review BTP documentation: https://help.sap.com/docs/btp
- Check Cloud Foundry docs: https://docs.cloudfoundry.org
