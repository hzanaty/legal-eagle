import feedparser
import os
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from openai import OpenAI

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# RSS Feed URL
RSS_URL = "https://saudigazette.com.sa/rssFeed/0"

# Gmail and OAuth
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# OpenAI setup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Function to summarize text with OpenAI
def summarize_text(text):
    prompt = f"Summarize the following news article in just one single line:\n{text}"
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# Function to send email using Gmail API
def send_email(subject, body):
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/gmail.send'])
    service = build('gmail', 'v1', credentials=creds)

    message = MIMEText(body, "plain")
    message['to'] = EMAIL_RECEIVER
    message['from'] = EMAIL_SENDER
    message['subject'] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {'raw': raw_message}

    try:
        send_message = service.users().messages().send(userId="me", body=create_message).execute()
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# Parse RSS feed
feed = feedparser.parse(RSS_URL)

# Build summary content
print("📰 Latest News from Saudi Gazette:\n")
summary_lines = []
for entry in feed.entries:
    title = entry.title
    link = entry.link
    description = entry.get("description", "No description available.")

    print(f"🔹 {title}\n{link}\n📄 Description: {description}\n")

    summary = summarize_text(description)
    summary_lines.append(f"📰 {title}\n🔗 {link}\n📝 Summary: {summary}\n")

# Prepare final email content
email_subject = "🗞️ Daily News Summary: Saudi Gazette"
email_body = "\n\n".join(summary_lines)

# Send the email
send_email(email_subject, email_body)
