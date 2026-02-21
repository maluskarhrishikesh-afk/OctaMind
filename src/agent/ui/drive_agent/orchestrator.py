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


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str = None,
    max_operations: int = 100,
) -> Dict[str, Any]:
    """
    Execute Drive commands using LLM-orchestrated tool selection.

    Args:
        user_query:     Natural language query from user.
        agent_id:       Agent ID for memory context.
        max_operations: Maximum number of individual Drive API operations allowed.

    Returns:
        Result dictionary from the tool execution.
    """
    try:
        memory_context = ""
        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory_context = memory.get_full_context_for_llm()
            except Exception:
                pass

        llm = get_llm_client()
        tool_decision = llm.orchestrate_mcp_tool(
            user_query, memory_context, tools_description=_DRIVE_TOOLS_DESCRIPTION
        )

        tool_name = tool_decision.get("tool")
        params = tool_decision.get("params", {})
        reasoning = tool_decision.get("reasoning", "")

        logger.debug(
            "[LLM] Tool: %s | Params: %s | max_ops: %s",
            tool_name, params, max_operations,
        )

        # ── max_operations guard ─────────────────────────────────────────────
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
                    f"\n\n⚠️ *Results capped at {effective} (max operations limit). "
                    f"You can raise this limit in ⚙️ Configure → General Settings.*"
                )
            return effective

        # ── Tool dispatch ────────────────────────────────────────────────────

        # Phase 1 ── Core file operations
        if tool_name == "list_files":
            files = list_files(
                max_results=_clamp(params.get("max_results", 20)),
                query=params.get("query", ""),
                folder_id=params.get("folder_id", "root"),
            )
            return {
                "status": "success", "action": "list_files",
                "files": files, "reasoning": reasoning + _ops_capped_note,
            }

        elif tool_name == "search_files":
            files = search_files(
                query=params.get("query", ""),
                max_results=_clamp(params.get("max_results", 20)),
            )
            return {
                "status": "success", "action": "search_files",
                "files": files, "query": params.get("query", ""),
                "reasoning": reasoning + _ops_capped_note,
            }

        elif tool_name == "get_file_info":
            return {**get_file_info(params.get("file_id", "")),
                    "action": "file_info", "reasoning": reasoning}

        elif tool_name == "upload_file":
            result = upload_file(
                local_path=params.get("local_path", ""),
                name=params.get("name"),
                folder_id=params.get("folder_id"),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "download_file":
            raw_id = params.get("file_id", "")
            # If the supplied "file_id" looks like a name (has extension, space,
            # or is too short to be a real Drive ID), resolve it via search first.
            import re as _re
            _looks_like_name = (
                "." in raw_id
                or " " in raw_id
                or len(raw_id) < 20
                or not _re.match(r'^[A-Za-z0-9_\-]{20,}$', raw_id)
            )
            if _looks_like_name and raw_id:
                logger.debug(
                    "[download_file] resolving name '%s' to file ID", raw_id)
                hits = search_files(query=raw_id, max_results=1)
                if not hits:
                    return {
                        "status": "error",
                        "message": (
                            f"Could not find a file named **{raw_id}** in your Drive. "
                            "Try listing your files first to confirm the exact name."
                        ),
                    }
                raw_id = hits[0]["id"]
                logger.debug("[download_file] resolved to ID: %s", raw_id)
            result = download_file(
                file_id=raw_id,
                destination=params.get("destination"),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "create_folder":
            result = create_folder(
                name=params.get("name", "New Folder"),
                parent_id=params.get("parent_id"),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "move_file":
            result = move_file(
                file_id=params.get("file_id", ""),
                destination_folder_id=params.get("destination_folder_id", ""),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "copy_file":
            result = copy_file(
                file_id=params.get("file_id", ""),
                name=params.get("name"),
                folder_id=params.get("folder_id"),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "trash_file":
            result = trash_file(params.get("file_id", ""))
            result["reasoning"] = reasoning
            return result

        elif tool_name == "restore_file":
            result = restore_file(params.get("file_id", ""))
            result["reasoning"] = reasoning
            return result

        elif tool_name == "star_file":
            result = star_file(
                params.get("file_id", ""),
                starred=params.get("starred", True),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "get_storage_quota":
            result = get_storage_quota()
            result["action"] = "storage_quota"
            result["reasoning"] = reasoning
            return result

        # Phase 2 ── Sharing & Permissions
        elif tool_name == "share_file":
            result = share_file(
                file_id=params.get("file_id", ""),
                email=params.get("email", ""),
                role=params.get("role", "reader"),
                send_notification=params.get("send_notification", True),
                message=params.get("message"),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "list_permissions":
            result = list_permissions(params.get("file_id", ""))
            result["action"] = "list_permissions"
            result["reasoning"] = reasoning
            return result

        elif tool_name == "remove_permission":
            result = remove_permission(
                file_id=params.get("file_id", ""),
                permission_id=params.get("permission_id", ""),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "update_permission":
            result = update_permission(
                file_id=params.get("file_id", ""),
                permission_id=params.get("permission_id", ""),
                role=params.get("role", "reader"),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "make_public":
            result = make_public(params.get("file_id", ""))
            result["reasoning"] = reasoning
            return result

        elif tool_name == "remove_public":
            result = remove_public(params.get("file_id", ""))
            result["reasoning"] = reasoning
            return result

        # Phase 3 ── Smart / AI features
        elif tool_name == "summarize_file":
            result = summarize_file(params.get("file_id", ""))
            result["action"] = "summarize_file"
            result["reasoning"] = reasoning
            return result

        elif tool_name == "summarize_folder":
            result = summarize_folder(params.get("folder_id", "root"))
            result["action"] = "summarize_folder"
            result["reasoning"] = reasoning
            return result

        elif tool_name == "find_duplicates":
            result = find_duplicates(
                folder_id=params.get("folder_id", "root"),
                max_files=_clamp(params.get("max_files", 500), 500),
            )
            result["action"] = "find_duplicates"
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "trash_duplicates":
            result = trash_duplicates(
                folder_id=params.get("folder_id", "root"),
                max_files=_clamp(params.get("max_files", 500), 500),
                dry_run=params.get("dry_run", True),
            )
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "suggest_organization":
            result = suggest_organization(
                folder_id=params.get("folder_id", "root"),
                max_files=_clamp(params.get("max_files", 100), 100),
            )
            result["action"] = "suggest_organization"
            result["reasoning"] = reasoning
            return result

        elif tool_name == "auto_organize":
            result = auto_organize(
                folder_id=params.get("folder_id", "root"),
                max_files=_clamp(params.get("max_files", 100), 100),
                dry_run=params.get("dry_run", True),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "bulk_rename":
            result = bulk_rename(
                folder_id=params.get("folder_id", ""),
                pattern=params.get("pattern", ""),
                replacement=params.get("replacement", ""),
                max_files=_clamp(params.get("max_files", 100), 100),
                dry_run=params.get("dry_run", True),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "list_versions":
            result = list_versions(params.get("file_id", ""))
            result["action"] = "list_versions"
            result["reasoning"] = reasoning
            return result

        elif tool_name == "restore_version":
            result = restore_version(
                file_id=params.get("file_id", ""),
                revision_id=params.get("revision_id", ""),
            )
            result["reasoning"] = reasoning
            return result

        elif tool_name == "delete_old_versions":
            result = delete_old_versions(
                file_id=params.get("file_id", ""),
                keep_latest=params.get("keep_latest", 5),
                dry_run=params.get("dry_run", True),
            )
            result["reasoning"] = reasoning
            return result

        # Phase 4 ── Analytics & Insights
        elif tool_name == "storage_breakdown":
            result = storage_breakdown(
                max_files=_clamp(params.get("max_files", 1000), 1000)
            )
            result["action"] = "storage_breakdown"
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "list_large_files":
            result = list_large_files(
                min_size_mb=params.get("min_size_mb", 50),
                max_results=_clamp(params.get("max_results", 50), 50),
            )
            result["action"] = "list_large_files"
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "list_old_files":
            result = list_old_files(
                days=params.get("days", 365),
                max_results=_clamp(params.get("max_results", 50), 50),
            )
            result["action"] = "list_old_files"
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "list_recently_modified":
            result = list_recently_modified(
                max_results=_clamp(params.get("max_results", 20), 20)
            )
            result["action"] = "list_files"
            result["files"] = result.get("files", [])
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "find_orphaned_files":
            result = find_orphaned_files(
                max_results=_clamp(params.get("max_results", 100), 100)
            )
            result["action"] = "list_files"
            result["files"] = result.get("files", [])
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "sharing_report":
            result = sharing_report(
                max_files=_clamp(params.get("max_files", 200), 200)
            )
            result["action"] = "sharing_report"
            result["reasoning"] = reasoning + _ops_capped_note
            return result

        elif tool_name == "generate_drive_report":
            result = generate_drive_report()
            result["action"] = "drive_report"
            result["reasoning"] = reasoning
            return result

        elif tool_name == "get_usage_insights":
            result = get_usage_insights()
            result["action"] = "usage_insights"
            result["reasoning"] = reasoning
            return result

        # ── Unknown tool ─────────────────────────────────────────────────────
        else:
            logger.warning("[LLM] Unknown Drive tool: %s", tool_name)
            return {
                "status": "error",
                "message": (
                    f"I don't know how to handle the action `{tool_name}`. "
                    f"Try rephrasing your request, e.g. 'list my files', "
                    f"'search for report', or 'show storage usage'."
                ),
            }

    except Exception as e:
        logger.error("execute_with_llm_orchestration error: %s", e)
        return {"status": "error", "message": str(e)}
