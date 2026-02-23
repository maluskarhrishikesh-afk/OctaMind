"""
WhatsApp credentials loader.

Reads WhatsApp API credentials from config/settings.json under the
"whatsapp" key.  Falls back to environment variables so CI/CD pipelines
can inject secrets without touching the settings file.

Expected settings.json shape:
    {
      "whatsapp": {
        "access_token":     "EAAxxxxxxxxxx...",
        "phone_number_id":  "123456789012345",
        "verify_token":     "any_string_you_choose_for_webhook_verification",
        "webhook_port":     9001
      }
    }
"""
from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("whatsapp_agent")

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"


def _load_settings() -> dict:
    """Load config/settings.json; return empty dict on any failure."""
    try:
        if _SETTINGS_PATH.exists():
            return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not load settings.json: %s", exc)
    return {}


def get_access_token() -> str:
    """
    Return the WhatsApp access token.

    Precedence:
      1. Environment variable ``WHATSAPP_ACCESS_TOKEN``
      2. settings.json ``whatsapp.access_token``
    """
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    if token:
        return token
    return _load_settings().get("whatsapp", {}).get("access_token", "")


def get_phone_number_id() -> str:
    """
    Return the WhatsApp phone-number ID (not the actual phone number).

    Precedence:
      1. Environment variable ``WHATSAPP_PHONE_NUMBER_ID``
      2. settings.json ``whatsapp.phone_number_id``
    """
    pid = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if pid:
        return pid
    return _load_settings().get("whatsapp", {}).get("phone_number_id", "")


def get_verify_token() -> str:
    """
    Return the webhook verification token (any static string you chose).

    Precedence:
      1. Environment variable ``WHATSAPP_VERIFY_TOKEN``
      2. settings.json ``whatsapp.verify_token``
    """
    tok = os.getenv("WHATSAPP_VERIFY_TOKEN")
    if tok:
        return tok
    return _load_settings().get("whatsapp", {}).get("verify_token", "octamind_webhook")


def get_webhook_port() -> int:
    """Return the port the webhook FastAPI server should listen on (default 9001)."""
    port_env = os.getenv("WHATSAPP_WEBHOOK_PORT")
    if port_env and port_env.isdigit():
        return int(port_env)
    return int(_load_settings().get("whatsapp", {}).get("webhook_port", 9001))


def credentials_configured() -> bool:
    """Return True if the minimum required credentials are present."""
    return bool(get_access_token() and get_phone_number_id())
