"""
Telegram long-polling background thread.

Calls getUpdates every 2 seconds (with a 10-second server-side timeout)
and writes inbound messages to the local message_store.

Usage — call start_poller_in_background() once per process:
    from src.telegram.polling.poller import start_poller_in_background
    start_poller_in_background()
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("telegram_agent")

_poll_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def _process_update(update: dict) -> None:
    """Extract and store one Telegram update."""
    from .message_store import store_inbound_message

    update_id = update.get("update_id", 0)

    # Regular message or channel post
    msg = update.get("message") or update.get("channel_post")
    if msg:
        store_inbound_message(msg, update_id=update_id)
        # Auto-reply: generate and send LLM response in a background thread
        # so the polling loop is never blocked.
        try:
            from ..auto_responder import maybe_auto_reply
            import threading as _threading
            _threading.Thread(
                target=maybe_auto_reply,
                args=({
                    "text": msg.get("text"),
                    "caption": msg.get("caption"),
                    "chat_id": msg.get("chat", {}).get("id"),
                    "direction": "inbound",
                    "media_type": None,
                },),
                daemon=True,
            ).start()
        except Exception as _exc:
            logger.warning("[Poller] auto_responder import error: %s", _exc)
        return

    # Edited message — update existing record (best-effort)
    edited = update.get("edited_message") or update.get("edited_channel_post")
    if edited:
        # Just treat it as a new entry with a note
        edited_copy = dict(edited)
        if "text" in edited_copy:
            edited_copy["text"] = "[edited] " + edited_copy["text"]
        store_inbound_message(edited_copy, update_id=update_id)
        return

    # Everything else (callback_query, inline_query, etc.) — ignore for now


def _poll_loop() -> None:
    """Main polling loop. Runs until _stop_event is set."""
    from .message_store import get_offset, set_offset
    from ..telegram_service import get_updates

    logger.info("[Poller] Background polling loop started.")

    while not _stop_event.is_set():
        try:
            offset = get_offset()
            updates = get_updates(offset=offset if offset else None, limit=100, timeout=10)

            if updates:
                for upd in updates:
                    try:
                        _process_update(upd)
                    except Exception as exc:
                        logger.warning("[Poller] Failed to process update %s: %s",
                                       upd.get("update_id"), exc)

                # Advance offset past the last processed update
                last_id = max(u["update_id"] for u in updates)
                set_offset(last_id + 1)
                logger.debug("[Poller] Processed %d updates, new offset=%d",
                             len(updates), last_id + 1)

        except Exception as exc:
            # Don't crash the thread on transient network errors
            logger.warning("[Poller] getUpdates error: %s", exc)
            err_str = str(exc)
            if "409" in err_str or "Conflict" in err_str:
                # 409 means a newer poller has taken over this bot token.
                # Count consecutive conflicts; after 5 we self-terminate so
                # stale pollers don't loop forever in the background.
                _poll_loop.conflict_count = getattr(_poll_loop, "conflict_count", 0) + 1
                if _poll_loop.conflict_count >= 5:
                    logger.info(
                        "[Poller] 5 consecutive 409 Conflicts — this poller has been "
                        "superseded. Exiting."
                    )
                    import sys as _sys
                    _sys.exit(0)
                logger.info(
                    "[Poller] 409 Conflict (%d/5) — another poller has claimed this token.",
                    _poll_loop.conflict_count,
                )
                time.sleep(5)
            else:
                _poll_loop.conflict_count = 0  # reset on non-409 error
                time.sleep(5)  # back off briefly for other errors
            continue

        _poll_loop.conflict_count = 0  # reset on successful poll

        # Small sleep between polls to avoid hammering the API when quiet
        time.sleep(2)

    logger.info("[Poller] Background polling loop stopped.")


def start_poller_in_background() -> threading.Thread:
    """
    Start the Telegram long-polling thread if not already running.

    Safe to call multiple times — only one thread will be created.
    Returns the thread object.
    """
    global _poll_thread

    if _poll_thread and _poll_thread.is_alive():
        logger.debug("[Poller] Already running (thread id=%s)", _poll_thread.ident)
        return _poll_thread

    _stop_event.clear()
    _poll_thread = threading.Thread(
        target=_poll_loop,
        name="telegram-poller",
        daemon=True,  # dies when the main process exits
    )
    _poll_thread.start()
    logger.info("[Poller] Started daemon thread id=%s", _poll_thread.ident)
    return _poll_thread


def stop_poller() -> None:
    """Signal the polling thread to stop gracefully."""
    _stop_event.set()
    if _poll_thread:
        _poll_thread.join(timeout=15)
    logger.info("[Poller] Stopped.")
