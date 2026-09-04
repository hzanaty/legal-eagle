# Test Harness Design — Deterministic Integration Tests

**Date:** 2026-09-04  
**Status:** Design Complete — Pending Implementation  
**Author:** Brainstorming session (I077750 + Claude)  
**Purpose:** Automated pass/fail verification for every v3.x upgrade

---

## 1. Context

The v3 upgrade is large — 8 bug fixes, new pipeline stages, new DB schema, new ranking engine. Without a controlled test harness, regressions are invisible until they reach production. This harness provides:

- **Deterministic input:** pre-crafted RSS feeds with known content
- **Deterministic expected output:** since input is known, correct output is calculable
- **Fully automated:** no human judgment needed — every assertion is binary pass/fail
- **Demo-ready:** feed URLs look real (`http://localhost:9999/feeds/xn_feed_a.xml`), article links open real pages, profile configured just like a production profile

---

## 2. Infrastructure

### Feed server
```bash
python -m http.server 9999 --directory tests/fixtures/
```
Serves both RSS XML files and article HTML pages from the same port. Zero extra dependencies — built into Python stdlib.

Feed URLs entered in the Legal Eagle admin UI: `http://localhost:9999/feeds/xn_feed_a_relevant.xml`  
Article links in feed items: `http://localhost:9999/articles/a1.html`

### AI calls — hybrid caching
- **First run:** real SAP AI Core calls (ranking, filtering, authority attribution)
- **Subsequent runs:** responses replayed from `tests/ai_cache/<prompt-hash>.json`
- **Cache key:** SHA-256 of the exact prompt string sent to the model
- **Cache committed to repo** — demo and CI runs never touch the live API
- **Activated by:** `LEGAL_EAGLE_TEST_MODE=1` environment variable

### DB lifecycle
Full reset before every run. No state leaks between runs.

### Two datasets
| Dataset | What it is | Purpose |
|---------|-----------|---------|
| **Feed XML files** | Served by localhost:9999 | What Legal Eagle fetches this run |
| **Baseline seed** (`seed/baseline.json`) | Pre-loaded into `news_items` | What Legal Eagle has "seen before" — gives dedup engine prior context |

Without the baseline, all items look new and dedup/duplicate tests cannot run.

---

## 3. Directory Structure

```
tests/
  fixtures/
    feeds/
      xn_feed_a_relevant.xml     ← 4 HCM-relevant items (must pass)
      xn_feed_b_filtered.xml     ← noise + wrong LoB + old items (must fail)
      xn_feed_c_duplicates.xml   ← exact + near + intra-run duplicates
      xn_feed_d_repeated.xml     ← items seen 3+ times (v3.2 REPEATED tag test)
    articles/
      a1.html                    ← article page for feed item A1
      a2.html
      a3.html
      a4.html
    seed/
      baseline.json              ← 6 news_items rows pre-loaded before each run
    expected/
      v3.0.json                  ← assertions for v3.0
      v3.1.json
      v3.2.json                  ← adds rank assertions
      v3.3.json                  ← adds email + authority group assertions
      v3.4.json                  ← adds grounding/challenge assertions
      v3.5.json                  ← adds glossary gap badge assertions
  ai_cache/
    <prompt-hash>.json           ← cached AI responses (committed to repo)
  run_harness.py                 ← single entry point
  server.py                      ← http.server subprocess wrapper
  reset_and_seed.py              ← DB reset + profile creation + baseline injection
  assertions.py                  ← loads expected/vX.Y.json, queries DB, prints results
  ai_cache_utils.py              ← cached_ai_call(prompt, call_fn) wrapper
```

---

## 4. Test Profile: "Xanadu" (XN / HCM)

An imaginary country with English-language labor regulations — no real-world data dependency.

| Field | Value |
|-------|-------|
| `country_code` | `XN` |
| `lob` | `HCM` |
| `name` | "Test Country HCM" |
| `language` | `en` |

**Glossary terms:** social insurance, payroll, employment contract, maternity leave, pension fund, minimum wage, termination notice

**Authorities:**
- "Ministry of Human Resources" (aliases: MoHR)
- "Xanadu Social Insurance Organization" (aliases: XNSO)

**RSS feeds configured in admin UI:**
```
http://localhost:9999/feeds/xn_feed_a_relevant.xml   publisher: "XN Ministry of HR"      authority: Ministry of Human Resources
http://localhost:9999/feeds/xn_feed_b_filtered.xml   publisher: "XN Mixed News Portal"   authority: (none)
http://localhost:9999/feeds/xn_feed_c_duplicates.xml publisher: "XN Official Gazette"    authority: (none — mixed)
http://localhost:9999/feeds/xn_feed_d_repeated.xml   publisher: "XNSO Official Feed"     authority: Xanadu Social Insurance Organization
```

---

## 5. Test Data

### `xn_feed_a_relevant.xml` — 4 items that must pass

Each item contains: `<title>`, `<link>` (→ localhost article page), `<pubDate>` (1–3 days ago), `<description>` (2–3 sentence body text), `<author>` (authority name).

| ID | Title | Expected outcome |
|----|-------|-----------------|
| A1 | "Xanadu Ministry updates maternity leave to 16 weeks" | Pass filter, rank 4–5 (v3.2+) |
| A2 | "New social insurance contribution rates effective Q1 2027" | Pass filter, rank 4–5 |
| A3 | "Employment Law Amendment: termination notice period extended to 60 days" | Pass filter, rank 4–5 |
| A4 | "Pension fund reform bill passes second parliamentary reading" | Pass filter, rank 3–4 |

### `xn_feed_b_filtered.xml` — 5 items that must be rejected

| ID | Title | Rejection reason |
|----|-------|-----------------|
| B1 | "Xanadu central bank raises benchmark interest rate to 6.5%" | Wrong LoB (FIN) → semantic filter |
| B2 | "President of Xanadu holds bilateral meeting with foreign trade delegation" | Noise (diplomacy) → semantic filter |
| B3 | "Xanadu signs new regional trade facilitation agreement" | Noise (trade/politics) → semantic filter |
| B4 | "Annual minimum wage review committee to convene next spring" | `pubDate` = 30 days ago → age gate |
| B5 | "Xanadu parliament approves three-year tax reform package" | Wrong LoB (FIN) → semantic filter |

### `xn_feed_c_duplicates.xml` — 4 dedup scenario items

| ID | Item | Expected outcome |
|----|------|-----------------|
| C1 | Exact copy of baseline row S2 (same URL, same guid) | Exact dedup → DUPLICATE (rank 0) |
| C2 | Same story as S3, reworded ("contribution rates set to increase next quarter") | Near-dedup (cosine + Jaccard) → DUPLICATE |
| C3 | Same authority (XNSO) + same story as a concurrent feed item, different guid | Intra-run dedup → second occurrence DUPLICATE |
| C4 | "Xanadu introduces mandatory health insurance for part-time workers" (new) | Passes dedup + filter → new item |

### `xn_feed_d_repeated.xml` — 3 items for REPEATED tag test (v3.2+)

Items R1–R3 have the same URL and hash as baseline rows S4–S6, which carry `repetition_count = 3`. In v3.2, these should receive the `REPEATED` tag and a +1 rank boost.

| ID | Title | Expected (v3.2+) |
|----|-------|-----------------|
| R1 | "XNSO circular: updated contribution table published" | REPEATED tag, rank elevated +1 |
| R2 | "Payroll compliance deadline extended to end of quarter" | REPEATED tag, rank elevated +1 |
| R3 | "Employment contract registration portal maintenance announced" | REPEATED tag, rank elevated +1 |

### `seed/baseline.json` — 6 pre-loaded `news_items` rows

```json
[
  {
    "id_label": "S1",
    "purpose": "Previously filtered high-score item — provides second-chance rescue baseline",
    "source_type": "RSS", "profile_id": "XN/HCM",
    "title": "Xanadu labor code amendment draft released for public comment",
    "relevance_score": 4
  },
  {
    "id_label": "S2",
    "purpose": "Exact match target for C1",
    "url": "http://localhost:9999/articles/s2.html",
    "guid": "xn-gazette-2026-0901-001"
  },
  {
    "id_label": "S3",
    "purpose": "Near-match target for C2 (social insurance contribution story, different wording)"
  },
  {
    "id_label": "S4", "repetition_count": 3,
    "purpose": "REPEATED target for R1"
  },
  {
    "id_label": "S5", "repetition_count": 3,
    "purpose": "REPEATED target for R2"
  },
  {
    "id_label": "S6", "repetition_count": 3,
    "purpose": "REPEATED target for R3"
  }
]
```

---

## 6. AI Cache

### `tests/ai_cache_utils.py`

```python
def cached_ai_call(prompt: str, call_fn: callable) -> dict:
    cache_key = hashlib.sha256(prompt.encode()).hexdigest()
    cache_path = Path(__file__).parent / "ai_cache" / f"{cache_key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())["response"]
    response = call_fn()
    cache_path.write_text(json.dumps({
        "prompt_hash": cache_key,
        "response": response,
        "cached_at": datetime.utcnow().isoformat()
    }, indent=2))
    return response
```

In `LEGAL_EAGLE_TEST_MODE=1`, all pipeline AI calls are wrapped with `cached_ai_call()`. The call function is passed as a lambda so the cache check runs before any network call.

---

## 7. Assertions Format (`expected/vX.Y.json`)

```json
{
  "version": "v3.1",
  "profile": { "country_code": "XN", "lob": "HCM" },
  "assertions": [
    {
      "item_id": "A1",
      "title_contains": "maternity leave",
      "expected_outcome": "passed",
      "expected_publisher": "XN Ministry of HR",
      "expected_authority": "Ministry of Human Resources",
      "expected_authority_status": "configured"
    },
    {
      "item_id": "B4",
      "title_contains": "minimum wage review",
      "expected_outcome": "filtered",
      "expected_filter_reason": "too_old"
    },
    {
      "item_id": "C1",
      "title_contains": "gazette",
      "expected_outcome": "duplicate"
    }
  ]
}
```

**Additional fields added per version:**
- `v3.2.json` adds: `"expected_rank_min": 4`, `"expected_tag": "REPEATED"`
- `v3.3.json` adds: `"expected_email_eligible": true`, `"expected_authority_group": "Ministry of Human Resources"`
- `v3.4.json` adds: `"expected_tier": "tier1"` (for pre-seeded grounding test)
- `v3.5.json` adds: `"expected_gap_badge": true` (for rank ≥ 3 + no glossary match item)

**Only deltas between versions.** `v3.2.json` lists only the assertions that change from `v3.1.json`. `assertions.py` merges the active version's file with the base `v3.1.json`.

---

## 8. Orchestration Flow (`run_harness.py --version vX.Y`)

```
Step 1  Start HTTP server
        subprocess: python -m http.server 9999 --directory tests/fixtures/
        Poll localhost:9999 until ready (max 5s timeout)

Step 2  Reset DB
        Drop all tables for XN/HCM profile (or delete test DB entirely)
        Re-run create_schema_if_needed()

Step 3  Create test profile
        Insert XN/HCM profile
        Insert glossary terms
        Insert authorities: Ministry of HR + XNSO
        Insert RSS feeds pointing to localhost:9999/feeds/xn_feed_*.xml
        (with publisher_name + authority_id pre-configured per feed)

Step 4  Inject baseline seed
        Load tests/fixtures/seed/baseline.json
        Insert all rows into news_items for XN/HCM profile

Step 5  Run pipeline
        os.environ["LEGAL_EAGLE_TEST_MODE"] = "1"
        Call run_profile_once(profile_id)  ← real pipeline, no mocking
        Wait for completion

Step 6  Assert
        Load tests/fixtures/expected/<version>.json
        Query news_items + filtered_news for XN/HCM profile
        Compare actual results against expected assertions
        Print pass/fail table

Step 7  Stop HTTP server
        Terminate subprocess

Step 8  Exit
        sys.exit(0) if all assertions passed
        sys.exit(1) if any assertion failed  ← CI-friendly
```

**Key principle:** Step 5 calls `run_profile_once()` — the exact same function production uses. The only test-mode behavior is AI responses coming from cache instead of the live API.

---

## 9. Version Delta Table

The same XML feed files run for every version. Only `expected/vX.Y.json` and `seed/baseline.json` change.

| Version | What's tested | Test data change |
|---------|--------------|-----------------|
| **v3.0** | Admin UI only — no pipeline run | Harness verifies profile, authorities, and feeds saved correctly to DB. No `run_profile_once()` call. |
| **v3.1** | First full pipeline run: filter, dedup, publisher/authority stamping | All assertions from `v3.1.json`. Assert publisher + authority_status = "configured" on A1–A4. |
| **v3.2** | Ranking engine + REPEATED tag + AI authority attribution | Add `expected_rank_min` to A1–A4. Add `repeat_count=3` to S4–S6 in seed. Assert REPEATED tag + rank boost on R1–R3. Assert ✦ icon (ai_suggested) on items from feed_c (mixed publisher). |
| **v3.3** | Email eligibility + authority grouping in digest | Add `expected_email_eligible: true` for rank ≥ 3 items. Add `expected_authority_group` assertions. |
| **v3.4** | Self-improving grounding — Tier 1 catches pre-seeded pattern | Add one pre-seeded row to `ranking_grounding` in seed. Assert `expected_tier: "tier1"` on matching item. |
| **v3.5** | Glossary gap badge | Add 1 item to `xn_feed_a_relevant.xml`: rank ≥ 3 HCM item with no glossary keyword match. Assert `expected_gap_badge: true`. |

---

## 10. Running the Harness

```bash
# First run (populates AI cache — requires live SAP AI Core)
python tests/run_harness.py --version v3.1

# Subsequent runs (uses cache — instant, free, works offline)
python tests/run_harness.py --version v3.1

# Run specific version
python tests/run_harness.py --version v3.2

# CI integration (exit code drives pass/fail)
python tests/run_harness.py --version v3.1 && echo "PASSED" || echo "FAILED"
```

Expected output:
```
[TEST] Legal Eagle v3.1 — Xanadu (XN/HCM)
[OK]  Server started on localhost:9999
[OK]  DB reset and profile created
[OK]  Baseline seed injected (6 rows)
[OK]  Pipeline run completed

[PASS] A1 maternity leave           → passed | publisher: XN Ministry of HR | authority: configured
[PASS] A2 social insurance rates    → passed | publisher: XN Ministry of HR | authority: configured
[PASS] A3 termination notice        → passed | publisher: XN Ministry of HR | authority: configured
[PASS] A4 pension fund reform       → passed | publisher: XN Ministry of HR | authority: configured
[PASS] B1 interest rates            → filtered (semantic_check_failed)
[PASS] B4 minimum wage review       → filtered (too_old)
[PASS] C1 gazette duplicate         → duplicate (exact)
[PASS] C2 near-duplicate            → duplicate (near)
[PASS] C4 health insurance          → passed

9/9 assertions passed
[OK]  Server stopped
```
