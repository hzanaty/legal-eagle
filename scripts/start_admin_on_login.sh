#!/bin/bash
# Simple startup script for Legal Eagle Admin Server
# This runs automatically when you log in

cd /Users/i077750/Documents/GitHub/legal-eagle || exit 1

# Kill any existing instance
pkill -f "python.*admin/app.py" 2>/dev/null

# Start the server in background
nohup python3 admin/app.py > outputs/admin-stdout.log 2> outputs/admin-stderr.log &

# Save PID
echo $! > outputs/admin.pid

echo "✅ Legal Eagle Admin Server started (PID: $(cat outputs/admin.pid))"
echo "🌐 Access at: http://localhost:8080/admin"