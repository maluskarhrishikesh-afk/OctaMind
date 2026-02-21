"""
Unit tests for src/drive/features/analytics.py (Phase 4).

All Drive API calls are fully mocked — no credentials required.
"""

from __future__ import annotations
import src.drive.features.analytics as anl

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_svc(files=None):
    svc = MagicMock()
    svc.files.return_value.list.return_value.execute.return_value = {
        "files": files or []
    }
    return svc


def _patch(svc):
    return patch("src.drive.features.analytics.get_drive_service", return_value=svc)


# ─────────────────────────────────────────────────────────────────────────────
# _human_size (module-level helper, tested indirectly)
# ─────────────────────────────────────────────────────────────────────────────

class TestHumanSize:
    def test_none_returns_dash(self):
        assert anl._human_size(None) == "—"

    def test_zero_bytes(self):
        result = anl._human_size(0)
        assert "B" in result

    def test_megabytes(self):
        result = anl._human_size(2 * 1024 * 1024)
        assert "2.0 MB" == result


# ─────────────────────────────────────────────────────────────────────────────
# storage_breakdown
# ─────────────────────────────────────────────────────────────────────────────

class TestStorageBreakdown:
    def test_empty_drive(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            result = anl.storage_breakdown()
        assert result["status"] == "success"
        assert result["total_files"] == 0
        assert result["breakdown"] == []

    def test_categorises_by_mime_type(self):
        files = [
            {"id": "1", "name": "doc.pdf",
                "mimeType": "application/pdf", "size": "1048576"},
            {"id": "2", "name": "img.jpg", "mimeType": "image/jpeg", "size": "524288"},
            {"id": "3", "name": "sheet.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "size": "262144"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.storage_breakdown()
        assert result["status"] == "success"
        assert result["total_files"] == 3
        types = [b["type"] for b in result["breakdown"]]
        assert "Pdf" in types or "application" in "".join(types).lower()

    def test_breakdown_sorted_by_size_descending(self):
        files = [
            {"id": "1", "name": "small.txt", "mimeType": "text/plain", "size": "100"},
            {"id": "2", "name": "large.pdf",
                "mimeType": "application/pdf", "size": "999999"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.storage_breakdown()
        # First entry should be the largest type
        assert result["breakdown"][0]["bytes"] >= result["breakdown"][-1]["bytes"]

    def test_total_size_human_populated(self):
        files = [{"id": "1", "name": "f.txt",
                  "mimeType": "text/plain", "size": "2048"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.storage_breakdown()
        assert result["total_size_human"] == "2.0 KB"

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = anl.storage_breakdown()
        assert result["status"] == "error"

    def test_google_drive_folders_labelled_folder(self):
        files = [
            {"id": "1", "name": "My Folder",
             "mimeType": "application/vnd.google-apps.folder", "size": "0"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.storage_breakdown()
        types = [b["type"] for b in result["breakdown"]]
        assert "Folder" in types


# ─────────────────────────────────────────────────────────────────────────────
# list_large_files
# ─────────────────────────────────────────────────────────────────────────────

class TestListLargeFiles:
    def test_returns_large_files(self):
        files = [
            {"id": "1", "name": "huge.mp4",
                "mimeType": "video/mp4", "size": "200000000"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.list_large_files(min_size_mb=10)
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["files"][0]["size_human"]  # populated

    def test_empty_result(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            result = anl.list_large_files()
        assert result["count"] == 0

    def test_min_size_mb_passed_to_query(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            anl.list_large_files(min_size_mb=50.0)
        q = svc.files.return_value.list.call_args.kwargs["q"]
        # 50 MB in bytes = 52428800
        assert "52428800" in q

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = anl.list_large_files()
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# list_old_files
# ─────────────────────────────────────────────────────────────────────────────

class TestListOldFiles:
    def test_returns_old_files(self):
        files = [{"id": "1", "name": "ancient.doc",
                  "mimeType": "application/msword"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.list_old_files(days=365)
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["older_than_days"] == 365

    def test_cutoff_date_in_query(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            anl.list_old_files(days=30)
        q = svc.files.return_value.list.call_args.kwargs["q"]
        assert "modifiedTime <" in q

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = anl.list_old_files()
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# list_recently_modified
# ─────────────────────────────────────────────────────────────────────────────

class TestListRecentlyModified:
    def test_returns_files(self):
        files = [{"id": "1", "name": "new.pdf", "mimeType": "application/pdf"}]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.list_recently_modified()
        assert result["status"] == "success"
        assert result["count"] == 1

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = anl.list_recently_modified()
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# sharing_report
# ─────────────────────────────────────────────────────────────────────────────

class TestSharingReport:
    def test_counts_shared_and_private(self):
        files = [
            {"id": "1", "name": "shared.pdf", "shared": True,
                "mimeType": "application/pdf"},
            {"id": "2", "name": "private.pdf", "shared": False,
                "mimeType": "application/pdf"},
            {"id": "3", "name": "also_shared.pdf",
                "shared": True, "mimeType": "application/pdf"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.sharing_report()
        assert result["status"] == "success"
        assert result["shared_count"] == 2
        assert result["private_count"] == 1
        assert result["total_files"] == 3

    def test_all_private(self):
        files = [
            {"id": "1", "name": "a.pdf", "shared": False,
                "mimeType": "application/pdf"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = anl.sharing_report()
        assert result["shared_count"] == 0
        assert result["private_count"] == 1

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "err")
        with _patch(svc):
            result = anl.sharing_report()
        assert result["status"] == "error"
