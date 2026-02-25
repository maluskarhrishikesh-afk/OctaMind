"""
Local Telegram message store.

All inbound messages received via the background poller are persisted here
as JSON.  Sent (outbound) messages are also logged so the agent has full
conversation history.

Storage layout (``data/telegram_messages.json``):
    {
      "offset": 0,          // next getUpdates offset (last_update_id + 1)
      "messages": [
        {
          "id":         "chat_id:message_id",  // composite key
          "update_id":  12345,
          "message_id": 567,
          "direction":  "inbound" | "outbound",
          "chat_id":    -100123456,
          "chat_type":  "private" | "group" | "supergroup" | "channel",
          "from_user":  "Alice",               // first_name or username
          "from_user_id": 789,
          "text":       "Hello!",
          "timestamp":  "2026-02-23T10:00:00",
          "read":       false,
          "media_type": null,                  // "photo" | "video" | "audio" | ...
          "file_id":    null,
          "caption":    null
        }
      ],
      "chats": {
        "123456": {
          "id":           123456,
          "type":         "private",
          "title":        "Alice",             // group title or user full_name
          "username":     "@alice",
          "first_seen":   "2026-02-23T10:00:00",
          "last_seen":    "2026-02-23T10:00:00",
          "message_count": 5
        }
      }
    }
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("telegram_agent")

# Per-PA pollers set TELEGRAM_DATA_FILE so each PA has its own message store.
_DATA_PATH = Path(
    os.environ.get(
        "TELEGRAM_DATA_FILE",
        str(Path(__file__).parent.parent.parent.parent / "data" / "telegram_messages.json"),
    )
)
_lock = threading.Lock()


# ── File I/O ──────────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    try:
        if _DATA_PATH.exists():
            return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load Telegram message store: %s", exc)
    return {"offset": 0, "messages": [], "chats": {}}


def _save(data: Dict[str, Any]) -> None:
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DATA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_DATA_PATH)


# ── Offset management ─────────────────────────────────────────────────────────

def get_offset() -> int:
    """Return the current getUpdates offset."""
    with _lock:
        return _load().get("offset", 0)


def set_offset(offset: int) -> None:
    """Persist the new getUpdates offset."""
    with _lock:
        data = _load()
        data["offset"] = offset
        _save(data)


# ── Write helpers ─────────────────────────────────────────────────────────────

def _extract_message_fields(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw Telegram Message object into our flat store schema."""
    # Sender info
    from_obj = msg.get("from") or msg.get("sender_chat") or {}
    from_name = from_obj.get("first_name") or from_obj.get("title") or ""
    if from_obj.get("last_name"):
        from_name += " " + from_obj["last_name"]
    from_user_id = from_obj.get("id", 0)
    username = from_obj.get("username", "")

    # Chat info
    chat = msg.get("chat", {})
    chat_id = chat.get("id", 0)
    chat_type = chat.get("type", "private")
    chat_title = chat.get("title") or (
        (chat.get("first_name", "") + " " + chat.get("last_name", "")).strip()
        or chat.get("username", str(chat_id))
    )
    chat_username = "@" + chat.get("username", "") if chat.get("username") else ""

    # Media detection
    media_type = None
    file_id = None
    text = msg.get("text") or msg.get("caption") or ""
    caption = msg.get("caption")

    for mtype in ("photo", "video", "audio", "voice", "document", "sticker",
                  "animation", "video_note"):
        if mtype in msg:
            media_type = mtype
            obj = msg[mtype]
            if isinstance(obj, list):  # photo is a list of sizes
                file_id = obj[-1].get("file_id") if obj else None
            elif isinstance(obj, dict):
                file_id = obj.get("file_id")
            break

    # Timestamp
    date_ts = msg.get("date", 0)
    try:
        ts = datetime.utcfromtimestamp(date_ts).isoformat()
    except Exception:
        ts = datetime.now().isoformat()

    message_id = msg.get("message_id", 0)
    composite_id = f"{chat_id}:{message_id}"

    return {
        "id": composite_id,
        "message_id": message_id,
        "direction": "inbound",
        "chat_id": chat_id,
        "chat_type": chat_type,
        "from_user": from_name,
        "from_user_id": from_user_id,
        "username": username,
        "text": text,
        "timestamp": ts,
        "read": False,
        "media_type": media_type,
        "file_id": file_id,
        "caption": caption,
        # chat metadata (for upsert)
        "_chat_title": chat_title,
        "_chat_username": chat_username,
    }


def store_inbound_message(msg: Dict[str, Any], update_id: int = 0) -> None:
    """Persist an inbound message object from a Telegram update."""
    fields = _extract_message_fields(msg)
    chat_id_str = str(fields["chat_id"])

    with _lock:
        data = _load()

        # Deduplicate by composite id
        existing_ids = {m["id"] for m in data["messages"]}
        if fields["id"] in existing_ids:
            return

        # Add update_id for traceability
        record = {k: v for k, v in fields.items() if not k.startswith("_")}
        record["update_id"] = update_id
        data["messages"].append(record)

        # Trim store to last 2 000 messages (keep it lean)
        if len(data["messages"]) > 2000:
            data["messages"] = data["messages"][-2000:]

        # Upsert chat
        existing_chat = data["chats"].get(chat_id_str, {})
        data["chats"][chat_id_str] = {
            "id": fields["chat_id"],
            "type": fields["chat_type"],
            "title": fields["_chat_title"],
            "username": fields["_chat_username"],
            "first_seen": existing_chat.get("first_seen", fields["timestamp"]),
            "last_seen": fields["timestamp"],
            "message_count": existing_chat.get("message_count", 0) + 1,
        }

        _save(data)


def store_outbound_message(
    chat_id: int | str,
    text: str,
    message_id: int = 0,
    media_type: Optional[str] = None,
    caption: Optional[str] = None,
) -> None:
    """Log a message sent by the bot."""
    ts = datetime.now().isoformat()
    composite_id = f"{chat_id}:{message_id}:out"

    with _lock:
        data = _load()
        data["messages"].append({
            "id": composite_id,
            "message_id": message_id,
            "direction": "outbound",
            "chat_id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else 0,
            "chat_type": "private",
            "from_user": "Bot",
            "from_user_id": 0,
            "username": "",
            "text": text,
            "timestamp": ts,
            "read": True,
            "media_type": media_type,
            "file_id": None,
            "caption": caption,
            "update_id": 0,
        })
        _save(data)


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_all_messages(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent messages across all chats."""
    with _lock:
        data = _load()
    msgs = data.get("messages", [])
    return sorted(msgs, key=lambda m: m.get("timestamp", ""), reverse=True)[:limit]


def get_unread_messages(limit: int = 20) -> List[Dict[str, Any]]:
    """Return inbound messages that have not been marked read."""
    with _lock:
        data = _load()
    unread = [
        m for m in data.get("messages", [])
        if m.get("direction") == "inbound" and not m.get("read", False)
    ]
    return sorted(unread, key=lambda m: m.get("timestamp", ""), reverse=True)[:limit]


def get_messages_for_chat(chat_id: int | str, limit: int = 30) -> List[Dict[str, Any]]:
    """Return recent messages for a specific chat_id."""
    cid = str(chat_id)
    with _lock:
        data = _load()
    msgs = [m for m in data.get("messages", []) if str(m.get("chat_id", "")) == cid]
    return sorted(msgs, key=lambda m: m.get("timestamp", ""))[-limit:]


def get_message_by_composite_id(composite_id: str) -> Optional[Dict[str, Any]]:
    """Find a specific message by its composite id (chat_id:message_id)."""
    with _lock:
        data = _load()
    for m in data.get("messages", []):
        if m.get("id") == composite_id:
            return m
    return None


def mark_message_read(composite_id: str) -> None:
    """Mark a message as read."""
    with _lock:
        data = _load()
        for m in data["messages"]:
            if m.get("id") == composite_id:
                m["read"] = True
                break
        _save(data)


def get_all_chats() -> Dict[str, Any]:
    """Return the chats dict (keyed by chat_id string)."""
    with _lock:
        return _load().get("chats", {})


def get_message_count() -> Dict[str, int]:
    """Return message counts broken down by direction and read status."""
    with _lock:
        data = _load()
    msgs = data.get("messages", [])
    inbound = [m for m in msgs if m.get("direction") == "inbound"]
    outbound = [m for m in msgs if m.get("direction") == "outbound"]
    unread = [m for m in inbound if not m.get("read", False)]
    return {
        "total": len(msgs),
        "inbound": len(inbound),
        "outbound": len(outbound),
        "unread": len(unread),
    }
