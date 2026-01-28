#!/usr/bin/env python3
import os
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path so 'agents' package is importable when running from scripts/
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Use the actual runner code path (simulates Playwright + dynamic logic)
from agents.url_sources_runner import run_unified_sources

def main():
    # Inputs (fixed per your request; can be adjusted if needed)
    url = "https://www.gosi.gov.sa/ar/MediaCenter/News"
    sample_link = "https://www.gosi.gov.sa/ar/MediaCenter/News/NewsDetails/1/18122025"
    mode = "force_dynamic"

    # Build source list for the unified runner
    src = [{
        "url": url,
        "mode": mode,
        "sample_link": sample_link
    }]

    # Run the actual pipeline (this invokes Playwright and our updated mapping logic)
    res = run_unified_sources(src, profile_slug="SA_HCM")
    items = res.get("items", [])[:10]
    errors = res.get("errors", [])

    # Prepare output shape: link, title, date, details (Arabic)
    out = []
    for it in items:
        out.append({
            "link": it.get("link"),
            "title": it.get("title"),
            "date": it.get("date"),
            "details": it.get("content"),
        })

    # Write to outputs/test_runs/ so you can open in VS Code without waiting on terminal stream
    out_dir = Path("scripts/test_runs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gosi_dynamic_preview.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": out, "errors": errors}, f, ensure_ascii=False, indent=2)

    # Print a short summary+path to the file
    print(f"Wrote {len(out)} items to {out_path}")
    if errors:
        print(f"Errors: {len(errors)} (see JSON for details)")

if __name__ == "__main__":
    main()
