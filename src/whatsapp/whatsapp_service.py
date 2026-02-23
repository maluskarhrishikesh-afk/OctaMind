"""
Meta WhatsApp Cloud API — low-level REST client.

All HTTP interactions with the Graph API live here.  Feature modules
(messaging, contacts, etc.) call these helpers instead of using
``requests`` directly, keeping error handling and retry logic in one place.

API reference: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests

from .whatsapp_auth import get_access_token, get_phone_number_id

logger = logging.getLogger("whatsapp_agent")

_GRAPH_BASE = "https://graph.facebook.com/v18.0"
_TIMEOUT = 20  # seconds


# ── Internal helpers ──────────────────────────────────────────────────────────

def _headers() -> Dict[str, str]:
    """Return request headers with Bearer token."""
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }


def _unwrap(response: requests.Response) -> Dict[str, Any]:
    """Raise on HTTP errors and return the parsed JSON body."""
    try:
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        body: Any = {}
        try:
            body = response.json()
        except Exception:
            pass
        error_msg = (
            body.get("error", {}).get("message", str(exc))
            if isinstance(body, dict) else str(exc)
        )
        logger.error("WhatsApp API error: %s | body=%s", exc, body)
        raise RuntimeError(f"WhatsApp API error: {error_msg}") from exc


# ── Public API ────────────────────────────────────────────────────────────────

def send_text(to: str, body: str, preview_url: bool = False) -> Dict[str, Any]:
    """
    Send a plain text message.

    Args:
        to:          Recipient phone number in E.164 format (e.g. '919876543210').
        body:        Message text (max 4096 characters).
        preview_url: Whether to render link previews.

    Returns:
        Raw API response dict containing ``messages[0].id`` on success.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": preview_url, "body": body},
    }
    resp = requests.post(
        f"{_GRAPH_BASE}/{get_phone_number_id()}/messages",
        headers=_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def send_media_message(
    to: str,
    media_type: str,
    link: Optional[str] = None,
    media_id: Optional[str] = None,
    caption: str = "",
    filename: str = "",
) -> Dict[str, Any]:
    """
    Send an image, video, audio, document, or sticker.

    Args:
        to:         Recipient phone (E.164).
        media_type: 'image' | 'video' | 'audio' | 'document' | 'sticker'.
        link:       Public HTTPS URL of the media (mutually exclusive with media_id).
        media_id:   Media ID from a previous upload (mutually exclusive with link).
        caption:    Optional caption (supported on image/video/document).
        filename:   Document filename (document type only).
    """
    media_type = media_type.lower()
    media_obj: Dict[str, Any] = {}
    if link:
        media_obj["link"] = link
    elif media_id:
        media_obj["id"] = media_id
    else:
        raise ValueError("Either link or media_id must be provided")

    if caption and media_type in ("image", "video", "document"):
        media_obj["caption"] = caption
    if filename and media_type == "document":
        media_obj["filename"] = filename

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": media_type,
        media_type: media_obj,
    }
    resp = requests.post(
        f"{_GRAPH_BASE}/{get_phone_number_id()}/messages",
        headers=_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def send_template_message(
    to: str,
    template_name: str,
    language_code: str = "en_US",
    components: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Send a pre-approved WhatsApp Business template message.

    Args:
        to:            Recipient phone (E.164).
        template_name: Exact name of the approved template.
        language_code: Language/locale code (e.g. 'en_US', 'hi', 'en').
        components:    Optional list of template components (header/body/button).
    """
    template: Dict[str, Any] = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        template["components"] = components

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    }
    resp = requests.post(
        f"{_GRAPH_BASE}/{get_phone_number_id()}/messages",
        headers=_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def send_reaction(to: str, message_id: str, emoji: str) -> Dict[str, Any]:
    """React to an inbound message with an emoji."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "reaction",
        "reaction": {"message_id": message_id, "emoji": emoji},
    }
    resp = requests.post(
        f"{_GRAPH_BASE}/{get_phone_number_id()}/messages",
        headers=_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def send_read_receipt(message_id: str) -> Dict[str, Any]:
    """Mark an inbound message as read (sends read receipt to sender)."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    resp = requests.post(
        f"{_GRAPH_BASE}/{get_phone_number_id()}/messages",
        headers=_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def get_media_url(media_id: str) -> str:
    """Retrieve the temporary download URL for a media object."""
    resp = requests.get(
        f"{_GRAPH_BASE}/{media_id}",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _unwrap(resp)
    return data.get("url", "")


def get_business_profile() -> Dict[str, Any]:
    """Fetch the WhatsApp Business profile for the configured phone number."""
    resp = requests.get(
        f"{_GRAPH_BASE}/{get_phone_number_id()}/whatsapp_business_profile",
        headers=_headers(),
        params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)
