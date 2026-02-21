"""
Unit tests for src/drive/features/duplicates.py (Phase 3).

All Drive API calls are fully mocked — no credentials required.
"""

from __future__ import annotations
import src.drive.features.duplicates as dup

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
    svc.files.return_value.update.return_value.execute.return_value = {}
    return svc


def _patch(svc):
    return patch("src.drive.features.duplicates.get_drive_service", return_value=svc)


class TestFindDuplicates:
    def test_no_files_returns_empty(self):
        svc = _make_svc(files=[])
        with _patch(svc):
            result = dup.find_duplicates()
        assert result["status"] == "success"
        assert result["group_count"] == 0
        assert result["total_duplicates"] == 0

    def test_unique_files_no_duplicates(self):
        files = [
            {"id": "1", "name": "a.txt", "size": "100",
                "mimeType": "text/plain", "createdTime": "2026-01-01"},
            {"id": "2", "name": "b.txt", "size": "200",
                "mimeType": "text/plain", "createdTime": "2026-01-02"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = dup.find_duplicates()
        assert result["group_count"] == 0
        assert result["total_duplicates"] == 0

    def test_detects_duplicates_by_name_and_size(self):
        files = [
            {"id": "1", "name": "report.pdf", "size": "5000",
                "mimeType": "application/pdf", "createdTime": "2026-01-01"},
            {"id": "2", "name": "report.pdf", "size": "5000",
                "mimeType": "application/pdf", "createdTime": "2026-01-02"},
            {"id": "3", "name": "report.pdf", "size": "5000",
                "mimeType": "application/pdf", "createdTime": "2026-01-03"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = dup.find_duplicates()
        assert result["group_count"] == 1
        assert result["total_duplicates"] == 2  # 3 copies - 1 = 2 redundant

    def test_files_scanned_count(self):
        files = [
            {"id": "1", "name": "x.pdf", "size": "100",
                "mimeType": "application/pdf", "createdTime": "2026-01-01"},
            {"id": "2", "name": "y.pdf", "size": "200",
                "mimeType": "application/pdf", "createdTime": "2026-01-02"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = dup.find_duplicates()
        assert result["files_scanned"] == 2

    def test_different_sizes_not_duplicates(self):
        """Same name but different sizes should NOT be flagged as duplicates."""
        files = [
            {"id": "1", "name": "doc.txt", "size": "100",
                "mimeType": "text/plain", "createdTime": "2026-01-01"},
            {"id": "2", "name": "doc.txt", "size": "200",
                "mimeType": "text/plain", "createdTime": "2026-01-02"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = dup.find_duplicates()
        assert result["group_count"] == 0

    def test_api_error_returns_error_dict(self):
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.side_effect = Exception(
            "API error")
        with _patch(svc):
            result = dup.find_duplicates()
        assert result["status"] == "error"


class TestTrashDuplicates:
    def test_dry_run_does_not_call_update(self):
        files = [
            {"id": "1", "name": "dup.pdf", "size": "100",
                "mimeType": "application/pdf", "createdTime": "2026-01-01"},
            {"id": "2", "name": "dup.pdf", "size": "100",
                "mimeType": "application/pdf", "createdTime": "2026-01-02"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = dup.trash_duplicates(dry_run=True)
        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["trashed_count"] == 1
        # No actual update calls should be made
        svc.files.return_value.update.assert_not_called()

    def test_trashes_all_but_oldest(self):
        """The oldest file (earliest createdTime) should be kept."""
        files = [
            {"id": "old", "name": "x.pdf", "size": "100",
                "mimeType": "application/pdf", "createdTime": "2026-01-01"},
            {"id": "new", "name": "x.pdf", "size": "100",
                "mimeType": "application/pdf", "createdTime": "2026-01-03"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = dup.trash_duplicates(dry_run=False)
        assert result["trashed_count"] == 1
        # The "new" file (id="new") should be trashed, not the "old" one
        call_args = svc.files.return_value.update.call_args
        assert call_args.kwargs["fileId"] == "new"

    def test_no_duplicates_trashes_nothing(self):
        files = [
            {"id": "1", "name": "unique.pdf", "size": "100",
                "mimeType": "application/pdf", "createdTime": "2026-01-01"},
        ]
        svc = _make_svc(files=files)
        with _patch(svc):
            result = dup.trash_duplicates()
        assert result["trashed_count"] == 0
