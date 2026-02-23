"""
Local WhatsApp message store.

All inbound messages received via the webhook are persisted here as JSON.
Sent messages are also logged so the agent has a full conversation history.

Storage layout (``data/whatsapp_messages.json``):
    {
      "messages": [
        {
          "id":           "wamid.xxx",       // WhatsApp message ID
          "direction":    "inbound"|"outbound",
          "from":         "919876543210",    // sender number (inbound)
          "to":           "919999999999",    // recipient (outbound)
          "type":         "text"|"image"|...,
          "body":         "Hello!",
          "timestamp":    "2025-01-15T10:30:00",
          "read":         false,
          "group_id":     null,              // group phone if group message
          "media_id":     null,
          "media_type":   null,
          "caption":      null
        },
        ...
      ],
      "contacts": {
        "919876543210": {
          "phone":        "919876543210",
          "name":         "Alice",           // display name (from profile or manual)
          "first_seen":   "2025-01-15T10:30:00",
          "last_seen":    "2025-01-15T12:00:00",
          "message_count": 5
        },
        ...
      },
      "groups": {
        "group_phone_id": {
          "id":           "group_phone_id",
          "subject":      "Team Chat",
          "first_seen":   "2025-01-15T10:30:00",
          "participants": []
        },
        ...
      }
    }
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("whatsapp_agent")

_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "whatsapp_messages.json"
_SCHEDULED_PATH = Path(__file__).parent.parent.parent.parent / "data" / "whatsapp_scheduled.json"
_AUTO_REPLY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "whatsapp_auto_reply.json"

_lock = threading.Lock()


# ── File I/O ──────────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    """Load the store from disk; create an empty store if the file doesn't exist."""
    try:
        if _DATA_PATH.exists():
            return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load message store: %s", exc)
    return {"messages": [], "contacts": {}, "groups": {}}


def _save(data: Dict[str, Any]) -> None:
    """Persist the store to disk atomically."""
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DATA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_DATA_PATH)


# ── Write helpers ─────────────────────────────────────────────────────────────

def store_inbound_message(
    message_id: str,
    from_number: str,
    message_type: str,
    body: str,
    timestamp: Optional[str] = None,
    group_id: Optional[str] = None,
    media_id: Optional[str] = None,
    media_type: Optional[str] = None,
    caption: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> None:
    """Persist an inbound message from the webhook."""
    ts = timestamp or datetime.now().isoformat()
    with _lock:
        data = _load()
        data["messages"].append({
            "id": message_id,
            "direction": "inbound",
            "from": from_number,
            "to": "",
            "type": message_type,
            "body": body,
            "timestamp": ts,
            "read": False,
            "group_id": group_id,
            "media_id": media_id,
            "media_type": media_type,
            "caption": caption,
        })

        # Update contact
        contact = data["contacts"].setdefault(from_number, {
            "phone": from_number,
            "name": sender_name or from_number,
            "first_seen": ts,
            "last_seen": ts,
            "message_count": 0,
        })
        contact["last_seen"] = ts
        contact["message_count"] = contact.get("message_count", 0) + 1
        if sender_name and contact.get("name") == from_number:
            contact["name"] = sender_name

        # Update group
        if group_id:
            group = data["groups"].setdefault(group_id, {
                "id": group_id,
                "subject": group_id,
                "first_seen": ts,
                "participants": [],
            })
            if from_number not in group.get("participants", []):
                group.setdefault("participants", []).append(from_number)

        _save(data)


def store_outbound_message(
    to: str,
    body: str,
    message_id: str = "",
    message_type: str = "text",
    media_id: Optional[str] = None,
    caption: Optional[str] = None,
) -> None:
    """Log a message we sent (so the history is complete)."""
    ts = datetime.now().isoformat()
    with _lock:
        data = _load()
        data["messages"].append({
            "id": message_id or f"out_{datetime.now().timestamp()}",
            "direction": "outbound",
            "from": "",
            "to": to,
            "type": message_type,
            "body": body,
            "timestamp": ts,
            "read": True,
            "group_id": None,
            "media_id": media_id,
            "media_type": None,
            "caption": caption,
        })
        _save(data)


def mark_message_read(message_id: str) -> None:
    """Mark a stored message as read."""
    with _lock:
        data = _load()
        for msg in data["messages"]:
            if msg["id"] == message_id:
                msg["read"] = True
                break
        _save(data)


def update_contact_name(phone: str, name: str) -> None:
    """Set or update the display name of a contact."""
    with _lock:
        data = _load()
        contact = data["contacts"].setdefault(phone, {
            "phone": phone, "name": name,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "message_count": 0,
        })
        contact["name"] = name
        _save(data)


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_all_messages(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent messages, newest first."""
    data = _load()
    msgs = sorted(data["messages"], key=lambda m: m.get("timestamp", ""), reverse=True)
    return msgs[:limit]


def get_messages_for_contact(phone: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Return messages exchanged with a specific phone number."""
    data = _load()
    msgs = [
        m for m in data["messages"]
        if m.get("from") == phone or m.get("to") == phone
    ]
    msgs.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return msgs[:limit]


def get_unread_messages(limit: int = 50) -> List[Dict[str, Any]]:
    """Return inbound messages that haven't been marked as read."""
    data = _load()
    unread = [
        m for m in data["messages"]
        if not m.get("read") and m.get("direction") == "inbound"
    ]
    unread.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return unread[:limit]


def get_messages_by_date(
    start_date: str,
    end_date: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Return messages within a date range (ISO prefix comparison)."""
    data = _load()
    msgs = [
        m for m in data["messages"]
        if m.get("timestamp", "") >= start_date
        and (not end_date or m.get("timestamp", "") <= end_date)
    ]
    msgs.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return msgs[:limit]


def get_media_messages(limit: int = 50) -> List[Dict[str, Any]]:
    """Return messages that contain media attachments."""
    data = _load()
    media_msgs = [
        m for m in data["messages"]
        if m.get("type") not in ("text", None)
    ]
    media_msgs.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return media_msgs[:limit]


def search_messages(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Full-text search across message bodies and contact names."""
    query_lower = query.lower()
    data = _load()
    results = [
        m for m in data["messages"]
        if query_lower in (m.get("body") or "").lower()
        or query_lower in (m.get("caption") or "").lower()
        or query_lower in (m.get("from") or "").lower()
        or query_lower in data["contacts"].get(m.get("from", ""), {}).get("name", "").lower()
    ]
    results.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return results[:limit]


def get_message_by_id(message_id: str) -> Optional[Dict[str, Any]]:
    """Find a single message by its ID."""
    for msg in _load()["messages"]:
        if msg["id"] == message_id:
            return msg
    return None


def get_all_contacts(limit: int = 200) -> List[Dict[str, Any]]:
    """Return all known contacts sorted by last_seen, newest first."""
    data = _load()
    contacts = sorted(
        data["contacts"].values(),
        key=lambda c: c.get("last_seen", ""),
        reverse=True,
    )
    return contacts[:limit]


def get_contact(phone: str) -> Optional[Dict[str, Any]]:
    """Return a contact dict by phone number."""
    return _load()["contacts"].get(phone)


def get_frequent_contacts(limit: int = 10) -> List[Dict[str, Any]]:
    """Return contacts sorted by message_count, most active first."""
    data = _load()
    contacts = sorted(
        data["contacts"].values(),
        key=lambda c: c.get("message_count", 0),
        reverse=True,
    )
    return contacts[:limit]


def get_all_groups(limit: int = 100) -> List[Dict[str, Any]]:
    """Return all known groups."""
    data = _load()
    return list(data["groups"].values())[:limit]


def get_group(group_id: str) -> Optional[Dict[str, Any]]:
    """Return a group dict by its ID."""
    return _load()["groups"].get(group_id)


def get_group_messages(group_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Return messages for a specific group."""
    data = _load()
    msgs = [m for m in data["messages"] if m.get("group_id") == group_id]
    msgs.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return msgs[:limit]


def get_message_count() -> Dict[str, int]:
    """Return total, inbound, outbound, and unread message counts."""
    data = _load()
    all_msgs = data["messages"]
    inbound = [m for m in all_msgs if m.get("direction") == "inbound"]
    outbound = [m for m in all_msgs if m.get("direction") == "outbound"]
    unread = [m for m in inbound if not m.get("read")]
    return {
        "total": len(all_msgs),
        "inbound": len(inbound),
        "outbound": len(outbound),
        "unread": len(unread),
    }
