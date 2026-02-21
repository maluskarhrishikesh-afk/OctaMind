"""
Google Drive Duplicate Finder Module (Phase 3)

Find and optionally remove duplicate files based on name + size.

Functions:
- find_duplicates  — list duplicate file groups in a folder
- trash_duplicates — move all-but-one copy of each duplicate group to trash

Usage:
    from src.drive.features.duplicates import find_duplicates, trash_duplicates
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List

from src.drive.drive_auth import get_drive_service

logger = logging.getLogger("drive_agent.duplicates")


def find_duplicates(
    folder_id: str = "root",
    max_files: int = 500,
) -> Dict[str, Any]:
    """
    Find duplicate files in a Drive folder (matched by name + size).

    Args:
        folder_id:  Folder to scan (defaults to root — entire My Drive).
        max_files:  Maximum files to scan.

    Returns:
        Dict with status, duplicate_groups list, and total duplicate count.
    """
    try:
        svc = get_drive_service()
        results: List[Dict] = []
        page_token = None
        remaining = max_files

        while remaining > 0:
            resp = (
                svc.files()
                .list(
                    q=(
                        f"'{folder_id}' in parents and trashed = false "
                        "and mimeType != 'application/vnd.google-apps.folder'"
                    ),
                    pageSize=min(remaining, 100),
                    fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
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

        # Group by (name, size)
        groups: dict = defaultdict(list)
        for f in results:
            key = (f.get("name", ""), f.get("size", ""))
            groups[key].append(f)

        # Keep only groups with duplicates
        dup_groups = [
            {
                "name": k[0],
                "size": k[1],
                "count": len(v),
                "files": v,
            }
            for k, v in groups.items()
            if len(v) > 1
        ]

        total_dups = sum(g["count"] - 1 for g in dup_groups)
        return {
            "status": "success",
            "duplicate_groups": dup_groups,
            "group_count": len(dup_groups),
            "total_duplicates": total_dups,
            "files_scanned": len(results),
        }
    except Exception as e:
        logger.error("find_duplicates error: %s", e)
        return {"status": "error", "message": str(e)}


def trash_duplicates(
    folder_id: str = "root",
    max_files: int = 500,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Remove duplicate files (keeps the oldest copy, trashes the rest).

    Args:
        folder_id: Folder to scan.
        max_files: Maximum files to scan.
        dry_run:   If True, report what would be trashed without actually trashing.

    Returns:
        Dict with status and count of trashed files.
    """
    try:
        found = find_duplicates(folder_id=folder_id, max_files=max_files)
        if found["status"] == "error":
            return found

        svc = get_drive_service()
        trashed = []
        for group in found["duplicate_groups"]:
            # Sort by createdTime ascending → keep oldest, trash the rest
            files_sorted = sorted(
                group["files"], key=lambda f: f.get("createdTime", "")
            )
            to_trash = files_sorted[1:]  # keep files_sorted[0]
            for f in to_trash:
                if not dry_run:
                    svc.files().update(
                        fileId=f["id"], body={"trashed": True}
                    ).execute()
                trashed.append({"id": f["id"], "name": f["name"]})

        return {
            "status": "success",
            "action": "trash_duplicates",
            "dry_run": dry_run,
            "trashed_count": len(trashed),
            "trashed": trashed,
        }
    except Exception as e:
        logger.error("trash_duplicates error: %s", e)
        return {"status": "error", "message": str(e)}
