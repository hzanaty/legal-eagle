# Source Attribution Design — Publisher + Authority

**Date:** 2026-09-04  
**Status:** Design Complete — Pending Implementation  
**Author:** Brainstorming session (I077750 + Claude)  
**Ships across:** v3.0 (config UI), v3.1 (pipeline), v3.2 (AI attribution + ranking), v3.3 (email grouping)

---

## 1. Context

The current pipeline has a fundamental attribution gap. Every RSS item is stored with `source_type = "RSS"` — the only source information persisted. By the time an item reaches the DB, there is no way to know:
- Which specific feed it came from
- Who published it (Saudi Gazette vs GOSI official website)
- Which legislative body issued the regulation (GOSI vs Ministry of HR)

This matters for ranking (first-party source = higher significance), dedup (same authority = stronger match signal), email grouping (group by authority, not just topic), and UI transparency.

---

## 2. Three Concepts

These are three distinct dimensions — each answers a different question:

| Term | Question | Example values |
|------|----------|---------------|
| **Channel** | How did we get it? | RSS, Twitter, URL |
| **Publisher** | Who published it on that channel? | "GOSI Official Website", "Saudi Gazette", "iKANUN" |
| **Authority** | Which legislative body issued it? | "GOSI", "Ministry of Human Resources" |

**Channel** already exists as `source_type` — only the UI label changes.

**Publisher** is user-configured per feed. If left blank, defaults to the feed's domain (e.g., `gosi.gov.sa`). A publisher like "iKANUN" (Turkey) aggregates from multiple authorities — so Publisher ≠ Authority.

**Authority** is optional. A feed may have a known authority (GOSI official site → GOSI) or no single authority (Saudi Gazette → blank). When blank, authority is either AI-detected or left unset.

---

## 3. Data Model

### New table: `authorities`
```sql
CREATE TABLE IF NOT EXISTS authorities (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    name TEXT NOT NULL,
    aliases TEXT  -- JSON array, e.g. ["GOSI", "General Organization for Social Insurance", "التأمينات"]
);
```
One row per known legislative body per profile. User-maintained via Configure tab.

### `rss_feeds` — two new columns (ALTER TABLE migration)
```sql
publisher_name TEXT   -- user-configured label; NULL defaults to domain at display time
authority_id INTEGER  -- FK → authorities.id; NULL = mixed publisher (e.g. iKANUN)
```

### `url_sources` — two new columns (ALTER TABLE migration)
```sql
publisher_name TEXT
authority_id INTEGER  -- FK → authorities.id; NULL = mixed
```

### `news_items` — three new columns (ALTER TABLE migration)
```sql
publisher TEXT        -- denormalized from feed config at fetch time; never changes after insert
authority_id INTEGER  -- FK → authorities.id; NULL until attributed
authority_status TEXT -- "configured" | "ai_suggested" | "human_confirmed" | "human_overridden"
```

### `filtered_news` — same three new columns (ALTER TABLE migration)
```sql
publisher TEXT
authority_id INTEGER
authority_status TEXT
```

**Denormalization rationale:** `publisher` is stored directly on `news_items` (not just a FK to `rss_feeds`) so that feed renames or deletions never retroactively change an item's historical publisher.

---

## 4. Pipeline — ATTRIBUTE Stage

New pipeline stage inserted between ANNOTATE (dedup) and RANK:

```
FETCH → ANNOTATE → [ATTRIBUTE] → RANK → TAG → TRANSLATE → SAVE → EMAIL
```

### New agent: `agents/authority_attributor.py`

Entry point: `attribute_authorities(items, profile_id, conn)`

Per item logic:
1. **Feed has `authority_id` set** → stamp `authority_id` on item, set `authority_status = "configured"`. No AI call. Done.
2. **Feed has no `authority_id`** AND profile has at least one authority defined → AI call: pass item title + content + profile authorities list (name + aliases) → model returns best match ID or `"none"` → set `authority_id` + `authority_status = "ai_suggested"`.
3. **Profile has no authorities defined** → skip. `authority_id = NULL`, no `authority_status` set.

**Non-blocking:** If attribution fails for an item (AI error, timeout), `authority_id` stays NULL and the item continues through the pipeline. Attribution is enrichment, never a gate.

**AI caching:** Authority attribution AI calls are intercepted by the same `cached_ai_call()` wrapper used in the test harness. Cache key = SHA-256 of the exact prompt. Cached after first run — free on all subsequent runs.

### Authority-assisted dedup

In `agents/compare_news.py`, when comparing two items that both have a non-null `authority_id` and the `authority_id` values match, lower the cosine similarity threshold:

| Condition | Cosine threshold (duplicate) | Cosine threshold (near-dedup) |
|-----------|------------------------------|-------------------------------|
| No authority match | 0.92 (current) | 0.85 (current) |
| Same `authority_id` | 0.80 | 0.70 |

Same authority + similar content = stronger duplicate signal.

---

## 5. Ranking Engine Impact

### New Tier 1 rule: first-party source boost

Add to `ranking_signals` table at profile setup time:

```
signal_type: "first_party_source"
pattern: authority_id matches publisher's authority_id
min_rank: current_rank + 1  (boost, not override)
confidence: 0.90
created_from: "initial_setup"
```

An item published directly by the issuing authority (GOSI official website publishing GOSI news) gets a +1 rank boost. Third-party coverage (Saudi Gazette reporting on GOSI circular) does not.

---

## 6. UI Changes

### Configure tab — Authorities section (new)

New section below RSS Feeds in the profile Configure tab:

**Authorities table:**
```
Name                              | Aliases            | Actions
Xanadu Social Insurance Org       | XNSO, التأمينات   | Edit | Delete
Ministry of Human Resources       | MoHR               | Edit | Delete
[+ Add Authority]
```

**Add/Edit Authority form:** Name (required) + Aliases (comma-separated, optional)

### Configure tab — Feed add/edit form (updated)

Two new optional fields added to the existing RSS feed form:
- **Publisher Name** — text input, placeholder: "Auto: gosi.gov.sa" (shows domain if blank)
- **Authority** — dropdown: "None (mixed publisher)" + one option per profile authority

Same update applied to URL source add/edit form.

### Review tab — Column changes

| Before | After |
|--------|-------|
| "Source" column showing `RSS` badge | **Channel** column showing `RSS` / `Twitter` / `URL` badge |
| *(not present)* | **Publisher** column: publisher name text |
| *(not present)* | **Authority** column: authority name + status icon + override |

**Authority status icons:**
- 🔒 `configured` — came from feed's pre-set authority, certain
- ✦ `ai_suggested` — AI detected, pending human review
- ✓ `human_confirmed` — user confirmed AI suggestion
- *(pencil)* `human_overridden` — user selected different authority

**Override interaction:** clicking the authority cell opens an inline dropdown listing all profile authorities + "Unknown". Selecting updates `authority_id` + sets `authority_status = "human_overridden"` or `"human_confirmed"`.

---

## 7. Version Placement

| Version | Deliverable |
|---------|------------|
| **v3.0** | DB: `authorities` table + `rss_feeds`/`url_sources` new columns. Configure tab: Authorities CRUD + updated feed/source forms. Review UI: "Source" renamed to "Channel" + stub Publisher/Authority columns (show "—" until v3.1 populates them). |
| **v3.1** | DB: `news_items`/`filtered_news` new columns. ATTRIBUTE stage: configured path only (stamp from feed config, no AI). Publisher + Authority columns populated in Review UI. Same-authority dedup threshold lowering in `compare_news.py`. |
| **v3.2** | Tier 1 first-party ranking boost. ATTRIBUTE AI path for mixed publishers. ✦ spark icon + override dropdown in Review UI. |
| **v3.3** | Email V2 digest: primary grouping by Authority (with Topic Label as secondary grouping within each authority block). |

---

## 8. New / Modified Files

| File | Change |
|------|--------|
| `agents/authority_attributor.py` | New — ATTRIBUTE stage agent |
| `agents/compare_news.py` | Add same-authority dedup threshold logic |
| `agents/agents_controller.py` | Call `attribute_authorities()` after ANNOTATE, before RANK |
| `agents/rss_parser.py` | Accept `publisher_name` param; stamp on items; extract `entry.author` as secondary field |
| `configurations/db.py` | New `authorities` table; ALTER migrations for all four affected tables |
| `configurations/config_loader.py` | Update `load_rss_feeds()` + `load_url_sources()` to return `publisher_name` + `authority_id` |
| `admin/app.py` | New CRUD routes for authorities; updated feed/source add routes; Review UI authority override route |
| `admin/templates/profile.html` | Authorities section; updated feed/source forms |
| `admin/templates/review_news.html` | Channel/Publisher/Authority columns; override interaction |
