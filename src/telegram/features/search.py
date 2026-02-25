"""
Telegram message search and retrieval tools.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..polling.message_store import (
    get_all_messages,
    get_messages_for_chat,
    get_all_chats,
)

logger = logging.getLogger("telegram_agent")


def search_messages(
    query: str,
    chat_id: Optional[int | str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Full-text search across stored Telegram messages.

    Args:
        query:   Text to search for (case-insensitive).
        chat_id: Restrict search to one chat (optional).
        limit:   Maximum results.
    """
    try:
        if chat_id:
            pool = get_messages_for_chat(chat_id, limit=1000)
        else:
            pool = get_all_messages(limit=2000)

        q = query.lower()
        matches = [
            m for m in pool
            if q in (m.get("text") or "").lower()
            or q in (m.get("caption") or "").lower()
            or q in (m.get("from_user") or "").lower()
        ][:limit]

        return {
            "status": "success",
            "query": query,
            "count": len(matches),
            "messages": matches,
        }
    except Exception as exc:
        logger.error("search_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_messages_by_date(
    chat_id: int | str,
    from_date: str,
    to_date: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Get messages from a chat within a date range.

    Args:
        chat_id:   Target chat.
        from_date: Start date (YYYY-MM-DD).
        to_date:   End date (YYYY-MM-DD). Defaults to today.
        limit:     Maximum results.
    """
    try:
        msgs = get_messages_for_chat(chat_id, limit=2000)
        end_str = (to_date or datetime.now().strftime("%Y-%m-%d")) + "T23:59:59"
        start_str = from_date + "T00:00:00"

        filtered = [
            m for m in msgs
            if start_str <= m.get("timestamp", "") <= end_str
        ][:limit]

        return {
            "status": "success",
            "chat_id": chat_id,
            "from_date": from_date,
            "to_date": to_date or datetime.now().strftime("%Y-%m-%d"),
            "count": len(filtered),
            "messages": filtered,
        }
    except Exception as exc:
        logger.error("get_messages_by_date failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_pinned_messages(chat_id: int | str) -> Dict[str, Any]:
    """
    Get the currently pinned message(s) in a chat (via live API).

    Args:
        chat_id: Target chat.
    """
    try:
        from ..telegram_service import get_chat_api
        chat_info = get_chat_api(chat_id)
        pinned = chat_info.get("pinned_message")
        if not pinned:
            return {
                "status": "success",
                "chat_id": chat_id,
                "count": 0,
                "pinned_messages": [],
                "message": "No pinned message in this chat.",
            }

        # Normalise
        text = pinned.get("text") or pinned.get("caption") or ""
        from_obj = pinned.get("from") or {}
        from_name = from_obj.get("first_name", "") + " " + from_obj.get("last_name", "")
        return {
            "status": "success",
            "chat_id": chat_id,
            "count": 1,
            "pinned_messages": [{
                "message_id": pinned.get("message_id"),
                "text": text,
                "from": from_name.strip(),
                "date": datetime.utcfromtimestamp(
                    pinned.get("date", 0)).isoformat(),
            }],
        }
    except Exception as exc:
        logger.error("get_pinned_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_message_stats(limit: int = 30) -> Dict[str, Any]:
    """
    Return summary statistics across stored messages.

    Args:
        limit: Days of data to summarise (uses latest N messages as proxy).
    """
    try:
        msgs = get_all_messages(limit=2000)
        chats = get_all_chats()

        inbound = [m for m in msgs if m.get("direction") == "inbound"]
        outbound = [m for m in msgs if m.get("direction") == "outbound"]
        unread = [m for m in inbound if not m.get("read", False)]
        media = [m for m in msgs if m.get("media_type")]

        # Per-chat breakdown
        per_chat: Dict[str, int] = {}
        for m in inbound:
            cid = str(m.get("chat_id", ""))
            per_chat[cid] = per_chat.get(cid, 0) + 1

        top_chats = sorted(per_chat.items(), key=lambda x: x[1], reverse=True)[:5]
        top_chat_names = []
        for cid, cnt in top_chats:
            chat_data = chats.get(cid, {})
            top_chat_names.append({
                "chat_id": cid,
                "name": chat_data.get("title", cid),
                "messages": cnt,
            })

        return {
            "status": "success",
            "total_stored": len(msgs),
            "inbound": len(inbound),
            "outbound": len(outbound),
            "unread": len(unread),
            "with_media": len(media),
            "total_chats": len(chats),
            "top_active_chats": top_chat_names,
        }
    except Exception as exc:
        logger.error("get_message_stats failed: %s", exc)
        return {"status": "error", "message": str(exc)}
