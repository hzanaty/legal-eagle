import smtplib
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from rss_parser import get_rss_summaries
import requests
from rss_parser import get_rss_summaries

email_body = get_rss_summaries()
send_email(subject="Daily News Summary", body=email_body)

# === Load secrets from GitHub Actions ENV or key.env ===
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")

# === Get Gmail access token using refresh token ===
def get_gmail_access_token():
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "refresh_token": GMAIL_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        print("✅ Access token retrieved successfully.")
        return response.json()["access_token"]
    else:
        raise Exception(f"❌ Failed to refresh access token: {response.text}")

# === Send email via Gmail SMTP using OAuth2 ===
def send_email(subject, body):
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
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.docmd("AUTH", "XOAUTH2 " + auth_string)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# === Prepare the email content ===
if __name__ == "__main__":
    summaries = get_rss_summaries()
    if summaries:
        body = "<h2>📰 Daily News Summary</h2>" + "<br><br>".join(summaries)
        send_email("🗞️ Your RSS Feed Summary", body)
    else:
        print("⚠️ No articles found or failed to fetch RSS feed.")
