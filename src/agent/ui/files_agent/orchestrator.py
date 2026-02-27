"""
Local Files skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
list_directory(path, show_hidden=False, limit=200) – List files in a local directory.
get_file_info(path) – Get metadata for a local file or folder.
copy_file(source, destination) – Copy a file or folder.
move_file(source, destination) – Move / rename a file or folder.
delete_file(path, permanent=False) – Delete a file (recycle bin by default).
create_folder(path) – Create a new directory.
rename_file(path, new_name) – Rename a file or folder.
open_file(path) – Open a file with its default application.
search_by_name(directory, pattern, recursive=True, limit=50) – Search for files by name pattern.
search_by_extension(directory, extension, recursive=True, limit=50) – Search by file extension.
search_by_date(directory, date_from=None, date_to=None, recursive=True, limit=50) – Search by modification date.
search_by_size(directory, min_bytes=None, max_bytes=None, recursive=True, limit=50) – Search by file size.
find_duplicates(directory, recursive=True) – Find duplicate files.
find_empty_folders(directory, recursive=True) – Find empty folders.
zip_folder(folder_path, output_path="") – Zip an entire folder into a .zip archive. output_path defaults to same location as folder with .zip extension.
zip_files(sources, output_path) – Zip one or more files and/or folders into a single archive. sources is a list of paths.
unzip_file(archive_path, destination="") – Extract a zip archive. destination defaults to a folder named after the archive.
list_archive_contents(archive_path) – List contents of a zip archive without extracting.
""".strip()

_SKILL_CONTEXT = """
You are the Local Files Skill Agent.
You can browse, search, copy, move, delete, rename and organise files on the user's local filesystem.
Always use absolute paths when calling tools; expand relative paths if given.
Be careful with delete_file — prefer permanent=False (recycle bin) unless the user asks for permanent deletion.
For zip/compression requests ALWAYS use zip_folder (for a whole folder) or zip_files (for specific files). Never suggest manual steps — you have the tools to do it directly.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.files.features.file_ops import (  # noqa: PLC0415
        list_directory, get_file_info, copy_file, move_file,
        delete_file, create_folder, rename_file, open_file,
    )
    from src.files.features.search import (  # noqa: PLC0415
        search_by_name, search_by_extension, search_by_date,
        search_by_size, find_duplicates, find_empty_folders,
    )
    from src.files.features.archives import (  # noqa: PLC0415
        zip_folder, zip_files, unzip_file, list_archive_contents,
    )

    return {
        "list_directory": list_directory,
        "get_file_info": get_file_info,
        "copy_file": copy_file,
        "move_file": move_file,
        "delete_file": delete_file,
        "create_folder": create_folder,
        "rename_file": rename_file,
        "open_file": open_file,
        "search_by_name": search_by_name,
        "search_by_extension": search_by_extension,
        "search_by_date": search_by_date,
        "search_by_size": search_by_size,
        "find_duplicates": find_duplicates,
        "find_empty_folders": find_empty_folders,
        "zip_folder": zip_folder,
        "zip_files": zip_files,
        "unzip_file": unzip_file,
        "list_archive_contents": list_archive_contents,
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="files",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Files skill error: {exc}",
            "action": "react_response",
        }
