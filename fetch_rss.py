import feedparser
import openai
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv  # ✅ Correct import
from pathlib import Path

# Try to load .env only if it exists (for local runs)
if Path("key.env").is_file():
    load_dotenv("key.env")

# Read API credentials securely
openai.api_key = os.getenv("OPENAI_API_KEY")

# Email Configuration
# ✅ Read credentials from .env
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))

# Define the RSS feed URL
rss_url = "https://saudigazette.com.sa/rssFeed/0"

# Fetch and parse the RSS feed
feed = feedparser.parse(rss_url)

# Function to summarize articles using OpenAI
def summarize_text(text):
    prompt = f"Summarize this news article in 3-4 sentences:\n\n{text}"

    response = openai.chat.completions.create(
        model="gpt-4o",  
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.choices[0].message.content.strip()

# Prepare email content
email_subject = "📩 Daily News Summary from Saudi Gazette"
email_body = "<h2>Latest News</h2>"

for entry in feed.entries:  # Read all articles
    title = entry.title
    link = entry.link
    description = entry.get("description", entry.get("summary", "No Description Available"))
    pub_date = entry.get("published", "No Publication Date Available")

    # Summarize the article description using AI
    summary = summarize_text(description)

    # Print progress to terminal
    print(f"🔹 {title}")
    print(f"📅 {pub_date}")
    print(f"🔗 {link}")
    print(f"📝 Summary: {description}\n")

    # Add to email body
    email_body += f"""
    <p><strong>🔹 {title}</strong></p>
    <p><strong>📝 Summary:</strong> {summary}</p>
    <p><strong>📅 Published:</strong> {pub_date}</p>
    <p><strong>🔗 <a href='{link}'>Read Full Article</a></strong></p>
    <hr>
    """

# Send email function
def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))  # Send as HTML

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()  # 👈 Add this line
        server.starttls()
        server.ehlo()  # 👈 Re-identify after starting TLS
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# Send the email
send_email(email_subject, email_body)
