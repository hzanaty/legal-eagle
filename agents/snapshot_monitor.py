import os
from datetime import datetime
from playwright.sync_api import sync_playwright

SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

def _get_domain_from_url(url: str) -> str:
    return url.split("//")[-1].split("/")[0].replace(".", "_")

def save_snapshot(url: str):
    """Render page using Playwright Chromium and save HTML."""
    domain = _get_domain_from_url(url)
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(SNAPSHOT_DIR, f"{domain}_{today}.html")

    print(f"🌐 Rendering dynamic page via Playwright: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"⚠️ Rendering failed: {e}")
        return None

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # Keep only 2 latest snapshots
    files = sorted([f for f in os.listdir(SNAPSHOT_DIR) if f.startswith(domain)], reverse=True)
    for old in files[2:]:
        os.remove(os.path.join(SNAPSHOT_DIR, old))

    print(f"✅ Snapshot saved: {path}")
    return path
