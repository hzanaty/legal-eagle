## Update v2.32 (2026-06-28)

### Current Product State

**Stage 1 — Journalist**: Fully operational. Monitors regulatory sources, filters with AI, groups by theme, delivers bilingual email digests via BTP ANS or Gmail.

**Legal Repository** (v2.30): Global knowledge base linking detected regulations to SAP delivery artifacts. Tracks lifecycle NEW → SCOPING → ANALYZED → COMPLETE. Connects news items to JIRA EPICs, SAP Notes, PRDs, MindMaps.

**Active Profiles**: Saudi Arabia (SA/HCM), Turkey (TR/HCM), Spain (ES/HCM), UAE (AE/HCM), Greece (GR/HCM)

**Stage 2 — Lawyer**: Planned. Legal text interpretation, impact analysis.

**Strategic Vision**: See [Big_Picture.md](../Big_Picture.md) — 6-stage evolution to Virtual LPM.

---

## Update v2.4.0 (2026-01-13 18:49:55Z)

### v2.4.0 — Admin Run Page, Live Logs, Bulk Actions, and Credentials View (2026-01-13 18:49:55Z)

- Admin UI
  - New Run page (split layout): left pane has Confirm Run and 7-day Run History; right pane streams live logs via SSE and displays historical logs.
  - Cancel button: cooperative termination; finishes current step, sends email with collected results, marks status=Canceled.
  - Dashboard/Profile: Run buttons redirect to the Run page.
  - Bulk delete added for all sections: RSS, URL Sources, Twitter Accounts, Email Receivers, Glossary.
  - Email Receivers simplified: single email add field, per-row delete, and multi-select delete; legacy textarea path hidden.
  - Glossary simplified: terms list with single add + bulk add (one-per-line); controller auto-maps terms to profile LoB.
  - Global Credentials page enhanced: shows openai_api_key, full Gmail OAuth/App fields, and SMTP; values merge from DB + credentials.json (fallbacks).

- Controller & Agents
  - Controller refactored to unified URL sources runner (auto static with dynamic fallback; force_static/force_dynamic modes; optional sample_link).
  - Added run_profile_once(profile_id) for single-run execution used by Admin Run page.
  - stdout tee to DB for live log streaming; finish records status and email result.

- DB Schema & Helpers (SQLite)
  - New tables: runs (history/status/metrics), run_logs (sequenced log lines).
  - Helpers: create_run, start_run, finish_run, append_run_log, list_runs_for_profile, get_run, list_run_logs, set_cancel_requested, is_cancel_requested, prune_old_runs(days=7).
  - Existing tables in use: url_sources, global_credentials, audit_log.

- Retention
  - Automatic cleanup of runs and logs older than 7 days on dashboard access.

- UX Notes
  - Live logs via SSE with auto-scroll.
  - History list shows Status, Started/Finished times; selecting a run shows its logs on the right pane.
  - Simple design (no filters/search) per requirement.

# Product Context

## Purpose and Benefits
The Legal Eagle project aims to streamline the process of detecting and analyzing legal changes impacting SAP's localized products, particularly in HR and finance sectors. By automating the monitoring of legal updates, it alleviates the workload on Localization Product Managers and enhances decision-making through timely insights.

## Key Problems Addressed
- Manual monitoring of numerous legal sources is labor-intensive and error-prone.
- Stakeholders' need for reliable, rapid updates that inform strategic decisions.
- A need for a cohesive platform that integrates varying sources into a centralized solution.

## User Experience Goals
- Ensure clarity in information presentation to promote fast interpretation and action.
- Provide seamless integration that fits within existing product management workflows.
- Afford transparency and traceability of legal updates that align with SAP standards.
