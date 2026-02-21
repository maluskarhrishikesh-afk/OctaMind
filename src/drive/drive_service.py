"""
Google Drive Service Module

Core Drive operations (Phase 1):
- list_files         — list files in Drive (with optional query)
- search_files       — full-text / metadata search
- upload_file        — upload a local file to Drive
- download_file      — download a Drive file to local disk
- create_folder      — create a new folder
- move_file          — move a file to a different folder
- copy_file          — copy a file
- trash_file         — move a file to the trash
- restore_file       — restore a trashed file
- star_file          — star / un-star a file
- get_file_info      — get detailed metadata for a single file
- get_storage_quota  — return used / total storage quota

Usage:
    from src.drive import list_files, search_files, upload_file
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from .drive_auth import get_drive_service

logger = logging.getLogger("drive_agent.drive_service")
logger.setLevel(logging.DEBUG)

# Fields returned for file listings by default
_FILE_FIELDS = (
    "id, name, mimeType, size, createdTime, modifiedTime, "
    "parents, starred, trashed, webViewLink, iconLink, owners"
)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _svc():
    """Return authenticated Drive service (new instance each call; caching is
    handled by the underlying credential object)."""
    return get_drive_service()


def _human_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Core File Operations
# ─────────────────────────────────────────────────────────────────────────────

def _is_drive_query(text: str) -> bool:
    """Return True if *text* looks like a Drive query expression."""
    _operators = (
        " contains ", "name =", "name!=", " in parents", " in owners",
        "mimeType", "modifiedTime", "createdTime", "trashed",
        " and ", " or ", "not ", "fullText",
    )
    tl = text.lower()
    return any(op in tl for op in _operators)


def list_files(
    max_results: int = 20,
    query: str = "",
    folder_id: str = "root",
    order_by: str = "modifiedTime desc",
) -> List[Dict[str, Any]]:
    """
    List files in Google Drive.

    Args:
        max_results: Maximum number of files to return (1–1000).
        query:       Additional Drive query string (e.g. "mimeType='image/jpeg'").
        folder_id:   Parent folder ID to list. Use 'root' for My Drive root.
                     Pass 'trash' to list trashed files instead.
        order_by:    Sort order string (Drive API orderBy syntax).

    Returns:
        List of file metadata dicts.
    """
    svc = _svc()

    # Special-case: listing the Trash
    if folder_id.lower() in ("trash", "trashed", "bin"):
        q_parts = ["trashed = true"]
    else:
        q_parts = [f"'{folder_id}' in parents", "trashed = false"]

    if query:
        q_parts.append(f"({query})")
    q = " and ".join(q_parts)

    results = []
    page_token = None
    remaining = max_results

    while remaining > 0:
        page_size = min(remaining, 100)
        resp = (
            svc.files()
            .list(
                q=q,
                pageSize=page_size,
                fields=f"nextPageToken, files({_FILE_FIELDS})",
                orderBy=order_by,
                pageToken=page_token,
            )
            .execute()
        )
        batch = resp.get("files", [])
        results.extend(batch)
        page_token = resp.get("nextPageToken")
        remaining -= len(batch)
        if not page_token or not batch:
            break

    # Enrich with human-readable size
    for f in results:
        f["size_human"] = _human_size(
            int(f["size"]) if f.get("size") else None)
    return results


def search_files(
    query: str,
    max_results: int = 20,
    include_trashed: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search for files across all of Google Drive.

    Args:
        query:           Drive query string OR plain file name / search term.
                         Plain text (no Drive operators) is automatically wrapped
                         as ``name contains 'X'``.
        max_results:     Maximum number of results.
        include_trashed: Whether to include trashed files.

    Returns:
        List of matching file metadata dicts.
    """
    svc = _svc()

    # Normalise plain-text queries to a valid Drive query expression
    if query and not _is_drive_query(query):
        # escape any single quotes in filename
        safe = query.replace("'", "\\'")
        query = f"name contains '{safe}'"

    q_parts = [query] if query else []
    if not include_trashed:
        q_parts.append("trashed = false")
    q = " and ".join(q_parts) if q_parts else ""

    results = []
    page_token = None
    remaining = max_results

    while remaining > 0:
        page_size = min(remaining, 100)
        resp = (
            svc.files()
            .list(
                q=q,
                pageSize=page_size,
                fields=f"nextPageToken, files({_FILE_FIELDS})",
                orderBy="modifiedTime desc",
                pageToken=page_token,
            )
            .execute()
        )
        batch = resp.get("files", [])
        results.extend(batch)
        page_token = resp.get("nextPageToken")
        remaining -= len(batch)
        if not page_token or not batch:
            break

    for f in results:
        f["size_human"] = _human_size(
            int(f["size"]) if f.get("size") else None)
    return results


def get_file_info(file_id: str) -> Dict[str, Any]:
    """
    Get detailed metadata for a single Drive file.

    Args:
        file_id: The Drive file ID.

    Returns:
        File metadata dict, or error dict.
    """
    try:
        svc = _svc()
        file = (
            svc.files()
            .get(
                fileId=file_id,
                fields=_FILE_FIELDS + ", description, permissions, capabilities",
            )
            .execute()
        )
        file["size_human"] = _human_size(
            int(file["size"]) if file.get("size") else None
        )
        return {"status": "success", "file": file}
    except Exception as e:
        logger.error("get_file_info error: %s", e)
        return {"status": "error", "message": str(e)}


def upload_file(
    local_path: str,
    name: Optional[str] = None,
    folder_id: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upload a local file to Google Drive.

    Args:
        local_path: Absolute or relative path to the local file.
        name:       Name to use on Drive (defaults to local file name).
        folder_id:  Destination folder ID (defaults to My Drive root).
        mime_type:  MIME type override (auto-detected if omitted).

    Returns:
        Dict with status, file id, name, and web link.
    """
    try:
        svc = _svc()
        local = Path(local_path)
        if not local.exists():
            return {"status": "error", "message": f"File not found: {local_path}"}

        file_name = name or local.name
        metadata: Dict[str, Any] = {"name": file_name}
        if folder_id:
            metadata["parents"] = [folder_id]

        media = MediaFileUpload(str(local), mimetype=mime_type, resumable=True)
        result = (
            svc.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, name, webViewLink, mimeType, size",
            )
            .execute()
        )
        result["size_human"] = _human_size(
            int(result["size"]) if result.get("size") else None
        )
        return {"status": "success", "action": "upload", "file": result}
    except Exception as e:
        logger.error("upload_file error: %s", e)
        return {"status": "error", "message": str(e)}


def download_file(
    file_id: str,
    destination: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download a Drive file to local disk.

    Args:
        file_id:     The Drive file ID.
        destination: Local directory or file path (defaults to current directory).

    Returns:
        Dict with status and local path.
    """
    import io
    try:
        svc = _svc()
        meta = svc.files().get(fileId=file_id, fields="name, mimeType").execute()
        file_name = meta.get("name", file_id)
        mime = meta.get("mimeType", "")

        dest_dir = Path(destination) if destination else Path.cwd()
        if dest_dir.is_dir():
            dest_path = dest_dir / file_name
        else:
            dest_path = dest_dir

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Google Workspace files can't be downloaded directly — export as PDF
        export_map = {
            "application/vnd.google-apps.document": (
                "application/pdf", dest_path.with_suffix(".pdf")
            ),
            "application/vnd.google-apps.spreadsheet": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                dest_path.with_suffix(".xlsx"),
            ),
            "application/vnd.google-apps.presentation": (
                "application/pdf", dest_path.with_suffix(".pdf")
            ),
        }

        if mime in export_map:
            export_mime, dest_path = export_map[mime]
            request = svc.files().export_media(
                fileId=file_id, mimeType=export_mime
            )
        else:
            request = svc.files().get_media(fileId=file_id)

        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        dest_path.write_bytes(buf.getvalue())
        return {
            "status": "success",
            "action": "download",
            "local_path": str(dest_path),
            "file_name": file_name,
            "size_human": _human_size(len(buf.getvalue())),
        }
    except Exception as e:
        logger.error("download_file error: %s", e)
        return {"status": "error", "message": str(e)}


def create_folder(
    name: str,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new folder in Google Drive.

    Args:
        name:      Folder name.
        parent_id: Parent folder ID (defaults to My Drive root).

    Returns:
        Dict with status and new folder metadata.
    """
    try:
        svc = _svc()
        metadata: Dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = (
            svc.files()
            .create(body=metadata, fields="id, name, webViewLink, parents")
            .execute()
        )
        return {"status": "success", "action": "create_folder", "folder": folder}
    except Exception as e:
        logger.error("create_folder error: %s", e)
        return {"status": "error", "message": str(e)}


def move_file(
    file_id: str,
    destination_folder_id: str,
) -> Dict[str, Any]:
    """
    Move a file to a different folder.

    Args:
        file_id:                Drive file ID.
        destination_folder_id:  ID of the target folder.

    Returns:
        Dict with status and updated file metadata.
    """
    try:
        svc = _svc()
        # Fetch current parents
        file = svc.files().get(fileId=file_id, fields="parents").execute()
        previous_parents = ",".join(file.get("parents", []))
        updated = (
            svc.files()
            .update(
                fileId=file_id,
                addParents=destination_folder_id,
                removeParents=previous_parents,
                fields="id, name, parents, webViewLink",
            )
            .execute()
        )
        return {"status": "success", "action": "move", "file": updated}
    except Exception as e:
        logger.error("move_file error: %s", e)
        return {"status": "error", "message": str(e)}


def copy_file(
    file_id: str,
    name: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Copy a file in Google Drive.

    Args:
        file_id:   Source Drive file ID.
        name:      Name for the copy (defaults to 'Copy of <original>').
        folder_id: Folder for the copy (defaults to same folder as original).

    Returns:
        Dict with status and new file metadata.
    """
    try:
        svc = _svc()
        body: Dict[str, Any] = {}
        if name:
            body["name"] = name
        if folder_id:
            body["parents"] = [folder_id]
        copy = (
            svc.files()
            .copy(fileId=file_id, body=body, fields="id, name, webViewLink, parents")
            .execute()
        )
        return {"status": "success", "action": "copy", "file": copy}
    except Exception as e:
        logger.error("copy_file error: %s", e)
        return {"status": "error", "message": str(e)}


def trash_file(file_id: str) -> Dict[str, Any]:
    """
    Move a file to the Drive trash.

    Args:
        file_id: The Drive file ID.

    Returns:
        Dict with status.
    """
    try:
        svc = _svc()
        svc.files().update(fileId=file_id, body={"trashed": True}).execute()
        return {"status": "success", "action": "trash", "file_id": file_id}
    except Exception as e:
        logger.error("trash_file error: %s", e)
        return {"status": "error", "message": str(e)}


def restore_file(file_id: str) -> Dict[str, Any]:
    """
    Restore a trashed file.

    Args:
        file_id: The Drive file ID.

    Returns:
        Dict with status.
    """
    try:
        svc = _svc()
        svc.files().update(fileId=file_id, body={"trashed": False}).execute()
        return {"status": "success", "action": "restore", "file_id": file_id}
    except Exception as e:
        logger.error("restore_file error: %s", e)
        return {"status": "error", "message": str(e)}


def star_file(file_id: str, starred: bool = True) -> Dict[str, Any]:
    """
    Star or un-star a Drive file.

    Args:
        file_id: The Drive file ID.
        starred: True to star, False to un-star.

    Returns:
        Dict with status.
    """
    try:
        svc = _svc()
        svc.files().update(fileId=file_id, body={"starred": starred}).execute()
        verb = "starred" if starred else "unstarred"
        return {"status": "success", "action": verb, "file_id": file_id}
    except Exception as e:
        logger.error("star_file error: %s", e)
        return {"status": "error", "message": str(e)}


def get_storage_quota() -> Dict[str, Any]:
    """
    Return used and available Drive storage quota.

    Returns:
        Dict with used, limit, and usage_human fields.
    """
    try:
        svc = _svc()
        about = svc.about().get(fields="storageQuota").execute()
        quota = about.get("storageQuota", {})
        used = int(quota.get("usage", 0))
        limit = int(quota.get("limit", 0)) if quota.get("limit") else None
        return {
            "status": "success",
            "used_bytes": used,
            "limit_bytes": limit,
            "used_human": _human_size(used),
            "limit_human": _human_size(limit) if limit else "Unlimited",
            "free_human": _human_size(limit - used) if limit else "Unlimited",
        }
    except Exception as e:
        logger.error("get_storage_quota error: %s", e)
        return {"status": "error", "message": str(e)}
