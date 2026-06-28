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
| B2 | `config_loader.py` | Baseline window `today - 7 days` — meaningless when runs have gaps | Anchor to `last_successful_run_date`, cap 90 days |
| B3 | `news_grouper.py` | Grouper assigns FIN/OTHER to HCM profile items | Constrain to profile LoB |
| B4 | `news_grouper.py` | "OTHER" category exists and accepted in email | Eliminate — items that don't fit profile LoB are false positives |
| B5 | `email_sender.py` | `published_at` never rendered in email | Show on every email card and in Review UI |
| B6 | `news_filter.py` | Binary yes/no filter — noise ("the king met the president") reaches email | Demote to pre-screen only; AI ranker is the real gate |
| B7 | `compare_news.py` | `hash_signature` breaks on minor editorial changes — cross-source dedup fails | Entity-based canonical fingerprint |
| B8 | `email_sender.py` | Translation called inside email sender (wrong layer) | Move to post-save step, store in DB, email sender renders only |

### 2.2 Structural Weaknesses

- **Rescue pass** is a near-no-op: requires human score ≥ 4 on baseline items, which almost never exists → powered by AI rank in v3
- **Binary filter** is the sole quality gate: no gradation of significance, noise and gazette entries are treated identically
- **Dedup silently drops** REPEATED news: repetition across sources is actually a significance signal, not noise
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
| **Repetition Tag** | Is this a recurring topic? | Cross-run frequency counter | NEW / REPEATED ×N / UPDATE |

These dimensions are **independent**. A rank 4 item with blank LoB Relevance is valid — it means the AI found a legally significant item that the current glossary cannot explain. This triggers a Glossary Gap Alert (see §7).

---

## 4. New Pipeline Architecture

```
FETCH (unchanged)
  RSS + Twitter/X + URL scrapers, date-windowed by profile date_scope
   ↓
PRE-SCREEN (coarse, fast, cheap)
  Binary LLM check — "is this vaguely related to [country] [LoB]?"
  Drop obvious garbage only. Not a quality gate.
   ↓
ANNOTATE (compare_news.py — redesigned)
  Entity fingerprint matching against last_successful_run_date baseline
  Classify: NEW | UPDATE (with delta) | REPEATED (with count) | DUPLICATE (log only)
  No items dropped. Everything annotated.
   ↓
RANK (new: news_ranker.py)
  Three-tier ranking engine (see §5)
  Each item receives Significance Rank 1–5
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
  All four dimensions stored per item
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
- `significance_rank INTEGER` — AI-assigned 1–5
- `rank_tier TEXT` — 'tier1' | 'tier2'
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

---

## 12. New Agent Files

| File | Purpose | Replaces |
|---|---|---|
| `agents/news_ranker.py` | Three-tier ranking engine | Part of `news_filter.py` |
| `agents/news_tagger.py` | Glossary keyword tagging + LoB relevance | Part of `news_grouper.py` |
| `agents/news_translator.py` | Post-save translation step | Extracted from `email_sender.py` |

Modified files:
- `agents/news_filter.py` — demoted to coarse pre-screen only
- `agents/compare_news.py` — redesigned as annotator (NEW/UPDATE/REPEATED/DUPLICATE)
- `agents/news_grouper.py` — replaced by tagger; LLM summarization removed
- `agents/email_sender.py` — pure rendering, no AI calls
- `configurations/db.py` — new tables + new columns
- `admin/app.py` — new Review UI routes (Challenge, Override, Glossary enrichment)
- `admin/templates/profile.html` / `review_news.html` — rank badges, gap alerts, challenge button

---

## 13. Transition Plan v2.32 → v3.0

### Phase 1 — Fix bugs (no pipeline changes)
- B1, B5, B8 — code-only fixes, no DB migration needed
- B2 — requires migration: add `last_successful_run_date` column to `runs` table (already exists as `completed_at` — verify and alias)
- B7 — requires migration: add `canonical_fingerprint TEXT` column to `news_items`; fingerprint = normalized(publication_date + issuing_authority_name + topic_noun_phrase)
- No visible behavior changes to user in this phase

### Phase 2 — Add ranking alongside existing pipeline
- Add `significance_rank` column (nullable) to `news_items`
- Add `news_ranker.py` — runs after filter, writes rank to DB
- Review UI shows rank — no email behavior change yet
- Validate ranking quality across all profiles before proceeding

### Phase 3 — Replace email filter with rank threshold
- Email gated on rank ≥ 3 (configurable)
- Binary filter demoted to pre-screen
- Fix B3, B4 (category/OTHER)

### Phase 4 — Replace grouping with tagging
- Add `news_tagger.py`
- Add topic label columns
- Redesign email organization by topic label
- Add publish date to email cards

### Phase 5 — Add Challenge + Grounding Loop
- Add `ranking_signals` and `ranking_grounding` tables
- Add Challenge UI + override reason validation chat
- Wire self-improving signal extraction

### Phase 6 — Add Glossary Gap Alert
- Red badge for rank ≥ 3 + no LoB match
- "+ Add to Glossary" inline action in Review UI

---

## 14. Version Naming

- v3.0 — Phase 3 complete (rank-gated email, bugs fixed)
- v3.1 — Phase 4 (tagging replaces grouping)
- v3.2 — Phase 5 (Challenge + grounding loop)
- v3.3 — Phase 6 (glossary gap alert)
