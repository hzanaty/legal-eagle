import feedparser
import openai
import os
import base64
import json
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# === Load credentials from environment variables ===
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# === Set your OpenAI API key ===
openai.api_key = OPENAI_API_KEY

# === Define the RSS feed URL ===
RSS_FEED_URL = "https://saudigazette.com.sa/rssFeed/0"

# === Summarize function using GPT-4o ===
def summarize_text(text):
    prompt = f"Summarize the following news article in just 1 line:\n\n{text}"
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# === Get Gmail access token from token.json ===
def get_gmail_access_token():
    with open("token.json") as token_file:
        token_data = json.load(token_file)
    creds = Credentials.from_authorized_user_info(token_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())
    return creds.token

# === Send email via Gmail SMTP using OAuth2 ===
def send_email(subject, body):
    access_token = get_gmail_access_token()

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
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

# === Parse RSS feed ===
feed = feedparser.parse(RSS_FEED_URL)
print("📰 Latest News from Saudi Gazette:\n")

email_body = ""
for entry in feed.entries:
    title = entry.title
    link = entry.link
    description = entry.description
    pub_date = entry.published

    summary = summarize_text(description)
    print(f"🔹 {title} ({pub_date})")
    print(f"Summary: {summary}\n")

    email_body += f"<h3>{title}</h3><p><strong>{pub_date}</strong></p><p>{summary}</p><a href='{link}'>Read more</a><br><hr>"

email_subject = f"🗞️ Daily News Summary – {datetime.datetime.now().strftime('%Y-%m-%d')}"
send_email(email_subject, email_body)
