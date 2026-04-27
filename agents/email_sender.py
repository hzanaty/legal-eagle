import smtplib
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from agents.sap_ai_client import SAPAICoreClient
from configurations.config_loader import creds

# Flag-inspired colours per country (bilingual card top half).
COUNTRY_COLORS = {
    "SA": {"border": "#006c35", "bg": "#f0faf4"},
    "AE": {"border": "#006c35", "bg": "#f0faf4"},
    "KW": {"border": "#007a3d", "bg": "#f0faf4"},
    "TR": {"border": "#e30a17", "bg": "#fff5f5"},
    "ES": {"border": "#c60b1e", "bg": "#fff5f5"},
    "MA": {"border": "#c1272d", "bg": "#fff5f5"},
    "EG": {"border": "#ce1126", "bg": "#fff5f5"},
    "DE": {"border": "#1a1a1a", "bg": "#f7f7f7"},
    "FR": {"border": "#002395", "bg": "#f0f4ff"},
    "GB": {"border": "#012169", "bg": "#f0f4ff"},
    "IN": {"border": "#FF9933", "bg": "#fff8f0"},
    "CN": {"border": "#DE2910", "bg": "#fff5f5"},
    "JP": {"border": "#bc002d", "bg": "#fff5f5"},
}
COUNTRY_COLOR_DEFAULT = {"border": "#4a90d9", "bg": "#f0f7ff"}
LANG_BADGES = {
    "en": "EN", "ar": "AR", "tr": "TR", "es": "ES",
    "de": "DE", "fr": "FR", "it": "IT", "pt": "PT",
    "zh": "ZH", "ja": "JA", "ko": "KO", "hi": "HI",
    "ru": "RU", "nl": "NL", "pl": "PL",
}



# ---------------------------------------------------------------------
# 🦅  Email Sender using Gmail App Password + RTL & Category Logic
# ---------------------------------------------------------------------

def _get_ai_client():
    """Get SAP AI Core client from credentials."""
    sap_cfg = creds.get("sap_aicore", {})
    return SAPAICoreClient(
        base_url=sap_cfg["base_url"],
        auth_url=sap_cfg["auth_url"],
        client_id=sap_cfg["client_id"],
        client_secret=sap_cfg["client_secret"],
        chat_deployment_id=sap_cfg["chat_deployment_id"],
        embeddings_deployment_id=sap_cfg["embeddings_deployment_id"]
    )


def translate_grouped_summary(grouped_summary: List[Dict[str, Any]], from_lang: str, to_lang: str, openai_api_key: str) -> List[Dict[str, Any]]:
    """
    Translate grouped summary items from one language to another using OpenAI GPT.
    Returns a translated copy of the grouped_summary.
    
    Args:
        grouped_summary: List of grouped news items
        from_lang: Source language code (e.g., 'ar', 'es', 'en')
        to_lang: Target language code (e.g., 'en', 'ar', 'es')
        openai_api_key: OpenAI API key for translation
    
    Returns:
        Translated copy of grouped_summary
    """
    # No translation needed if languages match
    if from_lang == to_lang:
        return grouped_summary
    
    # Map language codes to full names for better GPT understanding
    lang_names = {
        "en": "English", "ar": "Arabic", "es": "Spanish", "de": "German",
        "fr": "French", "it": "Italian", "pt": "Portuguese", "zh": "Chinese",
        "ja": "Japanese", "ko": "Korean", "hi": "Hindi", "ru": "Russian"
    }
    
    from_lang_name = lang_names.get(from_lang, from_lang)
    to_lang_name = lang_names.get(to_lang, to_lang)
    
    print(f"🌐 Translating summary from {from_lang_name} to {to_lang_name}...")
    
    translated_summary = []
    
    try:
        client = _get_ai_client()
        
        for _idx, group in enumerate(grouped_summary):
            # Extract fields to translate
            title = group.get("title", "")
            summary = group.get("summary", "")
            
            # Handle dict summary format
            if isinstance(summary, dict):
                summary = summary.get("summary", "")
            
            # Prepare translation prompt
            prompt = f"""Translate the following legal news summary from {from_lang_name} to {to_lang_name}. 
Maintain the professional tone and legal terminology accuracy.

Title: {title}

Summary: {summary}

Provide the translation in this exact JSON format:
{{
    "translated_title": "...",
    "translated_summary": "..."
}}"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"You are a professional legal translator specializing in {from_lang_name} to {to_lang_name} translation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            # Parse translation response
            translation_text = response.choices[0].message.content.strip()
            
            # Try to extract JSON
            try:
                # Remove markdown code blocks if present
                if translation_text.startswith("```"):
                    translation_text = translation_text.split("```")[1]
                    if translation_text.startswith("json"):
                        translation_text = translation_text[4:]
                    translation_text = translation_text.strip()
                
                translation = json.loads(translation_text)
                translated_title = translation.get("translated_title", title)
                translated_summary_text = translation.get("translated_summary", summary)
            except json.JSONDecodeError:
                # Fallback: use original if parsing fails
                print(f"   ⚠️ Translation parse failed for: {title[:50]}...")
                translated_title = title
                translated_summary_text = summary
            
            # Create translated group (preserve all other fields)
            translated_group = group.copy()
            translated_group["title"] = translated_title
            translated_group["summary"] = translated_summary_text
            
            translated_summary.append(translated_group)
        
        print(f"✅ Translated {len(translated_summary)} group(s)")
        return translated_summary
        
    except Exception as e:
        print(f"❌ Translation failed: {e}")
        print("   Falling back to original language")
        return grouped_summary


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


def build_email_body(grouped_summary: list, lang: str, monitor_updates: dict = None, english_summary: list = None, country_code: str = "") -> str:
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
    is_bilingual = (lang != "en") and bool(english_summary)
    cs = COUNTRY_COLORS.get(country_code.upper(), COUNTRY_COLOR_DEFAULT)
    native_border = cs["border"]
    native_bg = cs["bg"]
    native_badge = LANG_BADGES.get(lang, lang.upper())
    en_map = {}
    if is_bilingual and english_summary:
        for _i, _g in enumerate(english_summary):
            en_map[_i] = _g

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

    for _idx, group in enumerate(grouped_summary):
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

        # Render group (bilingual or monolingual)
        if is_bilingual:
            _eg = en_map.get(_idx, group)
            _et, _es = normalize_group_for_email(_eg)
            _ed = _eg.get("delta") or []
            _elk = _eg.get("links", []) or []
            _elt = _eg.get("titles", []) or []
            if bool(_eg.get("is_update_section")) and _ed:
                _ec = "<ul>" + "".join("<li>" + d + "</li>" for d in _ed) + "</ul>"
            else:
                _ec = "<p>" + _es + "</p>"
            _ep = " ".join(
                "<a href=" + chr(39) + lk + chr(39) + ">" + (lb or "Src")[:60] + "</a>"
                for lk, lb in zip(_elk, _elt or _elk)
            )
            _dls = group.get("delta") or []
            if is_update and _dls:
                _nc = "<ul>" + "".join("<li>" + d + "</li>" for d in _dls) + "</ul>"
            else:
                _nc = "<p>" + summary + "</p>"
            html.append(
                "<table width=" + chr(39) + "100%" + chr(39) +
                " style=" + chr(39) + "margin-bottom:12px;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;" + chr(39) + ">"
                "<tr><td style=" + chr(39) + "padding:12px 16px 10px;background:" + native_bg + ";border-left:4px solid " + native_border + ";" + chr(39) + ">"
                "<small style=" + chr(39) + "font-weight:700;color:" + native_border + ";font-size:10px;" + chr(39) + ">" + native_badge + "</small>"
                "<p style=" + chr(39) + "margin:4px 0 0;font-size:14px;font-weight:700;color:#1a202c;" + chr(39) + ">" + title + "</p>"
                + _nc +
                "</td></tr>"
                "<tr><td style=" + chr(39) + "height:1px;background:#e2e8f0;padding:0;" + chr(39) + "></td></tr>"
                "<tr><td style=" + chr(39) + "padding:12px 16px 12px;background:#f9fafb;border-left:4px solid #9ca3af;" + chr(39) + ">"
                "<small style=" + chr(39) + "font-weight:700;color:#9ca3af;font-size:10px;" + chr(39) + ">EN</small>"
                "<p style=" + chr(39) + "margin:4px 0 0;font-size:14px;font-weight:700;color:#2b6cb0;" + chr(39) + ">" + _et + "</p>"
                + _ec + ("<p>" + _ep + "</p>" if _ep else "") +
                "</td></tr></table>"
            )
        else:
            # Monolingual card
            html.append("<p><b>📚 " + title + "</b></p>")
            if is_update:
                delta_lines = group.get("delta") or []
                if delta_lines:
                    html.append("<ul>")
                    for d in delta_lines:
                        html.append("<li>" + d + "</li>")
                    html.append("</ul>")
                else:
                    html.append("<p>" + summary + "</p>")
            else:
                html.append("<p>" + summary + "</p>")
            links = group.get("links", []) or []
            titles_g = group.get("titles", []) or []
            if links:
                html.append("<ul>")
                for link, item_title in zip(links, titles_g):
                    safe_title = item_title or "Source"
                    html.append("<li><a href=" + chr(39) + link + chr(39) + ">" + safe_title + "</a></li>")
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


def generate_email_html(
    grouped_summary: List[Dict[str, Any]],
    profile_lang: str,
    country: str,
    lob: str,
    monitor_updates: dict = None
) -> str:
    """
    Generate email HTML without sending (for test mode preview).
    
    Args:
        grouped_summary: List of grouped news items
        profile_lang: Profile's analysis language
        country: Country code
        lob: Line of Business
        monitor_updates: Optional monitor updates data
    
    Returns:
        HTML string of the email body
    """
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    subject = f"🦅 Legal Eagle Daily Digest — {country}/{lob} — {today}"
    body = build_email_body(grouped_summary, profile_lang, monitor_updates=monitor_updates, country_code=country)
    
    # Wrap in basic HTML email structure
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{subject}</title>
</head>
<body>
{body}
</body>
</html>"""
    return html


def send_email(
    grouped_summary: List[Dict[str, Any]],
    receivers_with_lang,
    GMAIL_CREDS: dict,
    profile_lang: str,
    country: str,
    lob: str,
    openai_api_key: str = "",
    monitor_updates: dict = None
) -> bool:
    """
    Send the daily digest email.

    Bilingual mode (profile_lang != en):
      Translates grouped_summary to English once, then builds ONE bilingual email
      body (native + English card per group) and sends it to ALL receivers together.

    Monolingual mode (profile_lang == en):
      Sends a standard single-language email to all receivers.
    """
    EMAIL_SENDER = GMAIL_CREDS["email_sender"]
    APP_PASSWORD = GMAIL_CREDS["app_password"]

    # Collect all recipient email addresses
    if receivers_with_lang and isinstance(receivers_with_lang[0], str):
        all_emails = list(receivers_with_lang)
    else:
        all_emails = [r["email"] for r in receivers_with_lang if r.get("email")]

    if not all_emails:
        print("No email receivers configured.")
        return False

    print(f"Preparing email for {len(all_emails)} receiver(s)...")

    # Translate to English for bilingual body (if needed)
    english_summary = None
    if profile_lang != "en" and grouped_summary:
        english_summary = translate_grouped_summary(
            grouped_summary, profile_lang, "en", openai_api_key
        )

    # Build ONE bilingual/monolingual body
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"Legal Eagle Daily Digest - {country}/{lob} - {today}"
    body = build_email_body(
        grouped_summary,
        profile_lang,
        monitor_updates=monitor_updates,
        english_summary=english_summary,
        country_code=country
    )

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(all_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    # Send with retries
    sent = False
    for attempt in range(1, 3):
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=120) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(EMAIL_SENDER, APP_PASSWORD)
                server.sendmail(EMAIL_SENDER, all_emails, msg.as_string())
            print(f"Email sent successfully via STARTTLS to {len(all_emails)} receiver(s)")
            sent = True
            break
        except Exception as e1:
            print(f"STARTTLS send failed (attempt {attempt}/2): {e1}")
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=120) as server:
                    server.login(EMAIL_SENDER, APP_PASSWORD)
                    server.sendmail(EMAIL_SENDER, all_emails, msg.as_string())
                print(f"Email sent successfully via SSL to {len(all_emails)} receiver(s)")
                sent = True
                break
            except Exception as e2:
                print(f"SSL send failed (attempt {attempt}/2): {e2}")

    if not sent:
        print(f"Failed to send email after retries")
    return sent
