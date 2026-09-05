"""
Copies the latest harness run data from tests/test.db → configurations/config.db
for the Xanadu (XN/HCM) demo profile. Run after a successful harness pass.

Usage: python3 scripts/refresh_xanadu_demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configurations.db import get_connection

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'tests', 'test.db')
LIVE_DB = os.path.join(os.path.dirname(__file__), '..', 'configurations', 'config.db')

if not os.path.exists(TEST_DB):
    print("ERROR: tests/test.db not found — run the harness first")
    sys.exit(1)

live = get_connection(LIVE_DB)
test = get_connection(TEST_DB)

xn_test = test.execute("SELECT id FROM profiles WHERE country_code='XN'").fetchone()
xn_live = live.execute("SELECT id FROM profiles WHERE country_code='XN'").fetchone()
if not xn_test:
    print("ERROR: XN profile not found in test.db — run the harness first")
    sys.exit(1)
if not xn_live:
    print("ERROR: XN profile not found in config.db — create it first")
    sys.exit(1)

test_pid = xn_test['id']
live_pid = xn_live['id']

# -- Clear existing Xanadu data from live --
old_run_ids = [r[0] for r in live.execute(
    "SELECT id FROM runs WHERE profile_id=?", (live_pid,)).fetchall()]
if old_run_ids:
    ph = ','.join('?' * len(old_run_ids))
    live.execute(f"DELETE FROM news_announcements WHERE run_id IN ({ph})", old_run_ids)
live.execute("DELETE FROM news_items WHERE profile_id=?", (live_pid,))
live.execute("DELETE FROM runs WHERE profile_id=?", (live_pid,))

# -- Copy run --
run_row = test.execute(
    "SELECT * FROM runs WHERE profile_id=? ORDER BY id DESC LIMIT 1", (test_pid,)).fetchone()
if not run_row:
    print("ERROR: no run in test.db — run the harness first")
    sys.exit(1)
old_run_id = run_row['id']

run_cols = [r[1] for r in test.execute("PRAGMA table_info(runs)").fetchall() if r[1] != 'id']
live_run_cols = {r[1] for r in live.execute("PRAGMA table_info(runs)").fetchall()}
shared_run_cols = [c for c in run_cols if c in live_run_cols]

vals = {c: run_row[c] for c in shared_run_cols}
vals['profile_id'] = live_pid
cols_str = ','.join(vals.keys())
ph_str = ','.join([f':{c}' for c in vals.keys()])
cur = live.execute(f"INSERT INTO runs ({cols_str}) VALUES ({ph_str})", vals)
new_run_id = cur.lastrowid

# -- Copy news_items (no run_id; use profile_id) --
items = test.execute("SELECT * FROM news_items WHERE profile_id=?", (test_pid,)).fetchall()
item_cols = [r[1] for r in test.execute("PRAGMA table_info(news_items)").fetchall() if r[1] != 'id']
live_item_cols = {r[1] for r in live.execute("PRAGMA table_info(news_items)").fetchall()}
shared_item_cols = [c for c in item_cols if c in live_item_cols]

for item in items:
    d = {c: item[c] for c in shared_item_cols}
    d['profile_id'] = live_pid
    cols_str = ','.join(d.keys())
    ph_str = ','.join([f':{c}' for c in d.keys()])
    live.execute(f"INSERT INTO news_items ({cols_str}) VALUES ({ph_str})", d)

# -- Copy news_announcements (has run_id) --
anns = test.execute("SELECT * FROM news_announcements WHERE run_id=?", (old_run_id,)).fetchall()
ann_cols = [r[1] for r in test.execute("PRAGMA table_info(news_announcements)").fetchall() if r[1] != 'id']
live_ann_cols = {r[1] for r in live.execute("PRAGMA table_info(news_announcements)").fetchall()}
shared_ann_cols = [c for c in ann_cols if c in live_ann_cols]

for ann in anns:
    d = {c: ann[c] for c in shared_ann_cols}
    d['run_id'] = new_run_id
    cols_str = ','.join(d.keys())
    ph_str = ','.join([f':{c}' for c in d.keys()])
    live.execute(f"INSERT INTO news_announcements ({cols_str}) VALUES ({ph_str})", d)

live.commit()
print(f"Xanadu refreshed: {len(items)} items, {len(anns)} announcements "
      f"(live profile id={live_pid}, run id={new_run_id})")
test.close()
live.close()
