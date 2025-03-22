import feedparser
import openai
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from dotenv import load_dotenv

# Load environment variables
load_dotenv("key.env")  # If running locally
openai.api_key = os.getenv("OPENAI_API_KEY")

# Email details
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# RSS feed URL
RSS_FEED_URL = "https://saudigazette.com.sa/rssFeed/0"

# Summarize description using OpenAI
def summarize_text(text):
    prompt = f"Please summarize this news article in 1-2 sentences:\n\n{text}"
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Failed to summarize: {e}"

# Fetch and process RSS feed
feed = feedparser.parse(RSS_FEED_URL)
summaries = []

print("📰 Latest News from Saudi Gazette:\n")

for entry in feed.entries:
    title = entry.title
    link = entry.link
    description = entry.description
    pub_date = entry.published

    summary = summarize_text(description)

    print(f"🔹 {title}")
    print(f"📅 {pub_date}")
    print(f"📝 {summary}\n")

    summaries.append(f"<p><strong>{title}</strong><br><em>{pub_date}</em><br>{summary}<br><a href='{link}'>Read more</a></p><hr>")

# Prepare email content
email_subject = "🗞️ Daily Saudi Gazette RSS Summary"
email_body = "<h2>Here are today’s headlines:</h2>" + "".join(summaries)

# ✅ Print the email preview before sending
print("\n📧 Preview of Email Content:")
print(f"Subject: {email_subject}")
print(email_body)

# Send the email using SendGrid
def send_email(subject, body):
    message = Mail(
        from_email=Email(EMAIL_SENDER, name="Hany Zanaty"),
        to_emails=EMAIL_RECEIVER,
        subject=subject,
        html_content=body
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# Send the email
send_email(email_subject, email_body)
