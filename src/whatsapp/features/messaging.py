"""
Core WhatsApp messaging tools.

All functions return a dict with at minimum::

    {"status": "success"|"error", ...}

so the orchestrator can report errors consistently.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..whatsapp_service import (
    send_text,
    send_media_message,
    send_template_message,
    send_read_receipt,
)
from ..webhook.message_store import (
    store_outbound_message,
    get_all_messages,
    get_unread_messages as _get_unread,
    mark_message_read as _mark_read,
    get_messages_for_contact,
    get_message_by_id,
)

logger = logging.getLogger("whatsapp_agent")


def send_message(to: str, body: str) -> Dict[str, Any]:
    """
    Send a plain text WhatsApp message.

    Args:
        to:   Recipient phone in E.164 format (e.g. '919876543210').
        body: Message text.
    """
    try:
        resp = send_text(to, body)
        msg_id = resp.get("messages", [{}])[0].get("id", "")
        store_outbound_message(to, body, message_id=msg_id, message_type="text")
        return {
            "status": "success",
            "message_id": msg_id,
            "to": to,
            "message": f"Message sent to {to}",
        }
    except Exception as exc:
        logger.error("send_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def send_media(
    to: str,
    media_type: str,
    url: str,
    caption: str = "",
    filename: str = "",
) -> Dict[str, Any]:
    """
    Send a media message (image, video, audio, document, sticker).

    Args:
        to:         Recipient phone (E.164).
        media_type: 'image' | 'video' | 'audio' | 'document' | 'sticker'.
        url:        Public HTTPS URL of the media file.
        caption:    Optional caption.
        filename:   Document filename (for document type).
    """
    try:
        resp = send_media_message(
            to, media_type, link=url, caption=caption, filename=filename,
        )
        msg_id = resp.get("messages", [{}])[0].get("id", "")
        store_outbound_message(
            to, caption or f"[{media_type}]",
            message_id=msg_id, message_type=media_type, caption=caption,
        )
        return {
            "status": "success",
            "message_id": msg_id,
            "to": to,
            "media_type": media_type,
            "message": f"{media_type.title()} sent to {to}",
        }
    except Exception as exc:
        logger.error("send_media failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def send_template(
    to: str,
    template_name: str,
    language_code: str = "en_US",
) -> Dict[str, Any]:
    """
    Send an approved WhatsApp Business template message.

    Args:
        to:            Recipient phone (E.164).
        template_name: Exact name of the approved template.
        language_code: Language code (e.g. 'en_US', 'hi', 'en').
    """
    try:
        resp = send_template_message(to, template_name, language_code)
        msg_id = resp.get("messages", [{}])[0].get("id", "")
        store_outbound_message(
            to, f"[Template: {template_name}]",
            message_id=msg_id, message_type="template",
        )
        return {
            "status": "success",
            "message_id": msg_id,
            "to": to,
            "template": template_name,
            "message": f"Template '{template_name}' sent to {to}",
        }
    except Exception as exc:
        logger.error("send_template failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def reply_to_message(
    to: str,
    original_message_id: str,
    body: str,
) -> Dict[str, Any]:
    """
    Reply to an existing WhatsApp message, showing it as a quoted reply.

    Args:
        to:                  Recipient phone (E.164).
        original_message_id: ID of the message to reply to.
        body:                Reply text.
    """
    try:
        # Meta requires the context field for quoted replies
        import requests as _req
        from ..whatsapp_auth import get_access_token, get_phone_number_id
        _GRAPH_BASE = "https://graph.facebook.com/v18.0"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "context": {"message_id": original_message_id},
            "text": {"preview_url": False, "body": body},
        }
        resp = _req.post(
            f"{_GRAPH_BASE}/{get_phone_number_id()}/messages",
            headers={
                "Authorization": f"Bearer {get_access_token()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        msg_id = data.get("messages", [{}])[0].get("id", "")
        store_outbound_message(to, body, message_id=msg_id, message_type="text")
        return {
            "status": "success",
            "message_id": msg_id,
            "replied_to": original_message_id,
            "message": f"Replied to message {original_message_id}",
        }
    except Exception as exc:
        logger.error("reply_to_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_messages(limit: int = 20) -> Dict[str, Any]:
    """
    Get recent WhatsApp messages (both inbound and outbound).

    Args:
        limit: Max number of messages to return (default 20, max 200).
    """
    try:
        limit = max(1, min(int(limit), 200))
        msgs = get_all_messages(limit=limit)
        return {
            "status": "success",
            "messages": msgs,
            "count": len(msgs),
        }
    except Exception as exc:
        logger.error("get_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_unread_messages(limit: int = 20) -> Dict[str, Any]:
    """
    Get unread inbound WhatsApp messages.

    Args:
        limit: Max number of messages to return.
    """
    try:
        limit = max(1, min(int(limit), 200))
        msgs = _get_unread(limit=limit)
        return {
            "status": "success",
            "messages": msgs,
            "count": len(msgs),
            "unread_count": len(msgs),
        }
    except Exception as exc:
        logger.error("get_unread_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def mark_as_read(message_id: str) -> Dict[str, Any]:
    """
    Mark an inbound message as read (sends a read receipt to the sender).

    Args:
        message_id: WhatsApp message ID (wamid.xxx).
    """
    try:
        # Send read receipt via API
        send_read_receipt(message_id)
        # Update local store
        _mark_read(message_id)
        return {
            "status": "success",
            "message_id": message_id,
            "message": f"Message {message_id} marked as read",
        }
    except Exception as exc:
        logger.error("mark_as_read failed: %s", exc)
        return {"status": "error", "message": str(exc)}
