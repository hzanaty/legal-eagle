# agents/email_sender.py

import smtplib
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

# Load from GitHub secrets
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")


def get_gmail_access_token():
    """Fetch a fresh Gmail access token using the refresh token."""
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        print("✅ Access token retrieved successfully.")
        return response.json()["access_token"]
    else:
        raise Exception(f"❌ Failed to refresh token: {response.text}")


def send_email(subject, body):
    """Send an email with the given subject and HTML body."""
    access_token = get_gmail_access_token()

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    auth_string = f"user={EMAIL_SENDER}\1auth=Bearer {access_token}\1\1"
    auth_string = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.docmd("AUTH", "XOAUTH2 " + auth_string)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")


def send_summary_email(grouped_results):
    """
    Formats grouped news results into an HTML digest and sends it by email.
    """
    if not grouped_results:
        print("ℹ️ No grouped results to email.")
        return

    html_body = "<h2>📢 Daily Legal Eagle Digest</h2>"

    # Group by category for cleaner structure
    categories = {}
    for group in grouped_results:
        cat = group.get("category", "OTHER")
        categories.setdefault(cat, []).append(group)

    # Render categories in order: HCM → FIN → others
    ordered_cats = ["HCM", "FIN"] + [c for c in categories.keys() if c not in ["HCM", "FIN"]]

    for cat in ordered_cats:
        if cat not in categories:
            continue
        html_body += f"<h3>{cat} Updates</h3>"
        for i, group in enumerate(categories[cat], 1):
            html_body += f"<p><b>Group {i} ({len(group['items'])} items)</b><br>"
            html_body += f"📝 {group['summary']}<br>"
            html_body += "🔗 Sources:<ul>"
            for link in group["links"]:
                html_body += f"<li><a href='{link}'>{link}</a></li>"
            html_body += "</ul></p>"

    # Send email
    send_email("Daily Legal Eagle Digest", html_body)
