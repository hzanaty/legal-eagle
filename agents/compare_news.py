import json
from pathlib import Path
from datetime import datetime, timedelta
from openai import OpenAI
import numpy as np

# Initialize OpenAI client
client = OpenAI()

def cosine_similarity(vec_a, vec_b):
    """Compute cosine similarity between two vectors."""
    return np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))

def run_compare_news_agent(current_items):
    """
    Compares today's collected items with the latest snapshot.
    Returns only new or significantly changed items.
    """

    print("🧠 Running Compare News Agent...")

    outputs_dir = Path("outputs")
    outputs_dir.mkdir(exist_ok=True)

    today_str = (datetime.utcnow() + timedelta(hours=4)).strftime("%Y-%m-%d")
    latest_path = outputs_dir / "latest_all_news.json"
    dated_path = outputs_dir / f"all_news_{today_str}.json"

    # Load previous snapshot if it exists
    previous_items = []
    if latest_path.exists():
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                previous_items = json.load(f)
            print(f"📂 Loaded {len(previous_items)} items from latest_all_news.json")
        except Exception as e:
            print(f"⚠️ Failed to load previous snapshot: {e}")
    else:
        print("⚠️ No previous snapshot found — treating all items as new.")

    # If no previous snapshot, return all as new
    if not previous_items:
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(current_items, f, ensure_ascii=False, indent=2)
        with open(dated_path, "w", encoding="utf-8") as f:
            json.dump(current_items, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved initial baseline → {latest_path}")
        return {"new_items": current_items}

    # Generate embeddings for current and previous items
    def get_text_signature(item):
        return f"{item.get('title', '')} {item.get('content', '')}"

    print("🔍 Generating embeddings for semantic comparison...")
    prev_texts = [get_text_signature(i) for i in previous_items]
    curr_texts = [get_text_signature(i) for i in current_items]

    prev_embeddings = client.embeddings.create(input=prev_texts, model="text-embedding-3-small").data
    curr_embeddings = client.embeddings.create(input=curr_texts, model="text-embedding-3-small").data

    new_items = []
    threshold = 0.90  # similarity threshold

    for i, curr in enumerate(curr_embeddings):
        curr_vec = np.array(curr.embedding)
        is_new = True
        for prev in prev_embeddings:
            prev_vec = np.array(prev.embedding)
            if cosine_similarity(curr_vec, prev_vec) > threshold:
                is_new = False
                break
        if is_new:
            new_items.append(current_items[i])

    print(f"✅ {len(new_items)} new items found (threshold {threshold}).")

    # Save both daily and latest versions
    with open(dated_path, "w", encoding="utf-8") as f:
        json.dump(current_items, f, ensure_ascii=False, indent=2)

    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(current_items, f, ensure_ascii=False, indent=2)

    print(f"💾 Updated latest snapshot → {latest_path}")

    return {"new_items": new_items}
