"""
WhatsApp message scheduler.

Scheduled messages are stored in ``data/whatsapp_scheduled.json`` and
dispatched by a background thread (started lazily on first scheduling call).

This follows the exact same pattern as the email scheduler.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("whatsapp_agent")

_SCHEDULED_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "whatsapp_scheduled.json"
)
_AUTO_REPLY_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "whatsapp_auto_reply.json"
)
_lock = threading.Lock()
_scheduler_started = False


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_send_time(send_time: str) -> Optional[datetime]:
    """
    Parse a send time string into a datetime.

    Accepts ISO-8601 or natural-language strings like:
    'tomorrow 9am', 'Friday 3pm', '2025-12-25 18:00'.
    Falls back to LLM-based parsing if dateutil is unavailable.
    """
    # Try ISO format first
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(send_time.strip(), fmt)
        except ValueError:
            continue

    # Try dateutil (optional dependency)
    try:
        from dateutil import parser as _dp, relativedelta as _rd  # type: ignore
        return _dp.parse(send_time, fuzzy=True)
    except Exception:
        pass

    logger.warning("Could not parse send_time: %s", send_time)
    return None


# ── Store I/O ─────────────────────────────────────────────────────────────────

def _load_scheduled() -> List[Dict[str, Any]]:
    try:
        if _SCHEDULED_PATH.exists():
            return json.loads(_SCHEDULED_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load scheduled messages: %s", exc)
    return []


def _save_scheduled(items: List[Dict[str, Any]]) -> None:
    _SCHEDULED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SCHEDULED_PATH.write_text(
        json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_auto_reply() -> Dict[str, Any]:
    try:
        if _AUTO_REPLY_PATH.exists():
            return json.loads(_AUTO_REPLY_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"enabled": False, "message": ""}


def _save_auto_reply(config: Dict[str, Any]) -> None:
    _AUTO_REPLY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _AUTO_REPLY_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Background dispatcher ─────────────────────────────────────────────────────

def _dispatcher_loop() -> None:
    """Background thread: check every 30 seconds and dispatch due messages."""
    from .messaging import send_message as _send

    while True:
        try:
            now = datetime.now()
            with _lock:
                items = _load_scheduled()
                remaining = []
                for item in items:
                    if item.get("status") != "pending":
                        remaining.append(item)
                        continue
                    dt = _parse_send_time(item.get("send_time", ""))
                    if dt and dt <= now:
                        logger.info(
                            "Dispatching scheduled message %s to %s",
                            item["id"], item["to"],
                        )
                        result = _send(item["to"], item["body"])
                        item["status"] = (
                            "sent" if result.get("status") == "success" else "failed"
                        )
                        item["dispatched_at"] = now.isoformat()
                    remaining.append(item)
                _save_scheduled(remaining)
        except Exception as exc:
            logger.error("Scheduler loop error: %s", exc)
        time.sleep(30)


def _ensure_scheduler_started() -> None:
    global _scheduler_started
    if not _scheduler_started:
        t = threading.Thread(
            target=_dispatcher_loop, daemon=True, name="whatsapp-scheduler",
        )
        t.start()
        _scheduler_started = True
        logger.info("WhatsApp scheduler started")


# ── Public API ────────────────────────────────────────────────────────────────

def schedule_message(to: str, body: str, send_time: str) -> Dict[str, Any]:
    """
    Schedule a WhatsApp message for future delivery.

    Args:
        to:        Recipient phone (E.164).
        body:      Message text.
        send_time: When to send — ISO string or natural language ('tomorrow 9am').
    """
    try:
        dt = _parse_send_time(send_time)
        if not dt:
            return {
                "status": "error",
                "message": f"Could not parse send_time: '{send_time}'. "
                           "Use an ISO date like '2025-12-25 09:00' or "
                           "natural language like 'tomorrow 9am'.",
            }
        if dt <= datetime.now():
            return {
                "status": "error",
                "message": f"send_time '{send_time}' is in the past. "
                           "Please provide a future date/time.",
            }

        item: Dict[str, Any] = {
            "id": str(uuid.uuid4())[:8],
            "to": to,
            "body": body,
            "send_time": dt.isoformat(),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }

        with _lock:
            items = _load_scheduled()
            items.append(item)
            _save_scheduled(items)

        _ensure_scheduler_started()

        return {
            "status": "success",
            "scheduled_id": item["id"],
            "to": to,
            "send_time": dt.strftime("%Y-%m-%d %H:%M"),
            "message": f"Message scheduled for {dt.strftime('%Y-%m-%d %H:%M')}",
        }
    except Exception as exc:
        logger.error("schedule_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def list_scheduled_messages() -> Dict[str, Any]:
    """List all pending scheduled WhatsApp messages."""
    try:
        items = _load_scheduled()
        pending = [i for i in items if i.get("status") == "pending"]
        return {
            "status": "success",
            "scheduled_messages": pending,
            "count": len(pending),
        }
    except Exception as exc:
        logger.error("list_scheduled_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def cancel_scheduled_message(scheduled_id: str) -> Dict[str, Any]:
    """
    Cancel a pending scheduled message.

    Args:
        scheduled_id: The ID returned by schedule_message.
    """
    try:
        with _lock:
            items = _load_scheduled()
            matched = [i for i in items if i["id"] == scheduled_id]
            if not matched:
                return {
                    "status": "error",
                    "message": f"Scheduled message '{scheduled_id}' not found.",
                }
            item = matched[0]
            if item.get("status") != "pending":
                return {
                    "status": "error",
                    "message": f"Message '{scheduled_id}' is already {item.get('status')} and cannot be cancelled.",
                }
            item["status"] = "cancelled"
            item["cancelled_at"] = datetime.now().isoformat()
            _save_scheduled(items)

        return {
            "status": "success",
            "scheduled_id": scheduled_id,
            "message": f"Scheduled message '{scheduled_id}' cancelled",
        }
    except Exception as exc:
        logger.error("cancel_scheduled_message failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def set_auto_reply(enabled: bool, message: str = "") -> Dict[str, Any]:
    """
    Enable or disable automatic replies to all inbound messages.

    When enabled, the WhatsApp agent will automatically reply to every
    inbound message with the configured message text.

    Args:
        enabled: True to turn on auto-reply, False to turn off.
        message: Auto-reply text (required when enabled=True).
    """
    try:
        if enabled and not message.strip():
            return {
                "status": "error",
                "message": "A message text is required when enabling auto-reply.",
            }
        config = {"enabled": enabled, "message": message.strip()}
        _save_auto_reply(config)
        state = "enabled" if enabled else "disabled"
        return {
            "status": "success",
            "auto_reply_enabled": enabled,
            "message": f"Auto-reply {state}." + (f" Reply text: '{message}'" if enabled else ""),
        }
    except Exception as exc:
        logger.error("set_auto_reply failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_auto_reply_config() -> Dict[str, Any]:
    """Get the current auto-reply configuration."""
    try:
        config = _load_auto_reply()
        return {"status": "success", **config}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
