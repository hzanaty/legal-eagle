"""
Authority Attributor — publisher + authority attribution.

FINAL RULE (v3.26):
  - publisher  = SOURCE IDENTITY, always derived from the source: configured
                 publisher_name if set, else the site domain (leading "www." stripped)
                 for URL/RSS, or "@handle" for tweets. NEVER the authority.
  - authority  = the government body PRIMARILY RESPONSIBLE for the article's overall
                 subject. It is resolved in two ways:
                   * CONFIGURED — a feed/source with a configured authority_id (at ingest, here).
                   * INFERRED   — the AI subject-owner reasoning happens in L2
                                  (`primary_authority`); `resolve_primary_authority()` maps
                                  that name to a registered authority post-L2. No match → unknown.
  - Law Match NEVER determines authority.

`attribute_items` (ingest) does publisher + any CONFIGURED authority only — no AI.
"""
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

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
        cfg[url] = {"publisher": f.get("publisher_name"), "authority_id": f.get("authority_id")}
    return cfg


def build_url_config(url_sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map URL-source host (netloc) -> {publisher, authority_id} from loaded url_source rows."""
    cfg: Dict[str, Dict[str, Any]] = {}
    for s in url_sources or []:
        url = s.get("url") if isinstance(s, dict) else None
        if not url:
            continue
        try:
            host = urlparse(url).netloc
        except Exception:
            host = None
        if host:
            cfg[host] = {"publisher": s.get("publisher_name"), "authority_id": s.get("authority_id")}
    return cfg


def _ensure_publisher(it: Dict[str, Any]) -> None:
    """Guarantee a source-identity publisher: existing → @handle (tweets) → domain (www. stripped) → 'Source'.

    Never the authority — publisher is where we consumed the item from.
    """
    if it.get("publisher"):
        return
    handle = it.get("handle") or it.get("account")
    if (it.get("source_type") or "").lower().startswith("tweet") and handle:
        it["publisher"] = "@" + str(handle).lstrip("@")
        return
    u = it.get("link") or it.get("url") or ""
    try:
        host = urlparse(u).netloc
    except Exception:
        host = ""
    if host.lower().startswith("www."):
        host = host[4:]
    it["publisher"] = host or it.get("source") or "Source"


def attribute_items(
    items: List[Dict[str, Any]],
    feed_config: Dict[str, Dict[str, Any]] | None = None,
    db_conn=None,
    profile_id: int | None = None,
    url_config: Dict[str, Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Ingest-time attribution: stamp publisher (+ CONFIGURED authority only). No AI here.

    The AI responsible-authority is inferred later in L2 (`primary_authority`) and mapped by
    `resolve_primary_authority()`. `db_conn`/`profile_id` are kept for signature compatibility.
    """
    feed_config = feed_config or {}
    url_config = url_config or {}

    def _host_of(it: Dict[str, Any]):
        u = it.get("link") or it.get("url") or ""
        try:
            return urlparse(u).netloc or it.get("source") or None
        except Exception:
            return it.get("source") or None

    for it in items:
        cfg = feed_config.get(it.get("feed_url")) if it.get("feed_url") else None
        if cfg is None:
            host = _host_of(it)
            if host and host in url_config:
                cfg = url_config[host]
        if cfg is not None:
            if cfg.get("publisher"):
                it["publisher"] = cfg.get("publisher")   # configured source identity
            if cfg.get("authority_id"):
                it["authority_id"] = cfg.get("authority_id")
                it["authority_status"] = CONFIGURED
        it.setdefault("authority_status", UNKNOWN)
        _ensure_publisher(it)   # publisher = source identity, never the authority
    return items


def _norm_name(s) -> str:
    return (s or "").strip().lower()


def resolve_primary_authority(items: List[Dict[str, Any]], conn, profile_id: int) -> dict:
    """Post-L2: map each item's `primary_authority` (AI subject-owner name) → a registered authority_id.

    Name/alias match against the profile's authorities (exact, then loose contains). No match →
    left as-is (unknown). Never creates authorities; never overrides a CONFIGURED authority.
    Persists authority_id/authority_status.
    """
    from configurations.db import list_authorities, update_news_fields
    auths = list_authorities(conn, profile_id)
    by_name: Dict[str, int] = {}
    for a in auths:
        by_name[_norm_name(a["name"])] = a["id"]
        for al in (a.get("aliases") or "").split(","):
            aln = _norm_name(al)
            if aln:
                by_name.setdefault(aln, a["id"])
    resolved = 0
    for it in items:
        if it.get("authority_status") == CONFIGURED:
            continue
        name = _norm_name(it.get("primary_authority"))
        if not name:
            continue
        aid = by_name.get(name)
        if aid is None:
            for nm, i in by_name.items():
                if nm and (nm in name or name in nm):
                    aid = i
                    break
        if aid is not None:
            it["authority_id"] = aid
            it["authority_status"] = INFERRED
            update_news_fields(conn, it, {"authority_id": aid, "authority_status": INFERRED}, profile_id)
            resolved += 1
    conn.commit()
    return {"resolved": resolved}
