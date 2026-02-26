"""
Dashboard channel — the Streamlit UI.

This is the internal channel: the user opens a browser and talks directly
to the PA. It is always enabled and cannot be stopped without shutting
down the whole application.
"""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

from .base import BaseChannel, ChannelStatus

# When frozen by PyInstaller, __file__ points to a temp extraction directory.
# Use sys.executable (the .exe location) to find the real project root instead.
if getattr(sys, 'frozen', False):
    _ROOT = Path(sys.executable).parent
else:
    _ROOT = Path(__file__).parent.parent.parent.parent.parent


class DashboardChannel(BaseChannel):
    name = "dashboard"
    display_name = "Dashboard"
    icon = "🖥️"
    description = "Streamlit web dashboard — the primary browser interface."
    enabled = True
    supports_markdown = True
    max_message_length = 100_000
    is_external = False

    PORT = 8501

    def start(self) -> None:
        if self.is_running():
            return
        venv_python = _ROOT / ".venv" / "Scripts" / "python.exe"
        python = str(venv_python) if venv_python.exists() else sys.executable
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_ROOT)
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen(
            [
                python, "-m", "streamlit", "run",
                str(_ROOT / "src" / "agent" / "ui" / "dashboard" / "app.py"),
                "--server.port", str(self.PORT),
                "--server.headless", "true",
            ],
            cwd=str(_ROOT), env=env, creationflags=creationflags,
        )

    def stop(self) -> None:
        # Dashboard is the main process — stopping it shuts everything down.
        # Intentionally a no-op here; handled by the OS on exit.
        pass

    def is_running(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", self.PORT)) == 0

    def status(self) -> ChannelStatus:
        return ChannelStatus(
            running=self.is_running(),
            port=self.PORT,
            detail=f"http://localhost:{self.PORT}",
        )
