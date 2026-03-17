from __future__ import annotations

import importlib
import json
from pathlib import Path


def test_start_pa_poller_requires_per_assistant_token(monkeypatch, tmp_path: Path) -> None:
    manager = importlib.import_module("src.telegram.pa_poller_manager")

    monkeypatch.setattr(manager, "_STATE_FILE", tmp_path / "running_tg_pollers.json")
    monkeypatch.setattr(
        "src.agent.hub.pa_manager.get_assistant",
        lambda pa_id: {
            "id": pa_id,
            "name": "My Assistant",
            "config": {"telegram": {"bot_token": ""}},
        },
    )

    try:
        manager.start_pa_poller("pa_1")
        assert False, "Expected missing-token startup to fail"
    except RuntimeError as exc:
        assert "No Telegram bot token" in str(exc)


def test_start_pa_poller_clears_state_when_child_exits_immediately(monkeypatch, tmp_path: Path) -> None:
    manager = importlib.import_module("src.telegram.pa_poller_manager")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "My_Assistant_stderr.txt").write_text("startup failed\n", encoding="utf-8")

    monkeypatch.setattr(manager, "_ROOT", tmp_path)
    monkeypatch.setattr(manager, "_POLLER_SCRIPT", tmp_path / "src" / "telegram" / "pa_poller_runner.py")
    monkeypatch.setattr(manager, "_STATE_FILE", tmp_path / "running_tg_pollers.json")
    monkeypatch.setattr(manager.sys, "platform", "win32")
    monkeypatch.setattr(manager, "_venv_python", lambda: str(tmp_path / ".venv" / "Scripts" / "python.exe"))
    monkeypatch.setattr(manager.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "src.agent.hub.pa_manager.get_assistant",
        lambda pa_id: {
            "id": pa_id,
            "name": "My Assistant",
            "config": {"telegram": {"bot_token": "123:abc"}},
        },
    )

    class _RunResult:
        returncode = 0
        stdout = "3456\n"
        stderr = ""

    monkeypatch.setattr(manager.subprocess, "run", lambda *args, **kwargs: _RunResult())
    monkeypatch.setattr(manager, "_is_pid_alive", lambda pid: False)

    try:
        manager.start_pa_poller("pa_1")
        assert False, "Expected fast-exit startup to fail"
    except RuntimeError as exc:
        assert "Telegram poller exited immediately" in str(exc)

    saved_state = json.loads((tmp_path / "running_tg_pollers.json").read_text(encoding="utf-8"))
    assert saved_state == {}