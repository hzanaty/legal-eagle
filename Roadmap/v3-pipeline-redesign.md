# Legal Eagle v3.0 — Pipeline Redesign Specification

**Date:** 2026-06-29  
**Status:** v3.6 Shipped — v3.7 (deprecate Legal Repository) next; V4 = Announce + Impact Agents on L2A MCPs  
**Version Jump:** v2.32 → v3.0  
**Author:** Brainstorming session (I077750 + Claude)

---

## 1. Executive Summary

Legal Eagle v3.0 is a fundamental redesign of the news processing pipeline. The current pipeline is a linear collect → filter → deduplicate → group → send flow with a binary AI filter and optional manual scoring. It produces low-quality output (noise reaches the email, important items are dropped, publish dates are missing, repeated news is discarded instead of surfaced as signal).

v3.0 introduces a **four-dimensional item model**, a **three-tier self-improving ranking engine**, and a **glossary-driven tagging system** that replaces LLM-based grouping. The result is a system that sends only legally significant items, gets smarter from every human interaction, and requires zero authoring from the user — only confirmation of what the AI proposes.

---

## 2. Current Pipeline — Confirmed Bugs and Weaknesses

### 2.1 Confirmed Bugs

| ID | Location | Bug | Fix in v3 |
|---|---|---|---|
| B1 | `news_filter.py:14` | `MAX_NEWS_AGE_DAYS = 7` hardcoded — conflicts silently with profile `date_scope` | Replace with profile's `date_scope` value |
| B2 | `config_loader.py` | Baseline window `today - 7 days` — meaningless when runs have gaps | Anchor to `last_successful_fetch` per source; new sources fall back to `date_scope` days ago |
| B3 | `news_grouper.py` | Grouper assigns FIN/OTHER to HCM profile items | Constrain to profile LoB |
| B4 | `news_grouper.py` | "OTHER" category exists and accepted in email | Eliminate — items that don't fit profile LoB are false positives |
| B5 | `email_sender.py` | `published_at` never rendered in email | Show on every email card and in Review UI |
| B6 | `news_filter.py` | Binary yes/no filter — noise ("the king met the president") reaches email | Delete `news_filter.py` entirely — ranker (Rank 1 = Noise) is the quality gate; useful code migrated (see §12) |
| B7 | `compare_news.py` | `hash_signature` breaks on minor editorial changes — cross-source dedup fails | Entity-based canonical fingerprint |
| B8 | `email_sender.py` | Translation called inside email sender (wrong layer) | Move to post-save step, store in DB, email sender renders only |

### 2.2 Structural Weaknesses

- **Rescue pass** is a near-no-op: requires human score ≥ 4 on baseline items, which almost never exists → powered by AI rank in v3
- **Binary filter** is the sole quality gate: no gradation of significance, noise and gazette entries are treated identically
- **Dedup silently drops** REPEATED news: repetition across sources is actually a significance signal, not noise
- **DUPLICATEs silently dropped**: in v2 identical items are discarded with no audit trail — v3 saves them with rank 0 and shows them in Review UI
- **Per-source lookback missing**: profile-level `date_scope` drives all sources identically, ignoring individual source fetch history — a failed source resets to the profile window on next run, potentially missing items
- **Grouping discards item-level signal**: LLM summarization obscures individual items and their ranks
- **No publish date** anywhere in the user-facing output: critical for urgency assessment

---

## 3. The Four-Dimensional Item Model

Every news item in v3 carries four independent dimensions, stored in the DB and visible in the Review UI:

| Dimension | Question it answers | Source | Values |
|---|---|---|---|
| **Significance Rank** | How legally important is this? | Three-tier ranking engine | 1–5 |
| **LoB Relevance** | Is this HCM/FIN relevant? | Glossary semantic match | Matched terms, or blank (gap alert) |
| **Topic Label** | What is this about? | Glossary keyword tagging | One or more glossary terms |
| **Repetition Tag** | Is this a recurring topic? | Cross-run frequency counter | NEW / UPDATE / REPEATED ×N / DUPLICATE (rank 0) |

These dimensions are **independent**. A rank 4 item with blank LoB Relevance is valid — it means the AI found a legally significant item that the current glossary cannot explain. This triggers a Glossary Gap Alert (see §7).

**DUPLICATE items carry rank 0** — a special value meaning "not evaluated by the ranker, exact match of a previously processed item." Rank 0 is outside the 1–5 significance scale. DUPLICATEs are never dropped — they are always saved to DB and visible in the Review UI in a collapsed section.

---

## 4. New Pipeline Architecture

```
HEALTH CHECK (new: agents/health_check.py)
  Runs after preflight config check, before any fetching
  Parallel checks — completes in seconds:
    - URL sources (selected): HTTP HEAD → warn + allow skip on failure
    - RSS feeds (selected): HTTP HEAD → warn + allow skip on failure
    - Twitter API: GET /2/users/me → validates auth only, zero quota cost → warn + allow skip
    - Gmail SMTP: connect → login → quit (no email sent) → HARD BLOCK on failure
    - SAP AI Core: minimal chat completion → HARD BLOCK on failure
    - DB writability: quick write test → HARD BLOCK on failure
  Hard blocks prevent run from starting; warnings let user skip source or abort
   ↓
FETCH (per-source lookback anchor)
  RSS + Twitter/X + URL scrapers
  Per source: use last_successful_fetch as window start (null = new source → fallback to profile date_scope days ago)
  Force fetch: treat last_successful_fetch as null for this run (bounded by date_scope — never unlimited)
  last_successful_fetch updated immediately on success, not at end of run
   ↓
ANNOTATE (compare_news.py — redesigned)
  Entity fingerprint matching against per-source last_successful_fetch baseline
  Classify: NEW | UPDATE (with delta) | REPEATED (with count) | DUPLICATE
  DUPLICATE = canonical fingerprint matches existing DB item
  ⚠️ DUPLICATE items are NEVER dropped — saved to DB with rank 0, visible in Review UI
   ↓
RANK (new: news_ranker.py)
  Three-tier ranking engine (see §5)
  DUPLICATE items skip ranking — they carry rank 0
  Each non-duplicate item receives Significance Rank 1–5
   ↓
TAG (new: news_tagger.py)
  Glossary keyword matching — assigns Topic Labels and LoB Relevance
  Blank LoB Relevance → Glossary Gap Alert flag
   ↓
TRANSLATE (new: news_translator.py — extracted from email_sender.py)
  Translate title + content for non-English profiles
  Store translation in DB alongside original
  Operates on ALL items regardless of rank (translations available in Review UI)
   ↓
SAVE TO DB
  All four dimensions stored per item (rank 0 for DUPLICATEs)
  Both published_at and fetched_at stored and indexed
  Available immediately in Review UI
   ↓
EMAIL FILTER + SEND (decoupled — runs after run marks SUCCESS)
  Apply rank threshold (default: send rank 3+)
  Apply REPEATED suppression rules (see §6)
  Generate AI digest via email_composer.py — grouped by Topic Label, one AI call per topic
  Language: recipient profile language only — no bilingual
  Render email — publish date on every card, rank badge, topic tag, source links
  Set email_sent = 1 on all included items; update runs.email_status
  Gmail SMTP (ANS re-enabled when BTP rebuilt)
  Run log shows email stage status + Resend button on failure
```

---

## 5. Three-Tier Ranking Engine

### Tier 1 — Deterministic (no AI, instant)

Rules stored in `ranking_signals` DB table, per profile. Each rule is a row:

| Column | Type | Example |
|---|---|---|
| `profile_id` | FK | SA/HCM profile |
| `signal_type` | TEXT | `gazette_number`, `effective_date_window`, `penalty_clause` |
| `pattern` | TEXT | regex or keyword pattern |
| `min_rank` | INT | 4 |
| `confidence` | FLOAT | 0.95 (increases as confirmed overrides match) |
| `created_from` | TEXT | `human_challenge` or `initial_setup` |

Examples:
- Gazette number + decree number + effective date → rank 4 minimum
- Effective date within 30 days + penalty clause → rank 5
- No legal keywords, no authority → rank 1 candidate

No AI call. O(1) per item. Fully auditable — you can inspect and delete any rule.

### Tier 2 — AI with Few-Shot Grounding

Items with no Tier 1 match go to the LLM with:
- 5-point scale definitions with one concrete example per level
- Profile country + LoB as context
- **Curated bootstrap examples** (5–8 hand-authored per profile at setup time, permanent)
- **Accumulated grounding summaries** (up to 10, from confirmed human overrides — oldest replaced by newest)

Prompt instruction: *"When in doubt between two levels, choose the lower one."*

### Ranking Prompt — Key Design

```
You are a legal significance classifier for [COUNTRY] [LOB] regulatory news.

Scale:
1 - Noise: no legal content (e.g. "The king met the president")
2 - Background: commentary, no specific legal action
3 - Watch: draft or announcement, not yet enacted
4 - Legal Change: official publication, enacted regulation, gazette entry
5 - Urgent: effective within 30 days, penalties, direct SAP [LOB] impact

Country context: [COUNTRY_SPECIFIC_HINTS]

Examples from this profile:
[BOOTSTRAP_EXAMPLES]
[GROUNDING_SUMMARIES — max 10]

Rule: when in doubt between two levels, choose the lower one.

Article: [TITLE + CONTENT]
Repetition context: [appeared N times, first seen DATE, original rank X]

Return JSON: {"rank": 1-5, "reasoning": "...", "signals_found": [...]}
```

### Tier escalation over time
- More human challenges → more Tier 1 rules → more items resolved without AI
- System gets **faster AND smarter** simultaneously
- Prompt never grows unbounded — grounding examples capped at 10 per profile

---

## 6. Ranking + REPEATED Decision Table

| Initial Rank | Tags | Updated Rank | Email Decision | Manual Override |
|---|---|---|---|---|
| 1 — Noise | — | 1 | ❌ Not sent — logged as false positive | Can upgrade |
| 2 — Background | — | 2 | ❌ Not sent — Review UI only | Can upgrade to 3+ |
| 3 — Watch | — | 3 | ✅ Sent (default threshold) | Can downgrade to 2 |
| 4 — Legal Change | — | 4 | ✅ Sent | Can downgrade |
| 5 — Urgent | — | 5 | ✅ Sent — highlighted | Can downgrade |
| 3 — Watch | REPEATED ×1–2 | 3 | ❌ Not sent — already emailed, no upgrade | Can upgrade to force re-send |
| 3 — Watch | REPEATED ×3+ | 4 — auto-elevated | ✅ Sent — frequency triggered | Can downgrade |
| 4 — Legal Change | REPEATED — unchanged | 4 | ❌ Not sent — no new content | Can upgrade to force reminder |
| 4 — Legal Change | REPEATED — rank upgrade | 5 — upgraded | ✅ Sent — escalation is the news | Can downgrade |
| 1 — Noise | REPEATED ×3+ | 1 — no elevation | ❌ Not sent — flags source | Can mark source for removal |
| 2 — Background | REPEATED ×3+ | 3 — auto-elevated | ✅ Sent — topic heating up | Can downgrade |

**Three elevation rules:**
1. Rank upgrade detected in new content → always elevates, overrides REPEATED suppression
2. REPEATED ×3+ AND rank ≥ 2 → auto-elevate by +1 (frequency = significance)
3. REPEATED ×3+ AND rank 1 → no elevation, flag source for removal

---

## 7. Glossary Gap Alert + On-Spot Enrichment

**Trigger:** Significance Rank ≥ 3 AND zero glossary keyword matches (blank LoB Relevance)

**Review UI behavior:**
- Red **"No LoB Match"** badge on the item card
- Signals: AI found legally significant content the current vocabulary cannot explain
- Two responses available: downgrade rank (AI was wrong) or enrich glossary (AI was right, vocabulary gap)

**"+ Add to Glossary" inline action:**
1. AI pre-suggests keywords extracted from article text
2. User selects/types terms, assigns LoB category (HCM / FIN), optionally assigns topic label
3. Confirm → term saved to profile glossary immediately
4. Card refreshes showing matched glossary terms in green
5. No navigation away from Review screen

---

## 8. Human Review Model — Async + Self-Improving

### Principle
Pipeline sends automatically on AI rank. Human review is async — after email, no blocking.

### Challenge Feature
Before overriding, user hits **"Challenge"** on any item:
1. System re-evaluates using full Approach A (LLM with all grounding context)
2. Two outcomes:
   - AI agrees → shows reasoning → user can still override manually with full context
   - AI disagrees → suggests new rank + **auto-populates override reason** → one-click confirm
3. Human effort = judgment only, zero authoring

### Override Reason Validation (mini-chat)
1. Reason written (or AI auto-populated from challenge)
2. AI reflects back the understood signal: *"I understood: future items from Official Gazette sources with decree numbers and effective dates within 30 days should be ranked 5 in SA/HCM. Correct?"*
3. User confirms once — **both writes happen simultaneously**

### Self-Improving Signal Schema
When Challenge → rank override → confirm, **one confirmation covers everything:**

1. Human writes (or accepts AI-populated) override reason
2. AI reflects back the understood signal (see mini-chat above)
3. Human confirms once — **both writes happen simultaneously:**
   - `ranking_grounding` updated: validated summary becomes a Tier 2 grounding example
   - `ranking_signals` updated: extracted pattern becomes a new Tier 1 deterministic rule

**Full self-improvement loop:**
```
Challenge
  → LLM re-evaluates
    → Override + reason auto-populated
      → AI reflects signal back
        → User confirms (single action)
          → W ranking_grounding  (grounding example — LLM uses this as few-shot context next run)
          → W ranking_signals    (Tier 1 rule — deterministic match, no AI call needed next run)
```

---

## 9. Grouping Replaced by Glossary-Keyword Organization

**Old:** LLM invents theme titles, writes 2–3 sentence summaries, items lose individual identity  
**New:** Items tagged with glossary keywords, email organized by primary topic label

- Each item is individually visible in the email with its own rank badge, publish date, tags, source link
- Organization is structural (by topic label), not editorial (no LLM-written summaries)
- Multiple tags per item supported
- Review UI filterable by tag: "show me everything tagged 'social insurance'"
- LLM summarization eliminated as a default step (optional per profile if desired)

---

## 10. Review Hierarchy Terminology (v3.4+)

The three levels of the Review tab hierarchy, locked in v3.4:

| Level | Term | Description | DB / Field |
|---|---|---|---|
| 1 | **Topic** | Broad regulatory area from glossary tagger | `news_items.topic_label` |
| 2 | **Announcement** | AI-generated draft in Law2Spec Announcement format (Introduction / Business Need / Related Resources) | `news_announcements` table (renamed from `news_aspects` in v3.4) |
| 3 | **Sources** | Individual news articles that back the Announcement | `news_items` rows (via `news_announcements.item_ids_json`) |

**Why "Announcement":** The content in `announcement_md` is structured to match the SAP RCM / Law2Spec Announcement template. Calling it "Announcement" makes the intent explicit to LPMs.

**Rendering timeline:**
- v3.4: inline markdown rendering of `announcement_md` in Review tab
- v3.6: full RCM-branded template page with publish action and JIRA linking

---

## 11. Email Structure (v3)

Each email section:
- Organized by Topic Label (primary glossary tag)
- Per item card shows:
  - **Rank badge** (color-coded: rank 3 = yellow, rank 4 = orange, rank 5 = red)
  - **Published date** (prominent — critical for urgency)
  - **Repetition tag** if REPEATED (e.g., "Appeared 4× this month")
  - **Title** (original language)
  - **Translation** (if non-English profile)
  - **Source link**
  - **Topic tags** (glossary keywords)
- Rank 5 items appear first, highlighted section at top
- Email threshold configurable per profile (default: rank 3+)

---

## 11. New DB Tables Required

### `ranking_signals`
```sql
id INTEGER PRIMARY KEY
profile_id INTEGER FK
signal_type TEXT
pattern TEXT
min_rank INTEGER
confidence REAL DEFAULT 0.8
created_from TEXT  -- 'initial_setup' | 'human_challenge'
created_at TEXT
```

### `ranking_grounding`
```sql
id INTEGER PRIMARY KEY
profile_id INTEGER FK
rank INTEGER
summary TEXT  -- AI-confirmed understanding of the override reason
source_item_id INTEGER FK  -- which item triggered this grounding
created_at TEXT
```

### Modified `news_items` / `filtered_news`
New columns:
- `significance_rank INTEGER` — 0 = DUPLICATE (not evaluated), 1–5 = AI-ranked significance
- `rank_tier TEXT` — 'tier1' | 'tier2' | 'duplicate'
- `rank_reasoning TEXT` — AI explanation
- `lob_relevance_terms TEXT` — JSON array of matched glossary keywords
- `topic_labels TEXT` — JSON array of primary topic labels
- `repetition_tag TEXT` — NEW | UPDATE | REPEATED | DUPLICATE
- `repetition_count INTEGER`
- `human_rank_override INTEGER` — NULL if not overridden
- `human_override_reason TEXT`
- `title_translated TEXT`
- `content_translated TEXT`
- `translation_lang TEXT`
- `published_at TEXT` — publication date (parsed from source)
- `fetched_at TEXT` — when Legal Eagle retrieved this item

### Modified `rss_feeds`
- Add `last_successful_fetch TEXT` — updated only on successful fetch (existing `last_fetch_date` kept for debugging)

### Modified `tweet_accounts`
- Add `last_successful_fetch TEXT` — updated only on successful fetch (existing `last_fetch_date` kept for debugging)

### Modified `runs`
- Add `error_step TEXT` — which pipeline step failed (null if success)
- Add `error_message TEXT` — human-readable failure reason

---

## 12. New Agent Files

| File | Purpose | Replaces |
|---|---|---|
| `agents/news_ranker.py` | Three-tier ranking engine | `news_filter.py` (deleted) |
| `agents/news_tagger.py` | Glossary keyword tagging + LoB relevance | Part of `news_grouper.py` |
| `agents/news_translator.py` | Post-save translation step | Extracted from `email_sender.py` |
| `agents/health_check.py` | Pre-run runtime reachability checks | New |

**`agents/news_filter.py` — DELETED in Phase 1.** Useful pieces migrated:
- `_parse_publication_date()` → `agents/text_utils.py` (utility, fixes B5)
- Age gate logic (`is_news_too_old()`) → `agents/compare_news.py` ANNOTATE step (driven by per-source `last_successful_fetch`, not a hardcoded constant)
- `semantic_glossary_check()` prompt structure → `agents/news_ranker.py` Tier 2 prompt (cross-language semantic approach inherited)

Not migrated (obsolete):
- `is_similar_to_baseline()` embedding rescue — superseded by ranker
- `high_score_baseline` mechanism — superseded by Tier 1 + Tier 2
- Binary `is_relevant` gate — replaced by Rank 1 = Noise

Modified files:
- `agents/compare_news.py` — redesigned as annotator (NEW/UPDATE/REPEATED/DUPLICATE); DUPLICATEs saved with rank 0, never dropped
- `agents/news_grouper.py` — replaced by tagger; LLM summarization removed
- `agents/email_sender.py` — pure rendering, no AI calls
- `configurations/db.py` — new tables + new columns (see §11)
- `configurations/config_loader.py` — remove "all" / "force_full" from `parse_date_scope()`; force fetch now means "use date_scope window" not "unlimited"
- `admin/app.py` — new Review UI routes (Challenge, Override, Glossary enrichment, Re-rank); remove "all" from date_scope allowed values
- `admin/templates/profile.html` — remove "Full" option from lookback dropdown
- `admin/templates/run_status.html` — health check results display; per-step error messages; immediate stop via threading event
- `admin/templates/review_news.html` — rank badges, DUPLICATE collapsed section, gap alerts, challenge button, re-rank action, published/fetched date on every card

---

## 13. Transition Plan v2.32 → v3.0

### Phase 1 — Setup + Collect structural improvements (no pipeline behaviour change to user)
Follows lifecycle order: Setup → ① Start → ② Collect → infrastructure fixes.

**Setup — Sources (F9 Source Simulator):**
- URL source form reduced to 1 field; simulator auto-discovers container selectors, field selectors, depth, render mode, pagination (see F9)
- Add `agents/source_simulator.py`; migrate `url_sources` schema; add `/simulate` SSE route; replace form in `profile.html`
- Add `scrape_url_source_with_config()` to `url_sources_runner.py`
- **Spec:** `docs/superpowers/specs/2026-07-01-source-simulator-design.md` · **Plan:** `docs/superpowers/plans/2026-07-01-source-simulator.md`

**① Start — Health Check (F2):**
- Add `agents/health_check.py`; runs before any fetching begins
- Hard blocks: Gmail SMTP, SAP AI Core, DB writability
- Warnings: source unreachability (user can skip or abort)
- Run error messages: add `error_step` + `error_message` to `runs` table; surface in run status UI (F3)
- Immediate stop: threading event checked between items; `last_successful_fetch` written per source on completion (F4)

**② Collect — Per-source lookback (F1, B1, B2):**
- Per-source `last_successful_fetch` on all source types (RSS, Twitter, URL); new sources fall back to `date_scope` days ago
- Replace hardcoded `MAX_NEWS_AGE_DAYS = 7` with per-source anchor; age gate moved to ANNOTATE step
- Force fetch redefined: treat `last_successful_fetch` as null, bounded by `date_scope`; remove "full/all/unlimited" options (F5)

**③ Process — Infrastructure fixes (B5, B7, B8, F7, F8):**
- Delete `news_filter.py`; migrate useful pieces (B6)
- Move translation to post-save step; extract `news_translator.py` (B8)
- Add `canonical_fingerprint TEXT` to `news_items`; entity-based fingerprint (B7)
- DUPLICATE items saved to DB with rank 0, never dropped; collapsed section in Review UI (F7)
- Store both `published_at` and `fetched_at`; Review UI default sort by publish date descending (F5, F8)

### Phase 2 — Rank (③ Process — new step)
Follows lifecycle order: Compare → **Rank** added after Compare.

- Add `significance_rank` column (nullable) to `news_items`
- Add `news_ranker.py` — three-tier engine runs after ANNOTATE, writes rank 1–5 to DB
- DUPLICATE items (rank 0) skip ranker
- Review UI shows rank badges — no email behaviour change yet
- Validate ranking quality across all profiles before proceeding to Phase 3

### Phase 3 — Tag + Email threshold (③ Process + ④ Finish)
Follows lifecycle order: Rank → **Tag** → Group removed → **Send Email** threshold gate.

- Add `news_tagger.py` — glossary keyword matching; assigns Topic Labels + LoB Relevance
- Remove `news_grouper.py` — LLM summarization eliminated; Group step removed
- Fix B3, B4 (category/OTHER constrained to profile LoB)
- Email gated on rank ≥ 3 (configurable); binary filter gate fully gone
- **Email V2 digest format** — new `agents/email_composer.py`; AI digest grouped by Topic Label (one AI call per topic, sequential); single language per recipient; no bilingual
- Email send **decoupled from run** — run marks SUCCESS first, digest runs as follow-on step
- `email_sent INTEGER` on `news_items`; `email_status TEXT` on `runs`
- Run log: email stage indicator (`PENDING → SENDING → SENT / FAILED / SKIPPED`) + Resend button on failure
- Review page: Email filter chip (Unsent only), Send Email toolbar button, Sent/Unsent pill per item
- Publish date on every email card (B5)
- ANNOTATE fully operational: DUPLICATE collapsed section in Review UI
- Fallback: if tagger not yet live at Phase 3 deploy, email uses single "General" block

### Phase 4 — Challenge + Grounding Loop (Review — Challenge Rank)
Follows lifecycle order: Review → **Challenge Rank** → feeds back into Rank (next run).

- Add `ranking_signals` and `ranking_grounding` tables
- Add Challenge UI + override reason mini-chat validation
- Wire self-improving signal extraction: confirmed override → W `ranking_grounding` + W `ranking_signals` simultaneously
- Add **Re-rank selected items** action in Review UI (F6 — re-runs ranker on existing DB items without re-fetching)
- **Email V2 topic grouping fully active** — tagger output feeds directly into `email_composer.py` topic grouping; no extra work needed

### Phase 5 — Glossary Gap Alert (Review — after Challenge Rank)
Follows lifecycle order: final Review enhancement, depends on Tag (Phase 3) being live.

- Red **"No LoB Match"** badge for rank ≥ 3 + zero glossary keyword matches
- "+ Add to Glossary" inline action in Review UI
- AI pre-suggests keywords; user confirms; glossary updated immediately without navigation

### Phase 6 (v3.6) — Preview for RCM + Close-the-Loop (JIRA link → Done)

A presentation layer over data v3.4 already stores, plus the LPM's manual finish line. **No external integration** — the LPM still hands off to L2S manually, exactly as today.

- **"Preview for RCM" button** on each Announcement row (label is intentionally *not* "Publish" — it sends nothing).
- Opens a **read-only modal** rendering `news_announcements.announcement_md` in the RCM / Law2Spec announcement template, with **source links** resolved from `news_announcements.item_ids_json`.
- An **"Open L2S"** link opens L2S in a new browser tab (`target="_blank"`); the LPM copies/pastes manually.
- **Close the loop (LPM finish line):** after publishing to RCM, the LPM pastes the **JIRA Legal Change number** onto the announcement and marks it **Done**. This *stamps the announcement complete* — the LPM's job is finished. Announcement status flows Published → Done.
- **New DB (small):** `news_announcements.jira_legal_change TEXT` + `news_announcements.status TEXT` (e.g. draft/published/done). **New route:** `GET /admin/announcement-template/<id>` (template modal) + a small `POST` to save the JIRA number / status. No API to JIRA — manual paste.
- **Deferred to V4:** automated JIRA Legal Change creation + auto-link + auto-stamp (the Announce Agent), announcement editing, and Impact Analysis.

---

### Phase 6.5 (v3.7) — Deprecate Legal Repository

The **Legal Repository** (regs → JIRA EPIC / SAP Notes knowledge base: `repo_nodes`/`repo_assets`, `admin/templates/legal_repo.html`, repo routes in `admin/app.py`, `loka_client.py`) predates v3 (shipped v2.30) and is **out of Legal Eagle's scope**. It is unrelated to the monitor→announce pipeline and was bundled in by mistake.

- **Retire it from Legal Eagle:** remove the Legal Repo UI + routes; drop it from the lifecycle diagram.
- **Data first:** if any real repo data exists, export/migrate it before dropping the tables (or keep the tables dormant and only remove the UI — decide at v3.7 start).
- Independent of the v3.6 announce/close-the-loop work.

---

### Phase 7 (V4) — Announce Agent + Impact Agent (on L2A capability-hub MCPs)

Two new agents that automate what v3.6 does manually — built on **existing SAP L2A capability-hub MCPs/skills**, not from scratch, and **not** the deprecated in-app Legal Repo.

- **Announce Agent** (`agents/announce_agent.py`, new): creates the JIRA Legal Change from the announcement and auto-links/stamps it Done (automating the v3.6 manual step). Uses the **sanctioned L2S/GLO path** — `l2s-prd-mcp` + the `glo-requirements-setup` skill — which resolves the earlier governance concern (no raw, unsanctioned JIRA REST). Also handles announcement editing before hand-off.
- **Impact Agent** (`agents/impact_analyzer.py`, new): one AI call per announcement → structured impact report (affected products, before/after, expected solution) saved to `news_announcements.impact_analysis_md` (new column, V4 migration); **"Preview Analysis"** button (AI first click, cached thereafter, Copy MD). Grounded on **legal + technical knowledge from external SAP sources**, not the in-app Legal Repo.

**Resources (owner-supplied; SAP-internal — verify/confirm mapping at V4 start):**
- Announce / L2S write: `https://auth-proxy.daf98e7.kyma.ondemand.com/l2s-prd-mcp/mcp` (L2S PRD MCP); `glo-requirements-setup` skill (`github.tools.sap/law-to-action/l2a-capability-hub/blob/main/skills/glo-requirements-setup/SKILL.md`)
- Impact / fit-gap: `glo-functional-spec-fitgap-generator` skill (`.../skills/glo-functional-spec-fitgap-generator/SKILL.md`)
- Legal/requirements grounding: `https://glo-taxonomy-kg-mcp-server.daf98e7.kyma.ondemand.com/mcp` (GLO taxonomy KG); `https://sap-mcp-glorep-kg.cfapps.eu12.hana.ondemand.com/mcp-http` (GLO repo KG)
- Technical grounding: SAP ABAP MCP; SAP Enterprise Knowledge Graph
- Catalog: `https://pages.github.tools.sap/law-to-action/l2a-capability-hub/#mcp-servers`
- **Spec:** write a fresh V4 spec at start (the old `docs/superpowers/specs/2026-07-03-impact-analysis-agent.md` references `news_aspects` and predates this MCP direction).

---

## 14. Version Naming

Versions v3.0–v3.5 are **shipped**. v3.6, v3.7, and V4 are targets — each is reached when its phase is fully delivered and tested.

| Version | Phase | What it delivers |
|---|---|---|
| **v3.0** | Phase 0 | Admin UI navigation overhaul — clean flow between Setup → Run → Review; fix jumping/disorientation between config, run status, and review screens. **Run All Active UI:** button enabled (solid blue, no "Soon" badge), live status pill CSS on profile rows, toast on click. **Source Attribution (config):** `authorities` table + Authorities CRUD section in Configure tab + `publisher_name`/`authority_id` fields on feed/source forms; "Source" column renamed to "Channel" in Review UI with stub Publisher + Authority columns. **Spec:** `docs/superpowers/specs/2026-07-02-v3-0-admin-ux-design.md` · `docs/superpowers/specs/2026-07-02-run-all-active-design.md` · `docs/superpowers/specs/2026-09-04-source-attribution-design.md` · **Mockups:** `docs/superpowers/mockups/v3-0-admin-ux/` **Test Harness v3.0:** no pipeline run — harness verifies Xanadu profile, authorities, and feeds saved correctly to DB (`python tests/run_harness.py --version v3.0`). |
| **v3.1** | Phase 1 | All structural fixes (bugs B1–B8, F1–F5, F7–F9) + Source Simulator. No pipeline behaviour change visible to email recipients. **Run All Active backend:** sequential background thread, skip-on-failure, SSE live row updates on dashboard. **Source Attribution (pipeline):** `publisher`/`authority_id`/`authority_status` columns on `news_items`; ATTRIBUTE stage (configured path — stamps from feed config, no AI); Publisher + Authority columns populated in Review UI; same-authority dedup threshold lowering. **Test Harness v3.1:** first full pipeline run against Xanadu (XN/HCM) test profile; asserts pass/filter/duplicate outcomes + publisher/authority values on all items. |
| **v3.2** | Phase 2 | Ranking engine live; rank badges in Review UI. Email still uses old threshold. **Source Attribution (AI + ranking):** ATTRIBUTE AI path for mixed publishers (ai_suggested status + ✦ spark icon + override UI); Tier 1 first-party source rank boost. **Test Harness v3.2:** adds `expected_rank_min` assertions on A1–A4; adds `repetition_count = 3` to seed rows S4–S6; asserts REPEATED tag + rank +1 boost on R1–R3; asserts ✦ ai_suggested status on items from mixed-publisher feeds. |
| **v3.3** | Phase 3 | Email gated on rank ≥ 3; tagging replaces grouping; publish dates on cards. **Email V2 digest format** — AI newsletter grouped by Authority then Topic Label; Law2Spec Announcement-aligned structure; decoupled from run; Resend button; manual send from Review. **Test Harness v3.3:** adds `expected_email_eligible: true` assertions for rank ≥ 3 items; adds `expected_authority_group` assertions matching digest grouping. |
| **v3.4** | Phase 4 | Challenge + grounding loop; self-improving Tier 1 rules; Re-rank action (F6). **Also pulled forward from Phase 6:** V2 digest wired into pipeline (`email_composer.generate_digest()` replaces old `email_sender` call); Review tab restructured into **Topic→Announcement→Sources** nested hierarchy (Option A: nested indent); clicking an Announcement renders `announcement_md` as markdown inline (intro, business need, sources). Terminology locked: Level 1 = Topic, Level 2 = Announcement (`news_announcements` table — renamed from `news_aspects`), Level 3 = Sources. **Test Harness v3.4:** pre-seeds one `ranking_grounding` row in baseline; asserts `news_announcements` table exists + has rows after run; asserts `human_rank_override` column exists. **Spec:** `docs/superpowers/specs/2026-09-05-v3-4-challenge-grounding-design.md` |
| **v3.5** | Phase 5 | Glossary gap alert; inline "+ Add to Glossary" in Review UI. **Test Harness v3.5:** adds one item to `xn_feed_a_relevant.xml` with rank ≥ 3 + no glossary keyword match; asserts `expected_gap_badge: true` on that item. |
| **v3.6** | Phase 6 | **Preview for RCM + close-the-loop.** Read-only modal rendering `announcement_md` in the RCM/Law2Spec template + source links (from `item_ids_json`) + an "Open L2S" link (new tab; manual paste). Button "Preview for RCM" (not "Publish"). **Close the loop:** LPM pastes the JIRA Legal Change # onto the announcement and marks it **Done** (status Published→Done) — the LPM's finish line. New: `news_announcements.jira_legal_change` + `status` columns; `GET /admin/announcement-template/<id>` + a POST to save JIRA #/status. No JIRA API — manual. **Test Harness v3.6:** template route returns announcement + resolves sources; JIRA #/status persist. |
| **v3.7** | Phase 6.5 | **Deprecate Legal Repository.** Retire the out-of-scope regs→JIRA/SAP-Notes knowledge base (`repo_nodes`/`repo_assets`, `legal_repo.html`, repo routes, `loka_client.py`) from Legal Eagle; remove from the lifecycle diagram. Export/migrate any real data first (or keep tables dormant, remove UI only — decide at start). |
| **V4** | Phase 7 | **Announce Agent + Impact Agent on L2A capability-hub MCPs.** *Announce Agent* (`agents/announce_agent.py`): auto-creates the JIRA Legal Change + auto-links/stamps Done via the **sanctioned L2S path** (`l2s-prd-mcp` + `glo-requirements-setup` skill) — resolves the raw-JIRA-REST governance concern. *Impact Agent* (`agents/impact_analyzer.py`): per-announcement AI impact report → `news_announcements.impact_analysis_md`; grounded on external SAP sources (`glo-functional-spec-fitgap-generator`, `glo-taxonomy-kg`, `sap-mcp-glorep-kg`, SAP ABAP MCP, SAP Enterprise KG) — **not** the in-app Legal Repo. Fresh V4 spec written at start. |

---

## 15. Features Added Post-Initial Design

### F1 — Per-Source Successful Lookback Anchor
Every source type (RSS, Twitter, URL) tracks its own `last_successful_fetch`. Lookback anchors to that date per source. New sources (null) fall back to `profile.date_scope` days ago. Updated only on success — failed fetches leave the anchor intact, ensuring no gap in coverage. "Full/unlimited" lookback removed entirely.

### F2 — Pre-Run Health Check
Before any fetching begins, `agents/health_check.py` verifies runtime reachability in parallel: HTTP HEAD for each selected URL/RSS source, `GET /2/users/me` for Twitter auth, SMTP connect+login+quit for Gmail, a minimal AI Core chat call, and a DB write test. Gmail, AI Core, and DB failures are hard blocks. Source unreachability is a warning (user can skip or abort).

### F3 — Improved Run Error Messages
Each pipeline step records its failure reason in `runs.error_step` + `runs.error_message`. The run status UI shows the specific step and message, not just a red icon.

### F4 — Immediate Stop + Per-Source Save
Stop is a threading event checked between items (not just between steps) — run breaks at the next item boundary. `last_successful_fetch` is written immediately when each source finishes, so a mid-run stop correctly records which sources completed.

### F5 — Force Fetch Redefined
Force fetch = treat `last_successful_fetch` as null for this run → use `date_scope` window. Always bounded by `date_scope`. Re-fetched items hit ANNOTATE and are tagged DUPLICATE (rank 0) if already in DB. Not a re-test mechanism — use Re-rank (F6) for that.

### F6 — Re-Rank Action in Review UI
"Re-rank selected items" bulk/per-item action in Review UI. Passes existing DB items through the current ranker without re-fetching. Updates `significance_rank`, `rank_tier`, `rank_reasoning`. Correct mechanism for testing ranking fixes.

### F7 — DUPLICATE Handling: Rank 0, Never Dropped
DUPLICATE = canonical fingerprint matches an existing DB item — not evaluated by ranker, assigned rank 0 (grey badge, outside 1–5 scale). **Never dropped** — always saved to DB and visible in Review UI in a collapsed section (expand to see). v2 silently dropped these; v3 makes them auditable.

### F8 — Run Date vs Publish Date Segregation
Every item card shows both `published_at` (legally meaningful, drives urgency) and `fetched_at` (when Legal Eagle retrieved it). Review UI default sort: publish date descending. Email cards: publish date prominent on every card (fixes B5).

### F9 — Source Simulator (Zero-Config URL Source Setup)
Adding a new URL source today requires filling 11 manual fields (mode, sample_link, read_more_label, max_depth, allowed_domains, path_filter, etc.). F9 replaces all of this with a single URL field and a one-time AI-powered simulation step.

**What changes:**
- URL source form reduced from 11 fields → 1 field (URL only)
- All structural config (container selector, field selectors, depth, render mode, pagination) auto-discovered once by the simulator and stored in DB
- Runtime scraper reads stored selectors per run — no re-discovery on every run (faster, more reliable)
- Dropped params: `mode`, `crawl_version`, `max_depth`, `allowed_domains`, `path_filter`, `max_results`, `url_date_template`, `read_more_label`
- Repurposed: `sample_link` — simulator writes a proof article URL here

**Simulator pipeline (one-time, user-triggered):**
1. **Fetch** — static HTTP first; auto-falls back to Playwright if page is JS-skeleton (`requires_js` stored)
2. **Detect containers** — scans DOM for repeating elements (same tag + class, ≥3 occurrences); presents preview of found articles to user
3. **Depth loop** — if articles not found at entry URL, LLM picks most likely nav link, simulator follows it one level deeper; user confirms or requests another level (max depth 5)
4. **Map fields** — extracts CSS selectors for title, link, date, author within confirmed container (automatic, no user input)
5. **Button picker** — if multiple clickable elements found near articles, presents up to 4 candidates; user picks which opens article detail (conditional — skipped if article title IS the link)
6. **Pagination detection** — scans for date-nav or page-nav controls; stores selector + type; shown to user informally before saving (no action required)
7. **Sample capture** — follows first article link, stores detail URL as `sample_link` (proof of success)
8. **Save** — all discovered config written to `url_sources`; `simulation_status = success`

**New `url_sources` columns:** `simulation_status` (pending/success/failed), `simulated_at`, `container_selector`, `field_selectors` (JSON), `read_more_selector`, `pagination_type`, `pagination_selector`, `depth_level`, `requires_js`

**Simulation trigger:** User adds URL → row saved as `pending` → user clicks **⚡ Simulate** button in the row. Not triggered automatically on save. Existing un-simulated sources show same `⏳ Pending` badge + Simulate button.

**Runtime impact:** `url_sources_runner.py` gains `scrape_url_source_with_config()` — reads stored selectors directly instead of re-discovering. Legacy path (un-simulated sources) preserved as fallback.

**Limits:** Does not handle login-required sites. GOSI-style click-discover absorbed into general Playwright + depth loop.

**Spec:** `docs/superpowers/specs/2026-07-01-source-simulator-design.md`  
**Plan:** `docs/superpowers/plans/2026-07-01-source-simulator.md`

### Email V2 — AI Digest + Manual Send

Replaces the current flat bilingual HTML email with a structured AI-generated newsletter digest. Ships in **v3.3 (Phase 3)**.

**Digest format:**
- Header: "Legal Eagle Digest — {Profile Name}" + date
- One topic block per glossary Topic Label, sorted by highest rank item desc
- Within each topic: AI detects distinct legal aspects → one sub-section per aspect (title + collective summary + first publish date + source links)
- Single language per recipient (profile language) — no bilingual output

**AI generation approach:**
- Topic grouping is deterministic in code (uses existing Topic Labels from tagger — no AI needed)
- One sequential AI call per topic group: detects sub-aspects, writes title + summary per aspect
- In-memory dict collects results per topic; assembled into final HTML after all calls complete
- Fallback: if tagger not yet live, all items fall into a single "General" block

**Decoupling from run execution:**
- Run marks SUCCESS as soon as items are stored and ranked — does not wait for email
- Digest generation starts immediately after as a follow-on step
- `email_status` on `runs` table tracks: `PENDING → SENDING → SENT / FAILED / SKIPPED`
- `SKIPPED` = test mode run (no auto-send)
- Run log shows email as a separate observable stage + **Resend** button on `FAILED`

**Manual send from Review page (test mode use case):**
- "Unsent only" filter chip (5th filter row, amber) — filters `email_sent = 0`
- "✉ Send Email (N)" button in toolbar — active only when items selected
- `✉ Unsent` / `✓ Sent` pill in item meta line — DUPLICATE items get no pill
- `/send-email` route accepts either `item_ids` (manual) or `run_id` (Resend from run log)

**DB changes:**
- `news_items.email_sent INTEGER DEFAULT 0` — set to 1 on first send, never reset
- `runs.email_status TEXT DEFAULT 'PENDING'`

**Spec:** `docs/superpowers/specs/2026-07-02-email-v2-design.md`

### Run All Active — One-Click Multi-Profile Runner

Activates the "Run All Active" placeholder button in the dashboard summary strip. Split across two phases.

**v3.0 (UI only):**
- Button enabled: solid blue `#0a6ed1`, no dashed border, no "Soon" badge
- Live status pill CSS added to profile rows (Waiting / Running / Done / Failed)
- Clicking shows toast: "Run All wiring coming in v3.1"

**v3.1 (backend wired):**
- `POST /admin/run-all`: spawns background thread, runs each active profile sequentially using existing `run_profile()` logic
- Skip-on-failure: failed profile is marked `✗ Failed` with error reason, next profile starts immediately
- One session at a time: button disabled while running, shows `N / TOTAL` counter
- SSE push events (`run_all_status`) update profile row pills live on the dashboard — reuses existing SSE infrastructure
- `GET /admin/run-all/status`: reconnect recovery after page reload

**Spec:** `docs/superpowers/specs/2026-07-02-run-all-active-design.md`

### Source Attribution — Publisher + Authority (added 2026-09-04)

Three distinct source dimensions exposed across the pipeline:
- **Channel** — mechanism: RSS / Twitter / URL (existing `source_type`, renamed in UI)
- **Publisher** — who published on that channel: "GOSI Official Website", "Saudi Gazette", "iKANUN"
- **Authority** — the legislative body that issued the regulation: "GOSI", "Ministry of HR"

Authority is optional per feed. If blank, the publisher is a mixed aggregator. ATTRIBUTE stage (new, after ANNOTATE) stamps authority on items from configured feeds instantly; AI detection fires only for unconfigured mixed publishers. Ships across v3.0 (config UI) → v3.1 (pipeline + dedup) → v3.2 (AI attribution + rank boost) → v3.3 (email grouping by authority).

**Spec:** `docs/superpowers/specs/2026-09-04-source-attribution-design.md`

---

## 16. Test Harness (added 2026-09-04)

Deterministic integration test harness for automated verification of every v3.x upgrade. Uses a controlled "Xanadu" (XN/HCM) test profile with pre-crafted RSS feeds served from `localhost:9999`. Known input → calculable expected output → fully automated pass/fail assertions.

**Two datasets per run:**
- **Feed XML files** — served at `localhost:9999/feeds/` — what Legal Eagle fetches
- **Baseline seed** — pre-loaded `news_items` rows — what Legal Eagle has seen before (enables dedup testing)

**AI calls:** hybrid caching — real on first run, replayed from `tests/ai_cache/` on all subsequent runs. Activated by `LEGAL_EAGLE_TEST_MODE=1`.

**Test scenarios covered:** HCM-relevant items (pass), wrong LoB + noise + old items (filter), exact + near + intra-run duplicates, REPEATED tag items, authority attribution.

**Version delta:** same XML feed files across all versions; only `expected/vX.Y.json` adds new assertions per version (rank, tag, email eligibility, authority group, gap badge).

**Entry point:** `python tests/run_harness.py --version v3.1` — exits 0 (all pass) or 1 (any fail).

**Spec:** `docs/superpowers/specs/2026-09-04-test-harness-design.md`

