"""
Cross-agent integration tools.

Allows the WhatsApp agent to collaborate with other agents in the system:
  - forward_to_email: Forward a WhatsApp message to an email recipient
  - share_drive_file: Share a Google Drive file link via WhatsApp
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..webhook.message_store import get_message_by_id, get_messages_for_contact

logger = logging.getLogger("whatsapp_agent")


def forward_to_email(
    message_id: str,
    to_email: str,
    subject: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Forward a WhatsApp message to an email address.

    Uses the Email agent's send_email function to deliver the message
    content as an email.

    Args:
        message_id: WhatsApp message ID to forward.
        to_email:   Recipient email address.
        subject:    Optional email subject (auto-generated if not provided).
    """
    try:
        msg = get_message_by_id(message_id)
        if not msg:
            return {"status": "error", "message": f"Message {message_id} not found."}

        from_phone = msg.get("from", "unknown")
        body = msg.get("body", "")
        ts = msg.get("timestamp", "")[:16].replace("T", " ")
        email_subject = subject or f"WhatsApp message from {from_phone}"
        email_body = (
            f"Forwarded WhatsApp message\n"
            f"From: {from_phone}\n"
            f"Time: {ts}\n"
            f"---\n{body}"
        )

        # Use the email agent's send function
        from src.email import send_email
        result = send_email(
            to=to_email,
            subject=email_subject,
            message=email_body,
        )

        if result.get("status") == "success":
            return {
                "status": "success",
                "message_id": message_id,
                "forwarded_to": to_email,
                "message": f"WhatsApp message forwarded to {to_email}",
            }
        return {"status": "error", "message": result.get("message", "Email sending failed.")}

    except ImportError:
        return {
            "status": "error",
            "message": (
                "Email agent is not available. "
                "Ensure you have a Gmail agent configured."
            ),
        }
    except Exception as exc:
        logger.error("forward_to_email failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def share_drive_file(
    to: str,
    file_id: str,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Share a Google Drive file link via WhatsApp.

    Retrieves the share link for a Drive file and sends it as a WhatsApp
    message.  Requires a configured Google Drive agent.

    Args:
        to:      Recipient phone (E.164).
        file_id: Google Drive file ID.
        message: Optional message to include with the link.
    """
    try:
        # Get the sharing link from Drive
        from src.drive import get_file_info
        drive_result = get_file_info(file_id)
        if drive_result.get("status") != "success":
            return {
                "status": "error",
                "message": f"Could not retrieve Drive file: {drive_result.get('message')}",
            }

        file_name = drive_result.get("name", "file")
        share_link = drive_result.get("webViewLink") or drive_result.get("link", "")

        if not share_link:
            return {
                "status": "error",
                "message": "Could not retrieve share link for the Drive file.",
            }

        body = message or f"📎 Shared file: {file_name}"
        body = f"{body}\n{share_link}"

        # Send via WhatsApp
        from .messaging import send_message
        result = send_message(to, body)
        if result.get("status") == "success":
            return {
                "status": "success",
                "to": to,
                "file_name": file_name,
                "share_link": share_link,
                "message": f"Drive file '{file_name}' shared with {to}",
            }
        return result

    except ImportError:
        return {
            "status": "error",
            "message": (
                "Google Drive agent is not available. "
                "Ensure you have a Drive agent configured."
            ),
        }
    except Exception as exc:
        logger.error("share_drive_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}
