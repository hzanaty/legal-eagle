# snap_url_agent.py  (Playwright version)
import re
import json
import asyncio
from urllib.parse import urljoin, urlparse
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

            # 🔹 Auto-infer link pattern
            sample_path = urlparse(site["sample_link"]).path
            link_pattern = re.sub(r'\d+', r'\\d+', sample_path)
            print(f"🔗 Inferred link pattern: {link_pattern}")

            try:
                await page.goto(site["url"], timeout=30000)
            except Exception as e:
                print(f"⚠️ Failed to load {site['url']} → {e}")
                continue

            # extract all <a href> links
            anchors = await page.eval_on_selector_all("a[href]", "els => els.map(a => a.href)")
            found_links = [url for url in anchors if re.search(link_pattern, url)]
            found_links = list(set(found_links))
            print(f"📎 Found {len(found_links)} news links")

            for link in found_links:
                try:
                    await page.goto(link, timeout=30000)
                except Exception as e:
                    print(f"⚠️ Failed to open detail {link} → {e}")
                    continue

                # 🏷️ Extract title (first h1/h2)
                title = await page.locator("h1, h2").first.text_content()
                if title:
                    title = title.strip()
                else:
                    title = "No title"

                # 📄 Extract visible text from largest Arabic block
                html = await page.content()
                arabic_blocks = re.findall(r'>([^<>]{50,}[\u0600-\u06FF][^<>]{20,})<', html)
                content = max(arabic_blocks, key=len) if arabic_blocks else "No Arabic content found."

                # 🗓️ Try to find a Gregorian date
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


if __name__ == "__main__":
    SNAP_URLS = [
        {
            "name": "GOSI News",
            "url": "https://www.gosi.gov.sa/ar/MediaCenter/News",
            "sample_link": "https://www.gosi.gov.sa/ar/MediaCenter/News/NewsDetails/1/0028102025"
        }
    ]

    async def main():
        data = await smart_snap_sites(SNAP_URLS)
        out_file = f"snap_output_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Saved {len(data)} items to {out_file}")

    asyncio.run(main())
