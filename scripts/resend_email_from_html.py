#!/usr/bin/env python3
"""
Resend email from HTML preview file with translation support.
Parses email_preview.html and sends to all configured receivers with their preferred languages.
"""

import os
import sys
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Any

# Add project root to path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from configurations.config_loader import (
    load_email_receivers_with_lang,
    load_language,
    creds,
)
from configurations.db import get_connection, create_schema_if_needed
from agents.email_sender import send_email


def parse_email_preview_html(html_path: str) -> List[Dict[str, Any]]:
    """
    Parse email_preview.html and extract grouped_summary structure.
    
    Returns list of dicts matching grouped_summary format:
    [
        {
            "title": "...",
            "summary": "...",
            "links": ["url1", "url2"],
            "titles": ["title1", "title2"],
            "category": "Other",
            "is_update_section": false
        },
        ...
    ]
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    grouped_summary = []
    
    # Find the main content div
    content_div = soup.find('div', {'dir': True})
    if not content_div:
        return []
    
    # Track current category and section type
    current_category = "Other"
    is_update_section = False
    
    # Iterate through all elements
    for elem in content_div.find_all(['h3', 'h4', 'p', 'ul']):
        # Category headers (h3)
        if elem.name == 'h3':
            text = elem.get_text().strip()
            if 'HCM' in text or 'الموارد البشرية' in text:
                current_category = "HCM"
            elif 'FIN' in text or 'المالية' in text:
                current_category = "FIN"
            else:
                current_category = "Other"
            is_update_section = False
            continue
        
        # Section headers (h4)
        if elem.name == 'h4':
            text = elem.get_text().strip()
            if 'New' in text or 'جديدة' in text:
                is_update_section = False
            elif 'Update' in text or 'تحديثات' in text:
                is_update_section = True
            continue
        
        # News item title (bold p tag)
        if elem.name == 'p':
            b_tag = elem.find('b')
            if b_tag:
                # This is a title
                title = b_tag.get_text().strip()
                # Remove emoji if present
                title = re.sub(r'^📚\s*', '', title)
                
                # Get summary (next p tag)
                next_p = elem.find_next_sibling('p')
                summary = ""
                if next_p and not next_p.find('b'):
                    summary = next_p.get_text().strip()
                
                # Get links (next ul tag)
                links = []
                titles = []
                next_ul = elem.find_next_sibling('ul')
                if next_ul:
                    for li in next_ul.find_all('li'):
                        a_tag = li.find('a')
                        if a_tag:
                            links.append(a_tag.get('href', ''))
                            titles.append(a_tag.get_text().strip())
                
                # Add to grouped_summary
                grouped_summary.append({
                    "title": title,
                    "summary": summary,
                    "links": links,
                    "titles": titles,
                    "category": current_category,
                    "is_update_section": is_update_section,
                })
    
    return grouped_summary


def resend_email_from_html(profile_id: int, country_code: str, lob: str) -> bool:
    """
    Resend email from HTML preview file with translation support.
    
    Args:
        profile_id: Profile ID
        country_code: Country code (e.g., 'TR')
        lob: Line of Business (e.g., 'HCM')
    
    Returns:
        True if successful
    
    Raises:
        FileNotFoundError: If email preview HTML not found
        ValueError: If configuration is missing or invalid
        RuntimeError: If email sending fails
    """
    profile_slug = f"{country_code}_{lob}"
    html_path = os.path.join(BASE_DIR, "outputs", profile_slug, "email_preview.html")
    
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"Email preview not found at: {html_path}. Run the profile first to generate the preview.")
    
    print(f"📧 Resending email from {html_path}...")
    
    # Parse HTML to extract grouped_summary
    print("📄 Parsing HTML...")
    grouped_summary = parse_email_preview_html(html_path)
    print(f"✅ Parsed {len(grouped_summary)} news items")
    
    # Load email receivers with translation languages
    receivers_with_lang = load_email_receivers_with_lang(profile_id)
    if not receivers_with_lang:
        raise ValueError("No email receivers configured for this profile. Add receivers in the Configure tab.")
    
    print(f"📧 Found {len(receivers_with_lang)} receiver(s)")
    
    # Load profile language
    profile_lang = load_language(profile_id)
    
    # Get credentials
    gmail_creds = creds.get("gmail", {})
    email_sender = gmail_creds.get("email_sender")
    app_password = gmail_creds.get("app_password")
    
    if not email_sender:
        raise ValueError("Gmail email address not configured. Set LEGAL_EAGLE_GMAIL_EMAIL environment variable.")
    if not app_password:
        raise ValueError("Gmail app password not configured. Set LEGAL_EAGLE_GMAIL_APP_PASSWORD environment variable.")
    
    # Get OpenAI API key for translation
    sap_cfg = creds.get("sap_aicore", {})
    if not sap_cfg:
        raise ValueError("SAP AI Core credentials not configured. Set required environment variables for translation.")
    
    # Send email with translation support
    print(f"📨 Sending email (profile language: {profile_lang})...")
    success = send_email(
        grouped_summary=grouped_summary,
        receivers_with_lang=receivers_with_lang,
        GMAIL_CREDS=gmail_creds,
        profile_lang=profile_lang,
        country=country_code,
        lob=lob,
        openai_api_key="",  # Not used - SAP AI Core credentials loaded from creds
        monitor_updates=None
    )
    
    if success:
        print("✅ Email sent successfully!")
        return True
    else:
        raise RuntimeError("Email sending failed. Check the email_sender agent logs for details.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python resend_email_from_html.py <profile_id>")
        print("Example: python resend_email_from_html.py 3")
        sys.exit(1)
    
    profile_id = int(sys.argv[1])
    
    # Get profile info
    conn = get_connection()
    create_schema_if_needed(conn)
    prof = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    conn.close()
    
    if not prof:
        print(f"❌ Profile {profile_id} not found")
        sys.exit(1)
    
    country_code = prof["country_code"]
    lob = prof["lob"]
    
    print(f"🦅 Legal Eagle - Resend Email")
    print(f"Profile: {country_code}/{lob} (ID: {profile_id})")
    print()
    
    success = resend_email_from_html(profile_id, country_code, lob)
    sys.exit(0 if success else 1)