"""
Google Calendar Authentication

OAuth 2.0 flow for the Calendar API.  Reuses the project-level credentials.json
(same OAuth app as Gmail + Drive) and persists tokens to config/calendar_token.json.

Usage:
    from src.calendar.calendar_auth import get_calendar_service
    service = get_calendar_service()
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger("calendar_agent.auth")

# Read + write scope (full calendar access).
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _resolve_paths() -> tuple[str, str]:
    """Resolve credential paths from config/settings.json, with sensible defaults."""
    try:
        from src.agent.llm.provider_registry import get_google_credential_path
        oauth = get_google_credential_path("oauth_credentials_path") or "config/credentials.json"
        token = get_google_credential_path("calendar_token_path") or "config/calendar_token.json"
        return oauth, token
    except Exception:
        return "config/credentials.json", "config/calendar_token.json"


def get_calendar_service():
    """
    Authenticate and return a Google Calendar API v3 service object.

    Token is cached in config/calendar_token.json.  If missing or expired,
    the function automatically opens a browser OAuth flow.

    Returns:
        googleapiclient.discovery.Resource (calendar v3)

    Raises:
        FileNotFoundError: If credentials.json is missing.
        Exception: If the OAuth flow itself fails.
    """
    credentials_path, token_path = _resolve_paths()
    token_file = Path(token_path)
    creds: Credentials | None = None

    # ── Load cached token ────────────────────────────────────────────────────
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(token_file.read_text(encoding="utf-8")), SCOPES
            )
        except Exception as exc:
            logger.warning("[calendar_auth] Could not load cached token: %s", exc)
            creds = None

    # ── Refresh or full OAuth flow ───────────────────────────────────────────
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("[calendar_auth] Token refreshed successfully.")
            except Exception as exc:
                logger.warning("[calendar_auth] Token refresh failed (%s) — re-authorising.", exc)
                token_file.unlink(missing_ok=True)
                creds = None

        if not creds or not creds.valid:
            cred_file = Path(credentials_path)
            if not cred_file.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at '{credentials_path}'. "
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("[calendar_auth] New Calendar OAuth token created.")

        # Persist token
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


def is_calendar_authorized() -> bool:
    """Return True if a valid-looking calendar token exists on disk (no API call)."""
    _, token_path = _resolve_paths()
    return Path(token_path).exists()
