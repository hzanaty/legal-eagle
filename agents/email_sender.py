import smtplib
import base64
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from configurations.config_loader import creds

CLIENT_ID = creds["gmail"]["client_id"]
CLIENT_SECRET = creds["gmail"]["client_secret"]
REFRESH_TOKEN = creds["gmail"]["refresh_token"]

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
        return response.json()["access_token"]
    else:
        raise Exception(f"❌ Failed to refresh token: {response.text}")

def send_email(sender, receivers, subject, body):
    """
    Sends an email via Gmail SMTP using OAuth2.
    - sender: string
    - receivers: list or string
    - subject: string
    - body: HTML content
    """
    access_token = get_gmail_access_token()

    msg = MIMEMultipart()
    msg["From"] = sender
    if isinstance(receivers, list):
        msg["To"] = ", ".join(receivers)
    else:
        msg["To"] = receivers
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    auth_string = f"user={sender}\1auth=Bearer {access_token}\1\1"
    auth_string = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.docmd("AUTH", "XOAUTH2 " + auth_string)
        server.sendmail(sender, receivers if isinstance(receivers, list) else [receivers], msg.as_string())
        server.quit()
        print(f"✅ Email sent successfully to {msg['To']}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
