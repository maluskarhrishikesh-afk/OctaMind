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
    /agents  — list available and enabled skill agents for this PA
    /skills  — show enabled and disabled skills for this PA
    /enable <skill>  — enable a skill for this PA
    /disable <skill> — disable a skill for this PA
        /auth <calendar|email|drive> — start Google auth in Telegram
        /authcomplete <redirect-url> — finish Google auth from a pasted redirect URL
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("telegram_agent")

# Thread lock so concurrent messages from the same chat don't overlap
_reply_lock = threading.Lock()

# Telegram message length cap — messages longer than this are split
_TG_MAX_LEN = 4000  # slightly below the hard 4096 limit for safety

# Characters that can break Telegram Markdown v1 entity parsing
_MD_STRIP_TABLE = str.maketrans("", "", "*_`[]\\\u200B")
_GOOGLE_AUTH_COMPLETE_RE = re.compile(r"(?:https?://localhost[^\s]+|\bcode=[^\s]+.*\bstate=[^\s]+)", re.IGNORECASE)


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

    if cmd == "/status":
        _handle_status(chat_id)
        return

    if cmd in ("/agents", "/skills"):
        _handle_agents(chat_id)
        return

    if cmd.lower().startswith("/enable "):
        _handle_skill_toggle(chat_id, cmd.split(" ", 1)[1], enable=True)
        return

    if cmd.lower().startswith("/disable "):
        _handle_skill_toggle(chat_id, cmd.split(" ", 1)[1], enable=False)
        return

    if cmd.lower().startswith("/authcomplete "):
        _handle_google_auth_complete(chat_id, cmd.split(" ", 1)[1])
        return

    if cmd.lower() == "/authcomplete":
        _handle_google_auth_complete(chat_id, "")
        return

    if cmd.lower().startswith("/auth "):
        _handle_google_auth_start(chat_id, cmd.split(" ", 1)[1])
        return

    if cmd.lower() == "/auth":
        _handle_google_auth_start(chat_id, "")
        return

    if _looks_like_google_auth_completion_payload(cmd):
        _handle_google_auth_complete(chat_id, cmd)
        return

    # Skip other bot commands (they start with /)
    if cmd.startswith("/"):
        return

    with _reply_lock:
        _generate_and_send(chat_id, text)


def maybe_handle_callback_query(callback_query: Dict[str, Any]) -> None:
    """Handle Telegram inline-button taps for critical confirmations."""
    data = str(callback_query.get("data", "") or "").strip()
    callback_id = str(callback_query.get("id", "") or "").strip()
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")

    if not data or not chat_id or not callback_id:
        return

    if not (data.startswith("mailbox_cleanup:") or data.startswith("destructive_action:")):
        return

    from .telegram_service import answer_callback_query, edit_message_reply_markup

    synthetic_text = _callback_query_to_user_text(data)
    if not synthetic_text:
        try:
            answer_callback_query(callback_id, text="Unsupported action")
        except Exception:
            pass
        return

    try:
        answer_callback_query(callback_id, text="Working on it...")
    except Exception:
        pass

    try:
        if message_id:
            edit_message_reply_markup(chat_id, int(message_id), {"inline_keyboard": []})
    except Exception:
        pass

    with _reply_lock:
        _generate_and_send(chat_id, synthetic_text)


def _callback_query_to_user_text(callback_data: str) -> str:
    parts = str(callback_data or "").split(":", 2)
    if len(parts) != 3:
        return ""

    if parts[0] == "destructive_action":
        decision, action_key = parts[1], parts[2]
        if decision == "cancel":
            return f"cancel action {action_key}"
        if decision == "confirm":
            return f"confirm action {action_key}"
        return ""

    if parts[0] != "mailbox_cleanup":
        return ""

    decision, action = parts[1], parts[2]
    if decision == "cancel":
        return "cancel"
    if decision != "confirm":
        return ""
    if action == "delete_all_filters_and_labels":
        return "confirm delete all filters and labels"
    if action == "delete_all_filters":
        return "confirm delete all filters"
    return ""


def _telegram_reply_markup(result: Any) -> Optional[Dict[str, Any]]:
    payloads = getattr(result, "channel_payloads", {}) or {}
    if not isinstance(payloads, dict):
        return None
    telegram_payload = payloads.get("telegram", {})
    if not isinstance(telegram_payload, dict):
        return None
    reply_markup = telegram_payload.get("reply_markup")
    return reply_markup if isinstance(reply_markup, dict) else None


def _resolve_current_pa(chat_id: int | str) -> tuple[str, str]:
    """Resolve the current Personal Assistant id/name for this Telegram chat."""
    pa_id_env = os.environ.get("PA_ID", "").strip()
    if pa_id_env:
        try:
            from src.agent.hub.pa_manager import get_assistant

            pa = get_assistant(pa_id_env)
            if pa:
                return str(pa.get("id") or "_collective_memory_"), str(pa.get("name") or "Personal Assistant")
        except Exception:
            pass
        return pa_id_env or "_collective_memory_", "Personal Assistant"

    try:
        from .pa_router import get_pa_for_chat

        pa = get_pa_for_chat(chat_id)
        if pa:
            return str(pa.get("id") or "_collective_memory_"), str(pa.get("name") or "Personal Assistant")
    except Exception:
        pass
    return "_collective_memory_", "Personal Assistant"


def _record_direct_command_turn(chat_id: int | str, user_text: str, assistant_text: str) -> None:
    """Persist direct Telegram command turns into shared hub/dashboard history."""
    try:
        from src.agent.hub.processor import log_external_turn

        pa_id, _ = _resolve_current_pa(chat_id)
        log_external_turn(
            session_id=f"telegram_{chat_id}",
            source="telegram",
            agent_id=pa_id,
            user_message=user_text,
            assistant_message=assistant_text,
        )
    except Exception as exc:
        logger.debug("[AutoReply] Direct command history persist skipped for %s: %s", chat_id, exc)


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
        "• `/status` — show runtime and reachability status\n"
        "• `/skills` — view enabled and available skills\n"
        "• `/enable files` — enable a skill\n"
        "• `/enable scheduler` — enable another skill\n"
        "• `/disable files` — disable a skill\n"
        "• `/auth calendar` — start Google Calendar sign-in\n"
        "• `/authcomplete <redirect-url>` — finish Google sign-in"
    )
    try:
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message
        resp = send_text(chat_id, welcome)
        store_outbound_message(chat_id, welcome, message_id=resp.get("message_id", 0))
        _record_direct_command_turn(chat_id, "/start", welcome)
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
        _record_direct_command_turn(chat_id, "/reset", msg)
        logger.info("[AutoReply] Reset conversation for chat %s", chat_id)
    except Exception as exc:
        logger.warning("[AutoReply] /reset failed for %s: %s", chat_id, exc)


def _handle_status(chat_id: int | str) -> None:
    """Send runtime and reachability status for this Telegram-connected assistant."""
    try:
        from src.agent.system.runtime_status import get_keep_awake_status
        from src.telegram.pa_poller_manager import get_pa_poller_status

        pa_id, pa_name = _resolve_current_pa(chat_id)
        keep_awake = get_keep_awake_status()
        poller_running = get_pa_poller_status(pa_id) is not None if pa_id and pa_id != "_collective_memory_" else True
        auto_reply_state = "On" if auto_reply_enabled() else "Off"

        msg = (
            f"📡 *Status for {pa_name}*\n\n"
            f"• Telegram bot: {'Running' if poller_running else 'Stopped'}\n"
            f"• Auto-reply: {auto_reply_state}\n"
            f"• Sleep protection: {keep_awake['label']}\n"
            f"• Detail: {keep_awake['detail']}\n\n"
            f"_Note: {keep_awake['hard_limit']}_"
        )

        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message

        resp = send_text(chat_id, msg)
        store_outbound_message(chat_id, msg, message_id=resp.get("message_id", 0))
        _record_direct_command_turn(chat_id, "/status", msg)
    except Exception as exc:
        logger.warning("[AutoReply] /status failed for %s: %s", chat_id, exc)


def _handle_agents(chat_id: int | str) -> None:
    """Send enabled and available skill agents for the current PA."""
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        pa_id_env = os.environ.get("PA_ID", "").strip()
        enabled_skills = set()
        pa_name = "this assistant"
        if pa_id_env:
            from src.agent.hub.pa_manager import get_assistant

            pa = get_assistant(pa_id_env)
            if pa:
                enabled_skills = {str(skill).strip() for skill in pa.get("skills", []) if str(skill).strip()}
                pa_name = pa.get("name") or pa_name

        lines = [f"🤖 *Skills for {pa_name}*\n"]
        _icons = {
            "email": "✉️", "drive": "📁", "files": "🗂️",
            "calendar": "📅", "stock_market": "📈", "whatsapp": "💬",
            "telegram": "✈️", "browser": "🌐", "linkedin": "💼",
            "habit_tracker": "📊", "scheduler": "🔔", "file_organizer": "🗃️",
        }
        enabled_lines = []
        disabled_lines = []
        for name in AGENT_REGISTRY:
            icon = _icons.get(name, "🔧")
            label = name.replace("_", " ").title()
            if name in enabled_skills:
                enabled_lines.append(f"{icon} *{label}*")
            else:
                disabled_lines.append(f"{icon} {label}")
        lines.append("✅ *Enabled*\n" + ("\n".join(enabled_lines) if enabled_lines else "None"))
        if disabled_lines:
            lines.append("\n➕ *Available to Enable*\n" + "\n".join(disabled_lines[:12]))
        sample_disabled = [name for name in AGENT_REGISTRY if name not in enabled_skills][:3]
        if sample_disabled:
            command_examples = ", ".join(f"`/enable {name.replace('_', ' ')}`" for name in sample_disabled)
            lines.append(f"\nUse {command_examples} to enable more skills here in Telegram.")
        else:
            lines.append("\nUse `/disable <skill>` if you want to turn a skill off here in Telegram.")
        lines.append("\nUse `/status` to check whether sleep protection is active on the laptop.")
        msg = "\n".join(lines)
    except Exception:
        msg = "🤖 Skills are loading — try again in a moment."

    try:
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message
        resp = send_text(chat_id, msg)
        store_outbound_message(chat_id, msg, message_id=resp.get("message_id", 0))
        _record_direct_command_turn(chat_id, "/skills", msg)
    except Exception as exc:
        logger.warning("[AutoReply] /agents response failed for %s: %s", chat_id, exc)


def _normalize_skill_name(raw_name: str) -> str:
    return str(raw_name or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_google_auth_service(raw_name: str) -> str:
    value = _normalize_skill_name(raw_name)
    aliases = {
        "gmail": "email",
        "mail": "email",
        "gdrive": "drive",
        "google_drive": "drive",
        "google_calendar": "calendar",
        "scheduler": "calendar",
    }
    return aliases.get(value, value)


def _looks_like_google_auth_completion_payload(text: str) -> bool:
    return bool(_GOOGLE_AUTH_COMPLETE_RE.search(str(text or "")))


def _handle_google_auth_start(chat_id: int | str, raw_service: str) -> None:
    try:
        from src.agent.hub.google_auth_session import build_telegram_google_auth_reply
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message

        service = _normalize_google_auth_service(raw_service)
        if service not in {"calendar", "email", "drive"}:
            msg = "Use `/auth calendar`, `/auth email`, or `/auth drive` to start Google sign-in."
        else:
            msg = build_telegram_google_auth_reply([service], force=True, session_id=f"telegram_{chat_id}") or (
                f"{service.title()} is already authorized. If you want to re-authorize it, try `/auth {service}` again in a moment."
            )

        resp = send_text(chat_id, msg)
        store_outbound_message(chat_id, msg, message_id=resp.get("message_id", 0))
        _record_direct_command_turn(chat_id, f"/auth {raw_service}".strip(), msg)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.warning("[AutoReply] /auth failed for %s: %s", chat_id, exc)


def _handle_google_auth_complete(chat_id: int | str, raw_payload: str) -> None:
    try:
        from src.agent.hub.google_auth_session import complete_google_auth_session
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message

        if not raw_payload.strip():
            msg = "Paste the full `http://localhost/...` redirect URL after `/authcomplete`, or just paste the URL directly into this chat."
        else:
            _, msg = complete_google_auth_session(raw_payload)

        resp = send_text(chat_id, msg)
        store_outbound_message(chat_id, msg, message_id=resp.get("message_id", 0))
        _record_direct_command_turn(chat_id, f"/authcomplete {raw_payload}".strip(), msg)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.warning("[AutoReply] /authcomplete failed for %s: %s", chat_id, exc)


def _handle_skill_toggle(chat_id: int | str, raw_skill: str, *, enable: bool) -> None:
    """Enable or disable a PA skill directly from Telegram."""
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        from src.agent.hub.pa_manager import get_assistant, update_assistant
        from .telegram_service import send_text
        from .polling.message_store import store_outbound_message

        pa_id_env = os.environ.get("PA_ID", "").strip()
        if not pa_id_env:
            msg = "⚠️ Skill changes are only supported for dedicated Personal Assistant bots."
        else:
            pa = get_assistant(pa_id_env)
            if not pa:
                msg = "⚠️ I could not find the assistant configuration for this bot."
            else:
                skill_name = _normalize_skill_name(raw_skill)
                if skill_name not in AGENT_REGISTRY:
                    available = ", ".join(sorted(AGENT_REGISTRY.keys()))
                    msg = f"⚠️ Unknown skill: `{skill_name}`.\n\nAvailable skills: {available}"
                else:
                    current_skills = [str(skill).strip() for skill in pa.get("skills", []) if str(skill).strip()]
                    if enable:
                        if skill_name in current_skills:
                            msg = f"✅ **{skill_name.replace('_', ' ').title()}** is already enabled for **{pa['name']}**."
                        else:
                            updated_skills = current_skills + [skill_name]
                            update_assistant(pa_id_env, skills=updated_skills)
                            msg = f"✅ Enabled **{skill_name.replace('_', ' ').title()}** for **{pa['name']}**."
                    else:
                        if skill_name not in current_skills:
                            msg = f"ℹ️ **{skill_name.replace('_', ' ').title()}** is not enabled for **{pa['name']}**."
                        else:
                            updated_skills = [skill for skill in current_skills if skill != skill_name]
                            update_assistant(pa_id_env, skills=updated_skills)
                            msg = f"✅ Disabled **{skill_name.replace('_', ' ').title()}** for **{pa['name']}**."

        resp = send_text(chat_id, msg)
        store_outbound_message(chat_id, msg, message_id=resp.get("message_id", 0))
        action = "/enable" if enable else "/disable"
        _record_direct_command_turn(chat_id, f"{action} {raw_skill}".strip(), msg)
    except Exception as exc:
        logger.warning("[AutoReply] skill toggle failed for %s: %s", chat_id, exc)


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
        reply_markup = _telegram_reply_markup(result)

        # ── Deliver the text reply ────────────────────────────────────────────
        # Edit the placeholder if it exists, otherwise send a fresh message.
        # Split messages that exceed Telegram's 4096-char limit.
        chunks = _split_message(reply_text)
        first_chunk = chunks[0]

        if placeholder_id:
            try:
                edit_message_text(chat_id, placeholder_id, first_chunk, reply_markup=reply_markup)
                store_outbound_message(chat_id, first_chunk, message_id=placeholder_id)
                # Send any overflow chunks as new messages
                for chunk in chunks[1:]:
                    r = send_text(chat_id, chunk)
                    store_outbound_message(chat_id, chunk, message_id=r.get("message_id", 0))
            except Exception:
                # edit_message_text can fail if message is identical or has markdown issues.
                # Fall back to a fresh sendMessage — use plain text to guarantee delivery.
                plain = _plain_text(first_chunk)
                r = send_text(chat_id, plain, parse_mode=None, reply_markup=reply_markup)
                store_outbound_message(chat_id, plain, message_id=r.get("message_id", 0))
                for chunk in chunks[1:]:
                    plain_chunk = _plain_text(chunk)
                    r = send_text(chat_id, plain_chunk, parse_mode=None)
                    store_outbound_message(chat_id, plain_chunk, message_id=r.get("message_id", 0))
        else:
            for index, chunk in enumerate(chunks):
                r = send_text(chat_id, chunk, reply_markup=reply_markup if index == 0 else None)
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
