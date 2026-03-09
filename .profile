#!/bin/bash
# Cloud Foundry startup script - runs before the app starts
# This script installs Playwright browsers for dynamic content rendering

echo "======================================"
echo "Legal Eagle - Installing Playwright Browsers"
echo "======================================"

# Install Playwright Chromium browser (without system deps, CF doesn't allow sudo)
echo "[$(date)] Installing Playwright Chromium..."
python -m playwright install chromium 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date)] ✅ Playwright Chromium installed successfully"
else
    echo "[$(date)] ⚠️  Playwright installation failed"
    exit 1
fi

# Set Playwright environment variables
export PLAYWRIGHT_BROWSERS_PATH=/home/vcap/app/.cache/ms-playwright

echo "[$(date)] Playwright setup complete"
echo "======================================"
