"""
Octa Bot — Start Launcher
Starts the Octa Bot dashboard and opens it in the default browser.
Bundled to start.exe via PyInstaller.

NOTE: This launcher intentionally does NOT import any heavy src.* modules
(torch, transformers, etc.).  All channel startup logic that was previously
handled by DashboardChannel / TelegramChannel is done here directly so that:
  1. The PyInstaller build stays fast (no ML-library analysis).
  2. Path resolution works correctly when frozen (__file__ is unreliable
     inside a PyInstaller bundle; sys.executable is always correct).
"""
import os
import sys
import glob
import json
import shutil
import subprocess
import webbrowser
import time
import socket
from pathlib import Path


def _project_root() -> str:
    """Return the project root regardless of whether running as script or .exe."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def _truncate_logs(root: str) -> None:
    """Truncate all *.log files inside the logs/ folder so each run starts fresh."""
    logs_dir = os.path.join(root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    for path in glob.glob(os.path.join(logs_dir, "*.log")):
        try:
            Path(path).write_text("", encoding="utf-8")
        except OSError:
            pass
    for path in glob.glob(os.path.join(logs_dir, "tests", "*.log")):
        try:
            Path(path).write_text("", encoding="utf-8")
        except OSError:
            pass


def _cleanup_old_archive_bundles(root: str, max_age_hours: int = 24) -> None:
    """Delete temporary archive staging folders older than the retention window."""
    archives_root = Path(root) / "your_data" / "archives"
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0

    for folder_name in ("bundles", "search_results"):
        target_root = archives_root / folder_name
        if not target_root.exists():
            continue
        for child in target_root.iterdir():
            if not child.is_dir():
                continue
            try:
                if child.stat().st_mtime >= cutoff:
                    continue
                shutil.rmtree(child)
                removed += 1
            except OSError:
                pass

    if removed:
        print(f"Cleared {removed} expired archive bundle folder(s).")


def _load_settings(root: str) -> dict:
    settings_path = os.path.join(root, "config", "settings.json")
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _keep_awake_enabled(root: str) -> bool:
    if sys.platform != "win32":
        return False
    env_value = os.environ.get("OCTAMIND_KEEP_AWAKE_WHEN_RUNNING", "").strip().lower()
    if env_value in {"0", "false", "no", "off"}:
        return False
    if env_value in {"1", "true", "yes", "on"}:
        return True
    runtime_cfg = _load_settings(root).get("runtime", {})
    configured = runtime_cfg.get("keep_awake_when_running")
    if isinstance(configured, bool):
        return configured
    return True


def _keep_awake_state_path(root: str) -> Path:
    state_dir = Path(root) / "your_data" / "runtime_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "keep_awake.json"


def _load_keep_awake_state(root: str) -> dict:
    path = _keep_awake_state_path(root)
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_keep_awake_state(root: str, pid: int) -> None:
    _keep_awake_state_path(root).write_text(
        json.dumps({"pid": pid}, indent=2),
        encoding="utf-8",
    )


def _is_pid_alive(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes

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
            return bool(ok) and exit_code.value == STILL_ACTIVE
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _start_keep_awake(root: str, python: str) -> None:
    if not _keep_awake_enabled(root):
        print("Keep-awake disabled.")
        return

    state = _load_keep_awake_state(root)
    pid = state.get("pid")
    if isinstance(pid, int) and _is_pid_alive(pid):
        print("Keep-awake process already running.")
        return

    script_path = os.path.join(root, "src", "agent", "system", "keep_awake.py")
    if not os.path.exists(script_path):
        print("Keep-awake script not found — skipping.")
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = root
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    logs_dir = os.path.join(root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    stdout_path = os.path.join(logs_dir, "keep_awake_stdout.txt")
    stderr_path = os.path.join(logs_dir, "keep_awake_stderr.txt")
    stdout_handle = open(stdout_path, "a", encoding="utf-8")
    stderr_handle = open(stderr_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [python, script_path],
        cwd=root,
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )
    _save_keep_awake_state(root, proc.pid)
    print("Keep-awake process started.")


def _start_consolidation(root: str, python: str) -> None:
    """
    Spawn the memory consolidation runner as an independent detached process.

    Using --loop so it keeps running every 8 hours alongside the dashboard.
    A separate process means heavy LLM consolidation calls never slow down
    the Streamlit UI and survives dashboard hot-reloads cleanly.
    """
    consolidation_script = os.path.join(
        root, "src", "agent", "memory", "run_consolidation.py"
    )
    if not os.path.exists(consolidation_script):
        print("  Consolidation script not found — skipping.")
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = root
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(
        [python, consolidation_script, "--loop"],
        cwd=root,
        env=env,
        creationflags=creationflags,
    )
    print("Memory consolidation process started (8-hour cycle).")


def _start_dashboard(root: str, python: str) -> None:
    """Spawn the Streamlit dashboard as a detached subprocess."""
    app_path = os.path.join(root, "src", "agent", "ui", "dashboard", "app.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = root  # Must be the real project root, not a temp dir
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    logs_dir = os.path.join(root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    stdout_path = os.path.join(logs_dir, "dash_stdout.txt")
    stderr_path = os.path.join(logs_dir, "dash_stderr.txt")
    stdout_handle = open(stdout_path, "a", encoding="utf-8")
    stderr_handle = open(stderr_path, "a", encoding="utf-8")
    subprocess.Popen(
        [
            python, "-m", "streamlit", "run", app_path,
            "--server.port", "8501",
            "--server.headless", "true",
        ],
        cwd=root,
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )


def _start_hub_api(root: str, python: str) -> None:
    """Spawn the FastAPI hub server as a detached subprocess on port 8502."""
    env = os.environ.copy()
    env["PYTHONPATH"] = root
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    logs_dir = os.path.join(root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    stdout_path = os.path.join(logs_dir, "hub_stdout.txt")
    stderr_path = os.path.join(logs_dir, "hub_stderr.txt")
    stdout_handle = open(stdout_path, "a", encoding="utf-8")
    stderr_handle = open(stderr_path, "a", encoding="utf-8")
    subprocess.Popen(
        [
            python, "-m", "uvicorn", "src.agent.hub.server:app",
            "--host", "0.0.0.0",
            "--port", "8502",
        ],
        cwd=root,
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )


def main():
    root = _project_root()
    venv_python = os.path.join(root, '.venv', 'Scripts', 'python.exe')
    if not os.path.exists(venv_python):
        venv_python = sys.executable  # Fallback to current Python

    _truncate_logs(root)
    print("Log files cleared.")
    _cleanup_old_archive_bundles(root)

    if _port_in_use(8501):
        _start_keep_awake(root, venv_python)
        if not _port_in_use(8502):
            print("Hub API is not running — starting it on http://localhost:8502 ...")
            _start_hub_api(root, venv_python)
        print("Octa Bot is already running — opening browser...")
        webbrowser.open('http://localhost:8501')
        return

    print("Starting OctaMind dashboard on http://localhost:8501 ...")
    _start_dashboard(root, venv_python)
    if not _port_in_use(8502):
        print("Starting OctaMind Hub API on http://localhost:8502 ...")
        _start_hub_api(root, venv_python)
    _start_keep_awake(root, venv_python)

    # Launch memory consolidation as an independent background process.
    # Runs immediately on startup (one-shot pass) then loops every 8 hours.
    _start_consolidation(root, venv_python)
    # Note: per-PA Telegram pollers are started from within the Streamlit
    # process (dashboard configure tab) — not here.

    # Wait for Streamlit to be ready (up to 15 seconds)
    for i in range(15):
        time.sleep(1)
        if _port_in_use(8501):
            print(f"Ready after {i + 1}s — opening browser...")
            break
        print(f"  Waiting for server... ({i + 1}s)")
    else:
        print("  Server did not respond in 15s — check logs/dash_stderr.txt")
        return

    webbrowser.open('http://localhost:8501')
    print("OctaMind started. You can close this window.")


if __name__ == '__main__':
    main()
