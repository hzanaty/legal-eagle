"""
Authority Attributor — the ATTRIBUTE stage (v3.2).

Stamps each fetched news item with its source attribution:
  - publisher:        display name of the source (from feed config)
  - authority_id:     FK to the `authorities` table
  - authority_status: 'configured' (from feed config) |
                      'inferred'   (AI match, v3.2)   |
                      'unknown'    (no match)

v3.1 implemented the *configured* path only.  v3.2 adds the *inferred* path:
when a feed has no configured authority_id the attributor calls AI with
(title, content, authorities list) to pick the best match.  On success
authority_status='inferred'; on no match authority_status='unknown' as before.

AI calls are wrapped via ai_cache for offline harness determinism.
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from configurations.config_loader import creds
from agents.sap_ai_client import SAPAICoreClient
from agents.ai_cache import cached_chat

CONFIGURED = "configured"
INFERRED = "inferred"
UNKNOWN = "unknown"


def build_feed_config(rss_feeds: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map feed URL -> {publisher, authority_id} from loaded RSS feed rows."""
    cfg: Dict[str, Dict[str, Any]] = {}
    for f in rss_feeds or []:
        url = f.get("url") if isinstance(f, dict) else None
        if not url:
            continue
        cfg[url] = {
            "publisher": f.get("publisher_name"),
            "authority_id": f.get("authority_id"),
        }
    return cfg


def _get_ai_client() -> SAPAICoreClient:
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"],
    )


def _infer_authority(
    title: str, content: str, authorities: List[Dict[str, Any]]
) -> Tuple[Optional[int], Optional[str]]:
    """Call AI to match item to the best known authority.

    Returns (authority_id, authority_name) on a confident match, (None, None)
    when no authority fits or AI is unavailable.
    """
    if not authorities:
        return None, None

    auth_list = "\n".join(f"  - ID {a['id']}: {a['name']}" for a in authorities)
    prompt = (
        "You are an authority attribution assistant for regulatory news.\n"
        f"News item title: {title!r}\n"
        f"Content snippet: {(content or '')[:300]!r}\n\n"
        "Which regulatory authority from the list below is the most likely original "
        "source of this news? If none match well, respond with authority_id null.\n\n"
        f"Known authorities:\n{auth_list}\n\n"
        'Respond with JSON only: {"authority_id": <integer id or null>, "authority_name": "<name or null>"}'
    )

    def _call() -> str:
        return _get_ai_client().chat(prompt)

    try:
        raw = cached_chat(prompt, _call)
        match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            aid = parsed.get("authority_id")
            if aid and aid != "null":
                known = {a["id"]: a["name"] for a in authorities}
                aid_int = int(aid)
                if aid_int in known:
                    return aid_int, known[aid_int]
    except Exception:
        pass
    return None, None


def attribute_items(
    items: List[Dict[str, Any]],
    feed_config: Optional[Dict[str, Dict[str, Any]]] = None,
    db_conn=None,
    profile_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Stamp publisher / authority_id / authority_status onto each item in place.

    An item is matched to its feed via ``item['feed_url']`` (set by rss_parser).
    Configured path: authority_id is taken from feed config → status 'configured'.
    Inferred path (v3.2): no configured authority_id + db_conn + profile_id supplied
      → AI picks best match from profile authorities → status 'inferred' or 'unknown'.
    """
    feed_config = feed_config or {}

    # Load authorities once for the inferred path (only when DB is available).
    authorities: List[Dict[str, Any]] = []
    if db_conn is not None and profile_id is not None:
        try:
            from configurations.db import list_authorities
            authorities = list_authorities(db_conn, profile_id)
        except Exception:
            pass

    for it in items:
        cfg = feed_config.get(it.get("feed_url")) if it.get("feed_url") else None
        if cfg is not None:
            if cfg.get("publisher"):
                it["publisher"] = cfg.get("publisher")
            if cfg.get("authority_id"):
                it["authority_id"] = cfg.get("authority_id")
                it["authority_status"] = CONFIGURED
                continue

        # No configured authority — try AI inference if DB context is available.
        if authorities:
            aid, aname = _infer_authority(
                it.get("title", ""), it.get("content", ""), authorities
            )
            if aid is not None:
                it["authority_id"] = aid
                it["authority_status"] = INFERRED
                if not it.get("publisher"):
                    it["publisher"] = aname
                continue

        it.setdefault("authority_status", UNKNOWN)

    return items
