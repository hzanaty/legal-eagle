#!/usr/bin/env python3
"""
Legal Eagle Admin Server - Python launcher for macOS launchd.
Replaces bash wrapper to avoid Palo Alto / endpoint-security posix_spawn restrictions.
Loads .env, sets environment, then exec-replaces itself with the Flask app.
"""
import os
import sys

BASE = '/Users/i077750/Documents/GitHub/legal-eagle'
os.chdir(BASE)

# Required environment variables
os.environ['PYTHONPATH'] = BASE
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = '0'
os.environ.setdefault('HOME', '/Users/i077750')

# Load .env file (safe line-by-line parser — no shell quoting or ! expansion issues)
env_file = os.path.join(BASE, '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key, val = key.strip(), val.strip()
            if key:
                os.environ.setdefault(key, val)

# exec-replace this process with the Flask app (equivalent to bash exec)
python = sys.executable
app_path = os.path.join(BASE, 'admin', 'app.py')
os.execv(python, [python, app_path])
