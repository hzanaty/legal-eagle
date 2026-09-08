"""
Embeddings utility (v3.13).

Reusable embedding generation + cosine similarity, factored out of compare_news.py
so both the dedup stage and the announcement_agent clustering share one implementation.

- get_embeddings(texts): returns a list of float vectors (np.ndarray), cached.
- cosine(a, b): cosine similarity between two vectors.
"""

import os
from typing import List

import numpy as np

from agents.ai_cache import cached_embeddings

# Same limits as the dedup embedder — keep requests under the token ceiling.
MAX_CHARS_PER_ITEM = 1000
BATCH_SIZE = 10


def _get_ai_client():
    from configurations.config_loader import creds
    from agents.sap_ai_client import SAPAICoreClient
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
    )


def _truncate(s: str, max_chars: int = MAX_CHARS_PER_ITEM) -> str:
    return (s or "")[:max_chars]


def _embed_raw(texts: List[str], client, model: str = "text-embedding-3-small"):
    """Batch embeddings, returning a flat list of objects each exposing .embedding."""
    out = []
    timeout_s = float(os.environ.get("LEGAL_EAGLE_OPENAI_TIMEOUT", "60"))
    for i in range(0, len(texts), BATCH_SIZE):
        chunk = [_truncate(t) for t in texts[i:i + BATCH_SIZE]]
        resp = client.embeddings.create(input=chunk, model=model, timeout=timeout_s)
        out.extend(resp.data)
    return out


def get_embeddings(texts: List[str]) -> List[np.ndarray]:
    """Return one np.ndarray vector per input text (cached via ai_cache).

    Raises on failure — callers decide whether to degrade. Empty input → [].
    """
    if not texts:
        return []
    client = _get_ai_client()
    data = cached_embeddings(texts, lambda t: _embed_raw(t, client))
    return [np.array(d.embedding) for d in data]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors; 0.0 when either is zero-length."""
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
