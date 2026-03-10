from __future__ import annotations

from pathlib import Path


def test_existing_runtime_state_path_falls_back_to_legacy(tmp_path, monkeypatch):
    from src.agent import runtime_paths as rp

    monkeypatch.setattr(rp, "get_workspace_root", lambda: tmp_path)
    legacy_file = tmp_path / "data" / "state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text('{"legacy": true}', encoding="utf-8")

    resolved = rp.get_existing_runtime_state_path("state.json")

    assert resolved == legacy_file


def test_migrate_legacy_runtime_state_file_copies_into_your_data(tmp_path, monkeypatch):
    from src.agent import runtime_paths as rp

    monkeypatch.setattr(rp, "get_workspace_root", lambda: tmp_path)
    legacy_file = tmp_path / "data" / "state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text('{"legacy": true}', encoding="utf-8")

    migrated = rp.migrate_legacy_runtime_state_file("state.json")

    assert migrated == tmp_path / "your_data" / "state.json"
    assert migrated.exists()
    assert migrated.read_text(encoding="utf-8") == '{"legacy": true}'
    assert legacy_file.exists()


def test_runtime_state_path_uses_canonical_your_data_when_no_legacy_exists(tmp_path, monkeypatch):
    from src.agent import runtime_paths as rp

    monkeypatch.setattr(rp, "get_workspace_root", lambda: tmp_path)

    resolved = rp.get_existing_runtime_state_path("fresh.json")

    assert resolved == tmp_path / "your_data" / "fresh.json"
    assert not resolved.exists()