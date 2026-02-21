"""
Google Drive Storage & Activity Analytics Module (Phase 4)

Functions:
- storage_breakdown     — storage used by MIME type / owner
- list_large_files      — list largest files in Drive
- list_old_files        — list files not modified in N days
- list_recently_modified — list recently changed files
- find_orphaned_files   — find files with no parent folder
- sharing_report        — generate a sharing/permissions audit report

Usage:
    from src.drive.features.analytics import storage_breakdown, list_large_files
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.drive.drive_auth import get_drive_service

logger = logging.getLogger("drive_agent.analytics")

_FILE_FIELDS = "id, name, mimeType, size, modifiedTime, createdTime, owners, parents, shared"


def _human_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def storage_breakdown(max_files: int = 1000) -> Dict[str, Any]:
    """
    Analyse storage usage broken down by file type.

    Args:
        max_files: Maximum files to scan.

    Returns:
        Dict with per-type totals and summary.
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
                    q="trashed = false",
                    pageSize=min(remaining, 100),
                    fields=f"nextPageToken, files({_FILE_FIELDS})",
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

        type_map: Dict[str, Dict] = defaultdict(
            lambda: {"count": 0, "bytes": 0})
        for f in results:
            mt = f.get("mimeType", "unknown")
            short = (
                "Folder" if mt == "application/vnd.google-apps.folder"
                else mt.split("/")[-1].replace("vnd.google-apps.", "").capitalize()
            )
            size = int(f.get("size", 0) or 0)
            type_map[short]["count"] += 1
            type_map[short]["bytes"] += size

        breakdown = [
            {
                "type": k,
                "count": v["count"],
                "bytes": v["bytes"],
                "size_human": _human_size(v["bytes"]),
            }
            for k, v in sorted(type_map.items(), key=lambda x: -x[1]["bytes"])
        ]

        total_bytes = sum(v["bytes"] for v in type_map.values())
        return {
            "status": "success",
            "breakdown": breakdown,
            "total_files": len(results),
            "total_size_human": _human_size(total_bytes),
        }
    except Exception as e:
        logger.error("storage_breakdown error: %s", e)
        return {"status": "error", "message": str(e)}


def list_large_files(
    min_size_mb: float = 10.0,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    List files larger than a given size threshold.

    Args:
        min_size_mb: Minimum file size in MB.
        max_results: Maximum results to return.

    Returns:
        Dict with status and list of large files.
    """
    try:
        svc = get_drive_service()
        min_bytes = int(min_size_mb * 1024 * 1024)
        resp = (
            svc.files()
            .list(
                q=f"size > {min_bytes} and trashed = false",
                pageSize=min(max_results, 100),
                fields=f"files({_FILE_FIELDS})",
                orderBy="quotaBytesUsed desc",
            )
            .execute()
        )
        files = resp.get("files", [])
        for f in files:
            f["size_human"] = _human_size(int(f.get("size", 0) or 0))

        return {
            "status": "success",
            "files": files,
            "count": len(files),
            "min_size_mb": min_size_mb,
        }
    except Exception as e:
        logger.error("list_large_files error: %s", e)
        return {"status": "error", "message": str(e)}


def list_old_files(
    days: int = 365,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    List files not modified in the last N days.

    Args:
        days:        Number of days since last modification.
        max_results: Maximum results.

    Returns:
        Dict with status and list of stale files.
    """
    try:
        svc = get_drive_service()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        resp = (
            svc.files()
            .list(
                q=f"modifiedTime < '{cutoff}' and trashed = false",
                pageSize=min(max_results, 100),
                fields=f"files({_FILE_FIELDS})",
                orderBy="modifiedTime asc",
            )
            .execute()
        )
        return {
            "status": "success",
            "files": resp.get("files", []),
            "count": len(resp.get("files", [])),
            "older_than_days": days,
        }
    except Exception as e:
        logger.error("list_old_files error: %s", e)
        return {"status": "error", "message": str(e)}


def list_recently_modified(max_results: int = 20) -> Dict[str, Any]:
    """
    List files most recently modified.

    Args:
        max_results: Maximum results.

    Returns:
        Dict with status and list of recently modified files.
    """
    try:
        svc = get_drive_service()
        resp = (
            svc.files()
            .list(
                q="trashed = false",
                pageSize=min(max_results, 100),
                fields=f"files({_FILE_FIELDS})",
                orderBy="modifiedTime desc",
            )
            .execute()
        )
        return {
            "status": "success",
            "files": resp.get("files", []),
            "count": len(resp.get("files", [])),
        }
    except Exception as e:
        logger.error("list_recently_modified error: %s", e)
        return {"status": "error", "message": str(e)}


def find_orphaned_files(max_results: int = 100) -> Dict[str, Any]:
    """
    Find files that are not in any folder (orphaned — no parents).

    Args:
        max_results: Maximum results.

    Returns:
        Dict with status and orphaned file list.
    """
    try:
        svc = get_drive_service()
        resp = (
            svc.files()
            .list(
                q="not 'root' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                pageSize=min(max_results, 100),
                fields=f"files({_FILE_FIELDS})",
            )
            .execute()
        )
        files = [f for f in resp.get("files", []) if not f.get("parents")]
        return {
            "status": "success",
            "files": files,
            "count": len(files),
        }
    except Exception as e:
        logger.error("find_orphaned_files error: %s", e)
        return {"status": "error", "message": str(e)}


def sharing_report(max_files: int = 200) -> Dict[str, Any]:
    """
    Generate a sharing/permissions audit report.

    Returns:
        Dict with counts for public files, shared files, and owner breakdown.
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
                    q="trashed = false",
                    pageSize=min(remaining, 100),
                    fields="nextPageToken, files(id, name, shared, owners, mimeType)",
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

        shared_files = [f for f in results if f.get("shared")]
        private_files = [f for f in results if not f.get("shared")]

        return {
            "status": "success",
            "total_files": len(results),
            "shared_count": len(shared_files),
            "private_count": len(private_files),
            "shared_files": shared_files[:50],  # Return up to 50 for display
        }
    except Exception as e:
        logger.error("sharing_report error: %s", e)
        return {"status": "error", "message": str(e)}
