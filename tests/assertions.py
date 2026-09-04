import json
import sqlite3
from pathlib import Path

def run_assertions(conn: sqlite3.Connection, profile_id: int, version: str) -> bool:
    spec_path = Path(__file__).parent / "fixtures" / "expected" / f"{version}.json"
    spec = json.loads(spec_path.read_text())
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    results = []

    for a in spec["assertions"]:
        t, desc = a["type"], a["description"]
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

    print(f"\n[TEST] Legal Eagle {version} — Xanadu (XN/HCM)")
    all_pass = True
    for ok, desc, err in results:
        print(f"  {'[PASS]' if ok else '[FAIL]'} {desc}" + (f"  <- {err}" if err else ""))
        if not ok:
            all_pass = False
    print(f"\n  {sum(1 for o, _, _ in results if o)}/{len(results)} assertions passed")
    return all_pass
