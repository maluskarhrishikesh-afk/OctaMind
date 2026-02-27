"""
Google Drive skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
list_files(query="", max_results=20, folder_id=None) – List files in Drive (optional folder filter).
search_files(name="", file_type="", max_results=10) – Search files by name and/or type (e.g. "spreadsheet").
get_file_info(file_id) – Return metadata for a specific file.
upload_file(local_path, name="", folder_id=None, mime_type=None) – Upload a local file to Drive.
download_file(file_id, local_path) – Download a Drive file to a local path.
create_folder(name, parent_id=None) – Create a new folder.
move_file(file_id, folder_id) – Move a file to a different folder.
copy_file(file_id, name="", folder_id=None) – Copy a file.
trash_file(file_id) – Move a file to Trash.
restore_file(file_id) – Restore a file from Trash.
star_file(file_id, starred=True) – Star or un-star a file.
get_storage_quota() – Return used/total Drive storage quota.
""".strip()

_SKILL_CONTEXT = """
You are the Google Drive Skill Agent.
Help the user manage their Google Drive: list, search, upload, download, move, copy, delete and organise files.
When the user says "upload", ask for the local file path if not provided.
When the user says "download", ask for the file name or ID if not provided.
Always prefer search_files over list_files when looking for a specific file by name.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.drive import drive_service as ds  # noqa: PLC0415

    return {
        "list_files": lambda query="", max_results=20, folder_id=None: ds.list_files(
            max_results=int(max_results) if max_results else 20,
            query=query or "",
            folder_id=folder_id or "root",
        ),
        "search_files": lambda name="", file_type="", max_results=10: ds.search_files(
            query=" and ".join(filter(None, [
                (f"name contains '{name}'" if name else ""),
                (f"mimeType='{file_type}'" if file_type else ""),
            ])) or "",
            max_results=int(max_results) if str(max_results).isdigit() else 10,
        ),
        "get_file_info": lambda file_id: ds.get_file_info(file_id),
        "upload_file": lambda local_path, name="", folder_id=None, mime_type=None: ds.upload_file(local_path, name, folder_id, mime_type),
        "download_file": lambda file_id, local_path: ds.download_file(file_id, local_path),
        "create_folder": lambda name, parent_id=None: ds.create_folder(name, parent_id),
        "move_file": lambda file_id, folder_id: ds.move_file(file_id, folder_id),
        "copy_file": lambda file_id, name="", folder_id=None: ds.copy_file(file_id, name, folder_id),
        "trash_file": lambda file_id: ds.trash_file(file_id),
        "restore_file": lambda file_id: ds.restore_file(file_id),
        "star_file": lambda file_id, starred=True: ds.star_file(file_id, starred),
        "get_storage_quota": lambda: ds.get_storage_quota(),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="drive",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Drive skill error: {exc}",
            "action": "react_response",
        }
