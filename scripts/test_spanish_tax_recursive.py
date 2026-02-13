#!/usr/bin/env python3
"""
Test recursive crawling on Spanish Tax Agency (Agencia Tributaria).

Tests the 3-level hierarchy:
L1: https://sede.agenciatributaria.gob.es/Sede/irpf/novedades-impuesto.html
L2: Monthly archives (e.g., November 2025)
L3: Final news articles with IAFRIAFRC12F pattern
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.url_sources_runner import run_unified_sources


def test_spanish_tax_recursive():
    """
    Test recursive crawling on Spanish Tax Agency.
    """
    print("=" * 80)
    print("Testing Recursive Crawling: Spanish Tax Agency")
    print("=" * 80)
    
    # Configuration for Spanish Tax Agency
    url_sources = [{
        "url": "https://sede.agenciatributaria.gob.es/Sede/irpf/novedades-impuesto.html",
        "mode": "recursive",
        "sample_link": "https://www2.agenciatributaria.gob.es/ES13/S/IAFRIAFRC12F?TIPO=R&CODIGO=0141773",
        "max_depth": 3,
        "allowed_domains": "sede.agenciatributaria.gob.es\nwww2.agenciatributaria.gob.es",
        "path_filter": "novedades",
        "max_results": 5  # Limit for testing
    }]
    
    print("\n[Config]")
    print(f"  Entry URL: {url_sources[0]['url']}")
    print(f"  Mode: {url_sources[0]['mode']}")
    print(f"  Sample Link: {url_sources[0]['sample_link']}")
    print(f"  Max Depth: {url_sources[0]['max_depth']}")
    print(f"  Allowed Domains: {url_sources[0]['allowed_domains'].replace(chr(10), ', ')}")
    print(f"  Path Filter: {url_sources[0]['path_filter']}")
    print(f"  Max Results: {url_sources[0]['max_results']}")
    print()
    
    # Run the crawler
    result = run_unified_sources(url_sources)
    
    # Display results
    items = result.get("items", [])
    errors = result.get("errors", [])
    
    print("\n" + "=" * 80)
    print(f"Results: {len(items)} items, {len(errors)} errors")
    print("=" * 80)
    
    if items:
        print("\n[Items Found]")
        for idx, item in enumerate(items, 1):
            print(f"\n{idx}. {item.get('title', 'No title')[:80]}")
            print(f"   Link: {item.get('link', 'No link')}")
            print(f"   Date: {item.get('date', 'No date')}")
            print(f"   Source: {item.get('source', 'Unknown')}")
            print(f"   Type: {item.get('source_type', 'Unknown')}")
            content_preview = (item.get('content', '')[:200] or '').replace('\n', ' ')
            if content_preview:
                print(f"   Content: {content_preview}...")
    else:
        print("\n[No Items Found]")
    
    if errors:
        print("\n[Errors]")
        for idx, error in enumerate(errors, 1):
            print(f"{idx}. {error.get('url', 'Unknown URL')}")
            print(f"   Error: {error.get('error', 'Unknown error')}")
            if 'depth' in error:
                print(f"   Depth: {error.get('depth')}")
    
    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)
    
    return len(items) > 0


if __name__ == "__main__":
    success = test_spanish_tax_recursive()
    sys.exit(0 if success else 1)
