"""
PA Manager — CRUD for Personal Assistants.

A Personal Assistant has:
  - A name (chosen by the user)
  - A set of attached Skills  (subset of AGENT_REGISTRY keys)
  - A set of attached Channels (subset of CHANNEL_REGISTRY keys)
  - Its own memory space (memory/<pa_id>/)

Skills are stateless executors; all memory and context live at the PA level.

Storage: data/assistants.json
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.agent.runtime_paths import migrate_legacy_runtime_state_file

_PA_PATH = migrate_legacy_runtime_state_file("assistants.json")

_PA_MANAGER_ERRORS = (OSError, TypeError, ValueError, json.JSONDecodeError)
_PA_IMPORT_ERRORS = (ImportError, AttributeError)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_pa_log_name(name: str) -> str:
    return re.sub(r"[^\w\-.]", "_", (name or "").strip())

def _make_assistant(
    name: str,
    skills: List[str],
    channels: List[str],
    config: Optional[dict] = None,
) -> dict:
    pa_id = f"pa_{uuid.uuid4().hex[:8]}"
    return {
        "id": pa_id,
        "name": name,
        "skills": skills,
        "channels": channels,
        "config": config or {},   # per-PA config, e.g. {"telegram": {"bot_token": "..."}}
        "memory_id": pa_id,    # memory stored at memory/<pa_id>/
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _save(assistants: List[dict]) -> None:
    _PA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PA_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(assistants, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(_PA_PATH)


def _build_pa_log_patterns(pa: dict) -> List[str]:
    pa_id = str(pa.get("id", "")).strip()
    pa_name = str(pa.get("name", "")).strip()
    safe_name = _safe_pa_log_name(pa_name)

    project_root = _PA_PATH.parent.parent
    logs_dir = project_root / "logs"
    patterns = [
        str(logs_dir / f"{pa_id}.log") if pa_id else "",
        str(logs_dir / f"{pa_name}.log") if pa_name else "",
        str(logs_dir / f"{safe_name}.log") if safe_name else "",
        str(logs_dir / f"{safe_name}_stderr.txt") if safe_name else "",
        str(logs_dir / f"pa_{pa_id}_stderr.txt") if pa_id else "",
        str(logs_dir / f"*{pa_id}*.log") if pa_id else "",
    ]
    return [pattern for pattern in patterns if pattern]


def cleanup_orphaned_pa_resources(assistants: Optional[List[dict]] = None) -> None:
    """Remove logs and memory folders that belong to deleted personal assistants."""
    import glob
    import shutil

    active_assistants = assistants if assistants is not None else load_assistants()
    active_ids = {str(pa.get("id", "")).strip() for pa in active_assistants}

    project_root = _PA_PATH.parent.parent
    logs_dir = project_root / "logs"
    memory_root = project_root / "memory"

    keep_log_paths = set()
    for pa in active_assistants:
        for pattern in _build_pa_log_patterns(pa):
            for path in glob.glob(pattern):
                keep_log_paths.add(str(Path(path).resolve()))

    for log_path in logs_dir.glob("*.log"):
        resolved = str(log_path.resolve())
        if resolved in keep_log_paths:
            continue
        if log_path.name in {"dash_stdout.txt", "dash_stderr.txt"}:
            continue
        if log_path.parent.name == "tests":
            continue
        # Only delete logs that look PA-specific.
        if log_path.stem.startswith("pa_") or log_path.stem.startswith("My_Assistant") or "-" in log_path.stem or "_" in log_path.stem:
            try:
                log_path.unlink()
            except OSError as exc:
                print(f"⚠️  Could not remove orphan log {log_path}: {exc}")

    for stderr_path in logs_dir.glob("*_stderr.txt"):
        resolved = str(stderr_path.resolve())
        if resolved in keep_log_paths:
            continue
        if stderr_path.name.startswith("pa_pa_") or stderr_path.stem.endswith("_stderr"):
            try:
                stderr_path.unlink()
            except OSError as exc:
                print(f"⚠️  Could not remove orphan stderr log {stderr_path}: {exc}")

    if memory_root.exists():
        for child in memory_root.iterdir():
            if not child.is_dir():
                continue
            if child.name == "_collective_memory_":
                continue
            if child.name not in active_ids:
                try:
                    shutil.rmtree(child)
                except OSError as exc:
                    print(f"⚠️  Could not remove orphan memory dir {child}: {exc}")


# ── Public API ────────────────────────────────────────────────────────────────

def load_assistants() -> List[dict]:
    """
    Return all Personal Assistants from disk.
    Creates (and persists) a default assistant only on first run (no file yet).
    """
    if _PA_PATH.exists():
        try:
            data = json.loads(_PA_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                cleanup_orphaned_pa_resources(data)
                return data   # may be empty — that's valid after deleting all PAs
        except _PA_MANAGER_ERRORS:
            pass

    # First run — create the default assistant with every available skill
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        all_skills = list(AGENT_REGISTRY.keys())
    except _PA_IMPORT_ERRORS:
        all_skills = ["drive", "email", "files"]

    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        all_channels = list(CHANNEL_REGISTRY.keys())
    except _PA_IMPORT_ERRORS:
        all_channels = ["dashboard", "api", "telegram"]

    default = _make_assistant(
        name="My Assistant",
        skills=all_skills,
        channels=all_channels,
    )
    _save([default])
    cleanup_orphaned_pa_resources([default])
    return [default]


def save_assistants(assistants: List[dict]) -> None:
    """Persist the full list of assistants."""
    _save(assistants)


def _init_pa_memory(pa: dict) -> None:
    """Initialise memory files for a new Personal Assistant.

    Creates the memory directory and seeds personality.md with a template
    that includes a section for tracking the user's personality/preferences.
    PAs are the ONLY entities that own memory in this system.
    """
    try:
        from src.agent.memory.agent_memory import get_agent_memory
        mem = get_agent_memory(pa["id"])
        pa_name = pa["name"]
        # Seed personality.md with user-personality tracking template
        personality_content = f"""# Personality Profile — {pa_name}

## About This Assistant
- **Name:** {pa_name}
- **Created:** {pa.get('created_at', '')[:10]}
- **Skills:** {', '.join(pa.get('skills', []))}

## User Personality (auto-learned)

The assistant observes how the user communicates and adapts over time.
This section is updated automatically during memory consolidation.

| Trait                | Observed Preference              |
| -------------------- | -------------------------------- |
| Communication style  | *(to be learned)*                |
| Response length pref | *(to be learned)*                |
| Formality level      | *(to be learned)*                |
| Preferred topics     | *(to be learned)*                |
| Active hours         | *(to be learned)*                |

## Behavioural Guidelines

- Greet the user warmly and remember their name when shared.
- Adapt tone and verbosity to match the user's observed preference.
- Be proactive — surface useful insights without being asked.
- Always be honest about capabilities and limitations.
- Protect the user: flag unusual requests before acting on them.

## Notes
*(Updated automatically during memory consolidation.)*
"""
        mem.personality_path.write_text(personality_content, encoding="utf-8")
    except (_PA_IMPORT_ERRORS + _PA_MANAGER_ERRORS + (KeyError,)) as exc:
        print(f"⚠️ Could not initialise PA memory for {pa['id']}: {exc}")


def create_assistant(name: str, skills: List[str], channels: List[str],
                     config: Optional[dict] = None) -> dict:
    """Create a new PA, persist it, and initialise its memory.  Returns the new PA dict."""
    assistants = load_assistants()
    pa = _make_assistant(name, skills, channels, config=config)
    assistants.append(pa)
    _save(assistants)
    _init_pa_memory(pa)
    return pa


def get_assistant(pa_id: str) -> Optional[dict]:
    """Return a single PA by id, or None."""
    return next((a for a in load_assistants() if a["id"] == pa_id), None)


def update_assistant(pa_id: str, **fields) -> bool:
    """Patch arbitrary fields on an existing PA.  Returns False if not found."""
    assistants = load_assistants()
    for pa in assistants:
        if pa["id"] == pa_id:
            pa.update(fields)
            _save(assistants)
            return True
    return False


def delete_assistant(pa_id: str) -> bool:
    """Delete a PA by id, its memory directory, and any log files that belong to it.

    Returns False if the PA is not found.
    """
    assistants = load_assistants()
    deleted_pa = next((assistant for assistant in assistants if assistant["id"] == pa_id), None)
    remaining = [a for a in assistants if a["id"] != pa_id]
    if len(remaining) == len(assistants):
        return False   # not found

    _save(remaining)
    _cleanup_pa_resources(deleted_pa or {"id": pa_id, "name": pa_id})
    return True


def _cleanup_pa_resources(pa: dict) -> None:
    """Delete the memory directory and log files for a personal assistant.

    Also stops any running Telegram poller so file handles are released before
    the log is deleted.  Safe to call even if resources do not exist.
    """
    import shutil
    import glob

    pa_id = str(pa.get("id", "")).strip()
    pa_name = str(pa.get("name", "")).strip()
    safe_name = _safe_pa_log_name(pa_name) if pa_name else ""

    project_root = _PA_PATH.parent.parent   # …/OctaMind

    # 1. Stop any running Telegram poller (releases the log file handle)
    try:
        from src.telegram.pa_poller_manager import stop_pa_poller
        stop_pa_poller(pa_id)
    except (_PA_IMPORT_ERRORS + (OSError, RuntimeError, ValueError)):
        pass  # poller may not be running — that's fine

    # 2. Memory directory
    memory_dir = project_root / "memory" / pa_id
    if memory_dir.exists():
        try:
            shutil.rmtree(memory_dir)
        except OSError as exc:
            print(f"⚠️  Could not remove memory dir {memory_dir}: {exc}")

    # 3. Log files — remove both current name-based files and legacy id-based files
    logs_dir = project_root / "logs"
    patterns = [
        str(logs_dir / f"*{pa_id}*.log"),
        str(logs_dir / f"{pa_id}.log"),
        str(logs_dir / f"{pa_name}.log") if pa_name else "",
        str(logs_dir / f"{safe_name}.log") if safe_name else "",
        str(logs_dir / f"{safe_name}_stderr.txt") if safe_name else "",
        str(logs_dir / f"pa_{pa_id}_stderr.txt") if pa_id else "",
    ]
    for pattern in patterns:
        if not pattern:
            continue
        for path in glob.glob(pattern):
            try:
                Path(path).unlink()
            except OSError as exc:
                print(f"⚠️  Could not remove log {path}: {exc}")
