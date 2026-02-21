"""
Unit tests for src/agent/core/automations/automation_config.py

Covers:
 - load / save round-trip
 - update_automation_state: enable/disable, params, interval_minutes
 - getautomations_for_agent_type
 - corrupt / missing file handling
"""

from src.agent.core.automations.automation_config import (
    AUTOMATION_CATALOG,
    get_automations_for_agent_type,
    load_automation_config,
    save_automation_config,
    update_automation_state,
)
import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────── helpers ─────────────────────────────────────────

def _agent_dir(tmp_path: Path, agent_id: str) -> Path:
    """Create a memory/<agent_id>/ folder under tmp_path and return it."""
    d = tmp_path / "memory" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _config_file(tmp_path: Path, agent_id: str) -> Path:
    return tmp_path / "memory" / agent_id / "automation_config.json"


# ─────────────────────────── load / save ─────────────────────────────────────

class TestLoadSave:
    def test_load_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert load_automation_config("nonexistent_agent") == {}

    def test_load_returns_empty_on_corrupt_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _agent_dir(tmp_path, "bad_agent")
        _config_file(tmp_path, "bad_agent").write_text(
            "{not valid json", encoding="utf-8")
        assert load_automation_config("bad_agent") == {}

    def test_save_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _agent_dir(tmp_path, "agent1")
        save_automation_config(
            "agent1", {"auto_delete_spam": {"enabled": True}})
        data = json.loads(_config_file(tmp_path, "agent1").read_text())
        assert data["auto_delete_spam"]["enabled"] is True

    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _agent_dir(tmp_path, "agent2")
        original = {
            "out_of_office": {"enabled": True, "params": {"reply_message": "OOO"}, "last_run": None}
        }
        save_automation_config("agent2", original)
        loaded = load_automation_config("agent2")
        assert loaded == original

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        """save_automation_config should create the memory/<id>/ folder if missing."""
        monkeypatch.chdir(tmp_path)
        # Do NOT pre-create the dir
        save_automation_config(
            "new_agent", {"flag_old_unread": {"enabled": False}})
        assert _config_file(tmp_path, "new_agent").exists()


# ─────────────────────────── update_automation_state ─────────────────────────

class TestUpdateAutomationState:
    def _setup(self, tmp_path, monkeypatch, agent_id="test_agent"):
        monkeypatch.chdir(tmp_path)
        _agent_dir(tmp_path, agent_id)
        return agent_id

    def test_creates_entry_when_absent(self, tmp_path, monkeypatch):
        aid = self._setup(tmp_path, monkeypatch)
        update_automation_state(aid, "auto_delete_spam", enabled=True)
        cfg = load_automation_config(aid)
        assert "auto_delete_spam" in cfg
        assert cfg["auto_delete_spam"]["enabled"] is True

    def test_disable_existing_entry(self, tmp_path, monkeypatch):
        aid = self._setup(tmp_path, monkeypatch)
        update_automation_state(aid, "auto_delete_spam", enabled=True)
        update_automation_state(aid, "auto_delete_spam", enabled=False)
        assert load_automation_config(
            aid)["auto_delete_spam"]["enabled"] is False

    def test_params_are_stored(self, tmp_path, monkeypatch):
        aid = self._setup(tmp_path, monkeypatch)
        params = {"reply_message": "Gone fishing",
                  "active_until": "2026-12-31"}
        update_automation_state(aid, "out_of_office",
                                enabled=True, params=params)
        stored = load_automation_config(aid)["out_of_office"]["params"]
        assert stored["reply_message"] == "Gone fishing"
        assert stored["active_until"] == "2026-12-31"

    def test_interval_minutes_persisted(self, tmp_path, monkeypatch):
        aid = self._setup(tmp_path, monkeypatch)
        update_automation_state(aid, "auto_delete_spam",
                                enabled=True, interval_minutes=5.0)
        cfg = load_automation_config(aid)
        assert cfg["auto_delete_spam"]["interval_minutes"] == 5.0

    def test_interval_minutes_none_does_not_overwrite(self, tmp_path, monkeypatch):
        """Calling update with interval_minutes=None must NOT erase an existing value."""
        aid = self._setup(tmp_path, monkeypatch)
        update_automation_state(aid, "auto_delete_spam",
                                enabled=True, interval_minutes=30.0)
        update_automation_state(aid, "auto_delete_spam",
                                enabled=True, interval_minutes=None)
        cfg = load_automation_config(aid)
        assert cfg["auto_delete_spam"]["interval_minutes"] == 30.0

    def test_last_run_defaults_to_null(self, tmp_path, monkeypatch):
        aid = self._setup(tmp_path, monkeypatch)
        update_automation_state(aid, "weekly_report", enabled=True)
        assert load_automation_config(aid)["weekly_report"]["last_run"] is None

    def test_existing_last_run_is_preserved(self, tmp_path, monkeypatch):
        aid = self._setup(tmp_path, monkeypatch)
        ts = "2026-02-20T10:00:00+00:00"
        save_automation_config(
            aid, {"weekly_report": {"enabled": True, "last_run": ts}})
        update_automation_state(aid, "weekly_report", enabled=False)
        assert load_automation_config(aid)["weekly_report"]["last_run"] == ts

    def test_multiple_automations_independent(self, tmp_path, monkeypatch):
        aid = self._setup(tmp_path, monkeypatch)
        update_automation_state(aid, "auto_delete_spam", enabled=True)
        update_automation_state(aid, "daily_digest",
                                enabled=False, interval_minutes=1440.0)
        cfg = load_automation_config(aid)
        assert cfg["auto_delete_spam"]["enabled"] is True
        assert cfg["daily_digest"]["enabled"] is False
        assert cfg["daily_digest"]["interval_minutes"] == 1440.0


# ─────────────────────────── catalog ─────────────────────────────────────────

class TestCatalog:
    def test_gmail_has_ten_automations(self):
        gmail = get_automations_for_agent_type("gmail")
        assert len(gmail) == 10

    def test_all_gmail_ids_present(self):
        expected = {
            "auto_delete_spam", "auto_archive_newsletters", "daily_digest",
            "auto_label_vip", "flag_old_unread", "weekly_report",
            "auto_categorize", "auto_unsubscribe", "out_of_office", "archive_old_read",
        }
        assert set(get_automations_for_agent_type("gmail").keys()) == expected

    def test_unknown_type_returns_empty(self):
        assert get_automations_for_agent_type("slack") == {}

    def test_every_gmail_entry_has_required_keys(self):
        for aid, entry in get_automations_for_agent_type("gmail").items():
            assert "label" in entry, f"{aid} missing 'label'"
            assert "interval_minutes" in entry, f"{aid} missing 'interval_minutes'"
            assert "default_params" in entry, f"{aid} missing 'default_params'"

    def test_catalog_dict_structure(self):
        assert "gmail" in AUTOMATION_CATALOG
        assert isinstance(AUTOMATION_CATALOG["gmail"], dict)
