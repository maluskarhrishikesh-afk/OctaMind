"""
Google Drive Sharing & Permissions Module (Phase 2)

Functions:
- share_file          — share a file with a user/group/domain
- list_permissions    — list all permissions on a file
- remove_permission   — revoke a specific permission
- update_permission   — change role for an existing permission
- make_public         — make a file publicly readable (anyone with link)
- remove_public       — remove public access from a file

Usage:
    from src.drive.features.sharing import share_file, list_permissions
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.drive.drive_auth import get_drive_service

logger = logging.getLogger("drive_agent.sharing")


def share_file(
    file_id: str,
    email: str,
    role: str = "reader",
    send_notification: bool = True,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Share a Drive file with a specific user.

    Args:
        file_id:           Drive file ID.
        email:             Recipient email address.
        role:              Permission role: 'reader', 'commenter', 'writer', 'owner'.
        send_notification: Whether to send a sharing notification email.
        message:           Optional personal message in the notification.

    Returns:
        Dict with status and permission metadata.
    """
    try:
        svc = get_drive_service()
        body: Dict[str, Any] = {
            "type": "user",
            "role": role,
            "emailAddress": email,
        }
        kwargs: Dict[str, Any] = {
            "fileId": file_id,
            "body": body,
            "sendNotificationEmail": send_notification,
            "fields": "id, type, role, emailAddress, displayName",
        }
        if message:
            kwargs["emailMessage"] = message

        perm = svc.permissions().create(**kwargs).execute()
        return {
            "status": "success",
            "action": "share",
            "permission": perm,
            "shared_with": email,
            "role": role,
        }
    except Exception as e:
        logger.error("share_file error: %s", e)
        return {"status": "error", "message": str(e)}


def list_permissions(file_id: str) -> Dict[str, Any]:
    """
    List all permissions on a Drive file.

    Args:
        file_id: Drive file ID.

    Returns:
        Dict with status and list of permission dicts.
    """
    try:
        svc = get_drive_service()
        resp = (
            svc.permissions()
            .list(
                fileId=file_id,
                fields="permissions(id, type, role, emailAddress, displayName, domain)",
            )
            .execute()
        )
        return {
            "status": "success",
            "permissions": resp.get("permissions", []),
            "count": len(resp.get("permissions", [])),
        }
    except Exception as e:
        logger.error("list_permissions error: %s", e)
        return {"status": "error", "message": str(e)}


def remove_permission(file_id: str, permission_id: str) -> Dict[str, Any]:
    """
    Revoke a specific permission from a Drive file.

    Args:
        file_id:       Drive file ID.
        permission_id: The permission ID to remove.

    Returns:
        Dict with status.
    """
    try:
        svc = get_drive_service()
        svc.permissions().delete(
            fileId=file_id, permissionId=permission_id
        ).execute()
        return {
            "status": "success",
            "action": "remove_permission",
            "permission_id": permission_id,
        }
    except Exception as e:
        logger.error("remove_permission error: %s", e)
        return {"status": "error", "message": str(e)}


def update_permission(
    file_id: str,
    permission_id: str,
    role: str,
) -> Dict[str, Any]:
    """
    Update the role of an existing permission.

    Args:
        file_id:       Drive file ID.
        permission_id: Existing permission ID.
        role:          New role: 'reader', 'commenter', 'writer'.

    Returns:
        Dict with status and updated permission.
    """
    try:
        svc = get_drive_service()
        perm = (
            svc.permissions()
            .update(
                fileId=file_id,
                permissionId=permission_id,
                body={"role": role},
                fields="id, role",
            )
            .execute()
        )
        return {"status": "success", "action": "update_permission", "permission": perm}
    except Exception as e:
        logger.error("update_permission error: %s", e)
        return {"status": "error", "message": str(e)}


def make_public(file_id: str) -> Dict[str, Any]:
    """
    Make a file publicly readable (anyone with the link).

    Args:
        file_id: Drive file ID.

    Returns:
        Dict with status and webViewLink.
    """
    try:
        svc = get_drive_service()
        svc.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            fields="id",
        ).execute()
        file = svc.files().get(
            fileId=file_id, fields="webViewLink"
        ).execute()
        return {
            "status": "success",
            "action": "make_public",
            "link": file.get("webViewLink"),
        }
    except Exception as e:
        logger.error("make_public error: %s", e)
        return {"status": "error", "message": str(e)}


def remove_public(file_id: str) -> Dict[str, Any]:
    """
    Remove public ('anyone') access from a file.

    Args:
        file_id: Drive file ID.

    Returns:
        Dict with status.
    """
    try:
        svc = get_drive_service()
        # Find the 'anyone' permission ID
        resp = (
            svc.permissions()
            .list(fileId=file_id, fields="permissions(id, type)")
            .execute()
        )
        anyone_ids = [
            p["id"]
            for p in resp.get("permissions", [])
            if p.get("type") == "anyone"
        ]
        for pid in anyone_ids:
            svc.permissions().delete(
                fileId=file_id, permissionId=pid
            ).execute()
        return {
            "status": "success",
            "action": "remove_public",
            "revoked_count": len(anyone_ids),
        }
    except Exception as e:
        logger.error("remove_public error: %s", e)
        return {"status": "error", "message": str(e)}
