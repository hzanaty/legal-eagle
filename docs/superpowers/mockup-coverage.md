# Mockup Coverage Tracker

Tracks how closely the live admin UI and email digest match the v3.0 UX spec mockups.
Updated after each version upgrade. Mockup source files: `docs/superpowers/mockups/v3-0-admin-ux/`.

---

## v3.4 — 2026-09-05 — Overall ~72%

| Area | Coverage | Notes |
|------|----------|-------|
| Email digest | ~85% | Authority → Topic → Announcement grouping ✓, rank badges ✓, sources ✓. |
| Configure tab | ~80% | FCL shell ✓, object header ✓, anchor sub-nav ✓, source cards ✓. |
| Run tab | ~65% | Tab structure ✓. Test mode toggle, pre-run checklist, stage progress bar, history pills not built yet. |
| Review tab | ~70% | Topic→Announcement→Sources 3-level hierarchy ✓ (v3.4), `announcement_md` markdown rendering ✓, ⚡ Challenge modal ✓, ↺ Re-rank per-item ✓, ⚙ Re-rank All ✓, filter chips ✓. **Missing:** Gap alert strip, "+ Add to Glossary" action. |

### Top open items for future versions

1. **Run tab: source selection panel** — chip-based source toggle, test mode toggle, pre-run checklist (5 rows), stage progress bar, history pills.
2. **Review tab: Gap alerts** — "⚠ N gap alerts need confirmation" toolbar strip + orange left-border item cards + "+ Add to Glossary" button.
3. **Review tab: Announcement RCM template** — styled publish action, JIRA link creation (v3.5+).

---

## v3.3 — 2026-09-05 — Overall ~65%

| Area | Coverage | Notes |
|------|----------|-------|
| Email digest | ~85% | Authority → Topic → Aspect grouping ✓, rank badges ✓, `(authority inferred ✦)` ✓, sources ✓. Rank badge was "TBD by design" in mockup annotations — confirm with design. |
| Configure tab | ~80% | FCL shell ✓, object header ✓, sticky anchor sub-nav ✓, source cards + expand/collapse ✓. "Monitor/L2S emails" toggle intentionally absent (commented out in code). |
| Run tab | ~65% | Tab structure ✓. Only "never run" state captured — source chip panel, test mode toggle, pre-run checklist, stage progress bar, and history pills not exercised/built yet. |
| Review tab | ~40% | Filter chips ✓, item list ✓. **Missing:** 2-level Topic→Aspect→Item grouping hierarchy, per-item rank override buttons, "Preview Announcement / Analysis" modals, Gap "Add to Glossary" action. Currently a flat paginated list. |

---

## How to update this file

After each version's visual validation session:

1. Run Playwright screenshots of Configure, Run, Review tabs and email preview
2. Compare against `docs/superpowers/mockups/v3-0-admin-ux/` HTML files and `docs/superpowers/previews/v3.3-email-mockup.html`
3. Add a new `## vX.Y — YYYY-MM-DD` section above, keeping previous versions below for history
4. Update the "top open items" list — strike through anything that shipped
