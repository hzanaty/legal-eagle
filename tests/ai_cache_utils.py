import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def cached_ai_call(prompt: str, call_fn) -> dict:
    cache_dir = Path(__file__).parent / "ai_cache"
    cache_dir.mkdir(exist_ok=True)
    key = hashlib.sha256(prompt.encode()).hexdigest()
    p = cache_dir / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())["response"]
    resp = call_fn()
    p.write_text(json.dumps({"prompt_hash": key, "response": resp,
                              "cached_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    return resp
