import re
import json
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright


async def _async_snap(SNAP_URLS, max_items=None):
    """Internal async routine that captures visible news summaries."""
    all_items = []

    print("\n📸 [SNAP] Launching headless browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="ar-SA")
        page = await context.new_page()

        for site in SNAP_URLS:
            print(f"\n🌐 [SNAP] Capturing: {site['name']} → {site['url']}")
            try:
                await page.goto(site["url"], timeout=40000)
                await page.wait_for_selector("a.readMore", timeout=30000)
            except Exception as e:
                print(f"⚠️ [SNAP] Failed to load {site['url']} → {e}")
                continue

            # Gentle scroll to trigger Angular lazy loading
            for _ in range(4):
                await page.mouse.wheel(0, 1200)
                await page.wait_for_timeout(800)

            try:
                titles = await page.eval_on_selector_all(
                    "div.newsItemDetails h1",
                    "els => els.map(e => (e.textContent||'').trim())"
                )
                dates = await page.eval_on_selector_all(
                    "div.newsItemDetails span.newsItemDate",
                    "els => els.map(e => (e.textContent||'').trim())"
                )
                paras = await page.eval_on_selector_all(
                    "div.newsItemDetails p",
                    "els => els.map(e => (e.textContent||'').trim())"
                )
            except Exception as e:
                print(f"⚠️ [SNAP] Could not extract listing cards → {e}")
                continue

            count = min(len(titles), len(dates), len(paras))
            if max_items is not None:
                count = min(count, max_items)

            print(f"📑 [SNAP] Found {count} visible news cards")

            for i in range(count):
                title = titles[i] if i < len(titles) else ""
                date_text = dates[i] if i < len(dates) else ""
                para = paras[i] if i < len(paras) else ""

                # Normalize date
                m = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
                date_norm = m.group(0) if m else datetime.now().strftime("%Y-%m-%d")

                item = {
                    "source": site["name"],
                    "title": title,
                    "date": date_norm,
                    "content": para,
                    "link": site.get("url"),  # config-driven fallback link
                    "snap_time": datetime.now(timezone.utc).isoformat(),  # internal UTC marker
                    "status": "OK",
                }
                print(f"📰 [SNAP] Parsed: {title[:60]}...")
                all_items.append(item)

        await browser.close()
        print("✅ [SNAP] Browser closed cleanly.")
    return all_items


def run_snap_and_return_items(SNAP_URLS, output_subdir: Optional[str] = None):
    """
    Public entry point used by agents_controller.py
    Runs Playwright internally and saves snapshot in /snapshots/ (Dubai time UTC+4).
    If output_subdir is provided, snapshots are saved under /snapshots/{output_subdir}/.
    Returns the collected list of items.
    """
    print("\n📸 Running URL Snap Agent...")

    try:
        items = asyncio.run(_async_snap(SNAP_URLS))
    except Exception as e:
        print(f"❌ [SNAP] Fatal error while running Playwright: {e}")
        items = []

    # Dubai time (UTC +4)
    dubai_time = datetime.now(timezone.utc) + timedelta(hours=4)

    base = Path("snapshots")
    if output_subdir:
        base = base / output_subdir
    base.mkdir(parents=True, exist_ok=True)
    out_file = base / f"snap_output_{dubai_time.strftime('%Y-%m-%d')}.json"

    try:
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"💾 [SNAP] Saved {len(items)} items to {out_file}")
        print(f"🕓 [SNAP] Dubai timestamp: {dubai_time.isoformat()}")
    except Exception as e:
        print(f"❌ [SNAP] Failed to save JSON file: {e}")

    print("✅ [SNAP] Agent finished.\n")
    return items
