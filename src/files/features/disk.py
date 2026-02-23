"""
Disk and drive analytics tools for the Files Agent.

No external dependencies — all stdlib (shutil, os, pathlib).
"""
from __future__ import annotations

import logging
import os
import platform
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from ..files_service import resolve_path, _fmt_size

logger = logging.getLogger("files_agent")


def list_drives() -> Dict[str, Any]:
    """
    List all available drives / mount points with free/used/total space.
    Windows: returns lettered drives (C:, D:, ...).
    macOS/Linux: returns mounted filesystems.
    """
    try:
        import shutil
        drives = []
        system = platform.system()

        if system == "Windows":
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        total, used, free = shutil.disk_usage(drive)
                        drives.append({
                            "drive": drive,
                            "total": _fmt_size(total),
                            "used": _fmt_size(used),
                            "free": _fmt_size(free),
                            "used_pct": f"{used / max(total, 1) * 100:.1f}%",
                        })
                    except Exception:
                        drives.append({"drive": drive, "error": "cannot read"})
        else:
            # macOS / Linux — use df-style output
            for part in _get_partitions():
                try:
                    total, used, free = shutil.disk_usage(part)
                    drives.append({
                        "drive": part,
                        "total": _fmt_size(total),
                        "used": _fmt_size(used),
                        "free": _fmt_size(free),
                        "used_pct": f"{used / max(total, 1) * 100:.1f}%",
                    })
                except Exception:
                    pass

        return {"status": "success", "drives": drives}
    except Exception as exc:
        logger.error("list_drives failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def _get_partitions() -> List[str]:
    """Return a list of mount points on macOS / Linux."""
    try:
        import psutil  # type: ignore
        return [p.mountpoint for p in psutil.disk_partitions()]
    except ImportError:
        return ["/"]


def get_disk_usage(path: str = "C:/") -> Dict[str, Any]:
    """
    Return free / used / total space for a specific drive or path.

    Args:
        path: Drive letter (e.g. 'C:/') or any directory path.
    """
    try:
        import shutil
        p = resolve_path(path)
        total, used, free = shutil.disk_usage(str(p))
        return {
            "status": "success",
            "path": str(p),
            "total": _fmt_size(total),
            "used": _fmt_size(used),
            "free": _fmt_size(free),
            "used_pct": f"{used / max(total, 1) * 100:.1f}%",
        }
    except Exception as exc:
        logger.error("get_disk_usage failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_directory_size(path: str) -> Dict[str, Any]:
    """
    Calculate the total size of a folder (including all nested contents).

    Args:
        path: Directory to measure.
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"Path does not exist: {p}"}

        total = 0
        file_count = 0
        for child in p.rglob("*"):
            if child.is_file():
                try:
                    total += child.stat().st_size
                    file_count += 1
                except OSError:
                    pass

        return {
            "status": "success",
            "path": str(p),
            "total_size": _fmt_size(total),
            "total_bytes": total,
            "file_count": file_count,
        }
    except Exception as exc:
        logger.error("get_directory_size failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def find_large_files(
    directory: str,
    min_mb: float = 100,
    limit: int = 20,
    recursive: bool = True,
) -> Dict[str, Any]:
    """
    Find the largest files in a directory.

    Args:
        directory: Directory to scan.
        min_mb:    Only include files larger than this size in MB. Default 100.
        limit:     Number of results to return. Default 20.
        recursive: Scan subdirectories.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        min_bytes = int(min_mb * 1024 * 1024)
        results = []
        iterator = root.rglob("*") if recursive else root.glob("*")
        for p in iterator:
            if p.is_file():
                try:
                    sz = p.stat().st_size
                    if sz >= min_bytes:
                        results.append({
                            "name": p.name,
                            "path": str(p),
                            "size": _fmt_size(sz),
                            "size_bytes": sz,
                        })
                except OSError:
                    pass

        results.sort(key=lambda x: x["size_bytes"], reverse=True)
        return {
            "status": "success",
            "directory": str(root),
            "min_mb": min_mb,
            "count": len(results),
            "results": results[:limit],
        }
    except Exception as exc:
        logger.error("find_large_files failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_recently_modified(
    directory: str,
    days: int = 7,
    limit: int = 30,
    recursive: bool = True,
) -> Dict[str, Any]:
    """
    List files modified in the last N days, newest first.

    Args:
        directory: Directory to scan.
        days:      How many days back to look. Default 7.
        limit:     Maximum results. Default 30.
        recursive: Scan subdirectories.
    """
    try:
        root = resolve_path(directory)
        if not root.exists():
            return {"status": "error", "message": f"Directory does not exist: {root}"}

        cutoff = datetime.now() - timedelta(days=days)
        results = []
        iterator = root.rglob("*") if recursive else root.glob("*")
        for p in iterator:
            if p.is_file():
                try:
                    mtime = datetime.fromtimestamp(p.stat().st_mtime)
                    if mtime >= cutoff:
                        results.append({
                            "name": p.name,
                            "path": str(p),
                            "modified": mtime.isoformat(),
                            "size": _fmt_size(p.stat().st_size),
                        })
                except OSError:
                    pass

        results.sort(key=lambda x: x["modified"], reverse=True)
        return {
            "status": "success",
            "directory": str(root),
            "days": days,
            "count": len(results),
            "results": results[:limit],
        }
    except Exception as exc:
        logger.error("get_recently_modified failed: %s", exc)
        return {"status": "error", "message": str(exc)}
