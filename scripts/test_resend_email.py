#!/usr/bin/env python3
"""
Test script for resend_email_from_html functionality.
Tests HTML parsing without actually sending emails.
"""

import os
import sys

# Add project root to path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.resend_email_from_html import parse_email_preview_html

def test_parse_tr_hcm_html():
    """Test parsing TR/HCM email preview HTML."""
    html_path = os.path.join(BASE_DIR, "outputs", "TR_HCM", "email_preview.html")
    
    if not os.path.exists(html_path):
        print(f"❌ HTML file not found: {html_path}")
        return False
    
    print(f"📄 Parsing: {html_path}")
    print()
    
    try:
        grouped_summary = parse_email_preview_html(html_path)
        
        print(f"✅ Successfully parsed {len(grouped_summary)} news items")
        print()
        
        # Display parsed items
        for i, item in enumerate(grouped_summary, 1):
            print(f"Item {i}:")
            print(f"  Title: {item['title'][:80]}...")
            print(f"  Summary: {item['summary'][:100]}...")
            print(f"  Category: {item['category']}")
            print(f"  Is Update: {item['is_update_section']}")
            print(f"  Links: {len(item['links'])} link(s)")
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🧪 Testing HTML Email Parser")
    print("=" * 60)
    print()
    
    success = test_parse_tr_hcm_html()
    
    print()
    print("=" * 60)
    if success:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Tests failed")
        sys.exit(1)