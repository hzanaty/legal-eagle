import smtplib
import base64
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Hardcoded sender address
EMAIL_SENDER = "hanyzanaty@gmail.com"


def get_gmail_access_token(gmail_creds):
    """
    Exchanges the refresh token for a short-lived access token.
    gmail_creds must be a dict with client_id, client_secret, refresh_token.
    """
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": gmail_creds["client_id"],
        "client_secret": gmail_creds["client_secret"],
        "refresh_token": gmail_creds["refresh_token"],
        "grant_type": "refresh_token"
    }
    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"❌ Failed to refresh token: {response.text}")


def build_email_body(grouped_summary):
    """
    Builds a simple HTML email body from grouped news items.
    """
    html = ["<h2>🦅 Legal Eagle Daily Digest</h2>"]

    for i, group in enumerate(grouped_summary, 1):
        html.append(f"<h3>📚 Group {i} ({group['category']}, {group['group_size']} items)</h3>")
        html.append(f"<p><b>Summary:</b> {group['summary']}</p>")
        html.append("<ul>")
        for link, title in zip(group["links"], group["titles"]):
            html.append(f"<li><a href='{link}'>{title}</a></li>")
        html.append("</ul><hr>")

    return "\n".join(html)


def send_email(grouped_summary, EMAIL_RECEIVERS, GMAIL_CREDS):
    """
    Sends an email via Gmail SMTP using OAuth2.
    - grouped_summary: output of grouping agent
    - receivers: list or string
    - gmail_creds: dict from credentials.json
    """
    access_token = get_gmail_access_token(GMAIL_CREDS)

    subject = "🦅 Legal Eagle Daily Digest"
    body = build_email_body(grouped_summary)

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    if isinstance(EMAIL_RECEIVERS, list):
        msg["To"] = ", ".join(EMAIL_RECEIVERS)
    else:
        msg["To"] = EMAIL_RECEIVERS
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    auth_string = f"user={EMAIL_SENDER}\1auth=Bearer {access_token}\1\1"
    auth_string = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.docmd("AUTH", "XOAUTH2 " + auth_string)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVERS if isinstance(EMAIL_RECEIVERS, list) else [EMAIL_RECEIVERS], msg.as_string())
        server.quit()
        print(f"✅ Email sent successfully to {msg['To']}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
