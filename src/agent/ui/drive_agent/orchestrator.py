"""
LLM-orchestrated Google Drive command executor.

execute_with_llm_orchestration() lets the LLM pick the right Drive tool
and runs it, applying the max_operations safety cap on bulk-fetch parameters.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from src.agent.llm.llm_parser import get_llm_client
from src.drive import (
    # Phase 1
    list_files, search_files, get_file_info, upload_file, download_file,
    create_folder, move_file, copy_file, trash_file, restore_file,
    star_file, get_storage_quota,
    # Phase 2
    share_file, list_permissions, remove_permission, update_permission,
    make_public, remove_public,
    # Phase 3
    summarize_file, summarize_folder,
    find_duplicates, trash_duplicates,
    suggest_organization, auto_organize, bulk_rename,
    list_versions, get_version_info, restore_version, delete_old_versions,
    # Phase 4
    storage_breakdown, list_large_files, list_old_files, list_recently_modified,
    find_orphaned_files, sharing_report,
    generate_drive_report, get_usage_insights,
)

logger = logging.getLogger("drive_agent")

try:
    from src.agent.memory.agent_memory import get_agent_memory
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False

# ── Drive tool descriptions for LLM orchestration ────────────────────────────
# This is passed to orchestrate_mcp_tool() so the LLM picks from Drive tools
# rather than the default Gmail tools.
_DRIVE_TOOLS_DESCRIPTION = """
1. **list_files**(max_results: int = 20, query: str = '', folder_id: str = 'root')
   - List files in Google Drive. Use for: "show my files", "list files", "what files do I have"
   - Pass folder_id='trash' to list trashed files ("show files in trash", "what's in the bin")

2. **search_files**(query: str, max_results: int = 20)
   - Search files by name or content. Pass the plain file name or search term directly
     (e.g. query="budget report" or query="fashionable.xlsx"). Do NOT format as a Drive
     query expression — the system handles that automatically.
   - Use for: "find files named X", "search for budget", "find PDFs"

3. **get_file_info**(file_id: str)
   - Get metadata for a specific file. Use for: "info about file ID X", "details of X"

4. **upload_file**(local_path: str, name: str = None, folder_id: str = None)
   - Upload a local file to Drive. Use for: "upload file", "add file to Drive"

5. **download_file**(file_id: str, destination: str = None)
   - Download a Drive file locally. Use for: "download file X", "save file to disk"
   - If you only have the file name (not the Drive ID), pass the name as file_id —
     the system will search for it automatically.

6. **create_folder**(name: str, parent_id: str = None)
   - Create a new folder. Use for: "create folder", "make new folder named X"

7. **move_file**(file_id: str, destination_folder_id: str)
   - Move a file to another folder. Use for: "move file X to folder Y"

8. **copy_file**(file_id: str, name: str = None, folder_id: str = None)
   - Copy a file. Use for: "copy file X", "duplicate file"

9. **trash_file**(file_id: str)
   - Send a file to trash. Use for: "delete file X", "trash file", "remove file"

10. **restore_file**(file_id: str)
    - Restore a trashed file. Use for: "restore file X", "undelete file", "recover file"

11. **star_file**(file_id: str, starred: bool = True)
    - Star or unstar a file. Use for: "star file X", "unstar file X", "mark as important"

12. **get_storage_quota**()
    - Get Drive storage usage. Use for: "how much storage", "storage quota", "how full is my Drive"

13. **share_file**(file_id: str, email: str, role: str = 'reader', send_notification: bool = True, message: str = None)
    - Share file with someone. Use for: "share file X with email Y", "give access to file"
    - role: 'reader', 'commenter', 'writer'

14. **list_permissions**(file_id: str)
    - List who has access to a file. Use for: "who can see file X", "show permissions", "list sharing"

15. **remove_permission**(file_id: str, permission_id: str)
    - Remove someone's access. Use for: "revoke access to file X for permission Y"

16. **update_permission**(file_id: str, permission_id: str, role: str)
    - Change someone's access level. Use for: "change role for permission Y on file X"

17. **make_public**(file_id: str)
    - Make file publicly accessible (anyone with link). Use for: "make file X public", "share publicly"

18. **remove_public**(file_id: str)
    - Remove public access. Use for: "make file X private", "remove public access"

19. **summarize_file**(file_id: str)
    - AI summary of file content. Use for: "summarize file X", "what does file X say", "TL;DR of X"

20. **summarize_folder**(folder_id: str = 'root')
    - Overview of folder contents. Use for: "what's in folder X", "summarize folder"

21. **find_duplicates**(folder_id: str = 'root', max_files: int = 500)
    - Find duplicate files. Use for: "find duplicates", "duplicate files", "same files twice"

22. **trash_duplicates**(folder_id: str = 'root', max_files: int = 500, dry_run: bool = True)
    - Delete duplicate files. Use for: "remove duplicates", "clean up duplicates"

23. **suggest_organization**(folder_id: str = 'root', max_files: int = 100)
    - Suggest how to organise files. Use for: "how to organise my Drive", "suggest folders"

24. **auto_organize**(folder_id: str = 'root', max_files: int = 100, dry_run: bool = True)
    - Automatically move files into organised folders. Use for: "organise my files", "auto-sort Drive"

25. **bulk_rename**(folder_id: str, pattern: str, replacement: str, max_files: int = 100, dry_run: bool = True)
    - Rename files matching a pattern. Use for: "rename all files with X to Y"

26. **list_versions**(file_id: str)
    - List revision history. Use for: "version history of file X", "revisions of X"

27. **restore_version**(file_id: str, revision_id: str)
    - Restore a previous version. Use for: "restore previous version of X"

28. **delete_old_versions**(file_id: str, keep_latest: int = 5, dry_run: bool = True)
    - Delete old revisions. Use for: "clean up old versions of X"

29. **storage_breakdown**()
    - Break down storage usage by file type. Use for: "storage breakdown", "what's taking up space"

30. **list_large_files**(min_size_mb: float = 50, max_results: int = 50)
    - List files above a size threshold. Use for: "large files", "big files", "files over 50MB"

31. **list_old_files**(days: int = 365, max_results: int = 50)
    - List files not modified in N days. Use for: "stale files", "old files", "files not modified in a year"

32. **list_recently_modified**(max_results: int = 20)
    - List recently modified files. Use for: "recent files", "recently modified", "what changed recently"

33. **find_orphaned_files**(max_results: int = 100)
    - Find files with no parent folder. Use for: "orphaned files", "files without folders"

34. **sharing_report**(max_files: int = 200)
    - Report on shared vs private files. Use for: "sharing report", "how many files are shared"

35. **generate_drive_report**()
    - Full Drive health report. Use for: "Drive report", "health report", "Drive summary"

36. **get_usage_insights**()
    - AI-generated insights about Drive usage. Use for: "insights", "tips to organise Drive", "Drive recommendations"
"""


def _observation_from_result(result: dict, tool_name: str) -> str:
    """Convert a Drive tool result into a readable observation string for the ReAct loop."""
    import json as _json

    if result.get("status") == "error":
        return f"Error: {result.get('message', 'Unknown error')}"

    # File list results — include IDs so the LLM can chain tool calls
    files = result.get("files") or result.get("results") or []
    if files and isinstance(files, list):
        lines = [f"Found {len(files)} file(s):"]
        for i, f in enumerate(files[:20], 1):
            size_str = ""
            if f.get("size"):
                try:
                    mb = int(f["size"]) / (1024 * 1024)
                    size_str = f" | {mb:.1f} MB"
                except (ValueError, TypeError):
                    pass
            lines.append(
                f"[{i}] ID: {f.get('id', '?')} | "
                f"Name: {f.get('name', '?')} | "
                f"Type: {f.get('mimeType', '?')}{size_str}"
            )
        return "\n".join(lines)

    # Storage quota
    if "used" in result and "limit" in result:
        used_gb = int(result.get("used", 0)) / (1024 ** 3)
        limit_gb = int(result.get("limit", 1)) / (1024 ** 3)
        return f"Storage: {used_gb:.2f} GB used of {limit_gb:.2f} GB"

    # Generic compact serialisation
    compact = {
        k: v for k, v in result.items()
        if k not in ("status",) and not isinstance(v, (list, dict))
    }
    list_summaries = {
        k: f"[{len(v)} items]"
        for k, v in result.items()
        if isinstance(v, list)
    }
    compact.update(list_summaries)
    return _json.dumps(compact, default=str)[:600]


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str = None,
    max_operations: int = 100,
    artifacts_out: dict = None,
) -> Dict[str, Any]:
    """
    Execute Drive commands using a Thought-Action-Observation (ReAct) loop.

    ``artifacts_out`` — optional dict that will be populated with any file
    paths produced by this call (e.g. from download_file).  Pass an empty
    dict when calling from a multi-agent workflow to receive the path.

    The LLM reasons freely across as many steps as needed:
      Thought -> Action (tool call) -> Observation (result) -> Thought -> ...
    until it produces a final_answer.  Supports multi-step tasks like:
      "Find duplicates in my project folder and delete them" — will:
        1. list files / find_duplicates  ->  observe duplicate IDs
        2. trash_duplicates              ->  observe success
        3. write final_answer

    Args:
        user_query:     Natural language task from the user.
        agent_id:       Agent ID for memory context.
        max_operations: Safety cap on bulk API operations per tool call.
    """
    try:
        # ── Memory context ──────────────────────────────────────────────────
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
            except Exception:
                pass

        # ── Tool executor used by the ReAct loop ────────────────────────────
        _ops_capped_note = ""

        def _clamp(value, fallback: int = 20) -> int:
            nonlocal _ops_capped_note
            try:
                v = int(value)
            except (TypeError, ValueError):
                v = fallback
            effective = min(v, max_operations)
            if effective < v:
                _ops_capped_note = (
                    f"\n\n⚠️ *Results capped at {effective} (max operations limit).*"
                )
            return effective

        def _dispatch(tool_name: str, params: dict) -> str:
            """Execute one Drive tool and return a readable observation string."""
            result: Dict[str, Any] = {
                "status": "error", "message": f"Unknown tool: {tool_name}",
            }

            # Phase 1 — Core file operations
            if tool_name == "list_files":
                files = list_files(
                    max_results=_clamp(params.get("max_results", 20)),
                    query=params.get("query", ""),
                    folder_id=params.get("folder_id", "root"),
                )
                result = {"status": "success", "files": files}

            elif tool_name == "search_files":
                files = search_files(
                    query=params.get("query", ""),
                    max_results=_clamp(params.get("max_results", 20)),
                )
                result = {"status": "success", "files": files}

            elif tool_name == "get_file_info":
                result = get_file_info(params.get("file_id", ""))

            elif tool_name == "upload_file":
                result = upload_file(
                    local_path=params.get("local_path", ""),
                    name=params.get("name"),
                    folder_id=params.get("folder_id"),
                )

            elif tool_name == "download_file":
                import re as _re
                raw_id = params.get("file_id", "")
                _looks_like_name = (
                    "." in raw_id or " " in raw_id or len(raw_id) < 20
                    or not _re.match(r'^[A-Za-z0-9_\-]{20,}$', raw_id)
                )
                if _looks_like_name and raw_id:
                    hits = search_files(query=raw_id, max_results=1)
                    if not hits:
                        return f"Error: Could not find a file named '{raw_id}' in Drive."
                    raw_id = hits[0]["id"]
                result = download_file(file_id=raw_id,
                                       destination=params.get("destination"))
                # Capture local_path for inter-agent handoff (Drive → Email)
                if artifacts_out is not None and isinstance(result, dict):
                    local = result.get("local_path")
                    if local:
                        artifacts_out["file_path"] = local

            elif tool_name == "create_folder":
                result = create_folder(
                    name=params.get("name", "New Folder"),
                    parent_id=params.get("parent_id"),
                )

            elif tool_name == "move_file":
                result = move_file(
                    file_id=params.get("file_id", ""),
                    destination_folder_id=params.get("destination_folder_id", ""),
                )

            elif tool_name == "copy_file":
                result = copy_file(
                    file_id=params.get("file_id", ""),
                    name=params.get("name"),
                    folder_id=params.get("folder_id"),
                )

            elif tool_name == "trash_file":
                result = trash_file(params.get("file_id", ""))

            elif tool_name == "restore_file":
                result = restore_file(params.get("file_id", ""))

            elif tool_name == "star_file":
                result = star_file(
                    params.get("file_id", ""),
                    starred=params.get("starred", True),
                )

            elif tool_name == "get_storage_quota":
                result = get_storage_quota()

            # Phase 2 — Sharing & Permissions
            elif tool_name == "share_file":
                result = share_file(
                    file_id=params.get("file_id", ""),
                    email=params.get("email", ""),
                    role=params.get("role", "reader"),
                    send_notification=params.get("send_notification", True),
                    message=params.get("message"),
                )

            elif tool_name == "list_permissions":
                result = list_permissions(params.get("file_id", ""))

            elif tool_name == "remove_permission":
                result = remove_permission(
                    file_id=params.get("file_id", ""),
                    permission_id=params.get("permission_id", ""),
                )

            elif tool_name == "update_permission":
                result = update_permission(
                    file_id=params.get("file_id", ""),
                    permission_id=params.get("permission_id", ""),
                    role=params.get("role", "reader"),
                )

            elif tool_name == "make_public":
                result = make_public(params.get("file_id", ""))

            elif tool_name == "remove_public":
                result = remove_public(params.get("file_id", ""))

            # Phase 3 — Smart / AI features
            elif tool_name == "summarize_file":
                result = summarize_file(params.get("file_id", ""))

            elif tool_name == "summarize_folder":
                result = summarize_folder(params.get("folder_id", "root"))

            elif tool_name == "find_duplicates":
                result = find_duplicates(
                    folder_id=params.get("folder_id", "root"),
                    max_files=_clamp(params.get("max_files", 500), 500),
                )

            elif tool_name == "trash_duplicates":
                result = trash_duplicates(
                    folder_id=params.get("folder_id", "root"),
                    max_files=_clamp(params.get("max_files", 500), 500),
                    dry_run=params.get("dry_run", True),
                )

            elif tool_name == "suggest_organization":
                result = suggest_organization(
                    folder_id=params.get("folder_id", "root"),
                    max_files=_clamp(params.get("max_files", 100), 100),
                )

            elif tool_name == "auto_organize":
                result = auto_organize(
                    folder_id=params.get("folder_id", "root"),
                    max_files=_clamp(params.get("max_files", 100), 100),
                    dry_run=params.get("dry_run", True),
                )

            elif tool_name == "bulk_rename":
                result = bulk_rename(
                    folder_id=params.get("folder_id", ""),
                    pattern=params.get("pattern", ""),
                    replacement=params.get("replacement", ""),
                    max_files=_clamp(params.get("max_files", 100), 100),
                    dry_run=params.get("dry_run", True),
                )

            elif tool_name == "list_versions":
                result = list_versions(params.get("file_id", ""))

            elif tool_name == "get_version_info":
                result = get_version_info(
                    file_id=params.get("file_id", ""),
                    revision_id=params.get("revision_id", ""),
                )

            elif tool_name == "restore_version":
                result = restore_version(
                    file_id=params.get("file_id", ""),
                    revision_id=params.get("revision_id", ""),
                )

            elif tool_name == "delete_old_versions":
                result = delete_old_versions(
                    file_id=params.get("file_id", ""),
                    keep_latest=params.get("keep_latest", 5),
                    dry_run=params.get("dry_run", True),
                )

            # Phase 4 — Analytics & Insights
            elif tool_name == "storage_breakdown":
                result = storage_breakdown()

            elif tool_name == "list_large_files":
                result = list_large_files(
                    min_size_mb=params.get("min_size_mb", 50),
                    max_results=_clamp(params.get("max_results", 50), 50),
                )

            elif tool_name == "list_old_files":
                result = list_old_files(
                    days=params.get("days", 365),
                    max_results=_clamp(params.get("max_results", 50), 50),
                )

            elif tool_name == "list_recently_modified":
                result = list_recently_modified(
                    max_results=_clamp(params.get("max_results", 20), 20),
                )

            elif tool_name == "find_orphaned_files":
                result = find_orphaned_files(
                    max_results=_clamp(params.get("max_results", 100), 100),
                )

            elif tool_name == "sharing_report":
                result = sharing_report(
                    max_files=_clamp(params.get("max_files", 200), 200),
                )

            elif tool_name == "generate_drive_report":
                result = generate_drive_report()

            elif tool_name == "get_usage_insights":
                result = get_usage_insights()

            return _observation_from_result(result, tool_name)

        # ── Run the ReAct loop ───────────────────────────────────────────────
        llm = get_llm_client()
        final_answer = llm.reason_and_act(
            user_query,
            _DRIVE_TOOLS_DESCRIPTION,
            _dispatch,
            memory_context,
        )
        return {"status": "success", "action": "react_response",
                "message": final_answer}

    except Exception as e:
        logger.error("Error in ReAct orchestration: %s", e)
        return {
            "status": "error",
            "message": "I had trouble completing that request. Please try rephrasing.",
        }


