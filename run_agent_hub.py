"""
Launch Agent Hub Dashboard

Run this script to start the multi-agent management interface.
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).parent


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("localhost", port)) == 0


def _load_settings(project_root: Path) -> dict:
    settings_path = project_root / "config" / "settings.json"
    try:
        if settings_path.exists():
            return json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _keep_awake_enabled(project_root: Path) -> bool:
    if sys.platform != "win32":
        return False
    env_value = os.environ.get("OCTAMIND_KEEP_AWAKE_WHEN_RUNNING", "").strip().lower()
    if env_value in {"0", "false", "no", "off"}:
        return False
    if env_value in {"1", "true", "yes", "on"}:
        return True
    runtime_cfg = _load_settings(project_root).get("runtime", {})
    configured = runtime_cfg.get("keep_awake_when_running")
    if isinstance(configured, bool):
        return configured
    return True


def _keep_awake_state_path(project_root: Path) -> Path:
    state_dir = project_root / "your_data" / "runtime_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "keep_awake.json"


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
            ok = ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            )
            ctypes.windll.kernel32.CloseHandle(handle)
            return bool(ok) and exit_code.value == still_active
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _start_keep_awake(project_root: Path, python_cmd: str) -> None:
    if not _keep_awake_enabled(project_root):
        print("Keep-awake disabled.")
        return

    state_path = _keep_awake_state_path(project_root)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}

    pid = state.get("pid")
    if isinstance(pid, int) and _is_pid_alive(pid):
        print("Keep-awake process already running.")
        return

    script_path = project_root / "src" / "agent" / "system" / "keep_awake.py"
    if not script_path.exists():
        print("Keep-awake script not found; skipping.")
        return

    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_handle = open(logs_dir / "keep_awake_stdout.txt", "a", encoding="utf-8")
    stderr_handle = open(logs_dir / "keep_awake_stderr.txt", "a", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [python_cmd, str(script_path)],
        cwd=str(project_root),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )
    state_path.write_text(json.dumps({"pid": proc.pid}, indent=2), encoding="utf-8")
    print("Keep-awake process started.")


def _start_hub_api(project_root: Path, python_cmd: str) -> None:
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_handle = open(logs_dir / "hub_stdout.txt", "a", encoding="utf-8")
    stderr_handle = open(logs_dir / "hub_stderr.txt", "a", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(
        [
            python_cmd,
            "-m",
            "uvicorn",
            "src.agent.hub.server:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8502",
        ],
        cwd=str(project_root),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )
    print("Hub API started on http://localhost:8502")


def main():
    """Launch the agent dashboard"""
    project_root = _project_root()
    dashboard_path = project_root / "src" / "agent" / "ui" / "dashboard" / "app.py"

    # Use virtual environment python if available
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    python_cmd = str(venv_python) if venv_python.exists() else "python"

    print("🚀 Launching Agent Hub...")
    print(f"📍 Dashboard: {dashboard_path}")
    print("🌐 URL: http://localhost:8501")
    print("-" * 50)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    if sys.platform == "win32":
        _start_keep_awake(project_root, python_cmd)
    if not _port_in_use(8502):
        _start_hub_api(project_root, python_cmd)

    print("Keep-awake helper is enabled while OctaMind is running on Windows.")
    print("If the laptop enters real sleep or hibernation, Telegram cannot reach it until Windows wakes.")

    subprocess.run([
        python_cmd,
        "-m", "streamlit", "run",
        str(dashboard_path),
        "--server.port", "8501"
    ], env=env, check=False)


if __name__ == "__main__":
    main()
