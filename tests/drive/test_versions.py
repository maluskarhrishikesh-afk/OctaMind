"""
Unit tests for src/drive/features/versions.py (Phase 3).

All Drive API calls are fully mocked — no credentials required.
"""

from __future__ import annotations
import src.drive.features.versions as ver

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_svc(revisions=None):
    svc = MagicMock()
    svc.files.return_value.get.return_value.execute.return_value = {
        "name": "doc.txt"}
    svc.revisions.return_value.list.return_value.execute.return_value = {
        "revisions": revisions or []
    }
    svc.revisions.return_value.get.return_value.execute.return_value = {
        "id": "rev1", "modifiedTime": "2026-01-01T00:00:00Z"
    }
    svc.revisions.return_value.update.return_value.execute.return_value = {}
    svc.revisions.return_value.delete.return_value.execute.return_value = {}
    return svc


def _patch(svc):
    return patch("src.drive.features.versions.get_drive_service", return_value=svc)


# ─────────────────────────────────────────────────────────────────────────────
# list_versions
# ─────────────────────────────────────────────────────────────────────────────

class TestListVersions:
    def test_returns_revision_list(self):
        revisions = [
            {"id": "r1", "modifiedTime": "2026-01-01T00:00:00Z"},
            {"id": "r2", "modifiedTime": "2026-02-01T00:00:00Z"},
        ]
        svc = _make_svc(revisions=revisions)
        with _patch(svc):
            result = ver.list_versions("file1")
        assert result["status"] == "success"
        assert result["count"] == 2
        assert result["file_name"] == "doc.txt"

    def test_empty_revisions(self):
        svc = _make_svc(revisions=[])
        with _patch(svc):
            result = ver.list_versions("file1")
        assert result["count"] == 0

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.get.return_value.execute.side_effect = Exception(
            "not found")
        with _patch(svc):
            result = ver.list_versions("bad_id")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# get_version_info
# ─────────────────────────────────────────────────────────────────────────────

class TestGetVersionInfo:
    def test_returns_revision_metadata(self):
        svc = _make_svc()
        svc.revisions.return_value.get.return_value.execute.return_value = {
            "id": "rev1", "modifiedTime": "2026-01-15T12:00:00Z", "keepForever": False
        }
        with _patch(svc):
            result = ver.get_version_info("file1", "rev1")
        assert result["status"] == "success"
        assert result["revision"]["id"] == "rev1"

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.revisions.return_value.get.return_value.execute.side_effect = Exception(
            "gone")
        with _patch(svc):
            result = ver.get_version_info("f1", "r1")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# restore_version
# ─────────────────────────────────────────────────────────────────────────────

class TestRestoreVersion:
    def test_pins_revision(self):
        svc = _make_svc()
        with _patch(svc):
            result = ver.restore_version("file1", "rev1")
        assert result["status"] == "success"
        assert result["action"] == "pin_revision"
        body = svc.revisions.return_value.update.call_args.kwargs["body"]
        assert body["keepForever"] is True

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.revisions.return_value.update.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = ver.restore_version("f1", "r1")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# delete_old_versions
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteOldVersions:
    def test_keeps_latest_n_deletes_rest(self):
        revisions = [
            {"id": "r1", "modifiedTime": "2026-01-01T00:00:00Z", "keepForever": False},
            {"id": "r2", "modifiedTime": "2026-02-01T00:00:00Z", "keepForever": False},
            {"id": "r3", "modifiedTime": "2026-03-01T00:00:00Z", "keepForever": False},
            {"id": "r4", "modifiedTime": "2026-04-01T00:00:00Z", "keepForever": False},
            {"id": "r5", "modifiedTime": "2026-05-01T00:00:00Z", "keepForever": False},
        ]
        svc = _make_svc(revisions=revisions)
        with _patch(svc):
            result = ver.delete_old_versions(
                "file1", keep_latest=3, dry_run=False)
        assert result["status"] == "success"
        assert result["deleted_count"] == 2  # 5 - 3 = 2 deleted
        assert result["kept"] == 3

    def test_dry_run_does_not_call_delete(self):
        revisions = [
            {"id": f"r{i}", "modifiedTime": f"2026-0{i}-01T00:00:00Z",
                "keepForever": False}
            for i in range(1, 5)
        ]
        svc = _make_svc(revisions=revisions)
        with _patch(svc):
            result = ver.delete_old_versions(
                "file1", keep_latest=2, dry_run=True)
        assert result["dry_run"] is True
        assert result["deleted_count"] == 2
        svc.revisions.return_value.delete.assert_not_called()

    def test_pinned_revisions_are_skipped_not_in_deleted_count(self):
        """Pinned (keepForever=True) revisions must not be deleted."""
        revisions = [
            {"id": "r1", "modifiedTime": "2026-01-01T00:00:00Z",
                "keepForever": True},  # pinned
            {"id": "r2", "modifiedTime": "2026-02-01T00:00:00Z", "keepForever": False},
            {"id": "r3", "modifiedTime": "2026-03-01T00:00:00Z", "keepForever": False},
        ]
        svc = _make_svc(revisions=revisions)
        with _patch(svc):
            result = ver.delete_old_versions(
                "file1", keep_latest=1, dry_run=True)
        # r1 is pinned so can't be deleted; r2 can be deleted (r3 kept as latest)
        assert result["deleted_count"] == 1
        # r2 is pinned so only r1 should be deleted — deleted_count == 1
        assert result["deleted_count"] == 1

    def test_fewer_revisions_than_keep_deletes_nothing(self):
        revisions = [
            {"id": "r1", "modifiedTime": "2026-01-01T00:00:00Z", "keepForever": False},
        ]
        svc = _make_svc(revisions=revisions)
        with _patch(svc):
            result = ver.delete_old_versions(
                "file1", keep_latest=5, dry_run=False)
        assert result["deleted_count"] == 0

    def test_minimum_keep_is_one(self):
        """keep_latest=0 should be treated as 1 (never delete everything)."""
        revisions = [
            {"id": "r1", "modifiedTime": "2026-01-01T00:00:00Z", "keepForever": False},
            {"id": "r2", "modifiedTime": "2026-02-01T00:00:00Z", "keepForever": False},
        ]
        svc = _make_svc(revisions=revisions)
        with _patch(svc):
            result = ver.delete_old_versions(
                "file1", keep_latest=0, dry_run=True)
        # keep_latest clamped to 1 → delete 1
        assert result["kept"] == 1
