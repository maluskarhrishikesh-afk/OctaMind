"""Document Parser skill orchestrator."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.agent.telemetry import log_fallback_to_react
from src.agent.workflows.skill_dag_engine import run_skill_dag
from src.agent.workflows.skill_react_engine import run_skill_react

logger = logging.getLogger("document_parser.orchestrator")

_DOCUMENT_PARSER_ORCHESTRATION_ERRORS = (
    ImportError,
    LookupError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _load_skill_context() -> str:
    return (Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()


def _build_all_tools() -> Dict[str, Any]:
    from src.files.features.document_parser import (  # noqa: PLC0415
        batch_parse_documents,
        check_liteparse_installation,
        parse_document_spatially,
        screenshot_document_pages,
    )
    from src.files.features.file_ops import deliver_file, get_file_info, list_directory  # noqa: PLC0415
    from src.files.features.reader import read_json_file, read_text_file  # noqa: PLC0415
    from src.files.features.search import search_by_extension, search_by_name  # noqa: PLC0415

    return {
        "check_liteparse_installation": check_liteparse_installation,
        "list_directory": list_directory,
        "get_file_info": get_file_info,
        "search_by_name": search_by_name,
        "search_by_extension": search_by_extension,
        "parse_document_spatially": parse_document_spatially,
        "batch_parse_documents": batch_parse_documents,
        "screenshot_document_pages": screenshot_document_pages,
        "read_text_file": read_text_file,
        "read_json_file": read_json_file,
        "deliver_file": deliver_file,
    }


def _get_tool_docs_for_dag() -> str:
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415

    docs = get_all_tool_docs("document_parser")
    if not docs:
        logger.error(
            "[document-parser-agent] skills.md returned no tools — check ui/document_parser_agent/skills.md exists. "
            "DAG planning will fail without tool docs."
        )
    return docs


def _get_tool_docs_for_react(user_query: str) -> str:
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415

    docs = load_tool_docs(
        "document_parser",
        user_query,
        always_include=[
            "check_liteparse_installation",
            "parse_document_spatially",
            "screenshot_document_pages",
        ],
    )
    if not docs:
        logger.error(
            "[document-parser-agent] skills.md returned no filtered docs for query=%r — check ui/document_parser_agent/skills.md",
            user_query[:60],
        )
    return docs


def _get_tool_map_for_react(user_query: str, all_tools: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if all_tools is None:
        all_tools = _build_all_tools()
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415

        selected = select_tool_names(
            "document_parser",
            user_query,
            always_include=[
                "check_liteparse_installation",
                "parse_document_spatially",
                "screenshot_document_pages",
            ],
        )
        filtered = {name: all_tools[name] for name in selected if name in all_tools}
        if filtered:
            return filtered
    except _DOCUMENT_PARSER_ORCHESTRATION_ERRORS as exc:
        logger.warning("[tool-map] FAISS filtering failed (%s) — using full tool map", exc)
    return all_tools


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    del agent_id
    all_tools = _build_all_tools()
    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)

    try:
        return run_skill_dag(
            skill_name="document_parser",
            skill_context=skill_context,
            tool_map=all_tools,
            tool_docs=dag_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(user_query, all_tools),
            react_tool_docs=react_tool_docs,
        )
    except _DOCUMENT_PARSER_ORCHESTRATION_ERRORS as dag_exc:
        logger.warning("DAG path raised %s — falling back to ReAct", dag_exc)
        log_fallback_to_react("document_parser", "document_parser_orchestrator_exception")

    try:
        return run_skill_react(
            skill_name="document_parser",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except _DOCUMENT_PARSER_ORCHESTRATION_ERRORS as exc:
        return {
            "status": "error",
            "message": f"❌ Document Parser skill error: {exc}",
            "action": "react_response",
        }