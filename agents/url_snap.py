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
            domain = f"{urlparse(site['url']).scheme}://{urlparse(site['url']).netloc}"

            try:
                await page.goto(site["url"], timeout=40000)
                await page.wait_for_selector("a.readMore", timeout=30000)
            except Exception as e:
                print(f"⚠️ Failed to load {site['url']} → {e}")
                continue

            # Scroll to ensure all cards render
            for _ in range(5):
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(1500)

            # Get number of news items
            read_more_buttons = await page.query_selector_all("a.readMore")
            print(f"📑 Found {len(read_more_buttons)} visible news cards")

            for idx in range(len(read_more_buttons)):
                try:
                    # Re-acquire buttons after each navigation
                    await page.wait_for_selector("a.readMore", timeout=20000)
                    buttons = await page.query_selector_all("a.readMore")

                    if idx >= len(buttons):
                        print(f"⚠️ Index {idx} out of range, breaking loop.")
                        break

                    print(f"🖱️ Clicking news item {idx + 1}/{len(buttons)}")
                    await buttons[idx].click()
                    await page.wait_for_timeout(2000)

                    # Wait until article title appears
                    await page.wait_for_selector("h1", timeout=20000)
                    html = await page.content()

                    # Extract data
                    title = await page.locator("h1").first.text_content()
                    title = title.strip() if title else "No title"

                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', html)
                    date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")

                    arabic_blocks = re.findall(r'>([^<>]{50,}[\u0600-\u06FF][^<>]{20,})<', html)
                    content = max(arabic_blocks, key=len) if arabic_blocks else "No Arabic content found."

                    link = page.url  # now we have the actual URL

                    item = {
                        "source": site["name"],
                        "title": title,
                        "date": date,
                        "content": content,
                        "link": link,
                        "snap_time": datetime.now().isoformat(),
                        "status": "OK"
                    }
                    print(f"📰 Parsed: {title[:60]}...")
                    all_items.append(item)

                    # Go back to main listing
                    await page.go_back()
                    await page.wait_for_selector("a.readMore", timeout=30000)
                    await page.wait_for_timeout(1500)

                except Exception as e:
                    print(f"⚠️ Failed to parse news item {idx + 1}: {e}")
                    await page.go_back()
                    await page.wait_for_selector("a.readMore", timeout=30000)
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
