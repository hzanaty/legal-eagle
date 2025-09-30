# email_sender.py
import smtplib
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from lpm_agent import get_lpm_analysis

# Load from GitHub secrets
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")

def get_gmail_access_token():
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
