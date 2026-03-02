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


# ─────────────────────────────────────────────────────────────────────────────
# Batch operations
# ─────────────────────────────────────────────────────────────────────────────

def batch_move_files(file_ids: List[str], folder_id: str) -> Dict[str, Any]:
    """Move multiple Drive files to a destination folder in one operation.

    Args:
        file_ids:  List of Drive file IDs to move.
        folder_id: Destination folder ID (use 'root' for My Drive root).

    Returns:
        Dict with moved_count and per-file results.
    """
    svc = _svc()
    moved, errors = [], []
    for fid in file_ids:
        try:
            # Retrieve current parents to remove them
            meta = svc.files().get(fileId=fid, fields="id,name,parents").execute()
            current_parents = ",".join(meta.get("parents", []))
            svc.files().update(
                fileId=fid,
                addParents=folder_id,
                removeParents=current_parents,
                fields="id,name,parents",
            ).execute()
            moved.append({"id": fid, "name": meta.get("name", fid)})
        except Exception as exc:
            errors.append({"id": fid, "error": str(exc)})

    return {
        "status": "success" if not errors else "partial",
        "moved_count": len(moved),
        "error_count": len(errors),
        "moved": moved,
        "errors": errors,
        "message": f"Moved {len(moved)} file(s) to folder '{folder_id}'. {len(errors)} error(s).",
    }


def batch_delete_files(file_ids: List[str], permanent: bool = False) -> Dict[str, Any]:
    """Trash (or permanently delete) multiple Drive files.

    Args:
        file_ids:  List of Drive file IDs.
        permanent: If True, permanently deletes; if False (default), moves to Trash.

    Returns:
        Dict with deleted_count and per-file results.
    """
    svc = _svc()
    deleted, errors = [], []
    for fid in file_ids:
        try:
            if permanent:
                svc.files().delete(fileId=fid).execute()
            else:
                svc.files().trash(fileId=fid).execute()
            deleted.append(fid)
        except Exception as exc:
            errors.append({"id": fid, "error": str(exc)})

    action = "permanently deleted" if permanent else "moved to Trash"
    return {
        "status": "success" if not errors else "partial",
        "deleted_count": len(deleted),
        "error_count": len(errors),
        "deleted_ids": deleted,
        "errors": errors,
        "message": f"{len(deleted)} file(s) {action}. {len(errors)} error(s).",
    }


def batch_copy_files(
    file_ids: List[str],
    folder_id: str = "",
    name_suffix: str = " (copy)",
) -> Dict[str, Any]:
    """Copy multiple Drive files, optionally into a destination folder.

    Args:
        file_ids:    List of Drive file IDs to copy.
        folder_id:   Destination folder ID (keeps in same folder if empty).
        name_suffix: Appended to each copy name (default ' (copy)').

    Returns:
        Dict with copied files list.
    """
    svc = _svc()
    copied, errors = [], []
    for fid in file_ids:
        try:
            meta = svc.files().get(fileId=fid, fields="id,name,parents").execute()
            body: Dict = {"name": meta.get("name", fid) + name_suffix}
            if folder_id:
                body["parents"] = [folder_id]
            result = svc.files().copy(fileId=fid, body=body, fields="id,name").execute()
            copied.append({"original_id": fid, "copy_id": result["id"], "name": result["name"]})
        except Exception as exc:
            errors.append({"id": fid, "error": str(exc)})

    return {
        "status": "success" if not errors else "partial",
        "copied_count": len(copied),
        "copies": copied,
        "errors": errors,
        "message": f"Copied {len(copied)} file(s). {len(errors)} error(s).",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sharing & permissions (expose sharing.py helpers)
# ─────────────────────────────────────────────────────────────────────────────

def share_file(
    file_id: str,
    email: str = "",
    role: str = "reader",
    make_public: bool = False,
) -> Dict[str, Any]:
    """Share a Drive file with a person or make it publicly accessible.

    Args:
        file_id:     Drive file ID.
        email:       Email address to share with (ignored if make_public=True).
        role:        Permission role: 'reader', 'commenter', or 'writer'.
        make_public: If True, anyone with the link can view.

    Returns:
        Dict with shareable link and permission details.
    """
    from src.drive.features.sharing import (
        share_file as _share,
        make_public as _make_public,
    )
    if make_public:
        return _make_public(file_id)
    if not email:
        return {"status": "error", "message": "Provide email or set make_public=True."}
    return _share(file_id, email, role)


def manage_file_permissions(
    file_id: str,
    action: str,
    permission_id: str = "",
    email: str = "",
    new_role: str = "reader",
) -> Dict[str, Any]:
    """List, update or remove permissions on a Drive file.

    Args:
        file_id:       Drive file ID.
        action:        'list', 'remove', or 'update'.
        permission_id: Required for 'remove' and 'update'.
        email:         Display only (not required for API calls).
        new_role:      New role for 'update' action.

    Returns:
        Dict with permission results.
    """
    from src.drive.features.sharing import (
        list_permissions as _list_perms,
        remove_permission as _remove_perm,
        update_permission as _update_perm,
    )
    if action == "list":
        return _list_perms(file_id)
    elif action == "remove":
        if not permission_id:
            return {"status": "error", "message": "permission_id required for 'remove'."}
        return _remove_perm(file_id, permission_id)
    elif action == "update":
        if not permission_id:
            return {"status": "error", "message": "permission_id required for 'update'."}
        return _update_perm(file_id, permission_id, new_role)
    else:
        return {"status": "error", "message": "action must be 'list', 'remove', or 'update'."}


def list_shared_with_me(max_results: int = 20) -> List[Dict[str, Any]]:
    """List Drive files shared with the authenticated user by others.

    Returns:
        List of file metadata dicts.
    """
    try:
        svc = _svc()
        results = svc.files().list(
            q="sharedWithMe=true and trashed=false",
            pageSize=max_results,
            fields=f"files({_FILE_FIELDS})",
            orderBy="sharedWithMeTime desc",
        ).execute()
        files = results.get("files", [])
        for f in files:
            f["size_human"] = _human_size(int(f["size"])) if f.get("size") else "—"
        return files
    except Exception as exc:
        logger.error("list_shared_with_me error: %s", exc)
        return [{"status": "error", "message": str(exc)}]


# ─────────────────────────────────────────────────────────────────────────────
# Storage analysis
# ─────────────────────────────────────────────────────────────────────────────

def find_large_files(
    folder_id: str = "root",
    min_size_mb: float = 10.0,
    max_results: int = 25,
) -> Dict[str, Any]:
    """Find the largest files in a Drive folder (non-recursive via query).

    Args:
        folder_id:   Folder to search (default: entire Drive via 'root' query).
        min_size_mb: Only include files larger than this value in MB.
        max_results: Maximum files to return.

    Returns:
        Dict with list of large files sorted by size descending.
    """
    try:
        svc = _svc()
        min_bytes = int(min_size_mb * 1_048_576)
        q = f"size > {min_bytes} and trashed=false and mimeType != 'application/vnd.google-apps.folder'"
        results = svc.files().list(
            q=q,
            pageSize=max_results,
            fields="files(id, name, size, mimeType, modifiedTime, webViewLink, parents)",
            orderBy="quotaBytesUsed desc",
        ).execute()
        files = results.get("files", [])
        enriched = []
        for f in files:
            f["size_human"] = _human_size(int(f["size"])) if f.get("size") else "—"
            enriched.append(f)
        enriched.sort(key=lambda x: int(x.get("size", 0)), reverse=True)
        return {
            "status": "success",
            "file_count": len(enriched),
            "min_size_filter": f"{min_size_mb} MB",
            "files": enriched,
            "message": f"Found {len(enriched)} file(s) larger than {min_size_mb} MB.",
        }
    except Exception as exc:
        logger.error("find_large_files error: %s", exc)
        return {"status": "error", "message": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate detection (wraps features/duplicates.py)
# ─────────────────────────────────────────────────────────────────────────────

def find_drive_duplicates(folder_id: str = "root", max_results: int = 200) -> Dict[str, Any]:
    """Find duplicate files in Drive by name + size fingerprint.

    Returns:
        Dict with groups of duplicate files.
    """
    from src.drive.features.duplicates import find_duplicates as _find_dups
    return _find_dups(folder_id=folder_id, max_results=max_results)


def trash_drive_duplicates(folder_id: str = "root", keep: str = "newest") -> Dict[str, Any]:
    """Trash duplicate Drive files, keeping one copy per group.

    Args:
        folder_id: Folder to scan.
        keep:      'newest' or 'oldest' — which copy to keep.

    Returns:
        Dict with trashed count.
    """
    from src.drive.features.duplicates import trash_duplicates as _trash_dups
    return _trash_dups(folder_id=folder_id, keep=keep)


# ─────────────────────────────────────────────────────────────────────────────
# Document conversion (export to PDF / CSV / DOCX etc.)
# ─────────────────────────────────────────────────────────────────────────────

_EXPORT_MIME: Dict[str, str] = {
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv":  "text/csv",
    "txt":  "text/plain",
    "html": "text/html",
    "odt":  "application/vnd.oasis.opendocument.text",
}


def convert_document(
    file_id: str,
    output_format: str = "pdf",
    save_path: str = "",
) -> Dict[str, Any]:
    """Export a Google Docs/Sheets/Slides file to a different format.

    Args:
        file_id:       Drive file ID of a Google Workspace document.
        output_format: Target format: 'pdf', 'docx', 'xlsx', 'pptx', 'csv', 'txt', 'html'.
        save_path:     Local path to save the exported file.  If empty, saves to the
                       user's Downloads folder.

    Returns:
        Dict with file_path of the downloaded export.
    """
    import io, os
    from googleapiclient.http import MediaIoBaseDownload
    fmt = output_format.lstrip(".").lower()
    mime = _EXPORT_MIME.get(fmt)
    if not mime:
        return {
            "status": "error",
            "message": f"Unsupported format '{output_format}'. Supported: {', '.join(_EXPORT_MIME)}",
        }
    try:
        svc = _svc()
        meta = svc.files().get(fileId=file_id, fields="id,name").execute()
        base_name = os.path.splitext(meta.get("name", file_id))[0]
        if not save_path:
            dl = Path.home() / "Downloads"
            dl.mkdir(exist_ok=True)
            save_path = str(dl / f"{base_name}.{fmt}")

        request = svc.files().export_media(fileId=file_id, mimeType=mime)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        with open(save_path, "wb") as fh:
            fh.write(buf.getvalue())

        return {
            "status": "success",
            "file_path": save_path,
            "original_name": meta.get("name", ""),
            "format": fmt,
            "message": f"Exported '{meta.get('name', file_id)}' as {fmt.upper()} → {save_path}",
        }
    except Exception as exc:
        logger.error("convert_document error: %s", exc)
        return {"status": "error", "message": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Version management (wraps features/versions.py)
# ─────────────────────────────────────────────────────────────────────────────

def list_file_versions(file_id: str) -> Dict[str, Any]:
    """List all revision history for a Drive file."""
    from src.drive.features.versions import list_versions
    return list_versions(file_id)


def cleanup_old_versions(
    file_id: str,
    keep_latest: int = 3,
) -> Dict[str, Any]:
    """Delete old revisions of a Drive file, keeping only the N most recent.

    Args:
        file_id:     Drive file ID.
        keep_latest: Number of most-recent revisions to keep (default 3).
    """
    from src.drive.features.versions import delete_old_versions
    return delete_old_versions(file_id, keep_latest=keep_latest)


# ─────────────────────────────────────────────────────────────────────────────
# Sharing management
# ─────────────────────────────────────────────────────────────────────────────

def revoke_access_all(file_id: str) -> Dict[str, Any]:
    """Remove ALL non-owner permissions from a Drive file (make it fully private).

    Args:
        file_id: The Drive file ID to lock down.
    """
    svc = _svc()
    try:
        resp = svc.permissions().list(
            fileId=file_id,
            fields="permissions(id,role,emailAddress,displayName,type)",
        ).execute()
        perms = [p for p in resp.get("permissions", []) if p.get("role") != "owner"]
        if not perms:
            return {"status": "success", "revoked": 0,
                    "message": "File already private — no shared permissions found."}
        revoked, errors = [], []
        for p in perms:
            try:
                svc.permissions().delete(fileId=file_id, permissionId=p["id"]).execute()
                revoked.append({"permission_id": p["id"],
                                "email": p.get("emailAddress", ""),
                                "role": p.get("role", "")})
            except Exception as e:
                errors.append({"permission_id": p["id"], "error": str(e)})
        return {
            "status": "success",
            "file_id": file_id,
            "revoked": len(revoked),
            "revoked_details": revoked,
            "errors": errors,
            "message": f"Revoked {len(revoked)} permission(s). File is now private.",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def get_sharing_stats(file_id: str) -> Dict[str, Any]:
    """Return a summary of all sharing permissions for a Drive file.

    Shows who has access, at what role, and whether the file is public.
    """
    svc = _svc()
    try:
        file_info = svc.files().get(fileId=file_id, fields="id,name,webViewLink").execute()
        resp = svc.permissions().list(
            fileId=file_id,
            fields="permissions(id,role,emailAddress,displayName,type,expirationTime)",
        ).execute()
        perms = resp.get("permissions", [])
        by_role: Dict[str, list] = {}
        for p in perms:
            role = p.get("role", "unknown")
            by_role.setdefault(role, []).append({
                "permission_id": p.get("id"),
                "email": p.get("emailAddress", ""),
                "name": p.get("displayName", ""),
                "type": p.get("type", ""),
                "expires": p.get("expirationTime", "never"),
            })
        is_public = any(p.get("type") == "anyone" for p in perms)
        return {
            "status": "success",
            "file_id": file_id,
            "name": file_info.get("name"),
            "web_link": file_info.get("webViewLink"),
            "total_permissions": len(perms),
            "is_public": is_public,
            "by_role": by_role,
            "message": (
                f"'{file_info.get('name')}' has {len(perms)} permission(s). "
                f"{'Publicly accessible.' if is_public else 'Not public.'}"
            ),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Storage / archival insights
# ─────────────────────────────────────────────────────────────────────────────

def suggest_archival(
    folder_id: str = "root",
    months_old: int = 6,
    max_results: int = 25,
) -> Dict[str, Any]:
    """Find Drive files that haven't been modified in N months.

    Useful for identifying stale content that could be archived or deleted.
    """
    import datetime as _dt
    svc = _svc()
    try:
        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=months_old * 30)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        query = (
            f"'{folder_id}' in parents and trashed=false "
            f"and mimeType!='application/vnd.google-apps.folder' "
            f"and modifiedTime < '{cutoff_str}'"
        )
        resp = svc.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
            orderBy="modifiedTime asc",
        ).execute()
        files = resp.get("files", [])
        results = [
            {
                "id": f["id"],
                "name": f["name"],
                "type": f.get("mimeType", ""),
                "size_human": _human_size(int(f["size"])) if f.get("size") else "unknown",
                "last_modified": f.get("modifiedTime", ""),
                "web_link": f.get("webViewLink", ""),
            }
            for f in files
        ]
        return {
            "status": "success",
            "months_threshold": months_old,
            "count": len(results),
            "files": results,
            "message": (
                f"Found {len(results)} file(s) not modified in {months_old}+ months. "
                "Consider archiving or deleting."
            ),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Backup / Sync
# ─────────────────────────────────────────────────────────────────────────────

def backup_drive_to_local(
    folder_id: str,
    output_dir: str,
    max_files: int = 100,
) -> Dict[str, Any]:
    """Download all files from a Drive folder to a local directory.

    Google Docs / Sheets / Slides are exported as PDF / XLSX / PDF respectively.
    Binary files (PDF, images, etc.) are downloaded as-is.

    Args:
        folder_id:  Drive folder ID to back up.
        output_dir: Local directory path to save files into (created if missing).
        max_files:  Maximum number of files to download per call (default 100).
    """
    import io as _io
    svc = _svc()
    _EXPORT_MAP = {
        "application/vnd.google-apps.document":     ("pdf", "application/pdf"),
        "application/vnd.google-apps.spreadsheet":  (
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        "application/vnd.google-apps.presentation": ("pdf", "application/pdf"),
    }
    try:
        out_path = Path(output_dir).expanduser()
        out_path.mkdir(parents=True, exist_ok=True)
        resp = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=max_files,
            fields="files(id,name,mimeType,size)",
        ).execute()
        files = resp.get("files", [])
        downloaded, skipped, errors = [], [], []
        for f in files:
            fname, mime = f["name"], f.get("mimeType", "")
            try:
                if mime in _EXPORT_MAP:
                    ext, export_mime = _EXPORT_MAP[mime]
                    req = svc.files().export_media(fileId=f["id"], mimeType=export_mime)
                    dest = out_path / (fname + "." + ext)
                elif mime.startswith("application/vnd.google-apps."):
                    skipped.append({"id": f["id"], "name": fname, "reason": "unsupported Google type"})
                    continue
                else:
                    req = svc.files().get_media(fileId=f["id"])
                    dest = out_path / fname
                buf = _io.BytesIO()
                dl = MediaIoBaseDownload(buf, req)
                done = False
                while not done:
                    _, done = dl.next_chunk()
                dest.write_bytes(buf.getvalue())
                downloaded.append({"id": f["id"], "name": fname, "saved_as": str(dest), "bytes": len(buf.getvalue())})
            except Exception as e:
                errors.append({"id": f["id"], "name": fname, "error": str(e)})
        return {
            "status": "success",
            "output_dir": str(out_path),
            "downloaded": len(downloaded),
            "skipped": len(skipped),
            "errors": len(errors),
            "files": downloaded,
            "skipped_files": skipped,
            "error_files": errors,
            "message": f"Downloaded {len(downloaded)} file(s) to '{out_path}'. {len(errors)} error(s).",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def sync_local_folder_to_drive(
    local_path: str,
    drive_folder_id: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Sync a local folder to Google Drive — upload new or modified files.

    Compares local file modification times against the Drive file's modifiedTime.
    Only uploads files that are new or newer locally.

    Args:
        local_path:       Absolute path to the local folder.
        drive_folder_id:  Google Drive folder ID to sync into.
        dry_run:          Show what would be uploaded without uploading (default True).
    """
    import datetime as _dt, mimetypes as _mt
    svc = _svc()
    try:
        local = Path(local_path).expanduser()
        if not local.is_dir():
            return {"status": "error", "message": f"'{local_path}' is not a directory."}
        # Fetch existing Drive files in the target folder
        existing: Dict[str, Dict] = {}
        page_token = None
        while True:
            resp = svc.files().list(
                q=f"'{drive_folder_id}' in parents and trashed=false",
                pageSize=1000,
                fields="nextPageToken,files(id,name,modifiedTime)",
                pageToken=page_token,
            ).execute()
            for item in resp.get("files", []):
                existing[item["name"]] = item
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        to_upload, up_to_date = [], []
        for f in local.iterdir():
            if not f.is_file():
                continue
            mtime = _dt.datetime.fromtimestamp(f.stat().st_mtime, tz=_dt.timezone.utc)
            if f.name in existing:
                drive_mtime_str = existing[f.name].get("modifiedTime", "")
                drive_mtime = _dt.datetime.fromisoformat(drive_mtime_str.replace("Z", "+00:00"))
                if mtime <= drive_mtime:
                    up_to_date.append(f.name)
                    continue
                action = "update"
            else:
                action = "create"
            to_upload.append({"name": f.name, "action": action, "path": str(f),
                               "local_mtime": mtime.isoformat()})
        if dry_run:
            return {
                "status": "dry_run",
                "would_upload": len(to_upload),
                "up_to_date": len(up_to_date),
                "files": to_upload,
                "message": (
                    f"DRY RUN: Would upload {len(to_upload)} file(s). "
                    "Call with dry_run=False to apply."
                ),
            }
        uploaded, errors = [], []
        for item in to_upload:
            try:
                mime_type = _mt.guess_type(item["path"])[0] or "application/octet-stream"
                media = MediaFileUpload(item["path"], mimetype=mime_type, resumable=True)
                if item["action"] == "create":
                    meta = {"name": item["name"], "parents": [drive_folder_id]}
                    result = svc.files().create(body=meta, media_body=media, fields="id,name").execute()
                else:
                    drive_id = existing[item["name"]]["id"]
                    result = svc.files().update(fileId=drive_id, media_body=media, fields="id,name").execute()
                uploaded.append({"name": item["name"], "action": item["action"], "drive_id": result["id"]})
            except Exception as e:
                errors.append({"name": item["name"], "error": str(e)})
        return {
            "status": "success",
            "uploaded": len(uploaded),
            "up_to_date": len(up_to_date),
            "errors": len(errors),
            "files": uploaded,
            "error_files": errors,
            "message": (
                f"Uploaded {len(uploaded)} file(s). "
                f"{len(up_to_date)} already up-to-date. {len(errors)} error(s)."
            ),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}