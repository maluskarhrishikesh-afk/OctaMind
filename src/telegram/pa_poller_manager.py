"""
PA Telegram Poller Manager.

Starts/stops per-PA Telegram poller processes and tracks their state
in running_agents.json (same file as process_manager, using key
"tg_pa_<pa_id>" to avoid collisions).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).parent.parent.parent
_STATE_FILE = _ROOT / "running_tg_pollers.json"   # separate from running_agents.json
_POLLER_SCRIPT = _ROOT / "src" / "telegram" / "pa_poller_runner.py"


# ── State helpers ─────────────────────────────────────────────────────────────

def _load_state() -> Dict[str, Any]:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _is_pid_alive(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes
            # PROCESS_QUERY_LIMITED_INFORMATION is enough and widely accessible
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong(0)
            ok = ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            )
            ctypes.windll.kernel32.CloseHandle(handle)
            # STILL_ACTIVE (259) means the process hasn't exited yet
            return bool(ok) and exit_code.value == STILL_ACTIVE
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def _venv_python() -> str:
    p = _ROOT / ".venv" / "Scripts" / "python.exe"
    return str(p) if p.exists() else sys.executable


def _state_key(pa_id: str) -> str:
    return pa_id


# ── Public API ────────────────────────────────────────────────────────────────

def start_pa_poller(pa_id: str) -> Dict[str, Any]:
    """
    Start the per-PA Telegram poller subprocess.

    Returns {"pid": int, "pa_id": str} or raises on error.
    """
    key = _state_key(pa_id)
    state = _load_state()

    # Already running?
    if key in state and _is_pid_alive(state[key]["pid"]):
        return {"pid": state[key]["pid"], "pa_id": pa_id, "already_running": True}

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT)
    env["PA_ID"] = pa_id

    if sys.platform == "win32":
        # On Windows, subprocess.Popen inherits the parent's Windows Job Object.
        # If the parent Job Object has JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, the
        # poller subprocess is killed the moment the calling Python process exits
        # (e.g., the Streamlit worker thread recycles).  CREATE_BREAKAWAY_FROM_JOB
        # silently fails when the Job doesn't have BREAKAWAY_OK set.
        #
        # Using PowerShell Start-Process creates a fully independent process that
        # is NOT in the parent's Job Object — exactly what we need for a long-lived
        # background daemon.
        python_exe = _venv_python().replace("'", "''")
        script_path = str(_POLLER_SCRIPT).replace("'", "''")
        cwd = str(_ROOT).replace("'", "''")
        ps_cmd = (
            f"(Start-Process "
            f"-FilePath '{python_exe}' "
            f"-ArgumentList '{script_path}' "
            f"-WorkingDirectory '{cwd}' "
            f"-WindowStyle Hidden "
            f"-PassThru).Id"
        )
        # Pass env directly to the powershell subprocess so that PA_ID and
        # PYTHONPATH are already set in its environment; Start-Process inherits them.
        ps_result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15, env=env,
        )
        pid_str = ps_result.stdout.strip().splitlines()[-1] if ps_result.stdout.strip() else ""
        if not pid_str.isdigit():
            raise RuntimeError(
                f"Start-Process failed (exit {ps_result.returncode}): "
                f"{ps_result.stderr.strip() or ps_result.stdout.strip()}"
            )
        pid = int(pid_str)
    else:
        proc = subprocess.Popen(
            [_venv_python(), str(_POLLER_SCRIPT)],
            cwd=str(_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pid = proc.pid

    state[key] = {"pid": pid, "pa_id": pa_id}
    _save_state(state)

    # Brief pause so the poller has time to initialise before the Streamlit
    # page reloads and calls _is_pid_alive().
    import time as _time
    _time.sleep(0.5)

    return {"pid": pid, "pa_id": pa_id}


def stop_pa_poller(pa_id: str) -> bool:
    """Stop the per-PA Telegram poller. Returns True if stopped."""
    key = _state_key(pa_id)
    state = _load_state()
    if key not in state:
        return False

    pid = state[key]["pid"]
    stopped = False
    if _is_pid_alive(pid):
        try:
            if sys.platform == "win32":
                subprocess.call(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, 9)
            stopped = True
        except Exception:
            pass

    del state[key]
    _save_state(state)
    return stopped


def get_pa_poller_status(pa_id: str) -> Optional[Dict[str, Any]]:
    """
    Return {"pid": int, "running": True} if the poller is alive, else None.
    Stale entries are garbage-collected.
    """
    key = _state_key(pa_id)
    state = _load_state()
    if key not in state:
        return None

    pid = state[key]["pid"]
    if _is_pid_alive(pid):
        return {"pid": pid, "pa_id": pa_id, "running": True}

    # Stale — clean up
    del state[key]
    _save_state(state)
    return None
