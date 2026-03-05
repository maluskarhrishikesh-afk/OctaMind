"""
Local Files skill orchestrator.

Key corrections vs. older version:
- search_by_name first argument is ``query`` (not ``pattern``).
- _build_skill_context() is dynamic so the LLM receives the real
  system paths (home / Downloads / Desktop / Documents) rather than
  guessing platform-specific placeholders.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag

_TOOL_DOCS = """
list_directory(path, show_hidden=False, limit=200) – List files in a local directory.
get_file_info(path) – Get metadata for a local file or folder.
copy_file(source, destination) – Copy a file or folder.
collect_files_to_folder(file_paths, destination) – Copy a LIST of files/folders (from any locations) into a single destination folder, creating it if needed. Returns the destination folder path as file_path. Use BEFORE zip_folder when you have files scattered across multiple locations that need to be gathered first. When the user's previous turn found files, use file_paths={__session__.last_found_paths} to reference ALL found paths without enumerating them.
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
save_search_manifest(found_paths, manifest_path="") – Persist a list of found file paths to <workspace>/data/octa_manifest.txt (one path per line). Call this IMMEDIATELY after any search step so the paths survive across turns. found_paths must be a Python list of absolute path strings.
collect_files_from_manifest(manifest_path="", destination="") – Read the manifest file written by save_search_manifest and copy EVERY listed file to *destination*. Default destination: <workspace>/data/. Use this instead of collect_files_to_folder when copying files from a previous search turn — it is NOT limited by session-state size.
undo_last_file_operation() – Undo the most-recent copy/collect operation by deleting the destination folder that was created. Call this when the user says 'undo', 'revert that', 'undo the copy', 'take that back', or 'delete what you just copied'.
list_file_operations(days=30) – Return the file-operation audit history for the last N days (newest-first). Each entry has: type, destination, count, timestamp, undone. Call this when the user asks 'what did you copy recently?', 'show operation history', or 'what operations have been done?'.
save_context(topic, resolved_entities, awaiting="") – Persist the current file listing as cross-turn context. topic="file_search", resolved_entities={"listed_files":[...], "query":"..."}, awaiting="file_action". Call AFTER every search so the user can say 'copy them' next turn without repeating the query.
""".strip()


def _build_skill_context() -> str:
    """Build the files-agent system prompt with real OS paths injected."""
    import sys as _sys
    home = Path.home()
    downloads = home / "Downloads"
    desktop   = home / "Desktop"
    documents = home / "Documents"
    # Workspace-relative data folder (consistent across OS)
    data_dir  = Path(__file__).resolve().parents[4] / "data"

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
        "⛔ RULE #1 — NEVER ask the user for a destination folder, confirmation, or any missing parameter.\n"
        "   If destination is not specified → SILENTLY use the default: "
        f"{data_dir}\n"
        "   If you are copying files from a previous search → call collect_files_from_manifest().\n"
        "   • If the user named a destination (e.g. 'copy to qwerty in Downloads'), pass\n"
        "     destination=<resolved full path> (e.g. destination=str(Downloads / 'qwerty')).\n"
        "   • ONLY omit destination when the user did NOT specify one — it defaults to data/.\n"
        "   Do NOT ask the user for anything. Act immediately.\n"
        "- Be careful with delete_file \u2014 prefer permanent=False (recycle bin) unless the user asks for permanent deletion.\n"
        "- For zip/compression ALWAYS use zip_folder (whole folder) or zip_files (specific files).\n"
        f"- When zipping for email/delivery, ALWAYS specify output_path inside the Downloads folder ({downloads}\\<ArchiveName>.zip) so the zip is always written to a writable location. NEVER leave output_path empty when the source folder may be under C:\\Windows\\ or other system paths.\n"
        "- When the user mentions a folder like 'Downloads', always expand it to the full absolute path shown above.\n"
        "- When the user mentions a folder you cannot find under Home/Downloads/Desktop/Documents, use search_file_all_drives(query) to locate it anywhere on all drives — it now finds BOTH files AND folders. Example: search_file_all_drives('xpanse') will find C:\\Hrishikesh\\xpanse even if it is not under Home.\n"
        "- When asked to ZIP a folder given only by name (e.g. 'zip xpanse'), ALWAYS call search_file_all_drives(folder_name) FIRST to get the full absolute path, THEN call zip_folder(found_path, output_path=str(Downloads / (folder_name + '.zip'))).\n"
        "- Use write_text_file to save any text, list or note to a local .txt file when the user asks to 'write to notepad', 'save this as text', or similar.\n"
        "- Use write_pdf_report for polished PDF reports; use write_excel_report when the user mentions spreadsheet, table, or Excel.\n"
        "- Use list_laptop_structure(output_file=\"...\", depth=2) when the user asks about ALL folders/files on the entire laptop or machine — this scans every drive and user directory deterministically without guessing. Use depth=3 if the user explicitly wants to see inside sub-folders. A .txt report is always auto-saved; include its path in email attachments.\n"
        "- Use search_file_all_drives(query) when the user asks to FIND or SEARCH for any specific file on the laptop — it searches all drives, not just Downloads.\n"
        "- When searching for a file to DELIVER to the user: use search_file_all_drives first; SKIP Windows shortcut files (.lnk extension) — only return actual files (.pdf, .docx, .xlsx, .txt, .jpg, etc.).\n"
        "- Use deliver_file(path) AFTER finding a file to explicitly send it to the user as a download.\n"
        "⚠️ SEARCH STRATEGY FOR FILE TYPE QUERIES:\n"
        "  When the user asks 'are there any image files / video files / pdf files' etc., ALWAYS search by\n"
        "  extension (NOT by name). Run one search_by_extension call per relevant extension, then after ALL\n"
        "  searches complete, call save_search_manifest(found_paths=[...all collected paths...]).\n"
        "  Image extensions  → jpg, jpeg, png, gif, bmp, tiff, tif, webp, svg, ico\n"
        "  Video extensions  → mp4, avi, mov, mkv, wmv, flv, webm\n"
        "  Document extensions → pdf, docx, doc, xlsx, xls, pptx, ppt, txt\n"
        "  Run ALL extension searches BEFORE calling save_search_manifest with the combined list.\n"
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
        "- Use collect_files_to_folder(file_paths=[...], destination=...) when you have a LIST of files from different locations that need to be gathered into one folder before zipping/sharing. Returns file_path = the destination folder, which can then be passed to zip_folder.\n"
        "- The full flow for 'collect found files, zip and email' is: collect_files_to_folder → zip_folder → email attachment.\n"
        "- DEFAULT DESTINATION FOLDER: Unless the user explicitly names a different folder/path, ALWAYS use\n"
        f"  {data_dir} as the destination for copy/collect/zip operations.\n"
        "  Never use generic names like 'CollectedImages', 'ImageFiles', or 'Output' — use the data folder.\n"
        "- save_search_manifest(found_paths=[...]) — call this after a search to save ALL found paths reliably.\n"
        "- collect_files_from_manifest(destination=...) — use this when copying files from a PREVIOUS search\n"
        "  turn (even if the user says 'copy them'). It reads the saved manifest and copies EVERY found file.\n"
        "  It is more reliable than collect_files_to_folder because it is not limited by session-state size.\n"
        "- undo_last_file_operation() — call this when user says 'undo', 'revert that', 'take that back',\n"
        "  'undo the copy', or 'delete what you copied'. Deletes the folder created by the last copy.\n"
        "- list_file_operations(days=30) — call this when user asks 'what did you copy?', 'show history',\n"
        "  'what operations were done recently?'. Returns audit log newest-first.\n"
        "\n"
        "## Handling '## Session State' context (CRITICAL)\n"
        "The user query may include a '## Session State' JSON block from the previous conversation turn.\n"
        "\n"
        "⚠️  CRITICAL — distinguish fresh search from follow-up action:\n"
        "- FRESH SEARCH: if the user asks to FIND or SEARCH for files (e.g. 'Are there any X files?',\n"
        "  'Find all Y', 'Search for Z', 'How many X?', 'Do I have any X?'), IGNORE last_found_paths /\n"
        "  last_found_folder completely and run the search fresh using the appropriate search tools.\n"
        "- FOLLOW-UP ACTION: if the user refers to previously found files using pronouns ('them',\n"
        "  'those', 'copy them', 'send them', 'zip those', 'the files you found'), THEN use session state.\n"
        "\n"
        "- 'last_found_paths': a list of file paths the user found in the previous search (may be hundreds of paths).\n"
        "  ONLY use this when the user is performing a follow-up action on those files (pronouns like 'them', 'those').\n"
        "  When the user says 'copy them', 'put them in a folder', 'collect them', 'move them' etc.:\n"
        "  ⛔ NEVER ask the user for a destination folder. NEVER say 'please provide a path' or 'where should I copy'.\n"
        "     If no destination is mentioned, SILENTLY use the default OctaMind folder without asking.\n"
        "  PREFERRED: call collect_files_from_manifest(destination=<user_folder_if_named>).\n"
        "  • If user said 'copy to qwerty in Downloads', pass destination=str(downloads / 'qwerty').\n"
        "  • ONLY omit destination if user did NOT name one — it defaults to <workspace>/data/.\n"
        "  FALLBACK: use collect_files_to_folder(file_paths={__session__.last_found_paths}, destination=...)\n"
        "  The token {__session__.last_found_paths} will be automatically resolved to the actual Python list.\n"
        "  NEVER use copy_file(source=last_found_folder, destination=...) — that copies the ENTIRE folder.\n"
        "- 'last_found_folder': the parent folder of those files. Use it ONLY when the user explicitly asks to copy/zip the whole folder.\n"
        "- 'last_found_file_path': the single most-recently found file. Use it for single-file operations.\n"
        "\n"
        "## CONTEXT MANIFEST (cross-turn awareness)\n"
        "After every search_by_name or search_by_extension call, a context manifest is automatically written.\n"
        "You may also call save_context(topic=\"file_search\", resolved_entities={\"listed_files\":[...], \"query\":\"...\"}, awaiting=\"file_action\")\n"
        "explicitly to capture results from other search tools.\n"
        "On the NEXT turn, if the user says 'copy them', 'move those', etc., check for injected context BEFORE asking.\n"
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
        collect_files_to_folder,
        save_search_manifest, collect_files_from_manifest,
        undo_last_file_operation,
        list_file_operations,
    )
    from src.files.features.search import (  # noqa: PLC0415
        search_by_name as _sbn, search_by_extension as _sbe,
        search_by_date,
        search_by_size, find_duplicates, find_empty_folders,
        search_file_all_drives,
    )
    from src.agent.manifest.context_manifest import (  # noqa: PLC0415
        auto_save_files_context, make_save_context_tool,
    )

    def search_by_name(query: str, directory: str = "~", recursive: bool = True, limit: int = 50):
        result = _sbn(query, directory, recursive, limit)
        return auto_save_files_context(result, query)

    def search_by_extension(ext: str, directory: str = "~", recursive: bool = True, limit: int = 100):
        result = _sbe(ext, directory, recursive, limit)
        return auto_save_files_context(result, ext)
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
        "cleanup_app_caches":        cleanup_app_caches,
        "archive_old_files":         archive_old_files,
        "resolve_shortcut":          resolve_shortcut,
        "get_file_hash":             get_file_hash,
        "list_running_apps":         list_running_apps,
        "collect_files_to_folder":    collect_files_to_folder,
        "save_search_manifest":        save_search_manifest,
        "collect_files_from_manifest": collect_files_from_manifest,
        "undo_last_file_operation":    undo_last_file_operation,
        "list_file_operations":         list_file_operations,
        # ── Context Manifest ───────────────────────────────────────────────
        "save_context":                 make_save_context_tool("files"),
    }


def _maybe_save_manifest(artifacts_out: Optional[Dict[str, Any]]) -> None:
    """Save found_paths to the manifest file if the current execution produced any."""
    if not artifacts_out:
        return
    found = artifacts_out.get("found_paths", [])
    if not found:
        return
    try:
        from src.files.features.file_ops import save_search_manifest  # noqa: PLC0415
        save_search_manifest(found)
        import logging as _lg
        _lg.getLogger("files.orchestrator").info(
            "[manifest] saved %d paths to octa_manifest.txt", len(found)
        )
    except Exception as exc:
        import logging as _lg
        _lg.getLogger("files.orchestrator").warning("[manifest] save failed: %s", exc)


# ---------------------------------------------------------------------------
# Pre-flight: direct copy-from-manifest (no LLM needed)
# ---------------------------------------------------------------------------

_FOLLOW_UP_COPY_RE = re.compile(
    # action word followed by file/image/pronoun reference within ~100 chars
    r'\b(copy|move|put|collect|gather|transfer)\b'
    r'.{0,100}'
    r'\b(them|those|it|files?|images?|photos?|videos?|documents?|results?|found)\b'
    # pronoun first, action word second
    r'|\b(them|those)\b.{0,50}\b(copy|move|put|collect|gather|transfer)\b'
    # direct: "copy them", "collect those", "put it"
    r'|\b(copy|move|put|collect)\s+(them|those|it)\b'
    # common user phrases
    r'|\bcan you copy\b'
    # action + previously/found/searched — catches DAG-rewritten instructions
    r'|\b(copy|move|collect|gather)\b.{0,40}\b(previously|found|searched|earlier)\b',
    re.IGNORECASE | re.DOTALL,
)


def _is_follow_up_copy(query: str) -> bool:
    """Return True when the query looks like 'copy them / put those / collect the files'."""
    return bool(_FOLLOW_UP_COPY_RE.search(query))


def _try_direct_copy_from_manifest(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Bypass the LLM entirely when:
      1. The query is a follow-up copy/move/collect request, AND
      2. The manifest file (octa_manifest.txt) exists and is non-empty.

    Returns a result dict on success/failure, or None if conditions are not met
    (so the caller falls through to the normal LLM path).
    """
    if not _is_follow_up_copy(user_query):
        return None

    from src.files.features.file_ops import (
        collect_files_from_manifest,  # noqa: PLC0415
        _DEFAULT_MANIFEST,
        _DEFAULT_OCTAMIND_DIR,
    )

    if not _DEFAULT_MANIFEST.exists():
        import logging as _lg
        _lg.getLogger("files.orchestrator").info(
            "[direct-copy] manifest not found — falling through to LLM"
        )
        return None

    # Check if the user asked for a specific destination
    import logging as _lg
    _lg.getLogger("files.orchestrator").info(
        "[direct-copy] follow-up copy detected + manifest exists — executing directly"
    )

    # Look for an explicit destination in the query (e.g. "copy them to C:\Foo" or "in Downloads")
    destination = ""
    dest_match = re.search(
        r'\bto\b\s+([A-Za-z]:\\[^\s,\.]+|[\w\s]+(?:folder|directory)?)',
        user_query, re.IGNORECASE,
    )
    if dest_match:
        raw_dest = dest_match.group(1).strip()
        # Only use if it looks like an absolute path or a known folder keyword
        if raw_dest.startswith(("C:\\", "D:\\", "E:\\", "~/", "/")):
            destination = raw_dest
        elif raw_dest.lower() in ("downloads", "desktop", "documents", "home"):
            mapping = {
                "downloads": str(Path.home() / "Downloads"),
                "desktop":   str(Path.home() / "Desktop"),
                "documents": str(Path.home() / "Documents"),
                "home":      str(Path.home()),
            }
            destination = mapping.get(raw_dest.lower(), "")

    result = collect_files_from_manifest(destination=destination)

    if artifacts_out is not None:
        artifacts_out["file_path"] = result.get("destination", "")

    count = result.get("copied_count", 0)
    dest  = result.get("destination", str(_DEFAULT_OCTAMIND_DIR))
    skipped = result.get("skipped", [])
    skipped_note = f"  ({len(skipped)} file(s) skipped — not found on disk)" if skipped else ""

    if result.get("status") == "success":
        message = (
            f"✅ Copied **{count}** file(s) from the previous search into:\n"
            f"`{dest}`{skipped_note}"
        )
    else:
        message = f"❌ Copy failed: {result.get('message', 'unknown error')}"

    return {
        "status":  result.get("status", "error"),
        "message": message,
        "action":  "react_response",
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
    # ── Pre-flight: copy-from-manifest bypass (no LLM needed) ────────────
    direct = _try_direct_copy_from_manifest(user_query, artifacts_out)
    if direct is not None:
        return direct

    skill_context = _build_skill_context()  # dynamic — includes real OS paths
    tool_map = _get_tools()
    try:
        result = run_skill_dag(
            skill_name="files",
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
        _maybe_save_manifest(artifacts_out)  # safety net — DAG engine already tries this
        return result
    except Exception as dag_exc:
        import logging as _logging
        _logging.getLogger("files.orchestrator").warning(
            "DAG path raised %s — falling back to ReAct", dag_exc
        )
    try:
        result = run_skill_react(
            skill_name="files",
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
        _maybe_save_manifest(artifacts_out)  # ReAct engine does NOT auto-save manifest
        return result
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Files skill error: {exc}",
            "action": "react_response",
        }
