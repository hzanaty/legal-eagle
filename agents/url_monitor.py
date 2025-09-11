import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

from configurations.agents_config import MONITOR_URLS

def extract_gregorian_date(text):
    match = re.search(r'(\d{4}-\d{2}-\d{2})$', text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            return None
    return None

def is_recent_news(text, days=3):
    pub_date = extract_gregorian_date(text)
    if pub_date:
        return pub_date >= datetime.today() - timedelta(days=days)
    return False

def fetch_news_from_url(url):
    print(f"🌐 Scraping {url}...")
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        # This logic may vary based on the UQN HTML structure
        news_cards = soup.find_all("div", class_="post-card")
        news_items = []

        for card in news_cards:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue

            news_url = link_tag["href"]
            full_url = f"https://uqn.gov.sa{news_url}" if news_url.startswith("/") else news_url

            details = link_tag.get_text(strip=True)
            if not is_recent_news(details):
                continue

            detail_page = requests.get(full_url)
            detail_soup = BeautifulSoup(detail_page.content, "html.parser")
            content_div = detail_soup.find("div", class_="post-content")
            content_text = content_div.get_text(strip=True) if content_div else ""

            news_items.append({
                "source": "UQN",
                "title": details.split("\n")[0][:80],
                "summary": details,
                "link": full_url,
                "date": extract_gregorian_date(details).strftime("%Y-%m-%d") if extract_gregorian_date(details) else "",
                "content": content_text
            })

        return news_items

    except Exception as e:
        print(f"❌ Error scraping {url}: {e}")
        return []

def url_monitor():
    print("🔍 Starting UQN URL Monitor Agent...")
    all_news = []
    for url in MONITOR_URLS:
        news = fetch_news_from_url(url)
        all_news.extend(news)
    print(f"✅ UQN Monitor collected {len(all_news)} item(s)")
    return all_news

if __name__ == "__main__":
    items = url_monitor()
    for item in items:
        print("📌", item["title"])
        print("🔗", item["link"])
        print("🕒", item["date"])
        print("✍️", item["summary"][:100], "...\n")
