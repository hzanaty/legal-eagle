# snap_url_agent.py
import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime

def smart_snap_sites(SNAP_URLS):
    all_items = []

    for site in SNAP_URLS:
        print(f"🌐 Capturing: {site['name']} → {site['url']}")
        domain = f"{urlparse(site['url']).scheme}://{urlparse(site['url']).netloc}"

        # 🔹 Auto-infer link pattern from sample link
        sample_path = urlparse(site["sample_link"]).path
        link_pattern = re.sub(r'\d+', r'\\d+', sample_path)
        print(f"🔗 Inferred link pattern: {link_pattern}")

        try:
            res = requests.get(site["url"], timeout=15)
            res.raise_for_status()
        except Exception as e:
            print(f"⚠️ Failed to fetch {site['url']} → {e}")
            continue

        soup = BeautifulSoup(res.text, "html.parser")
        found_links = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(link_pattern, href):
                full_link = urljoin(domain, href)
                found_links.add(full_link)

        print(f"📎 Found {len(found_links)} news links")

        # 🔹 Fetch each detail page
        for link in found_links:
            try:
                detail = requests.get(link, timeout=15)
                detail.raise_for_status()
            except Exception as e:
                print(f"⚠️ Failed detail fetch {link} → {e}")
                continue

            s2 = BeautifulSoup(detail.text, "html.parser")

            # 🏷️ Title: prefer h1, then h2, then meta title
            title_tag = s2.find(["h1", "h2"])
            title = title_tag.get_text(strip=True) if title_tag else s2.title.get_text(strip=True) if s2.title else "No title"

            # 📄 Content: choose the largest Arabic text block
            arabic_blocks = []
            for div in s2.find_all(["div", "article", "section"]):
                text = div.get_text(" ", strip=True)
                if re.search(r'[\u0600-\u06FF]', text):
                    arabic_blocks.append(text)
            content = max(arabic_blocks, key=len) if arabic_blocks else "No Arabic content found."

            # 🗓️ Try to detect date inside page (Gregorian)
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', detail.text)
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
            all_items.append(item)

    return all_items


if __name__ == "__main__":
    # 🧩 Minimal config: only 3 keys per site
    SNAP_URLS = [
        {
            "name": "GOSI News",
            "url": "https://www.gosi.gov.sa/ar/MediaCenter/News",
            "sample_link": "https://www.gosi.gov.sa/ar/MediaCenter/News/NewsDetails/1/0028102025"
        }
    ]

    data = smart_snap_sites(SNAP_URLS)

    # 💾 Save JSON snapshot
    out_file = f"snap_output_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved {len(data)} items to {out_file}")
