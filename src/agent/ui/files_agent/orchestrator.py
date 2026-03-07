"""
Local Files skill orchestrator.

Key corrections vs. older version:
- search_by_name first argument is ``query`` (not ``pattern``).
- _build_skill_context() is dynamic so the LLM receives the real
  system paths (home / Downloads / Desktop / Documents) rather than
  guessing platform-specific placeholders.
- Tool documentation is loaded from skills.md with cosine-similarity
  selection for the ReAct engine (fewer tokens, more relevant tools).
  The DAG planner still sees the full tool list.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react
from src.agent.workflows.skill_dag_engine import run_skill_dag

def _build_skill_context() -> str:
    """Build the files-agent system prompt with real OS paths injected from skill_context.md."""
    import sys as _sys
    home = Path.home()
    downloads = home / "Downloads"
    desktop   = home / "Desktop"
    documents = home / "Documents"
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

    # Load user-defined personal folders from settings.json
    personal_folders_note = ""
    try:
        import json as _json
        _sf = Path(__file__).resolve().parents[4] / "config" / "settings.json"
        _cfg = _json.loads(_sf.read_text(encoding="utf-8"))
        _pf = {k: v for k, v in _cfg.get("personal_folders", {}).items() if not k.startswith("_")}
        if _pf:
            _lines = "\n".join(f"  {k}: {v}" for k, v in _pf.items())
            personal_folders_note = (
                "\nUser-defined personal folders (use these EXACT paths \u2014 do NOT search):\n"
                + _lines + "\n"
                "  Rule: when the user mentions one of these exact names (e.g. 'payslips', 'neo'),"
                " call list_directory(<exact path>) DIRECTLY \u2014 never use search_file_all_drives for a known folder.  \n"
            )
    except Exception:
        pass

    # Load template and substitute placeholders.
    # Longer/more-specific keys are replaced before any shorter key that is a prefix,
    # so "${downloads_example_subfolder}" is handled before "${downloads}".
    template = (Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8")
    replacements = {
        "${downloads_example_subfolder}": str(downloads / "MyFolder"),
        "${desktop_example_file}": str(desktop / "report.pdf"),
        "${home}": str(home),
        "${downloads}": str(downloads),
        "${desktop}": str(desktop),
        "${documents}": str(documents),
        "${data_dir}": str(data_dir),
        "${drive_root_note}": drive_root_note,
        "${personal_folders_note}": personal_folders_note,
    }
    for k, v in replacements.items():
        template = template.replace(k, v)
    return template.strip()

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

def _resolve_destination_from_query(user_query: str) -> str:
    """
    Extract and resolve a destination folder name from a natural-language query.

    Handles (in priority order):
      1. Absolute Windows/Unix path: "copy to C:\\Users\\..."
      2. Named folder: "a folder named/called X" or "folder named/called X"
      3. Sub-path under a known keyword: "to Downloads/X", "to Desktop\\X"
      4. Known keyword standalone: "to downloads", "to desktop", "to documents"
      5. Sub-path under Downloads "<keyword>/X" within a 'to' clause
      6. Simple single-word name at end of query: "copy to qwerty", "put in test"

    Returns the resolved absolute path string, or "" if nothing parseable is found.
    """
    home = Path.home()
    downloads = home / "Downloads"
    _KW: Dict[str, Path] = {
        "downloads": home / "Downloads",
        "download":  home / "Downloads",
        "desktop":   home / "Desktop",
        "documents": home / "Documents",
        "document":  home / "Documents",
        "home":      home,
    }
    # Stopwords that are never folder names
    _STOP = frozenset({
        "them", "those", "it", "the", "a", "an", "my", "our", "your",
        "all", "folder", "folders", "directory", "file", "files",
        "here", "there", "this", "that",
    })

    # 1. Absolute path after "to" (Windows drive letter or Unix root)
    abs_m = re.search(
        r'\bto\s+([A-Za-z]:[/\\][^\s,]+|/[^\s,]+)',
        user_query, re.IGNORECASE,
    )
    if abs_m:
        return abs_m.group(1).strip().rstrip("/\\")

    # 2. "a folder named/called X" / "folder named/called X" / "named/called X folder"
    named_m = re.search(
        r'\b(?:a\s+)?(?:new\s+)?folder\s+(?:named|called)\s+["\']?(\w[\w\-\.]*)["\']?'
        r'|(?:named|called)\s+["\']?(\w[\w\-\.]*)["\']?\s*(?:folder|directory)?',
        user_query, re.IGNORECASE,
    )
    if named_m:
        name = (named_m.group(1) or named_m.group(2) or "").strip()
        if name and name.lower() not in _STOP:
            return str(downloads / name)

    # 3. Known keyword + sub-folder: "to Downloads/qwerty", "to Desktop\test"
    sub_m = re.search(
        r'\bto\s+(downloads?|desktop|documents?|home)[/\\](\w[\w\-\.]*)',
        user_query, re.IGNORECASE,
    )
    if sub_m:
        base = _KW.get(sub_m.group(1).lower().rstrip("s"), _KW.get(sub_m.group(1).lower(), downloads))
        return str(base / sub_m.group(2))

    # 4. Standalone known keyword: "to downloads", "to desktop"
    kw_m = re.search(
        r'\bto\s+(downloads?|desktop|documents?|home)\b',
        user_query, re.IGNORECASE,
    )
    if kw_m:
        kw = kw_m.group(1).lower().rstrip("s")
        return str(_KW.get(kw, _KW.get(kw_m.group(1).lower(), downloads)))

    # 5. "in Downloads/X" or "in Desktop/X"
    in_sub_m = re.search(
        r'\bin\s+(downloads?|desktop|documents?|home)[/\\](\w[\w\-\.]*)',
        user_query, re.IGNORECASE,
    )
    if in_sub_m:
        base = _KW.get(in_sub_m.group(1).lower().rstrip("s"), _KW.get(in_sub_m.group(1).lower(), downloads))
        return str(base / in_sub_m.group(2))

    # 6. "to X" or "into X" where X is a simple identifier at/near end of query
    simple_m = re.search(
        r'\b(?:to|into)\s+(?:a\s+)?(?:new\s+)?(?:folder\s+)?(?:named\s+|called\s+)?([A-Za-z]\w*)\s*[?!.]?\s*$',
        user_query.strip(), re.IGNORECASE,
    )
    if simple_m:
        name = simple_m.group(1).strip()
        if name.lower() not in _STOP:
            return str(downloads / name)

    # 7. "put/place them in X" where X is a simple name at end
    in_m = re.search(
        r'\b(?:put|place|store|save)\b.{0,40}\bin\s+(?:a\s+)?(?:new\s+)?(?:folder\s+)?(?:named\s+|called\s+)?([A-Za-z]\w*)\s*[?!.]?\s*$',
        user_query.strip(), re.IGNORECASE,
    )
    if in_m:
        name = in_m.group(1).strip()
        if name.lower() not in _STOP:
            return str(downloads / name)

    # 8. "to this folder - X" / "folder - X" — dash used as a name separator
    #    e.g. "copy them to this folder - payslips_01"
    folder_dash_m = re.search(
        r'\bfolder\s*[-–]\s*([A-Za-z]\w*)',
        user_query, re.IGNORECASE,
    )
    if folder_dash_m:
        name = folder_dash_m.group(1).strip()
        if name and name.lower() not in _STOP:
            return str(downloads / name)

    return ""

# Fresh-search patterns — these ALWAYS bypass the direct-copy shortcut,
# regardless of injected context or session state.
_FRESH_SEARCH_RE = re.compile(
    r'\b(how many|are there|do i have|find all|search for|count|list all|'
    r'how much|any \w+ files?|search.*computer|look for|show me all)\b',
    re.IGNORECASE,
)

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
    # Extract the raw user intent — strip injected ## Context and ## Session State
    # blocks so we never accidentally trigger a copy on fresh search queries whose
    # injected 'file_action' instruction contains "collect" / "copy" + "files".
    _raw = user_query.split("## Context from Previous Turn")[0]
    _raw = _raw.split("## Session State")[0].strip()

    # Explicit guard: fresh search queries must NEVER be treated as copy follow-ups.
    if _FRESH_SEARCH_RE.search(_raw):
        return None

    if not _is_follow_up_copy(_raw):
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

    import logging as _lg
    _lg.getLogger("files.orchestrator").info(
        "[direct-copy] follow-up copy detected + manifest exists — executing directly"
    )

    # Resolve destination using the cleaned raw intent (no injected ## blocks)
    destination = _resolve_destination_from_query(_raw)
    _lg.getLogger("files.orchestrator").info(
        "[direct-copy] resolved destination=%r from query=%r", destination, _raw
    )

    # If we can't determine where the user wants the files, fall through to the LLM
    # rather than silently dumping everything into the default data directory.
    if not destination:
        _lg.getLogger("files.orchestrator").info(
            "[direct-copy] destination unresolvable — falling through to LLM"
        )
        return None

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
        # Clear the file_action context — the action is complete; the next
        # turn should not re-trigger the same copy.
        try:
            from src.agent.manifest.context_manifest import clear_context as _cc  # noqa: PLC0415
            _cc()
        except Exception:
            pass
    else:
        message = f"❌ Copy failed: {result.get('message', 'unknown error')}"

    return {
        "status":  result.get("status", "error"),
        "message": message,
        "action":  "react_response",
    }

# ---------------------------------------------------------------------------
# Background job dispatch — heavy full-disk scans
# ---------------------------------------------------------------------------

# Queries that imply scanning the entire computer / all drives
_HEAVY_SCAN_RE = re.compile(
    r'\b('
    r'on\s+my\s+(computer|laptop|machine|pc)\b'          # "on my computer"
    r'|across\s+(all|my|the)\s+drives?\b'                # "across all drives"
    r'|search\s+all\s+drives?\b'                         # "search all drives"
    r'|on\s+all\s+drives?\b'                             # "on all drives"
    r'|entire\s+(computer|laptop|machine|disk|system)\b' # "entire computer"
    r'|full\s+(disk|system|computer|laptop)\s+scan\b'    # "full disk scan"
    r'|all\s+drives?\s+and\b'                            # "all drives and..."
    r')',
    re.IGNORECASE,
)

# Queries that narrow the scope to a specific folder (exempt from background)
_SCOPED_DIR_RE = re.compile(
    r'\b(in\s+(downloads?|desktop|documents?|pictures?|videos?|music)\b'
    r'|in\s+["\'][\w\s]+["\']'        # in "folder name"
    r'|under\s+[A-Za-z]:\\'           # under C:\
    r'|inside\s+\w+'                  # inside SomeFolder
    r')',
    re.IGNORECASE,
)

def _is_heavy_scan(query: str) -> bool:
    """
    Return True when the query requires an unscoped full-disk scan that
    would block the chat for potentially minutes.
    """
    if not _HEAVY_SCAN_RE.search(query):
        return False
    # Scoped queries ("on my computer in Downloads") are still fast enough
    if _SCOPED_DIR_RE.search(query):
        return False
    return True

def _try_background_job(
    user_query: str,
    artifacts_out: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    If the query is a heavy full-disk scan, dispatch it to a background job
    and return an immediate acknowledgement message.

    Returns a result dict (immediate response) on dispatch, or None to fall
    through to normal synchronous LLM execution.
    """
    if not _is_heavy_scan(user_query):
        return None

    session_id = (artifacts_out or {}).get("_session_id", "")
    pa_id      = (artifacts_out or {}).get("_pa_id", "")

    # Fallback: read PA_ID from the process environment (set by Telegram poller)
    if not pa_id:
        import os as _os
        pa_id = _os.environ.get("PA_ID", "")

    try:
        from src.agent.manifest.job_manifest import create_job, update_job  # noqa: PLC0415
        from src.agent.manifest.job_runner import submit_job                 # noqa: PLC0415
    except Exception as exc:
        import logging as _lg
        _lg.getLogger("files.orchestrator").warning(
            "[bg-scan] job manifest/runner unavailable (%s) — running synchronously", exc
        )
        return None  # fall through to synchronous execution

    job_id = create_job(
        agent="files",
        description=user_query[:120],
        session_id=session_id,
        pa_id=pa_id,
        params={"query": user_query},
    )

    # Strip any injected '## Session State' block from the query so the plain
    # natural-language question is stored cleanly in the closure.
    _clean_marker = "## Session State"
    _raw_query = user_query.split(_clean_marker)[0].strip()

    # Capture references for the closure
    _job_id = job_id

    # ------------------------------------------------------------------
    # Classify query type so _do_scan can search directly without LLM.
    # ------------------------------------------------------------------
    _lower = _raw_query.lower()
    _EXT_MAP = {
        "image":    ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp", "svg", "ico"],
        "video":    ["mp4", "avi", "mov", "mkv", "wmv", "flv", "webm"],
        "audio":    ["mp3", "wav", "flac", "aac", "m4a", "ogg", "wma"],
        "document": ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt"],
        "pdf":      ["pdf"],
    }
    _type_label: Optional[str] = None
    _scan_exts: Optional[list] = None
    if any(w in _lower for w in ("image", "photo", "picture", "screenshot", "jpg", "png")):
        _type_label, _scan_exts = "image", _EXT_MAP["image"]
    elif any(w in _lower for w in ("video", "film", "movie", "recording", "mp4", "mkv")):
        _type_label, _scan_exts = "video", _EXT_MAP["video"]
    elif any(w in _lower for w in ("audio", "music", "song", "mp3", "wav")):
        _type_label, _scan_exts = "audio", _EXT_MAP["audio"]
    elif "pdf" in _lower and not any(w in _lower for w in ("document", "word", "excel")):
        _type_label, _scan_exts = "PDF", _EXT_MAP["pdf"]
    elif any(w in _lower for w in ("document", "doc", "word", "excel", "spreadsheet", "office")):
        _type_label, _scan_exts = "document", _EXT_MAP["document"]

    def _do_scan() -> str:
        """
        Direct Python search — no LLM, no iteration limits.

        For extension-based queries (images, videos, PDFs…) we call
        search_by_extension() directly for each relevant extension.
        For unrecognised queries we fall back to the DAG/ReAct engine
        with the clean (Session-State-free) query.
        """
        import sys as _sys
        import string as _string
        from src.files.features.search import search_by_extension as _sbe  # noqa: PLC0415
        from src.files.features.file_ops import save_search_manifest as _ssm  # noqa: PLC0415

        if _scan_exts:
            # ── Direct extension search (no LLM) ─────────────────────────────
            all_paths: list = []
            home = Path.home()
            total = len(_scan_exts)

            # Build list of directories to search:
            # 1. Home directory (C:\Users\malus — covers most user files)
            # 2. C:\ root but ONLY non-system top-level folders
            #    (catches C:\Hrishikesh\, C:\Projects\, etc.)
            # 3. Any additional drive roots (D:\, E:\, …)
            search_roots: list = [str(home)]

            # Add non-home, non-system top-level C:\ folders
            try:
                c_root = Path("C:\\")
                if c_root.exists():
                    _skip = {"windows", "program files", "program files (x86)",
                              "programdata", "users", "recovery", "system volume information",
                              "$recycle.bin", "perflogs", "msocache"}
                    for child in c_root.iterdir():
                        if child.is_dir() and child.name.lower() not in _skip:
                            search_roots.append(str(child))
            except Exception:
                pass

            # Add other drive roots (D:\, E:\, …)
            if _sys.platform == "win32":
                try:
                    for d in _string.ascii_uppercase:
                        if d == "C":
                            continue
                        drive = Path(f"{d}:\\")
                        if drive.exists():
                            search_roots.append(str(drive))
                except Exception:
                    pass

            for i, ext in enumerate(_scan_exts):
                update_job(
                    _job_id, status="running",
                    progress_pct=int(5 + 85 * i / total),
                    progress_detail=f"Searching *.{ext} files ({i + 1}/{total})…",
                )
                for root_dir in search_roots:
                    try:
                        result = _sbe(ext, root_dir, True, 500)
                        for entry in result.get("results", []):
                            p = entry.get("path", "")
                            if p:
                                all_paths.append(p)
                    except Exception:
                        pass

            # Deduplicate preserving order
            seen: set = set()
            unique: list = []
            for p in all_paths:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)

            update_job(_job_id, status="running", progress_pct=95,
                       progress_detail="Saving results…")
            if unique:
                _ssm(unique)

            count = len(unique)
            # Build extension breakdown (top 5)
            ext_counts: dict = {}
            for p in unique:
                e = Path(p).suffix.lower().lstrip(".") or "other"
                ext_counts[e] = ext_counts.get(e, 0) + 1
            top = sorted(ext_counts.items(), key=lambda x: -x[1])[:5]
            breakdown = "  |  ".join(f".{e}: **{c}**" for e, c in top)

            if count == 0:
                return (f"✅ Scan complete — No {_type_label} files found on your computer.\n\n"
                        f"_(Searched: {', '.join('.' + x for x in _scan_exts)})_")
            s = "s" if count != 1 else ""
            lines = [
                f"✅ Scan complete — Found **{count} {_type_label} file{s}** on your computer.",
                "",
                f"📊 Breakdown: {breakdown}",
                "",
                "💡 Say *'copy them to Downloads'* to collect all found files.",
            ]
            return "\n".join(lines)

        else:
            # ── Fallback: LLM orchestration for non-extension queries ─────────
            # Use the clean query (no injected Session State) to avoid DAG
            # planning failures caused by non-JSON LLM responses.
            update_job(_job_id, status="running", progress_pct=5,
                       progress_detail="Starting analysis…")
            _skill_context = _build_skill_context()
            _tool_map      = _get_tools()
            _dag_docs = _get_tool_docs_for_dag()
            _react_docs = _get_tool_docs_for_react(_raw_query)
            try:
                res = run_skill_dag(
                    skill_name="files",
                    skill_context=_skill_context,
                    tool_map=_tool_map,
                    tool_docs=_dag_docs,
                    user_query=_raw_query,
                    artifacts_out={},
                )
            except Exception:
                res = run_skill_react(
                    skill_name="files",
                    skill_context=_skill_context,
                    tool_map=_tool_map,
                    tool_docs=_react_docs,
                    user_query=_raw_query,
                    artifacts_out={},
                )
            return res.get("message", "Scan complete.")

    submit_job(job_id, _do_scan, session_id=session_id, pa_id=pa_id)

    return {
        "status":  "success",
        "message": (
            f"⏳ I've started the search in the background *(Job `{job_id}`)*.\n\n"
            "This may take a few minutes for a full scan across all drives. "
            "I'll send you a message here as soon as the results are ready! 🔔"
        ),
        "action":  "react_response",
        "job_id":  job_id,
    }

def _get_tool_docs_for_dag() -> str:
    """Return full tool docs for the DAG planner (needs all tools to plan)."""
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415
    docs = get_all_tool_docs("files")
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("files.orchestrator").error(
            "[files-agent] skills.md returned no tools — check ui/files_agent/skills.md exists. "
            "DAG planning will fail without tool docs."
        )
    return docs

def _get_tool_docs_for_react(user_query: str) -> str:
    """Return filtered tool docs for the ReAct engine (cosine-similarity top-K)."""
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415
    docs = load_tool_docs(
        "files", user_query, top_k=15,
        always_include=["save_context", "deliver_file", "save_search_manifest"],
    )
    if not docs:
        import logging as _lg  # noqa: PLC0415
        _lg.getLogger("files.orchestrator").error(
            "[files-agent] FAISS returned no tool docs for query=%r — "
            "check ui/files_agent/skills.md", user_query[:60]
        )
    return docs

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

    # ── Background dispatch: heavy full-disk scans run async ──────────────
    try:
        bg = _try_background_job(user_query, artifacts_out)
        if bg is not None:
            return bg
    except Exception as _bg_exc:
        import logging as _bg_log
        _bg_log.getLogger("files.orchestrator").warning(
            "[bg-scan] background dispatch raised %s — running synchronously", _bg_exc
        )

    skill_context = _build_skill_context()  # dynamic — includes real OS paths
    tool_map = _get_tools()
    dag_tool_docs = _get_tool_docs_for_dag()
    try:
        result = run_skill_dag(
            skill_name="files",
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=dag_tool_docs,
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
    react_tool_docs = _get_tool_docs_for_react(user_query)
    try:
        result = run_skill_react(
            skill_name="files",
            skill_context=skill_context,
            tool_map=tool_map,
            tool_docs=react_tool_docs,
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
