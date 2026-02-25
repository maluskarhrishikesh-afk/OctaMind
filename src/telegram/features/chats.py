"""
Telegram chat and group management tools.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..telegram_service import (
    get_chat_api,
    get_chat_member_count,
    get_chat_administrators,
    pin_chat_message_api,
    unpin_chat_message_api,
    leave_chat_api,
)
from ..polling.message_store import get_all_chats

logger = logging.getLogger("telegram_agent")


def list_chats(limit: int = 50) -> Dict[str, Any]:
    """
    List all known Telegram chats from the local store.

    Args:
        limit: Maximum number of chats to return.
    """
    try:
        chats = get_all_chats()
        chats_list = sorted(
            chats.values(),
            key=lambda c: c.get("last_seen", ""),
            reverse=True,
        )[:limit]
        return {
            "status": "success",
            "count": len(chats_list),
            "chats": chats_list,
        }
    except Exception as exc:
        logger.error("list_chats failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_chat_info(chat_id: int | str) -> Dict[str, Any]:
    """
    Get detailed information about a chat.

    Fetches live data from the Telegram API and merges with local history.

    Args:
        chat_id: Telegram chat ID or @username.
    """
    try:
        live = get_chat_api(chat_id)
        member_count = 0
        chat_type = live.get("type", "private")
        if chat_type in ("group", "supergroup", "channel"):
            try:
                member_count = get_chat_member_count(chat_id)
            except Exception:
                pass

        title = (
            live.get("title")
            or (live.get("first_name", "") + " " + live.get("last_name", "")).strip()
            or str(chat_id)
        )
        username = "@" + live["username"] if live.get("username") else ""
        description = live.get("description", "")
        invite_link = live.get("invite_link", "")
        is_forum = live.get("is_forum", False)

        # Merge local message count
        local_chats = get_all_chats()
        local = local_chats.get(str(live.get("id", chat_id)), {})
        msg_count = local.get("message_count", 0)

        return {
            "status": "success",
            "chat_id": live.get("id", chat_id),
            "type": chat_type,
            "title": title,
            "username": username,
            "description": description,
            "member_count": member_count,
            "invite_link": invite_link,
            "is_forum": is_forum,
            "local_message_count": msg_count,
        }
    except Exception as exc:
        logger.error("get_chat_info failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_chat_members(chat_id: int | str, limit: int = 200) -> Dict[str, Any]:
    """
    Get administrators of a group or channel.

    Note: The Bot API only allows fetching administrators, not all members,
    unless the bot has additional permissions.

    Args:
        chat_id: Group or channel chat ID.
        limit:   Maximum members to return.
    """
    try:
        admins = get_chat_administrators(chat_id)
        member_count = 0
        try:
            member_count = get_chat_member_count(chat_id)
        except Exception:
            pass

        members = []
        for a in admins[:limit]:
            user = a.get("user", {})
            name = user.get("first_name", "")
            if user.get("last_name"):
                name += " " + user["last_name"]
            members.append({
                "user_id": user.get("id"),
                "name": name,
                "username": "@" + user["username"] if user.get("username") else "",
                "status": a.get("status", "member"),
                "is_anonymous": a.get("is_anonymous", False),
                "custom_title": a.get("custom_title", ""),
            })

        return {
            "status": "success",
            "chat_id": chat_id,
            "total_member_count": member_count,
            "administrators_shown": len(members),
            "members": members,
        }
    except Exception as exc:
        logger.error("get_chat_members failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def pin_message(
    chat_id: int | str,
    message_id: int,
    silent: bool = False,
) -> Dict[str, Any]:
    """
    Pin a message in a chat.

    Args:
        chat_id:    Chat where the message is.
        message_id: Message ID to pin.
        silent:     If True, pin without notifying members.
    """
    try:
        pin_chat_message_api(chat_id, message_id, disable_notification=silent)
        return {
            "status": "success",
            "message": f"Message {message_id} pinned in chat {chat_id}.",
        }
    except Exception as exc:
        logger.error("pin_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def unpin_message(
    chat_id: int | str,
    message_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Unpin a message (or the most recently pinned message if no ID given).

    Args:
        chat_id:    Chat to unpin in.
        message_id: Specific message ID to unpin. Omit to unpin the latest.
    """
    try:
        unpin_chat_message_api(chat_id, message_id)
        target = f"message {message_id}" if message_id else "latest pinned message"
        return {
            "status": "success",
            "message": f"Unpinned {target} in chat {chat_id}.",
        }
    except Exception as exc:
        logger.error("unpin_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def leave_chat(chat_id: int | str) -> Dict[str, Any]:
    """
    Make the bot leave a group or channel.

    Args:
        chat_id: Group or channel to leave.
    """
    try:
        leave_chat_api(chat_id)
        return {
            "status": "success",
            "message": f"Left chat {chat_id}.",
        }
    except Exception as exc:
        logger.error("leave_chat failed: %s", exc)
        return {"status": "error", "message": str(exc)}
