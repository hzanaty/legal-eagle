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
        content_tag = source.get["content_tag"]

        print(f"🌐 Scraping: {name} → {url}")
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup.select(selector):
                title = tag.get_text(strip=True)
                relative_link = tag.get("href", "")
                full_link = urljoin(domain, relative_link)

                # 🗓️ Get date from adjacent <time> tag
                time_tag = tag.find_parent().find_next("time")
                date_str = ""
                skip_due_to_old_date = False

                if time_tag and "الموافق" in time_tag.text:
                    try:
                        parts = time_tag.text.split("الموافق")
                        gregorian_part = parts[1].strip()
                        parsed_date = datetime.strptime(gregorian_part, "%Y-%m-%d")
                        date_str = parsed_date.strftime("%Y-%m-%d")

                        # ⏳ Skip if older than 3 days
                        if datetime.today() - parsed_date > timedelta(days=3):
                            print(f"⏭️ Skipping old news: {title} ({date_str})")
                            continue
                    except Exception as e:
                        print(f"⚠️ Failed to parse date for '{title}': {e}")

                # 📄 Fetch full content from detail page
                try:
                    detail_response = requests.get(full_link)
                    detail_soup = BeautifulSoup(detail_response.text, "html.parser")

                    if content_tag:
                        content_element = detail_soup.find(content_tag.get("name"), class_=content_tag.get("class"))
                        detail_text = content_element.get_text(separator="\n", strip=True) if content_element else ""
                    else:
                        detail_text = ""

                    if not detail_text:
                        detail_text = f"{title}\n{full_link}"  # fallback
                except Exception as e:
                    print(f"⚠️ Failed to fetch detail page: {e}")
                    detail_text = f"{title}\n{full_link}"

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
