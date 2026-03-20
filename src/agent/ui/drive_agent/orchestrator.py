"""
Google Drive skill orchestrator.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from src.agent.telemetry import log_fallback_to_react
from src.agent.workflows.execution_plan import attach_execution_plan, build_execution_plan, build_execution_step
from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag


logger = logging.getLogger("drive.orchestrator")


def _build_drive_execution_plan(user_query: str, engine: str, result: Dict[str, Any]) -> Dict[str, Any]:
    lowered = str(user_query or "").lower()
    destructive = bool(re.search(r"\b(delete|trash|remove|revoke|cleanup)\b", lowered))
    confidence = 0.86 if engine == "dag" else 0.78
    if destructive:
        confidence -= 0.08
    if str(result.get("status", "") or "") != "success":
        confidence = min(confidence, 0.45)

    step = build_execution_step(
        step_id="drive_execution",
        description="Execute the requested Google Drive operation.",
        confidence=confidence,
        why=[
            "The request was routed to the Drive skill based on Google Drive intent.",
            (
                "The request ran through the DAG planner before tool execution."
                if engine == "dag"
                else "The request ran through the ReAct fallback path because DAG planning was unavailable or skipped."
            ),
        ],
        safe_to_apply=not destructive,
        metadata={
            "engine": engine,
            "query": user_query,
            "action": str(result.get("action", "") or "react_response"),
        },
    )
    return build_execution_plan(
        goal="Fulfill the requested Google Drive task safely and transparently.",
        steps=[step],
        requires_confirmation=destructive,
    )


def _attach_drive_execution_plan(user_query: str, engine: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    return attach_execution_plan(
        result,
        _build_drive_execution_plan(user_query, engine, result),
        include_summary=str(result.get("status", "") or "") == "success",
        heading="Execution plan",
        include_step_reasons=True,
    )



def _load_skill_context() -> str:
    """Load the drive skill context from skill_context.md (next to this file)."""
    from pathlib import Path as _Path
    return (_Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()


def _build_all_tools() -> Dict[str, Any]:
    from src.drive import drive_service as ds  # noqa: PLC0415
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_drive_context, make_save_context_tool,
    )

    def list_files(query: str = "", max_results: int = 20, folder_id=None) -> list:
        result = ds.list_files(
            max_results=int(max_results) if max_results else 20,
            query=query or "",
            folder_id=folder_id or "root",
        )
        return auto_save_drive_context(result, query or "")

    def search_files(name: str = "", file_type: str = "", max_results: int = 10) -> list:
        q = " and ".join(filter(None, [
            (f"name contains '{name}'" if name else ""),
            (f"mimeType='{file_type}'" if file_type else ""),
        ])) or ""
        result = ds.search_files(
            query=q,
            max_results=int(max_results) if str(max_results).isdigit() else 10,
        )
        return auto_save_drive_context(result, name or file_type or "")

    return {
        # Browse & Search
        "list_files":          list_files,
        "search_files":        search_files,
        "get_file_info":       lambda file_id: ds.get_file_info(file_id),
        "list_shared_with_me": lambda max_results=20: ds.list_shared_with_me(max_results),
        # Upload & Download
        "upload_file":                lambda local_path, name="", folder_id=None, mime_type=None: ds.upload_file(local_path, name, folder_id, mime_type),
        "download_file":              lambda file_id, local_path: ds.download_file(file_id, local_path),
        "backup_drive_to_local":      lambda folder_id, output_dir, max_files=100: ds.backup_drive_to_local(folder_id, output_dir, max_files),
        "sync_local_folder_to_drive": lambda local_path, drive_folder_id, dry_run=True: ds.sync_local_folder_to_drive(local_path, drive_folder_id, dry_run),
        # File Operations
        "create_folder": lambda name, parent_id=None: ds.create_folder(name, parent_id),
        "move_file":     lambda file_id, folder_id: ds.move_file(file_id, folder_id),
        "copy_file":     lambda file_id, name="", folder_id=None: ds.copy_file(file_id, name, folder_id),
        "trash_file":    lambda file_id: ds.trash_file(file_id),
        "restore_file":  lambda file_id: ds.restore_file(file_id),
        "star_file":     lambda file_id, starred=True: ds.star_file(file_id, starred),
        # Batch Operations
        "batch_move_files":  lambda file_ids, folder_id: ds.batch_move_files(file_ids, folder_id),
        "batch_delete_files":lambda file_ids, permanent=False: ds.batch_delete_files(file_ids, permanent),
        "batch_copy_files":  lambda file_ids, folder_id="", name_suffix=" (copy)": ds.batch_copy_files(file_ids, folder_id, name_suffix),
        # Sharing & Permissions
        "share_file":              lambda file_id, email="", role="reader", make_public=False: ds.share_file(file_id, email, role, make_public),
        "manage_file_permissions": lambda file_id, action, permission_id="", new_role="reader": ds.manage_file_permissions(file_id, action, permission_id, new_role=new_role),
        "revoke_access_all":       lambda file_id: ds.revoke_access_all(file_id),
        "get_sharing_stats":       lambda file_id: ds.get_sharing_stats(file_id),
        # Storage & Cleanup
        "get_storage_quota":    lambda: ds.get_storage_quota(),
        "find_large_files":     lambda folder_id="root", min_size_mb=10.0, max_results=25: ds.find_large_files(folder_id, min_size_mb, max_results),
        "find_drive_duplicates":  lambda folder_id="root", max_results=200: ds.find_drive_duplicates(folder_id, max_results),
        "trash_drive_duplicates": lambda folder_id="root", keep="newest": ds.trash_drive_duplicates(folder_id, keep),
        "suggest_archival":       lambda folder_id="root", months_old=6, max_results=25: ds.suggest_archival(folder_id, months_old, max_results),
        # Conversion & Versioning
        "convert_document":     lambda file_id, output_format="pdf", save_path="": ds.convert_document(file_id, output_format, save_path),
        "list_file_versions":   lambda file_id: ds.list_file_versions(file_id),
        "cleanup_old_versions": lambda file_id, keep_latest=3: ds.cleanup_old_versions(file_id, keep_latest),
        # Context Manifest
        "save_context": make_save_context_tool("drive"),
    }


def _get_tool_docs_for_dag() -> str:
    """Return full tool docs for the DAG planner (needs all tools to plan)."""
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    return get_all_tool_docs("drive")


def _get_tool_docs_for_react(user_query: str) -> str:
    """Return filtered tool docs for the ReAct engine (cosine-similarity top-K)."""
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    return load_tool_docs(
        "drive", user_query,
        always_include=["save_context"],
    )


def _get_tool_map_for_react(
    user_query: str,
    all_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a FAISS-filtered tool map for the ReAct engine.

    Falls back to the full tool map if FAISS selection fails.
    """
    if all_tools is None:
        all_tools = _build_all_tools()
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415
        selected = select_tool_names(
            "drive", user_query,
            always_include=["save_context"],
        )
        filtered = {n: all_tools[n] for n in selected if n in all_tools}
        if filtered:
            return filtered
    except Exception as exc:
        import logging as _lg
        _lg.getLogger("drive.orchestrator").warning(
            "[tool-map] FAISS filtering failed (%s) — using full tool map", exc
        )
    return all_tools


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Skill entry-point called by master_orchestrator / PA chat.

    Primary path: DAG planner (2 LLM calls regardless of task length).
    Fallback:      ReAct loop (1 LLM call per step, up to 6 iterations).
    """
    all_tools = _build_all_tools()
    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        return _attach_drive_execution_plan(user_query, "dag", run_skill_dag(
            skill_name="drive",
            skill_context=skill_context,
            tool_map=all_tools,
            tool_docs=dag_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(user_query, all_tools),
            react_tool_docs=react_tool_docs,
        ))
    except Exception as dag_exc:
        logger.warning("DAG path raised %s — falling back to ReAct", dag_exc)
        log_fallback_to_react("drive", "drive_orchestrator_exception")
    try:
        return _attach_drive_execution_plan(user_query, "react", run_skill_react(
            skill_name="drive",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        ))
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Drive skill error: {exc}",
            "action": "react_response",
        }
