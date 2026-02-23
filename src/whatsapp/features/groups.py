"""
WhatsApp groups tools.

Groups are discovered automatically when group messages arrive via the
webhook.  The Meta Cloud API does not provide an endpoint to enumerate
all groups for a number, so this module works entirely from the locally
stored message data.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ..webhook.message_store import (
    get_all_groups,
    get_group,
    get_group_messages as _get_group_msgs,
)

logger = logging.getLogger("whatsapp_agent")


def list_groups(limit: int = 50) -> Dict[str, Any]:
    """
    List all WhatsApp groups that have sent at least one message.

    Args:
        limit: Max groups to return (default 50).
    """
    try:
        limit = max(1, min(int(limit), 200))
        groups = get_all_groups(limit=limit)
        return {
            "status": "success",
            "groups": groups,
            "count": len(groups),
        }
    except Exception as exc:
        logger.error("list_groups failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_group_info(group_id: str) -> Dict[str, Any]:
    """
    Get metadata for a specific group (subject, participants, first/last seen).

    Args:
        group_id: The group identifier (phone-number-based ID as received in webhook).
    """
    try:
        group = get_group(group_id)
        if not group:
            return {
                "status": "error",
                "message": (
                    f"Group '{group_id}' not found. "
                    "Groups appear automatically once a group message is received."
                ),
            }
        return {
            "status": "success",
            "group": group,
        }
    except Exception as exc:
        logger.error("get_group_info failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_group_messages(group_id: str, limit: int = 30) -> Dict[str, Any]:
    """
    Get recent messages from a specific group.

    Args:
        group_id: The group identifier.
        limit:    Max messages to return (default 30).
    """
    try:
        limit = max(1, min(int(limit), 200))
        messages = _get_group_msgs(group_id, limit=limit)
        if not messages:
            return {
                "status": "success",
                "messages": [],
                "count": 0,
                "note": (
                    f"No messages found for group '{group_id}'. "
                    "Check the group ID or ensure messages have been received."
                ),
            }
        return {
            "status": "success",
            "group_id": group_id,
            "messages": messages,
            "count": len(messages),
        }
    except Exception as exc:
        logger.error("get_group_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}
