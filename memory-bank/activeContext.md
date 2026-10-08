## Current State: v3.35 — Dated URL sources fix (2026-10-08)

### ✅ v3.35 COMPLETE

**v3.35 changes (Dated URL sources + lifecycle docs):**
- `agents/url_sources_runner.py` — `_scrape_single_url()` helper extracted; `scrape_url_source_with_config()` now handles `url_date_template`: generates N dated URLs (default 30), scrapes each, URL date is always authoritative (`it["date"] = date_str` unconditional)
- `admin/app.py` — `/api/simulate` composes yesterday's dated URL when `url_date_template` is in payload
- `admin/templates/profile.html` — Simulate button forwards `url_date_template` to `startSimulation()`
- `Roadmap/lifecycle.html` — "Select Profile" → "Run Orchestrator"; `url_date_template` column in URL Scrape detail; `url_date_template` in Sources setup detail

---

### ✅ v3.34 COMPLETE

**v3.34 changes (BTP Data Persistence):**
- `admin/app.py` — new endpoints: `/api/export-all` (GET) + `/api/import-all` (POST)
  - Export ALL database tables (config + production) as JSON
  - Import ALL tables from JSON backup (clears existing data first)
  - Both protected by admin secret (query param or Bearer token)
- `scripts/btp_backup.py` — local CLI script to export BTP database to JSON file
  - Usage: `python btp_backup.py --url <btp-url> --secret <admin-secret> --output backup.json`
  - Auto-generates timestamped filename if not specified
- `scripts/btp_restore.py` — local CLI script to import backup JSON to BTP
  - Usage: `python btp_restore.py --file backup.json --url <btp-url> --secret <admin-secret>`
  - Requires confirmation before restoring (dangerous operation)

**Problem Solved:**
- BTP uses ephemeral SQLite → data lost on restart/restage/push
- Solution: Export before restart, import after restart
- Workflow: `btp_backup.py` → `cf restart` → `btp_restore.py`

---

### ✅ v3.33 COMPLETE

**v3.33 changes:**
- `admin/templates/run_status.html` — history pills now prefix `#N ·` (run ID) so each pill is uniquely identifiable.
- `agents/health_check.py` — `run_health_checks()` accepts `selected_urls`; skips sources not selected for the current run.
- `agents/agents_controller.py` — passes `selected_urls` to health check; stage preambles include item count (e.g., `🌐 L2 Fetch: 2 item(s) —…`).
- `admin/app.py` — `add_rss()` rejects relative URLs (no `http://` scheme) with a flash error.
- `agents/rss_parser.py` — `feedparser` bozo failures raise `RuntimeError`; delta anchor preserved on feed failure.
- `agents/l2_fetcher.py` — `run_l2_fetch()` emits per-item progress: `↳ [i/N] "title…" — OK (laws=X, refs=Y)`.

---

### ✅ v3.32 COMPLETE

**v3.32 changes:**
- `agents/compare_news.py` — same-run act_ref match now routes as update+repeated instead of duplicate.
- `agents/compare_news.py` — removed hardcoded `WEEKLY_BASELINE_DAYS = 7`; uses `get_baseline_days()` per profile.
- `configurations/config_loader.py` — added `get_baseline_days(profile_id)`.
- `agents/source_simulator.py` — date detection tier 3: content-based parse.
- `Roadmap/v3/xanadu-gov-site/` — Xanadu demo site with REPEATED validation articles.

---

## Current Pipeline Architecture (v3.33)
- `agents/compare_news.py` — `reconcile_by_act_ref` same-run branch: was marking second article with same `act_ref`/`law_id` as `dedup_status = "duplicate"`. Now sets `dedup_status = "update"` + `_repeated_followup = True` + `repetition_status = "repeated"`. Root cause: reconcile runs after L2 fetch sets `act_ref`, so two articles about the same law in one run triggered the duplicate branch.
- `agents/compare_news.py` — removed `WEEKLY_BASELINE_DAYS = 7` hardcoded constant; replaced with `_BASELINE_DAYS_DEFAULT = 7` (private fallback) + per-profile lookup via `get_baseline_days()`.
- `configurations/config_loader.py` — added `get_baseline_days(profile_id)`: reads `"baseline_days"` from the per-profile `settings` table, falling back to 7.
- `agents/source_simulator.py` — date detection tier 3: content-based parse using `parse_date_string` when no `<time>` tag or class-name hint is present.
- `Roadmap/v3/xanadu-gov-site/` — full Xanadu Republic of Xanadu Ministry of HR demo site: 7 articles, real file:// URLs, including the two Royal Decree No. 18/2026 articles that validate the REPEATED fix.

**Root cause of REPEATED/DUPLICATE misclassification (the trigger for v3.32):**
- Two articles about Royal Decree No. 18/2026 (Aug 20 original + Sep 5 reminder) both passed compare_news as "new" (different fingerprints, empty baseline).
- L2 fetch set the same `act_ref` on both. `reconcile_by_act_ref` fired, found the Sep 5 article as a same-run match, and wrongly set `dedup_status = "duplicate"`.
- Fix: same-run act_ref matches are follow-ups, not copies — route as "update" + "repeated".

---

### ✅ v3.31 COMPLETE (committed `bf7200e`, pushed to origin/main)

**v3.31 changes:**
- `agents/impact_gate.py` — hardcoded `effective_date:` field definition tightened.
- Per-item `[IMPACT]` and `[RANK]` logs added.

---

## Current Pipeline Architecture (v3.33)

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
