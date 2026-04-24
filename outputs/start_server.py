#!/usr/bin/env python3
"""Simple server starter - writes PID and starts Flask app."""
import os
import sys
import subprocess

BASE = '/Users/i077750/Documents/GitHub/legal-eagle'
log_file = os.path.join(BASE, 'outputs', 'server_run.log')
pid_file = os.path.join(BASE, 'outputs', 'server.pid')

# Load .env
env = dict(os.environ)
env_path = os.path.join(BASE, '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            k, v = k.strip(), v.strip()
            if k:
                env.setdefault(k, v)

env['PYTHONPATH'] = BASE
env['PYTHONUNBUFFERED'] = '1'

with open(log_file, 'w') as log:
    proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE, 'admin', 'app.py')],
        cwd=BASE,
        env=env,
        stdout=log,
        stderr=log
    )

with open(pid_file, 'w') as f:
    f.write(str(proc.pid))

print(f"Started Flask server with PID {proc.pid}")
print(f"Log: {log_file}")