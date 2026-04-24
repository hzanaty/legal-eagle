#!/bin/bash
# Smart auto-reload script for Legal Eagle Admin Server
# Watches Python files and restarts server automatically when they change

cd /Users/i077750/Documents/GitHub/legal-eagle || exit 1

echo "🚀 Starting Legal Eagle Admin Server with auto-reload..."

# Kill any existing instances
pkill -f "python.*admin/app.py" 2>/dev/null
pkill -f "watchmedo" 2>/dev/null

# Free up port 8080 if needed
lsof -ti:8080 | xargs kill -9 2>/dev/null

sleep 1

# Start server with watchdog auto-reload
# Watches: admin/*.py, agents/*.py, configurations/*.py
# Restarts server when any Python file changes
exec watchmedo auto-restart \
  --directory=. \
  --patterns="*.py" \
  --recursive \
  --ignore-patterns="*/test_*.py;*/__pycache__/*;*/.*" \
  -- python3 admin/app.py