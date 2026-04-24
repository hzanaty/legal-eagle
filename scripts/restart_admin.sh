#!/bin/bash
# restart_admin.sh — Kills any process on port 8080, then starts the admin server fresh.
# Usage: bash scripts/restart_admin.sh

PORT=8080
LOGFILE=/tmp/le_launchd_debug.txt

echo "🔄 Restarting Legal Eagle admin server on port $PORT..."

# Kill anything holding the port
PIDS=$(lsof -ti tcp:$PORT 2>/dev/null)
if [ -n "$PIDS" ]; then
  echo "⛔ Killing existing process(es) on port $PORT: $PIDS"
  echo "$PIDS" | xargs kill -9 2>/dev/null
  sleep 1
else
  echo "✅ Port $PORT is free."
fi

# Double-check the port is now free
RETRY=0
while lsof -ti tcp:$PORT > /dev/null 2>&1; do
  RETRY=$((RETRY + 1))
  if [ $RETRY -gt 5 ]; then
    echo "❌ Port $PORT is still in use after 5 retries. Aborting."
    exit 1
  fi
  echo "⏳ Waiting for port $PORT to be released... ($RETRY/5)"
  sleep 1
done

echo "🚀 Starting admin server..."
cd /Users/i077750/Documents/GitHub/legal-eagle

# Load .env
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

echo "$(date): restart_admin.sh started PID=$$" >> "$LOGFILE" 2>&1

exec /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/i077750/Documents/GitHub/legal-eagle/admin/app.py