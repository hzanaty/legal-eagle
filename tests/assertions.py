import json
import sqlite3
from pathlib import Path


def _find_item(conn: sqlite3.Connection, profile_id: int, table: str, needle: str):
    """Return the row (as sqlite3.Row) whose title contains `needle` (case-insensitive)
    within the given profile+table, or None. Assumes a `title` column exists."""
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "title" not in cols:
        return None
    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"SELECT * FROM {table} WHERE profile_id=? AND LOWER(title) LIKE ? LIMIT 1",
        (profile_id, f"%{needle.lower()}%"),
    ).fetchone()


def _check_item_outcome(conn, profile_id, needle, expect_table, fields, not_null, absent_from):
    """Verify a single pipeline item's landing table and stamped fields.
    Returns (ok, error_message)."""
    # Absence case: item must not appear anywhere (or in the named table).
    if expect_table is None:
        target = absent_from or ["news_items", "filtered_news"]
        for tbl in target:
            if _find_item(conn, profile_id, tbl, needle) is not None:
                return False, f"'{needle}' unexpectedly present in {tbl}"
        return True, ""

    row = _find_item(conn, profile_id, expect_table, needle)
    if row is None:
        return False, f"'{needle}' not found in {expect_table}"

    keys = row.keys()
    for col, expected in (fields or {}).items():
        if col not in keys:
            return False, f"column '{col}' missing on {expect_table}"
        if str(row[col]) != str(expected):
            return False, f"{col}: expected {expected!r}, got {row[col]!r}"
    for col in (not_null or []):
        if col not in keys or row[col] is None:
            return False, f"{col} is null (expected value)"
    for tbl in (absent_from or []):
        if _find_item(conn, profile_id, tbl, needle) is not None:
            return False, f"'{needle}' unexpectedly also present in {tbl}"
    return True, ""


def _load_spec(version: str) -> dict:
    """Load a fixture spec, recursively merging delta files (base: <version> chain)."""
    fixtures_dir = Path(__file__).parent / "fixtures" / "expected"
    spec = json.loads((fixtures_dir / f"{version}.json").read_text())
    base_version = spec.get("base")
    if not base_version:
        return spec
    base_spec = _load_spec(base_version)
    # Delta: base assertions first, then override/extend with this version's assertions.
    # Deduplication key: (type, table?, column?, title_contains?) — delta entries win.
    def _key(a: dict) -> tuple:
        return (a.get("type"), a.get("table"), a.get("column"), a.get("title_contains"), a.get("topic_label"))
    merged: dict[tuple, dict] = {_key(a): a for a in base_spec["assertions"]}
    for a in spec["assertions"]:
        merged[_key(a)] = a  # delta entry overrides base
    return {**spec, "assertions": list(merged.values())}


def run_assertions(conn: sqlite3.Connection, profile_id: int, version: str, ai_available: bool = True) -> bool:
    spec = _load_spec(version)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    results = []
    skipped = []

    for a in spec["assertions"]:
        t, desc = a["type"], a["description"]
        # AI-dependent assertions (semantic dedup) are skipped when no embedding
        # cache / AI Core is available, so the deterministic suite stays green.
        if a.get("requires_ai") and not ai_available:
            skipped.append(desc)
            continue
        if t == "table_exists":
            ok = a["table"] in tables
            results.append((ok, desc, f"table '{a['table']}' missing" if not ok else ""))
        elif t == "column_exists":
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({a['table']})").fetchall()}
            ok = a["column"] in cols
            results.append((ok, desc, "column missing" if not ok else ""))
        elif t == "row_count":
            count = conn.execute(
                f"SELECT COUNT(*) FROM {a['table']} WHERE profile_id=?", (profile_id,)
            ).fetchone()[0]
            ok = count == a["expected"]
            results.append((ok, desc, f"expected {a['expected']}, got {count}" if not ok else ""))
        elif t == "value_check":
            row = conn.execute(
                f"SELECT {a['column']} FROM {a['table']} WHERE {a['where']} AND profile_id=? LIMIT 1",
                (profile_id,)
            ).fetchone()
            if "expected_not_null" in a:
                ok = row is not None and row[0] is not None
            else:
                ok = row is not None and str(row[0]) == str(a["expected"])
            results.append((ok, desc, "" if ok else f"got {row[0] if row else 'NO ROW'}"))
        elif t == "item_outcome":
            # Resolve one pipeline item by title substring within the profile, then
            # verify where it landed and its stamped fields. Flexible shape:
            #   title_contains: substring to locate the item (case-insensitive)
            #   expect_table:   'news_items' | 'filtered_news' | null (null = must NOT appear anywhere)
            #   fields:         {col: expected_value, ...} equality checks on the found row
            #   not_null:       [col, ...] columns that must be non-null on the found row
            #   absent_from:    [table, ...] tables the item must NOT appear in
            needle = a["title_contains"]
            expect_table = a.get("expect_table")
            ok, err = _check_item_outcome(conn, profile_id, needle, expect_table,
                                          a.get("fields"), a.get("not_null"),
                                          a.get("absent_from"))
            results.append((ok, desc, err))
        elif t == "rank_min":
            # Assert significance_rank >= min_rank for the named item.
            row = _find_item(conn, profile_id, a.get("table", "news_items"), a["title_contains"])
            if row is None:
                results.append((False, desc, f"'{a['title_contains']}' not found in news_items"))
            else:
                val = row["significance_rank"] if "significance_rank" in row.keys() else None
                ok = val is not None and int(val) >= a["min_rank"]
                msg = f"significance_rank={val}, expected >= {a['min_rank']}" if not ok else ""
                results.append((ok, desc, msg))
        elif t == "news_aspects_entry" or t == "news_announcements_entry":
            # Assert a news_announcements row exists for the given topic_label.
            count = conn.execute(
                "SELECT COUNT(*) FROM news_announcements WHERE LOWER(topic_label) LIKE ?",
                (f"%{a['topic_label'].lower()}%",),
            ).fetchone()[0]
            ok = count > 0
            results.append((ok, desc, f"no news_announcements row with topic_label '{a['topic_label']}'" if not ok else ""))

    print(f"\n[TEST] Legal Eagle {version} — Xanadu (XN/HCM)")
    all_pass = True
    for ok, desc, err in results:
        print(f"  {'[PASS]' if ok else '[FAIL]'} {desc}" + (f"  <- {err}" if err else ""))
        if not ok:
            all_pass = False
    for desc in skipped:
        print(f"  [SKIP] {desc}  <- needs AI Core / embedding cache")
    tail = f" ({len(skipped)} skipped — AI unavailable)" if skipped else ""
    print(f"\n  {sum(1 for o, _, _ in results if o)}/{len(results)} assertions passed{tail}")
    return all_pass
