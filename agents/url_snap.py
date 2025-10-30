import re
import json
import asyncio
import sys
import yaml
from urllib.parse import urlparse
from datetime import datetime
from playwright.async_api import async_playwright


async def smart_snap_sites(SNAP_URLS):
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

            # Scroll to ensure all cards render
            for _ in range(5):
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(1000)

            cards = await page.query_selector_all("div.newsItemDetails")
            print(f"📑 Found {len(cards)} visible news cards")

            for idx in range(len(cards)):
                try:
                    # re-select each iteration (DOM changes)
                    await page.wait_for_selector("a.readMore", timeout=20000)
                    buttons = await page.query_selector_all("a.readMore")
                    if idx >= len(buttons):
                        break

                    print(f"🖱️ Expanding news item {idx + 1}/{len(buttons)}")
                    await buttons[idx].click()
                    await page.wait_for_timeout(2000)

                    # Wait until expanded article text is visible
                    await page.wait_for_selector("div.newsItemDetails h1", timeout=15000)

                    # Extract title, date, and paragraph directly from the expanded card
                    title = await page.locator("div.newsItemDetails h1").nth(idx).text_content()
                    date = await page.locator("div.newsItemDetails span.newsItemDate").nth(idx).text_content()
                    paragraph = await page.locator("div.newsItemDetails p").nth(idx).text_content()

                    item = {
                        "source": site["name"],
                        "title": title.strip(),
                        "date": date.strip(),
                        "content": paragraph.strip(),
                        "link": site.get("url", "https://www.gosi.gov.sa/ar/MediaCenter/News"),  # dynamic fallback
                        "snap_time": datetime.now().isoformat(),
                        "status": "OK"
                    }

                    print(f"📰 Parsed: {title[:60]}...")
                    all_items.append(item)

                    # Close overlay or restore listing
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(1000)

                except Exception as e:
                    print(f"⚠️ Failed to extract item {idx + 1}: {e}")
                    continue

        await browser.close()
    return all_items


# 🔹 MAIN ENTRY POINT
if __name__ == "__main__":
    """
    Run locally or from GitHub Actions.

    Examples:
      python agents/url_snap.py
      python agents/url_snap.py snap_sources.yml
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
