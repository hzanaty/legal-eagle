#!/usr/bin/env python3
import argparse, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def run_v3_0():
    from tests.reset_and_seed import reset_and_seed
    from tests.assertions import run_assertions
    print("[TEST] v3.0 harness — DB schema verification")
    conn, pid = reset_and_seed()
    print(f"[OK]  DB reset, XN/HCM profile created (id={pid})")
    ok = run_assertions(conn, pid, "v3.0")
    conn.close()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.version == "v3.0":
        run_v3_0()
    else:
        print(f"Version {args.version} not yet in harness")
        sys.exit(1)
