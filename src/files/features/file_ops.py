"""
Core file and folder CRUD operations for the Files Agent.

All functions return {"status": "success"|"error", ...} so the orchestrator
can report errors consistently.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Any, Dict, List

from ..files_service import resolve_path, _file_dict, _is_safe_path, send_to_recycle_bin

logger = logging.getLogger("files_agent")


def list_directory(path: str, show_hidden: bool = False, limit: int = 200) -> Dict[str, Any]:
    """
    List files and subfolders at *path*.

    Args:
        path:        Directory to list. Accepts ~ and env vars.
        show_hidden: Include files/folders starting with '.' or hidden attribute (Windows).
        limit:       Maximum number of entries to return.
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"Path does not exist: {p}"}
        if not p.is_dir():
            return {"status": "error", "message": f"Not a directory: {p}"}

        entries = []
        for child in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if not show_hidden and child.name.startswith("."):
                continue
            entries.append(_file_dict(child))
            if len(entries) >= limit:
                break

        folders = [e for e in entries if e["type"] == "folder"]
        files   = [e for e in entries if e["type"] == "file"]
        return {
            "status": "success",
            "path": str(p),
            "total_entries": len(entries),
            "folders": len(folders),
            "files": len(files),
            "entries": entries,
        }
    except PermissionError:
        return {"status": "error", "message": f"Permission denied: {path}"}
    except Exception as exc:
        logger.error("list_directory failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def get_file_info(path: str) -> Dict[str, Any]:
    """
    Get detailed metadata for a file or folder.

    Args:
        path: Path to the file or folder.
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"Path does not exist: {p}"}
        info = _file_dict(p, include_hash=p.is_file())
        info["status"] = "success"
        info["absolute_path"] = str(p.resolve())
        info["parent"] = str(p.parent)
        return info
    except Exception as exc:
        logger.error("get_file_info failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def copy_file(source: str, destination: str) -> Dict[str, Any]:
    """
    Copy a file or folder tree from *source* to *destination*.

    Args:
        source:      Path to copy from.
        destination: Path to copy to. If destination is a directory, the source
                     is copied inside it.
    """
    try:
        src = resolve_path(source)
        dst = resolve_path(destination)
        if not src.exists():
            return {"status": "error", "message": f"Source does not exist: {src}"}
        if src.is_dir():
            out = shutil.copytree(src, dst / src.name if dst.is_dir() else dst)
        else:
            out = shutil.copy2(src, dst)
        return {"status": "success", "message": f"Copied to {out}", "destination": str(out)}
    except Exception as exc:
        logger.error("copy_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def move_file(source: str, destination: str) -> Dict[str, Any]:
    """
    Move or rename a file or folder.

    Args:
        source:      Path to move from.
        destination: New path (or destination directory).
    """
    try:
        src = resolve_path(source)
        dst = resolve_path(destination)
        if not src.exists():
            return {"status": "error", "message": f"Source does not exist: {src}"}
        if not _is_safe_path(src):
            return {"status": "error", "message": "Cannot move from a protected system path."}
        out = shutil.move(str(src), str(dst))
        return {"status": "success", "message": f"Moved to {out}", "destination": str(out)}
    except Exception as exc:
        logger.error("move_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def delete_file(path: str, permanent: bool = False) -> Dict[str, Any]:
    """
    Delete a file or folder.

    Args:
        path:      Path to delete.
        permanent: If True, bypass Recycle Bin. Default False (safer).
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"Path does not exist: {p}"}
        if not _is_safe_path(p):
            return {"status": "error", "message": "Cannot delete a protected system path."}
        if permanent:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            msg = f"Permanently deleted: {p}"
        else:
            send_to_recycle_bin(p)
            msg = f"Moved to Recycle Bin: {p}"
        return {"status": "success", "message": msg}
    except Exception as exc:
        logger.error("delete_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def create_folder(path: str) -> Dict[str, Any]:
    """
    Create a directory and any missing parent directories.

    Args:
        path: Full path of the new folder to create.
    """
    try:
        p = resolve_path(path)
        if p.exists():
            return {"status": "success", "message": f"Folder already exists: {p}", "path": str(p)}
        p.mkdir(parents=True, exist_ok=True)
        return {"status": "success", "message": f"Created folder: {p}", "path": str(p)}
    except Exception as exc:
        logger.error("create_folder failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def rename_file(path: str, new_name: str) -> Dict[str, Any]:
    """
    Rename a file or folder (keeping it in the same directory).

    Args:
        path:     Current path of the file or folder.
        new_name: New name only (not a full path).
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"Path does not exist: {p}"}
        new_path = p.parent / new_name
        if new_path.exists():
            return {"status": "error", "message": f"Destination already exists: {new_path}"}
        p.rename(new_path)
        return {"status": "success", "message": f"Renamed to {new_path.name}", "new_path": str(new_path)}
    except Exception as exc:
        logger.error("rename_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def open_file(path: str) -> Dict[str, Any]:
    """
    Open a file with its default application (Windows: os.startfile, others: xdg-open/open).

    Args:
        path: Path to the file to open.
    """
    try:
        p = resolve_path(path)
        if not p.exists():
            return {"status": "error", "message": f"File does not exist: {p}"}
        if not p.is_file():
            return {"status": "error", "message": f"Not a file: {p}"}
        system = platform.system()
        if system == "Windows":
            os.startfile(str(p))
        elif system == "Darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"status": "success", "message": f"Opened {p.name} with default application"}
    except Exception as exc:
        logger.error("open_file failed: %s", exc)
        return {"status": "error", "message": str(exc)}
