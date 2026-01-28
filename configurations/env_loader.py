import os
from typing import Dict, Any

# Optional: load .env when present for local development
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    _dotenv_path = find_dotenv(usecwd=True)
    if _dotenv_path:
        load_dotenv(_dotenv_path)
except Exception:
    # python-dotenv is optional in production; ignore if not installed
    pass


def _require_env(name: str) -> str:
    """
    Read a required environment variable. Raise a clear error if missing.
    """
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            "Provide it via local .env (not committed) or as a CI/CD secret."
        )
    return val


def load_env_credentials() -> Dict[str, Any]:
    """
    Build the credentials dict from environment variables (LEGAL_EAGLE_*).
    No secrets are read from files or databases.

    Required:
      - LEGAL_EAGLE_OPENAI_API_KEY
      - LEGAL_EAGLE_TWITTER_BEARER_TOKEN
      - LEGAL_EAGLE_GMAIL_EMAIL_SENDER
      - LEGAL_EAGLE_GMAIL_APP_PASSWORD

    Optional (for future Gmail OAuth flows; not needed by SMTP sender):
      - LEGAL_EAGLE_GMAIL_CLIENT_ID
      - LEGAL_EAGLE_GMAIL_CLIENT_SECRET
      - LEGAL_EAGLE_GMAIL_REFRESH_TOKEN
      - LEGAL_EAGLE_GMAIL_SCOPE
      - LEGAL_EAGLE_GMAIL_TOKEN_URI
    """
    # Required values
    openai_key = _require_env("LEGAL_EAGLE_OPENAI_API_KEY")
    twitter_bearer = _require_env("LEGAL_EAGLE_TWITTER_BEARER_TOKEN")
    gmail_sender = _require_env("LEGAL_EAGLE_GMAIL_EMAIL_SENDER")
    gmail_app_pw = _require_env("LEGAL_EAGLE_GMAIL_APP_PASSWORD")

    # Optional Gmail OAuth values
    env = os.environ
    gmail_client_id = env.get("LEGAL_EAGLE_GMAIL_CLIENT_ID")
    gmail_client_secret = env.get("LEGAL_EAGLE_GMAIL_CLIENT_SECRET")
    gmail_refresh_token = env.get("LEGAL_EAGLE_GMAIL_REFRESH_TOKEN")
    gmail_scope = env.get("LEGAL_EAGLE_GMAIL_SCOPE")
    gmail_token_uri = env.get("LEGAL_EAGLE_GMAIL_TOKEN_URI")

    return {
        "openai_api_key": openai_key,
        "gmail": {
            "email_sender": gmail_sender,
            "app_password": gmail_app_pw,
            "client_id": gmail_client_id,
            "client_secret": gmail_client_secret,
            "refresh_token": gmail_refresh_token,
            "scope": gmail_scope,
            "token_uri": gmail_token_uri,
        },
        "twitter": {
            "x_bearer_token": twitter_bearer
        }
    }
