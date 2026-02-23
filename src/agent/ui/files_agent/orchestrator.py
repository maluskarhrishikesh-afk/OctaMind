"""
LLM-orchestrated Files Agent command executor.

execute_with_llm_orchestration() lets the LLM pick the right local file
system tool and runs it via the ReAct loop.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from src.agent.llm.llm_parser import get_llm_client
from src.files import (
    # file_ops
    list_directory, get_file_info, copy_file, move_file,
    delete_file, create_folder, rename_file, open_file,
    # search
    search_by_name, search_by_extension, search_by_date,
    search_by_size, find_duplicates, find_empty_folders,
    # archives
    zip_files, zip_folder, unzip_file, list_archive_contents, get_archive_info,
    # organizer
    bulk_rename, organize_by_type, organize_by_date,
    move_files_matching, delete_files_matching, clean_empty_folders, deduplicate_files,
    # disk
    list_drives, get_disk_usage, get_directory_size,
    find_large_files, get_recently_modified,
    # reader
    read_text_file, get_file_stats, preview_csv,
    read_json_file, tail_log, calculate_file_hash,
    # smart_features
    summarize_file, analyze_folder, suggest_organization,
    generate_rename_suggestions, find_related_files, describe_file,
    # cross_agent
    zip_and_email, zip_and_upload_to_drive, email_file,
    upload_file_to_drive, send_file_via_whatsapp,
)

logger = logging.getLogger("files_agent")

try:
    from src.agent.memory.agent_memory import get_agent_memory
    MEMORY_AVAILABLE = True
except Exception:
    MEMORY_AVAILABLE = False

# ── Path hints injected into every LLM context call ─────────────────────────
def _path_hints() -> str:
    """Return a one-paragraph hint about common OS paths for the LLM."""
    from pathlib import Path as _Path
    home = _Path.home()
    return (
        f"IMPORTANT PATH CONTEXT (use these full paths when the user mentions common folders):\n"
        f"  Home directory  : {home}\n"
        f"  Downloads       : {home / 'Downloads'}\n"
        f"  Desktop         : {home / 'Desktop'}\n"
        f"  Documents       : {home / 'Documents'}\n"
        f"  Pictures        : {home / 'Pictures'}\n"
        f"Always pass FULL ABSOLUTE PATHS to tools — e.g. pass \"{home / 'Downloads' / 'rtofraud'}\" "
        f"when the user says 'rtofraud folder in downloads'."
    )


# ── Tool descriptions for LLM orchestration ──────────────────────────────────
_FILES_TOOLS_DESCRIPTION = """
## File & Folder Operations

1. **list_directory**(path: str, show_hidden: bool = False, limit: int = 200)
   - List files and subfolders at a path
   - Use for: "show files in", "list folder", "what's in D:/Photos"

2. **get_file_info**(path: str)
   - Get name, size, extension, created/modified dates for a file or folder
   - Use for: "info about", "file details", "when was X modified"

3. **copy_file**(source: str, destination: str)
   - Copy a file or entire folder tree
   - Use for: "copy X to Y", "duplicate file", "backup folder"

4. **move_file**(source: str, destination: str)
   - Move or rename a file or folder
   - Use for: "move X to Y", "rename folder", "relocate"

5. **delete_file**(path: str, permanent: bool = False)
   - Delete a file or folder (Recycle Bin by default; permanent=True to skip)
   - ALWAYS use dry_run approach: describe what will be deleted before setting permanent=True
   - Use for: "delete", "remove file", "trash folder"

6. **create_folder**(path: str)
   - Create a directory (and any missing parents)
   - Use for: "create folder", "make directory", "new folder"

7. **rename_file**(path: str, new_name: str)
   - Rename a file or folder in-place
   - new_name must be just the name, not a full path
   - Use for: "rename X to Y"

8. **open_file**(path: str)
   - Open with the default application (e.g. PDF → Acrobat, .xlsx → Excel)
   - Use for: "open file", "launch", "view with default app"

## Search & Finding

9. **search_by_name**(query: str, directory: str = "~", recursive: bool = True, limit: int = 50)
   - Search by filename glob ('*.pdf', 'report*') or substring
   - Use for: "find files named", "search for *.docx", "where is report.pdf"

10. **search_by_extension**(ext: str, directory: str = "~", recursive: bool = True, limit: int = 100)
    - Find all files with a given extension
    - Use for: "find all PDFs", "list JPG files", "show all Excel files"

11. **search_by_date**(directory: str, after: str = "", before: str = "", recursive: bool = True, limit: int = 100)
    - Find files modified in a date range
    - after/before: ISO date 'YYYY-MM-DD' or natural language 'last 7 days', 'last week', 'last month', 'today'
    - Use for: "files from last week", "modified today", "files between Jan 1 and Feb 1"

12. **search_by_size**(directory: str, min_mb: float = 0, max_mb: float = 0, recursive: bool = True, limit: int = 100)
    - Find files within a size range (in MB)
    - Use for: "large files", "files bigger than 100MB", "files between 1MB and 10MB"

13. **find_duplicates**(directory: str, recursive: bool = True)
    - Detect duplicate files by MD5 hash
    - Use for: "find duplicate files", "show duplicates", "what's taking space"

14. **find_empty_folders**(directory: str, recursive: bool = True)
    - Locate folders with no files
    - Use for: "empty folders", "unused directories"

## Archives (Zip)

15. **zip_files**(sources: list, output_path: str, compression_level: int = 6)
    - Zip one or more files/folders into a single archive
    - sources must be a Python list of path strings
    - Use for: "zip these files", "create archive", "compress multiple"

16. **zip_folder**(folder_path: str, output_path: str = "")
    - Zip an entire folder (shorthand for zip_files)
    - Use for: "zip the folder", "compress D:/Photos", "archive my documents"

17. **unzip_file**(archive_path: str, destination: str = "")
    - Extract a zip archive
    - Use for: "unzip", "extract archive", "decompress"

18. **list_archive_contents**(archive_path: str)
    - Preview zip contents without extracting
    - Use for: "what's in the zip", "show archive contents"

19. **get_archive_info**(archive_path: str)
    - Summary stats: file count, original vs compressed size, ratio
    - Use for: "zip stats", "archive info"

## Organisation (bulk ops — always dry_run=True first)

20. **bulk_rename**(directory: str, pattern: str, replacement: str, dry_run: bool = True)
    - Rename all files matching a pattern (supports regex)
    - ALWAYS show preview first (dry_run=True), only apply with dry_run=False after user confirms
    - Use for: "rename all files with X to Y", "replace in filenames"

21. **organize_by_type**(directory: str, destination: str = "", dry_run: bool = True)
    - Sort files into subfolders by type: Images/, Documents/, Videos/, etc.
    - Use for: "organise by type", "sort files", "clean up folder"

22. **organize_by_date**(directory: str, dry_run: bool = True)
    - Sort files into YYYY/MM/ subfolders by modification date
    - Use for: "organise by date", "sort by year"

23. **move_files_matching**(pattern: str, source: str, destination: str, dry_run: bool = True)
    - Move all files matching a glob to another folder
    - Use for: "move all PDFs to X", "move matching files"

24. **delete_files_matching**(pattern: str, directory: str, dry_run: bool = True, permanent: bool = False)
    - Delete files matching a pattern
    - ALWAYS preview with dry_run=True first
    - Use for: "delete all .tmp files", "remove log files"

25. **clean_empty_folders**(directory: str, dry_run: bool = True)
    - Remove empty directories
    - Use for: "clean empty folders", "remove unused directories"

26. **deduplicate_files**(directory: str, keep: str = "newest", dry_run: bool = True)
    - Remove duplicate files, keep newest or oldest
    - ALWAYS preview first
    - Use for: "remove duplicates", "deduplicate folder"

## Disk & Drive Analytics

27. **list_drives**()
    - List all drives with free/used/total space
    - Use for: "show drives", "what drives do I have", "disk space overview"

28. **get_disk_usage**(path: str = "C:/")
    - Free/used/total for a specific drive or path
    - Use for: "how much space on C:", "disk usage for D:", "free space"

29. **get_directory_size**(path: str)
    - Total size of a folder (recursive)
    - Use for: "how big is this folder", "size of D:/Photos"

30. **find_large_files**(directory: str, min_mb: float = 100, limit: int = 20, recursive: bool = True)
    - Find the largest files in a directory
    - Use for: "what's taking space", "large files", "biggest files"

31. **get_recently_modified**(directory: str, days: int = 7, limit: int = 30, recursive: bool = True)
    - Files changed in the last N days
    - Use for: "recently changed files", "what did I edit this week"

## File Content Reading

32. **read_text_file**(path: str, max_lines: int = 200)
    - Read text content: .txt, .md, .py, .json, .csv, .html, .log, etc.
    - Use for: "read file", "show contents", "what does this file contain"

33. **get_file_stats**(path: str)
    - Word count, line count, character count
    - Use for: "word count", "how many lines", "file statistics"

34. **preview_csv**(path: str, rows: int = 10)
    - Column headers + first N rows of a CSV file
    - Use for: "preview CSV", "show columns", "what's in this spreadsheet"

35. **read_json_file**(path: str)
    - Parse and return a JSON file
    - Use for: "read JSON", "show JSON contents"

36. **tail_log**(path: str, lines: int = 50)
    - Last N lines of a log/text file
    - Use for: "tail log", "last lines", "recent log entries"

37. **calculate_file_hash**(path: str, algorithm: str = "md5")
    - MD5 or SHA-256 hash for integrity verification
    - Use for: "file hash", "checksum", "verify file integrity"

## AI Smart Features

38. **summarize_file**(path: str)
    - LLM-generated summary of any readable text file
    - Use for: "summarise this file", "what is this document about"

39. **analyze_folder**(directory: str)
    - LLM analysis of a folder: contents, patterns, suggestions
    - Use for: "analyse this folder", "what's in here overview"

40. **suggest_organization**(directory: str)
    - LLM recommends a better folder structure
    - Use for: "suggest organisation", "how should I organise this"

41. **generate_rename_suggestions**(directory: str)
    - LLM suggests cleaner names for cryptic filenames
    - Use for: "suggest better names", "rename suggestions"

42. **find_related_files**(path: str)
    - Find files related to a given file by name similarity
    - Use for: "related files", "find similar files"

43. **describe_file**(path: str)
    - Natural language description of what a file is
    - Use for: "what is this file", "describe this", "file description"

## Cross-Agent Integration

44. **zip_and_email**(path: str, to_email: str, subject: str = "", body: str = "")
    - Zip a file/folder then send via Gmail
    - Use for: "zip and email to X", "send compressed folder to Y"

45. **zip_and_upload_to_drive**(path: str, drive_folder_name: str = "")
    - Zip then upload to Google Drive
    - Use for: "zip and upload to Drive", "backup folder to Drive"

46. **email_file**(path: str, to_email: str, subject: str = "", body: str = "")
    - Attach a file directly to a Gmail email
    - Use for: "email this file to X", "send file via email"

47. **upload_file_to_drive**(path: str, drive_folder_name: str = "")
    - Upload a file directly to Google Drive
    - Use for: "upload to Drive", "put this on Drive"

48. **send_file_via_whatsapp**(to: str, path: str, caption: str = "")
    - Share a file via WhatsApp (requires publicly hosted URL)
    - Use for: "send via WhatsApp", "share on WhatsApp"
"""


def _clamp(val: Any, maximum: int) -> int:
    """Safety cap on numeric parameters to prevent runaway bulk operations."""
    try:
        return min(int(val), maximum)
    except (TypeError, ValueError):
        return maximum


def _observation_from_result(result: Dict[str, Any], tool_name: str) -> str:
    """Convert a tool result dict into a readable observation string."""
    if result.get("status") == "error":
        return f"Error: {result.get('message', 'Unknown error')}"

    # Directory listing
    if "entries" in result:
        entries = result["entries"]
        lines = [
            f"Directory: {result.get('path','')} — "
            f"{result.get('folders',0)} folder(s), {result.get('files',0)} file(s)"
        ]
        for e in entries[:30]:
            icon = "📁" if e.get("type") == "folder" else "📄"
            size = f" ({e['size']})" if e.get("size") else ""
            lines.append(f"  {icon} {e['name']}{size}")
        if result.get("total_entries", 0) > 30:
            lines.append(f"  ... and {result['total_entries'] - 30} more")
        return "\n".join(lines)

    # Search results
    if "results" in result and isinstance(result["results"], list):
        items = result["results"]
        lines = [f"Found {result.get('count', len(items))} item(s):"]
        for r in items[:20]:
            size = f" ({r.get('size','')}) " if r.get("size") else ""
            modified = f"modified {r.get('modified','')[:10]}" if r.get("modified") else ""
            lines.append(f"  {r.get('path', r.get('name',''))} {size}{modified}")
        if len(items) > 20:
            lines.append(f"  ... and {len(items) - 20} more")
        return "\n".join(lines)

    # Drives
    if "drives" in result:
        lines = ["Drives:"]
        for d in result["drives"]:
            if "error" in d:
                lines.append(f"  {d['drive']} — {d['error']}")
            else:
                lines.append(f"  {d['drive']} — {d.get('free','')} free / {d.get('total','')} total ({d.get('used_pct','')} used)")
        return "\n".join(lines)

    # Archive contents
    if "contents" in result:
        lines = [f"Archive: {result.get('archive','')} — {result.get('entry_count',0)} entries ({result.get('archive_size','')})"]
        for c in result["contents"][:20]:
            lines.append(f"  {c['name']} ({c.get('original_size','')})")
        if result.get("entry_count", 0) > 20:
            lines.append(f"  ... and {result['entry_count'] - 20} more")
        return "\n".join(lines)

    # Duplicate groups
    if "groups" in result:
        lines = [
            f"Found {result.get('duplicate_groups',0)} duplicate group(s), "
            f"wasting {result.get('total_wasted_space','')}:"
        ]
        for g in result["groups"][:10]:
            lines.append(f"  [{g['count']} copies, {g.get('size_each','')} each] {g['files'][0]}")
        return "\n".join(lines)

    # Default: return message or summary fields
    for key in ("message", "summary", "analysis", "suggestion", "suggestions", "description", "content"):
        if key in result:
            return result[key]

    import json as _json
    return _json.dumps({k: v for k, v in result.items() if k != "status"}, indent=2)[:2000]


def _dispatch(tool_name: str, params: dict) -> str:
    """Execute one Files tool and return a readable observation string."""
    result: Dict[str, Any] = {}

    # ── File & Folder Operations ──────────────────────────────────────────────
    if tool_name == "list_directory":
        result = list_directory(
            params.get("path", "~"),
            show_hidden=bool(params.get("show_hidden", False)),
            limit=_clamp(params.get("limit", 100), 200),
        )
    elif tool_name == "get_file_info":
        result = get_file_info(params.get("path", ""))
    elif tool_name == "copy_file":
        result = copy_file(params.get("source", ""), params.get("destination", ""))
    elif tool_name == "move_file":
        result = move_file(params.get("source", ""), params.get("destination", ""))
    elif tool_name == "delete_file":
        result = delete_file(params.get("path", ""), permanent=bool(params.get("permanent", False)))
    elif tool_name == "create_folder":
        result = create_folder(params.get("path", ""))
    elif tool_name == "rename_file":
        result = rename_file(params.get("path", ""), params.get("new_name", ""))
    elif tool_name == "open_file":
        result = open_file(params.get("path", ""))

    # ── Search ────────────────────────────────────────────────────────────────
    elif tool_name == "search_by_name":
        result = search_by_name(
            params.get("query", ""),
            directory=params.get("directory", "~"),
            recursive=bool(params.get("recursive", True)),
            limit=_clamp(params.get("limit", 50), 200),
        )
    elif tool_name == "search_by_extension":
        result = search_by_extension(
            params.get("ext", ""),
            directory=params.get("directory", "~"),
            recursive=bool(params.get("recursive", True)),
            limit=_clamp(params.get("limit", 100), 300),
        )
    elif tool_name == "search_by_date":
        result = search_by_date(
            params.get("directory", "~"),
            after=params.get("after", ""),
            before=params.get("before", ""),
            recursive=bool(params.get("recursive", True)),
            limit=_clamp(params.get("limit", 100), 300),
        )
    elif tool_name == "search_by_size":
        result = search_by_size(
            params.get("directory", "~"),
            min_mb=float(params.get("min_mb", 0)),
            max_mb=float(params.get("max_mb", 0)),
            recursive=bool(params.get("recursive", True)),
            limit=_clamp(params.get("limit", 100), 300),
        )
    elif tool_name == "find_duplicates":
        result = find_duplicates(
            params.get("directory", "~"),
            recursive=bool(params.get("recursive", True)),
        )
    elif tool_name == "find_empty_folders":
        result = find_empty_folders(
            params.get("directory", "~"),
            recursive=bool(params.get("recursive", True)),
        )

    # ── Archives ──────────────────────────────────────────────────────────────
    elif tool_name == "zip_files":
        sources = params.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        result = zip_files(sources, params.get("output_path", ""))
    elif tool_name == "zip_folder":
        result = zip_folder(params.get("folder_path", ""), params.get("output_path", ""))
    elif tool_name == "unzip_file":
        result = unzip_file(params.get("archive_path", ""), params.get("destination", ""))
    elif tool_name == "list_archive_contents":
        result = list_archive_contents(params.get("archive_path", ""))
    elif tool_name == "get_archive_info":
        result = get_archive_info(params.get("archive_path", ""))

    # ── Organizer ─────────────────────────────────────────────────────────────
    elif tool_name == "bulk_rename":
        result = bulk_rename(
            params.get("directory", ""),
            params.get("pattern", ""),
            params.get("replacement", ""),
            dry_run=bool(params.get("dry_run", True)),
        )
    elif tool_name == "organize_by_type":
        result = organize_by_type(
            params.get("directory", ""),
            destination=params.get("destination", ""),
            dry_run=bool(params.get("dry_run", True)),
        )
    elif tool_name == "organize_by_date":
        result = organize_by_date(
            params.get("directory", ""),
            dry_run=bool(params.get("dry_run", True)),
        )
    elif tool_name == "move_files_matching":
        result = move_files_matching(
            params.get("pattern", ""),
            params.get("source", ""),
            params.get("destination", ""),
            dry_run=bool(params.get("dry_run", True)),
        )
    elif tool_name == "delete_files_matching":
        result = delete_files_matching(
            params.get("pattern", ""),
            params.get("directory", ""),
            dry_run=bool(params.get("dry_run", True)),
            permanent=bool(params.get("permanent", False)),
        )
    elif tool_name == "clean_empty_folders":
        result = clean_empty_folders(
            params.get("directory", ""),
            dry_run=bool(params.get("dry_run", True)),
        )
    elif tool_name == "deduplicate_files":
        result = deduplicate_files(
            params.get("directory", ""),
            keep=params.get("keep", "newest"),
            dry_run=bool(params.get("dry_run", True)),
        )

    # ── Disk ──────────────────────────────────────────────────────────────────
    elif tool_name == "list_drives":
        result = list_drives()
    elif tool_name == "get_disk_usage":
        result = get_disk_usage(params.get("path", "C:/"))
    elif tool_name == "get_directory_size":
        result = get_directory_size(params.get("path", ""))
    elif tool_name == "find_large_files":
        result = find_large_files(
            params.get("directory", "~"),
            min_mb=float(params.get("min_mb", 100)),
            limit=_clamp(params.get("limit", 20), 100),
            recursive=bool(params.get("recursive", True)),
        )
    elif tool_name == "get_recently_modified":
        result = get_recently_modified(
            params.get("directory", "~"),
            days=int(params.get("days", 7)),
            limit=_clamp(params.get("limit", 30), 100),
            recursive=bool(params.get("recursive", True)),
        )

    # ── Reader ────────────────────────────────────────────────────────────────
    elif tool_name == "read_text_file":
        result = read_text_file(
            params.get("path", ""),
            max_lines=_clamp(params.get("max_lines", 200), 500),
        )
    elif tool_name == "get_file_stats":
        result = get_file_stats(params.get("path", ""))
    elif tool_name == "preview_csv":
        result = preview_csv(
            params.get("path", ""),
            rows=_clamp(params.get("rows", 10), 50),
        )
    elif tool_name == "read_json_file":
        result = read_json_file(params.get("path", ""))
    elif tool_name == "tail_log":
        result = tail_log(
            params.get("path", ""),
            lines=_clamp(params.get("lines", 50), 200),
        )
    elif tool_name == "calculate_file_hash":
        result = calculate_file_hash(
            params.get("path", ""),
            algorithm=params.get("algorithm", "md5"),
        )

    # ── Smart Features ────────────────────────────────────────────────────────
    elif tool_name == "summarize_file":
        result = summarize_file(params.get("path", ""))
    elif tool_name == "analyze_folder":
        result = analyze_folder(params.get("directory", ""))
    elif tool_name == "suggest_organization":
        result = suggest_organization(params.get("directory", ""))
    elif tool_name == "generate_rename_suggestions":
        result = generate_rename_suggestions(params.get("directory", ""))
    elif tool_name == "find_related_files":
        result = find_related_files(params.get("path", ""))
    elif tool_name == "describe_file":
        result = describe_file(params.get("path", ""))

    # ── Cross-Agent ───────────────────────────────────────────────────────────
    elif tool_name == "zip_and_email":
        result = zip_and_email(
            params.get("path", ""),
            params.get("to_email", ""),
            subject=params.get("subject", ""),
            body=params.get("body", ""),
        )
    elif tool_name == "zip_and_upload_to_drive":
        result = zip_and_upload_to_drive(
            params.get("path", ""),
            drive_folder_name=params.get("drive_folder_name", ""),
        )
    elif tool_name == "email_file":
        result = email_file(
            params.get("path", ""),
            params.get("to_email", ""),
            subject=params.get("subject", ""),
            body=params.get("body", ""),
        )
    elif tool_name == "upload_file_to_drive":
        result = upload_file_to_drive(
            params.get("path", ""),
            drive_folder_name=params.get("drive_folder_name", ""),
        )
    elif tool_name == "send_file_via_whatsapp":
        result = send_file_via_whatsapp(
            params.get("to", ""),
            params.get("path", ""),
            caption=params.get("caption", ""),
        )
    else:
        return f"Unknown tool: {tool_name}"

    return _observation_from_result(result, tool_name)


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str = None,
    max_operations: int = 100,
    artifacts_out: dict = None,
) -> Dict[str, Any]:
    """
    Run the ReAct loop for a user query about local files.

    Returns a dict with 'status', 'response', and optional 'artifacts_out'.
    """
    llm = get_llm_client()

    memory_context = _path_hints() + "\n\n"
    if agent_id and MEMORY_AVAILABLE:
        try:
            memory = get_agent_memory(agent_id)
            memory_context += memory.get_full_context_for_llm()
            recalled = memory.recall_for_llm(user_query)
            if recalled:
                memory_context += f"\n\n{recalled}"
        except Exception as exc:
            logger.warning("Memory load failed: %s", exc)

    try:
        response = llm.reason_and_act(
            user_query,
            _FILES_TOOLS_DESCRIPTION,
            _dispatch,
            memory_context,
        )

        # Propagate zip output path for multi-agent artifact handoff
        if artifacts_out is not None and isinstance(response, str):
            import re as _re
            # Extract the first absolute path that looks like an archive
            m = _re.search(
                r'[A-Za-z]:[/\\][\w ./\\-]+\.zip',
                response, _re.IGNORECASE,
            )
            if m:
                artifacts_out["file_path"] = m.group(0).replace("\\", "/")

        if agent_id and MEMORY_AVAILABLE:
            try:
                memory = get_agent_memory(agent_id)
                memory.add_interaction(user_query, str(response))
            except Exception as exc:
                logger.warning("Memory save failed: %s", exc)

        msg = response if isinstance(response, str) else str(response)
        return {"status": "success", "message": msg, "action": "react_response"}
    except Exception as exc:
        logger.error("execute_with_llm_orchestration failed: %s", exc)
        return {"status": "error", "message": str(exc), "action": "error"}
