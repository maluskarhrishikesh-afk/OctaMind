from __future__ import annotations

import shutil
from pathlib import Path


def get_workspace_root() -> Path:
    """Return the repository root for the active OctaMind workspace."""
    return Path(__file__).resolve().parents[2]


def get_your_data_dir(*parts: str, create: bool = False) -> Path:
    """Return a path under the workspace-local your_data directory."""
    target = get_workspace_root() / "your_data"
    for part in parts:
        if part:
            target /= part
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def get_legacy_data_dir(*parts: str, create: bool = False) -> Path:
    """Return a path under the legacy workspace-local data directory."""
    target = get_workspace_root() / "data"
    for part in parts:
        if part:
            target /= part
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def get_runtime_state_dir(*parts: str, create: bool = False) -> Path:
    """Return the canonical directory for runtime state stored under your_data."""
    return get_your_data_dir(*parts, create=create)


def get_runtime_state_path(*parts: str, create_parent: bool = False) -> Path:
    """Return the canonical runtime-state path under your_data."""
    target = get_runtime_state_dir(*parts)
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def get_existing_runtime_state_path(*parts: str) -> Path:
    """Return the canonical runtime-state path, falling back to legacy data if needed."""
    target = get_runtime_state_path(*parts)
    legacy = get_legacy_data_dir(*parts)
    if target.exists() or not legacy.exists():
        return target
    return legacy


def migrate_legacy_runtime_state_file(*parts: str) -> Path:
    """Copy a legacy data file into your_data on first write and return the canonical path."""
    target = get_runtime_state_path(*parts, create_parent=True)
    legacy = get_legacy_data_dir(*parts)
    if not target.exists() and legacy.exists() and legacy.is_file():
        shutil.copy2(legacy, target)
    return target


def get_root_runtime_state_dir(*parts: str, create: bool = False) -> Path:
    """Return the dedicated folder for legacy root-level runtime state files."""
    return get_runtime_state_dir("runtime_state", *parts, create=create)


def get_root_runtime_state_path(*parts: str, create_parent: bool = False) -> Path:
    """Return the canonical path for runtime state migrated from the repo root."""
    target = get_root_runtime_state_dir(*parts)
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def get_existing_root_runtime_state_path(*parts: str) -> Path:
    """Return the canonical root-runtime path, falling back to the legacy repo root file."""
    target = get_root_runtime_state_path(*parts)
    legacy = get_workspace_root().joinpath(*parts)
    if target.exists() or not legacy.exists():
        return target
    return legacy


def migrate_legacy_root_runtime_state_file(*parts: str) -> Path:
    """Copy a legacy repo-root runtime state file into your_data/runtime_state on first use."""
    target = get_root_runtime_state_path(*parts, create_parent=True)
    legacy = get_workspace_root().joinpath(*parts)
    if not target.exists() and legacy.exists() and legacy.is_file():
        shutil.copy2(legacy, target)
    return target