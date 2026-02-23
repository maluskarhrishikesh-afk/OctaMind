"""
WhatsApp search and retrieval tools.

Wraps the message store search functions with proper result formatting.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..webhook.message_store import (
    search_messages as _search,
    get_messages_for_contact,
    get_messages_by_date as _by_date,
    get_media_messages as _media_msgs,
)

logger = logging.getLogger("whatsapp_agent")


def search_messages(query: str, limit: int = 20) -> Dict[str, Any]:
    """
    Full-text search across all WhatsApp messages.

    Args:
        query: Search term (searches message body and contact names).
        limit: Max results to return.
    """
    try:
        limit = max(1, min(int(limit), 200))
        results = _search(query, limit=limit)
        return {
            "status": "success",
            "query": query,
            "messages": results,
            "count": len(results),
        }
    except Exception as exc:
        logger.error("search_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_conversation(phone: str, limit: int = 30) -> Dict[str, Any]:
    """
    Get the full conversation thread with a specific contact.

    Args:
        phone: Contact phone (E.164).
        limit: Max messages to return (default 30).
    """
    try:
        limit = max(1, min(int(limit), 200))
        msgs = get_messages_for_contact(phone, limit=limit)
        if not msgs:
            return {
                "status": "success",
                "phone": phone,
                "messages": [],
                "count": 0,
                "note": f"No messages found with {phone}.",
            }
        # Return oldest first for a natural conversation view
        msgs.reverse()
        return {
            "status": "success",
            "phone": phone,
            "messages": msgs,
            "count": len(msgs),
        }
    except Exception as exc:
        logger.error("get_conversation failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_messages_by_date(
    start_date: str,
    end_date: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Retrieve messages within a date range.

    Args:
        start_date: Start date in YYYY-MM-DD or YYYY-MM-DDTHH:MM format.
        end_date:   Optional end date (same format); defaults to now.
        limit:      Max messages to return.
    """
    try:
        limit = max(1, min(int(limit), 500))
        msgs = _by_date(start_date, end_date, limit=limit)
        return {
            "status": "success",
            "start_date": start_date,
            "end_date": end_date or "now",
            "messages": msgs,
            "count": len(msgs),
        }
    except Exception as exc:
        logger.error("get_messages_by_date failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_media_messages(limit: int = 30) -> Dict[str, Any]:
    """
    Get messages that contain media (images, videos, audio, documents).

    Args:
        limit: Max messages to return.
    """
    try:
        limit = max(1, min(int(limit), 200))
        msgs = _media_msgs(limit=limit)
        return {
            "status": "success",
            "messages": msgs,
            "count": len(msgs),
        }
    except Exception as exc:
        logger.error("get_media_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}
