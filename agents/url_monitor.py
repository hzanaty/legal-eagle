from urllib.parse import urljoin
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def scrape_all_monitor_urls(MONITOR_URLS):
    all_items = []
    errors = []

    for source in MONITOR_URLS:
        name = source["name"]
        url = source["url"]
        domain = source["domain"]
        title_tag = source["title_tag"]
        content_tag = source["content_tag"]

        try:
            response = requests.get(url)
            if response.status_code != 200:
                errors.append({
                    "source": name,
                    "url": url,
                    "error": f"Failed to fetch listing page, status {response.status_code}"
                })
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup.select(title_tag):
                title = tag.get_text(strip=True)
                relative_link = tag.get("href", "")
                full_link = urljoin(domain, relative_link)

                # Extract date from nearby <time> tag
                date_str = ""
                time_tag = tag.find_next("time", class_="td-module-date")
                if time_tag:
                    full_date_text = time_tag.get_text(strip=True)
                    match = re.search(r"\d{4}-\d{2}-\d{2}", full_date_text)
                    if match:
                        gregorian_part = match.group(0)
                        year = int(gregorian_part.split("-")[0])
                        if year < 2020:
                            continue  # Skip Hijri-only entries
                        try:
                            parsed_date = datetime.strptime(gregorian_part, "%Y-%m-%d")
                            date_str = parsed_date.strftime("%Y-%m-%d")
                            if datetime.today() - parsed_date > timedelta(days=10):
                                continue  # Skip old entries
                        except Exception as e:
                            errors.append({
                                "source": name,
                                "url": full_link,
                                "error": f"Date parse failed for {gregorian_part}: {e}"
                            })

                # Fetch detail page
                detail_response = requests.get(full_link)
                if detail_response.status_code != 200:
                    errors.append({
                        "source": name,
                        "url": full_link,
                        "error": f"Failed to fetch detail page, status {detail_response.status_code}"
                    })
                    continue

                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                detail_text = f"{title}\n{full_link}"

                # Extract only from configured content class
                content_element = detail_soup.find("div", class_=content_tag)
                if content_element:
                    detail_text = content_element.get_text(separator="\n", strip=True)

                item = {
                    "source": name,
                    "title": title,
                    "link": full_link,
                    "date": date_str,
                    "content": detail_text
                }
                all_items.append(item)

        except Exception as e:
            errors.append({
                "source": name,
                "url": url,
                "error": str(e)
            })

    return {
        "items": all_items,
        "errors": errors
    }
