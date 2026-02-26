"""
Google Drive File Summarizer Module (Phase 3)

AI-powered summaries of Drive files using the Octa Bot LLM client.

Functions:
- summarize_file   — generate a natural-language summary of a file's content
- summarize_folder — generate a high-level overview of a folder's contents

Usage:
    from src.drive.features.summarizer import summarize_file, summarize_folder
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict

from src.drive.drive_auth import get_drive_service

logger = logging.getLogger("drive_agent.summarizer")

# Text-extractable MIME types
_TEXT_MIMES = {
    "text/plain",
    "text/csv",
    "text/html",
    "text/markdown",
    "application/json",
}

# Google Docs types we can export to plain text
_EXPORT_AS_TEXT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _fetch_text(svc, file_id: str, mime: str) -> str:
    """Download/export a file and return its text content (up to 8 KB)."""
    try:
        if mime in _EXPORT_AS_TEXT:
            request = svc.files().export_media(
                fileId=file_id, mimeType=_EXPORT_AS_TEXT[mime]
            )
        elif mime in _TEXT_MIMES:
            request = svc.files().get_media(fileId=file_id)
        else:
            return ""

        buf = io.BytesIO()
        from googleapiclient.http import MediaIoBaseDownload  # local import
        dl = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue().decode("utf-8", errors="replace")[:8000]
    except Exception as e:
        logger.warning("_fetch_text failed for %s: %s", file_id, e)
        return ""


def summarize_file(file_id: str) -> Dict[str, Any]:
    """
    Generate an AI summary of a Drive file's content.

    Args:
        file_id: Drive file ID.

    Returns:
        Dict with status, file name, and summary text.
    """
    try:
        from src.agent.llm.llm_parser import get_llm_client

        svc = get_drive_service()
        meta = svc.files().get(
            fileId=file_id, fields="name, mimeType, size"
        ).execute()
        file_name = meta.get("name", file_id)
        mime = meta.get("mimeType", "")

        text = _fetch_text(svc, file_id, mime)

        if not text.strip():
            return {
                "status": "success",
                "file_name": file_name,
                "summary": (
                    f"**{file_name}** is a binary/unsupported file "
                    f"(MIME: `{mime}`). Text content is not available for summarization."
                ),
            }

        llm = get_llm_client()
        prompt = (
            f"Summarize the following document in 3–5 concise sentences. "
            f"File name: {file_name}\n\n---\n\n{text}"
        )
        summary = llm.generate(prompt)
        return {
            "status": "success",
            "file_name": file_name,
            "summary": summary,
        }
    except Exception as e:
        logger.error("summarize_file error: %s", e)
        return {"status": "error", "message": str(e)}


def summarize_folder(folder_id: str = "root") -> Dict[str, Any]:
    """
    Generate a high-level overview of what's in a Drive folder.

    Args:
        folder_id: Drive folder ID (defaults to root).

    Returns:
        Dict with status, folder overview, and type breakdown.
    """
    try:
        svc = get_drive_service()

        folder_name = "My Drive"
        if folder_id != "root":
            meta = svc.files().get(fileId=folder_id, fields="name").execute()
            folder_name = meta.get("name", folder_id)

        resp = (
            svc.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                pageSize=100,
                fields="files(id, name, mimeType, size)",
            )
            .execute()
        )
        files = resp.get("files", [])
        if not files:
            return {
                "status": "success",
                "folder_name": folder_name,
                "summary": f"The folder **{folder_name}** is empty.",
                "breakdown": {},
                "total": 0,
            }

        breakdown: Dict[str, int] = {}
        for f in files:
            mt = f.get("mimeType", "other")
            short = (
                "Folder" if mt == "application/vnd.google-apps.folder"
                else mt.split("/")[-1].replace("vnd.google-apps.", "").capitalize()
            )
            breakdown[short] = breakdown.get(short, 0) + 1

        type_lines = "\n".join(f"- {k}: {v}" for k,
                               v in sorted(breakdown.items()))
        summary = (
            f"**{folder_name}** contains **{len(files)}** item(s):\n\n{type_lines}"
        )
        return {
            "status": "success",
            "folder_name": folder_name,
            "summary": summary,
            "breakdown": breakdown,
            "total": len(files),
        }
    except Exception as e:
        logger.error("summarize_folder error: %s", e)
        return {"status": "error", "message": str(e)}
