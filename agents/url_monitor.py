from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

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

                # Extract only the article section
                content_div = detail_soup.find("div", class_="m-3 mt-4")
                if content_div:
                    detail_text = content_div.get_text(separator="\n", strip=True)
                else:
                    detail_text = f"{title}\n{full_link}"

                # Initialize
                date_str = ""
                skip_due_to_old_date = False

                # Extract Gregorian date from "الموافق 2025-08-19" style line
                for line in detail_text.splitlines():
                    if "الموافق" in line and "-" in line:
                        try:
                            gregorian_part = line.split("الموافق")[1].strip()
                            # Only pick the date part (ignore trailing words)
                            gregorian_date = gregorian_part.split()[0].strip()
                            parsed_date = datetime.strptime(gregorian_date, "%Y-%m-%d")
                            date_str = parsed_date.strftime("%Y-%m-%d")

                            if datetime.today() - parsed_date > timedelta(days=2):
                                print(f"⏭️ Skipping old news: {title} ({date_str})")
                                skip_due_to_old_date = True
                            break
                        except Exception:
                            pass

                if skip_due_to_old_date:
                    continue

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
