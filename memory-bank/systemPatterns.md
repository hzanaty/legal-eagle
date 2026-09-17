# System Patterns

## System Architecture
The Legal Eagle system is designed around a modular architecture that ensures scalability and ease of maintenance. Agents are employed to parse, analyze, and notify stakeholders on relevant legal changes. A central controller orchestrates these agents to align with business deadlines and objectives.

## Key Technical Decisions
- Adopting a microservices approach with each agent handling specific tasks, ensuring single responsibility and simplicity.
- Utilizing Python for its robust libraries and community for data analysis and AI-driven insights.
- Integrating Google and OpenAI APIs to leverage existing capabilities for email notifications and content analysis.

## Design Patterns in Use
1. **Observer Pattern**: Used to notify stakeholders when significant legal updates are detected.
2. **Factory Pattern**: Employed for dynamically initializing different agents as per the project necessity.
3. **Singleton Pattern**: Maintains a single initialized configuration object across different components of the system to ensure consistency.

## Component Relationships
Each agent within the system operates independently but communicates through defined APIs and shared data structures. The agents_controller coordinates their execution order and maintains an overview of data flows and dependencies within the system's architecture.

---

## BTP Data Backup/Restore Workflow (v3.34) — CRITICAL PATTERN

### THE PROBLEM
- BTP Cloud Foundry containers are **ephemeral** — database is local to container filesystem
- On `cf push`, `cf restart`, or `cf restage`, new container may spin up on different Diego Cell
- Old container's database is **LOST** → All config and production data gone
- Users have to reconfigure everything from scratch

### THE SOLUTION: Three-Script Approach (NO API ENDPOINTS)

**Uses only `cf` CLI commands** to directly manage database files. **NO HTTP API endpoints in `admin/app.py`.**

### EXACT WORKFLOW (MANDATORY)

```bash
# Step 1: BACKUP (before any deployment)
python3 scripts/btp_backup.py --output backup.json
# → Downloads config.db from BTP container
# → Exports all 21 tables to local JSON file

# Step 2: DO YOUR DEPLOYMENT
cf push
# or
cf restart legal-eagle-ui

# Step 3: CHECK if data was lost (MANDATORY)
python3 scripts/btp_check.py --file backup.json
# → Downloads current BTP database
# → Shows comparison table:
#     Table         | Backup | BTP Now | Status
#     profiles      | 4      | 4       | ✅ OK
#     rss_feeds     | 12     | 0       | ❌ LOST
#     news_items    | 500    | 0       | ❌ LOST
#     ...
# → Recommendation: restore if >50% rows lost

# Step 4: RESTORE only if needed
python3 scripts/btp_restore.py --file backup.json
# → Asks confirmation: "Type 'restore' to proceed"
# → Downloads current BTP db
# → Imports backup data into local copy
# → Uploads modified db back to BTP
# → Says: "Restart BTP for changes to take effect"
cf restart legal-eagle-ui
```

### THE THREE SCRIPTS (SEPARATE, EACH DOES ONE JOB)

| Script | Input | Does | Output |
|--------|-------|------|--------|
| `btp_backup.py` | BTP app running | `cf download` → export to JSON | Local `btp_backup_YYYYMMDD_HHMMSS.json` |
| `btp_check.py` | Backup JSON file | `cf download` BTP → compare vs backup | Comparison table + recommendation |
| `btp_restore.py` | Backup JSON file | Download current → import backup → upload | "Restart BTP for changes to take effect" |

### KEY DESIGN POINTS (NEVER CHANGE)

1. ✅ **NO API endpoints** — Uses only `cf` CLI (`cf download`, `cf upload-file`)
2. ✅ **Check step is MANDATORY** — Shows comparison table, user decides
3. ✅ **Confirmation required** — Restore asks "Type 'restore'" before proceeding
4. ✅ **Separate scripts** — Each script has ONE clear job, no mixing
5. ✅ **Local SQLite processing** — Uses temp databases for speed
6. ✅ **Transparent** — User sees exactly what data was lost/kept

### WHY THIS DESIGN

- **Simpler**: No HTTP endpoints to maintain, debug, or secure
- **Faster**: Local processing, no network latency
- **Safer**: Check step prevents accidental overwrites
- **Transparent**: User can see the comparison before deciding
- **Reliable**: Uses only `cf` CLI, no custom endpoints

### WHEN TO USE

| Scenario | Commands |
|----------|----------|
| Before `cf push` | `btp_backup.py` |
| Before `cf restart` | `btp_backup.py` |
| Before `cf restage` | `btp_backup.py` |
| After any of above | `btp_check.py` (check if lost) |
| If data lost | `btp_restore.py` |

---

## 🔴 GOLDEN RULES: Command Execution (MUST FOLLOW EVERY TASK — NO EXCEPTIONS)

These rules exist because violating them causes commands to hang as "Pending" or "Skipped" in Cline, requiring the user to interrupt manually.

---

### 🥇 GOLDEN RULE #1: ALWAYS use `gtimeout` — NEVER wait more than 30 seconds

**`timeout` does NOT exist on macOS. Use `gtimeout` (from GNU coreutils, installed at `/opt/homebrew/bin/gtimeout`).**

Every command that could potentially hang MUST use `gtimeout`:
```bash
gtimeout 30 curl -s http://localhost:8080/admin
gtimeout 30 python scripts/some_script.py
gtimeout 10 pip install something
```

If a command gets stuck (Pending/Skipped), **immediately stop and report to the user** — do NOT keep waiting.

---

### 🥇 GOLDEN RULE #2: For background processes, ALWAYS wrap with `gtimeout`

Direct background commands (`&`, `nohup`, `disown`) get stuck as **"Pending" or "Skipped"** in Cline.

**WRONG (gets stuck forever):**
```bash
nohup bash scripts/restart_admin.sh > /tmp/admin_server.log 2>&1 & disown
python admin/app.py > /tmp/server.log 2>&1 &
```

**CORRECT — wrap background commands with `gtimeout`:**
```bash
gtimeout 10 bash -c 'python admin/app.py > /tmp/admin_server.log 2>&1 & echo "PID: $!"'
gtimeout 10 bash -c 'nohup bash scripts/restart_admin.sh > /tmp/admin_server.log 2>&1 & echo "PID: $!"'
```

The `gtimeout` wrapper ensures Cline gets a result back quickly and doesn't hang.

---

### 🥇 GOLDEN RULE #3: Only run commands that complete and exit (or are wrapped with gtimeout)

Safe commands for Cline (no wrapper needed):
- `echo`, `cat`, `grep`, `ls`, `git`, `sqlite3` queries, short Python scripts that exit

Require `gtimeout` wrapper:
- `curl` calls, `pip install`, any network operation
- Background process starts (servers, watchers)
- Any script that might take >5 seconds

**Never run through Cline without gtimeout:**
- Flask/Django servers without `gtimeout` wrapper
- Watchers, schedulers, or any infinite loop process

---

### 🥇 GOLDEN RULE #4: If a command gets Pending or Skipped — report immediately
Do NOT wait. Do NOT retry the same command. Immediately tell the user:
- What command got stuck
- What the likely cause is
- What the user needs to do manually

---

### Correct Server Restart Sequence

```bash
# Command 1: Kill existing server
lsof -ti tcp:8080 | xargs kill -9 2>/dev/null; echo "done"

# Command 2: Start server (wrapped with gtimeout)
gtimeout 10 bash -c 'nohup bash scripts/restart_admin.sh > /tmp/admin_server.log 2>&1 & echo "PID: $!"'

# Command 3: Verify server is up
gtimeout 10 curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/admin
```

Each command is a **separate** `execute_command` call. Never combined.

---

### macOS Note: `timeout` vs `gtimeout`
- `timeout` = Linux only — **NOT available on macOS** (returns "command not found")
- `gtimeout` = macOS GNU coreutils — **installed at `/opt/homebrew/bin/gtimeout`**
- Always use `gtimeout` on this machine

### Why the Server Keeps Going Down
The Flask admin server (`admin/app.py`) runs on port 8080. It is a development server started manually. It does NOT auto-start on boot. If it goes down, use the restart sequence above.

### Auto-Reload is Enabled
`scripts/start_admin.sh` uses `FLASK_DEBUG=1` and `FLASK_ENV=development`. Flask will **automatically reload** when Python files change. For most code changes, no manual restart is needed.