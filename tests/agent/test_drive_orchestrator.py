from __future__ import annotations

import importlib


def test_drive_orchestrator_attaches_execution_plan_on_dag_success(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.drive_agent.orchestrator")

    monkeypatch.setattr(orchestrator, "_build_all_tools", lambda: {})
    monkeypatch.setattr(orchestrator, "_load_skill_context", lambda: "drive skill")
    monkeypatch.setattr(orchestrator, "_get_tool_docs_for_dag", lambda: "dag docs")
    monkeypatch.setattr(orchestrator, "_get_tool_docs_for_react", lambda query: "react docs")
    monkeypatch.setattr(orchestrator, "_get_tool_map_for_react", lambda query, all_tools=None: {})
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda **kwargs: {"status": "success", "message": "Listed Drive files.", "action": "react_response"},
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("ReAct should not run when DAG succeeds")),
    )

    result = orchestrator.execute_with_llm_orchestration("List my drive files")

    assert result["status"] == "success"
    assert result["execution_plan"]["confidence_label"] == "medium"
    assert result["execution_plan"]["steps"][0]["engine"] == "dag"
    assert "Execution plan:" in result["message"]


def test_drive_orchestrator_attaches_execution_plan_on_react_fallback(monkeypatch) -> None:
    orchestrator = importlib.import_module("src.agent.ui.drive_agent.orchestrator")

    monkeypatch.setattr(orchestrator, "_build_all_tools", lambda: {})
    monkeypatch.setattr(orchestrator, "_load_skill_context", lambda: "drive skill")
    monkeypatch.setattr(orchestrator, "_get_tool_docs_for_dag", lambda: "dag docs")
    monkeypatch.setattr(orchestrator, "_get_tool_docs_for_react", lambda query: "react docs")
    monkeypatch.setattr(orchestrator, "_get_tool_map_for_react", lambda query, all_tools=None: {})
    monkeypatch.setattr(
        orchestrator,
        "run_skill_dag",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("planner unavailable")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_skill_react",
        lambda **kwargs: {"status": "success", "message": "Removed Drive access.", "action": "react_response"},
    )

    result = orchestrator.execute_with_llm_orchestration("Revoke access to that Drive file")

    assert result["status"] == "success"
    assert result["execution_plan"]["requires_confirmation"] is True
    assert result["execution_plan"]["steps"][0]["engine"] == "react"
    assert result["execution_plan"]["risk_level"] == "medium"