## Current State: v3.31 — effective_date fix + per-item signal observability (2026-09-11)

### ✅ v3.31 COMPLETE (committed `bf7200e`, pushed to origin/main)

**v3.31 changes:**
- `agents/impact_gate.py` — hardcoded `effective_date:` field definition tightened: publication/approval/Gazette/decision dates forbidden unless article explicitly links them to entry into force.
- Per-item `[IMPACT]` log: `↳ [IMPACT] "Title…" → minor · change=no · prep=no · eff=none`
- Per-item `[RANK]` log: `↳ [RANK 3/Watch] "Title…" | gate: operational impact detected | glossary✓ rcm=net-new`
- Version annotation `(v3.1)` stripped from existing log message in `agents_controller.py`

**Root cause of OVP rank-5 false positive (the trigger for v3.31):**
- Impact Gate AI misclassified a policy program (OVP) as `regulatory_change_confirmed=true` — fix: Impact Rubric calibration (Admin > Config, user-managed)
- AI used publication date as `effective_date` — fix: tightened hardcoded prompt instruction (code change)
- Both fixes together prevent rank-5 from firing on non-enacted programs

---

## Current Pipeline Architecture (v3.31)

**Stages (in order):** Collect → Glossary Match → L2 Fetch → Impact Gate → Timing → Rank → Announce

| Stage | File | What it does |
|---|---|---|
| Collect | `agents/agents_controller.py` | RSS + URL sources → `news_items` |
| Glossary Match | `agents/glossary_match.py` | keyword/label match → `topic_label`, `glossary_match` |
| L2 Fetch | `agents/l2_fetcher.py` | full article fetch → `l2_summary` + `act_ref` (AI) |
| Impact Gate | `agents/impact_gate.py` | GPT-4o: `operational_impact` (0-3), `regulatory_change_confirmed`, `preparation_required`, `effective_date` |
| Timing | `agents/timing.py` | classifies `effective_date` → `timing_class` / `timing_signal` (0=none/past, 1=upcoming, 2=imminent ±30d) |
| Rank | `agents/news_ranker.py` | deterministic signal-fusion → `significance_rank` 1-5 |
| Announce | `agents/announcement_agent.py` | Select → Title → Cluster → Compose → Persist to `news_announcements` |

**Rank gate logic (deterministic, do not change):**
- Rank 5: `rc AND oi >= 2 AND tm == 2` (confirmed change + high impact + imminent)
- Rank 4: `rc AND pr` (confirmed change + prep required)
- Rank 3: `oi > 0` (operational impact detected)
- Rank 2: glossary/law match, no impact
- Rank 1: no match, no impact

**Grounding signals:** `glossary_match` (g), `law_match` (lm), `rcm_match` (rm 0/1/2), `authority_match` (am)

---

## UI Tabs

- **Review tab** — flat item list; each item shows rank badge, [IMPACT] signals, authority tag, l2_summary accordion
- **Announcement tab** — owns grouping; groups by Glossary Label (canonical, cross-language)
- **Configure tab** — sections: Profile, Glossary (label cards), RCM (topic + portal URL + history), Impact Rubric

**Impact Rubric** — per-profile setting in DB, editable via Admin > Configure > Impact Rubric. Injected as `{rubric}` into `_assess_one` prompt under `SCOPE RUBRIC:`. Controls which items are in-scope for impact assessment. **Note:** `effective_date` field definition is a separate hardcoded line in `impact_gate.py` — rubric does NOT reach it (code change required to modify it).

---

## Key Files

| File | Role |
|---|---|
| `app.py` | Flask app + `_DBLogger` (pipes all `print()` to run_logs DB + SSE stream) |
| `agents/agents_controller.py` | Pipeline orchestration, stage sequencing |
| `agents/impact_gate.py` | Impact Gate AI call; per-item [IMPACT] log |
| `agents/news_ranker.py` | Deterministic ranker; per-item [RANK] log |
| `agents/timing.py` | Effective date → timing_signal classifier |
| `agents/glossary_match.py` | Glossary Match stage |
| `agents/l2_fetcher.py` | L2 deep fetch + act_ref extraction |
| `agents/announcement_agent.py` | Announcement grouping + composition |
| `configurations/` | SAP AI Core client, DB schema/helpers, config loader |
| `tests/run_harness.py` | Test harness (do not auto-run; user must request) |

---

## V4 Roadmap

**V4 = Announce Agent + Impact Agent on existing SAP L2A capability-hub MCPs** (resources in `[[l2a-capability-hub-mcps]]`):
- Announce Agent → sanctioned L2S path (`l2s-prd-mcp`) — auto-creates + links + stamps Done
- Impact Agent → grounded on `glo-functional-spec-fitgap-generator` + `glo-taxonomy-kg` + SAP ABAP MCP → `news_announcements.impact_analysis_md`

---

## Key Rules

- **NEVER use X.Y.Z versions** — always X.Y only (e.g., v3.31, v3.32)
- **Always update memory-bank/activeContext.md** after every version ship
- **Single main branch** — commit + tag per version, no per-version branches (see `[[per-version-workflow]]`)
- **Do not change the deterministic Rank gates** — calibration issues go via Impact Rubric (Admin > Config)
- **Server restart after Python edits**: `launchctl kickstart -k gui/$(id -u)/com.legaleagle.admin` — assistant should run this, not tell the user

---

## Working Directory
`/Users/i077750/Documents/GitHub/legal-eagle`

## Key Environment Variables
- `LEGAL_EAGLE_SAP_AICORE_BASE_URL` — SAP AI Core API endpoint
- `LEGAL_EAGLE_SAP_AICORE_AUTH_URL` — OAuth2 auth endpoint
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_ID` — OAuth2 client ID
- `LEGAL_EAGLE_SAP_AICORE_CLIENT_SECRET` — OAuth2 client secret
- `LEGAL_EAGLE_SAP_AICORE_CHAT_DEPLOYMENT_ID` — Chat model (gpt-4o)
- `LEGAL_EAGLE_SAP_AICORE_EMBEDDINGS_DEPLOYMENT_ID` — Embeddings model
- `LEGAL_EAGLE_GMAIL_EMAIL` — Gmail sender address
- `LEGAL_EAGLE_GMAIL_APP_PASSWORD` — Gmail app password
- `LEGAL_EAGLE_AI_CACHE` — set to enable AI response caching in test harness (unset in production)
