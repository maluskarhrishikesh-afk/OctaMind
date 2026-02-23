"""
Cross-agent integration tools for the Files Agent.

These tools bridge local files with Gmail and Google Drive agents.
Each function gracefully handles ImportError if those agents are not configured.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..files_service import resolve_path

logger = logging.getLogger("files_agent")


def zip_and_email(
    path: str,
    to_email: str,
    subject: str = "",
    body: str = "",
) -> Dict[str, Any]:
    """
    Zip a file or folder, then send it as a Gmail attachment.

    Args:
        path:     File or folder to zip and send.
        to_email: Recipient email address.
        subject:  Email subject. Defaults to "Shared: <filename>".
        body:     Email body. Defaults to a generic message.
    """
    try:
        from .archives import zip_folder, zip_files
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"Path does not exist: {p}"}

        # Create zip in a temp location next to the source
        zip_path = str(p.parent / (p.name + ".zip"))
        if p.is_dir():
            zip_result = zip_folder(path, zip_path)
        else:
            zip_result = zip_files([path], zip_path)

        if zip_result["status"] == "error":
            return zip_result

        # Email the zip
        try:
            from src.email import send_email_with_attachment  # type: ignore
        except ImportError:
            return {
                "status": "error",
                "message": "Gmail agent is not configured. Please set up Gmail OAuth first.",
                "zip_created": zip_result["archive"],
            }

        subject = subject or f"Shared: {p.name}.zip"
        body = body or f"Please find the attached archive: {p.name}.zip\n\nSent via OctaMind Files Agent."

        email_result = send_email_with_attachment(
            to=to_email,
            subject=subject,
            message=body,
            attachment_path=zip_result["archive"],
        )

        return {
            "status": email_result.get("status", "error"),
            "zip_path": zip_result["archive"],
            "zip_size": zip_result.get("compressed_size", ""),
            "email_to": to_email,
            "message": (
                f"Zipped '{p.name}' ({zip_result.get('compressed_size','')}) and emailed to {to_email}."
                if email_result.get("status") == "success"
                else email_result.get("message", "Email failed")
            ),
        }
    except Exception as exc:
        logger.error("zip_and_email failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def zip_and_upload_to_drive(
    path: str,
    drive_folder_name: str = "",
) -> Dict[str, Any]:
    """
    Zip a file or folder, then upload the archive to Google Drive.

    Args:
        path:              File or folder to zip and upload.
        drive_folder_name: Optional Drive folder name to upload into.
    """
    try:
        from .archives import zip_folder, zip_files
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"Path does not exist: {p}"}

        zip_path = str(p.parent / (p.name + ".zip"))
        if p.is_dir():
            zip_result = zip_folder(path, zip_path)
        else:
            zip_result = zip_files([path], zip_path)

        if zip_result["status"] == "error":
            return zip_result

        try:
            from src.drive import upload_file  # type: ignore
        except ImportError:
            return {
                "status": "error",
                "message": "Drive agent is not configured. Please set up Google Drive OAuth first.",
                "zip_created": zip_result["archive"],
            }

        drive_result = upload_file(
            local_path=zip_result["archive"],
            name=Path(zip_result["archive"]).name,
            folder_name=drive_folder_name or None,
        )

        return {
            "status": drive_result.get("status", "error"),
            "zip_path": zip_result["archive"],
            "zip_size": zip_result.get("compressed_size", ""),
            "drive_folder": drive_folder_name or "My Drive root",
            "drive_file_id": drive_result.get("file_id", ""),
            "message": (
                f"Zipped '{p.name}' and uploaded to Drive {('→ ' + drive_folder_name) if drive_folder_name else ''}."
                if drive_result.get("status") == "success"
                else drive_result.get("message", "Upload failed")
            ),
        }
    except Exception as exc:
        logger.error("zip_and_upload_to_drive failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def email_file(
    path: str,
    to_email: str,
    subject: str = "",
    body: str = "",
) -> Dict[str, Any]:
    """
    Attach a local file directly to a Gmail email (no zipping).

    Args:
        path:     Path to the file to attach.
        to_email: Recipient email address.
        subject:  Email subject.
        body:     Email body.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        try:
            from src.email import send_email_with_attachment  # type: ignore
        except ImportError:
            return {
                "status": "error",
                "message": "Gmail agent is not configured. Please set up Gmail OAuth first.",
            }

        subject = subject or f"File: {p.name}"
        body = body or f"Please find the attached file: {p.name}\n\nSent via OctaMind Files Agent."

        result = send_email_with_attachment(
            to=to_email,
            subject=subject,
            message=body,
            attachment_path=str(p),
        )

        return {
            "status": result.get("status", "error"),
            "file": p.name,
            "email_to": to_email,
            "message": result.get("message", "Email failed"),
        }
    except Exception as exc:
        logger.error("email_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def upload_file_to_drive(
    path: str,
    drive_folder_name: str = "",
) -> Dict[str, Any]:
    """
    Upload a local file directly to Google Drive (no zipping).

    Args:
        path:              Path to the file to upload.
        drive_folder_name: Optional Drive folder name to upload into.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        try:
            from src.drive import upload_file  # type: ignore
        except ImportError:
            return {
                "status": "error",
                "message": "Drive agent is not configured. Please set up Google Drive OAuth first.",
            }

        result = upload_file(
            local_path=str(p),
            name=p.name,
            folder_name=drive_folder_name or None,
        )

        return {
            "status": result.get("status", "error"),
            "file": p.name,
            "drive_folder": drive_folder_name or "My Drive root",
            "drive_file_id": result.get("file_id", ""),
            "message": result.get("message", "Upload failed"),
        }
    except Exception as exc:
        logger.error("upload_file_to_drive failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def send_file_via_whatsapp(
    to: str,
    path: str,
    caption: str = "",
) -> Dict[str, Any]:
    """
    Share a local file via WhatsApp by uploading it to Drive first to get a public URL,
    then sending it as a WhatsApp media message.

    Args:
        to:      Recipient phone number in E.164 format.
        path:    Path to the file (image, video, document).
        caption: Optional caption.
    """
    try:
        p = resolve_path(path)
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {p}"}

        try:
            from src.whatsapp import send_media  # type: ignore
        except ImportError:
            return {
                "status": "error",
                "message": "WhatsApp agent is not configured. Please set up WhatsApp credentials first.",
            }

        # Determine media type from extension
        ext = p.suffix.lower()
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
        video_exts = {".mp4", ".mov", ".avi", ".mkv"}
        audio_exts = {".mp3", ".wav", ".ogg", ".m4a", ".aac"}

        if ext in image_exts:
            media_type = "image"
        elif ext in video_exts:
            media_type = "video"
        elif ext in audio_exts:
            media_type = "audio"
        else:
            media_type = "document"

        return {
            "status": "error",
            "message": (
                "WhatsApp Cloud API requires a publicly hosted media URL — "
                f"local file '{p.name}' cannot be sent directly. "
                "Upload it to Google Drive first (make it public) and share the URL, "
                "or use zip_and_email to send it via Gmail instead."
            ),
        }
    except Exception as exc:
        logger.error("send_file_via_whatsapp failed: %s", exc)
        return {"status": "error", "message": str(exc)}
