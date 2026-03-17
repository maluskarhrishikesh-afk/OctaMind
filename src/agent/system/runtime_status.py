from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from src.agent.runtime_paths import get_root_runtime_state_path, get_workspace_root


def _settings_path() -> Path:
    return get_workspace_root() / "config" / "settings.json"


def _load_settings() -> Dict[str, Any]:
    path = _settings_path()
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def keep_awake_supported() -> bool:
    return sys.platform == "win32"


def keep_awake_enabled() -> bool:
    if not keep_awake_supported():
        return False

    env_value = os.environ.get("OCTAMIND_KEEP_AWAKE_WHEN_RUNNING", "").strip().lower()
    if env_value in {"0", "false", "no", "off"}:
        return False
    if env_value in {"1", "true", "yes", "on"}:
        return True

    runtime_cfg = _load_settings().get("runtime", {})
    configured = runtime_cfg.get("keep_awake_when_running")
    if isinstance(configured, bool):
        return configured
    return True


def _keep_awake_state_path() -> Path:
    return get_root_runtime_state_path("keep_awake.json", create_parent=True)


def _load_keep_awake_state() -> Dict[str, Any]:
    path = _keep_awake_state_path()
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _is_pid_alive(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes

            process_query_limited_information = 0x1000
            still_active = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong(0)
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return bool(ok) and exit_code.value == still_active

        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_keep_awake_status() -> Dict[str, Any]:
    supported = keep_awake_supported()
    enabled = keep_awake_enabled()
    state = _load_keep_awake_state() if supported else {}
    pid_value: Optional[int] = state.get("pid") if isinstance(state.get("pid"), int) else None
    running = bool(pid_value and _is_pid_alive(pid_value))

    if not supported:
        label = "Unavailable"
        detail = "Keep-awake helper is only available on Windows."
    elif not enabled:
        label = "Disabled"
        detail = "Idle sleep prevention is disabled; Telegram will stop responding after Windows sleeps."
    elif running:
        label = "Active"
        detail = "Idle sleep prevention is active while OctaMind is running."
    else:
        label = "Inactive"
        detail = "Keep-awake is enabled but the helper is not running; the laptop may sleep when idle."

    return {
        "supported": supported,
        "enabled": enabled,
        "running": running,
        "pid": pid_value,
        "label": label,
        "detail": detail,
        "hard_limit": "If Windows enters real sleep or hibernation, Telegram cannot reach OctaMind until the laptop wakes.",
    }