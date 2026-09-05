"""
Lightweight record-once/replay cache for AI calls (v3.1).

Production code paths call the real SAP AI Core client. When the environment
variable ``LEGAL_EAGLE_AI_CACHE`` points at a directory (set by the test
harness), embedding/chat responses are recorded on first call and replayed on
every subsequent call — making the pipeline deterministic and offline after a
single recording run. When the variable is unset, these helpers are transparent
passthroughs with zero behavioural change.

Cache entries are content-addressed by ``sha256`` of the input text, mirroring
``tests/ai_cache_utils.py``.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Callable, List


def _cache_dir() -> Path | None:
    d = os.environ.get("LEGAL_EAGLE_AI_CACHE")
    if not d:
        return None
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Vec:
    """Minimal stand-in exposing ``.embedding`` like the AI Core response items."""

    def __init__(self, embedding: List[float]):
        self.embedding = embedding


def cached_embeddings(texts: List[str], embed_fn: Callable[[List[str]], list]) -> list:
    """Return embedding items (each exposing ``.embedding``) for ``texts``.

    Cache miss → call ``embed_fn`` for the missing texts, store each vector.
    Cache hit  → replay stored vectors, never touching the network.
    Without ``LEGAL_EAGLE_AI_CACHE`` set, delegates fully to ``embed_fn``.
    """
    cdir = _cache_dir()
    if cdir is None:
        return embed_fn(texts)

    results: list = [None] * len(texts)
    missing_idx: List[int] = []
    missing_texts: List[str] = []
    for i, t in enumerate(texts):
        fp = cdir / f"emb_{_key(t)}.json"
        if fp.exists():
            try:
                results[i] = _Vec(json.loads(fp.read_text())["embedding"])
                continue
            except Exception:
                pass
        missing_idx.append(i)
        missing_texts.append(t)

    if missing_texts:
        fresh = embed_fn(missing_texts)
        for slot, item in zip(missing_idx, fresh):
            vec = list(item.embedding)
            results[slot] = _Vec(vec)
            fp = cdir / f"emb_{_key(texts[slot])}.json"
            fp.write_text(json.dumps({"embedding": vec}))

    return results


def cached_chat(prompt: str, call_fn: Callable[[], str]) -> str:
    """Return a chat completion string for ``prompt``, recording/replaying via the
    cache when ``LEGAL_EAGLE_AI_CACHE`` is set; otherwise call ``call_fn`` directly."""
    cdir = _cache_dir()
    if cdir is None:
        return call_fn()
    fp = cdir / f"chat_{_key(prompt)}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text())["response"]
        except Exception:
            pass
    resp = call_fn()
    try:
        fp.write_text(json.dumps({"response": resp}))
    except Exception:
        pass
    return resp

