import os
import requests
from datetime import datetime

# Folder where snapshots are saved
SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _get_domain_from_url(url: str) -> str:
    """Extracts a clean domain name for filenames."""
    return url.split("//")[-1].split("/")[0].replace(".", "_")


def save_snapshot(url: str):
    """
    Fetches page HTML and saves it under snapshots/<domain>_YYYY-MM-DD.html.
    Keeps only the 2 newest files for that domain.
    """
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
    except Exception as e:
        print(f"⚠️ Failed to fetch {url}: {e}")
        return None

    domain = _get_domain_from_url(url)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{domain}_{today}.html"
    path = os.path.join(SNAPSHOT_DIR, filename)

    # Save today's HTML
    with open(path, "w", encoding="utf-8") as f:
        f.write(response.text)

    # 🔄 Keep only last 2 versions
    files = sorted(
        [f for f in os.listdir(SNAPSHOT_DIR) if f.startswith(domain)],
        reverse=True
    )
    for old_file in files[2:]:  # delete older ones
        try:
            os.remove(os.path.join(SNAPSHOT_DIR, old_file))
        except Exception as e:
            print(f"⚠️ Could not delete {old_file}: {e}")

    print(f"✅ Snapshot saved for {url} → {path}")
    return path
