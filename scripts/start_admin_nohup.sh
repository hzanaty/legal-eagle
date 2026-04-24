#!/bin/bash
# Legal Eagle Admin - Login startup script
# Auto-starts Flask admin server at macOS login
set +H  # disable history expansion (prevents ! errors in .env values)

PROJ=/Users/i077750/Documents/GitHub/legal-eagle
LOGDIR="$PROJ/outputs"
PIDFILE="$LOGDIR/admin.pid"

# Kill any existing instance
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    kill "$OLD_PID" 2>/dev/null
    sleep 1
    rm -f "$PIDFILE"
fi

# Kill any stray app.py processes
pkill -f "admin/app.py" 2>/dev/null
sleep 1

export PYTHONPATH="$PROJ"
export PYTHONUNBUFFERED=1
export FLASK_ENV=production
export FLASK_DEBUG=0
export HOME=/Users/i077750

# Load .env safely (set +H disables ! expansion, IFS= preserves spaces)
if [ -f "$PROJ/.env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        [[ "$line" != *=* ]] && continue
        export "$line" 2>/dev/null || true
    done < "$PROJ/.env"
fi

# Start Flask in background, redirect logs
cd "$PROJ"
nohup /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    "$PROJ/admin/app.py" \
    >> "$LOGDIR/admin-stdout.log" \
    2>> "$LOGDIR/admin-stderr.log" &

echo $! > "$PIDFILE"
echo "$(date): Legal Eagle Admin started (PID=$(cat $PIDFILE), port=8080)" >> "$LOGDIR/admin-startup.log"
