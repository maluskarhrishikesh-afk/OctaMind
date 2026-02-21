"""
Unit tests for src/drive/features/organizer.py (Phase 3).

All Drive API calls are fully mocked — no credentials required.
"""

from __future__ import annotations
import src.drive.features.organizer as org

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_svc(files=None):
    svc = MagicMock()
    svc.files.return_value.list.return_value.execute.return_value = {
        "files": files or []
    }
    svc.files.return_value.create.return_value.execute.return_value = {
        "id": "new_folder_id"
    }
    svc.files.return_value.update.return_value.execute.return_value = {}
    return svc


def _patch(svc):
    return patch("src.drive.features.organizer.get_drive_service", return_value=svc)


# ─────────────────────────────────────────────────────────────────────────────
# suggest_organization
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestOrganization:
    def test_empty_folder_returns_empty_suggestion(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            result = org.suggest_organization()
        assert result["status"] == "success"
        assert result["total_files"] == 0

    def test_categorises_by_mime_type(self):
        files = [
            {"id": "1", "name": "photo.jpg", "mimeType": "image/jpeg"},
            {"id": "2", "name": "report.pdf", "mimeType": "application/pdf"},
            {"id": "3", "name": "budget.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.suggest_organization()
        assert result["status"] == "success"
        assert "Images" in result["categories"]
        assert "PDFs" in result["categories"]
        assert "Spreadsheets" in result["categories"]

    def test_folders_are_skipped(self):
        files = [
            {"id": "1", "name": "My Folder",
                "mimeType": "application/vnd.google-apps.folder"},
            {"id": "2", "name": "doc.pdf", "mimeType": "application/pdf"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.suggest_organization()
        # Folders (SKIP) should not appear in categories
        assert "SKIP" not in result["categories"]

    def test_suggestion_text_contains_folder_names(self):
        files = [{"id": "1", "name": "video.mp4", "mimeType": "video/mp4"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.suggest_organization()
        assert "Videos" in result["suggestion_text"]

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = org.suggest_organization()
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# auto_organize
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoOrganize:
    def test_dry_run_does_not_call_update(self):
        files = [
            {"id": "1", "name": "photo.jpg",
                "mimeType": "image/jpeg", "parents": ["root"]},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.auto_organize(dry_run=True)
        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["moved_count"] == 1
        svc.files.return_value.update.assert_not_called()

    def test_moves_files_for_known_types(self):
        files = [
            {"id": "f1", "name": "photo.jpg",
                "mimeType": "image/jpeg", "parents": ["root"]},
        ]
        svc = _make_svc(files=files)
        # _get_or_create_folder returns id from files().list (if folder exists) or files().create
        svc.files.return_value.list.return_value.execute.side_effect = [
            {"files": files},       # initial file listing
            {"files": []},          # folder existence check (not found)
        ]
        svc.files.return_value.create.return_value.execute.return_value = {
            "id": "images_folder_id"}
        with _patch(svc):
            result = org.auto_organize(dry_run=False)
        assert result["moved_count"] == 1
        assert result["moves"][0]["to_folder"] == "Images"

    def test_folders_are_skipped(self):
        files = [
            {"id": "1", "name": "Sub Folder",
                "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.auto_organize(dry_run=True)
        assert result["moved_count"] == 0

    def test_unknown_mime_goes_to_other(self):
        files = [
            {"id": "1", "name": "weird.xyz",
                "mimeType": "application/x-unknown", "parents": ["root"]},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.auto_organize(dry_run=True)
        assert result["moves"][0]["to_folder"] == "Other"


# ─────────────────────────────────────────────────────────────────────────────
# bulk_rename
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkRename:
    def test_renames_matching_files_dry_run(self):
        files = [
            {"id": "1", "name": "report_2025.pdf", "mimeType": "application/pdf"},
            {"id": "2", "name": "summary_2025.pdf", "mimeType": "application/pdf"},
            {"id": "3", "name": "other.txt", "mimeType": "text/plain"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.bulk_rename(
                "folder1", pattern=r"2025", replacement="2026", dry_run=True)
        assert result["status"] == "success"
        assert result["renamed_count"] == 2
        assert result["dry_run"] is True
        svc.files.return_value.update.assert_not_called()

    def test_actual_rename_calls_update(self):
        files = [
            {"id": "1", "name": "old_name.pdf", "mimeType": "application/pdf"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.bulk_rename(
                "folder1", pattern=r"old", replacement="new", dry_run=False)
        assert result["renamed_count"] == 1
        svc.files.return_value.update.assert_called_once()
        body = svc.files.return_value.update.call_args.kwargs["body"]
        assert body["name"] == "new_name.pdf"

    def test_no_matching_files_renames_none(self):
        files = [
            {"id": "1", "name": "report.pdf", "mimeType": "application/pdf"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = org.bulk_rename(
                "folder1", pattern=r"Invoice", replacement="Bill", dry_run=True)
        assert result["renamed_count"] == 0

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = org.bulk_rename("folder1", pattern="x", replacement="y")
        assert result["status"] == "error"
