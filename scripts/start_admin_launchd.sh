#!/bin/bash
# Wrapper script for launchd to start admin server
# This ensures all environment variables are properly set

cd /Users/i077750/Documents/GitHub/legal-eagle || exit 1

# Set Python path
export PYTHONPATH=/Users/i077750/Documents/GitHub/legal-eagle
export PYTHONUNBUFFERED=1
export FLASK_ENV=production

# Log startup
echo "[$(date)] Starting admin server via launchd..." >&2

# Start the admin server (Flask will use debug=True from app.py but without reloader in production)
exec /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 admin/app.py
