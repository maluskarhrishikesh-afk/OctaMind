"""
Google OAuth Re-Authorization Script
=====================================
Run this script interactively whenever your Gmail or Drive token expires:

    python setup_google_auth.py

What it does:
  1. Opens a browser window for Google sign-in
  2. Saves fresh tokens to config/token.json and config/drive_token.json
  3. Future PA email/drive queries will work without re-running this script
     (tokens are refreshed automatically — until the app is in Testing mode
     and 7 days pass again, at which point just re-run this script).

Note: To avoid the 7-day refresh-token expiry add your Google account as a
"Test User" in the Google Cloud Console → APIs & Services → OAuth consent screen,
or publish the app (marks it as verified).
"""
import json
import sys
from pathlib import Path

# ── Resolve project root ─────────────────────────────────────────────────────
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# ── Paths from settings.json ─────────────────────────────────────────────────
def _load_paths():
    settings_path = _ROOT / "config" / "settings.json"
    try:
        with open(settings_path) as f:
            s = json.load(f)
        google = s.get("google", {})
        def _abs(rel):
            p = Path(rel)
            return p if p.is_absolute() else _ROOT / p
        return (
            _abs(google.get("oauth_credentials_path", "config/credentials.json")),
            _abs(google.get("gmail_token_path",        "config/token.json")),
            _abs(google.get("drive_token_path",        "config/drive_token.json")),
        )
    except Exception as exc:
        print(f"⚠ Could not read config/settings.json: {exc}")
        return (
            _ROOT / "config" / "credentials.json",
            _ROOT / "config" / "token.json",
            _ROOT / "config" / "drive_token.json",
        )

CREDENTIALS_PATH, GMAIL_TOKEN_PATH, DRIVE_TOKEN_PATH = _load_paths()

# ── Scopes ───────────────────────────────────────────────────────────────────
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.settings.basic",  # OOO / vacation responder
]

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

CONTACTS_SCOPES = [
    "https://www.googleapis.com/auth/contacts.readonly",  # Google People API – read contacts
]

ALL_SCOPES = list(dict.fromkeys(GMAIL_SCOPES + DRIVE_SCOPES + CONTACTS_SCOPES))  # deduplicated


def _authorize(scopes: list, token_path: Path, label: str) -> bool:
    """Run OAuth flow, save token. Returns True on success."""
    if not CREDENTIALS_PATH.exists():
        print(f"❌ credentials.json not found at: {CREDENTIALS_PATH}")
        print("   Download it from Google Cloud Console → APIs & Services → Credentials.")
        return False

    creds = None
    # Try existing token first
    if token_path.exists():
        try:
            with open(token_path) as f:
                creds = Credentials.from_authorized_user_info(json.load(f), scopes)
        except Exception:
            creds = None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            print(f"✅ {label}: token refreshed successfully.")
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            return True
        except Exception as e:
            print(f"⚠  {label}: refresh failed ({e}), will re-authorize...")
            creds = None

    if creds and creds.valid:
        print(f"✅ {label}: token is still valid, no action needed.")
        return True

    # Full OAuth flow
    print(f"\n🔐 {label}: opening browser for Google authorization...")
    print("   Sign in with the Google account you want Octa Bot to access.\n")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"✅ {label}: token saved to {token_path}")
        return True
    except Exception as e:
        print(f"❌ {label}: authorization failed — {e}")
        return False


def main():
    print("=" * 60)
    print("  Octa Bot — Google OAuth Setup")
    print("=" * 60)
    print(f"  Credentials : {CREDENTIALS_PATH}")
    print(f"  Gmail token : {GMAIL_TOKEN_PATH}")
    print(f"  Drive token : {DRIVE_TOKEN_PATH}")
    print()

    # Use combined scopes so a single browser flow covers both Gmail + Drive
    gmail_ok = _authorize(ALL_SCOPES, GMAIL_TOKEN_PATH, "Gmail")
    # Drive uses the same credentials file but a separate token file
    drive_ok = _authorize(ALL_SCOPES, DRIVE_TOKEN_PATH, "Drive")

    print()
    if gmail_ok and drive_ok:
        print("🎉 All Google tokens are valid. Restart Octa Bot and try again.")
    else:
        print("⚠  Some tokens could not be refreshed. Check the errors above.")

    print("=" * 60)


if __name__ == "__main__":
    main()
