"""
Unit tests for src/drive/features/summarizer.py (Phase 3).

All Drive API calls and LLM calls are fully mocked — no credentials required.
"""

from __future__ import annotations
import src.drive.features.summarizer as summ

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_svc():
    svc = MagicMock()
    return svc


def _patch_svc(svc):
    return patch("src.drive.features.summarizer.get_drive_service", return_value=svc)


def _patch_llm(llm=None):
    """Patch get_llm_client at the module where it is imported (locally inside the fn)."""
    if llm is None:
        llm = MagicMock()
        llm.generate.return_value = "This is a summary."
    return patch("src.agent.llm.llm_parser.get_llm_client", return_value=llm)


def _patch_fetch_text(text: str = "Hello world content"):
    """Patch the internal _fetch_text helper to return controllable text."""
    return patch("src.drive.features.summarizer._fetch_text", return_value=text)


# ─────────────────────────────────────────────────────────────────────────────
# summarize_file
# ─────────────────────────────────────────────────────────────────────────────

class TestSummarizeFile:
    def test_binary_mime_type_returns_unavailable(self):
        """Binary files (e.g. images) should return a graceful "not available" message."""
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = {
            "id": "f1",
            "name": "photo.jpg",
            "mimeType": "image/jpeg",
        }

        mock_llm = MagicMock()
        with _patch_svc(svc), _patch_llm(mock_llm):
            result = summ.summarize_file("f1")

        assert result["status"] == "success"
        assert "not available" in result["summary"].lower(
        ) or "binary" in result["summary"].lower()
        mock_llm.generate.assert_not_called()

    def test_text_file_fetches_and_calls_llm(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = {
            "id": "f1",
            "name": "readme.txt",
            "mimeType": "text/plain",
        }
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "A simple greeting document."

        with _patch_svc(svc), _patch_fetch_text("Hello world content"), _patch_llm(mock_llm):
            result = summ.summarize_file("f1")

        assert result["status"] == "success"
        assert "greeting" in result["summary"]

    def test_google_doc_exports_as_plain_text(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = {
            "id": "f2",
            "name": "My Doc",
            "mimeType": "application/vnd.google-apps.document",
        }
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Export-based summary."

        with _patch_svc(svc), _patch_fetch_text("Exported doc content"), _patch_llm(mock_llm):
            result = summ.summarize_file("f2")

        assert result["status"] == "success"
        assert "Export-based summary" in result["summary"]

    def test_file_not_found_returns_error(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.side_effect = Exception(
            "404 Not Found")

        with _patch_svc(svc):
            result = summ.summarize_file("missing_id")

        assert result["status"] == "error"

    def test_llm_error_returns_error(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = {
            "id": "f3",
            "name": "notes.txt",
            "mimeType": "text/plain",
        }
        bad_llm = MagicMock()
        bad_llm.generate.side_effect = Exception("LLM unavailable")

        with _patch_svc(svc), _patch_fetch_text("Some content"), _patch_llm(bad_llm):
            result = summ.summarize_file("f3")

        assert result["status"] == "error"

    def test_result_contains_file_name(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.return_value = {
            "id": "f4",
            "name": "strategy.txt",
            "mimeType": "text/plain",
        }
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Strategic summary."

        with _patch_svc(svc), _patch_fetch_text("Strategy content here"), _patch_llm(mock_llm):
            result = summ.summarize_file("f4")

        assert result["file_name"] == "strategy.txt"


# ─────────────────────────────────────────────────────────────────────────────
# summarize_folder
# ─────────────────────────────────────────────────────────────────────────────

class TestSummarizeFolder:
    def _mock_folder_and_files(self, svc, folder_name, files):
        """Wire folder metadata and file listing mock."""
        get_mock = MagicMock()
        # First .get() call returns folder info, subsequent call for each file
        svc.files.return_value.get.return_value.execute.return_value = {
            "id": "folder1",
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        svc.files.return_value.list.return_value.execute.return_value = {
            "files": files}

    def test_empty_folder(self):
        svc = _make_svc()
        self._mock_folder_and_files(svc, "Empty Folder", [])

        with _patch_svc(svc):
            result = summ.summarize_folder("folder1")

        assert result["status"] == "success"
        assert "empty" in result["summary"].lower()
        assert result["total"] == 0

    def test_folder_with_files(self):
        svc = _make_svc()
        files = [
            {"id": "f1", "name": "report.pdf", "mimeType": "application/pdf"},
            {"id": "f2", "name": "budget.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            {"id": "f3", "name": "notes.txt", "mimeType": "text/plain"},
        ]
        self._mock_folder_and_files(svc, "Work Docs", files)

        with _patch_svc(svc):
            result = summ.summarize_folder("folder1")

        assert result["status"] == "success"
        assert result["total"] == 3
        assert result["folder_name"] == "Work Docs"

    def test_summary_mentions_file_types(self):
        svc = _make_svc()
        files = [
            {"id": "f1", "name": "image.jpg", "mimeType": "image/jpeg"},
            {"id": "f2", "name": "video.mp4", "mimeType": "video/mp4"},
        ]
        self._mock_folder_and_files(svc, "Media", files)

        with _patch_svc(svc):
            result = summ.summarize_folder("folder1")

        assert result["status"] == "success"
        # summary should mention file types or names
        assert "image.jpg" in result["summary"] or "jpeg" in result["summary"].lower(
        ) or "2 file" in result["summary"].lower()

    def test_folder_not_found_returns_error(self):
        svc = _make_svc()
        svc.files.return_value.get.return_value.execute.side_effect = Exception(
            "404 Not Found")

        with _patch_svc(svc):
            result = summ.summarize_folder("missing_folder")

        assert result["status"] == "error"
