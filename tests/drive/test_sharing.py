"""
Unit tests for src/drive/features/sharing.py (Phase 2).

All Drive API calls are fully mocked — no credentials required.
"""

from __future__ import annotations
import src.drive.features.sharing as sh

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_svc():
    svc = MagicMock()
    svc.permissions.return_value.create.return_value.execute.return_value = {
        "id": "perm1", "type": "user", "role": "reader", "emailAddress": "a@b.com"
    }
    svc.permissions.return_value.list.return_value.execute.return_value = {
        "permissions": []
    }
    svc.permissions.return_value.delete.return_value.execute.return_value = {}
    svc.permissions.return_value.update.return_value.execute.return_value = {
        "id": "perm1", "role": "writer"
    }
    svc.files.return_value.get.return_value.execute.return_value = {
        "webViewLink": "https://drive.google.com/file/1"
    }
    return svc


def _patch(svc):
    return patch("src.drive.features.sharing.get_drive_service", return_value=svc)


# ─────────────────────────────────────────────────────────────────────────────
# share_file
# ─────────────────────────────────────────────────────────────────────────────

class TestShareFile:
    def test_shares_with_user(self):
        svc = _make_svc()
        with _patch(svc):
            result = sh.share_file("file1", "bob@example.com", role="reader")
        assert result["status"] == "success"
        assert result["shared_with"] == "bob@example.com"
        assert result["role"] == "reader"

    def test_permission_body_has_correct_type(self):
        svc = _make_svc()
        with _patch(svc):
            sh.share_file("file1", "bob@example.com", role="writer")
        body = svc.permissions.return_value.create.call_args.kwargs["body"]
        assert body["type"] == "user"
        assert body["role"] == "writer"
        assert body["emailAddress"] == "bob@example.com"

    def test_notification_email_sent_by_default(self):
        svc = _make_svc()
        with _patch(svc):
            sh.share_file("file1", "x@y.com")
        kwargs = svc.permissions.return_value.create.call_args.kwargs
        assert kwargs["sendNotificationEmail"] is True

    def test_notification_can_be_disabled(self):
        svc = _make_svc()
        with _patch(svc):
            sh.share_file("file1", "x@y.com", send_notification=False)
        kwargs = svc.permissions.return_value.create.call_args.kwargs
        assert kwargs["sendNotificationEmail"] is False

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.permissions.return_value.create.return_value.execute.side_effect = Exception(
            "quota")
        with _patch(svc):
            result = sh.share_file("f1", "a@b.com")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# list_permissions
# ─────────────────────────────────────────────────────────────────────────────

class TestListPermissions:
    def test_returns_permission_list(self):
        svc = _make_svc()
        svc.permissions.return_value.list.return_value.execute.return_value = {
            "permissions": [
                {"id": "p1", "type": "user", "role": "reader",
                    "emailAddress": "a@b.com"},
                {"id": "p2", "type": "user", "role": "writer",
                    "emailAddress": "c@d.com"},
            ]
        }
        with _patch(svc):
            result = sh.list_permissions("file1")
        assert result["status"] == "success"
        assert result["count"] == 2

    def test_empty_permissions(self):
        svc = _make_svc()
        with _patch(svc):
            result = sh.list_permissions("file1")
        assert result["status"] == "success"
        assert result["count"] == 0

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.permissions.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = sh.list_permissions("bad_id")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# remove_permission
# ─────────────────────────────────────────────────────────────────────────────

class TestRemovePermission:
    def test_deletes_permission(self):
        svc = _make_svc()
        with _patch(svc):
            result = sh.remove_permission("file1", "perm1")
        assert result["status"] == "success"
        assert result["permission_id"] == "perm1"
        svc.permissions.return_value.delete.assert_called_once_with(
            fileId="file1", permissionId="perm1"
        )

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.permissions.return_value.delete.return_value.execute.side_effect = Exception(
            "not found")
        with _patch(svc):
            result = sh.remove_permission("f1", "p1")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# update_permission
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdatePermission:
    def test_updates_role(self):
        svc = _make_svc()
        with _patch(svc):
            result = sh.update_permission("file1", "perm1", role="writer")
        assert result["status"] == "success"
        body = svc.permissions.return_value.update.call_args.kwargs["body"]
        assert body["role"] == "writer"


# ─────────────────────────────────────────────────────────────────────────────
# make_public / remove_public
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicAccess:
    def test_make_public_creates_anyone_permission(self):
        svc = _make_svc()
        svc.permissions.return_value.create.return_value.execute.return_value = {
            "id": "anyp"}
        with _patch(svc):
            result = sh.make_public("file1")
        assert result["status"] == "success"
        body = svc.permissions.return_value.create.call_args.kwargs["body"]
        assert body["type"] == "anyone"
        assert body["role"] == "reader"

    def test_make_public_returns_link(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = {
            "webViewLink": "https://drive.google.com/file/test"
        }
        with _patch(svc):
            result = sh.make_public("file1")
        assert result["link"] == "https://drive.google.com/file/test"

    def test_remove_public_deletes_anyone_perm(self):
        svc = _make_svc()
        svc.permissions.return_value.list.return_value.execute.return_value = {
            "permissions": [
                {"id": "anyone_perm", "type": "anyone"},
                {"id": "user_perm", "type": "user"},
            ]
        }
        with _patch(svc):
            result = sh.remove_public("file1")
        assert result["status"] == "success"
        assert result["revoked_count"] == 1
        # Only the anyone permission should be deleted
        svc.permissions.return_value.delete.assert_called_once_with(
            fileId="file1", permissionId="anyone_perm"
        )

    def test_remove_public_no_public_perm_returns_zero(self):
        svc = _make_svc()
        svc.permissions.return_value.list.return_value.execute.return_value = {
            "permissions": [{"id": "u1", "type": "user"}]
        }
        with _patch(svc):
            result = sh.remove_public("file1")
        assert result["revoked_count"] == 0
