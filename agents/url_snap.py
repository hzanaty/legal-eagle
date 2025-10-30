import re
import json
import asyncio
import sys
import yaml
from datetime import datetime
from playwright.async_api import async_playwright


async def smart_snap_sites(SNAP_URLS, max_items=None):
    all_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="ar-SA")
        page = await context.new_page()

        for site in SNAP_URLS:
            print(f"🌐 Capturing: {site['name']} → {site['url']}")
            try:
                # Load page and wait ONLY once for any read-more buttons to exist
                await page.goto(site["url"], timeout=40000)
                await page.wait_for_selector("a.readMore", timeout=30000)
            except Exception as e:
                print(f"⚠️ Failed to load {site['url']} → {e}")
                continue

            # Gentle auto-scroll to let Angular render all card texts (no extra waits later)
            for _ in range(4):
                await page.mouse.wheel(0, 1200)
                await page.wait_for_timeout(800)

            # Extract card data directly from listing (no clicking, no further waits)
            # We read arrays for titles, dates, and paragraphs from the same index.
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

                # Normalize date to YYYY-MM-DD if present in text
                m = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
                date_norm = m.group(0) if m else datetime.now().strftime("%Y-%m-%d")

                item = {
                    "source": site["name"],
                    "title": title,
                    "date": date_norm,
                    "content": para,
                    # Option 2 fallback: use the configured main URL as link (not hardcoded; config-driven)
                    "link": site.get("url", "https://www.gosi.gov.sa/ar/MediaCenter/News"),
                    "snap_time": datetime.now().isoformat(),
                    "status": "OK"
                }
                print(f"📰 Parsed: {title[:60]}...")
                all_items.append(item)

        await browser.close()
    return all_items


# 🔹 MAIN ENTRY POINT
if __name__ == "__main__":
    """
    Run locally or from GitHub Actions.

      python agents/url_snap.py
      python agents/url_snap.py snap_sources.yml

    Behavior:
    - Loads the listing page once.
    - Uses a short initial wait for 'a.readMore' just to confirm cards rendered.
    - Scrolls a bit.
    - Extracts titles/dates/summaries directly from visible cards.
    - No further waits, no clicking, no per-article URLs.
    """
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "snap_sources.yml"
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            SNAP_URLS = yaml.safe_load(f)["sources"]
    except Exception:
        SNAP_URLS = [
            {"name": "GOSI News", "url": "https://www.gosi.gov.sa/ar/MediaCenter/News"}
        ]

    async def main():
        data = await smart_snap_sites(SNAP_URLS)
        out_file = f"snap_output_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Saved {len(data)} items to {out_file}")

    asyncio.run(main())
