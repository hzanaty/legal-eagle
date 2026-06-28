# ANS code disabled — re-enable when BTP service binding is restored.
# To re-enable: uncomment everything below and remove the stub get_ans_sender() at the bottom.
#
# from typing import List, Optional
#
# """
# SAP BTP Alert Notification Service (ANS) email sender.
#
# Used on BTP when VCAP_SERVICES contains an ANS service binding.
# Falls back gracefully to None when no binding is present (local dev).
#
# Provisions one Action + Condition + Subscription per recipient (idempotent),
# then sends one resource-event per recipient per digest run.
# """
#
# import hashlib
# import json
# import os
# import re
# from datetime import datetime, timedelta
# from typing import List, Optional
#
# import requests
#
#
# def _sanitize(s: str) -> str:
#     clean = re.sub(r"[^a-zA-Z0-9\-]", "-", s)
#     if len(clean) <= 50:
#         return clean
#     h = hashlib.md5(s.encode()).hexdigest()[:8]
#     return clean[:41] + "-" + h
#
#
# def _get_ans_credentials() -> Optional[dict]:
#     """
#     Extract ANS credentials from VCAP_SERVICES.
#     Tries managed 'alert-notification' binding first, then user-provided.
#     Returns None when no binding is found.
#     """
#     vcap_raw = os.environ.get("VCAP_SERVICES", "")
#     if not vcap_raw:
#         return None
#     try:
#         vcap = json.loads(vcap_raw)
#     except Exception:
#         return None
#
#     for entry in vcap.get("alert-notification", []):
#         creds = entry.get("credentials", {})
#         if creds.get("url") and creds.get("client_id"):
#             return creds
#
#     for entry in vcap.get("user-provided", []):
#         c = entry.get("credentials", {})
#         if c.get("url") and c.get("client_id"):
#             return c
#
#     return None
#
#
# class ANSSender:
#     """
#     Thin REST client for SAP BTP Alert Notification Service.
#     Handles OAuth2 token caching (same pattern as SAPAICoreClient).
#     """
#
#     def __init__(self, url: str, oauth_url: str, client_id: str, client_secret: str):
#         self._url = url.rstrip("/")
#         self._oauth_url = oauth_url
#         self._client_id = client_id
#         self._client_secret = client_secret
#         self._token: Optional[str] = None
#         self._token_expires_at: Optional[datetime] = None
#
#     def _get_token(self) -> str:
#         if self._token and self._token_expires_at:
#             if datetime.utcnow() < self._token_expires_at - timedelta(minutes=5):
#                 return self._token
#         resp = requests.post(
#             self._oauth_url,
#             auth=(self._client_id, self._client_secret),
#             data={"grant_type": "client_credentials"},
#             timeout=30,
#         )
#         print("[ANS] Token request to:", self._oauth_url)
#         print("[ANS] Token status:", resp.status_code)
#         if not resp.ok:
#             print("[ANS] Token error:", resp.text[:300])
#         resp.raise_for_status()
#         data = resp.json()
#         self._token = data["access_token"]
#         self._token_expires_at = datetime.utcnow() + timedelta(
#             seconds=data.get("expires_in", 3600)
#         )
#         return self._token
#
#     def _headers(self) -> dict:
#         return {
#             "Authorization": f"Bearer {self._get_token()}",
#             "Content-Type": "application/json",
#         }
#
#     def _upsert_action(self, sid: str, recipient_email: str) -> None:
#         name = "le-email-" + sid
#         url = self._url + "/cf/consumer/v1/actions"
#         print("[ANS] POST action URL:", url)
#         resp = requests.post(
#             url,
#             headers=self._headers(),
#             json={
#                 "name": name,
#                 "type": "EMAIL",
#                 "state": "ENABLED",
#                 "description": "Legal Eagle digest for " + recipient_email,
#                 "properties": {"destination": recipient_email},
#             },
#             timeout=30,
#         )
#         print("[ANS] Action status:", resp.status_code, resp.text[:200])
#         if resp.status_code == 409:
#             return
#         if not resp.ok:
#             raise RuntimeError("ANS action -> " + str(resp.status_code) + ": " + resp.text[:400])
#
#     def _upsert_condition(self, sid: str) -> None:
#         name = "le-cond-" + sid
#         resp = requests.post(
#             self._url + "/cf/consumer/v1/conditions",
#             headers=self._headers(),
#             json={
#                 "name": name,
#                 "description": "Match digests for " + sid,
#                 "propertyKey": "subject",
#                 "predicate": "CONTAINS",
#                 "propertyValue": sid,
#             },
#             timeout=30,
#         )
#         if resp.status_code == 409:
#             return
#         if not resp.ok:
#             raise RuntimeError("ANS condition -> " + str(resp.status_code) + ": " + resp.text[:400])
#
#     def _upsert_subscription(self, sid: str) -> None:
#         name = "le-sub-" + sid
#         resp = requests.post(
#             self._url + "/cf/consumer/v1/subscriptions",
#             headers=self._headers(),
#             json={
#                 "name": name,
#                 "state": "ENABLED",
#                 "actions": ["le-email-" + sid],
#                 "conditions": ["le-cond-" + sid],
#             },
#             timeout=30,
#         )
#         if resp.status_code == 409:
#             return
#         if not resp.ok:
#             raise RuntimeError("ANS subscription -> " + str(resp.status_code) + ": " + resp.text[:400])
#
#     def ensure_provisioned(self, recipient_email: str) -> None:
#         """Idempotently provision Action + Condition + Subscription for one recipient."""
#         sid = _sanitize(recipient_email)
#         self._upsert_action(sid, recipient_email)
#         self._upsert_condition(sid)
#         self._upsert_subscription(sid)
#
#     def send_event(
#         self,
#         recipient_email: str,
#         profile_slug: str,
#         subject: str,
#         body_html: str,
#     ) -> None:
#         """
#         Fire one resource-event for a single recipient.
#         The condition on their subscription matches subject CONTAINS sid.
#         """
#         sid = _sanitize(recipient_email)
#         resp = requests.post(
#             self._url + "/cf/producer/v1/resource-events",
#             headers=self._headers(),
#             json={
#                 "subject": subject + " [" + sid + "]",
#                 "eventType": "LegalEagleDigest",
#                 "severity": "INFO",
#                 "category": "NOTIFICATION",
#                 "resource": {
#                     "resourceName": "legal-eagle",
#                     "resourceType": "Application",
#                     "resourceInstance": os.environ.get("CF_INSTANCE_INDEX", "0"),
#                     "tags": {"profile": profile_slug},
#                 },
#                 "tags": {"body": body_html},
#             },
#             timeout=30,
#         )
#         if not resp.ok:
#             raise RuntimeError(
#                 "ANS sendEvent -> " + str(resp.status_code) + ": " + resp.text[:400]
#             )
#
#
# # Module-level singleton, initialised once on first use
# _ans_sender: Optional[ANSSender] = None
# _ans_checked = False
#
#
# def get_ans_sender() -> Optional[ANSSender]:
#     """
#     Returns a ready ANSSender if ANS is bound, else None.
#     Result is cached - safe to call repeatedly.
#     """
#     global _ans_sender, _ans_checked
#     if _ans_checked:
#         return _ans_sender
#     _ans_checked = True
#     creds = _get_ans_credentials()
#     if not creds:
#         return None
#     oauth_url = creds.get("oauth_url") or creds.get("oauth_token_url")
#     if not oauth_url:
#         return None
#     _ans_sender = ANSSender(
#         url=creds["url"],
#         oauth_url=oauth_url,
#         client_id=creds["client_id"],
#         client_secret=creds["client_secret"],
#     )
#     return _ans_sender
#
#
# def send_digest_via_ans(
#     profile_slug: str,
#     subject: str,
#     body_html: str,
#     recipient_emails: List[str],
# ) -> bool:
#     """
#     Send digest to all recipients via ANS.
#     Provisions Action+Condition+Subscription per recipient (idempotent),
#     then fires one event per recipient so ANS routes it to that recipient only.
#     Returns True if all sends succeeded, False if ANS unavailable or any send failed.
#     Caller falls back to Gmail SMTP on False.
#     """
#     sender = get_ans_sender()
#     if not sender:
#         return False
#
#     success = True
#     for email in recipient_emails:
#         try:
#             sender.ensure_provisioned(email)
#             sender.send_event(email, profile_slug, subject, body_html)
#             print("[ANS] Digest sent to " + email)
#         except Exception as e:
#             print("[ANS] Send failed for " + email + ": " + str(e))
#             success = False
#     return success


# Stub — always returns None while ANS is disabled.
# Re-enable by restoring the full implementation above.
from typing import Optional


def get_ans_sender() -> Optional[object]:
    return None


def send_digest_via_ans(*args, **kwargs) -> bool:
    return False
