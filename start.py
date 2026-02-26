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
import subprocess
import webbrowser
import time
import socket


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
            open(path, 'w').close()
        except OSError:
            pass
    for path in glob.glob(os.path.join(logs_dir, "tests", "*.log")):
        try:
            open(path, 'w').close()
        except OSError:
            pass


def _start_dashboard(root: str, python: str) -> None:
    """Spawn the Streamlit dashboard as a detached subprocess."""
    app_path = os.path.join(root, "src", "agent", "ui", "dashboard", "app.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = root  # Must be the real project root, not a temp dir
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(
        [
            python, "-m", "streamlit", "run", app_path,
            "--server.port", "8501",
            "--server.headless", "true",
        ],
        cwd=root,
        env=env,
        creationflags=creationflags,
    )


def main():
    root = _project_root()
    venv_python = os.path.join(root, '.venv', 'Scripts', 'python.exe')
    if not os.path.exists(venv_python):
        venv_python = sys.executable  # Fallback to current Python

    _truncate_logs(root)
    print("Log files cleared.")

    if _port_in_use(8501):
        print("Octa Bot is already running — opening browser...")
        webbrowser.open('http://localhost:8501')
        return

    print("Starting OctaMind dashboard on http://localhost:8501 ...")
    _start_dashboard(root, venv_python)
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
