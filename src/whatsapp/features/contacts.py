"""
WhatsApp contacts management tools.

Contacts are discovered automatically from incoming messages (via webhook)
and stored in the local message store.  You can also add/update contacts
manually using the update_contact_name helper.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..webhook.message_store import (
    get_all_contacts,
    get_contact,
    get_frequent_contacts as _frequent,
    update_contact_name,
    get_messages_for_contact,
)

logger = logging.getLogger("whatsapp_agent")


def list_contacts(limit: int = 50) -> Dict[str, Any]:
    """
    List all known WhatsApp contacts, sorted by most recently active.

    Args:
        limit: Max contacts to return (default 50).
    """
    try:
        limit = max(1, min(int(limit), 500))
        contacts = get_all_contacts(limit=limit)
        return {
            "status": "success",
            "contacts": contacts,
            "count": len(contacts),
        }
    except Exception as exc:
        logger.error("list_contacts failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_contact_info(phone: str) -> Dict[str, Any]:
    """
    Get details for a specific contact, including message history overview.

    Args:
        phone: Contact phone number in E.164 format (e.g. '919876543210').
    """
    try:
        contact = get_contact(phone)
        if not contact:
            return {
                "status": "error",
                "message": f"Contact {phone} not found. "
                           "They may not have messaged you yet.",
            }
        # Add message preview
        recent = get_messages_for_contact(phone, limit=5)
        return {
            "status": "success",
            "contact": contact,
            "recent_messages": recent,
            "recent_message_count": len(recent),
        }
    except Exception as exc:
        logger.error("get_contact_info failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_frequent_contacts(limit: int = 10) -> Dict[str, Any]:
    """
    Get the most active WhatsApp contacts by message volume.

    Args:
        limit: Number of top contacts to return (default 10).
    """
    try:
        limit = max(1, min(int(limit), 100))
        contacts = _frequent(limit=limit)
        return {
            "status": "success",
            "contacts": contacts,
            "count": len(contacts),
        }
    except Exception as exc:
        logger.error("get_frequent_contacts failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def set_contact_name(phone: str, name: str) -> Dict[str, Any]:
    """
    Set or update the display name for a contact.

    Args:
        phone: Contact phone (E.164).
        name:  Display name to assign.
    """
    try:
        update_contact_name(phone, name)
        return {
            "status": "success",
            "phone": phone,
            "name": name,
            "message": f"Contact {phone} renamed to '{name}'",
        }
    except Exception as exc:
        logger.error("set_contact_name failed: %s", exc)
        return {"status": "error", "message": str(exc)}
