"""
API channel — wraps the FastAPI / uvicorn Hub server.

External bots (WhatsApp, WeChat, custom integrations) POST to
POST http://localhost:8502/hub/chat  and this process handles it.
"""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .base import BaseChannel, ChannelStatus

_ROOT = Path(__file__).parent.parent.parent.parent.parent


class APIChannel(BaseChannel):
    name = "api"
    display_name = "REST API"
    icon = "🔌"
    description = "FastAPI HTTP endpoint — external bots call POST /hub/chat."
    enabled = True
    supports_markdown = False   # callers receive plain text by default
    max_message_length = 32_000
    is_external = True

    PORT = 8502
    _process: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self.is_running():
            return
        venv_python = _ROOT / ".venv" / "Scripts" / "python.exe"
        python = str(venv_python) if venv_python.exists() else sys.executable
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_ROOT)
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        log_path = _ROOT / "logs" / "hub_api.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as log_file:
            self._process = subprocess.Popen(
                [
                    python, "-m", "uvicorn",
                    "src.agent.hub.server:app",
                    "--host", "0.0.0.0",
                    "--port", str(self.PORT),
                ],
                cwd=str(_ROOT), env=env,
                stdout=log_file, stderr=log_file,
                creationflags=creationflags,
            )

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process = None

    def is_running(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", self.PORT)) == 0

    def status(self) -> ChannelStatus:
        pid = self._process.pid if self._process else None
        return ChannelStatus(
            running=self.is_running(),
            port=self.PORT,
            pid=pid,
            detail=f"http://localhost:{self.PORT}/docs",
        )
