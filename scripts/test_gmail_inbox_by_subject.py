#!/usr/bin/env python3
"""
Test script to fetch Law-to-Specification emails from Gmail IMAP by subject line.
This version searches by subject instead of sender (useful for forwarded emails).

Usage:
    python scripts/test_gmail_inbox_by_subject.py

Requirements:
    - LEGAL_EAGLE_GMAIL_EMAIL_SENDER environment variable
    - LEGAL_EAGLE_GMAIL_APP_PASSWORD environment variable
"""

import imaplib
import email
from email.header import decode_header
import sys
import os
from datetime import datetime
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.env_loader import load_env_credentials

def decode_mime_words(s):
    """Decode MIME encoded-words in headers."""
    if not s:
        return ""
    decoded_fragments = decode_header(s)
    return ''.join(
        fragment.decode(encoding or 'utf-8') if isinstance(fragment, bytes) else fragment
        for fragment, encoding in decoded_fragments
    )

def get_email_body(msg):
    """Extract plain text body from email message."""
    body = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # Skip attachments
            if "attachment" in content_disposition:
                continue
                
            # Get plain text parts
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='ignore')
                    break  # Use first plain text part
                except Exception as e:
                    print(f"Error decoding part: {e}")
                    continue
    else:
        # Not multipart
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='ignore')
        except Exception as e:
            print(f"Error decoding body: {e}")
            body = str(msg.get_payload())
    
    return body

def parse_law_to_spec_email(body):
    """
    Parse the Law-to-Specification email format.
    
    Expected format:
        Daily Report of Regulatory Changes - YYYY-MM-DD
        Hello,
        The following meaningful updates were identified for link:
        https://www.example.gov/...
        - change summary 1
        - change summary 2
        ...
    
    Handles both direct emails and forwarded emails from Outlook.
    """
    parsed = {
        'report_date': None,
        'monitored_url': None,
        'changes': [],
        'raw_body': body
    }
    
    # Extract report date
    date_match = re.search(r'Daily Report of Regulatory Changes - (\d{4}-\d{2}-\d{2})', body)
    if date_match:
        parsed['report_date'] = date_match.group(1)
    
    # Extract monitored URL - more flexible pattern to handle line breaks
    # Pattern 1: Standard format
    url_match = re.search(r'The following meaningful updates were identified for link:\s*(.+?)(?:\n|\r)', body, re.DOTALL)
    if url_match:
        url_candidate = url_match.group(1).strip()
        # Clean up any Outlook artifacts or line breaks
        url_candidate = re.sub(r'\s+', '', url_candidate)  # Remove all whitespace
        # Extract just the URL part
        url_pattern = re.search(r'(https?://[^\s<>\[\]]+)', url_candidate)
        if url_pattern:
            parsed['monitored_url'] = url_pattern.group(1)
    
    # If URL not found, try to find any https URL after "for link:"
    if not parsed['monitored_url']:
        # Look for any URL in the text after "for link:"
        link_section = re.search(r'for link:(.+?)(?:\n\n|-|$)', body, re.DOTALL)
        if link_section:
            url_pattern = re.search(r'(https?://[^\s<>\[\]]+)', link_section.group(1))
            if url_pattern:
                parsed['monitored_url'] = url_pattern.group(1)
    
    # Extract change bullet points
    # Look for lines starting with "- " after the URL or report date
    # More flexible pattern to handle different formatting
    changes_section = body
    if parsed['monitored_url']:
        url_pos = body.find(parsed['monitored_url'])
        if url_pos != -1:
            changes_section = body[url_pos + len(parsed['monitored_url']):]
    elif 'The following meaningful updates' in body:
        updates_pos = body.find('The following meaningful updates')
        changes_section = body[updates_pos:]
    
    # Extract bullet points with more flexible matching
    bullet_pattern = re.compile(r'^[\s]*[-•]\s*(.+?)(?=\n[\s]*[-•]|\nGo to Item|\n\n|You may review|$)', re.MULTILINE | re.DOTALL)
    matches = bullet_pattern.findall(changes_section)
    parsed['changes'] = [m.strip() for m in matches if m.strip()]
    
    return parsed

def fetch_law_to_spec_emails(email_address, app_password, max_emails=5):
    """
    Connect to Gmail IMAP and fetch Law-to-Specification emails by subject.
    
    Args:
        email_address: Gmail address
        app_password: Gmail App Password
        max_emails: Maximum number of emails to fetch
    
    Returns:
        List of parsed email data
    """
    print(f"\n{'='*80}")
    print(f"Connecting to Gmail IMAP...")
    print(f"Email: {email_address}")
    print(f"{'='*80}\n")
    
    try:
        # Connect to Gmail IMAP
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        print("✓ Connected to imap.gmail.com:993")
        
        # Login
        imap.login(email_address, app_password)
        print(f"✓ Authenticated as {email_address}")
        
        # Select inbox
        status, messages = imap.select("INBOX")
        if status != "OK":
            print(f"✗ Failed to select INBOX: {status}")
            return []
        
        total_messages = int(messages[0])
        print(f"✓ Selected INBOX ({total_messages} total messages)")
        
        # Search for emails with "Monitor updates" in subject
        print(f"\nSearching for emails with subject containing: 'Monitor updates'")
        status, message_ids = imap.search(None, '(SUBJECT "Monitor updates")')
        
        if status != "OK":
            print(f"✗ Search failed: {status}")
            return []
        
        # Get list of message IDs
        message_id_list = message_ids[0].split()
        found_count = len(message_id_list)
        print(f"✓ Found {found_count} email(s) with 'Monitor updates' in subject")
        
        if found_count == 0:
            print("\n⚠ No emails found.")
            print("\nTrying alternative search: 'Daily Report of Regulatory Changes'")
            status, message_ids = imap.search(None, '(BODY "Daily Report of Regulatory Changes")')
            if status == "OK":
                message_id_list = message_ids[0].split()
                found_count = len(message_id_list)
                print(f"✓ Found {found_count} email(s) with regulatory changes content")
            
            if found_count == 0:
                print("\n⚠ Still no emails found. Make sure you've forwarded the email to this inbox.")
                imap.close()
                imap.logout()
                return []
        
        # Fetch the most recent emails (up to max_emails)
        emails_to_fetch = message_id_list[-max_emails:] if len(message_id_list) > max_emails else message_id_list
        emails_to_fetch.reverse()  # Most recent first
        
        parsed_emails = []
        
        print(f"\n{'='*80}")
        print(f"Fetching and parsing {len(emails_to_fetch)} email(s)...")
        print(f"{'='*80}\n")
        
        for i, msg_id in enumerate(emails_to_fetch, 1):
            print(f"\n--- Email {i}/{len(emails_to_fetch)} (ID: {msg_id.decode()}) ---\n")
            
            # Fetch the email
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            
            if status != "OK":
                print(f"✗ Failed to fetch email {msg_id}: {status}")
                continue
            
            # Parse the email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Extract headers
            subject = decode_mime_words(msg.get("Subject", ""))
            sender = decode_mime_words(msg.get("From", ""))
            date_str = msg.get("Date", "")
            
            print(f"Subject: {subject}")
            print(f"From: {sender}")
            print(f"Date: {date_str}")
            
            # Extract body
            body = get_email_body(msg)
            
            # Parse Law-to-Spec format
            parsed = parse_law_to_spec_email(body)
            
            print(f"\n{'─'*80}")
            print("PARSED DATA:")
            print(f"{'─'*80}")
            print(f"Report Date: {parsed['report_date']}")
            print(f"Monitored URL: {parsed['monitored_url']}")
            print(f"Changes Found: {len(parsed['changes'])}")
            
            if parsed['changes']:
                print("\nChange Summaries:")
                for j, change in enumerate(parsed['changes'], 1):
                    # Truncate long changes for display
                    display_change = change[:200] + "..." if len(change) > 200 else change
                    print(f"  {j}. {display_change}")
            else:
                print("\n⚠ No changes parsed. Raw body preview:")
                print(body[:500])
            
            parsed_emails.append({
                'subject': subject,
                'sender': sender,
                'date': date_str,
                'parsed': parsed
            })
        
        # Close connection
        imap.close()
        imap.logout()
        print(f"\n{'='*80}")
        print("✓ Connection closed")
        print(f"{'='*80}\n")
        
        return parsed_emails
        
    except imaplib.IMAP4.error as e:
        print(f"\n✗ IMAP Error: {e}")
        print("\nTroubleshooting:")
        print("1. Verify Gmail App Password is correct")
        print("2. Ensure IMAP is enabled in Gmail settings")
        print("3. Check if 2FA is enabled on your Google account")
        return []
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def main():
    """Main entry point."""
    print("\n" + "="*80)
    print("Legal Eagle - Gmail IMAP Test Script (By Subject)")
    print("Testing email fetch for Law-to-Specification notifications")
    print("="*80)
    
    # Load environment variables
    creds = load_env_credentials()
    
    email_address = creds['gmail']['email_sender']
    app_password = creds['gmail']['app_password']
    
    if not email_address or not app_password:
        print("\n✗ Error: Missing Gmail credentials")
        print("\nRequired environment variables:")
        print("  - LEGAL_EAGLE_GMAIL_EMAIL_SENDER")
        print("  - LEGAL_EAGLE_GMAIL_APP_PASSWORD")
        sys.exit(1)
    
    # Fetch and parse emails
    emails = fetch_law_to_spec_emails(email_address, app_password, max_emails=5)
    
    # Summary
    print("\n" + "="*80)
    print(f"SUMMARY: Successfully parsed {len(emails)} email(s)")
    print("="*80)
    
    if emails:
        print("\nNext Steps:")
        print("1. ✓ Email parsing is working")
        print("2. Create email_inbox_parser.py agent to integrate with Legal Eagle")
        print("3. Add 'Email_Alert' as new source_type to pipeline")
        print("4. Configure forwarding rule or schedule to check inbox periodically")
    else:
        print("\n⚠ No emails were successfully parsed.")
        print("\nPlease:")
        print("1. Verify you forwarded the email to:", email_address)
        print("2. Wait a few minutes for email delivery")
        print("3. Check Gmail inbox manually to confirm email arrived")
        print("4. Re-run this script")
    
    print()

if __name__ == "__main__":
    main()
