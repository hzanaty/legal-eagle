#!/usr/bin/env python3
"""
Email Inbox Parser Agent for Law-to-Specification Monitor Updates.

Connects to Gmail IMAP, fetches "Monitor updates" emails forwarded by LPMs,
parses the content, and marks them as processed in the database.
"""

import imaplib
import email
from email.header import decode_header
import re
from typing import List, Dict, Optional, Any
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configurations.db import (
    get_connection,
    is_monitor_email_processed,
    insert_monitor_update_processed
)


def decode_mime_words(s: str) -> str:
    """Decode MIME encoded-words in headers."""
    if not s:
        return ""
    decoded_fragments = decode_header(s)
    return ''.join(
        fragment.decode(encoding or 'utf-8') if isinstance(fragment, bytes) else fragment
        for fragment, encoding in decoded_fragments
    )


def get_email_body(msg: email.message.Message) -> str:
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
                except Exception:
                    continue
    else:
        # Not multipart
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='ignore')
        except Exception:
            body = str(msg.get_payload())
    
    return body


def parse_law_to_spec_email(body: str) -> Dict[str, Any]:
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
        'changes': []
    }
    
    # Extract report date
    date_match = re.search(r'Daily Report of Regulatory Changes - (\d{4}-\d{2}-\d{2})', body)
    if date_match:
        parsed['report_date'] = date_match.group(1)
    
    # Extract monitored URL - more flexible pattern to handle line breaks
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
        link_section = re.search(r'for link:(.+?)(?:\n\n|-|$)', body, re.DOTALL)
        if link_section:
            url_pattern = re.search(r'(https?://[^\s<>\[\]]+)', link_section.group(1))
            if url_pattern:
                parsed['monitored_url'] = url_pattern.group(1)
    
    # Extract change bullet points
    changes_section = body
    if parsed['monitored_url']:
        url_pos = body.find(parsed['monitored_url'])
        if url_pos != -1:
            changes_section = body[url_pos + len(parsed['monitored_url']):]
    elif 'The following meaningful updates' in body:
        updates_pos = body.find('The following meaningful updates')
        changes_section = body[updates_pos:]
    
    # Extract bullet points with more flexible matching
    bullet_pattern = re.compile(
        r'^[\s]*[-•]\s*(.+?)(?=\n[\s]*[-•]|\nGo to Item|\n\n|You may review|$)',
        re.MULTILINE | re.DOTALL
    )
    matches = bullet_pattern.findall(changes_section)
    parsed['changes'] = [m.strip() for m in matches if m.strip()]
    
    return parsed


def fetch_monitor_updates(
    profile_id: int,
    recipient_emails: List[str],
    gmail_email: str,
    gmail_app_password: str,
    conn=None
) -> List[Dict[str, Any]]:
    """
    Fetch Law-to-Specification "Monitor updates" emails for a specific profile.
    
    Args:
        profile_id: Profile ID to associate emails with
        recipient_emails: List of LPM emails who forward these emails
        gmail_email: Gmail address to connect to
        gmail_app_password: Gmail App Password
        conn: Optional database connection (will create if not provided)
    
    Returns:
        List of parsed monitor updates (aggregated from all unprocessed emails)
    """
    should_close_conn = False
    if conn is None:
        conn = get_connection()
        should_close_conn = True
    
    try:
        # Connect to Gmail IMAP
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(gmail_email, gmail_app_password)
        
        # Select inbox
        status, messages = imap.select("INBOX")
        if status != "OK":
            return []
        
        # Search for "Monitor updates" emails (handles both original and FW: prefix)
        # IMAP SUBJECT search is case-insensitive and does substring matching
        status, message_ids = imap.search(None, '(SUBJECT "Monitor updates")')
        if status != "OK":
            imap.close()
            imap.logout()
            return []
        
        message_id_list = message_ids[0].split()
        if not message_id_list:
            imap.close()
            imap.logout()
            return []
        
        # Process emails
        monitor_updates = []
        
        for msg_id in message_id_list:
            # Fetch the email
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            
            # Parse the email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Get email metadata
            sender = decode_mime_words(msg.get("From", ""))
            email_message_id = msg.get("Message-ID", f"msg_{msg_id.decode()}")
            
            # Check if from any of the configured receivers
            sender_match = False
            for recipient_email in recipient_emails:
                if recipient_email.lower() in sender.lower():
                    sender_match = True
                    break
            
            if not sender_match:
                continue
            
            # Check if already processed
            if is_monitor_email_processed(conn, email_message_id):
                continue
            
            # Extract body and parse
            body = get_email_body(msg)
            parsed = parse_law_to_spec_email(body)
            
            # If we successfully parsed data, mark as processed and add to results
            if parsed['report_date'] or parsed['monitored_url'] or parsed['changes']:
                # Mark as processed in database
                insert_monitor_update_processed(
                    conn,
                    profile_id,
                    email_message_id,
                    parsed['report_date'],
                    parsed['monitored_url'],
                    parsed['changes']
                )
                
                # Add to results
                monitor_updates.append({
                    'report_date': parsed['report_date'],
                    'monitored_url': parsed['monitored_url'],
                    'changes': parsed['changes'],
                    'processed_at': datetime.utcnow().isoformat()
                })
        
        # Close connection
        imap.close()
        imap.logout()
        
        return monitor_updates
        
    except imaplib.IMAP4.error as e:
        print(f"IMAP Error while fetching monitor updates: {e}")
        return []
    except Exception as e:
        print(f"Error while fetching monitor updates: {e}")
        return []
    finally:
        if should_close_conn and conn:
            conn.close()


def format_monitor_updates_for_email(monitor_updates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Format monitor updates for inclusion in email digest.
    
    Args:
        monitor_updates: List of monitor update dictionaries
    
    Returns:
        Formatted data for email template, or None if no updates
    """
    if not monitor_updates:
        return None
    
    # Aggregate all changes from all emails
    all_changes = []
    latest_date = None
    urls = set()
    
    for update in monitor_updates:
        if update['changes']:
            all_changes.extend(update['changes'])
        if update['report_date']:
            if not latest_date or update['report_date'] > latest_date:
                latest_date = update['report_date']
        if update['monitored_url']:
            urls.add(update['monitored_url'])
    
    return {
        'report_date': latest_date,
        'monitored_urls': list(urls),
        'changes': all_changes,
        'count': len(all_changes)
    }
