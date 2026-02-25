"""
OctaMind — Start Launcher
Starts the OctaMind dashboard and opens it in the default browser.
Bundled to start.exe via PyInstaller.
"""
import os
import sys
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
    """Truncate all *.log files in the project root so each run starts fresh."""
    import glob
    log_names = ["drive_agent.log", "email_agent.log", "personal_assistant.log", "calendar_agent.log"]
    for name in log_names:
        path = os.path.join(root, name)
        try:
            open(path, 'w').close()  # truncate (or create empty)
        except OSError:
            pass
    # Also truncate any stray logs in src/
    for path in glob.glob(os.path.join(root, "src", "*.log")):
        try:
            open(path, 'w').close()
        except OSError:
            pass


def main():
    root = _project_root()
    venv_python = os.path.join(root, '.venv', 'Scripts', 'python.exe')
    if not os.path.exists(venv_python):
        venv_python = sys.executable  # Fallback to current Python

    _truncate_logs(root)
    print("Log files cleared.")

    if _port_in_use(8501):
        print("OctaMind is already running — opening browser...")
        webbrowser.open('http://localhost:8501')
        return

    print("Starting OctaMind channels...")

    # Each channel knows how to launch itself; adding a new channel only requires
    # a registry entry — no changes needed here.
    os.environ.setdefault('PYTHONPATH', root)   # ensure subprocesses inherit it
    from src.agent.hub.channel_registry import start_all_channels
    start_all_channels()
    # Note: the memory consolidation runner is started inside the Streamlit
    # process (dashboard/app.py _startup) — not here, since this launcher
    # process exits within seconds of spawning Streamlit.

    # Wait for Streamlit to be ready (up to 15 seconds)
    for i in range(15):
        time.sleep(1)
        if _port_in_use(8501):
            print(f"Ready after {i + 1}s — opening browser...")
            break
        print(f"  Waiting for server... ({i + 1}s)")

    webbrowser.open('http://localhost:8501')
    print("OctaMind started. You can close this window.")


if __name__ == '__main__':
    main()
