"""
Telegram cross-agent integration tools.

These tools bridge the Telegram Agent with other OctaMind agents:
  - Forward a Telegram message as an email (requires Email Agent)
  - Send a Google Drive file link to a Telegram chat (requires Drive Agent)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("telegram_agent")


def forward_to_email(
    composite_id: str,
    recipient_email: str,
    subject: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Forward a Telegram message to an email address via the Email Agent.

    Args:
        composite_id:     Message id (chat_id:message_id) to forward.
        recipient_email:  Destination email address.
        subject:          Email subject. Defaults to "Forwarded Telegram message".
    """
    try:
        from ..polling.message_store import get_message_by_composite_id
        msg = get_message_by_composite_id(composite_id)
        if not msg:
            return {
                "status": "error",
                "message": f"Message '{composite_id}' not found.",
            }

        text = msg.get("text") or msg.get("caption") or ""
        sender = msg.get("from_user", "Unknown")
        ts = msg.get("timestamp", "")[:16].replace("T", " ")

        body = (
            f"Forwarded Telegram message from {sender} at {ts}:\n\n"
            f"---\n{text}\n---\n\n"
            "Sent via OctaMind Telegram Agent."
        )
        mail_subject = subject or f"Forwarded Telegram message from {sender}"

        from src.email.gmail_service import send_email  # type: ignore
        result = send_email(to=recipient_email, subject=mail_subject, body=body)

        return {
            "status": "success",
            "message_id": composite_id,
            "recipient": recipient_email,
            "subject": mail_subject,
            "message": f"Telegram message forwarded to {recipient_email} via email.",
        }
    except ImportError:
        logger.warning("Email agent not available; cannot forward to email.")
        return {
            "status": "error",
            "message": "Email Agent is not running or not installed.",
        }
    except Exception as exc:
        logger.error("forward_to_email failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def share_drive_file(
    chat_id: int | str,
    drive_file_id: str,
    caption: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Share a Google Drive file link to a Telegram chat.

    Fetches the shareable link from the Drive Agent and sends it as a message.

    Args:
        chat_id:       Telegram chat to send to.
        drive_file_id: Google Drive file ID.
        caption:       Optional message to prepend to the link.
    """
    try:
        from src.drive.drive_service import get_file_share_link  # type: ignore
        link_result = get_file_share_link(drive_file_id)
        share_url = link_result.get("web_view_link") or link_result.get("share_link", "")
        if not share_url:
            return {
                "status": "error",
                "message": f"Could not retrieve share link for Drive file {drive_file_id}.",
            }

        text = (caption + "\n\n" if caption else "") + f"📁 {share_url}"

        from ..telegram_service import send_text
        resp = send_text(chat_id, text)
        msg_id = resp.get("message_id", 0)

        return {
            "status": "success",
            "chat_id": chat_id,
            "drive_file_id": drive_file_id,
            "share_url": share_url,
            "message_id": msg_id,
            "message": f"Drive file link sent to Telegram chat {chat_id}.",
        }
    except ImportError:
        logger.warning("Drive agent not available; cannot share Drive file.")
        return {
            "status": "error",
            "message": "Drive Agent is not running or not installed.",
        }
    except Exception as exc:
        logger.error("share_drive_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}
