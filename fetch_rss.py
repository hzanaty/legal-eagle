import feedparser
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from base64 import urlsafe_b64encode
import openai

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_TO = os.getenv("EMAIL_TO")

openai.api_key = OPENAI_API_KEY

rss_url = "https://saudigazette.com.sa/rssFeed/0"

# Function to summarize text using OpenAI
def summarize_text(text):
    prompt = f"Summarize this article for HCM and Payroll relevance only: {text}"
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# Gmail service
def create_gmail_service():
    creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/gmail.send"])
    service = build("gmail", "v1", credentials=creds)
    return service

# Send email via Gmail API
def send_email(subject, body):
    message = MIMEMultipart()
    message["To"] = EMAIL_TO
    message["From"] = EMAIL_SENDER
    message["Subject"] = subject
    message.attach(MIMEText(body, "html"))

    raw_message = urlsafe_b64encode(message.as_bytes()).decode()
    service = create_gmail_service()
    try:
        result = service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
        print(f"✅ Email sent successfully! Message ID: {result['id']}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# Process feed
feed = feedparser.parse(rss_url)
email_body = ""
print("📰 Saudi Gazette Articles:")

for entry in feed.entries:
    title = entry.title
    link = entry.link
    description = entry.description
    pub_date = entry.published

    print(f"\n📌 {title}\n{link}\n📅 {pub_date}\n{description}\n")

    summary = summarize_text(description)
    email_body += f"<h3>{title}</h3><p><strong>Date:</strong> {pub_date}</p><p>{summary}</p><a href='{link}'>Read more</a><hr>"

send_email("🗞️ Daily Saudi Gazette Summary", email_body)
