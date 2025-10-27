import os
from datetime import datetime
from playwright.sync_api import sync_playwright

SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

def _get_domain_from_url(url: str) -> str:
    return url.split("//")[-1].split("/")[0].replace(".", "_")

def save_snapshot(url: str):
    """Render full dynamic page with Playwright and save snapshot."""
    domain = _get_domain_from_url(url)
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(SNAPSHOT_DIR, f"{domain}_{today}.html")

    print(f"🌐 Rendering {url} using Playwright Chromium...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=120000)
            # scroll to bottom to load lazy elements
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"⚠️ Rendering failed for {url}: {e}")
        return None

    # Save rendered HTML with UTF-8 (Arabic-safe)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # Keep last 2 snapshots per site
    files = sorted(
        [f for f in os.listdir(SNAPSHOT_DIR) if f.startswith(domain)],
        reverse=True
    )
    for old in files[2:]:
        os.remove(os.path.join(SNAPSHOT_DIR, old))

    print(f"✅ Snapshot saved → {path}")
    return path

if __name__ == "__main__":
    from configurations.agents_config import SNAPSHOT_SITES
    for site in SNAPSHOT_SITES:
        save_snapshot(site["url"])
