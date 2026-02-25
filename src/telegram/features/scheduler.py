"""
Telegram message scheduler.

Scheduled messages are stored in ``data/telegram_scheduled.json`` and
dispatched by a background thread started lazily on first use.
Same pattern as the WhatsApp scheduler.
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

logger = logging.getLogger("telegram_agent")

_SCHEDULED_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "telegram_scheduled.json"
)
_lock = threading.Lock()
_scheduler_started = False


# ── Time parsing ──────────────────────────────────────────────────────────────

def _parse_send_time(send_time: str) -> Optional[datetime]:
    """
    Parse a send-time string into a datetime.

    Accepts ISO-8601 or natural language:
      'tomorrow 9am', 'Friday 3pm', '2026-12-25 18:00', 'in 2 hours'.
    """
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
    try:
        from dateutil import parser as _dp  # type: ignore
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


# ── Background dispatcher ─────────────────────────────────────────────────────

def _dispatch_loop() -> None:
    """Background thread: check every 30 seconds and send due messages."""
    from ..telegram_service import send_text

    while True:
        try:
            with _lock:
                items = _load_scheduled()
                now = datetime.now()
                remaining = []
                for item in items:
                    if item.get("status") != "pending":
                        remaining.append(item)
                        continue
                    try:
                        send_at = datetime.fromisoformat(item["send_at"])
                    except Exception:
                        remaining.append(item)
                        continue
                    if send_at <= now:
                        try:
                            send_text(item["chat_id"], item["text"])
                            item["status"] = "sent"
                            item["sent_at"] = now.isoformat()
                            logger.info(
                                "[Scheduler] Sent scheduled message %s to %s",
                                item["job_id"], item["chat_id"],
                            )
                        except Exception as exc:
                            item["status"] = "failed"
                            item["error"] = str(exc)
                            logger.error(
                                "[Scheduler] Failed to send %s: %s",
                                item["job_id"], exc,
                            )
                    remaining.append(item)
                _save_scheduled(remaining)
        except Exception as exc:
            logger.warning("[Scheduler] Dispatch error: %s", exc)
        time.sleep(30)


def _ensure_scheduler() -> None:
    global _scheduler_started
    if not _scheduler_started:
        _scheduler_started = True
        t = threading.Thread(target=_dispatch_loop, daemon=True, name="telegram-scheduler")
        t.start()
        logger.info("[Scheduler] Telegram message scheduler started.")


# ── Public API ────────────────────────────────────────────────────────────────

def schedule_message(
    chat_id: int | str,
    text: str,
    send_at: str,
) -> Dict[str, Any]:
    """
    Schedule a Telegram message to be sent at a future time.

    Args:
        chat_id: Target chat ID.
        text:    Message body.
        send_at: When to send — ISO datetime or natural language ('tomorrow 9am').
    """
    _ensure_scheduler()
    send_dt = _parse_send_time(send_at)
    if not send_dt:
        return {
            "status": "error",
            "message": f"Could not parse time '{send_at}'. Use ISO format or natural language.",
        }
    if send_dt <= datetime.now():
        return {
            "status": "error",
            "message": f"Scheduled time {send_dt.isoformat()} is in the past.",
        }

    job_id = str(uuid.uuid4())[:8]
    item = {
        "job_id": job_id,
        "chat_id": str(chat_id),
        "text": text,
        "send_at": send_dt.isoformat(),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    with _lock:
        items = _load_scheduled()
        items.append(item)
        _save_scheduled(items)

    return {
        "status": "success",
        "job_id": job_id,
        "chat_id": chat_id,
        "send_at": send_dt.strftime("%Y-%m-%d %H:%M"),
        "message": f"Message scheduled for {send_dt.strftime('%B %d at %I:%M %p')}. Job ID: {job_id}",
    }


def list_scheduled_messages() -> Dict[str, Any]:
    """List all pending scheduled Telegram messages."""
    with _lock:
        items = _load_scheduled()
    pending = [i for i in items if i.get("status") == "pending"]
    return {
        "status": "success",
        "count": len(pending),
        "scheduled": pending,
    }


def cancel_scheduled_message(job_id: str) -> Dict[str, Any]:
    """
    Cancel a pending scheduled message by its job ID.

    Args:
        job_id: The job_id returned when the message was scheduled.
    """
    with _lock:
        items = _load_scheduled()
        found = False
        for item in items:
            if item.get("job_id") == job_id and item.get("status") == "pending":
                item["status"] = "cancelled"
                item["cancelled_at"] = datetime.now().isoformat()
                found = True
                break
        _save_scheduled(items)

    if found:
        return {
            "status": "success",
            "job_id": job_id,
            "message": f"Scheduled message {job_id} cancelled.",
        }
    return {
        "status": "error",
        "message": f"No pending scheduled message found with job_id '{job_id}'.",
    }
