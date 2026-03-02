"""
Telegram Auto-Responder.

When a new inbound message arrives via the per-PA poller, this module
forwards it to the HubProcessor and sends the response back to the chat.

Configuration is entirely per-Personal-Assistant — stored in
data/assistants.json and injected as env vars by pa_poller_runner.py:
    TELEGRAM_AUTO_REPLY          — "true" / "false"
    TELEGRAM_AUTO_REPLY_PERSONA  — system prompt string

Auto-reply is skipped for:
  - Non-text messages (photos, stickers, etc.) with no caption
  - Bot messages (direction != inbound)

Special commands handled without the LLM:
  /start   — welcome message
  /reset   — clear conversation history for this chat
  /agents  — list the skill agents available to this PA
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("telegram_agent")

# Thread lock so concurrent messages from the same chat don't overlap
_reply_lock = threading.Lock()

# Telegram message length cap — messages longer than this are split
_TG_MAX_LEN = 4000  # slightly below the hard 4096 limit for safety

# Characters that can break Telegram Markdown v1 entity parsing
_MD_STRIP_TABLE = str.maketrans("", "", "*_`[]\\​")


def _plain_text(text: str) -> str:
    """Strip Telegram Markdown v1 entities from *text* so it can be sent
    safely as plain text (without parse_mode).  Used as a last-resort
    fallback when the API returns a ‘can’t parse entities’ error."""
    # Remove characters that Telegram Markdown v1 treats as formatting markers
    cleaned = text.translate(_MD_STRIP_TABLE)
    # Remove any remaining HTML entities that could cause issues
    cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
    return cleaned


def auto_reply_enabled() -> bool:
    """True if TELEGRAM_AUTO_REPLY env var is set to 'true' (default: True)."""
    env_val = os.environ.get("TELEGRAM_AUTO_REPLY", "").strip()
    if env_val:
        return env_val.lower() == "true"
    return True


def _get_persona() -> str:
    """Return the auto-reply persona from TELEGRAM_AUTO_REPLY_PERSONA env var."""
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

    cmd = text.strip()

    # ── Special commands ──────────────────────────────────────────────────────
    if cmd == "/start":
        _send_welcome(chat_id)
        return

    if cmd == "/reset":
        _handle_reset(chat_id)
        return

    if cmd in ("/agents", "/skills"):
        _handle_agents(chat_id)
        return

    # Skip other bot commands (they start with /)
    if cmd.startswith("/"):
        return

    with _reply_lock:
        _generate_and_send(chat_id, text)


def _send_welcome(chat_id: int | str) -> None:
    """Send a welcome message identifying the PA this bot belongs to."""
    pa_name = "Octa Bot Assistant"
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
        f"👋 Hi! I'm *{pa_name}*, your Octa Bot AI assistant.\n\n"
        "Send me any message and I'll get right to work. 😊\n\n"
        "**Commands:**\n"
        "• `/reset` — clear conversation history\n"
        "• `/agents` — list available skills"
    )
    try:
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message
        resp = send_text(chat_id, welcome)
        store_outbound_message(chat_id, welcome, message_id=resp.get("message_id", 0))
    except Exception as exc:
        logger.warning("[AutoReply] Failed to send welcome to %s: %s", chat_id, exc)


def _handle_reset(chat_id: int | str) -> None:
    """Clear conversation history for this chat and confirm."""
    try:
        session_id = f"telegram_{chat_id}"
        from src.agent.hub.processor import clear_session
        clear_session(session_id)

        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message
        msg = "🔄 *Conversation reset.* I've cleared our history — let's start fresh! 😊"
        resp = send_text(chat_id, msg)
        store_outbound_message(chat_id, msg, message_id=resp.get("message_id", 0))
        logger.info("[AutoReply] Reset conversation for chat %s", chat_id)
    except Exception as exc:
        logger.warning("[AutoReply] /reset failed for %s: %s", chat_id, exc)


def _handle_agents(chat_id: int | str) -> None:
    """Send a list of available skill agents to the user."""
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        lines = ["🤖 *Available Skills*\n"]
        _icons = {
            "email": "✉️", "drive": "📁", "files": "🗂️",
            "calendar": "📅", "stock_market": "📈", "whatsapp": "💬",
            "telegram": "✈️", "browser": "🌐", "linkedin": "💼",
            "habit_tracker": "📊", "scheduler": "🔔", "file_organizer": "🗃️",
        }
        for name, info in AGENT_REGISTRY.items():
            icon = _icons.get(name, "🔧")
            desc = info.get("description", "")[:60]
            lines.append(f"{icon} *{name.replace('_', ' ').title()}* — {desc}")
        msg = "\n".join(lines)
    except Exception:
        msg = "🤖 Skills are loading — try again in a moment."

    try:
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message
        resp = send_text(chat_id, msg)
        store_outbound_message(chat_id, msg, message_id=resp.get("message_id", 0))
    except Exception as exc:
        logger.warning("[AutoReply] /agents response failed for %s: %s", chat_id, exc)


def _generate_and_send(chat_id: int | str, user_text: str) -> None:
    """
    Forward the user's message to the HubProcessor (multi-agent brain),
    show real-time progress in the chat, and send the response back.

    Flow:
      1. sendChatAction typing  → shows "… is typing" immediately
      2. Send "⏳ Thinking…" placeholder
      3. on_progress callback → edit placeholder as processing advances
      4. Process via HubProcessor
      5. Edit placeholder with final reply
      6. If file artifacts produced → send them as documents
    """
    from .telegram_service import (
        send_text,
        edit_message_text,
        send_chat_action_api,
        send_document_file,
    )
    from .polling.message_store import store_outbound_message

    # Show "typing…" in the chat immediately (gives instant feedback)
    try:
        send_chat_action_api(chat_id, "typing")
    except Exception:
        pass

    # Send a placeholder "Thinking…" message so users get visual feedback
    # while the LLM works (which can take 5–30 seconds).
    placeholder_id: Optional[int] = None
    try:
        ph_resp = send_text(chat_id, "⏳ *Thinking…*")
        placeholder_id = ph_resp.get("message_id")
    except Exception as exc:
        logger.debug("[AutoReply] Could not send placeholder to %s: %s", chat_id, exc)

    def _on_progress(status_text: str) -> None:
        """Edit the placeholder as processing advances."""
        if placeholder_id:
            try:
                send_chat_action_api(chat_id, "typing")
                edit_message_text(chat_id, placeholder_id, f"⏳ _{status_text}_")
            except Exception:
                pass

    try:
        from src.agent.hub.processor import HubProcessor

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
                pa_id   = pa["id"]   if pa else "_collective_memory_"
                pa_name = pa["name"] if pa else "Personal Assistant"
            except Exception:
                pa_id, pa_name = "_collective_memory_", "Personal Assistant"
        else:
            try:
                from .pa_router import get_pa_for_chat
                pa = get_pa_for_chat(chat_id)
                pa_id   = pa["id"]   if pa else "_collective_memory_"
                pa_name = pa["name"] if pa else "Personal Assistant"
            except Exception:
                pa_id, pa_name = "_collective_memory_", "Personal Assistant"

        processor = HubProcessor()
        result = processor.process(
            message=user_text,
            session_id=session_id,
            source="telegram",
            agent_id=pa_id,
            agent_name=pa_name,
            on_progress=_on_progress,
        )
        reply_text = result.response or "✅ Done."

        # ── Deliver the text reply ────────────────────────────────────────────
        # Edit the placeholder if it exists, otherwise send a fresh message.
        # Split messages that exceed Telegram's 4096-char limit.
        chunks = _split_message(reply_text)
        first_chunk = chunks[0]

        if placeholder_id:
            try:
                edit_message_text(chat_id, placeholder_id, first_chunk)
                store_outbound_message(chat_id, first_chunk, message_id=placeholder_id)
                # Send any overflow chunks as new messages
                for chunk in chunks[1:]:
                    r = send_text(chat_id, chunk)
                    store_outbound_message(chat_id, chunk, message_id=r.get("message_id", 0))
            except Exception:
                # edit_message_text can fail if message is identical or has markdown issues.
                # Fall back to a fresh sendMessage — use plain text to guarantee delivery.
                plain = _plain_text(first_chunk)
                r = send_text(chat_id, plain, parse_mode=None)
                store_outbound_message(chat_id, plain, message_id=r.get("message_id", 0))
                for chunk in chunks[1:]:
                    plain_chunk = _plain_text(chunk)
                    r = send_text(chat_id, plain_chunk, parse_mode=None)
                    store_outbound_message(chat_id, plain_chunk, message_id=r.get("message_id", 0))
        else:
            for chunk in chunks:
                r = send_text(chat_id, chunk)
                store_outbound_message(chat_id, chunk, message_id=r.get("message_id", 0))

        # ── Deliver file artifacts (download + send as document) ──────────────
        for fp in result.file_artifacts:
            try:
                fname = os.path.basename(fp)
                caption = f"📎 *{fname}* — file produced by your request"
                send_document_file(chat_id, fp, caption=caption)
                logger.info("[AutoReply] Sent file artifact %s to chat %s", fname, chat_id)
            except Exception as exc:
                logger.warning("[AutoReply] Could not send artifact %s: %s", fp, exc)
                # Notify user that a file exists but couldn't be sent
                try:
                    note = f"📎 A file was produced at `{fp}` but couldn't be delivered automatically."
                    send_text(chat_id, note)
                except Exception:
                    pass

        logger.info(
            "[AutoReply] Replied to chat %s via PA '%s' (%.1fs): %.60s",
            chat_id, pa_name, result.elapsed, reply_text,
        )

    except Exception as exc:
        logger.warning("[AutoReply] Failed to generate/send reply to %s: %s", chat_id, exc)
        # If placeholder exists, edit it to show the error — use plain text to avoid
        # another entity-parse failure on the error message itself.
        if placeholder_id:
            try:
                err_msg = f"\u274c Something went wrong: {exc}"
                edit_message_text(chat_id, placeholder_id, err_msg, parse_mode=None)
            except Exception:
                pass


def _split_message(text: str) -> list[str]:
    """
    Split a long message into chunks of at most _TG_MAX_LEN characters,
    preferring to break at paragraph boundaries (double newlines).
    """
    if len(text) <= _TG_MAX_LEN:
        return [text]

    chunks: list[str] = []
    while len(text) > _TG_MAX_LEN:
        # Try to split at a paragraph boundary near the limit
        cut = text.rfind("\n\n", 0, _TG_MAX_LEN)
        if cut == -1 or cut < _TG_MAX_LEN // 2:
            # No good paragraph break — split at a line break
            cut = text.rfind("\n", 0, _TG_MAX_LEN)
        if cut == -1 or cut < _TG_MAX_LEN // 2:
            # Hard split at the limit
            cut = _TG_MAX_LEN
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks
