"""
Agent Process Manager

Handles spawning, tracking, and terminating agent subprocess windows.
Each running agent gets its own Streamlit server on a dedicated port.
State is persisted to running_agents.json so it survives dashboard reruns.
"""

import json
import os
import sys
import subprocess
import signal
from pathlib import Path
from typing import Dict, Any, Optional

# Path to persist running-agent state across Streamlit reruns
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_STATE_FILE = _PROJECT_ROOT / "running_agents.json"

# Port range for agent windows
_PORT_START = 8502
_PORT_END = 8600

# Map agent type → which Streamlit script to launch
_AGENT_SCRIPTS: Dict[str, str] = {
    "gmail": "src/agent/ui/email_agent_ui.py",
    "google_drive": "src/agent/ui/drive_agent_ui.py",
    "slack": "src/agent/ui/generic_agent_ui.py",
    "calendar": "src/agent/ui/generic_agent_ui.py",
    "stock_market": "src/agent/ui/generic_agent_ui.py",
    "custom": "src/agent/ui/generic_agent_ui.py",
}


def _load_state() -> Dict[str, Any]:
    """Load running-agents state from disk."""
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    """Persist running-agents state to disk."""
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _is_pid_alive(pid: int) -> bool:
    """Return True if a process with this PID is still running."""
    try:
        if sys.platform == "win32":
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(
                SYNCHRONIZE, False, pid)
            if handle == 0:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def _next_free_port() -> int:
    """Find the next port that is not claimed by a running agent."""
    state = _load_state()
    used_ports = {v["port"] for v in state.values() if _is_pid_alive(v["pid"])}
    for port in range(_PORT_START, _PORT_END):
        if port not in used_ports:
            return port
    raise RuntimeError("No free ports available in range 8502-8599")


def _python_exe() -> str:
    """Return the venv Python executable path."""
    venv_py = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return str(venv_py) if venv_py.exists() else sys.executable


def start_agent(agent_id: str, agent_name: str, agent_type: str) -> Dict[str, Any]:
    """
    Spawn a Streamlit process for the given agent.

    Returns a dict with keys: pid, port, url
    Raises RuntimeError if agent is already running.
    """
    state = _load_state()

    # Check if already running
    if agent_id in state and _is_pid_alive(state[agent_id]["pid"]):
        info = state[agent_id]
        return {"pid": info["pid"], "port": info["port"], "url": f"http://localhost:{info['port']}"}

    # Determine which script to use
    script = _AGENT_SCRIPTS.get(agent_type, _AGENT_SCRIPTS["custom"])
    script_path = str(_PROJECT_ROOT / script)

    port = _next_free_port()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_PROJECT_ROOT)
    env["AGENT_ID"] = agent_id
    env["AGENT_NAME"] = agent_name
    env["AGENT_TYPE"] = agent_type

    proc = subprocess.Popen(
        [
            _python_exe(), "-m", "streamlit", "run",
            script_path,
            "--server.port", str(port),
            "--server.headless", "true",
        ],
        cwd=str(_PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Persist state
    state[agent_id] = {"pid": proc.pid, "port": port}
    _save_state(state)

    return {"pid": proc.pid, "port": port, "url": f"http://localhost:{port}"}


def stop_agent(agent_id: str) -> bool:
    """
    Terminate the Streamlit process for the given agent.

    Returns True if successfully stopped, False if not found.
    """
    state = _load_state()
    if agent_id not in state:
        return False

    pid = state[agent_id]["pid"]
    stopped = False

    if _is_pid_alive(pid):
        try:
            if sys.platform == "win32":
                subprocess.call(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            stopped = True
        except Exception:
            stopped = False

    # Remove from state regardless
    del state[agent_id]
    _save_state(state)
    return stopped


def get_agent_status(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Return {"pid": ..., "port": ..., "url": ..., "running": True/False}
    or None if agent has never been started.
    """
    state = _load_state()
    if agent_id not in state:
        return None

    info = state[agent_id]
    alive = _is_pid_alive(info["pid"])

    # Garbage-collect stale entries
    if not alive:
        del state[agent_id]
        _save_state(state)
        return None

    return {
        "pid": info["pid"],
        "port": info["port"],
        "url": f"http://localhost:{info['port']}",
        "running": True,
    }


def cleanup_stale() -> None:
    """Remove any entries whose processes have already died."""
    state = _load_state()
    live = {aid: info for aid, info in state.items()
            if _is_pid_alive(info["pid"])}
    _save_state(live)


def remove_agent_from_state(agent_id: str) -> None:
    """Remove agent from tracking state without killing the process.
    Called by the agent UI itself when it self-terminates on browser close.
    """
    state = _load_state()
    if agent_id in state:
        del state[agent_id]
        _save_state(state)
