"""
SAP BTP Alert Notification Service (ANS) email sender.

Used on BTP when VCAP_SERVICES contains an ANS service binding.
Falls back gracefully to None when no binding is present (local dev).

Subscriptions and Actions are configured once manually in the ANS cockpit.
This module only fires producer events; ANS routes them to all subscribed recipients.
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Optional

import requests


def _get_ans_credentials() -> Optional[dict]:
    """
    Extract ANS credentials from VCAP_SERVICES.
    Tries managed 'alert-notification' binding first, then user-provided.
    Returns None when no binding is found.
    """
    vcap_raw = os.environ.get("VCAP_SERVICES", "")
    if not vcap_raw:
        return None
    try:
        vcap = json.loads(vcap_raw)
    except Exception:
        return None

    for entry in vcap.get("alert-notification", []):
        creds = entry.get("credentials", {})
        if creds.get("url") and creds.get("client_id"):
            return creds

    for entry in vcap.get("user-provided", []):
        c = entry.get("credentials", {})
        if c.get("url") and c.get("client_id"):
            return c

    return None


class ANSSender:
    """
    Thin REST client for SAP BTP Alert Notification Service.
    Handles OAuth2 token caching (same pattern as SAPAICoreClient).
    """

    def __init__(self, url: str, oauth_url: str, client_id: str, client_secret: str):
        self._url = url.rstrip("/")
        self._oauth_url = oauth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def _get_token(self) -> str:
        if self._token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at - timedelta(minutes=5):
                return self._token
        resp = requests.post(
            self._oauth_url,
            data={"client_id": self._client_id, "client_secret": self._client_secret},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = datetime.utcnow() + timedelta(
            seconds=data.get("expires_in", 3600)
        )
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def send_event(
        self,
        profile_slug: str,
        subject: str,
        body_html: str,
    ) -> None:
        """
        Fire one resource-event per digest run.
        The manually-configured subscription (no conditions) routes it to all recipients.
        """
        resp = requests.post(
            f"{self._url}/cf/producer/v1/resource-events",
            headers=self._headers(),
            json={
                "subject": subject,
                "eventType": "LegalEagleDigest",
                "severity": "INFO",
                "category": "NOTIFICATION",
                "resource": {
                    "resourceName": "legal-eagle",
                    "resourceType": "Application",
                    "resourceInstance": os.environ.get("CF_INSTANCE_INDEX", "0"),
                    "tags": {"profile": profile_slug},
                },
                "tags": {"body": body_html},
            },
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(
                f"ANS sendEvent -> {resp.status_code}: {resp.text[:400]}"
            )


# Module-level singleton, initialised once on first use
_ans_sender: Optional[ANSSender] = None
_ans_checked = False


def get_ans_sender() -> Optional[ANSSender]:
    """
    Returns a ready ANSSender if ANS is bound, else None.
    Result is cached - safe to call repeatedly.
    """
    global _ans_sender, _ans_checked
    if _ans_checked:
        return _ans_sender
    _ans_checked = True
    creds = _get_ans_credentials()
    if not creds:
        return None
    oauth_url = creds.get("oauth_url") or creds.get("oauth_token_url")
    if not oauth_url:
        return None
    _ans_sender = ANSSender(
        url=creds["url"],
        oauth_url=oauth_url,
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
    )
    return _ans_sender


def send_digest_via_ans(
    profile_slug: str,
    subject: str,
    body_html: str,
    recipient_emails: List[str],
) -> bool:
    """
    Send digest via ANS (one event per run).
    The manually-configured subscription routes the event to all recipients.
    Returns True on success, False if ANS unavailable or send failed.
    Caller falls back to Gmail SMTP on False.
    """
    sender = get_ans_sender()
    if not sender:
        return False

    try:
        sender.send_event(profile_slug, subject, body_html)
        print(f"[ANS] Digest sent ({len(recipient_emails)} recipient(s) via subscription)")
        return True
    except Exception as e:
        print(f"[ANS] Send failed: {e}")
        return False
