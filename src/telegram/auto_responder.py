"""
Telegram Auto-Responder.

When a new inbound message arrives via the per-PA poller, this module
forwards it to the HubProcessor and sends the response back to the chat.

Configuration is entirely per-Personal-Assistant — stored in
data/assistants.json and injected as env vars by pa_poller_runner.py:
    TELEGRAM_AUTO_REPLY          — "true" / "false"
    TELEGRAM_AUTO_REPLY_PERSONA  — system prompt string

Auto-reply is skipped for:
  - Bot commands (/start, /help, etc.) — those just get a welcome message
  - Messages the bot itself sent (outbound)
  - Non-text messages (photos, stickers, etc.) with no caption
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict

logger = logging.getLogger("telegram_agent")

# Thread lock so concurrent messages from the same chat don't overlap
_reply_lock = threading.Lock()


def auto_reply_enabled() -> bool:
    """True if TELEGRAM_AUTO_REPLY env var is set to 'true' (default: True).

    Set by pa_poller_runner from the PA's config.telegram.auto_reply field.
    Defaults to True if the env var is absent (opt-in is the safe default).
    """
    env_val = os.environ.get("TELEGRAM_AUTO_REPLY", "").strip()
    if env_val:
        return env_val.lower() == "true"
    return True  # default on if PA hasn't configured it yet


def _get_persona() -> str:
    """Return the auto-reply persona from TELEGRAM_AUTO_REPLY_PERSONA env var.

    Set by pa_poller_runner from the PA's config.telegram.auto_reply_persona.
    Falls back to a generic persona if not set.
    """
    env_val = os.environ.get("TELEGRAM_AUTO_REPLY_PERSONA", "").strip()
    if env_val:
        return env_val
    return "You are a friendly, helpful AI assistant. Keep replies concise and conversational."


# ── Main entry point ──────────────────────────────────────────────────────────

def maybe_auto_reply(stored_message: Dict[str, Any]) -> None:
    """
    Called by the poller after storing an inbound message.
    Generates an LLM reply and sends it back to the sender.

    This runs in the poller background thread — any exception is caught and
    logged so it never crashes the polling loop.
    """
    if not auto_reply_enabled():
        return

    text = stored_message.get("text") or stored_message.get("caption", "")
    chat_id = stored_message.get("chat_id")
    direction = stored_message.get("direction", "inbound")

    # Only reply to real inbound text messages
    if direction != "inbound" or not text or not chat_id:
        return

    # Handle /start — send welcome
    if text.strip() == "/start":
        _send_welcome(chat_id)
        return

    # Skip other bot commands (they start with /)
    if text.strip().startswith("/"):
        return

    with _reply_lock:
        _generate_and_send(chat_id, text)


def _send_welcome(chat_id: int | str) -> None:
    """Send a welcome message identifying the PA this bot belongs to."""
    pa_name = "OctaMind Assistant"
    try:
        pa_id_env = os.environ.get("PA_ID", "").strip()
        if pa_id_env:
            from src.agent.hub.pa_manager import get_assistant
            pa = get_assistant(pa_id_env)
            if pa:
                pa_name = pa["name"]
    except Exception:
        pass
    welcome = (
        f"👋 Hi! I'm *{pa_name}*, your OctaMind AI assistant.\n\n"
        "Send me any message and I'll get right to work. 😊"
    )
    try:
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message
        resp = send_text(chat_id, welcome)
        store_outbound_message(chat_id, welcome, message_id=resp.get("message_id", 0))
    except Exception as exc:
        logger.warning("[AutoReply] Failed to send welcome to %s: %s", chat_id, exc)


def _generate_and_send(chat_id: int | str, user_text: str) -> None:
    """
    Forward the user's message to the HubProcessor (multi-agent brain)
    and send the response back to the Telegram chat.
    """
    try:
        from src.agent.hub.processor import HubProcessor
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message

        # Use a stable session_id so the hub maintains per-chat history
        session_id = f"telegram_{chat_id}"

        # Per-PA poller: PA_ID env var is set by the poller process — always
        # route to that specific PA.  Legacy global poller: fall back to
        # the routing table (chat_id → pa mapping).
        pa_id_env = os.environ.get("PA_ID", "").strip()
        if pa_id_env:
            try:
                from src.agent.hub.pa_manager import get_assistant
                pa = get_assistant(pa_id_env)
                pa_id   = pa["id"]   if pa else "__multi_agent__"
                pa_name = pa["name"] if pa else "Personal Assistant"
            except Exception:
                pa_id, pa_name = "__multi_agent__", "Personal Assistant"
        else:
            # Legacy global poller — use routing table or default first PA
            try:
                from .pa_router import get_pa_for_chat
                pa = get_pa_for_chat(chat_id)
                pa_id   = pa["id"]   if pa else "__multi_agent__"
                pa_name = pa["name"] if pa else "Personal Assistant"
            except Exception:
                pa_id, pa_name = "__multi_agent__", "Personal Assistant"

        processor = HubProcessor()
        result = processor.process(
            message=user_text,
            session_id=session_id,
            source="telegram",
            agent_id=pa_id,
            agent_name=pa_name,
        )
        reply_text = result.response

        if not reply_text:
            return

        resp = send_text(chat_id, reply_text)
        store_outbound_message(chat_id, reply_text, message_id=resp.get("message_id", 0))
        logger.info(
            "[AutoReply] Replied to chat %s via PA '%s' (%.1fs): %.60s",
            chat_id, pa_name, result.elapsed, reply_text,
        )

    except Exception as exc:
        logger.warning("[AutoReply] Failed to generate/send reply to %s: %s", chat_id, exc)
