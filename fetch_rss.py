import smtplib
import os
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Load secrets from GitHub Actions env
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

def get_gmail_access_token():
    with open("token.json") as token_file:
        token_data = json.load(token_file)
    creds = Credentials.from_authorized_user_info(token_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())
    return creds.token

def send_email():
    access_token = get_gmail_access_token()

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = "✅ Gmail OAuth Test from GitHub Actions"
    msg.attach(MIMEText("This is a test message sent from GitHub Actions using Gmail OAuth2.", "plain"))

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

send_email()
