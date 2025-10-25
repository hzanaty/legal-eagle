import smtplib
import base64
import requests
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Hardcoded sender address
EMAIL_SENDER = "hanyzanaty@gmail.com"


def get_gmail_access_token(gmail_creds: dict) -> str:
    """
    Exchanges the refresh token for a short-lived access token.
    gmail_creds must be a dict with: client_id, client_secret, refresh_token.
    """
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": gmail_creds["client_id"],
        "client_secret": gmail_creds["client_secret"],
        "refresh_token": gmail_creds["refresh_token"],
        "grant_type": "refresh_token",
    }
    response = requests.post(token_url, data=payload, timeout=30)
    if response.status_code == 200:
        return response.json()["access_token"]
    raise Exception(f"❌ Failed to refresh token: {response.text}")


def normalize_group_for_email(group: dict) -> tuple[str, str]:
    """
    Ensure we always have clean (title, summary) strings, even if the model
    returned JSON or a dict for summary.
    """
    title = group.get("title") or "Untitled Group"
    summary = group.get("summary", "")

    # If the summary is a dict (from JSON), extract "summary"
    if isinstance(summary, dict):
        summary = summary.get("summary", "")

    # If the summary looks like JSON text, try parsing and extracting
    elif isinstance(summary, str) and summary.strip().startswith("{"):
        try:
            parsed = json.loads(summary)
            title = parsed.get("title", title)
            summary = parsed.get("summary", summary)
        except Exception:
            pass  # keep original summary as-is

    return str(title), str(summary)


def build_email_body(grouped_summary: list[dict]) -> str:
    """
    Build a simple HTML email body from grouped news items.
    Expects each group to contain: title, summary, category, links, titles, group_size.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    html = [f"<h2>🦅 Legal Eagle Daily Digest — {today}</h2>"]

    if not grouped_summary:
        html.append("<p>No relevant updates found today.</p>")
        return "\n".join(html)

    for group in grouped_summary:
        title, summary = normalize_group_for_email(group)
        category = group.get("category", "Uncategorized")
        size = group.get("group_size", 0)

        # Section header
        html.append(f"<h3>📚 {title} ({category}, {size} items)</h3>")
        # Group summary
        html.append(f"<p><b>Summary:</b> {summary}</p>")

        # Sources list
        html.append("<ul>")
        links = group.get("links", [])
        item_titles = group.get("titles", [])
        for link, item_title in zip(links, item_titles):
            safe_title = item_title or "Source"
            html.append(f"<li><a href='{link}'>{safe_title}</a></li>")
        html.append("</ul>")
        html.append("<hr>")

    # Footer
    html.append(
        "<div style='color:#666;font-size:12px;margin-top:16px;'>"
        "Legal Eagle — Automated Compliance Insights by LPMx"
        "</div>"
    )
    return "\n".join(html)


def send_email(grouped_summary: list[dict], EMAIL_RECEIVERS, GMAIL_CREDS: dict) -> None:
    """
    Sends the digest email via Gmail SMTP using OAuth2.
      - grouped_summary: output list from the grouping agent
      - EMAIL_RECEIVERS: list[str] or str
      - GMAIL_CREDS: dict with client_id, client_secret, refresh_token
    """
    # 1) Build body early; if this raises, we fail fast before SMTP
    subject = f"🦅 Legal Eagle Daily Digest — {datetime.now().strftime('%Y-%m-%d')}"
    body = build_email_body(grouped_summary)

    # 2) Get access token
    access_token = get_gmail_access_token(GMAIL_CREDS)

    # 3) Compose MIME
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    if isinstance(EMAIL_RECEIVERS, list):
        msg["To"] = ", ".join(EMAIL_RECEIVERS)
        rcpt_list = EMAIL_RECEIVERS
    else:
        msg["To"] = EMAIL_RECEIVERS
        rcpt_list = [EMAIL_RECEIVERS]
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    # 4) XOAUTH2 auth string
    auth_string = f"user={EMAIL_SENDER}\1auth=Bearer {access_token}\1\1"
    auth_string = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    # 5) Send
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.starttls()
        server.docmd("AUTH", "XOAUTH2 " + auth_string)
        server.sendmail(EMAIL_SENDER, rcpt_list, msg.as_string())
        server.quit()
        print(f"✅ Email sent successfully to {msg['To']}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        raise
