import os
from datetime import datetime
from requests_html import HTMLSession
from configurations.agents_config import SNAPSHOT_SITES

# Folder where snapshots will be stored
SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _get_domain_from_url(url: str) -> str:
    """Extract a clean domain name for filenames."""
    return url.split("//")[-1].split("/")[0].replace(".", "_")


def save_snapshot(url: str):
    """
    Fetch page HTML (render JavaScript if needed) and save it.
    Keeps only the last 2 snapshots for that domain.
    """
    domain = _get_domain_from_url(url)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{domain}_{today}.html"
    path = os.path.join(SNAPSHOT_DIR, filename)

    session = HTMLSession()
    try:
        print(f"🌐 Fetching and rendering {url} ...")
        r = session.get(url, timeout=30)
        # ✅ Executes JavaScript to load dynamic content
        r.html.render(timeout=60, sleep=3)
        html = r.html.html
        if not html:
            raise ValueError("Empty rendered content.")
    except Exception as e:
        print(f"⚠️ Failed to render {url}: {e}")
        return None
    finally:
        session.close()

    # Save snapshot with UTF-8 encoding (for Arabic and multilingual pages)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # 🔄 Keep only last 2 snapshots per domain
    files = sorted(
        [f for f in os.listdir(SNAPSHOT_DIR) if f.startswith(domain)],
        reverse=True
    )
    for old_file in files[2:]:
        try:
            os.remove(os.path.join(SNAPSHOT_DIR, old_file))
        except Exception as e:
            print(f"⚠️ Could not delete old snapshot {old_file}: {e}")

    print(f"✅ Rendered snapshot saved → {path}")
    return path


def run_snapshot_monitor():
    """
    Run snapshot capture for all configured sites.
    Returns list of saved snapshot file paths.
    """
    saved_files = []
    for site in SNAPSHOT_SITES:
        url = site["url"]
        print(f"\n📸 Capturing snapshot for: {site['name']}")
        result = save_snapshot(url)
        if result:
            saved_files.append(result)
    return saved_files


if __name__ == "__main__":
    # Manual test: run all configured sites
    results = run_snapshot_monitor()
    if results:
        print("\n✅ Snapshot capture complete. Saved files:")
        for r in results:
            print(f"   - {r}")
    else:
        print("\n⚠️ No snapshots were saved.")
