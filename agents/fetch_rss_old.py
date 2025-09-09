import feedparser
import openai
import os
import requests
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === Load secrets from GitHub Actions env ===
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")

# === Function to get a fresh Gmail access token ===
def get_gmail_access_token():
    print("🔄 Requesting new Gmail access token...")
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
        raise Exception(f"❌ Failed to refresh: {response.text}")

# === Function to summarize using OpenAI ===
def summarize_text(text):
    openai.api_key = OPENAI_API_KEY
    prompt = f"Summarize the following news article in 2 lines, the first line in English and the second line in Arabaic ():\n\n{text}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ OpenAI Error: {e}")
        return "Summary failed."

# === Parse RSS feed ===
def fetch_and_summarize_articles():
    feed_url = "https://saudigazette.com.sa/rssFeed/0"
    feed = feedparser.parse(feed_url)

    print("📰 Latest News from Saudi Gazette:\n")
    all_summaries = []

    for entry in feed.entries:
        title = entry.title
        link = entry.link
        description = entry.description
        pub_date = entry.published

        print(f"🔗 {title} ({pub_date})")
        print(f"📄 Description: {description}")

        summary = summarize_text(description)
        print(f"✏️ Summary: {summary}\n")

        all_summaries.append(f"<b>{title}</b><br>{summary}<br><a href='{link}'>{link}</a><br><br>")

    return all_summaries

# === Send Email via Gmail SMTP using OAuth2 ===
def send_email(subject, body_html):
    access_token = get_gmail_access_token()

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg.attach(MIMEText(body_html, "html"))

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

# === Run the full process ===
if __name__ == "__main__":
    email_subject = "🗞️ Daily Summary: Saudi Gazette RSS"
    email_body = "".join(fetch_and_summarize_articles())
    send_email(email_subject, email_body)
