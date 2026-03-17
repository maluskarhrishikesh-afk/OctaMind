from __future__ import annotations

import importlib
from pathlib import Path


def test_keep_awake_status_active(monkeypatch, tmp_path: Path) -> None:
    runtime_status = importlib.import_module("src.agent.system.runtime_status")

    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"runtime": {"keep_awake_when_running": true}}', encoding="utf-8")
    state_path = tmp_path / "keep_awake.json"
    state_path.write_text('{"pid": 1234}', encoding="utf-8")

    monkeypatch.setattr(runtime_status.sys, "platform", "win32")
    monkeypatch.setattr(runtime_status, "_settings_path", lambda: settings_path)
    monkeypatch.setattr(runtime_status, "_keep_awake_state_path", lambda: state_path)
    monkeypatch.setattr(runtime_status, "_is_pid_alive", lambda pid: pid == 1234)

    status = runtime_status.get_keep_awake_status()

    assert status["enabled"] is True
    assert status["running"] is True
    assert status["label"] == "Active"


def test_keep_awake_status_disabled(monkeypatch, tmp_path: Path) -> None:
    runtime_status = importlib.import_module("src.agent.system.runtime_status")

    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"runtime": {"keep_awake_when_running": false}}', encoding="utf-8")

    monkeypatch.setattr(runtime_status.sys, "platform", "win32")
    monkeypatch.setattr(runtime_status, "_settings_path", lambda: settings_path)
    monkeypatch.setattr(runtime_status, "_keep_awake_state_path", lambda: tmp_path / "missing_keep_awake.json")

    status = runtime_status.get_keep_awake_status()

    assert status["enabled"] is False
    assert status["running"] is False
    assert status["label"] == "Disabled"