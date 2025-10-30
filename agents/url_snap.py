import re
import json
import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright


async def _async_snap(SNAP_URLS, max_items=None):
    """Internal async routine that captures visible news summaries."""
    all_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="ar-SA")
        page = await context.new_page()

        for site in SNAP_URLS:
            print(f"🌐 Capturing: {site['name']} → {site['url']}")
            try:
                await page.goto(site["url"], timeout=40000)
                await page.wait_for_selector("a.readMore", timeout=30000)
            except Exception as e:
                print(f"⚠️ Failed to load {site['url']} → {e}")
                continue

            # Scroll gently to ensure all cards render
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
                print(f"⚠️ Could not read listing cards → {e}")
                continue

            count = min(len(titles), len(dates), len(paras))
            if max_items is not None:
                count = min(count, max_items)

            print(f"📑 Found {count} cards with extractable text")

            for i in range(count):
                title = titles[i] if i < len(titles) else ""
                date_text = dates[i] if i < len(dates) else ""
                para = paras[i] if i < len(paras) else ""
                m = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
                date_norm = m.group(0) if m else datetime.now().strftime("%Y-%m-%d")

                item = {
                    "source": site["name"],
                    "title": title,
                    "date": date_norm,
                    "content": para,
                    # Config-driven fallback link
                    "link": site.get("url"),
                    "snap_time": datetime.now().isoformat(),
                    "status": "OK"
                }
                print(f"📰 Parsed: {title[:60]}...")
                all_items.append(item)

        await browser.close()
    return all_items


def run_snap_and_return_items(SNAP_URLS):
    """
    Public entry point used by agents_controller.py
    Runs the async Playwright scraper internally and saves snapshot in /snapshots/.
    Returns the collected list of items.
    """
    print("\n📸 Running URL Snap Agent...")

    # Execute async part
    items = asyncio.run(_async_snap(SNAP_URLS))

    # Always save to snapshots folder
    Path("snap
