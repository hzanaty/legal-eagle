#!/bin/bash
LOGFILE=/tmp/le_launchd_debug.txt
echo "$(date): started PID=$$" >> "$LOGFILE" 2>&1
cd /Users/i077750/Documents/GitHub/legal-eagle
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    export "$line" 2>/dev/null
  done < .env
fi
export PYTHONPATH=/Users/i077750/Documents/GitHub/legal-eagle
export PYTHONUNBUFFERED=1
export FLASK_ENV=development
export FLASK_DEBUG=1
export HOME=/Users/i077750
echo "$(date): exec python" >> "$LOGFILE" 2>&1
exec /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/i077750/Documents/GitHub/legal-eagle/admin/app.py