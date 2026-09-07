# Legal Eagle v3 Demo — Bug & Maintenance Log

Defects found while building and rehearsing the v3 team demo, plus the corrective action for
each. Fill new rows during rehearsals (see `DEMO_RUNBOOK.md`) — one row per issue found while
driving the runbook end-to-end.

**Status legend:** 🔴 open · 🟡 in progress · 🟢 fixed · ⚪ won't-fix / accepted

| ID | Beat/Step | Symptom | Root cause | Corrective action | Status |
|----|-----------|---------|------------|-------------------|--------|
| B1 | Beat 5 (Review) | "REPEATED at rank 4" was impossible — a reworded re-announcement was tagged `new`/`update` (never `repeated`), and any exact re-publish became `duplicate` → rank 0. | `repetition_tag="repeated"` required an **exact-key** baseline match (guid/url/hash/fingerprint) with `repetition_count ≥ 3`; exact matches also forced `duplicate` → Tier-0 rank 0, so the `+1` REPEATED elevation was dead code. | Carry the **cosine-matched** baseline's `repetition_count` into the semantic `update` path in `agents/compare_news.py`, so a reworded re-announcement is tagged `repeated` while staying non-duplicate; the existing `+1` elevation in `news_ranker.py` then lifts the rank-3 base to 4. Verified harness v3.0–v3.6, 0 regressions. | 🟢 fixed |

## Corrective actions applied (changelog)

### #1 — REPEATED for semantic re-announcements  *(B1)*
- **File:** `agents/compare_news.py` (12 insertions, 2 deletions) — no change to `news_ranker.py`.
- **What:** In the semantic branch, when an item classifies as `update` (cosine 0.72–0.80 + a
  glossary-bearing delta), read the cosine-matched baseline's `repetition_count` and fold it into
  the repetition decision (`prior_count = max(exact_prior_count, semantic_prior_count)`).
- **Why safe:** `dedup_status`/classification is unchanged (existing `new`/`duplicate`/`update`
  assertions unaffected); only `repetition_tag`/`repetition_count` gain the semantic path. The
  v3.2 `repeated` assertions (R1–R3) are exact-key duplicates and are untouched.
- **Verification:** `python3 tests/run_harness.py --version v3.{0..6}` all exit 0. (The lone
  `[FAIL]` on the C4 `authority_status=inferred` assertion is a pre-existing `requires_ai` item
  set by the untouched ATTRIBUTE stage; non-fatal, unrelated to this change.)

---

## Watch-list (things likely to bite during rehearsal — verify, don't assume)

- **Cosine band sensitivity (flagship).** ✅ **Verified with live AI Core (2026-09-06)** on the
  **full article body** (what the URL-source scraper delivers): cosine(flagship, baseline) =
  **0.7948** — inside the 0.72–0.80 "update" band → `dedup_status=update`, `repetition_tag=repeated`,
  `significance_rank=4`. (An earlier teaser-only test gave 0.7696.) Embeddings can drift slightly;
  if you edit the flagship body (`xanadu-gov-site/public/news/social-insurance-rate-countdown.html`)
  or `BASELINE_ITEM` in `scripts/prep_xanadu_demo.py`, re-verify. (≥0.80 → duplicate/rank 0;
  <0.72 → new/no REPEATED.)
- **Rank 4 vs 5.** ✅ In the live verification the Tier-2 AI returned ≤3, so base stayed 3 and the
  `+1` elevation landed it at exactly **4** (`rank_tier=tier1`, "[repeated +1]"). If a future run
  shows 5 and you need a guaranteed 4, add a deterministic clamp to the REPEATED elevation in
  `agents/news_ranker.py`. → not needed as of the last check.
- **URL-source scraping (local site).** The gov site must be **served over HTTP**
  (`python3 -m http.server`), not a file path — Legal Eagle fetches with `requests.get`. Add the
  site as a URL source and **do NOT run the Source Simulator** (that stores list-page selectors →
  snippet-only content; leaving it un-simulated uses the full-body scraper). Confirm at rehearsal
  that the run discovers all 5 article links and pulls full bodies; if link discovery misses,
  set `sample_link` (one article URL) and/or `read_more_label="Read more"` on the URL source.
- **Latent bug (not on the demo path):** `reset_review_data()` in `configurations/db.py` and
  `rerank_items_for_profile()` in `agents/news_ranker.py` both query `news_items.run_id`, a column
  that does not exist → `OperationalError`. The demo prep script deliberately resets by
  `profile_id` instead and does not call these. Left as-is (out of demo scope).
- **Deferred (known, not demo-blocking):** the `update` branch in `agents/compare_news.py` does not
  register `url`/`source_id` in the intra-run seen-sets, so if the *same* article ever arrived from
  two channels in one run the copies would not consolidate. Not exercised by this demo (Xanadu uses
  a single URL source). A fuller cross-time date-window DUPLICATE-vs-REPEATED model is future work.
- **Email send.** A live Xanadu run may send a real digest email to the configured receiver.
  Confirm that's intended before running in front of the audience.

## Enhancement backlog (deferred — not built in this demo effort)

- **Test mode should be a no-persist dry-run.** Intended semantics: a high-level news review that
  writes **nothing** to the DB and sends no email. Current behaviour is a half-state: Test mode
  (`skip_email=True`, Run-tab toggle) still persists `news_items` via compare→rank→tag, but takes
  the preview branch in `agents/agents_controller.py` (~L744) that uses the old `generate_email_html`
  and never calls `generate_digest`, so `news_announcements` is **not** written → the Announcements
  view + Preview for RCM are empty in Test mode. **Demo workaround:** run Run 1 with **Test mode OFF**
  (real run; digest email goes to the presenter's own address). A true no-persist mode is non-trivial
  (persistence is inline across `compare_news.add_news_item`, the tagger, the ranker, and
  `generate_digest`) and needs its own design + harness pass. Deferred by decision on 2026-09-06.

---

## Run-1 findings (2026-09-06) — confirmed by code trace + Playwright + a clean temp-DB reproduction

**Context:** first live Xanadu run(s) via the local URL source. Symptoms: grey stage stepper, empty
log pane, "Digest failed", history pill shows no log, and Review had 6 items all rank-0/duplicate.
Investigation traced each to root cause. `run_logs` **is** populated (47–48 rows/run) and the SSE
endpoint works — the gaps are in the frontend + a few plumbing spots. A clean single run (reset →
one run, temp DB) reproduced the real behaviour below.

| ID | Symptom | Root cause | Corrective action | Severity |
|----|---------|------------|-------------------|----------|
| R1 | **Flagship is `new`/rank 3, NOT REPEATED/rank 4** | The URL source was **simulated** (`simulation_status=success`, `container_selector=li.release-item`), so runtime uses `scrape_url_source_with_config` → **snippet-only** content (title/link/date, ~100–150 chars). Thin snippet vs the full-paragraph baseline → cosine **below** the 0.72 update band → classified `new` (no REPEATED, no `+1`). | Use the **full-body** path: clear the source's simulator columns (`container_selector`/`simulation_status` NULL) or delete + re-add the URL source **without** running Source Simulator. Then flagship gets the full body → cosine ~0.79 → `update`/`repeated` → rank 4. Verify the legacy scraper discovers all 5 `a.read-more` links and pulls full bodies from the local site. | **demo-blocking** |
| R2 | Review filled but History shows "0 items"; runs recorded but counts 0 | `_worker`/`run_profile_once` don't record item counts into `runs` (`rss_count/url_count/grouped_count` stay 0). | Populate run metrics in `finish_run(... metrics=...)` (counts of fetched/ranked/eligible). | medium |
| R3 | Live run: stage stepper stays grey; log pane empty | `admin/templates/run_status.html` never opens an `EventSource` to `/admin/runs/<id>/stream`; stepper pills are static grey with no updater; no machine-readable stage signal is produced by `run_profile_once` (prints only). | Add client JS to stream `/admin/runs/<id>/stream` into the log pane; drive the stepper (min: light "Done" on the `done` event / parse known log markers; full: emit stage events from the pipeline). | high (user-visible) |
| R4 | Clicking a History pill shows no log | `admin_profile_runs` loads only run metadata (`get_run`) for `?run_id=`, never `list_run_logs`; template has no element/JS to render a past run's log. | On `?run_id=`, load `list_run_logs(run_id)` and render it (and reflect stored status/email badge). | high (user-visible) |
| R5 | EMAIL "Digest failed" badge | The v2 digest follow-on (`_digest_worker` → `send_digest` → `generate_digest`) fails at the **SMTP send** to real Gmail (`email_status='FAILED'`). `generate_digest` writes `news_announcements` **and commits BEFORE** the send, so announcements survive the failure. | Non-blocking for Review/Announcements/RCM. Options: configure/repair Gmail SMTP; or decouple — treat announcement generation as success independent of send; or suppress the scary badge when announcements were written. | low (cosmetic for demo) |
| R6 | Re-running without reset → all items become rank-0 `duplicate`; no announcements | Expected dedup: runs 2–3 exact-match run-1's saved rows (same url/hash) → `duplicate` → rank 0 → not email-eligible → `generate_digest` writes nothing. | Process: **reset (prep) before EACH run and run once.** Already in `DEMO_RUNBOOK.md`. Optionally add a guard/warning. | process |
| R7 | One item creates 2 announcements | Flagship matched **two** glossary terms (`contribution rate` + `social insurance`) → `topic_label` JSON array with 2 entries → `generate_digest` buckets per label → 2 announcement rows for the same item. | Optional: de-duplicate announcements per item, or narrow the flagship's glossary matches to one primary term. | low (cosmetic) |

**Clean single-run reproduction (temp DB, no email, full-body path NOT used because source was simulated):**
5 items scored, 1 eligible (flagship rank 3), `generate_digest` created announcements — so on a
clean run the Announcements view + Preview for RCM DO populate. The rank-4 REPEATED outcome requires
fixing **R1** (full-body path).

### Corrective actions applied (2026-09-06) — all verified

| ID | Fix | Files | Verified |
|----|-----|-------|----------|
| R1 | `prep_xanadu_demo.py` now **normalizes the Xanadu URL source to the full-body path** each run (clears `container_selector`/`simulation_status`/`sample_link`, sets `read_more_label='Read more'`); added `og:title` to each article so the scraper picks the real headline. | `scripts/prep_xanadu_demo.py`, `xanadu-gov-site/public/news/*.html` | Temp clean run: **5 articles full-body**, flagship `update`/`repeated`/**rank 4**; titles correct. Applied to `config.db`. |
| R2 | Record run item counts: `filtered_count` = non-duplicate `news_items`, `grouped_count` = announcements. History pill no longer shows "0 items". | `admin/app.py` (`_worker`) | Code; confirm on next live run. |
| R3 | Wired `run_status.html` to `EventSource /admin/runs/<id>/stream`: live **log pane** + **stage stepper** advance (log-marker driven) + `done`. | `admin/templates/run_status.html` | Playwright: **54 log lines rendered, all 7 stages → done**. |
| R4 | History-pill view now streams the selected run's stored log + completed stepper (same EventSource path; run already redirects with `run_id`). | `admin/templates/run_status.html` | Playwright: past run #1 log + stepper rendered. |
| R5 | **Root cause was a `NameError`**: `_digest_worker` used an undefined `d_conn`, so `generate_digest` never ran → announcements never written AND every digest showed "failed". Fixed the connection; if announcements are written but SMTP send fails, show **"Digest ready — email not sent"** (`GENERATED`) instead of "Digest failed". | `admin/app.py`, `admin/templates/run_status.html` | Code; `generate_digest` announcement-writing confirmed in temp repro; confirm badge on next live run. |
| R6 | Reset-before-each-run enforced by prep (also normalizes source). Runbook already documents it. | `DEMO_RUNBOOK.md`, `scripts/prep_xanadu_demo.py` | n/a (process) |
| R7 | De-duplicate announcements: an item matching multiple glossary terms is announced **once** (first topic), not once per term. | `agents/email_composer.py` | Harness v3.0–v3.6 green (0 regressions). |
| — | Transient **500** on the Start→redirect (recovered on reload) | Jinja `truncate` ran on `run.started_at` which is **None** for a just-created (Queued) run; `default('')` doesn't catch None → `TypeError`. | None-safe render `(run.started_at or '')` in the history pill. | ✅ reproduced Queued/NULL run → now 200 |
| — | Extra hardening | Concurrent Run page/SSE reads during the worker's log writes could hit "database is locked". | `busy_timeout=5000` in `get_connection`. | Harness green |

**Still to confirm on a live (Test mode OFF) run:** R2 counts + R5 `GENERATED` badge + announcements
created via the app's digest worker (the temp reproduction confirmed the underlying `generate_digest`
works; the `d_conn` fix removes the crash that blocked it in the app).

## P1–P8 corrections APPLIED + verified (2026-09-06)

All implemented and confirmed by a clean live run (Test off, Send off) + harness v3.0–v3.6 (0 regressions):
- **P1** log coloring severity-based — `errors=0`/warnings no longer red (`admin/templates/run_status.html`).
- **P2** glossary-gap line reads `✅ 0 gaps` when none (`agents/agents_controller.py`).
- **P6** removed the vestigial SOURCE (Accepted/Filtered) filter + counter (`review_news.html`) — confirmed `filtered_news` unused.
- **Attribution** URL items now attributed by host → `publisher`/`authority_id` populated (status `configured`);
  `list_url_sources` returns publisher/authority; `prep_xanadu_demo.py` stamps Ministry of Human Resources;
  `agents/agents_controller.py` builds a URL-source config; `agents/authority_attributor.py` matches by host + guarantees a publisher.
- **P7** source label "Name · Type" (e.g. **Ministry of Human Resources · URL**) in Review item cards + Sources rows.
- **P4** email digest now groups **by Topic → Announcement → Sources** (mirrors Review); authority wrapper removed → no "Other Topics".
- **P8+P5** single email path: the pipeline no longer sends (removed the duplicate legacy v1 send from the admin path);
  a new Run-tab **"Send email digest"** toggle (independent of Test mode) controls the one SMTP send; the digest is always
  **generated** (announcements written) so Review/RCM work even when not sending; email pre-checks follow the toggle;
  badge reflects the one real result (`GENERATED` when not sent). Verified: `email_status=GENERATED`, 1 announcement, no duplicate email.
- **Rank label** rank 2 renamed "Background" → **"Signal"** (Review filter + spec).
- Earlier: started-run 500 (None `started_at`) fixed; `busy_timeout` added.

Still deferred (not in this pass): test-mode no-persist dry-run; diagnose why the v2 SMTP *send* fails when a user opts in.

## Final enhancements APPLIED + verified (2026-09-07)

- **E1 — v2 Gmail send fixed.** Root cause: `send_digest` called `r.get("email")` on a `sqlite3.Row`
  (no `.get()`) → `AttributeError` → every send failed. Fixed to `r["email"]` (`agents/email_sender.py`).
  Verified with **Send ON**: `email_status=SENT`, "Digest sent to 1 receiver(s) — 6 items", digest delivered
  to the configured receiver.
- **E2 — Test mode is now a true no-persist dry-run.** `run_profile_once(dry_run=…)` threads
  `skip_persist` into `run_compare_news_agent` and guards the rank/tag DB writes; the admin worker skips
  the digest step in dry-run. Test mode = fetch→rank→tag for a high-level review in the run log, writing
  **nothing** to `news_items`/`news_announcements` and sending no email. Verified: after a Test-mode run,
  `news_items` unchanged (baseline only), 0 announcements, `email_status=SKIPPED`, full review log present.
  UI: Test-mode description/implications updated ("Nothing saved — no Review items or announcements").
- Harness v3.0–v3.6 green after both (0 regressions).

## Post-enhancement fixes (2026-09-07)

- **Override strip was cosmetic → now functional.** `setOverride` (Review) only updated a "You: N" label
  (v3.0 UI-only, never wired). Added `POST /admin/news/<id>/override` (sets `human_rank_override` +
  effective `significance_rank` + `rank_tier='human'`); `setOverride` now persists and updates the rank badge.
- **"Re-rank All" errored** — `rerank_items_for_profile` queried `news_items.run_id` (nonexistent column).
  Fixed to rank by `profile_id`. Verified `{"ok":true,"reranked":N}`.
- **Removed the residual per-card "Accepted"/"Filtered" label** (leftover of the retired filter; P6 follow-up).
- Re-confirmed E2 dry-run: prep→dry-run leaves news_items unchanged, 0 announcements, email SKIPPED.

## Run-tab fixes P10–P12 APPLIED + verified (2026-09-07)

Template/JS only (`admin/templates/run_status.html`); verified live via Playwright, no restart needed.
- **P10 — source selection now honored (fixes Turkey "runs all + hangs").** The Run form never
  submitted the `has_rss_sources`/`has_twitter_sources`/`has_url_sources` hidden flags
  `admin_start_run` uses to tell "deselected all" from "no UI", so every run was treated as run-all →
  Turkey fetched all RSS+URL+Twitter and the external URL/Twitter fetches hung. Added the 3 hidden
  inputs (rendered per source section, `form="startRunForm"`). Also fixed a latent name mismatch: URL
  checkboxes were `selected_url` but the backend reads `selected_urls` (renamed; `deselectAll('urls')`).
  Verified on Turkey: deselect Twitter+URL, keep RSS → payload `has_*_sources=1`,
  `selected_rss=1/twitter=0/urls=0` → backend runs RSS only, no hang.
- **P11 — stepper shows the real v3 flow.** Was stale v2 (`Starting·Collecting·Filtering·Comparing·
  Grouping·Sending·Done`). Now `Starting·Collecting·Attributing·Comparing·Ranking·Tagging·Sending·Done`,
  with the log-marker→stage JS remapped to the actual controller prints (Attribution stamped→Attributing,
  Rank stage→Ranking, Tag/Glossary→Tagging, Email gate/preview/digest→Sending). Verified: all stages
  advance to done on a replayed run.
- **P12 — "Sending" pill reflects whether email was actually sent.** Added a `skipped` pill style
  (grey + strikethrough); exposed `email_status` via `#runMeta[data-email-status]`; the `done` handler
  now greens Sending only when `email_status='SENT'`, else marks it skipped, and no longer blanket-greens
  every pill. Verified on the GENERATED past run: Sending = skipped, all other stages done.
