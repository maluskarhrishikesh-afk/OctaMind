"""
File Organizer skill orchestrator.

Specialises in batch organisation, deduplication, and smart sorting of local files
using the files feature modules.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
list_directory(path, show_hidden=False, limit=200) – Survey the contents of a folder.
get_file_info(path) – Get size, dates, type for a file or folder.
move_file(source, destination) – Move a file to an organised folder.
copy_file(source, destination) – Copy a file.
delete_file(path, permanent=False) – Delete a file (recycle bin by default).
create_folder(path) – Create an organisational folder.
rename_file(path, new_name) – Rename a file.
search_by_extension(directory, extension, recursive=True, limit=50) – Find all files of a given type.
search_by_size(directory, min_bytes=None, max_bytes=None, recursive=True, limit=50) – Find files by size.
search_by_date(directory, date_from=None, date_to=None, recursive=True, limit=50) – Find files by date.
find_duplicates(directory, recursive=True) – Locate duplicate files so the user can clean them up.
find_empty_folders(directory, recursive=True) – Find empty directories to delete.
""".strip()

_SKILL_CONTEXT = """
You are the File Organizer Skill Agent.
Your job is to help the user tidy and organise their local file system:
- Sort files into named sub-folders by type, date, or project.
- Find and remove duplicates.
- Clean up empty folders.
- Rename files according to a consistent naming scheme.

Always tell the user what changes you plan to make BEFORE making them (include counts and paths).
Use permanent=False when deleting so files can be recovered from the Recycle Bin.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.files.features.file_ops import (  # noqa: PLC0415
        list_directory, get_file_info, move_file, copy_file,
        delete_file, create_folder, rename_file,
    )
    from src.files.features.search import (  # noqa: PLC0415
        search_by_extension, search_by_size, search_by_date,
        find_duplicates, find_empty_folders,
    )

    return {
        "list_directory": list_directory,
        "get_file_info": get_file_info,
        "move_file": move_file,
        "copy_file": copy_file,
        "delete_file": delete_file,
        "create_folder": create_folder,
        "rename_file": rename_file,
        "search_by_extension": search_by_extension,
        "search_by_size": search_by_size,
        "search_by_date": search_by_date,
        "find_duplicates": find_duplicates,
        "find_empty_folders": find_empty_folders,
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="file_organizer",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ File Organizer skill error: {exc}",
            "action": "react_response",
        }
