#!/usr/bin/env python3
import argparse, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

HERE = os.path.dirname(__file__)
TEST_DB_PATH = os.path.join(HERE, "test.db")
FIXTURES_DIR = os.path.join(HERE, "fixtures")
AI_CACHE_DIR = os.path.join(HERE, "ai_cache")


def run_v3_0():
    from tests.reset_and_seed import reset_and_seed
    from tests.assertions import run_assertions
    print("[TEST] v3.0 harness — DB schema verification")
    conn, pid = reset_and_seed()
    print(f"[OK]  DB reset, XN/HCM profile created (id={pid})")
    ok = run_assertions(conn, pid, "v3.0")
    conn.close()
    sys.exit(0 if ok else 1)


def run_v3_1():
    """First full pipeline run: fetch → attribute → dedup, then assert outcomes.

    The pipeline is pointed at the isolated test DB (LEGAL_EAGLE_DB) and replays
    embeddings from the AI cache (LEGAL_EAGLE_AI_CACHE) for offline determinism.
    Env vars MUST be set before importing config_loader / agents.
    """
    os.environ["LEGAL_EAGLE_DB"] = TEST_DB_PATH
    os.environ["LEGAL_EAGLE_AI_CACHE"] = AI_CACHE_DIR
    os.environ["DISABLE_TWEETS"] = "1"  # no live Twitter in the harness

    from tests.server import start_server, stop_server
    from tests.reset_and_seed import reset_and_seed
    from tests.assertions import run_assertions
    from configurations.db import get_connection

    print("[TEST] v3.1 harness — first full pipeline run (attribution + dedup + age)")
    server = start_server(FIXTURES_DIR)
    print(f"[OK]  Fixture server on :9999 (root={FIXTURES_DIR})")
    try:
        conn, pid = reset_and_seed()
        conn.close()
        print(f"[OK]  DB reset + seeded (id={pid}), pointing pipeline at test.db")

        # Import AFTER env is set so config_loader resolves the test DB.
        from agents.agents_controller import run_profile_once
        print("[RUN] run_profile_once(skip_filter, skip_grouping, skip_email)...")
        run_profile_once(
            pid,
            skip_filter=True,      # v3.1: relevance filter deleted → all items pass
            skip_grouping=True,    # avoid grouping AI call in the harness
            skip_email=True,       # no email send; DB is already written by compare
        )

        conn = get_connection(TEST_DB_PATH)
        # AI is "available" for assertions only if the embedding cache was populated
        # (a prior recording run against live AI Core). Otherwise semantic-dedup
        # assertions are skipped rather than failed.
        import glob
        ai_available = bool(glob.glob(os.path.join(AI_CACHE_DIR, "emb_*.json")))
        ok = run_assertions(conn, pid, "v3.1", ai_available=ai_available)
        conn.close()
    finally:
        stop_server(server)
    sys.exit(0 if ok else 1)


def run_v3_2():
    """Ranking engine live: fetch → attribute → dedup → rank, then assert outcomes.

    Extends v3.1: ranking_signals seeded with bootstrap Tier 1 keywords so rank
    assertions are deterministic offline. Attribution AI assertions are AI-gated.
    """
    os.environ["LEGAL_EAGLE_DB"] = TEST_DB_PATH
    os.environ["LEGAL_EAGLE_AI_CACHE"] = AI_CACHE_DIR
    os.environ["DISABLE_TWEETS"] = "1"

    from tests.server import start_server, stop_server
    from tests.reset_and_seed import reset_and_seed
    from tests.assertions import run_assertions
    from configurations.db import get_connection

    print("[TEST] v3.2 harness — ranking engine live (Tier 1 deterministic + Tier 2 AI + REPEATED tag)")
    server = start_server(FIXTURES_DIR)
    print(f"[OK]  Fixture server on :9999 (root={FIXTURES_DIR})")
    try:
        conn, pid = reset_and_seed()
        conn.close()
        print(f"[OK]  DB reset + seeded (id={pid}), pointing pipeline at test.db")

        from agents.agents_controller import run_profile_once
        print("[RUN] run_profile_once(skip_grouping, skip_email)...")
        run_profile_once(
            pid,
            skip_filter=True,
            skip_grouping=True,
            skip_email=True,
        )

        conn = get_connection(TEST_DB_PATH)
        import glob
        ai_available = (
            bool(glob.glob(os.path.join(AI_CACHE_DIR, "emb_*.json")))
            and bool(glob.glob(os.path.join(AI_CACHE_DIR, "chat_*.json")))
        )
        ok = run_assertions(conn, pid, "v3.2", ai_available=ai_available)
        conn.close()
    finally:
        stop_server(server)
    sys.exit(0 if ok else 1)


def run_v3_3():
    """Tagging + email rank gate live: fetch → attribute → dedup → rank → tag → email gate.

    Extends v3.2: news_tagger.py assigns topic_label; rank gate sets email_eligible.
    Schema assertions (column_exists + table_exists) pass deterministically.
    email_eligible assertions for C4 are AI-gated (require embedding cache for dedup).
    """
    os.environ["LEGAL_EAGLE_DB"] = TEST_DB_PATH
    os.environ["LEGAL_EAGLE_AI_CACHE"] = AI_CACHE_DIR
    os.environ["DISABLE_TWEETS"] = "1"

    from tests.server import start_server, stop_server
    from tests.reset_and_seed import reset_and_seed
    from tests.assertions import run_assertions
    from configurations.db import get_connection

    print("[TEST] v3.3 harness — tagging + email rank gate (topic_label + email_eligible)")
    server = start_server(FIXTURES_DIR)
    print(f"[OK]  Fixture server on :9999 (root={FIXTURES_DIR})")
    try:
        conn, pid = reset_and_seed()
        conn.close()
        print(f"[OK]  DB reset + seeded (id={pid}), pointing pipeline at test.db")

        from agents.agents_controller import run_profile_once
        print("[RUN] run_profile_once(skip_grouping, skip_email)...")
        run_profile_once(
            pid,
            skip_filter=True,
            skip_grouping=True,
            skip_email=True,
        )

        # Populate news_announcements so content assertions can run.
        import sqlite3 as _sqlite3
        from configurations.db import create_run
        _conn = get_connection(TEST_DB_PATH)
        _conn.row_factory = _sqlite3.Row
        _run_id = create_run(_conn, pid, origin="harness")
        _items = _conn.execute(
            "SELECT * FROM news_items WHERE profile_id=? AND email_eligible=1", (pid,)
        ).fetchall()
        if _items:
            from agents.email_composer import generate_digest
            print(f"[RUN] generate_digest({len(_items)} eligible items) for news_announcements…")
            generate_digest([dict(it) for it in _items], pid, _conn, _run_id)
        _conn.close()

        conn = get_connection(TEST_DB_PATH)
        import glob
        ai_available = (
            bool(glob.glob(os.path.join(AI_CACHE_DIR, "emb_*.json")))
            and bool(glob.glob(os.path.join(AI_CACHE_DIR, "chat_*.json")))
        )
        ok = run_assertions(conn, pid, "v3.3", ai_available=ai_available)
        conn.close()
    finally:
        stop_server(server)
    sys.exit(0 if ok else 1)


def run_v3_4():
    """Challenge + grounding loop: all v3.3 assertions pass, plus new table/column schema checks.

    New in v3.4: ranking_grounding + ranking_signals tables exist, human_rank_override column exists,
    Review hierarchy (news_announcements) still populated. Challenge routes not tested here (HTTP flows).
    """
    os.environ["LEGAL_EAGLE_DB"] = TEST_DB_PATH
    os.environ["LEGAL_EAGLE_AI_CACHE"] = AI_CACHE_DIR
    os.environ["DISABLE_TWEETS"] = "1"

    from tests.server import start_server, stop_server
    from tests.reset_and_seed import reset_and_seed
    from tests.assertions import run_assertions
    from configurations.db import get_connection

    print("[TEST] v3.4 harness — challenge + grounding loop")
    server = start_server(FIXTURES_DIR)
    print(f"[OK]  Fixture server on :9999 (root={FIXTURES_DIR})")
    try:
        conn, pid = reset_and_seed()
        conn.close()
        print(f"[OK]  DB reset + seeded (id={pid}), pointing pipeline at test.db")

        from agents.agents_controller import run_profile_once
        print("[RUN] run_profile_once(skip_grouping, skip_email)...")
        run_profile_once(
            pid,
            skip_filter=True,
            skip_grouping=True,
            skip_email=True,
        )

        import sqlite3 as _sqlite3
        from configurations.db import create_run
        _conn = get_connection(TEST_DB_PATH)
        _conn.row_factory = _sqlite3.Row
        _run_id = create_run(_conn, pid, origin="harness")
        _items = _conn.execute(
            "SELECT * FROM news_items WHERE profile_id=? AND email_eligible=1", (pid,)
        ).fetchall()
        if _items:
            from agents.email_composer import generate_digest
            print(f"[RUN] generate_digest({len(_items)} eligible items) for news_announcements…")
            generate_digest([dict(it) for it in _items], pid, _conn, _run_id)
        _conn.close()

        conn = get_connection(TEST_DB_PATH)
        import glob
        ai_available = (
            bool(glob.glob(os.path.join(AI_CACHE_DIR, "emb_*.json")))
            and bool(glob.glob(os.path.join(AI_CACHE_DIR, "chat_*.json")))
        )
        ok = run_assertions(conn, pid, "v3.4", ai_available=ai_available)
        conn.close()
    finally:
        stop_server(server)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.version == "v3.0":
        run_v3_0()
    elif args.version == "v3.1":
        run_v3_1()
    elif args.version == "v3.2":
        run_v3_2()
    elif args.version == "v3.3":
        run_v3_3()
    elif args.version == "v3.4":
        run_v3_4()
    else:
        print(f"Version {args.version} not yet in harness")
        sys.exit(1)
