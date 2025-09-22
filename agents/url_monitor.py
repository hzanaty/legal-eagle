from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from configurations.agents_config import MONITOR_URLS

def scrape_all_monitor_urls(MONITOR_URLS):
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

                # Fetch detail page
                detail_response = requests.get(full_link)
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                detail_text = detail_soup.get_text(separator="\n", strip=True)

                # Try to extract Gregorian date in format yyyy-mm-dd
                date_str = ""
                for line in detail_text.splitlines():
                    if "الموافق" in line and "-" in line:
                        parts = line.split("الموافق")
                        if len(parts) > 1:
                            gregorian_part = parts[1].strip()
                            try:
                                # Try to parse date like 2025-07-25
                                parsed_date = datetime.strptime(gregorian_part, "%Y-%m-%d")
                                date_str = parsed_date.strftime("%Y-%m-%d")

                                # Skip if older than 2 weeks
                                if datetime.today() - parsed_date > timedelta(weeks=2):
                                    continue
                            except Exception:
                                pass  # fallback if parsing fails
                        break  # stop scanning lines after date found

                item = {
                    "source": name,
                    "title": title,
                    "link": full_link,
                    "date": date_str,
                    "content": detail_text
                }
                all_items.append(item)

        except Exception as e:
            print(f"❌ Failed to scrape {name}: {e}")

    return all_items
