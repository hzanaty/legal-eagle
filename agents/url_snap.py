import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _get_domain_from_url(url: str) -> str:
    return url.split("//")[-1].split("/")[0].replace(".", "_")


def save_snapshot(url: str):
    """Render GOSI or similar page, extract visible news, and save JSON snapshot."""
    domain = _get_domain_from_url(url)
    now_ksa = datetime.now(ZoneInfo("Asia/Riyadh"))
    today = now_ksa.strftime("%Y-%m-%d")
    json_path = os.path.join(SNAPSHOT_DIR, f"{domain}_{today}.json")

    print(f"🌐 Rendering {url} using Playwright Chromium (KSA time: {now_ksa:%Y-%m-%d %H:%M})...")
    news_data = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=120000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            # 📰 Extract visible news data
            items = page.query_selector_all(".newsItemDetails")
            print(f"📰 Found {len(items)} news entries:")
            for i, item in enumerate(items, 1):
                title = item.query_selector(".newsItemTitle").inner_text() if item.query_selector(".newsItemTitle") else ""
                date = item.query_selector(".newsItemDate").inner_text() if item.query_selector(".newsItemDate") else ""
                snippet = item.query_selector(".newsItemText").inner_text() if item.query_selector(".newsItemText") else ""
                link_el = item.query_selector("a")
                link = link_el.get_attribute("href") if link_el else url

                news_data.append({
                    "title": title.strip(),
                    "date": date.strip(),
                    "snippet": snippet.strip(),
                    "link": link
                })
                print(f"   {i}. {title.strip()} ({date.strip()})")

            browser.close()

    except Exception as e:
        print(f"⚠️ Rendering failed for {url}: {e}")
        return None

    # ✅ Save structured JSON snapshot
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)

    # 🔁 Keep only last 2 snapshots per domain
    files = sorted(
        [f for f in os.listdir(SNAPSHOT_DIR) if f.startswith(domain)],
        reverse=True
    )
    for old in files[2:]:
        os.remove(os.path.join(SNAPSHOT_DIR, old))

    print(f"✅ JSON snapshot saved → {json_path}")
    return json_path

def run_snap_and_return_items(SNAP_URLS):
    """
    Runs the snapshot extraction and returns today's JSON news items in normalized form.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    results = []

    for site in SNAP_URLS:
        site_url = site["url"]
        site_name = site["name"]

        print(f"🌐 Rendering {site_name} ({site_url})...")
        site_items = save_snapshot(site_url)  # assumes your existing save_snapshot() returns list of dicts
        if site_items:
            results.extend(site_items)

    # Also load today's saved JSON snapshots, if any
    snapshot_files = [
        f for f in os.listdir("snapshots")
        if f.endswith(f"{today}.json")
    ]

    for file in snapshot_files:
        with open(os.path.join("snapshots", file), "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                normalized = {
                    "title": item.get("title", "Untitled"),
                    "content": item.get("snippet", ""),  # rename field
                    "link": item.get("link", ""),
                    "date": item.get("date", today),
                    "source": "Snap"
                }
                results.append(normalized)

    print(f"✅ Snap completed: {len(results)} items extracted.")
    return results


