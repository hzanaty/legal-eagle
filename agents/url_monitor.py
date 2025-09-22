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
        title_tag = source["title_tag"]       # 👈 Cleaned
        content_tag = source["content_tag"]   # 👈 Cleaned

        print(f"🌐 Scraping: {name} → {url}")
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup.select(title_tag):
                title = tag.get_text(strip=True)
                relative_link = tag.get("href", "")
                full_link = urljoin(domain, relative_link)

                # Extract date from sibling <time> tag in the same container
                date_str = ""
                container = tag.find_parent("div")
                if container:
                    time_tag = container.find("time")
                    if time_tag and "الموافق" in time_tag.text:
                        for part in time_tag.text.split("الموافق"):
                            part = part.strip()
                            if "-" in part:
                                try:
                                    parsed_date = datetime.strptime(part, "%Y-%m-%d")
                                    date_str = parsed_date.strftime("%Y-%m-%d")
                                    # Skip if older than 3 days
                                    if datetime.today() - parsed_date > timedelta(days=3):
                                        print(f"⏭️ Skipping old news: {title} ({date_str})")
                                        break  # Skip this item
                                except:
                                    continue

                if not date_str:
                    continue  # No valid date parsed, skip

                # Fetch detail page
                detail_response = requests.get(full_link)
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")

                # Extract only from content_tag class (within <div>)
                detail_text = f"{title}\n{full_link}"
                content_element = detail_soup.find("div", class_=content_tag)
                if content_element:
                    detail_text = content_element.get_text(separator="\n", strip=True)

                # Append item
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
