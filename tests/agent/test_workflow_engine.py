"""
Tests for the multi-agent workflow engine.

Covers:
  - file_bridge: register, resolve, cleanup
  - router: detect_agents_needed keyword matching, describe_routing
  - workflow_context: set/get, elapsed_seconds, cleanup
  - step_runner: param resolution, unknown agent error, unknown tool error
  - master_orchestrator: plan_workflow JSON parsing, run_workflow success/failure
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── file_bridge ───────────────────────────────────────────────────────────────

class TestFileBridge:
    def setup_method(self):
        # Reset registry between tests
        import src.agent.workflows.file_bridge as fb
        fb._registry.clear()

    def test_register_and_resolve(self, tmp_path):
        from src.agent.workflows import file_bridge as fb
        f = tmp_path / "report.pdf"
        f.write_bytes(b"data")
        fb.register("myfile", f)
        assert fb.resolve("myfile") == f

    def test_resolve_unknown_handle_returns_none(self):
        from src.agent.workflows import file_bridge as fb
        result = fb.resolve("nonexistent_handle_xyz")
        assert result is None

    def test_resolve_missing_file_returns_none(self, tmp_path):
        from src.agent.workflows import file_bridge as fb
        f = tmp_path / "gone.txt"
        f.write_bytes(b"x")
        fb.register("gone", f)
        f.unlink()
        assert fb.resolve("gone") is None

    def test_cleanup_handle_removes_file(self, tmp_path):
        from src.agent.workflows import file_bridge as fb
        f = tmp_path / "temp.txt"
        f.write_bytes(b"hello")
        fb.register("tok", f)
        fb.cleanup_handle("tok")
        assert not f.exists()
        assert fb.resolve("tok") is None

    def test_cleanup_all_clears_registry(self, tmp_path):
        from src.agent.workflows import file_bridge as fb
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_bytes(b"x")
            fb.register(f"key{i}", f)
        fb.cleanup_all()
        assert fb._registry == {}

    def test_make_workflow_dir_creates_dir(self):
        from src.agent.workflows import file_bridge as fb
        d = fb.make_workflow_dir()
        assert d.exists()
        assert d.name.startswith("octamind_wf_")
        d.rmdir()  # cleanup

    def test_file_size_mb(self, tmp_path):
        from src.agent.workflows import file_bridge as fb
        f = tmp_path / "big.bin"
        f.write_bytes(b"0" * 1024 * 1024)  # 1 MB
        fb.register("big", f)
        size = fb.file_size_mb("big")
        assert size is not None
        assert abs(size - 1.0) < 0.01

    def test_file_size_mb_unknown_handle(self):
        from src.agent.workflows import file_bridge as fb
        assert fb.file_size_mb("no_such") is None


# ── router ────────────────────────────────────────────────────────────────────

class TestRouter:
    # Force keyword-only fallback (no real LLM calls) for deterministic tests.
    @pytest.fixture(autouse=True)
    def mock_router_llm(self):
        with patch(
            "src.agent.llm.llm_parser.get_llm_client",
            side_effect=RuntimeError("no llm in router tests"),
        ):
            yield

    def test_drive_and_email_returns_both(self):
        from src.agent.workflows.router import detect_agents_needed
        result = detect_agents_needed(
            "download the report and email it to alice")
        assert result == ["drive", "email"]

    def test_only_drive_keywords(self):
        from src.agent.workflows.router import detect_agents_needed
        # keyword fallback: "drive" is in _DRIVE_KEYWORDS → returns ["drive"]
        result = detect_agents_needed("list all files in my drive folder")
        assert result == ["drive"]

    def test_only_email_keywords(self):
        from src.agent.workflows.router import detect_agents_needed
        # keyword fallback: "inbox" is in _EMAIL_KEYWORDS → returns ["email"]
        result = detect_agents_needed("show my inbox messages")
        assert result == ["email"]

    def test_no_keywords(self):
        from src.agent.workflows.router import detect_agents_needed
        result = detect_agents_needed("what is the weather today")
        assert result is None

    def test_gmail_keyword(self):
        from src.agent.workflows.router import detect_agents_needed
        result = detect_agents_needed(
            "download the spreadsheet and send it via gmail")
        assert result == ["drive", "email"]

    def test_gdrive_keyword(self):
        from src.agent.workflows.router import detect_agents_needed
        result = detect_agents_needed("search gdrive and compose an email")
        assert result == ["drive", "email"]

    def test_describe_routing_both_agents(self):
        from src.agent.workflows.router import describe_routing
        info = describe_routing("download file and send email")
        # keyword fallback: "download" is in _DRIVE_KEYWORDS
        assert "download" in info["drive_keywords_matched"]
        assert "email" in info["email_keywords_matched"] or "send" in info["email_keywords_matched"]
        assert info["routing_decision"] == ["drive", "email"]

    def test_describe_routing_single_agent(self):
        from src.agent.workflows.router import describe_routing
        # keyword fallback: neither "list"/"my"/"files" is in drive/email keywords
        info = describe_routing("list my files")
        assert info["routing_decision"] == "single-agent"

    def test_case_insensitive(self):
        from src.agent.workflows.router import detect_agents_needed
        result = detect_agents_needed("DOWNLOAD FILE AND SEND EMAIL TO BOB")
        assert result == ["drive", "email"]


# ── WorkflowContext ───────────────────────────────────────────────────────────

class TestWorkflowContext:
    def test_set_and_get(self):
        from src.agent.workflows.workflow_context import WorkflowContext
        ctx = WorkflowContext()
        ctx.set("foo", 42)
        assert ctx.get("foo") == 42

    def test_get_default(self):
        from src.agent.workflows.workflow_context import WorkflowContext
        ctx = WorkflowContext()
        assert ctx.get("missing", "default_val") == "default_val"

    def test_elapsed_seconds_positive(self):
        from src.agent.workflows.workflow_context import WorkflowContext
        import time
        ctx = WorkflowContext()
        time.sleep(0.05)
        assert ctx.elapsed_seconds() >= 0.0

    def test_register_temp_file_and_cleanup(self, tmp_path):
        from src.agent.workflows.workflow_context import WorkflowContext
        f = tmp_path / "tmp.txt"
        f.write_bytes(b"x")
        ctx = WorkflowContext()
        ctx.register_temp_file(f)
        ctx.cleanup()
        assert not f.exists()

    def test_cleanup_removes_empty_parent_dir(self, tmp_path):
        from src.agent.workflows.workflow_context import WorkflowContext
        sub = tmp_path / "octamind_wf_testclean"
        sub.mkdir()
        f = sub / "file.txt"
        f.write_bytes(b"data")
        ctx = WorkflowContext()
        ctx.register_temp_file(f)
        ctx.cleanup()
        assert not f.exists()


# ── WorkflowStep / WorkflowPlan ───────────────────────────────────────────────

class TestWorkflowDataclasses:
    def test_workflow_step_fields(self):
        from src.agent.workflows.workflow_context import WorkflowStep
        step = WorkflowStep(
            step_num=1,
            agent="drive",
            tool="search_files",
            params={"query": "budget"},
            output_key="found",
            description="Search for budget file",
        )
        assert step.step_num == 1
        assert step.agent == "drive"
        assert step.tool == "search_files"

    def test_workflow_plan_created_at(self):
        from src.agent.workflows.workflow_context import WorkflowPlan, WorkflowStep
        step = WorkflowStep(1, "email", "send_email", {}, "sent", "Send email")
        plan = WorkflowPlan(
            command="test",
            agents_needed=["email"],
            steps=[step],
        )
        assert isinstance(plan.created_at, datetime)
        assert len(plan.steps) == 1


# ── step_runner param resolution ──────────────────────────────────────────────

class TestStepRunnerParamResolution:
    def test_resolves_context_reference(self):
        from src.agent.workflows.workflow_context import WorkflowContext
        from src.agent.workflows.step_runner import _resolve_params
        ctx = WorkflowContext()
        ctx.set("file_id", "abc123")
        params = {"id": "{file_id}", "other": "literal"}
        resolved = _resolve_params(params, ctx)
        assert resolved["id"] == "abc123"
        assert resolved["other"] == "literal"

    def test_unknown_reference_kept_as_literal(self):
        from src.agent.workflows.workflow_context import WorkflowContext
        from src.agent.workflows.step_runner import _resolve_params
        ctx = WorkflowContext()
        params = {"x": "{nonexistent_key}"}
        resolved = _resolve_params(params, ctx)
        assert resolved["x"] == "{nonexistent_key}"

    def test_non_string_params_pass_through(self):
        from src.agent.workflows.workflow_context import WorkflowContext
        from src.agent.workflows.step_runner import _resolve_params
        ctx = WorkflowContext()
        params = {"count": 5, "flag": True, "items": [1, 2, 3]}
        resolved = _resolve_params(params, ctx)
        assert resolved == params

    def test_bridge_reference_resolves_to_none_when_unregistered(self):
        from src.agent.workflows.workflow_context import WorkflowContext
        from src.agent.workflows.step_runner import _resolve_params
        ctx = WorkflowContext()
        params = {"local_path": "$bridge:myhandle"}
        resolved = _resolve_params(params, ctx)
        # No file registered → resolves to the literal prefix (unresolved)
        assert resolved["local_path"] == "$bridge:myhandle"


class TestStepRunnerErrors:
    def test_unknown_agent_returns_error(self):
        from src.agent.workflows.workflow_context import WorkflowContext, WorkflowStep
        from src.agent.workflows.step_runner import run_step
        ctx = WorkflowContext()
        step = WorkflowStep(1, "fax_machine", "send_fax",
                            {}, "result", "Send fax")
        result = run_step(step, ctx)
        assert result["status"] == "error"
        assert "fax_machine" in result["error"]

    def test_unknown_tool_returns_error(self):
        from src.agent.workflows.workflow_context import WorkflowContext, WorkflowStep
        from src.agent.workflows.step_runner import run_step, _get_drive_registry
        ctx = WorkflowContext()
        step = WorkflowStep(1, "drive", "nonexistent_tool_xyz",
                            {}, "result", "No such tool")
        result = run_step(step, ctx)
        assert result["status"] == "error"
        assert "nonexistent_tool_xyz" in result["error"]

    def test_successful_step_stores_output(self):
        from src.agent.workflows.workflow_context import WorkflowContext, WorkflowStep
        from src.agent.workflows.step_runner import run_step, _get_drive_registry, _DRIVE_REGISTRY
        import src.agent.workflows.step_runner as sr

        ctx = WorkflowContext()
        step = WorkflowStep(1, "drive", "get_storage_quota",
                            {}, "quota_result", "Check quota")

        mock_tool = MagicMock(return_value={"used": 5, "total": 15})
        original = sr._DRIVE_REGISTRY
        sr._DRIVE_REGISTRY = {"get_storage_quota": mock_tool}
        try:
            result = run_step(step, ctx)
        finally:
            sr._DRIVE_REGISTRY = original

        assert result["status"] == "success"
        assert ctx.get("quota_result") == {"used": 5, "total": 15}


# ── master_orchestrator plan_nl_workflow ──────────────────────────────────────

class TestMasterOrchestratorPlan:
    def _fake_completion(self, content: str):
        choice = MagicMock()
        choice.message.content = content
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def _mock_llm(self):
        mock_client = MagicMock()
        mock_llm = MagicMock()
        mock_llm.client = mock_client
        mock_llm.model = "test-model"
        return mock_llm, mock_client

    def test_plan_workflow_success(self):
        from src.agent.workflows.master_orchestrator import plan_nl_workflow

        # NLWorkflowStep uses "instruction", not "tool"/"params"
        steps_json = json.dumps([
            {
                "step_num": 1,
                "agent": "drive",
                "instruction": "Search for the report file in Drive",
                "output_key": "file_result",
                "description": "Find the report",
            },
            {
                "step_num": 2,
                "agent": "email",
                "instruction": "Email the report to alice@example.com",
                "output_key": "email_result",
                "description": "Email the report",
            },
        ])
        mock_llm, mock_client = self._mock_llm()
        mock_client.chat.completions.create.return_value = self._fake_completion(
            steps_json)

        with patch("src.agent.workflows.master_orchestrator.get_llm_client", return_value=mock_llm):
            plan = plan_nl_workflow("find report and email to alice")

        assert plan is not None
        assert len(plan.steps) == 2
        assert plan.steps[0].agent == "drive"
        assert plan.steps[1].agent == "email"
        assert set(plan.agents_needed) == {"drive", "email"}

    def test_plan_workflow_strips_code_fences(self):
        from src.agent.workflows.master_orchestrator import plan_nl_workflow

        steps_json = "```json\n" + json.dumps([
            {"step_num": 1, "agent": "drive",
             "instruction": "Get the storage quota",
             "output_key": "quota", "description": "Check quota"}
        ]) + "\n```"
        mock_llm, mock_client = self._mock_llm()
        mock_client.chat.completions.create.return_value = self._fake_completion(
            steps_json)

        with patch("src.agent.workflows.master_orchestrator.get_llm_client", return_value=mock_llm):
            plan = plan_nl_workflow("check drive storage")

        assert plan is not None
        assert plan.steps[0].agent == "drive"
        assert "quota" in plan.steps[0].instruction.lower() or "storage" in plan.steps[0].instruction.lower()

    def test_plan_workflow_returns_none_on_invalid_json(self):
        from src.agent.workflows.master_orchestrator import plan_nl_workflow

        mock_llm, mock_client = self._mock_llm()
        mock_client.chat.completions.create.return_value = self._fake_completion(
            "not json at all")

        with patch("src.agent.workflows.master_orchestrator.get_llm_client", return_value=mock_llm):
            plan = plan_nl_workflow("some command")

        assert plan is None

    def test_plan_workflow_returns_none_on_llm_exception(self):
        from src.agent.workflows.master_orchestrator import plan_nl_workflow

        mock_llm, mock_client = self._mock_llm()
        mock_client.chat.completions.create.side_effect = RuntimeError(
            "timeout")

        with patch("src.agent.workflows.master_orchestrator.get_llm_client", return_value=mock_llm):
            plan = plan_nl_workflow("anything")

        assert plan is None


# ── master_orchestrator run_workflow ──────────────────────────────────────────

class TestRunWorkflow:
    """run_workflow now delegates to react_workflow internally (ReAct loop)."""

    def test_run_workflow_all_errors_returns_error(self):
        """When react_workflow returns only error steps status is 'error'."""
        from src.agent.workflows.master_orchestrator import run_workflow

        error_step = {
            "status": "error", "step": 1, "agent": "drive",
            "description": "find file", "error": "Drive unreachable",
        }
        with patch("src.agent.workflows.master_orchestrator.react_workflow",
                   return_value=([error_step], None)), \
             patch("src.agent.workflows.master_orchestrator._file_bridge") as mock_fb:
            mock_fb.cleanup_all = MagicMock()
            result = run_workflow("some command")

        assert result["status"] == "error"
        assert result["plan"] is None

    def test_run_workflow_executes_steps(self):
        """When react_workflow returns success steps the result is 'success'."""
        from src.agent.workflows.master_orchestrator import run_workflow

        success_step = {
            "status": "success", "step": 1, "agent": "drive",
            "description": "get quota", "result": {"used": 5},
        }
        with patch("src.agent.workflows.master_orchestrator.react_workflow",
                   return_value=([success_step], "\u2705 Done")), \
             patch("src.agent.workflows.master_orchestrator._file_bridge") as mock_fb:
            mock_fb.cleanup_all = MagicMock()
            result = run_workflow("check storage")

        assert result["status"] == "success"
        assert len(result["steps"]) == 1
        assert result["elapsed"] >= 0
        assert result["plan"] is None
        assert result["final_answer"] == "\u2705 Done"

    def test_run_workflow_stops_on_step_failure(self):
        """When react_workflow returns an error step, overall status is 'error'."""
        from src.agent.workflows.master_orchestrator import run_workflow

        fail_step = {
            "status": "error", "step": 1, "agent": "drive",
            "description": "search", "error": "Drive offline",
        }
        with patch("src.agent.workflows.master_orchestrator.react_workflow",
                   return_value=([fail_step], None)), \
             patch("src.agent.workflows.master_orchestrator._file_bridge") as mock_fb:
            mock_fb.cleanup_all = MagicMock()
            result = run_workflow("cmd")

        assert result["status"] == "error"
