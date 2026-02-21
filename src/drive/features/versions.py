"""
Google Drive Version History Module (Phase 3)

Access and manage revision history for Drive files.

Functions:
- list_versions      — list all revisions of a file
- get_version_info   — get metadata for a specific revision
- restore_version    — make an older revision the latest (pin it)
- delete_old_versions — delete all revisions except the latest N

Usage:
    from src.drive.features.versions import list_versions, restore_version
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.drive.drive_auth import get_drive_service

logger = logging.getLogger("drive_agent.versions")


def list_versions(file_id: str) -> Dict[str, Any]:
    """
    List all revisions of a Drive file.

    Args:
        file_id: Drive file ID.

    Returns:
        Dict with status, file_name, and revisions list.
    """
    try:
        svc = get_drive_service()
        meta = svc.files().get(fileId=file_id, fields="name").execute()
        file_name = meta.get("name", file_id)

        resp = (
            svc.revisions()
            .list(
                fileId=file_id,
                fields="revisions(id, modifiedTime, lastModifyingUser, size, keepForever)",
            )
            .execute()
        )
        revisions = resp.get("revisions", [])
        return {
            "status": "success",
            "file_name": file_name,
            "revisions": revisions,
            "count": len(revisions),
        }
    except Exception as e:
        logger.error("list_versions error: %s", e)
        return {"status": "error", "message": str(e)}


def get_version_info(file_id: str, revision_id: str) -> Dict[str, Any]:
    """
    Get metadata for a specific revision.

    Args:
        file_id:     Drive file ID.
        revision_id: Revision ID.

    Returns:
        Dict with status and revision metadata.
    """
    try:
        svc = get_drive_service()
        rev = (
            svc.revisions()
            .get(
                fileId=file_id,
                revisionId=revision_id,
                fields="id, modifiedTime, lastModifyingUser, size, keepForever, exportLinks",
            )
            .execute()
        )
        return {"status": "success", "revision": rev}
    except Exception as e:
        logger.error("get_version_info error: %s", e)
        return {"status": "error", "message": str(e)}


def restore_version(file_id: str, revision_id: str) -> Dict[str, Any]:
    """
    Pin (keep forever) a revision to preserve it from automatic deletion.
    Note: Drive API doesn't support "rollback" directly; pinning keeps the revision.

    Args:
        file_id:     Drive file ID.
        revision_id: Revision ID to pin.

    Returns:
        Dict with status.
    """
    try:
        svc = get_drive_service()
        svc.revisions().update(
            fileId=file_id,
            revisionId=revision_id,
            body={"keepForever": True},
        ).execute()
        return {
            "status": "success",
            "action": "pin_revision",
            "revision_id": revision_id,
        }
    except Exception as e:
        logger.error("restore_version error: %s", e)
        return {"status": "error", "message": str(e)}


def delete_old_versions(
    file_id: str,
    keep_latest: int = 5,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Delete all revisions except the latest N.

    Args:
        file_id:     Drive file ID.
        keep_latest: Number of most-recent revisions to keep (minimum 1).
        dry_run:     If True, report what would be deleted without deleting.

    Returns:
        Dict with status and count of deleted revisions.
    """
    try:
        svc = get_drive_service()
        keep_latest = max(1, keep_latest)

        resp = (
            svc.revisions()
            .list(fileId=file_id, fields="revisions(id, modifiedTime, keepForever)")
            .execute()
        )
        revisions = resp.get("revisions", [])
        # Sort oldest first
        revisions_sorted = sorted(
            revisions, key=lambda r: r.get("modifiedTime", ""))

        to_delete = revisions_sorted[:-keep_latest] if len(
            revisions_sorted) > keep_latest else []
        # Skip pinned revisions
        to_delete = [r for r in to_delete if not r.get("keepForever")]

        deleted = []
        for rev in to_delete:
            if not dry_run:
                try:
                    svc.revisions().delete(
                        fileId=file_id, revisionId=rev["id"]
                    ).execute()
                    deleted.append(rev["id"])
                except Exception:
                    pass  # Some revisions can't be deleted (e.g., Google Docs)
            else:
                deleted.append(rev["id"])

        return {
            "status": "success",
            "action": "delete_old_versions",
            "dry_run": dry_run,
            "deleted_count": len(deleted),
            "kept": keep_latest,
            "total_revisions": len(revisions),
        }
    except Exception as e:
        logger.error("delete_old_versions error: %s", e)
        return {"status": "error", "message": str(e)}
