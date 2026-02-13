import smtplib
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ---------------------------------------------------------------------
# 🦅  Email Sender using Gmail App Password + RTL & Category Logic
# ---------------------------------------------------------------------

def normalize_group_for_email(group: dict) -> tuple[str, str]:
    """Ensure clean (title, summary) strings for each group."""
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


def build_email_body(grouped_summary: list[dict], lang: str, monitor_updates: dict = None) -> str:
    """
    Builds an HTML email body for grouped news items.
    Per category (HCM/FIN/Other), shows two sections when present:
      - New
      - Updates (with delta bullets)
    Supports RTL languages and avoids redundant labels.
    
    Args:
        grouped_summary: List of grouped news items
        lang: Language code
        monitor_updates: Optional dict with monitor update data from Law-to-Specification emails
    """
    today = datetime.now().strftime("%Y-%m-%d")

    rtl_langs = ["ar", "he", "fa", "ur"]
    direction = "rtl" if lang in rtl_langs else "ltr"
    align = "right" if direction == "rtl" else "left"

    html = [
        f"<div dir='{direction}' style='text-align:{align}; font-family:Arial, sans-serif;'>",
        f"<h2>🦅 Legal Eagle Daily Digest — {today}</h2>"
    ]

    if not grouped_summary:
        html.append(
            "<p>لا توجد تحديثات ذات صلة اليوم.</p>"
            if lang == "ar"
            else "<p>No relevant updates found today.</p>"
        )
        # Don't return early - we still need to add monitor updates section below
    
    last_category = None
    printed_new = False
    printed_updates = False

    for group in grouped_summary:
        title, summary = normalize_group_for_email(group)
        category = group.get("category", "Uncategorized")
        is_update = bool(group.get("is_update_section"))

        # Category header only once per category
        if category != last_category:
            if category == "HCM":
                html.append("<h3>📚 تحديثات الموارد البشرية (HCM)</h3>" if lang == "ar" else "<h3>📚 HCM Updates</h3>")
            elif category == "FIN":
                html.append("<h3>💰 تحديثات المالية (FIN)</h3>" if lang == "ar" else "<h3>💰 FIN Updates</h3>")
            else:
                html.append("<h3>🗞️ مواضيع أخرى</h3>" if lang == "ar" else "<h3>🗞️ Other Topics</h3>")
            last_category = category
            printed_new = False
            printed_updates = False

        # Subsection headers within category
        if not is_update and not printed_new:
            html.append("<h4>🆕 جديدة</h4>" if lang == "ar" else "<h4>🆕 New</h4>")
            printed_new = True
        if is_update and not printed_updates:
            html.append("<h4>♻️ تحديثات</h4>" if lang == "ar" else "<h4>♻️ Updates</h4>")
            printed_updates = True

        # Render group
        html.append(f"<p><b>📚 {title}</b></p>")

        if is_update:
            # Prefer delta bullets if available; otherwise show summary as plain text
            delta_lines = group.get("delta") or []
            if delta_lines:
                html.append("<ul>")
                for d in delta_lines:
                    html.append(f"<li>{d}</li>")
                html.append("</ul>")
            else:
                html.append(f"<p>{summary}</p>")
        else:
            html.append(f"<p>{summary}</p>")

        # Links
        links = group.get('links', []) or []
        titles = group.get('titles', []) or []
        if links:
            html.append("<ul>")
            for link, item_title in zip(links, titles):
                safe_title = item_title or "Source"
                html.append(f"<li><a href='{link}'>{safe_title}</a></li>")
            html.append("</ul>")

    # Monitor Updates Section (Law-to-Specification email integration)
    if monitor_updates is not None:
        html.append("<hr style='margin:32px 0;'>")
        html.append("<h3>🔍 تنبيهات تغييرات المواقع (Law-to-Spec)</h3>" if lang == "ar" else "<h3>🔍 Website Change Alerts (Law-to-Spec)</h3>")
        
        if monitor_updates.get('changes'):
            # Show report date if available
            if monitor_updates.get('report_date'):
                html.append(f"<p><b>📅 تقرير:</b> {monitor_updates['report_date']}</p>" if lang == "ar" else f"<p><b>📅 Report:</b> {monitor_updates['report_date']}</p>")
            
            # Show monitored URLs
            if monitor_updates.get('monitored_urls'):
                urls = monitor_updates['monitored_urls']
                for url in urls:
                    # Extract domain for display
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                    html.append(f"<p><b>🔗 المصدر:</b> {domain}</p>" if lang == "ar" else f"<p><b>🔗 Source:</b> {domain}</p>")
            
            # Show changes
            html.append("<p><b>تغييرات مكتشفة:</b></p>" if lang == "ar" else "<p><b>Changes detected:</b></p>")
            html.append("<ul>")
            for change in monitor_updates['changes']:
                html.append(f"<li>{change}</li>")
            html.append("</ul>")
        else:
            # No updates found
            html.append("<p>لم يتم الكشف عن تغييرات في المواقع منذ آخر تقرير.</p>" if lang == "ar" else "<p>No website changes detected since last report.</p>")
    
    html.append(
        "<hr><div style='color:#666;font-size:12px;margin-top:16px;'>"
        "Legal Eagle — Automated Compliance Insights by LPMx"
        "</div></div>"
    )
    return "\n".join(html)


def send_email(grouped_summary: list[dict], EMAIL_RECEIVERS, GMAIL_CREDS: dict, lang: str, monitor_updates: dict = None) -> bool:
    """
    Sends the Legal Eagle digest email using Gmail App Password authentication.
    
    Args:
        grouped_summary: List of grouped news items
        EMAIL_RECEIVERS: List of email addresses or single email
        GMAIL_CREDS: Gmail credentials dict
        lang: Language code
        monitor_updates: Optional monitor updates data from Law-to-Specification
    
    Returns:
      True on success, False on failure (after retries).
    """
    EMAIL_SENDER = GMAIL_CREDS["email_sender"]
    APP_PASSWORD = GMAIL_CREDS["app_password"]

    subject = f"🦅 Legal Eagle Daily Digest — {datetime.now().strftime('%Y-%m-%d')}"
    body = build_email_body(grouped_summary, lang, monitor_updates)

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

    # Retry up to 2 times to mitigate transient network issues/timeouts
    for attempt in range(1, 3):
        # First try STARTTLS on port 587
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=120) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(EMAIL_SENDER, APP_PASSWORD)
                server.sendmail(EMAIL_SENDER, rcpt_list, msg.as_string())
            print(f"✅ Email sent successfully via STARTTLS to {msg['To']}")
            return True
        except Exception as e1:
            print(f"❌ STARTTLS send failed (attempt {attempt}/2): {e1}")
            # Fallback to SSL on port 465
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=120) as server:
                    server.login(EMAIL_SENDER, APP_PASSWORD)
                    server.sendmail(EMAIL_SENDER, rcpt_list, msg.as_string())
                print(f"✅ Email sent successfully via SSL to {msg['To']}")
                return True
            except Exception as e2:
                print(f"❌ SSL send failed (attempt {attempt}/2): {e2}")
                if attempt >= 2:
                    return False
    return False
