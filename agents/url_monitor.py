from configurations.agents_config import MONITOR_PAGES

def scrape_news_from_url(url, selector):
    print(f"🌐 Scraping: {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        articles = soup.select(selector)
        scraped_items = []

        for article in articles:
            title = article.get_text(strip=True)
            relative_link = article.get("href", "")
            full_link = f"https://uqn.gov.sa{relative_link}" if relative_link.startswith("/") else relative_link

            # Try to get the associated publishing date
            parent_div = article.find_parent("div")
            time_tag = parent_div.find("time") if parent_div else None
            date_text = time_tag.get_text(strip=True) if time_tag else "Unknown"

            item = {
                "source": "Web",
                "title": title,
                "summary": title,
                "link": full_link,
                "date": date_text,
                "content": f"{title}\n{full_link}\n{date_text}"
            }
            scraped_items.append(item)

        print(f"✅ Found {len(scraped_items)} items on {url}")
        return scraped_items

    except Exception as e:
        print(f"❌ Failed to scrape {url}: {e}")
        return []

def monitor_web_sources():
    all_items = []
    for entry in MONITOR_PAGES:
        url = entry["url"]
        selector = entry["selector"]
        items = scrape_news_from_url(url, selector)
        all_items.extend(items)
    return all_items
