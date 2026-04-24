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