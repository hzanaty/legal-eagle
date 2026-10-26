# Legal Eagle v3 — Demo Runbook

Execution steps only. Two runs: **Run 1 = Xanadu (controlled)**, **Run 2 = Turkey (real-world)**.
Environment: live admin app against `configurations/config.db`, real AI Core.

Profiles: Xanadu HCM = `XN/HCM`, **id 6**. Türkiye HCM = `TR/HCM`, **id 4**.
Admin base URL below written as `http://127.0.0.1:8080` (app default `PORT`); use your instance's.

---

## Setup (prerequisites — before the session)

| # | Screen/command | Action | Value/config | Expected result |
|---|---|---|---|---|
| S1 | Terminal, in `Roadmap/v3/xanadu-gov-site` | Serve the gov site | `python3 -m http.server 8000 -d public` | Newsroom reachable at `http://127.0.0.1:8000/` |
| S2 | Terminal, repo root | Prep Xanadu profile | `python3 scripts/prep_xanadu_demo.py --rebuild-config --email <you>` | Prints guard OK, config built, baseline seeded, 3 other profiles untouched |
| S3 | Terminal, repo root | Start admin app | (project run command) | Admin UI reachable |

---

## Run 1 — Xanadu (controlled)

| # | Screen/page | Action | Value/config | Expected result |
|---|---|---|---|---|
| 1 | `http://127.0.0.1:8000/` | Open the gov site | — | 5 press releases listed (social-insurance item at top) |
| 2 | Xanadu profile → Sources — `http://127.0.0.1:8080/admin/profiles/6` | Add a **URL source** | URL `http://127.0.0.1:8000/`; **do not run Source Simulator** | URL source listed on the profile |
| 3 | Run tab — `http://127.0.0.1:8080/admin/profiles/6/runs` | Start run | **Test mode OFF** | SSE log runs to completion (fetch → attribute → compare → rank → tag → digest). A digest email is sent to the configured receiver (your own address). |
| 4 | Review tab — `http://127.0.0.1:8080/admin/profiles/6/review` | Open | — | Social-insurance item = **rank 4, tag REPEATED, glossary-matched**; other 4 items = rank 1–2 |
| 5 | Review → Announcements view | Switch view | — | Topic → Announcement → Sources hierarchy; social-insurance announcement present |
| 6 | Announcement → **Preview for RCM** | Generate, then Copy | — | Title / Introduction / Business Background / Reference Sources filled; Copy works |
| 7 | L2S | Paste | copied RCM content | Content pasted into L2S |

> **Test mode must be OFF for Run 1.** The Announcements view (step 5) and Preview for RCM (step 6)
> require the digest step, which only runs on a real (non-test) run. Test mode is a known limitation
> — see `DEMO_BUGS.md`.

**Prerequisite to repeat Run 1:** `python3 scripts/prep_xanadu_demo.py` (repeat-reset — keeps
config + the added URL source, re-seeds baseline).

---

## Run 2 — Turkey (real-world proof) — zero prep

| # | Screen/page | Action | Value/config | Expected result |
|---|---|---|---|---|
| 1 | Profiles / profile switch | Select **Türkiye HCM** | profile id 4 (already configured: real RSS feed + glossary) | Profile opens; no setup required |
| 2 | Run tab — `http://127.0.0.1:8080/admin/profiles/4/runs` | Start run | — | Run completes against the live real feed |
| 3 | Review tab — `http://127.0.0.1:8080/admin/profiles/4/review` | Open | — | Real ranked results shown (whatever the live feed returns; no scripted outcome) |

Turkey needs no reset, seed, or validation.

---

## Notes
- RSS Feed App (`rss-feed-creator-dev.cfapps.eu21.hana.ondemand.com`) is not required for Run 1. It
  is one available source-acquisition option and is how the Türkiye feed is produced.
- Technical details (URL-source scraper behaviour, cosine band, dedup) and known watch-items:
  see `Roadmap/v3/DEMO_BUGS.md`.
