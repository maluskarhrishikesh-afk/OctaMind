"""
Unit tests for src/agent/ui/drive_agent/formatters.py and orchestrator.py.

All Drive API calls and LLM calls are fully mocked — no credentials required.
"""

from __future__ import annotations
from src.agent.ui.drive_agent.orchestrator import execute_with_llm_orchestration
from src.agent.ui.drive_agent.formatters import format_drive_result

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# format_drive_result
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatDriveResult:

    # ── Error state ───────────────────────────────────────────────────────────

    def test_error_status_shows_error_message(self):
        result = {"status": "error", "message": "not authenticated"}
        out = format_drive_result(result, "list_files")
        assert "Error" in out
        assert "not authenticated" in out

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    def test_list_files_shows_file_names(self):
        result = {
            "status": "success",
            "files": [
                {"id": "f1", "name": "report.pdf",
                    "mimeType": "application/pdf", "size_human": "1.0 MB"},
                {"id": "f2", "name": "notes.txt",
                    "mimeType": "text/plain", "size_human": "10.0 B"},
            ],
        }
        out = format_drive_result(result, "list_files")
        assert "report.pdf" in out
        assert "notes.txt" in out

    def test_list_files_empty(self):
        result = {"status": "success", "files": []}
        out = format_drive_result(result, "list_files")
        assert "No files" in out

    def test_list_files_shows_file_ids(self):
        result = {
            "status": "success",
            "files": [{"id": "abc123", "name": "doc.pdf", "mimeType": "application/pdf"}],
        }
        out = format_drive_result(result, "list_files")
        assert "abc123" in out

    def test_search_files_shows_query(self):
        result = {
            "status": "success",
            "files": [],
            "query": "name contains 'budget'",
        }
        out = format_drive_result(result, "search_files")
        assert "budget" in out

    def test_upload_shows_file_name(self):
        result = {
            "status": "success",
            "action": "upload",
            "file": {
                "id": "up1",
                "name": "report.pdf",
                "size_human": "2.0 MB",
                "webViewLink": "https://drive.google.com/file/up1",
            },
        }
        out = format_drive_result(result, "upload")
        assert "report.pdf" in out
        assert "up1" in out

    def test_download_shows_local_path(self):
        result = {
            "status": "success",
            "action": "download",
            "file_name": "report.pdf",
            "local_path": "/downloads/report.pdf",
            "size_human": "2.0 MB",
        }
        out = format_drive_result(result, "download")
        assert "/downloads/report.pdf" in out

    def test_create_folder_shows_folder_name(self):
        result = {
            "status": "success",
            "action": "create_folder",
            "folder": {"id": "fold1", "name": "My Reports", "webViewLink": None},
        }
        out = format_drive_result(result, "create_folder")
        assert "My Reports" in out

    def test_trash_shows_file_id(self):
        result = {"status": "success", "action": "trash", "file_id": "file123"}
        out = format_drive_result(result, "trash")
        assert "file123" in out
        assert "trash" in out.lower()

    def test_restore_shows_success(self):
        result = {"status": "success",
                  "action": "restore", "file_id": "file123"}
        out = format_drive_result(result, "restore")
        assert "file123" in out

    def test_star_shows_starred(self):
        result = {"status": "success",
                  "action": "starred", "file_id": "file123"}
        out = format_drive_result(result, "starred")
        assert "⭐" in out or "starred" in out.lower()

    def test_storage_quota_shows_usage(self):
        result = {
            "status": "success",
            "used_human": "5.0 GB",
            "free_human": "10.0 GB",
            "limit_human": "15.0 GB",
        }
        out = format_drive_result(result, "storage_quota")
        assert "5.0 GB" in out

    # ── Phase 2 ───────────────────────────────────────────────────────────────

    def test_share_shows_email_and_role(self):
        result = {
            "status": "success",
            "action": "share",
            "permission": {"id": "p1"},
            "shared_with": "alice@example.com",
            "role": "reader",
        }
        out = format_drive_result(result, "share")
        assert "alice@example.com" in out
        assert "reader" in out

    def test_list_permissions_shows_count(self):
        result = {
            "status": "success",
            "permissions": [
                {"id": "p1", "type": "user", "role": "reader",
                 "emailAddress": "a@b.com", "displayName": "Alice"},
            ],
        }
        out = format_drive_result(result, "list_permissions")
        assert "Alice" in out or "a@b.com" in out

    def test_make_public_shows_link(self):
        result = {
            "status": "success",
            "action": "make_public",
            "link": "https://drive.google.com/file/public",
        }
        out = format_drive_result(result, "make_public")
        assert "https://drive.google.com/file/public" in out

    def test_remove_public_shows_revoked_count(self):
        result = {"status": "success",
                  "action": "remove_public", "revoked_count": 1}
        out = format_drive_result(result, "remove_public")
        assert "revoked" in out.lower() or "1" in out

    # ── Phase 3 ───────────────────────────────────────────────────────────────

    def test_summarize_file_shows_summary(self):
        result = {
            "status": "success",
            "file_name": "strategy.docx",
            "summary": "This document outlines the 2026 strategy.",
        }
        out = format_drive_result(result, "summarize_file")
        assert "strategy.docx" in out
        assert "2026 strategy" in out

    def test_find_duplicates_with_groups(self):
        result = {
            "status": "success",
            "duplicate_groups": [
                {"name": "report.pdf", "count": 3, "files": []},
            ],
            "group_count": 1,
            "total_duplicates": 2,
        }
        out = format_drive_result(result, "find_duplicates")
        assert "report.pdf" in out
        assert "1" in out

    def test_find_duplicates_no_groups(self):
        result = {
            "status": "success",
            "duplicate_groups": [],
            "group_count": 0,
            "total_duplicates": 0,
            "files_scanned": 50,
        }
        out = format_drive_result(result, "find_duplicates")
        assert "No duplicates" in out or "✅" in out

    def test_bulk_rename_shows_count(self):
        result = {
            "status": "success",
            "action": "bulk_rename",
            "dry_run": False,
            "renamed_count": 3,
            "renames": [
                {"old": "report_2025.pdf", "new": "report_2026.pdf"},
                {"old": "budget_2025.xlsx", "new": "budget_2026.xlsx"},
                {"old": "summary_2025.txt", "new": "summary_2026.txt"},
            ],
        }
        out = format_drive_result(result, "bulk_rename")
        assert "3" in out
        assert "report_2025.pdf" in out

    # ── Phase 4 ───────────────────────────────────────────────────────────────

    def test_storage_breakdown_shows_types(self):
        result = {
            "status": "success",
            "breakdown": [
                {"type": "Pdf", "count": 20,
                    "bytes": 10000000, "size_human": "9.5 MB"},
            ],
            "total_files": 20,
            "total_size_human": "9.5 MB",
        }
        out = format_drive_result(result, "storage_breakdown")
        assert "Pdf" in out
        assert "9.5 MB" in out

    def test_list_large_files_shows_names(self):
        result = {
            "status": "success",
            "files": [{"name": "video.mp4", "size_human": "500.0 MB"}],
            "count": 1,
            "min_size_mb": 50,
        }
        out = format_drive_result(result, "list_large_files")
        assert "video.mp4" in out

    def test_sharing_report_shows_counts(self):
        result = {
            "status": "success",
            "total_files": 100,
            "shared_count": 25,
            "private_count": 75,
        }
        out = format_drive_result(result, "sharing_report")
        assert "25" in out
        assert "75" in out

    def test_reasoning_appended_when_present(self):
        result = {
            "status": "success",
            "files": [],
            "reasoning": "User asked for recent files",
        }
        out = format_drive_result(result, "list_files")
        assert "User asked for recent files" in out

    def test_unknown_action_returns_completed_message(self):
        result = {"status": "success"}
        out = format_drive_result(result, "unknown_action_xyz")
        assert "unknown_action_xyz" in out or "completed" in out.lower()


# ─────────────────────────────────────────────────────────────────────────────
# execute_with_llm_orchestration
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteWithLlmOrchestration:

    def _mock_llm(self, tool: str, params: dict, reasoning: str = ""):
        client = MagicMock()
        client.orchestrate_mcp_tool.return_value = {
            "tool": tool,
            "params": params,
            "reasoning": reasoning,
        }
        return client

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    def test_list_files_tool(self):
        llm = self._mock_llm("list_files", {"max_results": 10})
        mock_files = [{"id": "f1", "name": "report.pdf",
                       "mimeType": "application/pdf"}]
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.list_files", return_value=mock_files):
            result = execute_with_llm_orchestration("list my files")
        assert result["status"] == "success"
        assert result["action"] == "list_files"
        assert len(result["files"]) == 1

    def test_search_files_tool(self):
        llm = self._mock_llm(
            "search_files", {"query": "name contains 'budget'", "max_results": 5})
        mock_files = [{"id": "s1", "name": "budget.xlsx"}]
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.search_files", return_value=mock_files):
            result = execute_with_llm_orchestration("find budget files")
        assert result["status"] == "success"
        assert result["action"] == "search_files"

    def test_get_file_info_tool(self):
        llm = self._mock_llm("get_file_info", {"file_id": "file123"})
        fake_info = {"status": "success", "file": {
            "id": "file123", "name": "doc.pdf"}}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.get_file_info", return_value=fake_info):
            result = execute_with_llm_orchestration("info about file123")
        assert result["action"] == "file_info"

    def test_create_folder_tool(self):
        llm = self._mock_llm("create_folder", {"name": "Reports 2026"})
        fake = {"status": "success", "action": "create_folder",
                "folder": {"id": "f1", "name": "Reports 2026"}}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.create_folder", return_value=fake):
            result = execute_with_llm_orchestration(
                "create folder Reports 2026")
        assert result["status"] == "success"

    def test_trash_file_tool(self):
        llm = self._mock_llm("trash_file", {"file_id": "old_file"})
        fake = {"status": "success", "action": "trash", "file_id": "old_file"}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.trash_file", return_value=fake):
            result = execute_with_llm_orchestration("delete old_file")
        assert result["status"] == "success"

    def test_get_storage_quota_tool(self):
        llm = self._mock_llm("get_storage_quota", {})
        fake = {
            "status": "success",
            "used_human": "5 GB", "limit_human": "15 GB",
            "free_human": "10 GB",
        }
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.get_storage_quota", return_value=fake):
            result = execute_with_llm_orchestration(
                "how much storage do I have?")
        assert result["action"] == "storage_quota"

    # ── Phase 2 ───────────────────────────────────────────────────────────────

    def test_share_file_tool(self):
        llm = self._mock_llm(
            "share_file", {"file_id": "f1", "email": "bob@test.com", "role": "reader"})
        fake = {"status": "success", "action": "share", "permission": {},
                "shared_with": "bob@test.com", "role": "reader"}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.share_file", return_value=fake):
            result = execute_with_llm_orchestration("share f1 with bob")
        assert result["status"] == "success"

    def test_make_public_tool(self):
        llm = self._mock_llm("make_public", {"file_id": "f1"})
        fake = {"status": "success",
                "action": "make_public", "link": "https://..."}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.make_public", return_value=fake):
            result = execute_with_llm_orchestration("make f1 public")
        assert result["status"] == "success"

    # ── Phase 3 ───────────────────────────────────────────────────────────────

    def test_find_duplicates_tool(self):
        llm = self._mock_llm("find_duplicates", {})
        fake = {"status": "success", "duplicate_groups": [],
                "group_count": 0, "total_duplicates": 0, "files_scanned": 0}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.find_duplicates", return_value=fake):
            result = execute_with_llm_orchestration("find duplicate files")
        assert result["action"] == "find_duplicates"

    def test_summarize_file_tool(self):
        llm = self._mock_llm("summarize_file", {"file_id": "doc1"})
        fake = {"status": "success", "file_name": "strategy.docx",
                "summary": "Summary text."}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.summarize_file", return_value=fake):
            result = execute_with_llm_orchestration("summarize doc1")
        assert result["action"] == "summarize_file"

    def test_bulk_rename_tool(self):
        llm = self._mock_llm(
            "bulk_rename", {"folder_id": "fold1", "pattern": "2025", "replacement": "2026"})
        fake = {"status": "success", "action": "bulk_rename",
                "dry_run": True, "renamed_count": 3, "renames": []}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.bulk_rename", return_value=fake):
            result = execute_with_llm_orchestration(
                "rename all 2025 files to 2026 in fold1")
        assert result["status"] == "success"

    # ── Phase 4 ───────────────────────────────────────────────────────────────

    def test_storage_breakdown_tool(self):
        llm = self._mock_llm("storage_breakdown", {})
        fake = {"status": "success", "breakdown": [],
                "total_files": 0, "total_size_human": "0 B"}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.storage_breakdown", return_value=fake):
            result = execute_with_llm_orchestration("show storage breakdown")
        assert result["action"] == "storage_breakdown"

    def test_generate_drive_report_tool(self):
        llm = self._mock_llm("generate_drive_report", {})
        fake = {"status": "success", "report_markdown": "# Report"}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.generate_drive_report", return_value=fake):
            result = execute_with_llm_orchestration(
                "generate drive health report")
        assert result["action"] == "drive_report"

    def test_get_usage_insights_tool(self):
        llm = self._mock_llm("get_usage_insights", {})
        fake = {"status": "success",
                "insights": "Clean up old files.", "report": "# Report"}
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.get_usage_insights", return_value=fake):
            result = execute_with_llm_orchestration(
                "give me insights about my drive")
        assert result["action"] == "usage_insights"

    # ── Safety / edge cases ───────────────────────────────────────────────────

    def test_unknown_tool_returns_error(self):
        llm = self._mock_llm("nonexistent_drive_tool", {})
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm):
            result = execute_with_llm_orchestration("do something unknown")
        assert result["status"] == "error"

    def test_max_operations_clamps_max_results(self):
        """max_results should be silently clamped to max_operations."""
        llm = self._mock_llm("list_files", {"max_results": 500})
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.list_files", return_value=[]) as mock_list:
            execute_with_llm_orchestration("list files", max_operations=10)
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs["max_results"] == 10

    def test_capped_note_added_when_clamped(self):
        """When clamped, the reasoning note should mention the cap."""
        llm = self._mock_llm(
            "list_files", {"max_results": 500}, reasoning="listing files")
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
                patch("src.agent.ui.drive_agent.orchestrator.list_files", return_value=[]):
            result = execute_with_llm_orchestration(
                "list files", max_operations=5)
        assert "capped" in result.get("reasoning", "").lower(
        ) or "limit" in result.get("reasoning", "").lower()

    def test_llm_exception_returns_error_dict(self):
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client",
                   side_effect=Exception("LLM down")):
            result = execute_with_llm_orchestration("list files")
        assert result["status"] == "error"

    def test_drive_api_exception_returns_error_dict(self):
        llm = self._mock_llm("list_files", {"max_results": 10})
        with patch("src.agent.ui.drive_agent.orchestrator.get_llm_client", return_value=llm), \
            patch("src.agent.ui.drive_agent.orchestrator.list_files",
                  side_effect=Exception("Drive API error")):
            result = execute_with_llm_orchestration("list files")
        assert result["status"] == "error"
