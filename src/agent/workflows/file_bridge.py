"""
FileBridge — temp-file exchange between agents in a workflow.

When the Drive agent downloads a file, the Email agent needs to find it
to attach it. FileBridge stores the mapping and cleans up afterwards.

Usage:
    # Drive step — after downloading:
    handle = file_bridge.register("abc123", "/tmp/octamind_wf_abc/budget.xlsx")

    # Email step — before attaching:
    path = file_bridge.resolve("abc123")   # → "/tmp/octamind_wf_abc/budget.xlsx"

    # After workflow completes:
    file_bridge.cleanup_handle("abc123")
"""
from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("workflows")

# In-memory registry: handle → absolute path
_registry: Dict[str, Path] = {}


def make_workflow_dir() -> Path:
    """Create a fresh temp directory for one workflow run."""
    tmp = Path(tempfile.gettempdir()) / f"octamind_wf_{uuid.uuid4().hex[:8]}"
    tmp.mkdir(parents=True, exist_ok=True)
    logger.debug("Created workflow temp dir: %s", tmp)
    return tmp


def register(handle: str, path: str | Path) -> str:
    """
    Register a file under a workflow handle.

    Args:
        handle: Unique identifier for this file within the workflow
                (e.g. "downloaded_file" or the file_id).
        path:   Absolute path where the file lives on disk.

    Returns:
        The handle, for convenience.
    """
    resolved = Path(path).resolve()
    _registry[handle] = resolved
    logger.debug("FileBridge: registered %s → %s", handle, resolved)
    return handle


def resolve(handle: str) -> Optional[Path]:
    """
    Look up the file path by handle.

    Returns None if the handle is not registered or file no longer exists.
    """
    path = _registry.get(handle)
    if path is None:
        logger.warning("FileBridge: unknown handle %s", handle)
        return None
    if not path.exists():
        logger.warning(
            "FileBridge: file gone for handle %s (%s)", handle, path)
        return None
    return path


def cleanup_handle(handle: str) -> None:
    """Delete the registered file and remove the handle from the registry."""
    path = _registry.pop(handle, None)
    if path and path.exists():
        try:
            path.unlink()
            logger.debug("FileBridge: deleted %s", path)
            # Remove parent dir if it's an octamind workflow dir and now empty
            if path.parent.name.startswith("octamind_wf_"):
                remaining = list(path.parent.iterdir())
                if not remaining:
                    path.parent.rmdir()
                    logger.debug(
                        "FileBridge: removed empty dir %s", path.parent)
        except Exception as exc:
            logger.warning("FileBridge: could not delete %s: %s", path, exc)


def cleanup_all() -> None:
    """Delete all registered files and clear the registry."""
    for handle in list(_registry.keys()):
        cleanup_handle(handle)


def file_size_mb(handle: str) -> Optional[float]:
    """Return file size in MB, or None if file not found."""
    path = resolve(handle)
    if path is None:
        return None
    try:
        return path.stat().st_size / (1024 * 1024)
    except Exception:
        return None
