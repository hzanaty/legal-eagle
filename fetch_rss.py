import os
import feedparser
import requests
import openai
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === Load secrets from GitHub Actions ENV ===
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === Get Gmail access token using refresh token ===
def get_gmail_access_token():
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    response = requests.post(token_url, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]

# === Fetch and summarize RSS feed ===
def fetch_and_summarize_rss(feed_url):
    feed = feedparser.parse(feed_url)
    summaries = []

    for entry in feed.entries:
        title = entry.get("title", "No Title")
        link = entry.get("link", "")
        description = entry.get("description", "No Description")
        pub_date = entry.get("published", "")

        prompt = f"Summarize the following news article in one simple line using same language used in the article:
Title: {title}
Date: {pub_date}
Description: {description}"

        openai.api_key = OPENAI_API_KEY
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        summary = response.choices[0].message.content.strip()
        print(f"\n📰 {title}\n🔗 {link}\n🗓️ {pub_date}\n📝 Summary: {summary}\n")
        summaries.append(f"<p><b>{title}</b><br>{summary}<br><a href='{link}'>{link}</a><br><i>{pub_date}</i></p>")

    return summaries

# === Send email via Gmail SMTP OAuth2 ===
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

# === MAIN EXECUTION ===
if __name__ == "__main__":
    FEED_URL = "https://saudigazette.com.sa/rssFeed/0"
    print("📡 Fetching RSS feed...")
    summary_list = fetch_and_summarize_rss(FEED_URL)
    email_subject = "📰 Daily RSS Summary - Saudi Gazette"
    email_body = "<h2>🗞️ Today's Highlights:</h2>" + "".join(summary_list)
    send_email(email_subject, email_body)
