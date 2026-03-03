"""
Local Files skill orchestrator.

Key corrections vs. older version:
- search_by_name first argument is ``query`` (not ``pattern``).
- _build_skill_context() is dynamic so the LLM receives the real
  system paths (home / Downloads / Desktop / Documents) rather than
  guessing platform-specific placeholders.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag

_TOOL_DOCS = """
list_directory(path, show_hidden=False, limit=200) – List files in a local directory.
get_file_info(path) – Get metadata for a local file or folder.
copy_file(source, destination) – Copy a file or folder.
move_file(source, destination) – Move / rename a file or folder.
delete_file(path, permanent=False) – Delete a file (recycle bin by default).
create_folder(path) – Create a new directory.
rename_file(path, new_name) – Rename a file or folder.
open_file(path) – Open a file with its default application.
search_by_name(query, directory="~", recursive=True, limit=50) – Search files/folders whose name matches query (glob or substring). First arg is the search term, second is the directory to search.
search_by_extension(ext, directory="~", recursive=True, limit=100) – Find all files with a given extension (e.g. 'pdf' or '.pdf').
search_by_date(directory, date_from=None, date_to=None, recursive=True, limit=50) – Search by modification date.
search_by_size(directory, min_bytes=None, max_bytes=None, recursive=True, limit=50) – Search by file size.
find_duplicates(directory, recursive=True) – Find duplicate files.
find_empty_folders(directory, recursive=True) – Find empty folders.
zip_folder(folder_path, output_path="") – Zip an entire folder into a .zip archive. output_path defaults to same location as folder with .zip extension.
zip_files(sources, output_path) – Zip one or more files and/or folders into a single archive. sources is a list of paths.
unzip_file(archive_path, destination="") – Extract a zip archive. destination defaults to a folder named after the archive.
list_archive_contents(archive_path) – List contents of a zip archive without extracting.
write_text_file(path, content) – Write text content to a local file (creates or overwrites it). Use when the user says "write this in a notepad", "save this as text", or similar.
write_pdf_report(path, title, content) – Generate a formatted PDF report. Falls back to .txt if fpdf2 is not installed. Use for polished multi-page reports.
write_excel_report(path, sheet_data, title="") – Generate an Excel .xlsx workbook. sheet_data is a dict mapping sheet_name → list-of-dicts. Use when the user asks for data in a spreadsheet or Excel format.
deliver_file(path) – Explicitly mark a local file for download delivery to the user (Telegram document / Dashboard download button). Call this after you have found or created the file the user wants.
search_file_all_drives(query, extensions=None, limit=20, include_folders=True) – Search ALL drives (C:, D:, …) and the full home directory tree for a file OR folder by name/pattern. Use when the user asks to "find", "search", or "zip" something and gives only a name with no path. Returns file_path set to the first match. ALWAYS use this before zip_folder when the folder path is unknown.
list_laptop_structure(include_hidden=False, output_file="", depth=2) – DETERMINISTIC full-laptop scan: discovers all available drives (C:, D:, …) and lists every drive root plus the major user directories (Home, Downloads, Desktop, Documents, Pictures, Music, Videos). The *depth* parameter controls how many levels deep to recurse inside user-created folders (default 2 — shows folder contents). Always writes a report .txt file automatically; the file_path in the result can be attached to emails. Use this whenever the user asks about ALL folders/files on their laptop, entire machine, or all drives.
organize_folder(directory, by="extension", dry_run=True, include_hidden=False) – Organise files in a folder into sub-folders. by options: "extension" (PDF/, Images/, etc.), "date" (year-month), "name" (A-Z), "size" (Small/Medium/Large). ALWAYS call with dry_run=True first to show the user the plan, then call again with dry_run=False to apply.
analyze_disk_usage(path, depth=2, top_n=20) – Recursively compute folder sizes and show biggest space consumers. Use when user asks 'what's taking up space' or 'show disk usage'.
get_drive_info() – Return total/used/free space for all local drives (C:, D:, etc.).
find_duplicate_files(directory, recursive=True, min_size_bytes=1024) – Find duplicate files by MD5 hash. Returns groups and wasted space.
search_files_by_content(query, directory="~", extensions=None, max_results=50, case_sensitive=False) – Grep-like search: find files whose content contains query text. extensions e.g. ['py','txt','md'].
batch_rename(directory, find, replace, dry_run=True, use_regex=False, extensions=None) – Rename files by replacing 'find' with 'replace' in filenames. ALWAYS dry_run=True first to show plan.
secure_delete(path, passes=3) – Overwrite file with random bytes N times before deleting. Use for sensitive files.
cleanup_temp_files(dry_run=True) – Remove OS temp files, Windows Update cache, Python __pycache__. ALWAYS dry_run=True first to show what will be removed.
monitor_folder(path, timeout_seconds=30, poll_interval=1.0) – Watch a folder for file changes (created/modified/deleted) for up to N seconds.
cleanup_app_caches(dry_run=True) – Remove Chrome/Edge/Firefox browser caches and Windows AppData temp files. ALWAYS dry_run=True first to show sizes, then dry_run=False to delete.
archive_old_files(folder, months_old=6, output_zip="", dry_run=True) – Compress files not modified in N months into a zip. dry_run=True first to preview.
resolve_shortcut(lnk_path) – Resolve a Windows .lnk shortcut file to its target executable or folder path.
get_file_hash(file_path, algorithm="md5") – Compute MD5/SHA256/SHA1 hash of a file for integrity checking or duplicate detection.
list_running_apps() – List all running processes with PID, name, memory usage, and CPU percentage.
""".strip()


def _build_skill_context() -> str:
    """Build the files-agent system prompt with real OS paths injected."""
    import sys as _sys
    home = Path.home()
    downloads = home / "Downloads"
    desktop   = home / "Desktop"
    documents = home / "Documents"

    # Detect Windows drive roots so the LLM knows about C:\-level folders
    drive_root_note = ""
    if _sys.platform == "win32":
        try:
            import string as _string
            drive_roots = [
                f"{d}:\\" for d in _string.ascii_uppercase
                if Path(f"{d}:\\").exists()
            ]
            if drive_roots:
                drive_root_note = (
                    "\nAvailable drive roots: " + ", ".join(drive_roots) + "\n"
                    "  Folders at C:\\ root may include user project folders "
                    "(e.g. C:\\Hrishikesh, C:\\Projects, etc.) — these are NOT under Home.\n"
                )
        except Exception:
            pass

    return (
        "You are the Local Files Skill Agent.\n"
        "You can browse, search, copy, move, delete, rename and organise files on the user's local filesystem.\n"
        "Always use ABSOLUTE paths when calling tools.\n"
        "\n"
        "System path reference (use these exact paths):\n"
        f"  Home:      {home}\n"
        f"  Downloads: {downloads}\n"
        f"  Desktop:   {desktop}\n"
        f"  Documents: {documents}\n"
        + drive_root_note +
        "\n"
        "Examples of correct absolute paths on this machine:\n"
        f"  Downloads folder       \u2192 {downloads}\n"
        f"  A folder in Downloads  \u2192 {downloads / 'MyFolder'}\n"
        f"  A file on Desktop      \u2192 {desktop / 'report.pdf'}\n"
        "\n"
        "Rules:\n"
        "- Be careful with delete_file \u2014 prefer permanent=False (recycle bin) unless the user asks for permanent deletion.\n"
        "- For zip/compression ALWAYS use zip_folder (whole folder) or zip_files (specific files).\n"
        "- When the user mentions a folder like 'Downloads', always expand it to the full absolute path shown above.\n"
        "- When the user mentions a folder you cannot find under Home/Downloads/Desktop/Documents, use search_file_all_drives(query) to locate it anywhere on all drives — it now finds BOTH files AND folders. Example: search_file_all_drives('xpanse') will find C:\\Hrishikesh\\xpanse even if it is not under Home.\n"
        "- When asked to ZIP a folder given only by name (e.g. 'zip xpanse'), ALWAYS call search_file_all_drives(folder_name) FIRST to get the full absolute path, THEN call zip_folder(found_path).\n"
        "- Use write_text_file to save any text, list or note to a local .txt file when the user asks to 'write to notepad', 'save this as text', or similar.\n"
        "- Use write_pdf_report for polished PDF reports; use write_excel_report when the user mentions spreadsheet, table, or Excel.\n"
        "- Use list_laptop_structure(output_file=\"...\", depth=2) when the user asks about ALL folders/files on the entire laptop or machine — this scans every drive and user directory deterministically without guessing. Use depth=3 if the user explicitly wants to see inside sub-folders. A .txt report is always auto-saved; include its path in email attachments.\n"
        "- Use search_file_all_drives(query) when the user asks to FIND or SEARCH for any specific file on the laptop — it searches all drives, not just Downloads.\n"
        "- When searching for a file to DELIVER to the user: use search_file_all_drives first; SKIP Windows shortcut files (.lnk extension) — only return actual files (.pdf, .docx, .xlsx, .txt, .jpg, etc.).\n"
        "- Use deliver_file(path) AFTER finding a file to explicitly send it to the user as a download.\n"
        "- Use organize_folder with dry_run=True first to preview, then dry_run=False to move files.\n"
        "- Use analyze_disk_usage(path) when user asks 'what\'s taking up space', 'disk usage', or 'which folder is largest'.\n"
        "- Use get_drive_info() for total storage overview across all drives (total/used/free per drive).\n"
        "- Use find_duplicate_files(directory) to identify duplicates; NEVER delete without user confirmation.\n"
        "- Use search_files_by_content(query, directory) when user wants to find files containing specific text.\n"
        "- Use batch_rename(directory, find, replace, dry_run=True) FIRST to preview; then dry_run=False to apply.\n"
        "- Use secure_delete(path) ONLY when user explicitly says 'securely delete' or 'shred' a file.\n"
        "- Use cleanup_temp_files(dry_run=True) first to show what will be cleaned, then dry_run=False to confirm.\n"
        "- Use monitor_folder(path, timeout_seconds=60) to watch for new files in a folder.\n"
        "- Use cleanup_app_caches(dry_run=True) to show browser / app cache sizes; call with dry_run=False after user confirms.\n"
        "- Use archive_old_files(folder, months_old=6, dry_run=True) to preview which old files will be zipped; re-call with dry_run=False to create the archive.\n"
        "- Use resolve_shortcut(lnk_path) when user says 'open this shortcut' or 'where does this .lnk point'.\n"
        "- Use get_file_hash(path) to check file integrity or when user asks for MD5/SHA256 of a file.\n"
        "- Use list_running_apps() when user asks 'what apps are open', 'show running processes', or 'what is using memory'.\n"
    ).strip()


def _get_tools() -> Dict[str, Any]:
    from src.files.features.file_ops import (  # noqa: PLC0415
        list_directory, get_file_info, copy_file, move_file,
        delete_file, create_folder, rename_file, open_file,
        list_laptop_structure, deliver_file,
        write_pdf_report, write_excel_report, organize_folder,
        analyze_disk_usage, get_drive_info, find_duplicate_files,
        search_files_by_content, batch_rename, secure_delete,
        cleanup_temp_files, monitor_folder,
        cleanup_app_caches, archive_old_files, resolve_shortcut,
        get_file_hash, list_running_apps,
    )
    from src.files.features.search import (  # noqa: PLC0415
        search_by_name, search_by_extension, search_by_date,
        search_by_size, find_duplicates, find_empty_folders,
        search_file_all_drives,
    )
    from src.files.features.archives import (  # noqa: PLC0415
        zip_folder, zip_files, unzip_file, list_archive_contents,
    )

    def write_text_file(path: str, content: str) -> dict:
        """Write *content* as plain text to *path*, creating or overwriting the file."""
        try:
            from pathlib import Path as _Path
            _p = _Path(path).expanduser()
            _p.parent.mkdir(parents=True, exist_ok=True)
            _p.write_text(content, encoding="utf-8")
            return {
                "status": "success",
                "path": str(_p),
                "bytes_written": len(content.encode("utf-8")),
                "message": f"Written {len(content)} character(s) to '{_p}'.",
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error writing file: {exc}"}

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
        "write_text_file": write_text_file,
        "write_pdf_report": write_pdf_report,
        "write_excel_report": write_excel_report,
        "deliver_file": deliver_file,
        "search_file_all_drives": search_file_all_drives,
        "list_laptop_structure": list_laptop_structure,
        "organize_folder": organize_folder,
        # ── NEW ────────────────────────────────────────────────────────────
        "analyze_disk_usage":     analyze_disk_usage,
        "get_drive_info":          get_drive_info,
        "find_duplicate_files":    find_duplicate_files,
        "search_files_by_content": search_files_by_content,
        "batch_rename":            batch_rename,
        "secure_delete":           secure_delete,
        "cleanup_temp_files":      cleanup_temp_files,
        "monitor_folder":          monitor_folder,
        # ── NEW ────────────────────────────────────────────────────────────
        "cleanup_app_caches":      cleanup_app_caches,
        "archive_old_files":       archive_old_files,
        "resolve_shortcut":        resolve_shortcut,
        "get_file_hash":           get_file_hash,
        "list_running_apps":       list_running_apps,
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Skill entry-point called by master_orchestrator / PA chat.

    Primary path: DAG planner (2 LLM calls regardless of task length).
    Fallback:      ReAct loop (1 LLM call per step, up to 6 iterations).
    """
    skill_context = _build_skill_context()  # dynamic — includes real OS paths
    tool_map = _get_tools()
    try:
        return run_skill_dag(
            skill_name="files",
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as dag_exc:
        import logging as _logging
        _logging.getLogger("files.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
    try:
        return run_skill_react(
            skill_name="files",
            skill_context=skill_context,
            tool_map=tool_map,
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
