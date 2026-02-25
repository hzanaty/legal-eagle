import smtplib
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
import openai


# ---------------------------------------------------------------------
# 🦅  Email Sender using Gmail App Password + RTL & Category Logic
# ---------------------------------------------------------------------

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
        client = openai.OpenAI(api_key=openai_api_key)
        
        for group in grouped_summary:
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


def send_email(
    grouped_summary: List[Dict[str, Any]], 
    receivers_with_lang: List[Dict[str, str]], 
    GMAIL_CREDS: dict, 
    profile_lang: str,
    country: str,
    lob: str,
    openai_api_key: str,
    monitor_updates: dict = None
) -> bool:
    """
    Sends the Legal Eagle digest email with per-receiver translation support.
    
    Args:
        grouped_summary: List of grouped news items (in profile language)
        receivers_with_lang: List of dicts with {"email": str, "translation_lang": str}
        GMAIL_CREDS: Gmail credentials dict
        profile_lang: Profile's analysis language (source language)
        country: Country code for subject line (e.g., 'SA')
        lob: Line of Business for subject line (e.g., 'HCM')
        openai_api_key: OpenAI API key for translation
        monitor_updates: Optional monitor updates data from Law-to-Specification
    
    Returns:
        True on success, False on failure (after retries).
    """
    EMAIL_SENDER = GMAIL_CREDS["email_sender"]
    APP_PASSWORD = GMAIL_CREDS["app_password"]
    
    # Handle backward compatibility: if receivers_with_lang is a simple list of strings
    if receivers_with_lang and isinstance(receivers_with_lang[0], str):
        receivers_with_lang = [{"email": email, "translation_lang": profile_lang} for email in receivers_with_lang]
    
    # Group receivers by translation language
    lang_groups = {}
    for receiver in receivers_with_lang:
        email = receiver["email"]
        trans_lang = receiver.get("translation_lang") or profile_lang
        lang_groups.setdefault(trans_lang, []).append(email)
    
    print(f"\n📧 Sending emails to {len(receivers_with_lang)} receiver(s) in {len(lang_groups)} language(s)")
    
    overall_success = True
    translation_cache = {}  # Cache translations to avoid re-translating for multiple receivers
    
    # Send to each language group
    for target_lang, emails in lang_groups.items():
        print(f"\n   Language: {target_lang} → {len(emails)} receiver(s)")
        
        # Translate if needed (with caching)
        if target_lang not in translation_cache:
            if target_lang == profile_lang:
                translation_cache[target_lang] = grouped_summary
            else:
                translation_cache[target_lang] = translate_grouped_summary(
                    grouped_summary, profile_lang, target_lang, openai_api_key
                )
        
        translated_summary = translation_cache[target_lang]
        
        # Build email with profile in subject
        today = datetime.now().strftime('%Y-%m-%d')
        subject = f"🦅 Legal Eagle Daily Digest — {country}/{lob} — {today}"
        body = build_email_body(translated_summary, target_lang, monitor_updates)
        
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = ", ".join(emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        
        # Send with retries
        sent = False
        for attempt in range(1, 3):
            # First try STARTTLS on port 587
            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=120) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(EMAIL_SENDER, APP_PASSWORD)
                    server.sendmail(EMAIL_SENDER, emails, msg.as_string())
                print(f"   ✅ Email sent successfully via STARTTLS to {', '.join(emails)}")
                sent = True
                break
            except Exception as e1:
                print(f"   ❌ STARTTLS send failed (attempt {attempt}/2): {e1}")
                # Fallback to SSL on port 465
                try:
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=120) as server:
                        server.login(EMAIL_SENDER, APP_PASSWORD)
                        server.sendmail(EMAIL_SENDER, emails, msg.as_string())
                    print(f"   ✅ Email sent successfully via SSL to {', '.join(emails)}")
                    sent = True
                    break
                except Exception as e2:
                    print(f"   ❌ SSL send failed (attempt {attempt}/2): {e2}")
        
        if not sent:
            overall_success = False
            print(f"   ❌ Failed to send to {', '.join(emails)} after retries")
    
    return overall_success
