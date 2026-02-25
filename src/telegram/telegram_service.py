"""
Telegram Bot API — low-level REST client.

All HTTP interactions with the Bot API live here.  Feature modules
call these helpers instead of using requests directly, keeping error
handling and retry logic in a single place.

Bot API reference: https://core.telegram.org/bots/api
Base URL: https://api.telegram.org/bot{token}/{method}
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from .telegram_auth import get_bot_token

logger = logging.getLogger("telegram_agent")

_TIMEOUT = 20  # seconds for regular calls


def _base_url() -> str:
    return f"https://api.telegram.org/bot{get_bot_token()}"


def _unwrap(response: requests.Response) -> Dict[str, Any]:
    """Raise on API errors and return the parsed result field."""
    try:
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as exc:
        body: Any = {}
        try:
            body = response.json()
        except Exception:
            pass
        err = body.get("description", str(exc)) if isinstance(body, dict) else str(exc)
        logger.error("Telegram API HTTP error: %s | body=%s", exc, body)
        raise RuntimeError(f"Telegram API error: {err}") from exc

    if not data.get("ok"):
        err = data.get("description", "Unknown error")
        logger.error("Telegram API returned ok=false: %s", data)
        raise RuntimeError(f"Telegram API error: {err}")

    return data.get("result", {})


# ── Bot info ──────────────────────────────────────────────────────────────────

def get_me() -> Dict[str, Any]:
    """Return information about the bot itself (tests auth)."""
    resp = requests.get(f"{_base_url()}/getMe", timeout=_TIMEOUT)
    return _unwrap(resp)


# ── Message sending ───────────────────────────────────────────────────────────

def send_text(
    chat_id: int | str,
    text: str,
    parse_mode: str = "Markdown",
    reply_to_message_id: Optional[int] = None,
    disable_notification: bool = False,
) -> Dict[str, Any]:
    """Send a plain-text message to a chat."""
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    resp = requests.post(f"{_base_url()}/sendMessage", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def send_photo(
    chat_id: int | str,
    photo: str,
    caption: str = "",
    reply_to_message_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Send a photo by URL or file_id."""
    payload: Dict[str, Any] = {"chat_id": chat_id, "photo": photo}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "Markdown"
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    resp = requests.post(f"{_base_url()}/sendPhoto", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def send_document(
    chat_id: int | str,
    document: str,
    caption: str = "",
    filename: str = "",
) -> Dict[str, Any]:
    """Send a document by URL or file_id."""
    payload: Dict[str, Any] = {"chat_id": chat_id, "document": document}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "Markdown"
    resp = requests.post(f"{_base_url()}/sendDocument", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def send_video(
    chat_id: int | str,
    video: str,
    caption: str = "",
) -> Dict[str, Any]:
    """Send a video by URL or file_id."""
    payload: Dict[str, Any] = {"chat_id": chat_id, "video": video}
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = "Markdown"
    resp = requests.post(f"{_base_url()}/sendVideo", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def send_audio(
    chat_id: int | str,
    audio: str,
    caption: str = "",
    title: str = "",
) -> Dict[str, Any]:
    """Send an audio file by URL or file_id."""
    payload: Dict[str, Any] = {"chat_id": chat_id, "audio": audio}
    if caption:
        payload["caption"] = caption
    if title:
        payload["title"] = title
    resp = requests.post(f"{_base_url()}/sendAudio", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def send_sticker(chat_id: int | str, sticker: str) -> Dict[str, Any]:
    """Send a sticker by file_id or URL."""
    payload = {"chat_id": chat_id, "sticker": sticker}
    resp = requests.post(f"{_base_url()}/sendSticker", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def send_voice(chat_id: int | str, voice: str, caption: str = "") -> Dict[str, Any]:
    """Send a voice message by file_id or URL."""
    payload: Dict[str, Any] = {"chat_id": chat_id, "voice": voice}
    if caption:
        payload["caption"] = caption
    resp = requests.post(f"{_base_url()}/sendVoice", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def send_media_group(
    chat_id: int | str,
    media: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Send a group of photos/videos as an album.

    media is a list of InputMedia* dicts:
      [{"type": "photo", "media": "url_or_file_id", "caption": "..."}]
    """
    payload = {"chat_id": chat_id, "media": media}
    resp = requests.post(f"{_base_url()}/sendMediaGroup", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)  # type: ignore[return-value]


def forward_message_api(
    chat_id: int | str,
    from_chat_id: int | str,
    message_id: int,
) -> Dict[str, Any]:
    """Forward a message from one chat to another."""
    payload = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    resp = requests.post(f"{_base_url()}/forwardMessage", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def edit_message_text(
    chat_id: int | str,
    message_id: int,
    text: str,
    parse_mode: str = "Markdown",
) -> Dict[str, Any]:
    """Edit the text of a previously sent message."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    resp = requests.post(f"{_base_url()}/editMessageText", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def delete_message_api(chat_id: int | str, message_id: int) -> bool:
    """Delete a message. Returns True on success."""
    payload = {"chat_id": chat_id, "message_id": message_id}
    resp = requests.post(f"{_base_url()}/deleteMessage", json=payload, timeout=_TIMEOUT)
    return bool(_unwrap(resp))


def send_chat_action_api(chat_id: int | str, action: str) -> bool:
    """
    Send a chat action indicator (typing, upload_photo, etc.).

    Common actions: typing, upload_photo, record_video, upload_video,
                    record_voice, upload_voice, upload_document, find_location
    """
    payload = {"chat_id": chat_id, "action": action}
    resp = requests.post(f"{_base_url()}/sendChatAction", json=payload, timeout=_TIMEOUT)
    return bool(_unwrap(resp))


# ── Updates / polling ─────────────────────────────────────────────────────────

def get_updates(
    offset: Optional[int] = None,
    limit: int = 100,
    timeout: int = 10,
    allowed_updates: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch pending updates from the Bot API.

    offset: Pass (last_update_id + 1) to confirm and skip previous updates.
    timeout: Long-polling timeout in seconds.
    """
    payload: Dict[str, Any] = {"limit": limit, "timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    if allowed_updates:
        payload["allowed_updates"] = allowed_updates

    resp = requests.post(
        f"{_base_url()}/getUpdates",
        json=payload,
        timeout=timeout + 15,  # client timeout must be > long-poll timeout
    )
    result = _unwrap(resp)
    return result if isinstance(result, list) else []


# ── Chat info ─────────────────────────────────────────────────────────────────

def get_chat_api(chat_id: int | str) -> Dict[str, Any]:
    """Return info about a chat (private, group, channel, supergroup)."""
    resp = requests.get(
        f"{_base_url()}/getChat",
        params={"chat_id": chat_id},
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def get_chat_member_count(chat_id: int | str) -> int:
    """Return the number of members in a chat."""
    resp = requests.get(
        f"{_base_url()}/getChatMemberCount",
        params={"chat_id": chat_id},
        timeout=_TIMEOUT,
    )
    result = _unwrap(resp)
    return int(result) if isinstance(result, int) else 0


def get_chat_member(chat_id: int | str, user_id: int) -> Dict[str, Any]:
    """Return info about a member in a chat."""
    resp = requests.post(
        f"{_base_url()}/getChatMember",
        json={"chat_id": chat_id, "user_id": user_id},
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def get_chat_administrators(chat_id: int | str) -> List[Dict[str, Any]]:
    """Return a list of administrators in a chat."""
    resp = requests.post(
        f"{_base_url()}/getChatAdministrators",
        json={"chat_id": chat_id},
        timeout=_TIMEOUT,
    )
    result = _unwrap(resp)
    return result if isinstance(result, list) else []


def pin_chat_message_api(
    chat_id: int | str,
    message_id: int,
    disable_notification: bool = False,
) -> bool:
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "disable_notification": disable_notification,
    }
    resp = requests.post(f"{_base_url()}/pinChatMessage", json=payload, timeout=_TIMEOUT)
    return bool(_unwrap(resp))


def unpin_chat_message_api(
    chat_id: int | str,
    message_id: Optional[int] = None,
) -> bool:
    payload: Dict[str, Any] = {"chat_id": chat_id}
    if message_id:
        payload["message_id"] = message_id
    resp = requests.post(f"{_base_url()}/unpinChatMessage", json=payload, timeout=_TIMEOUT)
    return bool(_unwrap(resp))


def leave_chat_api(chat_id: int | str) -> bool:
    """Make the bot leave a group, supergroup, or channel."""
    resp = requests.post(
        f"{_base_url()}/leaveChat",
        json={"chat_id": chat_id},
        timeout=_TIMEOUT,
    )
    return bool(_unwrap(resp))


# ── Files ─────────────────────────────────────────────────────────────────────

def get_file_api(file_id: str) -> Dict[str, Any]:
    """Return file info (path). Use to build a download URL."""
    resp = requests.get(
        f"{_base_url()}/getFile",
        params={"file_id": file_id},
        timeout=_TIMEOUT,
    )
    return _unwrap(resp)


def get_file_download_url(file_id: str) -> str:
    """Return the full download URL for a file by its file_id."""
    info = get_file_api(file_id)
    file_path = info.get("file_path", "")
    token = get_bot_token()
    return f"https://api.telegram.org/file/bot{token}/{file_path}"


# ── Polls ─────────────────────────────────────────────────────────────────────

def send_poll_api(
    chat_id: int | str,
    question: str,
    options: List[str],
    is_anonymous: bool = True,
    allows_multiple_answers: bool = False,
    correct_option_id: Optional[int] = None,
    explanation: str = "",
) -> Dict[str, Any]:
    """Create a native Telegram poll."""
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "question": question,
        "options": options,
        "is_anonymous": is_anonymous,
        "allows_multiple_answers": allows_multiple_answers,
    }
    if correct_option_id is not None:
        payload["type"] = "quiz"
        payload["correct_option_id"] = correct_option_id
    if explanation:
        payload["explanation"] = explanation
    resp = requests.post(f"{_base_url()}/sendPoll", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)


def stop_poll_api(chat_id: int | str, message_id: int) -> Dict[str, Any]:
    """Stop an active poll. Returns the final Poll object."""
    payload = {"chat_id": chat_id, "message_id": message_id}
    resp = requests.post(f"{_base_url()}/stopPoll", json=payload, timeout=_TIMEOUT)
    return _unwrap(resp)
