"""
File search tools for the Files Agent.

Searches by name, extension, date range, size, duplicates, and empty folders.
All searches are recursive by default.
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..files_service import resolve_path, _file_dict, _fmt_size

logger = logging.getLogger("files_agent")

_MAX_RESULTS = 500  # hard cap to avoid scanning entire drives accidentally


def search_by_name(
    query: str,
    directory: str = "~",
    recursive: bool = True,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Search for files/folders whose name matches a glob pattern or substring.

    Args:
        query:     Glob pattern (e.g. '*.pdf', 'report*') or plain substring.
        directory: Root directory to search.
        recursive: Search subdirectories.
        limit:     Maximum results to return.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        # If no wildcard chars, treat as a contains match
        if not any(c in query for c in ("*", "?", "[")):
            pattern = f"*{query}*"
        else:
            pattern = query

        results = []
        iterator = root.rglob(pattern) if recursive else root.glob(pattern)
        for p in iterator:
            try:
                results.append(_file_dict(p))
            except Exception:
                pass
            if len(results) >= min(limit, _MAX_RESULTS):
                break

        # Sort: real files (non .lnk) first, then shortcuts — so callers get
        # actual documents in position 0 rather than Windows shortcut files.
        results.sort(key=lambda r: (1 if r.get("extension", "").lower() == ".lnk" else 0))

        return {
            "status": "success",
            "query": query,
            "directory": str(root),
            "count": len(results),
            "results": results,
        }
    except Exception as exc:
        logger.error("search_by_name failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def search_by_extension(
    ext: str,
    directory: str = "~",
    recursive: bool = True,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Find all files with a given extension.

    Args:
        ext:       Extension string, with or without the dot (e.g. 'pdf' or '.pdf').
        directory: Root directory to search.
        recursive: Search subdirectories.
        limit:     Maximum results.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        ext = ext.lower().lstrip(".")
        pattern = f"*.{ext}"

        results = []
        iterator = root.rglob(pattern) if recursive else root.glob(pattern)
        for p in iterator:
            if p.is_file():
                try:
                    results.append(_file_dict(p))
                except Exception:
                    pass
            if len(results) >= min(limit, _MAX_RESULTS):
                break

        total_size = sum(r.get("size_bytes", 0) for r in results)
        return {
            "status": "success",
            "extension": f".{ext}",
            "directory": str(root),
            "count": len(results),
            "total_size": _fmt_size(total_size),
            "results": results,
        }
    except Exception as exc:
        logger.error("search_by_extension failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def search_by_date(
    directory: str,
    after: str = "",
    before: str = "",
    recursive: bool = True,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Find files modified/created within a date range.

    Args:
        directory: Root directory to search.
        after:     ISO date string 'YYYY-MM-DD' or shorthand like 'last 7 days'.
        before:    ISO date string 'YYYY-MM-DD'. Defaults to now.
        recursive: Search subdirectories.
        limit:     Maximum results.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        # Parse date helpers
        after_dt: Optional[datetime] = None
        before_dt: Optional[datetime] = datetime.now()

        if after:
            after_lower = after.lower().strip()
            if "last" in after_lower and "day" in after_lower:
                try:
                    days = int("".join(filter(str.isdigit, after_lower)) or "7")
                    after_dt = datetime.now() - timedelta(days=days)
                except ValueError:
                    after_dt = datetime.now() - timedelta(days=7)
            elif "last" in after_lower and "week" in after_lower:
                after_dt = datetime.now() - timedelta(weeks=1)
            elif "last" in after_lower and "month" in after_lower:
                after_dt = datetime.now() - timedelta(days=30)
            elif "today" in after_lower:
                after_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                try:
                    after_dt = datetime.fromisoformat(after)
                except ValueError:
                    return {"status": "error", "message": f"Cannot parse date: {after}. Use YYYY-MM-DD format."}

        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except ValueError:
                return {"status": "error", "message": f"Cannot parse date: {before}. Use YYYY-MM-DD format."}

        results = []
        iterator = root.rglob("*") if recursive else root.glob("*")
        for p in iterator:
            if not p.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
                if after_dt and mtime < after_dt:
                    continue
                if before_dt and mtime > before_dt:
                    continue
                results.append(_file_dict(p))
            except Exception:
                pass
            if len(results) >= min(limit, _MAX_RESULTS):
                break

        results.sort(key=lambda x: x.get("modified", ""), reverse=True)
        return {
            "status": "success",
            "directory": str(root),
            "after": after_dt.isoformat() if after_dt else None,
            "before": before_dt.isoformat() if before_dt else None,
            "count": len(results),
            "results": results,
        }
    except Exception as exc:
        logger.error("search_by_date failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def search_by_size(
    directory: str,
    min_mb: float = 0,
    max_mb: float = 0,
    recursive: bool = True,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Find files within a size range.

    Args:
        directory: Root directory to search.
        min_mb:    Minimum file size in MB (0 = no minimum).
        max_mb:    Maximum file size in MB (0 = no maximum).
        recursive: Search subdirectories.
        limit:     Maximum results.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        min_bytes = int(min_mb * 1024 * 1024)
        max_bytes = int(max_mb * 1024 * 1024) if max_mb > 0 else None

        results = []
        iterator = root.rglob("*") if recursive else root.glob("*")
        for p in iterator:
            if not p.is_file():
                continue
            try:
                sz = p.stat().st_size
                if sz < min_bytes:
                    continue
                if max_bytes is not None and sz > max_bytes:
                    continue
                results.append(_file_dict(p))
            except Exception:
                pass
            if len(results) >= min(limit, _MAX_RESULTS):
                break

        results.sort(key=lambda x: x.get("size_bytes", 0), reverse=True)
        return {
            "status": "success",
            "directory": str(root),
            "min_mb": min_mb,
            "max_mb": max_mb if max_mb > 0 else "unlimited",
            "count": len(results),
            "results": results,
        }
    except Exception as exc:
        logger.error("search_by_size failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def find_duplicates(directory: str, recursive: bool = True) -> Dict[str, Any]:
    """
    Detect duplicate files by MD5 hash. Only compares files ≤ 200 MB.

    Args:
        directory: Directory to scan.
        recursive: Scan subdirectories.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        size_groups: dict = defaultdict(list)
        iterator = root.rglob("*") if recursive else root.glob("*")
        for p in iterator:
            if p.is_file():
                try:
                    sz = p.stat().st_size
                    if sz > 0:
                        size_groups[sz].append(p)
                except Exception:
                    pass

        hash_groups: dict = defaultdict(list)
        for paths in size_groups.values():
            if len(paths) < 2:
                continue
            for p in paths:
                if p.stat().st_size > 200 * 1024 * 1024:
                    continue
                try:
                    h = hashlib.md5(p.read_bytes()).hexdigest()
                    hash_groups[h].append(p)
                except Exception:
                    pass

        duplicates = []
        wasted = 0
        for h, paths in hash_groups.items():
            if len(paths) < 2:
                continue
            sz = paths[0].stat().st_size
            wasted += sz * (len(paths) - 1)
            duplicates.append({
                "hash": h,
                "count": len(paths),
                "size_each": _fmt_size(sz),
                "total_waste": _fmt_size(sz * (len(paths) - 1)),
                "files": [str(p) for p in paths],
            })

        from ..files_service import _fmt_size as fs
        return {
            "status": "success",
            "directory": str(root),
            "duplicate_groups": len(duplicates),
            "total_wasted_space": _fmt_size(wasted),
            "groups": duplicates,
        }
    except Exception as exc:
        logger.error("find_duplicates failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def find_empty_folders(directory: str, recursive: bool = True) -> Dict[str, Any]:
    """
    Locate folders that contain no files (may contain only empty sub-folders).

    Args:
        directory: Directory to scan.
        recursive: Scan subdirectories.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        empty = []
        iterator = root.rglob("*") if recursive else root.glob("*")
        for p in iterator:
            if p.is_dir():
                try:
                    if not any(True for _ in p.rglob("*") if _.is_file()):
                        empty.append(str(p))
                except Exception:
                    pass

        return {
            "status": "success",
            "directory": str(root),
            "count": len(empty),
            "empty_folders": empty,
        }
    except Exception as exc:
        logger.error("find_empty_folders failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def search_file_all_drives(
    query: str,
    extensions: Optional[List[str]] = None,
    limit: int = 20,
    include_folders: bool = True,
) -> Dict[str, Any]:
    """
    Search ALL drives and the full home-directory tree for files **and folders**
    matching *query*.

    Unlike ``search_by_name`` (which defaults to ``~`` only), this function
    discovers every mounted drive on Windows (C:, D:, …) or ``/`` on Unix and
    scans each one, making it suitable for finding files **or** folders anywhere
    on the laptop.

    Args:
        query:          Filename/folder glob pattern or plain substring.
        extensions:     Optional list of extensions to restrict (files only).
                        If omitted, all files AND folders are considered.
        limit:          Maximum number of results to return (default 20).
        include_folders: When True (default) also match directories whose name
                        fits the query.  Set to False to return files only.

    Returns a result dict with ``file_path`` set to the path of the first (best)
    match, so the caller can pass it directly to ``zip_folder``, ``deliver_file``
    or an email attachment without additional steps.
    """
    import platform
    import string as _string
    from pathlib import Path as _P

    try:
        # Build normalised glob / substring pattern
        if not any(c in query for c in ("*", "?", "[")):
            pattern = f"*{query}*"
        else:
            pattern = query

        ext_filter: Optional[set] = (
            {e.lstrip(".").lower() for e in extensions} if extensions else None
        )

        # Discover drives
        drives: List[_P] = []
        if platform.system() == "Windows":
            for letter in _string.ascii_uppercase:
                d = _P(f"{letter}:\\")
                try:
                    if d.exists():
                        drives.append(d)
                except Exception:
                    pass
        else:
            drives = [_P("/")]

        # Extensions to always skip — Windows shortcuts and cache/temp files
        _SKIP_EXTENSIONS = {".lnk", ".tmp", ".cache", ".lock", ".partial", ".crdownload"}

        results: List[Dict[str, Any]] = []

        for drive in drives:
            if len(results) >= limit:
                break
            try:
                for p in drive.rglob(pattern):
                    is_dir  = p.is_dir()
                    is_file = p.is_file()

                    if is_dir:
                        # Include matching directories when include_folders is True
                        # and no extension filter is active (extension filters are
                        # file-only concepts).
                        if not include_folders or ext_filter:
                            continue
                    elif is_file:
                        # Skip Windows shortcuts and cache files
                        if p.suffix.lower() in _SKIP_EXTENSIONS:
                            continue
                        if ext_filter and p.suffix.lstrip(".").lower() not in ext_filter:
                            continue
                    else:
                        continue  # symlink or special — skip

                    try:
                        stat = p.stat()
                        if is_dir:
                            results.append({
                                "name": p.name,
                                "path": str(p),
                                "type": "folder",
                                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                            })
                        else:
                            size_str = (
                                f"{stat.st_size / 1024:.1f} KB"
                                if stat.st_size < 1_048_576
                                else f"{stat.st_size / 1_048_576:.1f} MB"
                            )
                            results.append({
                                "name": p.name,
                                "path": str(p),
                                "type": "file",
                                "size": size_str,
                                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                            })
                    except Exception:
                        results.append({"name": p.name, "path": str(p), "type": "folder" if is_dir else "file"})
                    if len(results) >= limit:
                        break
            except (PermissionError, OSError):
                # Skip drives / dirs we can't access
                continue
            except Exception as exc:
                logger.debug("search_file_all_drives drive %s error: %s", drive, exc)

        best_path = results[0]["path"] if results else ""
        return {
            "status": "success",
            "query": query,
            "drives_searched": [str(d) for d in drives],
            "count": len(results),
            "results": results,
            # Set file_path to the first match so artifact collector picks it up
            # for Telegram/Dashboard download delivery automatically.
            "file_path": best_path,
            "message": (
                f"Found {len(results)} item(s) matching '{query}' across {len(drives)} drive(s)."
                if results
                else f"No files or folders found matching '{query}' on any drive."
            ),
        }
    except Exception as exc:
        logger.error("search_file_all_drives failed: %s", exc)
        return {"status": "error", "message": str(exc)}
