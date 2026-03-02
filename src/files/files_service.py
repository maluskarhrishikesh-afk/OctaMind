"""
Files Agent — low-level filesystem helpers.

All feature modules call these helpers instead of using os / pathlib / shutil
directly, so path normalisation and error handling live in one place.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("files_agent")

# ── Path helpers ──────────────────────────────────────────────────────────────

# Common user-folder aliases.  When a path starts with one of these names
# (case-insensitive) and is still relative, it is resolved under the user's
# home directory so that "Downloads/rtofraud" → ~/Downloads/rtofraud.
_USER_FOLDER_ALIASES: Dict[str, str] = {
    "downloads":   "Downloads",
    "desktop":     "Desktop",
    "documents":   "Documents",
    "mydocuments": "Documents",
    "pictures":    "Pictures",
    "photos":      "Pictures",
    "music":       "Music",
    "videos":      "Videos",
    "onedrive":    "OneDrive",
}


def resolve_path(raw: str) -> Path:
    """
    Expand ~, env vars, and common user-folder aliases; return an absolute Path.
    Accepts forward or back slashes.

    Examples::

        resolve_path("Downloads/rtofraud")       → ~/Downloads/rtofraud
        resolve_path("~/Documents/report.pdf")   → ~/Documents/report.pdf
        resolve_path("C:/Projects/data")         → C:/Projects/data  (unchanged)
        resolve_path("hrishikesh")               → C:\\Hrishikesh   (if found at drive root)
    """
    raw = raw.strip().replace("\\", "/")
    p = Path(os.path.expandvars(os.path.expanduser(raw)))

    # If still relative, try to replace a known user-folder alias on the
    # first path component with the full home-relative path.
    if not p.is_absolute():
        parts = p.parts
        if parts:
            alias = parts[0].lower().rstrip("/")
            canonical = _USER_FOLDER_ALIASES.get(alias)
            if canonical:
                rest = Path(*parts[1:]) if len(parts) > 1 else Path("")
                p = Path.home() / canonical / rest if str(rest) != "." else Path.home() / canonical

    resolved = p.resolve()

    # On Windows: if the resolved path doesn't exist and the original input
    # was a bare name (no directory separator), try treating it as a top-level
    # folder on each available drive (e.g. "hrishikesh" → C:\Hrishikesh).
    if not resolved.exists() and "/" not in raw and "\\" not in raw and os.name == "nt":
        import string as _string
        for drive_letter in _string.ascii_uppercase:
            candidate = Path(f"{drive_letter}:\\") / raw
            if candidate.exists():
                return candidate.resolve()

    return resolved


def _fmt_size(size_bytes: int) -> str:
    """Human-readable size string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _file_dict(p: Path, include_hash: bool = False) -> Dict[str, Any]:
    """Return a metadata dict for a single file or directory."""
    try:
        s = p.stat()
        d: Dict[str, Any] = {
            "name": p.name,
            "path": str(p),
            "type": "folder" if p.is_dir() else "file",
            "extension": p.suffix.lower() if not p.is_dir() else "",
            "size_bytes": s.st_size if not p.is_dir() else 0,
            "size": _fmt_size(s.st_size) if not p.is_dir() else "",
            "modified": datetime.fromtimestamp(s.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(s.st_ctime).isoformat(),
        }
        if include_hash and p.is_file() and s.st_size < 50 * 1024 * 1024:
            d["md5"] = _hash_file(p, "md5")
        return d
    except PermissionError:
        return {"name": p.name, "path": str(p), "type": "unknown", "error": "permission denied"}
    except OSError as exc:
        return {"name": p.name, "path": str(p), "type": "unknown", "error": str(exc)}


def _hash_file(path: Path, algorithm: str = "md5") -> str:
    """Return a hex digest for a file."""
    h = hashlib.new(algorithm)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp string into a datetime, or None."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


# ── Safety helpers ────────────────────────────────────────────────────────────

_DANGEROUS_ROOTS = {
    "windows": [
        "C:/Windows", "C:/Windows/System32", "C:/Program Files",
        "C:/Program Files (x86)", "C:/ProgramData",
    ],
    "other": ["/bin", "/sbin", "/usr/bin", "/usr/sbin", "/etc", "/boot", "/proc", "/sys"],
}


def _is_safe_path(p: Path) -> bool:
    """Returns False if the path looks like a critical system location."""
    path_str = str(p).replace("\\", "/")
    danger = _DANGEROUS_ROOTS.get("windows" if platform.system() == "Windows" else "other", [])
    return not any(path_str.lower().startswith(d.lower()) for d in danger)


def send_to_recycle_bin(path: Path) -> bool:
    """
    Move a file to the Recycle Bin on Windows.
    Falls back to os.remove() / shutil.rmtree() if send2trash is not available.
    Returns True on success.
    """
    try:
        import send2trash  # type: ignore
        send2trash.send2trash(str(path))
        return True
    except ImportError:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
