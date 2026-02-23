"""
Bulk file organisation tools for the Files Agent.

Destructive operations (delete, deduplicate) default to dry_run=True and
return a preview list. The user must pass dry_run=False to apply changes.
"""
from __future__ import annotations

import fnmatch
import logging
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..files_service import resolve_path, _file_dict, _fmt_size, _is_safe_path, send_to_recycle_bin

logger = logging.getLogger("files_agent")

# Extension → subfolder name map for organize_by_type
_EXT_MAP: Dict[str, str] = {
    # Images
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images",
    ".bmp": "Images", ".svg": "Images", ".webp": "Images", ".heic": "Images",
    ".tiff": "Images", ".tif": "Images", ".ico": "Images",
    # Videos
    ".mp4": "Videos", ".mov": "Videos", ".avi": "Videos", ".mkv": "Videos",
    ".wmv": "Videos", ".flv": "Videos", ".webm": "Videos", ".m4v": "Videos",
    # Audio
    ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio", ".aac": "Audio",
    ".ogg": "Audio", ".m4a": "Audio", ".wma": "Audio",
    # Documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".xls": "Documents", ".xlsx": "Documents", ".ppt": "Documents",
    ".pptx": "Documents", ".odt": "Documents", ".ods": "Documents",
    # Text / Code
    ".txt": "Text", ".md": "Text", ".csv": "Text", ".json": "Text",
    ".xml": "Text", ".yaml": "Text", ".yml": "Text", ".log": "Text",
    ".py": "Code", ".js": "Code", ".ts": "Code", ".html": "Code",
    ".css": "Code", ".java": "Code", ".cpp": "Code", ".c": "Code",
    # Archives
    ".zip": "Archives", ".rar": "Archives", ".7z": "Archives",
    ".tar": "Archives", ".gz": "Archives",
    # Executables
    ".exe": "Executables", ".msi": "Executables", ".dmg": "Executables",
    ".sh": "Executables", ".bat": "Executables",
}


def bulk_rename(
    directory: str,
    pattern: str,
    replacement: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Rename all files in *directory* that match *pattern* using string replacement.

    Args:
        directory:   Directory containing files to rename.
        pattern:     Substring or regex to find in filenames.
        replacement: String to replace matches with.
        dry_run:     If True (default) just preview; set False to apply.
    """
    try:
        root = resolve_path(directory)
        if not root.is_dir():
            return {"status": "error", "message": f"Not a directory: {root}"}

        previews = []
        for p in root.iterdir():
            if not p.is_file():
                continue
            try:
                new_stem = re.sub(pattern, replacement, p.name)
            except re.error:
                new_stem = p.name.replace(pattern, replacement)

            if new_stem != p.name:
                new_path = p.parent / new_stem
                previews.append({"from": p.name, "to": new_stem, "path": str(p)})
                if not dry_run:
                    p.rename(new_path)

        return {
            "status": "success",
            "dry_run": dry_run,
            "renamed": len(previews),
            "preview": previews,
            "message": (
                f"Would rename {len(previews)} file(s). Set dry_run=False to apply."
                if dry_run else
                f"Renamed {len(previews)} file(s)."
            ),
        }
    except Exception as exc:
        logger.error("bulk_rename failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def organize_by_type(
    directory: str,
    destination: str = "",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Sort files in *directory* into subfolders by file type (Images/, Documents/, etc.).

    Args:
        directory:   Source folder containing unsorted files.
        destination: Where to create the type subfolders. Defaults to the same folder.
        dry_run:     Preview only if True (default).
    """
    try:
        src = resolve_path(directory)
        if not src.is_dir():
            return {"status": "error", "message": f"Not a directory: {src}"}
        dest_root = resolve_path(destination) if destination else src

        moves: List[Dict[str, str]] = []
        for p in src.iterdir():
            if not p.is_file():
                continue
            subfolder = _EXT_MAP.get(p.suffix.lower(), "Other")
            target_dir = dest_root / subfolder
            target = target_dir / p.name
            moves.append({"file": p.name, "ext": p.suffix, "to": subfolder, "full_target": str(target)})
            if not dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(target))

        summary = defaultdict(int)
        for m in moves:
            summary[m["to"]] += 1

        return {
            "status": "success",
            "dry_run": dry_run,
            "files_to_move": len(moves),
            "breakdown": dict(summary),
            "preview": moves[:50],
            "message": (
                f"Would move {len(moves)} files. Set dry_run=False to apply."
                if dry_run else
                f"Moved {len(moves)} files into type subfolders."
            ),
        }
    except Exception as exc:
        logger.error("organize_by_type failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def organize_by_date(
    directory: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Sort files into YYYY/MM/ subfolders based on modification date.

    Args:
        directory: Source folder.
        dry_run:   Preview only if True (default).
    """
    try:
        src = resolve_path(directory)
        if not src.is_dir():
            return {"status": "error", "message": f"Not a directory: {src}"}

        moves = []
        for p in src.iterdir():
            if not p.is_file():
                continue
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            year_month = mtime.strftime("%Y/%m")
            target_dir = src / year_month
            target = target_dir / p.name
            moves.append({"file": p.name, "date": mtime.strftime("%Y-%m-%d"), "folder": year_month})
            if not dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(target))

        return {
            "status": "success",
            "dry_run": dry_run,
            "files_to_move": len(moves),
            "preview": moves[:50],
            "message": (
                f"Would sort {len(moves)} files by date. Set dry_run=False to apply."
                if dry_run else
                f"Sorted {len(moves)} files into date subfolders."
            ),
        }
    except Exception as exc:
        logger.error("organize_by_date failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def move_files_matching(
    pattern: str,
    source: str,
    destination: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Move all files in *source* matching a glob pattern to *destination*.

    Args:
        pattern:     Glob pattern e.g. '*.jpg', 'report*'.
        source:      Source directory.
        destination: Destination directory.
        dry_run:     Preview only if True (default).
    """
    try:
        src = resolve_path(source)
        dst = resolve_path(destination)
        if not src.is_dir():
            return {"status": "error", "message": f"Source is not a directory: {src}"}

        matches = list(src.glob(pattern))
        if not dry_run:
            dst.mkdir(parents=True, exist_ok=True)
        moved = []
        for p in matches:
            if p.is_file():
                moved.append(p.name)
                if not dry_run:
                    shutil.move(str(p), str(dst / p.name))

        return {
            "status": "success",
            "dry_run": dry_run,
            "count": len(moved),
            "files": moved,
            "message": (
                f"Would move {len(moved)} file(s) to {dst}. Set dry_run=False to apply."
                if dry_run else
                f"Moved {len(moved)} file(s) to {dst}."
            ),
        }
    except Exception as exc:
        logger.error("move_files_matching failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def delete_files_matching(
    pattern: str,
    directory: str,
    dry_run: bool = True,
    permanent: bool = False,
) -> Dict[str, Any]:
    """
    Delete all files in *directory* matching a glob pattern.

    Args:
        pattern:   Glob pattern e.g. '*.tmp', '~*'.
        directory: Directory to clean.
        dry_run:   Preview only if True (default).
        permanent: Bypass Recycle Bin if True. Default False.
    """
    try:
        root = resolve_path(directory)
        if not root.is_dir():
            return {"status": "error", "message": f"Not a directory: {root}"}
        if not _is_safe_path(root):
            return {"status": "error", "message": "Cannot delete from a protected system path."}

        matches = [p for p in root.glob(pattern) if p.is_file()]
        total_size = sum(p.stat().st_size for p in matches)

        if not dry_run:
            for p in matches:
                if permanent:
                    p.unlink()
                else:
                    send_to_recycle_bin(p)

        return {
            "status": "success",
            "dry_run": dry_run,
            "count": len(matches),
            "total_size": _fmt_size(total_size),
            "files": [p.name for p in matches[:50]],
            "message": (
                f"Would delete {len(matches)} file(s) ({_fmt_size(total_size)}). Set dry_run=False to apply."
                if dry_run else
                f"Deleted {len(matches)} file(s) ({_fmt_size(total_size)})."
            ),
        }
    except Exception as exc:
        logger.error("delete_files_matching failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def clean_empty_folders(directory: str, dry_run: bool = True) -> Dict[str, Any]:
    """
    Remove empty (and recursively empty) subdirectories.

    Args:
        directory: Root directory to clean.
        dry_run:   Preview only if True (default).
    """
    try:
        root = resolve_path(directory)
        if not root.is_dir():
            return {"status": "error", "message": f"Not a directory: {root}"}

        empty = []
        # Walk bottom-up so child empty dirs are removed before checking parents
        for p in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            if p == root:
                continue
            if p.is_dir():
                try:
                    if not any(True for _ in p.iterdir()):
                        empty.append(str(p))
                        if not dry_run:
                            p.rmdir()
                except Exception:
                    pass

        return {
            "status": "success",
            "dry_run": dry_run,
            "count": len(empty),
            "folders": empty[:50],
            "message": (
                f"Would remove {len(empty)} empty folder(s). Set dry_run=False to apply."
                if dry_run else
                f"Removed {len(empty)} empty folder(s)."
            ),
        }
    except Exception as exc:
        logger.error("clean_empty_folders failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def deduplicate_files(
    directory: str,
    keep: str = "newest",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Remove duplicate files, keeping one copy per set.

    Args:
        directory: Directory to deduplicate.
        keep:      Which copy to keep: 'newest' (default) or 'oldest'.
        dry_run:   Preview only if True (default).
    """
    try:
        from .search import find_duplicates
        result = find_duplicates(directory)
        if result["status"] == "error":
            return result

        to_delete: List[str] = []
        for group in result["groups"]:
            paths = [Path(f) for f in group["files"]]
            if keep == "newest":
                paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            else:
                paths.sort(key=lambda p: p.stat().st_mtime)
            # Keep first, delete rest
            for p in paths[1:]:
                to_delete.append(str(p))
                if not dry_run:
                    send_to_recycle_bin(p)

        return {
            "status": "success",
            "dry_run": dry_run,
            "duplicate_groups": result["duplicate_groups"],
            "files_to_remove": len(to_delete),
            "space_to_recover": result["total_wasted_space"],
            "files": to_delete[:50],
            "message": (
                f"Would delete {len(to_delete)} duplicate file(s) and recover {result['total_wasted_space']}. Set dry_run=False to apply."
                if dry_run else
                f"Deleted {len(to_delete)} duplicate file(s), recovered {result['total_wasted_space']}."
            ),
        }
    except Exception as exc:
        logger.error("deduplicate_files failed: %s", exc)
        return {"status": "error", "message": str(exc)}
