from urllib.parse import urljoin
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def scrape_all_monitor_urls(MONITOR_URLS):
    all_items = []

    for source in MONITOR_URLS:
        name = source["name"]
        url = source["url"]
        domain = source["domain"]
        title_tag = source["title_tag"]
        content_tag = source["content_tag"]

        print(f"🌐 Scraping: {name} → {url}")
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup.select(title_tag):
                title = tag.get_text(strip=True)
                relative_link = tag.get("href", "")
                full_link = urljoin(domain, relative_link)

                # Extract date from <time> tag using regex
                date_str = ""
                time_tag = tag.find_next("time", class_="td-module-date")
                if time_tag:
                    full_date_text = time_tag.get_text(strip=True)
                    match = re.search(r"\d{4}-\d{2}-\d{2}", full_date_text)
                    if match:
                        try:
                            gregorian_part = match.group(0)
                            parsed_date = datetime.strptime(gregorian_part, "%Y-%m-%d")
                            date_str = parsed_date.strftime("%Y-%m-%d")
                            if datetime.today() - parsed_date > timedelta(days=7):
                                print(f"⏭️ Skipping old news: {title} ({date_str})")
                                continue
                        except Exception as e:
                            print(f"⚠️ Failed to parse date from: '{gregorian_part}' → {e}")

                # Fetch detail page
                detail_response = requests.get(full_link)
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")

                # Extract only from configured content class
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
