# Legal Eagle v3.0 — Pipeline Redesign Specification

**Date:** 2026-06-29  
**Status:** Design Complete — Pending Implementation Plan  
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
EMAIL FILTER + SEND
  Apply rank threshold (default: send rank 3+)
  Apply REPEATED suppression rules (see §6)
  Organize by Topic Label (replaces grouping)
  Render email — publish date on every card, rank badge, topic tag, source link
  Gmail SMTP (ANS re-enabled when BTP rebuilt)
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
2. AI reflects: *"I understood: future items from Official Gazette sources with decree numbers and effective dates within 30 days should be ranked 5 in SA/HCM. Correct?"*
3. User confirms or corrects
4. Confirmed summary saved as profile-specific grounding example (Tier 2 prompt)

### Self-Improving Signal Schema
When Challenge → rank override → confirm, **two things happen simultaneously:**

1. Item override recorded with confirmed reason
2. AI extracts generalizable signal pattern → proposes new `ranking_signals` row:
   - *"New ranking rule proposed: effective_date_within_days ≤ 14 + penalty_clause → rank 5 for SA/HCM — confirm to add?"*
   - One-click confirm, or auto-add with 24-hour review window

**Full self-improvement loop:**
```
Challenge
  → LLM re-evaluates
    → Override + reason auto-populated
      → User confirms
        → Item override saved
        → Signal pattern extracted
          → ranking_signals DB updated
            → Next run: Tier 1 catches this pattern, no AI call needed
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

## 10. Email Structure (v3)

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

### Phase 1 — Structural improvements (no pipeline behavior change to user)
- **B1**: Replace hardcoded `MAX_NEWS_AGE_DAYS = 7` with per-source `last_successful_fetch` anchor; age gate moved to ANNOTATE step
- **B2**: Per-source `last_successful_fetch` on all source types (RSS, Twitter, URL); new sources fall back to `date_scope` days ago
- **B5**: Surface `published_at` in email cards and Review UI; migrate `_parse_publication_date()` to `text_utils.py`
- **B7**: Add `canonical_fingerprint TEXT` to `news_items`; fingerprint = normalized(publication_date + issuing_authority_name + topic_noun_phrase)
- **B8**: Move translation to post-save step; extract `news_translator.py`
- **Delete `news_filter.py`**: migrate useful pieces, remove binary filter entirely
- **Force fetch redefined**: treat `last_successful_fetch` as null for this run; bounded by `date_scope` always; remove "full/all/unlimited" options
- **DUPLICATE handling**: save to DB with rank 0, never drop; collapsed section in Review UI
- **Pre-run health check**: add `agents/health_check.py`; run before FETCH
- **Run error messages**: add `error_step` + `error_message` to `runs` table; surface in run status UI
- **Immediate stop**: threading stop event checked between items; `last_successful_fetch` written per source on completion
- **Run/publish date**: store both `published_at` and `fetched_at`; Review UI default sort by publish date descending

### Phase 2 — Add ranking alongside existing pipeline
- Add `significance_rank` column (nullable) to `news_items`
- Add `news_ranker.py` — runs after filter, writes rank to DB
- Review UI shows rank — no email behavior change yet
- Validate ranking quality across all profiles before proceeding

### Phase 3 — Replace email filter with rank threshold
- Email gated on rank ≥ 3 (configurable)
- Binary filter fully removed (already deleted in Phase 1)
- Fix B3, B4 (category/OTHER)
- ANNOTATE fully operational: DUPLICATE items saved to DB with rank 0, collapsed section in Review UI

### Phase 4 — Replace grouping with tagging
- Add `news_tagger.py`
- Add topic label columns
- Redesign email organization by topic label
- Add publish date to email cards

### Phase 5 — Add Challenge + Grounding Loop
- Add `ranking_signals` and `ranking_grounding` tables
- Add Challenge UI + override reason validation chat
- Wire self-improving signal extraction
- Add **Re-rank selected items** action in Review UI (re-runs ranker on existing DB items without re-fetching — for testing ranking fixes)

### Phase 6 — Add Glossary Gap Alert
- Red badge for rank ≥ 3 + no LoB match
- "+ Add to Glossary" inline action in Review UI

---

## 14. Version Naming

- v3.0 — Phase 3 complete (rank-gated email, bugs fixed)
- v3.1 — Phase 4 (tagging replaces grouping)
- v3.2 — Phase 5 (Challenge + grounding loop)
- v3.3 — Phase 6 (glossary gap alert)

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
