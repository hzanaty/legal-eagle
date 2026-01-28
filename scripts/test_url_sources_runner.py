#!/usr/bin/env python3
"""
Isolated test harness for agents.url_sources_runner.run_unified_sources

Usage:
  python scripts/test_url_sources_runner.py            # runs built-in preset (your two URLs, 4 cases)
  python scripts/test_url_sources_runner.py --input path/to/sources.json  # run with custom JSON array

JSON format for --input:
[
  {"url": "https://example.com/listing", "mode": "auto", "sample_link": "optional"},
  {"url": "https://example.com/news", "mode": "force_dynamic"}
]
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path, then import the runner
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
try:
    from agents.url_sources_runner import run_unified_sources
except Exception as e:
    print(f"[HARNESS IMPORT ERROR] Could not import run_unified_sources: {e}", file=sys.stderr)
    sys.exit(1)

# Built-in preset using your two URLs, covering explicit and auto decisions
DEFAULT_SOURCES = [
    # Explicit static
    {"url": "https://uqn.gov.sa/category?cat=10", "mode": "force_static"},
    # Explicit dynamic (with example + read-more)
    {
        "url": "https://www.gosi.gov.sa/ar/MediaCenter/News",
        "mode": "force_dynamic",
        "sample_link": "https://www.gosi.gov.sa/ar/MediaCenter/News/NewsDetails/1/18122025",
        "read_more_label": "اقرأ المزيد"
    },
    # Auto: expect static success
    {"url": "https://uqn.gov.sa/category?cat=10", "mode": "auto"},
    # Auto: expect dynamic path (with example + read-more)
    {
        "url": "https://www.gosi.gov.sa/ar/MediaCenter/News",
        "mode": "auto",
        "sample_link": "https://www.gosi.gov.sa/ar/MediaCenter/News/NewsDetails/1/18122025",
        "read_more_label": "اقرأ المزيد"
    },
]


def load_sources_from_file(path: str):
    p = Path(path)
    if not p.exists():
        print(f"[HARNESS INPUT ERROR] File not found: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Input JSON must be an array of source objects")
        return data
    except Exception as e:
        print(f"[HARNESS INPUT ERROR] Failed to read/parse JSON from {path}: {e}", file=sys.stderr)
        sys.exit(2)


def run_once(sources):
    t0 = time.time()
    try:
        results = run_unified_sources(sources)
    except Exception as e:
        print(f"[HARNESS RUNTIME ERROR] run_unified_sources raised: {e}", file=sys.stderr)
        raise
    elapsed = time.time() - t0
    return results, elapsed


def print_summary(results, elapsed):
    items = results.get("items", []) or []
    errors = results.get("errors", []) or []
    print(f"[SUMMARY] elapsed={elapsed:.1f}s  items={len(items)}  errors={len(errors)}")
    if errors:
        print("[TOP ERRORS]")
        for e in errors[:3]:
            url = e.get("url")
            err = e.get("error")
            print(f" - {url}: {err}")


def save_results(results, elapsed, sources):
    outdir = Path("scripts/test_runs")
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    outfile = outdir / f"url_sources_run_{ts}.json"
    payload = {
        "sources": sources,
        "elapsed_sec": elapsed,
        "items": results.get("items", []),
        "errors": results.get("errors", []),
    }
    try:
        with outfile.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[SAVED] {outfile}")
    except Exception as e:
        print(f"[HARNESS SAVE ERROR] Failed writing results: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Isolated test harness for URL Sources Runner")
    ap.add_argument("--input", help="Path to JSON file containing array of sources")
    args = ap.parse_args()

    if args.input:
        sources = load_sources_from_file(args.input)
    else:
        sources = DEFAULT_SOURCES

    print("[HARNESS] Starting run with", len(sources), "sources")
    try:
        results, elapsed = run_once(sources)
    except Exception:
        sys.exit(3)

    print_summary(results, elapsed)
    save_results(results, elapsed, sources)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[HARNESS] Interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"[HARNESS FATAL] {e}", file=sys.stderr)
        sys.exit(1)
