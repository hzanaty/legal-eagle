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

            # 🧭 Go to main news listing page
            try:
                await page.goto(site["url"], timeout=40000)
            except Exception as e:
                print(f"⚠️ Failed to load {site['url']} → {e}")
                continue

            # 🕓 Wait for Angular feed to render completely
            try:
                await page.wait_for_selector("a.readMore", timeout=20000)

                # Scroll gradually to trigger lazy loading of news cards
                for _ in range(4):
                    await page.mouse.wheel(0, 1000)
                    await page.wait_for_timeout(2000)

                # Give Angular router time to populate the DOM
                await page.wait_for_timeout(4000)

                # 🧠 Extract news detail paths manually (Angular has no href attributes)
                html = await page.content()
                anchors = re.findall(r'/NewsDetails/\d+/\d+', html)
                anchors = list(set(anchors))

                # Construct absolute URLs
                anchors = [f"https://www.gosi.gov.sa/ar/MediaCenter/News{a}" for a in anchors]
            except Exception as e:
                print(f"⚠️ Could not extract anchors → {e}")
                anchors = []

            if not anchors:
                print(f"⚠️ No news links found on {site['url']}")
                continue

            # 🧠 Auto-learn link pattern
            first_example = anchors[0]
            sample_path = urlparse(first_example).path
            link_pattern = re.sub(r'\d+', r'\\d+', sample_path)
            print(f"🔗 Auto-learned link pattern: {link_pattern}")

            found_links = [url for url in anchors if re.search(link_pattern, url)]
            found_links = list(set(found_links))
            print(f"📎 Found {len(found_links)} news links")

            # 🔍 Visit each detail page
            for link in found_links:
                try:
                    await page.goto(link, timeout=30000)
                except Exception as e:
                    print(f"⚠️ Failed to open detail {link} → {e}")
                    continue

                # 🏷️ Extract title
                title = await page.locator("h1, h2").first.text_content()
                title = title.strip() if title else "No title"

                # 📄 Extract the main Arabic text block
                html = await page.content()
                arabic_blocks = re.findall(r'>([^<>]{50,}[\u0600-\u06FF][^<>]{20,})<', html)
                content = max(arabic_blocks, key=len) if arabic_blocks else "No Arabic content found."

                # 🗓️ Detect date (YYYY-MM-DD)
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', html)
                date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")

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

    # 🧩 Load YAML config (if provided) or fallback to internal default
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
            json.dump(data, f, ensure_ascii=False,_
