"""
Core Telegram messaging tools.

All functions return a dict with at minimum:
    {"status": "success" | "error", ...}
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..telegram_service import (
    send_text,
    send_chat_action_api,
    forward_message_api,
    edit_message_text,
    delete_message_api,
)
from ..polling.message_store import (
    store_outbound_message,
    get_all_messages,
    get_unread_messages as _get_unread,
    get_messages_for_chat,
    mark_message_read,
)

logger = logging.getLogger("telegram_agent")


def send_message(chat_id: int | str, text: str) -> Dict[str, Any]:
    """
    Send a plain-text message to a Telegram chat.

    Args:
        chat_id: Telegram chat ID (integer) or @username.
        text:    Message body (Markdown supported).
    """
    try:
        resp = send_text(chat_id, text)
        msg_id = resp.get("message_id", 0)
        store_outbound_message(chat_id, text, message_id=msg_id)
        return {
            "status": "success",
            "message_id": msg_id,
            "chat_id": chat_id,
            "message": f"Message sent to {chat_id}",
        }
    except Exception as exc:
        logger.error("send_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def reply_to_message(
    chat_id: int | str,
    message_id: int,
    text: str,
) -> Dict[str, Any]:
    """
    Reply to a specific Telegram message (threaded/quoted reply).

    Args:
        chat_id:    Chat the message is in.
        message_id: ID of the message to reply to.
        text:       Reply text.
    """
    try:
        from ..telegram_service import send_text as _send
        resp = _send(chat_id, text, reply_to_message_id=message_id)
        out_id = resp.get("message_id", 0)
        store_outbound_message(chat_id, text, message_id=out_id)
        return {
            "status": "success",
            "message_id": out_id,
            "reply_to": message_id,
            "message": f"Reply sent to message {message_id}",
        }
    except Exception as exc:
        logger.error("reply_to_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def forward_message(
    from_chat_id: int | str,
    to_chat_id: int | str,
    message_id: int,
) -> Dict[str, Any]:
    """
    Forward a message from one chat to another.

    Args:
        from_chat_id: Source chat.
        to_chat_id:   Destination chat.
        message_id:   Message ID in the source chat.
    """
    try:
        resp = forward_message_api(to_chat_id, from_chat_id, message_id)
        out_id = resp.get("message_id", 0)
        return {
            "status": "success",
            "forwarded_message_id": out_id,
            "from_chat_id": from_chat_id,
            "to_chat_id": to_chat_id,
            "message": f"Message {message_id} forwarded to {to_chat_id}",
        }
    except Exception as exc:
        logger.error("forward_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def edit_message(
    chat_id: int | str,
    message_id: int,
    new_text: str,
) -> Dict[str, Any]:
    """
    Edit the text of a previously sent message.

    Args:
        chat_id:    Chat the message belongs to.
        message_id: ID of the message to edit.
        new_text:   New text content.
    """
    try:
        resp = edit_message_text(chat_id, message_id, new_text)
        return {
            "status": "success",
            "message_id": resp.get("message_id", message_id),
            "message": f"Message {message_id} edited.",
        }
    except Exception as exc:
        logger.error("edit_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def delete_message(chat_id: int | str, message_id: int) -> Dict[str, Any]:
    """
    Delete a message.

    Args:
        chat_id:    Chat the message belongs to.
        message_id: ID of the message to delete.
    """
    try:
        delete_message_api(chat_id, message_id)
        return {
            "status": "success",
            "message": f"Message {message_id} deleted from chat {chat_id}.",
        }
    except Exception as exc:
        logger.error("delete_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_messages(limit: int = 20) -> Dict[str, Any]:
    """
    Get recent messages across all chats (inbound + outbound).

    Args:
        limit: Maximum number of messages to return.
    """
    try:
        msgs = get_all_messages(limit=limit)
        return {
            "status": "success",
            "count": len(msgs),
            "messages": msgs,
        }
    except Exception as exc:
        logger.error("get_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_unread_messages(limit: int = 20) -> Dict[str, Any]:
    """
    Get unread inbound messages.

    Args:
        limit: Maximum number to return.
    """
    try:
        msgs = _get_unread(limit=limit)
        return {
            "status": "success",
            "count": len(msgs),
            "unread": msgs,
            "message": f"{len(msgs)} unread message(s).",
        }
    except Exception as exc:
        logger.error("get_unread_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_chat_history(chat_id: int | str, limit: int = 30) -> Dict[str, Any]:
    """
    Get the full conversation thread for a specific chat.

    Args:
        chat_id: Telegram chat ID or @username.
        limit:   Number of recent messages.
    """
    try:
        msgs = get_messages_for_chat(chat_id, limit=limit)
        if not msgs:
            return {
                "status": "success",
                "count": 0,
                "messages": [],
                "message": f"No messages found for chat {chat_id}.",
            }
        return {
            "status": "success",
            "chat_id": chat_id,
            "count": len(msgs),
            "messages": msgs,
        }
    except Exception as exc:
        logger.error("get_chat_history failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def mark_as_read(composite_id: str) -> Dict[str, Any]:
    """
    Mark a stored message as read.

    Args:
        composite_id: The message composite id in format "chat_id:message_id".
    """
    try:
        mark_message_read(composite_id)
        return {
            "status": "success",
            "message": f"Message {composite_id} marked as read.",
        }
    except Exception as exc:
        logger.error("mark_as_read failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def send_chat_action(chat_id: int | str, action: str = "typing") -> Dict[str, Any]:
    """
    Show a chat action indicator to the user (e.g. "typing…").

    Args:
        chat_id: Target chat.
        action:  typing | upload_photo | record_video | upload_video |
                 record_voice | upload_voice | upload_document | find_location
    """
    try:
        send_chat_action_api(chat_id, action)
        return {
            "status": "success",
            "message": f"Chat action '{action}' sent to {chat_id}.",
        }
    except Exception as exc:
        logger.error("send_chat_action failed: %s", exc)
        return {"status": "error", "message": str(exc)}
