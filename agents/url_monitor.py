from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from configurations.agents_config import MONITOR_URLS

def scrape_all_monitor_urls():
    all_items = []

    for source in MONITOR_URLS:
        name = source["name"]
        url = source["url"]
        domain = source["domain"]
        selector = source["selector"]

        print(f"🌐 Scraping: {name} → {url}")
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup.select(selector):
                title = tag.get_text(strip=True)
                relative_link = tag.get("href", "")
                full_link = urljoin(domain, relative_link)

                item = {
                    "source": name,
                    "title": title,
                    "summary": title,
                    "link": full_link,
                    "date": "",  # Optional: add date parsing later
                    "content": title + "\n" + full_link
                }
                all_items.append(item)

        except Exception as e:
            print(f"❌ Failed to scrape {name}: {e}")

    return all_items

if __name__ == "__main__":
    items = scrape_all_monitor_urls()
    for item in items:
        print("📌", item["title"])
        print("🔗", item["link"])
        print("📎", item["content"])
        print("—" * 40)
