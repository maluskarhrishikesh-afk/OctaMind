from __future__ import annotations

import importlib


def test_document_parser_is_registered() -> None:
    registry = importlib.import_module("src.agent.workflows.agent_registry")

    assert "document_parser" in registry.AGENT_REGISTRY
    entry = registry.AGENT_REGISTRY["document_parser"]
    assert entry["module"] == "src.agent.ui.document_parser_agent.orchestrator"


def test_document_parser_agent_type_exists() -> None:
    agent_manager = importlib.import_module("src.agent.core.agent_manager")

    assert "document_parser" in agent_manager.AgentManager.AGENT_TYPES


def test_document_parser_skill_help_doc_loads() -> None:
    skill_help = importlib.import_module("src.agent.hub.skill_help")

    doc = skill_help.get_skill_help_doc("document_parser")

    assert doc is not None
    assert doc.title == "Document Parser"


def test_document_parser_orchestrator_builds_tool_map() -> None:
    orchestrator = importlib.import_module("src.agent.ui.document_parser_agent.orchestrator")
    build_all_tools = getattr(orchestrator, "_build_all_tools")

    tool_map = build_all_tools()

    assert "parse_document_spatially" in tool_map
    assert "extract_document_key_fields" in tool_map
    assert "batch_parse_documents" in tool_map
    assert "screenshot_document_pages" in tool_map