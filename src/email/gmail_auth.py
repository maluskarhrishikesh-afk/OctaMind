"""
Gmail Authentication Module

This module handles all Gmail API authentication methods:
- Service Account (via GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CREDENTIALS_CONFIG)
- OAuth 2.0 (via credentials.json and token.json)
- Application Default Credentials (ADC)

Usage:
    from src.email.gmail_auth import get_gmail_service
    
    gmail_service = get_gmail_service()
"""

import os
import json
import base64
from pathlib import Path
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import google.auth

# Constants
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

def _resolve_google_paths():
    """Resolve credential file paths — config/credentials.json first, then defaults."""
    try:
        from src.agent.llm.provider_registry import get_google_credential_path
        oauth = get_google_credential_path("oauth_credentials_path") or "credentials.json"
        token = get_google_credential_path("gmail_token_path") or "token.json"
        return oauth, token
    except Exception:
        return "credentials.json", "token.json"

CREDENTIALS_PATH, TOKEN_PATH = _resolve_google_paths()
SERVICE_ACCOUNT_PATH = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
CREDENTIALS_CONFIG = os.getenv('GOOGLE_CREDENTIALS_CONFIG')


def get_gmail_service():
    """
    Authenticate and return Gmail service.

    Tries authentication methods in this order:
    1. Service Account (from environment variables)
    2. OAuth 2.0 (from credentials.json)
    3. Application Default Credentials (ADC)

    Returns:
        Gmail API service instance

    Raises:
        Exception: If all authentication methods fail
    """
    creds = None

    # Try service account from config
    if CREDENTIALS_CONFIG:
        try:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(base64.b64decode(CREDENTIALS_CONFIG)),
                scopes=SCOPES
            )
            print("Using service account from GOOGLE_CREDENTIALS_CONFIG")
        except Exception as e:
            print(f"Error with GOOGLE_CREDENTIALS_CONFIG: {e}")
            creds = None

    # Try service account from file
    if not creds and SERVICE_ACCOUNT_PATH and Path(SERVICE_ACCOUNT_PATH).exists():
        try:
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_PATH,
                scopes=SCOPES
            )
            print("Using service account from file")
        except Exception as e:
            print(f"Error using service account file: {e}")
            creds = None

    # Try OAuth 2.0
    if not creds:
        if Path(TOKEN_PATH).exists():
            try:
                with open(TOKEN_PATH, 'r') as token:
                    creds = Credentials.from_authorized_user_info(
                        json.load(token), SCOPES)
                print("Using OAuth 2.0 credentials")
            except Exception as e:
                print(f"Error loading token: {e}")
                creds = None

        if not creds or not creds.valid:
            # ── Step 1: try to refresh an expired token ─────────────────────
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, 'w') as token:
                        token.write(creds.to_json())
                    print("Refreshed OAuth 2.0 token")
                except Exception as e:
                    print(f"Refresh token expired or revoked ({e}). "
                          "Removing stale token and re-running OAuth flow...")
                    try:
                        Path(TOKEN_PATH).unlink(missing_ok=True)
                    except Exception:
                        pass
                    creds = None  # fall through to full OAuth flow below

            # ── Step 2: full OAuth flow (first-time or after refresh failure) ─
            if not creds or not creds.valid:
                try:
                    if not Path(CREDENTIALS_PATH).exists():
                        raise FileNotFoundError(
                            f"credentials.json not found at '{CREDENTIALS_PATH}'. "
                            "Download it from Google Cloud Console → APIs & Services → Credentials "
                            "and place it in the config/ folder."
                        )
                    print("Opening browser for Google authorization...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        CREDENTIALS_PATH, SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(TOKEN_PATH, 'w') as token:
                        token.write(creds.to_json())
                    print(f"Authorization complete. Token saved to {TOKEN_PATH}")
                except Exception as e:
                    print(f"OAuth flow failed: {e}")
                    raise Exception(
                        f"Gmail authorization failed: {e}\n"
                        "Run `python setup_google_auth.py` from the project root "
                        "to complete Google authorization."
                    )

    # Try Application Default Credentials (ADC)
    if not creds:
        try:
            creds, project = google.auth.default(scopes=SCOPES)
            print(
                f"Using Application Default Credentials (project: {project})")
        except Exception as e:
            print(f"ADC error: {e}")
            raise Exception(
                "Gmail authentication failed. No valid credentials found. "
                "Please run `python setup_google_auth.py` from the project root "
                "to authorise Gmail access."
            )

    return build('gmail', 'v1', credentials=creds)
