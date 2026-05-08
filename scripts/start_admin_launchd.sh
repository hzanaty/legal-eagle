#!/bin/bash
# Wrapper for launchd (kept for reference; the active plist calls Python directly)
cd /Users/i077750/Documents/GitHub/legal-eagle || exit 1

if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    export "$line" 2>/dev/null
  done < .env
fi

export PYTHONPATH=/Users/i077750/Documents/GitHub/legal-eagle
export PYTHONUNBUFFERED=1
export FLASK_ENV=production
export HOME=/Users/i077750

exec /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 admin/app.py
