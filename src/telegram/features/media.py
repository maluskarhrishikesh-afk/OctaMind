"""
Telegram media tools.

Handles sending photos, videos, audio, documents, stickers, voice messages,
and media groups (albums).  Also provides retrieval of media messages.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..telegram_service import (
    send_photo,
    send_video,
    send_audio,
    send_document,
    send_sticker,
    send_voice,
    send_media_group as _send_media_group_api,
    get_file_download_url,
)
from ..polling.message_store import store_outbound_message, get_messages_for_chat

logger = logging.getLogger("telegram_agent")

_MEDIA_TYPES = {"photo", "video", "audio", "document", "sticker", "voice",
                "animation", "video_note"}


def send_media(
    chat_id: int | str,
    media_type: str,
    url: str,
    caption: str = "",
    filename: str = "",
) -> Dict[str, Any]:
    """
    Send a media file to a Telegram chat.

    Args:
        chat_id:    Target chat.
        media_type: photo | video | audio | document | sticker | voice
        url:        Public HTTPS URL or file_id.
        caption:    Optional caption.
        filename:   Optional filename hint (for documents).
    """
    mtype = media_type.lower().strip()
    try:
        if mtype == "photo":
            resp = send_photo(chat_id, url, caption=caption)
        elif mtype == "video":
            resp = send_video(chat_id, url, caption=caption)
        elif mtype == "audio":
            resp = send_audio(chat_id, url, caption=caption)
        elif mtype == "document":
            resp = send_document(chat_id, url, caption=caption, filename=filename)
        elif mtype == "sticker":
            resp = send_sticker(chat_id, url)
        elif mtype == "voice":
            resp = send_voice(chat_id, url, caption=caption)
        else:
            return {
                "status": "error",
                "message": f"Unsupported media_type '{mtype}'. "
                           f"Use: {', '.join(sorted(_MEDIA_TYPES))}",
            }

        msg_id = resp.get("message_id", 0)
        store_outbound_message(
            chat_id,
            caption or f"[{mtype}]",
            message_id=msg_id,
            media_type=mtype,
            caption=caption or None,
        )
        return {
            "status": "success",
            "message_id": msg_id,
            "chat_id": chat_id,
            "media_type": mtype,
            "message": f"{mtype.title()} sent to {chat_id}.",
        }
    except Exception as exc:
        logger.error("send_media failed (%s): %s", mtype, exc)
        return {"status": "error", "message": str(exc)}


def send_media_group(
    chat_id: int | str,
    media_urls: List[str],
    media_type: str = "photo",
    captions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Send a group of photos or videos as a Telegram album.

    Args:
        chat_id:     Target chat.
        media_urls:  List of public URLs or file_ids (2–10 items).
        media_type:  "photo" or "video" (all items must be the same type).
        captions:    Optional captions per item (only first caption is shown by Telegram).
    """
    try:
        if not (2 <= len(media_urls) <= 10):
            return {
                "status": "error",
                "message": f"media_group requires 2–10 items, got {len(media_urls)}.",
            }
        media_list = []
        for i, url in enumerate(media_urls):
            item: Dict[str, Any] = {"type": media_type, "media": url}
            if captions and i < len(captions) and captions[i]:
                item["caption"] = captions[i]
                item["parse_mode"] = "Markdown"
            media_list.append(item)

        result = _send_media_group_api(chat_id, media_list)
        return {
            "status": "success",
            "chat_id": chat_id,
            "items_sent": len(media_list),
            "message": f"Album of {len(media_list)} {media_type}(s) sent to {chat_id}.",
        }
    except Exception as exc:
        logger.error("send_media_group failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_file_url(file_id: str) -> Dict[str, Any]:
    """
    Get the download URL for a file by its Telegram file_id.

    Args:
        file_id: Telegram file ID (from a received media message).
    """
    try:
        url = get_file_download_url(file_id)
        return {
            "status": "success",
            "file_id": file_id,
            "download_url": url,
            "message": f"Download URL generated for file {file_id}.",
        }
    except Exception as exc:
        logger.error("get_file_url failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_media_messages(
    chat_id: Optional[int | str] = None,
    media_type: Optional[str] = None,
    limit: int = 30,
) -> Dict[str, Any]:
    """
    Get messages with media attachments from the local store.

    Args:
        chat_id:    Filter to a specific chat (omit for all chats).
        media_type: Filter by type: photo | video | audio | document | voice | sticker
        limit:      Maximum results.
    """
    try:
        from ..polling.message_store import get_all_messages, get_messages_for_chat
        if chat_id:
            msgs = get_messages_for_chat(chat_id, limit=limit * 3)
        else:
            msgs = get_all_messages(limit=limit * 3)

        media_msgs = [m for m in msgs if m.get("media_type")]
        if media_type:
            media_msgs = [m for m in media_msgs
                          if m.get("media_type", "").lower() == media_type.lower()]

        return {
            "status": "success",
            "count": len(media_msgs[:limit]),
            "messages": media_msgs[:limit],
        }
    except Exception as exc:
        logger.error("get_media_messages failed: %s", exc)
        return {"status": "error", "message": str(exc)}
