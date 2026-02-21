"""
Tests for execute_with_llm_orchestration and format_email_result.

The old API (parse_email_command / execute_email_action) was replaced by
execute_with_llm_orchestration() + format_email_result().  These tests
cover both via mocks — no network / live credentials needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.agent.ui.email_agent_ui import execute_with_llm_orchestration, format_email_result


# ── format_email_result ───────────────────────────────────────────────────────

class TestFormatEmailResult:
    def test_error_status_returns_error_message(self):
        result = {"status": "error", "message": "token expired"}
        output = format_email_result(result, "count")
        assert "Error" in output
        assert "token expired" in output

    def test_count_action_shows_statistics(self):
        result = {
            "status": "success",
            "total_messages": 1234,
            "unread_messages": 56,
            "total_threads": 800,
            "unread_threads": 30,
        }
        output = format_email_result(result, "count")
        assert "1,234" in output
        assert "56" in output

    def test_count_filtered_shows_count_and_query(self):
        result = {"status": "success", "count": 42,
                  "query": "from:boss@corp.com"}
        output = format_email_result(result, "count_filtered")
        assert "42" in output
        assert "boss@corp.com" in output

    def test_list_todays_no_emails(self):
        result = {"status": "success", "emails": [], "count": 0}
        output = format_email_result(result, "list_todays")
        assert "No emails" in output

    def test_list_todays_with_emails_shows_subjects(self):
        result = {
            "status": "success",
            "count": 2,
            "emails": [
                {"id": "m1", "subject": "Hello World",
                    "sender": "a@b.com", "date": "2026-02-21"},
                {"id": "m2", "subject": "Meeting at 3pm",
                    "sender": "c@d.com", "date": "2026-02-21"},
            ],
        }
        output = format_email_result(result, "list_todays")
        assert "Hello World" in output
        assert "Meeting at 3pm" in output

    def test_send_action_shows_message_id(self):
        result = {"status": "success",
                  "messageId": "abc123", "threadId": "t456"}
        output = format_email_result(result, "send")
        assert "abc123" in output

    def test_reasoning_appended_when_present(self):
        result = {"status": "success", "count": 5,
                  "reasoning": "Filtered by sender"}
        output = format_email_result(result, "count_filtered")
        assert "Filtered by sender" in output


# ── execute_with_llm_orchestration ────────────────────────────────────────────

class TestExecuteWithLlmOrchestration:
    """Tests that LLM tool decisions are dispatched correctly without any
    real LLM or Gmail API calls."""

    def _mock_llm(self, tool: str, params: dict, reasoning: str = ""):
        """Return a mock get_llm_client whose orchestrate_mcp_tool returns the given decision."""
        mock_client = MagicMock()
        mock_client.orchestrate_mcp_tool.return_value = {
            "tool": tool,
            "params": params,
            "reasoning": reasoning,
        }
        return mock_client

    def test_count_tool_returns_inbox_stats(self):
        # count_messages handler calls list_emails(max_results=1000) internally
        mock_client = self._mock_llm("count_messages", {})
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", return_value=[{"id": f"m{i}"} for i in range(42)]):
            result = execute_with_llm_orchestration(
                "how many emails do I have?")
        assert result["status"] == "success"
        assert result["action"] == "count_filtered"
        assert result["count"] == 42

    def test_list_message_tool_returns_email_list(self):
        mock_client = self._mock_llm(
            "list_message", {"query": "is:unread", "max_results": 10})
        mock_emails = [{"id": "1", "subject": "Test", "sender": "a@b.com"}]
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", return_value=mock_emails):
            result = execute_with_llm_orchestration("show my unread emails")
        assert result["status"] == "success"
        assert result["action"] == "list"
        assert result["count"] == 1

    def test_send_tool_sends_email(self):
        mock_client = self._mock_llm(
            "send_message",
            {"to": "x@y.com", "subject": "Hi", "message_text": "Hello"},
        )
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
            patch("src.agent.ui.email_agent.orchestrator.send_email",
                  return_value={"status": "success", "messageId": "msg1"}):
            result = execute_with_llm_orchestration(
                "send email to x@y.com subject Hi message Hello")
        assert result["action"] == "send"
        assert result.get("messageId") == "msg1"

    def test_llm_failure_returns_error(self):
        mock_client = MagicMock()
        mock_client.orchestrate_mcp_tool.side_effect = Exception(
            "LLM connection reset")
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client):
            result = execute_with_llm_orchestration("count emails")
        assert result["status"] == "error"

    def test_reasoning_propagated_to_result(self):
        mock_client = self._mock_llm(
            "list_message",
            {"query": "from:boss", "max_results": 5},
            reasoning="Listing emails from boss as requested",
        )
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", return_value=[]):
            result = execute_with_llm_orchestration("emails from boss")
        assert "Listing emails from boss" in result.get("reasoning", "")


# ── max_operations enforcement ────────────────────────────────────────────────

class TestMaxOperationsEnforcement:
    """Verify that the max_operations guard clamps bulk-fetch parameters and
    surfaces a cap warning in the result's reasoning field."""

    def _llm(self, tool, params, reasoning=""):
        mock_client = MagicMock()
        mock_client.orchestrate_mcp_tool.return_value = {
            "tool": tool, "params": params, "reasoning": reasoning
        }
        return mock_client

    def test_list_message_capped_when_max_results_exceeds_limit(self):
        """LLM requests more emails than max_operations allows — list_emails receives capped value."""
        captured = {}

        def fake_list_emails(query="", max_results=10):
            captured["max_results"] = max_results
            return []

        mock_client = self._llm(
            "list_message", {"query": "", "max_results": 500})
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", side_effect=fake_list_emails):
            execute_with_llm_orchestration(
                "show all emails", max_operations=10)

        assert captured["max_results"] == 10

    def test_cap_warning_appears_in_reasoning_when_clamped(self):
        """When results are capped, the reasoning note includes the warning text."""
        mock_client = self._llm(
            "list_message", {"query": "", "max_results": 999})
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", return_value=[]):
            result = execute_with_llm_orchestration(
                "list emails", max_operations=5)

        assert "capped" in result.get("reasoning", "").lower() or \
               "max operations" in result.get("reasoning", "").lower()

    def test_no_cap_note_when_within_limit(self):
        """No warning when requested count is within max_operations."""
        mock_client = self._llm(
            "list_message", {"query": "", "max_results": 5})
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", return_value=[]):
            result = execute_with_llm_orchestration(
                "list 5 emails", max_operations=100)

        assert "capped" not in result.get("reasoning", "").lower()

    def test_apply_smart_labels_batch_size_capped(self):
        """apply_smart_labels batch_size is capped to max_operations."""
        captured = {}

        def fake_apply(batch_size=20):
            captured["batch_size"] = batch_size
            return {"status": "success", "labeled": 0}

        mock_client = self._llm("apply_smart_labels", {"batch_size": 200})
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.apply_smart_labels", side_effect=fake_apply):
            execute_with_llm_orchestration(
                "label my emails", max_operations=15)

        assert captured["batch_size"] == 15

    def test_count_messages_capped_to_max_operations(self):
        """count_messages internally lists emails — that fetch is capped too."""
        captured = {}

        def fake_list(query="", max_results=10):
            captured["max_results"] = max_results
            return []

        mock_client = self._llm("count_messages", {})
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", side_effect=fake_list):
            result = execute_with_llm_orchestration(
                "count all emails", max_operations=50)

        assert captured["max_results"] == 50
        assert result["action"] == "count_filtered"

    def test_default_max_operations_is_100(self):
        """Default max_operations of 100 is used when arg not supplied."""
        captured = {}

        def fake_list(query="", max_results=10):
            captured["max_results"] = max_results
            return []

        mock_client = self._llm(
            "list_message", {"query": "", "max_results": 50})
        with patch("src.agent.ui.email_agent.orchestrator.get_llm_client", return_value=mock_client), \
                patch("src.agent.ui.email_agent.orchestrator.list_emails", side_effect=fake_list):
            execute_with_llm_orchestration("list emails")

        # 50 < 100 default, so no capping — value passes unchanged
        assert captured["max_results"] == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
