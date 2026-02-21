"""
Google Drive File Organizer Module (Phase 3)

Auto-organize and bulk-rename Drive files.

Functions:
- suggest_organization  — suggest a folder structure based on file types
- auto_organize         — move files into type-based sub-folders
- bulk_rename           — rename multiple files with a pattern

Usage:
    from src.drive.features.organizer import auto_organize, bulk_rename
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.drive.drive_auth import get_drive_service

logger = logging.getLogger("drive_agent.organizer")

# Simple MIME-type → folder-name mapping
_TYPE_FOLDERS = {
    "image/jpeg": "Images",
    "image/png": "Images",
    "image/gif": "Images",
    "image/webp": "Images",
    "video/mp4": "Videos",
    "video/quicktime": "Videos",
    "audio/mpeg": "Audio",
    "audio/wav": "Audio",
    "application/pdf": "PDFs",
    "application/zip": "Archives",
    "application/x-zip-compressed": "Archives",
    "text/plain": "Text Files",
    "text/csv": "Spreadsheets",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Spreadsheets",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Documents",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "Presentations",
    "application/vnd.google-apps.document": "Google Docs",
    "application/vnd.google-apps.spreadsheet": "Google Sheets",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.folder": "SKIP",
}


def _get_or_create_folder(svc, name: str, parent_id: str) -> str:
    """Return existing folder ID or create a new one."""
    resp = (
        svc.files()
        .list(
            q=(
                f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
                f"and '{parent_id}' in parents and trashed=false"
            ),
            fields="files(id)",
            pageSize=1,
        )
        .execute()
    )
    files = resp.get("files", [])
    if files:
        return files[0]["id"]
    folder = (
        svc.files()
        .create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id",
        )
        .execute()
    )
    return folder["id"]


def suggest_organization(
    folder_id: str = "root",
    max_files: int = 100,
) -> Dict[str, Any]:
    """
    Suggest a folder-structure reorganization based on file types.

    Args:
        folder_id: Folder to analyse.
        max_files: Maximum files to sample.

    Returns:
        Dict with status and suggested structure.
    """
    try:
        svc = get_drive_service()
        resp = (
            svc.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=min(max_files, 100),
                fields="files(id, name, mimeType)",
            )
            .execute()
        )
        files = resp.get("files", [])

        suggestion: Dict[str, List[str]] = {}
        for f in files:
            mime = f.get("mimeType", "")
            folder_name = _TYPE_FOLDERS.get(mime, "Other")
            if folder_name == "SKIP":
                continue
            suggestion.setdefault(folder_name, []).append(f["name"])

        lines = [f"## Suggested Organization for your Drive\n"]
        for folder_name, names in sorted(suggestion.items()):
            lines.append(f"**📁 {folder_name}/** ({len(names)} files)")
            for n in names[:5]:
                lines.append(f"  - {n}")
            if len(names) > 5:
                lines.append(f"  - ... and {len(names) - 5} more")
            lines.append("")

        return {
            "status": "success",
            "suggestion_text": "\n".join(lines),
            "categories": {k: len(v) for k, v in suggestion.items()},
            "total_files": len(files),
        }
    except Exception as e:
        logger.error("suggest_organization error: %s", e)
        return {"status": "error", "message": str(e)}


def auto_organize(
    folder_id: str = "root",
    max_files: int = 100,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Automatically move loose files into type-named sub-folders.

    Args:
        folder_id: Source folder to organize.
        max_files: Maximum files to process.
        dry_run:   If True, show what would happen without moving files.

    Returns:
        Dict with status and move log.
    """
    try:
        svc = get_drive_service()
        resp = (
            svc.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=min(max_files, 100),
                fields="files(id, name, mimeType, parents)",
            )
            .execute()
        )
        files = resp.get("files", [])
        moved: List[Dict] = []

        for f in files:
            mime = f.get("mimeType", "")
            target_folder = _TYPE_FOLDERS.get(mime, "Other")
            if target_folder == "SKIP":
                continue

            if not dry_run:
                dest_id = _get_or_create_folder(svc, target_folder, folder_id)
                prev_parents = ",".join(f.get("parents", []))
                svc.files().update(
                    fileId=f["id"],
                    addParents=dest_id,
                    removeParents=prev_parents,
                    fields="id",
                ).execute()

            moved.append(
                {"file": f["name"], "to_folder": target_folder, "mime": mime}
            )

        return {
            "status": "success",
            "action": "auto_organize",
            "dry_run": dry_run,
            "moved_count": len(moved),
            "moves": moved,
        }
    except Exception as e:
        logger.error("auto_organize error: %s", e)
        return {"status": "error", "message": str(e)}


def bulk_rename(
    folder_id: str,
    pattern: str,
    replacement: str,
    max_files: int = 100,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Rename files in a folder using a regex find-and-replace pattern.

    Args:
        folder_id:   Source folder ID.
        pattern:     Regex pattern to search in file names.
        replacement: Replacement string (supports back-references like \\1).
        max_files:   Maximum files to rename.
        dry_run:     If True, show new names without renaming.

    Returns:
        Dict with status and rename log.
    """
    try:
        svc = get_drive_service()
        resp = (
            svc.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=min(max_files, 100),
                fields="files(id, name, mimeType)",
            )
            .execute()
        )
        files = resp.get("files", [])
        renamed: List[Dict] = []

        regex = re.compile(pattern)
        for f in files:
            old_name = f.get("name", "")
            if not regex.search(old_name):
                continue
            new_name = regex.sub(replacement, old_name)
            if new_name == old_name:
                continue

            if not dry_run:
                svc.files().update(
                    fileId=f["id"], body={"name": new_name}, fields="id, name"
                ).execute()

            renamed.append({"old": old_name, "new": new_name})

        return {
            "status": "success",
            "action": "bulk_rename",
            "dry_run": dry_run,
            "renamed_count": len(renamed),
            "renames": renamed,
        }
    except Exception as e:
        logger.error("bulk_rename error: %s", e)
        return {"status": "error", "message": str(e)}
