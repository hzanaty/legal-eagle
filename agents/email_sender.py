import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

# ---------------------------------------------------------------------
# 🦅 Email Sender using Gmail App Password
# ---------------------------------------------------------------------

def normalize_group_for_email(group: dict) -> tuple[str, str]:
    """
    Ensures clean (title, summary) strings for each group.
    Handles both string and JSON-like summaries returned by the LLM.
    """
    title = group.get("title") or "Untitled Group"
    summary = group.get("summary", "")

    if isinstance(summary, dict):
        summary = summary.get("summary", "")

    elif isinstance(summary, str) and summary.strip().startswith("{"):
        try:
            parsed = json.loads(summary)
            title = parsed.get("title", title)
            summary = parsed.get("summary", summary)
        except Exception:
            pass

    return str(title), str(summary)


def build_email_body(grouped_summary: list[dict]) -> str:
    """
    Builds an HTML email body from grouped news items.
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

        html.append(f"<h3>📚 {title} ({category}, {size} items)</h3>")
        html.append(f"<p><b>Summary:</b> {summary}</p>")
        html.append("<ul>")
        for link, item_title in zip(group.get("links", []), group.get("titles", [])):
            safe_title = item_title or "Source"
            html.append(f"<li><a href='{link}'>{safe_title}</a></li>")
        html.append("</ul><hr>")

    html.append(
        "<div style='color:#666;font-size:12px;margin-top:16px;'>"
        "Legal Eagle — Automated Compliance Insights by LPMx"
        "</div>"
    )
    return "\n".join(html)


def send_email(grouped_summary: list[dict], EMAIL_RECEIVERS, GMAIL_CREDS: dict) -> None:
    """
    Sends the Legal Eagle digest email using Gmail App Password authentication.
      - grouped_summary: output of grouping agent
      - EMAIL_RECEIVERS: list or single email
      - GMAIL_CREDS: dict containing 'email_sender' and 'app_password'
    """
    EMAIL_SENDER = GMAIL_CREDS["email_sender"]
    APP_PASSWORD = GMAIL_CREDS["app_password"]

    subject = f"🦅 Legal Eagle Daily Digest — {datetime.now().strftime('%Y-%m-%d')}"
    body = build_email_body(grouped_summary)

    # Prepare MIME message
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

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.starttls()
        server.login(EMAIL_SENDER, APP_PASSWORD)  # ✅ App password here
        server.sendmail(EMAIL_SENDER, rcpt_list, msg.as_string())
        server.quit()
        print(f"✅ Email sent successfully to {msg['To']}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
