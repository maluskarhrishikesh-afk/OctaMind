"""
Unit tests for src/drive/drive_service.py (Phase 1 core operations).

All Google Drive API calls are fully mocked — no credentials required.
"""

from __future__ import annotations
import src.drive.drive_service as ds

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_svc(files=None, next_page_token=None):
    """Return a mock Drive service whose files().list().execute() returns *files*."""
    svc = MagicMock()
    resp = {"files": files or []}
    if next_page_token:
        resp["nextPageToken"] = next_page_token
    svc.files.return_value.list.return_value.execute.return_value = resp
    svc.files.return_value.get.return_value.execute.return_value = {}
    svc.files.return_value.create.return_value.execute.return_value = {}
    svc.files.return_value.update.return_value.execute.return_value = {}
    svc.files.return_value.copy.return_value.execute.return_value = {}
    svc.about.return_value.get.return_value.execute.return_value = {
        "storageQuota": {"usage": "1073741824", "limit": "16106127360"}
    }
    return svc


def _patch(svc):
    """Patch drive_service._svc to return *svc*."""
    return patch.object(ds, "_svc", return_value=svc)


# ─────────────────────────────────────────────────────────────────────────────
# _human_size
# ─────────────────────────────────────────────────────────────────────────────

class TestHumanSize:
    def test_none_returns_dash(self):
        assert ds._human_size(None) == "—"

    def test_bytes(self):
        assert ds._human_size(500) == "500.0 B"

    def test_kilobytes(self):
        assert ds._human_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert ds._human_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert ds._human_size(2 * 1024 ** 3) == "2.0 GB"


# ─────────────────────────────────────────────────────────────────────────────
# list_files
# ─────────────────────────────────────────────────────────────────────────────

class TestListFiles:
    def test_returns_files_from_api(self):
        files = [{"id": "f1", "name": "report.pdf",
                  "mimeType": "application/pdf"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = ds.list_files(max_results=10)
        assert len(result) == 1
        assert result[0]["name"] == "report.pdf"

    def test_size_human_added(self):
        files = [{"id": "f1", "name": "doc.txt",
                  "mimeType": "text/plain", "size": "2048"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = ds.list_files()
        assert result[0]["size_human"] == "2.0 KB"

    def test_empty_drive_returns_empty_list(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            result = ds.list_files()
        assert result == []

    def test_query_included_in_api_call(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            ds.list_files(query="mimeType='image/jpeg'", folder_id="root")
        call_kwargs = svc.files.return_value.list.call_args.kwargs
        assert "mimeType='image/jpeg'" in call_kwargs["q"]

    def test_folder_id_used_in_query(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            ds.list_files(folder_id="folder123")
        q = svc.files.return_value.list.call_args.kwargs["q"]
        assert "'folder123' in parents" in q

    def test_trashed_false_always_in_query(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            ds.list_files()
        q = svc.files.return_value.list.call_args.kwargs["q"]
        assert "trashed = false" in q

    def test_api_error_propagates(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "auth error")
        with _patch(svc):
            with pytest.raises(Exception, match="auth error"):
                ds.list_files()


# ─────────────────────────────────────────────────────────────────────────────
# search_files
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchFiles:
    def test_returns_matching_files(self):
        files = [{"id": "s1", "name": "budget.xlsx",
                  "mimeType": "application/vnd.ms-excel"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = ds.search_files(query="name contains 'budget'")
        assert len(result) == 1
        assert result[0]["name"] == "budget.xlsx"

    def test_trashed_excluded_by_default(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            ds.search_files(query="report")
        q = svc.files.return_value.list.call_args.kwargs["q"]
        assert "trashed = false" in q

    def test_trashed_included_when_requested(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            ds.search_files(query="report", include_trashed=True)
        q = svc.files.return_value.list.call_args.kwargs["q"]
        assert "trashed" not in q

    def test_empty_query_returns_all(self):
        files = [{"id": "a1", "name": "a.txt", "mimeType": "text/plain"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = ds.search_files(query="")
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────────────────────
# get_file_info
# ─────────────────────────────────────────────────────────────────────────────

class TestGetFileInfo:
    def test_returns_file_metadata(self):
        fake_file = {"id": "file1", "name": "doc.pdf",
                     "mimeType": "application/pdf"}
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = fake_file
        with _patch(svc):
            result = ds.get_file_info("file1")
        assert result["status"] == "success"
        assert result["file"]["name"] == "doc.pdf"

    def test_size_human_added_for_sized_file(self):
        fake_file = {"id": "f2", "name": "img.jpg", "size": "1048576"}
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = fake_file
        with _patch(svc):
            result = ds.get_file_info("f2")
        assert result["file"]["size_human"] == "1.0 MB"

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.get.return_value.execute.side_effect = Exception(
            "not found")
        with _patch(svc):
            result = ds.get_file_info("bad_id")
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ─────────────────────────────────────────────────────────────────────────────
# create_folder
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateFolder:
    def test_creates_folder_successfully(self):
        fake_folder = {"id": "folder1", "name": "My Reports",
                       "webViewLink": "https://drive.google.com/folder/1"}
        svc = _make_svc()
        svc.files.return_value.create.return_value.execute.return_value = fake_folder
        with _patch(svc):
            result = ds.create_folder("My Reports")
        assert result["status"] == "success"
        assert result["folder"]["name"] == "My Reports"

    def test_folder_mime_type_set(self):
        svc = _make_svc()
        svc.files.return_value.create.return_value.execute.return_value = {
            "id": "f1", "name": "x"}
        with _patch(svc):
            ds.create_folder("Test Folder")
        body = svc.files.return_value.create.call_args.kwargs["body"]
        assert body["mimeType"] == "application/vnd.google-apps.folder"

    def test_parent_id_set_when_provided(self):
        svc = _make_svc()
        svc.files.return_value.create.return_value.execute.return_value = {
            "id": "f1", "name": "x"}
        with _patch(svc):
            ds.create_folder("Sub Folder", parent_id="parent123")
        body = svc.files.return_value.create.call_args.kwargs["body"]
        assert "parent123" in body["parents"]

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.create.return_value.execute.side_effect = Exception(
            "quota exceeded")
        with _patch(svc):
            result = ds.create_folder("Fail Folder")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# move_file
# ─────────────────────────────────────────────────────────────────────────────

class TestMoveFile:
    def test_moves_file_removes_old_parent(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = {
            "parents": ["old_parent"]
        }
        svc.files.return_value.update.return_value.execute.return_value = {
            "id": "file1", "name": "report.pdf", "parents": ["new_parent"]
        }
        with _patch(svc):
            result = ds.move_file("file1", "new_parent")
        assert result["status"] == "success"
        update_kwargs = svc.files.return_value.update.call_args.kwargs
        assert update_kwargs["addParents"] == "new_parent"
        assert update_kwargs["removeParents"] == "old_parent"

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.get.return_value.execute.side_effect = Exception(
            "file not found")
        with _patch(svc):
            result = ds.move_file("bad_id", "dest")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# copy_file
# ─────────────────────────────────────────────────────────────────────────────

class TestCopyFile:
    def test_copies_file(self):
        svc = _make_svc()
        svc.files.return_value.copy.return_value.execute.return_value = {
            "id": "copy1", "name": "Copy of report.pdf"
        }
        with _patch(svc):
            result = ds.copy_file("orig_id")
        assert result["status"] == "success"
        assert result["file"]["id"] == "copy1"

    def test_custom_name_passed_to_api(self):
        svc = _make_svc()
        svc.files.return_value.copy.return_value.execute.return_value = {
            "id": "c2", "name": "Backup Report"
        }
        with _patch(svc):
            ds.copy_file("orig_id", name="Backup Report")
        body = svc.files.return_value.copy.call_args.kwargs["body"]
        assert body["name"] == "Backup Report"


# ─────────────────────────────────────────────────────────────────────────────
# trash_file / restore_file
# ─────────────────────────────────────────────────────────────────────────────

class TestTrashRestoreFile:
    def test_trash_sets_trashed_true(self):
        svc = _make_svc()
        with _patch(svc):
            result = ds.trash_file("file1")
        assert result["status"] == "success"
        assert result["action"] == "trash"
        body = svc.files.return_value.update.call_args.kwargs["body"]
        assert body["trashed"] is True

    def test_restore_sets_trashed_false(self):
        svc = _make_svc()
        with _patch(svc):
            result = ds.restore_file("file1")
        assert result["status"] == "success"
        assert result["action"] == "restore"
        body = svc.files.return_value.update.call_args.kwargs["body"]
        assert body["trashed"] is False

    def test_trash_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.update.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = ds.trash_file("file1")
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# star_file
# ─────────────────────────────────────────────────────────────────────────────

class TestStarFile:
    def test_star_sets_starred_true(self):
        svc = _make_svc()
        with _patch(svc):
            result = ds.star_file("file1", starred=True)
        assert result["status"] == "success"
        assert result["action"] == "starred"

    def test_unstar_sets_starred_false(self):
        svc = _make_svc()
        with _patch(svc):
            result = ds.star_file("file1", starred=False)
        assert result["action"] == "unstarred"


# ─────────────────────────────────────────────────────────────────────────────
# get_storage_quota
# ─────────────────────────────────────────────────────────────────────────────

class TestGetStorageQuota:
    def test_returns_quota_info(self):
        svc = _make_svc()
        svc.about.return_value.get.return_value.execute.return_value = {
            "storageQuota": {
                "usage": str(500 * 1024 * 1024),  # 500 MB
                "limit": str(15 * 1024 ** 3),     # 15 GB
            }
        }
        with _patch(svc):
            result = ds.get_storage_quota()
        assert result["status"] == "success"
        assert "MB" in result["used_human"] or "GB" in result["used_human"]
        assert result["limit_bytes"] == 15 * 1024 ** 3

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.about.return_value.get.return_value.execute.side_effect = Exception(
            "quota error")
        with _patch(svc):
            result = ds.get_storage_quota()
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# upload_file
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadFile:
    def test_missing_local_file_returns_error(self):
        svc = _make_svc()
        with _patch(svc):
            result = ds.upload_file("/nonexistent/path/file.txt")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_uploads_existing_file(self, tmp_path):
        local_file = tmp_path / "test.txt"
        local_file.write_text("hello world")
        fake_result = {
            "id": "uploaded1",
            "name": "test.txt",
            "webViewLink": "https://drive.google.com/file/1",
        }
        svc = _make_svc()
        svc.files.return_value.create.return_value.execute.return_value = fake_result
        with _patch(svc), patch("src.drive.drive_service.MediaFileUpload"):
            result = ds.upload_file(str(local_file))
        assert result["status"] == "success"
        assert result["file"]["id"] == "uploaded1"
