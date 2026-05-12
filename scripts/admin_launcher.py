#!/usr/bin/env python3
"""
Launcher wrapper for the Legal Eagle admin server.
Truncates launchd log files before starting to prevent exit code 78 on macOS Sequoia+.
"""
import os
import sys

ROOT = "/Users/i077750/Documents/GitHub/legal-eagle"

for log in [
    os.path.join(ROOT, "outputs", "admin-stdout.log"),
    os.path.join(ROOT, "outputs", "admin-stderr.log"),
]:
    try:
        open(log, "w").close()
    except OSError:
        pass

os.execv(
    sys.executable,
    [sys.executable, os.path.join(ROOT, "admin", "app.py")],
)
