#!/usr/bin/env python3
"""
Test script for Türkiye HCM sources:
- iKanun (force_dynamic mode)
- Resmi Gazete (date-templated mode)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.url_sources_runner import run_unified_sources


def test_ikanun():
    """Test iKanun source with force_dynamic mode."""
    print("=" * 60)
    print("Testing iKanun Source")
    print("=" * 60)
    
    sources = [{
        "url": "http://www.ikanun.com/duyurular",
        "mode": "force_dynamic",
        "sample_link": "http://www.ikanun.com/duyuru/muhsgk-beyanname-duzenleme-programinin-bdp-yeni-surumu-03022026-yayimlandi",
        "read_more_label": None,
        "date_scope": "all"
    }]
    
    result = run_unified_sources(sources)
    
    print(f"\n✓ Items collected: {len(result['items'])}")
    print(f"✗ Errors: {len(result['errors'])}")
    
    if result['items']:
        print("\nSample items:")
        for i, item in enumerate(result['items'][:3], 1):
            print(f"\n{i}. {item.get('title', 'No title')[:100]}")
            print(f"   Link: {item.get('link', 'No link')}")
            print(f"   Date: {item.get('date', 'No date')}")
    
    if result['errors']:
        print("\nErrors:")
        for err in result['errors'][:3]:
            print(f"  - {err}")
    
    return result


def test_resmi_gazete():
    """Test Resmi Gazete source with date-templated mode."""
    print("\n" + "=" * 60)
    print("Testing Resmi Gazete Source")
    print("=" * 60)
    
    sources = [{
        "url": "https://www.resmigazete.gov.tr/",
        "mode": "auto",
        "sample_link": "https://www.resmigazete.gov.tr/eskiler/2026/02/20260217.pdf",
        "read_more_label": "PDF Görüntüle",
        "date_scope": "last_7_days"
    }]
    
    result = run_unified_sources(sources)
    
    print(f"\n✓ Items collected: {len(result['items'])}")
    print(f"✗ Errors: {len(result['errors'])}")
    
    if result['items']:
        print("\nSample items:")
        for i, item in enumerate(result['items'][:5], 1):
            print(f"\n{i}. {item.get('title', 'No title')[:100]}")
            print(f"   Link: {item.get('link', 'No link')}")
            print(f"   Date: {item.get('date', 'No date')}")
    
    if result['errors']:
        print("\nErrors:")
        for err in result['errors'][:3]:
            print(f"  - {err}")
    
    return result


def main():
    """Run tests for both Turkish sources."""
    print("\n" + "=" * 60)
    print("TÜRKIYE HCM SOURCES TEST")
    print("=" * 60)
    
    # Test 1: iKanun
    try:
        ikanun_result = test_ikanun()
    except Exception as e:
        print(f"\n❌ iKanun test failed: {e}")
        ikanun_result = {"items": [], "errors": [{"error": str(e)}]}
    
    # Test 2: Resmi Gazete
    try:
        gazette_result = test_resmi_gazete()
    except Exception as e:
        print(f"\n❌ Resmi Gazete test failed: {e}")
        gazette_result = {"items": [], "errors": [{"error": str(e)}]}
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"iKanun: {len(ikanun_result['items'])} items, {len(ikanun_result['errors'])} errors")
    print(f"Resmi Gazete: {len(gazette_result['items'])} items, {len(gazette_result['errors'])} errors")
    print(f"Total: {len(ikanun_result['items']) + len(gazette_result['items'])} items")
    
    if len(ikanun_result['items']) > 0 and len(gazette_result['items']) > 0:
        print("\n✅ Both sources working!")
    elif len(ikanun_result['items']) > 0 or len(gazette_result['items']) > 0:
        print("\n⚠️  At least one source working")
    else:
        print("\n❌ Both sources failed")
    
    print("\n")


if __name__ == "__main__":
    main()
