"""
Google Drive Authentication Module

Handles OAuth 2.0 authentication for the Drive API.
Reuses the project-level credentials.json, persists tokens to drive_token.json.

Usage:
    from src.drive.drive_auth import get_drive_service

    service = get_drive_service()
"""

import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Full Drive scope — read + write
SCOPES = ["https://www.googleapis.com/auth/drive"]

def _resolve_drive_paths():
    """Resolve credential file paths — config/credentials.json first, then defaults."""
    try:
        from src.agent.llm.provider_registry import get_google_credential_path
        oauth = get_google_credential_path("oauth_credentials_path") or "credentials.json"
        token = get_google_credential_path("drive_token_path") or "drive_token.json"
        return oauth, token
    except Exception:
        return "credentials.json", "drive_token.json"

CREDENTIALS_PATH, TOKEN_PATH = _resolve_drive_paths()


def get_drive_service():
    """
    Authenticate and return a Google Drive API service object.

    Uses drive_token.json for cached credentials (auto-created on first run).
    Falls back to OAuth browser flow if token is missing or expired.

    Returns:
        Google Drive API service (v3)

    Raises:
        Exception: If authentication fails and no fallback is available.
    """
    creds = None

    if Path(TOKEN_PATH).exists():
        try:
            with open(TOKEN_PATH, "r") as token:
                creds = Credentials.from_authorized_user_info(
                    json.load(token), SCOPES
                )
        except Exception as e:
            print(f"[drive_auth] Error loading drive_token.json: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("[drive_auth] Refreshed Drive OAuth token.")
            except Exception as e:
                print(f"[drive_auth] Token refresh failed: {e}")
                creds = None

        if not creds or not creds.valid:
            if not Path(CREDENTIALS_PATH).exists():
                raise FileNotFoundError(
                    f"credentials.json not found at '{CREDENTIALS_PATH}'. "
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
            print("[drive_auth] New Drive OAuth token created and saved.")

    return build("drive", "v3", credentials=creds)
