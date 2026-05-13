"""
SAP BTP Alert Notification Service (ANS) email sender.

Used on BTP when VCAP_SERVICES contains an ANS service binding.
Falls back gracefully to None when no binding is present (local dev).

Mirrors the RSS app reference implementation: provisions one
Action + Condition + Subscription per recipient (idempotent), then
sends one resource-event per recipient per digest run.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional

import requests


def _sanitize(s: str) -> str:
    """Produce a safe ANS entity name from an arbitrary string."""
    clean = re.sub(r"[^a-zA-Z0-9\-]", "-", s)
    if len(clean) <= 50:
        return clean
    h = hashlib.md5(s.encode()).hexdigest()[:8]
    return clean[:50] + "-" + h


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

    # Managed service binding (label: alert-notification)
    for entry in vcap.get("alert-notification", []):
        creds = entry.get("credentials", {})
        if creds.get("url") and creds.get("client_id"):
            return creds

    # User-provided service (e.g. cf cups legal-eagle-ans)
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
        # oauth_url already contains ?grant_type=client_credentials
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

    def ensure_provisioned(self, recipient_email: str) -> None:
        """
        Idempotently provision Action + Condition + Subscription for one recipient.
        Safe to call on every run — ANS treats duplicate names as updates.
        """
        sid = _sanitize(recipient_email)
        action = f"le-email-{sid}"
        cond = f"le-cond-{sid}"
        sub = f"le-sub-{sid}"
        payload = {
            "actions": [
                {
                    "name": action,
                    "type": "EMAIL",
                    "state": "ENABLED",
                    "description": f"Legal Eagle digest for {recipient_email}",
                    "properties": {"destination": recipient_email},
                }
            ],
            "conditions": [
                {
                    "name": cond,
                    "description": f"Match digests for {sid}",
                    "propertyKey": "subject",
                    "predicate": "CONTAINS",
                    "propertyValue": sid,
                }
            ],
            "subscriptions": [
                {
                    "name": sub,
                    "state": "ENABLED",
                    "actions": [action],
                    "conditions": [cond],
                }
            ],
        }
        resp = requests.put(
            f"{self._url}/cf/consumer/v1/configuration/import",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

    def send_event(
        self,
        recipient_email: str,
        profile_slug: str,
        subject: str,
        body_html: str,
    ) -> None:
        """
        Fire one resource-event for a single recipient.
        The condition on their subscription matches subject CONTAINS sid.
        """
        sid = _sanitize(recipient_email)
        resp = requests.post(
            f"{self._url}/cf/producer/v1/resource-events",
            headers=self._headers(),
            json={
                "subject": f"{subject} [{sid}]",
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
        resp.raise_for_status()


# Module-level singleton — initialised once on first use
_ans_sender: Optional[ANSSender] = None
_ans_checked = False


def get_ans_sender() -> Optional[ANSSender]:
    """
    Returns a ready ANSSender if ANS is bound, else None.
    Result is cached — safe to call repeatedly.
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
    Send digest to all recipients via ANS.
    Returns True if all sends succeeded, False if ANS is unavailable or any send failed.
    Caller should fall back to Gmail SMTP on False.
    """
    sender = get_ans_sender()
    if not sender:
        return False

    success = True
    for email in recipient_emails:
        try:
            sender.ensure_provisioned(email)
            sender.send_event(email, profile_slug, subject, body_html)
            print(f"[ANS] Digest sent to {email}")
        except Exception as e:
            print(f"[ANS] Send failed for {email}: {e}")
            success = False
    return success
