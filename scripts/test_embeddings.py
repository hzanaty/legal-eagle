#!/usr/bin/env python3
"""
Embeddings Connectivity Test (Standalone)

Purpose:
- Isolate and test connectivity to the embeddings provider away from the pipeline.
- Use the same OpenAI client pattern as agents/compare_news.py (httpx.Client with HTTP/2 disabled, configurable timeout/base_url).
- Exercise varying payload sizes and batching to detect if connection errors correlate with request mass.

Environment variables (preferred):
- LEGAL_EAGLE_OPENAI_API_KEY: OpenAI API key (required unless --api-key provided)
- LEGAL_EAGLE_OPENAI_BASE_URL: Optional base URL override (e.g., Azure OpenAI or proxy)
- LEGAL_EAGLE_OPENAI_TIMEOUT: Optional timeout seconds (default: 30)

CLI options:
- --model TEXT                       Embedding model (default: text-embedding-3-small)
- --items INT                        Number of items to embed (default: 10)
- --batch-size INT                   Batch size per request (default: 10, matches pipeline)
- --max-chars INT                    Truncation length per item (default: 1000)
- --timeout FLOAT                    Request timeout seconds (default: env or 30)
- --concurrency INT                  Number of concurrent worker threads (default: 1)
- --retries INT                      Number of retries per batch on failure (default: 0)
- --backoff FLOAT                    Initial backoff seconds (default: 1.0, exponential)
- --from-json PATH                   Optional JSON file with items to embed (list[dict])
- --json-keys STR STR                Keys to read from JSON items (default: title content)
- --api-key TEXT                     API key override (falls back to env)
- --base-url TEXT                    Base URL override (falls back to env)
- --dry-run                          Print plan but do not call embeddings API

Usage examples:
- python scripts/test_embeddings.py --items 10
- python scripts/test_embeddings.py --batch-size 10 --items 100 --timeout 60
- python scripts/test_embeddings.py --from-json outputs/SA_HCM/all_news.json --items 100
- python scripts/test_embeddings.py --model text-embedding-3-large --items 10

Exit codes:
- 0 on success (no failures)
- 1 if any batch failed after retries
"""

import argparse
import json
import os
import time
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from openai import OpenAI  # OpenAI Python SDK (>=1.x)

# Optional: load .env for local development (mirrors configurations/env_loader.py behavior)
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    _dotenv_path = find_dotenv(usecwd=True)
    if _dotenv_path:
        load_dotenv(_dotenv_path)
except Exception:
    # python-dotenv is optional; ignore if not installed
    pass

# Mirror pipeline client settings: HTTP/2 disabled, timeout configurable.
def create_openai_client(api_key: Optional[str], base_url: Optional[str], timeout_s: float) -> OpenAI:
    if not api_key:
        raise RuntimeError("Missing OpenAI API key: set LEGAL_EAGLE_OPENAI_API_KEY or pass --api-key")
    http_client = httpx.Client(http2=False, timeout=timeout_s)
    return OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)

def truncate_text(s: str, max_chars: int) -> str:
    if not s:
        return ""
    return s[:max_chars]

def chunk_list(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i+size] for i in range(0, len(items), size)]

def load_texts_from_json(path: str, keys: Tuple[str, str], max_items: int) -> List[str]:
    """Load list of dicts and build signature 'title content' strings."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected list in JSON, got {type(data)}")
    title_key, content_key = keys
    texts: List[str] = []
    for item in data[:max_items]:
        title = str(item.get(title_key) or "")
        content = str(item.get(content_key) or "")
        sig = f"{title} {content}".strip()
        texts.append(sig)
    return texts

def generate_dummy_texts(n: int, length: int) -> List[str]:
    """Generate dummy texts (~length chars) for connectivity tests."""
    base = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " \
           "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    texts: List[str] = []
    for i in range(n):
        s = f"Test text #{i}: " + (base * max(1, length // len(base)))
        texts.append(s[:length])
    return texts

def embed_batch(client: OpenAI, inputs: List[str], model: str, timeout_s: float) -> Dict[str, Any]:
    """Call embeddings for a batch and return diagnostics."""
    t0 = time.monotonic()
    try:
        resp = client.embeddings.create(input=inputs, model=model, timeout=timeout_s)
        dt = time.monotonic() - t0
        return {
            "ok": True,
            "count": len(inputs),
            "latency_s": dt,
            "error_type": None,
            "error_msg": None,
            "dim": (len(resp.data[0].embedding) if resp.data else None),
        }
    except Exception as e:
        dt = time.monotonic() - t0
        return {
            "ok": False,
            "count": len(inputs),
            "latency_s": dt,
            "error_type": type(e).__name__,
            "error_msg": str(e),
            "dim": None,
        }

def run_sequential(
    client: OpenAI,
    texts: List[str],
    model: str,
    batch_size: int,
    timeout_s: float,
    retries: int,
    backoff: float,
    dry_run: bool,
    max_chars: int,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    batches = chunk_list([truncate_text(t, max_chars) for t in texts], batch_size)
    for idx, batch in enumerate(batches):
        print(f"[SEQ] Batch {idx+1}/{len(batches)} size={len(batch)}")
        if dry_run:
            results.append({"ok": True, "count": len(batch), "latency_s": 0.0, "error_type": None, "error_msg": None, "dim": None})
            continue
        attempt = 0
        while True:
            diag = embed_batch(client, batch, model, timeout_s)
            if diag["ok"]:
                print(f"  -> OK, latency={diag['latency_s']:.2f}s, dim={diag['dim']}")
                results.append(diag)
                break
            else:
                print(f"  -> FAIL [{diag['error_type']}] {diag['error_msg']} (latency={diag['latency_s']:.2f}s)")
                if attempt >= retries:
                    results.append(diag)
                    break
                sleep_s = backoff * (2 ** attempt)
                print(f"     retrying in {sleep_s:.1f}s (attempt {attempt+1}/{retries})...")
                time.sleep(sleep_s)
                attempt += 1
    return results

def run_concurrent(
    client: OpenAI,
    texts: List[str],
    model: str,
    batch_size: int,
    timeout_s: float,
    retries: int,
    backoff: float,
    dry_run: bool,
    max_chars: int,
    concurrency: int,
) -> List[Dict[str, Any]]:
    """Concurrent batch execution using threads. Use with caution; default is sequential."""
    results: List[Dict[str, Any]] = []
    batches = chunk_list([truncate_text(t, max_chars) for t in texts], batch_size)

    def worker(batch_idx: int, batch_inputs: List[str]) -> Dict[str, Any]:
        print(f"[CONC] Batch {batch_idx+1}/{len(batches)} size={len(batch_inputs)}")
        if dry_run:
            return {"ok": True, "count": len(batch_inputs), "latency_s": 0.0, "error_type": None, "error_msg": None, "dim": None}
        attempt = 0
        while True:
            diag = embed_batch(client, batch_inputs, model, timeout_s)
            if diag["ok"]:
                print(f"  -> OK (batch {batch_idx+1}), latency={diag['latency_s']:.2f}s, dim={diag['dim']}")
                return diag
            else:
                print(f"  -> FAIL (batch {batch_idx+1}) [{diag['error_type']}] {diag['error_msg']} (latency={diag['latency_s']:.2f}s)")
                if attempt >= retries:
                    return diag
                sleep_s = backoff * (2 ** attempt)
                print(f"     retrying in {sleep_s:.1f}s (attempt {attempt+1}/{retries})...")
                time.sleep(sleep_s)
                attempt += 1

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = []
        for idx, batch in enumerate(batches):
            futures.append(pool.submit(worker, idx, batch))
        for fut in as_completed(futures):
            results.append(fut.result())
    return results

def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = sum(r.get("count", 0) for r in results)
    ok = sum(1 for r in results if r.get("ok"))
    failed = len(results) - ok
    avg_latency = (
        sum(r.get("latency_s", 0.0) for r in results if r.get("ok")) / max(1, ok)
    )
    error_types = {}
    for r in results:
        if not r.get("ok"):
            et = r.get("error_type") or "UnknownError"
            error_types[et] = error_types.get(et, 0) + 1
    return {
        "batches": len(results),
        "total_items": total,
        "ok_batches": ok,
        "failed_batches": failed,
        "avg_latency_ok_s": avg_latency,
        "error_types": error_types,
    }

def main():
    parser = argparse.ArgumentParser(description="Embeddings Connectivity Test (Standalone)")
    parser.add_argument("--model", type=str, default="text-embedding-3-small")
    parser.add_argument("--items", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--max-chars", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("LEGAL_EAGLE_OPENAI_TIMEOUT", "30")))
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--backoff", type=float, default=1.0)
    parser.add_argument("--from-json", type=str, default=None)
    parser.add_argument("--json-keys", nargs=2, type=str, default=("title", "content"))
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--base-url", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("LEGAL_EAGLE_OPENAI_API_KEY")
    base_url = args.base_url or os.environ.get("LEGAL_EAGLE_OPENAI_BASE_URL")
    timeout_s = float(args.timeout)

    print("=== Embeddings Connectivity Test ===")
    print(f"Model:         {args.model}")
    print(f"Items:         {args.items}")
    print(f"Batch size:    {args.batch_size}")
    print(f"Max chars:     {args.max_chars}")
    print(f"Timeout (s):   {timeout_s}")
    print(f"Concurrency:   {args.concurrency}")
    print(f"Retries:       {args.retries}")
    print(f"Backoff (s):   {args.backoff}")
    print(f"Base URL:      {base_url or '(default)'}")
    print(f"API key:       {'provided' if api_key else 'MISSING'}")
    print(f"Dry run:       {args.dry_run}")
    print("====================================")

    # Prepare texts
    if args.from_json:
        print(f"Loading texts from JSON: {args.from_json} (keys={args.json_keys})")
        texts = load_texts_from_json(args.from_json, tuple(args.json_keys), args.items)
    else:
        print("Generating dummy texts")
        texts = generate_dummy_texts(args.items, args.max_chars)

    # Create client
    client: Optional[OpenAI] = None
    if not args.dry_run:
        try:
            client = create_openai_client(api_key, base_url, timeout_s)
        except Exception as e:
            print(f"❌ Failed to initialize OpenAI client: {type(e).__name__}: {e}")
            raise

    # Run tests
    if args.concurrency <= 1:
        results = run_sequential(
            client=client,
            texts=texts,
            model=args.model,
            batch_size=args.batch_size,
            timeout_s=timeout_s,
            retries=args.retries,
            backoff=args.backoff,
            dry_run=args.dry_run,
            max_chars=args.max_chars,
        )
    else:
        results = run_concurrent(
            client=client,
            texts=texts,
            model=args.model,
            batch_size=args.batch_size,
            timeout_s=timeout_s,
            retries=args.retries,
            backoff=args.backoff,
            dry_run=args.dry_run,
            max_chars=args.max_chars,
            concurrency=args.concurrency,
        )

    summary = summarize(results)
    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2))
    print("===============")

    # Exit code based on failures
    if summary["failed_batches"] > 0:
        exit(1)
    exit(0)

if __name__ == "__main__":
    main()
