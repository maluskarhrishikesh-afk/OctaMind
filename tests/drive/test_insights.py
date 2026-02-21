"""
Unit tests for src/drive/features/insights.py (Phase 4).

All Drive API calls and LLM calls are fully mocked.
"""

from __future__ import annotations
import src.drive.features.insights as ins

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _patch_analytics(
    storage_result=None,
    large_result=None,
    old_result=None,
    sharing_result=None,
):
    """Patch all analytics functions used by insights."""
    default_storage = {
        "status": "success",
        "total_files": 100,
        "total_size_human": "500.0 MB",
        "breakdown": [{"type": "Pdf", "count": 50, "size_human": "400 MB"}],
    }
    default_large = {"status": "success", "count": 5, "min_size_mb": 50,
                     "files": [{"name": "big.mp4", "size_human": "100 MB"}]}
    default_old = {"status": "success", "count": 10,
                   "files": [{"name": "old.doc", "modifiedTime": "2020-01-01"}]}
    default_sharing = {"status": "success", "total_files": 100,
                       "shared_count": 30, "private_count": 70}

    return [
        patch("src.drive.features.insights.storage_breakdown",
              return_value=storage_result or default_storage),
        patch("src.drive.features.insights.list_large_files",
              return_value=large_result or default_large),
        patch("src.drive.features.insights.list_old_files",
              return_value=old_result or default_old),
        patch("src.drive.features.insights.sharing_report",
              return_value=sharing_result or default_sharing),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# generate_drive_report
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateDriveReport:
    def test_returns_markdown_report(self):
        patches = _patch_analytics()
        with patches[0], patches[1], patches[2], patches[3]:
            result = ins.generate_drive_report()
        assert result["status"] == "success"
        assert "report_markdown" in result
        assert "Drive Health Report" in result["report_markdown"]

    def test_report_contains_storage_info(self):
        patches = _patch_analytics()
        with patches[0], patches[1], patches[2], patches[3]:
            result = ins.generate_drive_report()
        assert "500.0 MB" in result["report_markdown"]
        assert "100" in result["report_markdown"]  # total files

    def test_report_contains_large_files_section(self):
        patches = _patch_analytics()
        with patches[0], patches[1], patches[2], patches[3]:
            result = ins.generate_drive_report()
        assert "Large Files" in result["report_markdown"]

    def test_report_contains_sharing_section(self):
        patches = _patch_analytics()
        with patches[0], patches[1], patches[2], patches[3]:
            result = ins.generate_drive_report()
        assert "Sharing" in result["report_markdown"]
        assert "30" in result["report_markdown"]  # shared count

    def test_no_large_files_shows_checkmark(self):
        large_result = {"status": "success",
                        "count": 0, "min_size_mb": 50, "files": []}
        patches = _patch_analytics(large_result=large_result)
        with patches[0], patches[1], patches[2], patches[3]:
            result = ins.generate_drive_report()
        assert "✅" in result["report_markdown"]

    def test_analytics_error_propagates(self):
        with patch("src.drive.features.insights.storage_breakdown",
                   side_effect=Exception("API error")):
            result = ins.generate_drive_report()
        assert result["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# get_usage_insights
# ─────────────────────────────────────────────────────────────────────────────

class TestGetUsageInsights:
    def test_returns_llm_generated_insights(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "1. Clean up large files. 2. Organise by date."

        patches = _patch_analytics()
        with patches[0], patches[1], patches[2], patches[3], \
                patch("src.agent.llm.llm_parser.get_llm_client", return_value=mock_llm):
            result = ins.get_usage_insights()

        assert result["status"] == "success"
        assert "Clean up large files" in result["insights"]

    def test_report_included_in_result(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Some insights."

        patches = _patch_analytics()
        with patches[0], patches[1], patches[2], patches[3], \
                patch("src.agent.llm.llm_parser.get_llm_client", return_value=mock_llm):
            result = ins.get_usage_insights()

        assert "report" in result
        assert "Drive Health Report" in result["report"]

    def test_report_generation_error_propagates(self):
        with patch("src.drive.features.insights.generate_drive_report",
                   return_value={"status": "error", "message": "API down"}):
            result = ins.get_usage_insights()
        assert result["status"] == "error"

    def test_llm_error_returns_error_dict(self):
        patches = _patch_analytics()
        with patches[0], patches[1], patches[2], patches[3], \
            patch("src.agent.llm.llm_parser.get_llm_client",
                  side_effect=Exception("LLM unavailable")):
            result = ins.get_usage_insights()
        assert result["status"] == "error"
