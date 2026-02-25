"""
Unit tests for src/agent/core/agent_manager.py

Covers:
 - create_agent: valid types, invalid type raises, default personality traits
 - get_agent / get_all_agents
 - update_agent
 - delete_agent + memory folder cleanup
 - update_personality_traits
 - AGENT_TYPES completeness
"""

from src.agent.core.agent_manager import (
    DEFAULT_PERSONALITY_TRAITS,
    AgentManager,
)
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────── fixtures ────────────────────────────────────────

@pytest.fixture
def manager(tmp_path, monkeypatch):
    """AgentManager backed by a temp directory."""
    monkeypatch.chdir(tmp_path)
    return AgentManager(storage_path=str(tmp_path / "agents.json"))


# ─────────────────────────── create_agent ────────────────────────────────────

class TestCreateAgent:
    def test_creates_agent_with_required_fields(self, manager, tmp_path):
        agent = manager.create_agent("MyBot", "gmail", "Manage email")
        assert agent["name"] == "MyBot"
        assert agent["type"] == "gmail"
        assert agent["role"] == "Manage email"
        assert "id" in agent
        assert len(agent["id"]) == 8  # uuid[:8]

    def test_created_agent_is_enabled(self, manager):
        agent = manager.create_agent("Bot", "gmail", "role")
        assert agent["enabled"] is True

    def test_invalid_type_raises(self, manager):
        with pytest.raises(ValueError, match="Invalid agent type"):
            manager.create_agent("Bot", "twitter", "role")

    def test_default_personality_traits_applied(self, manager):
        agent = manager.create_agent("Bot", "gmail", "role")
        traits = agent["config"]["personality_traits"]
        for key, val in DEFAULT_PERSONALITY_TRAITS.items():
            assert traits[key] == val

    def test_custom_personality_traits_override_defaults(self, manager):
        traits = {"tone": 9, "humor": 8}
        agent = manager.create_agent(
            "Bot", "gmail", "role", personality_traits=traits)
        stored = agent["config"]["personality_traits"]
        assert stored["tone"] == 9
        assert stored["humor"] == 8
        # Remaining defaults should still be present
        assert "verbosity" in stored

    def test_all_agent_types_accepted(self, manager):
        for atype in AgentManager.AGENT_TYPES:
            agent = manager.create_agent(f"Bot_{atype}", atype, "role")
            assert agent["type"] == atype

    def test_agent_persisted_to_json(self, manager, tmp_path):
        manager.create_agent("Persist", "gmail", "test")
        data = json.loads((tmp_path / "agents.json").read_text())
        names = [a["name"] for a in data["agents"]]
        assert "Persist" in names

    def test_memory_folder_created(self, manager, tmp_path):
        agent = manager.create_agent("MemBot", "gmail", "role")
        mem_dir = tmp_path / "memory" / agent["id"]
        assert mem_dir.exists()


# ─────────────────────────── get_agent ───────────────────────────────────────

class TestGetAgent:
    def test_get_existing_agent(self, manager):
        created = manager.create_agent("GetBot", "gmail", "role")
        fetched = manager.get_agent(created["id"])
        assert fetched is not None
        assert fetched["name"] == "GetBot"

    def test_get_nonexistent_returns_none(self, manager):
        assert manager.get_agent("deadbeef") is None

    def test_get_all_agents(self, manager):
        manager.create_agent("A", "gmail", "r1")
        manager.create_agent("B", "slack", "r2")
        agents = manager.list_agents()
        names = {a["name"] for a in agents}
        assert {"A", "B"}.issubset(names)


# ─────────────────────────── update_agent ────────────────────────────────────

class TestUpdateAgent:
    def test_update_name(self, manager):
        agent = manager.create_agent("Old", "gmail", "role")
        manager.update_agent(agent["id"], {"name": "New"})
        assert manager.get_agent(agent["id"])["name"] == "New"

    def test_update_nonexistent_returns_false(self, manager):
        result = manager.update_agent("deadbeef", {"name": "X"})
        assert result is False


# ─────────────────────────── delete_agent ────────────────────────────────────

class TestDeleteAgent:
    def test_delete_removes_from_storage(self, manager):
        agent = manager.create_agent("Del", "gmail", "role")
        agent_id = agent["id"]
        assert manager.delete_agent(agent_id) is True
        assert manager.get_agent(agent_id) is None

    def test_delete_removes_memory_folder(self, manager, tmp_path):
        agent = manager.create_agent("DelMem", "gmail", "role")
        agent_id = agent["id"]
        mem_dir = tmp_path / "memory" / agent_id
        assert mem_dir.exists()
        manager.delete_agent(agent_id)
        assert not mem_dir.exists()

    def test_delete_nonexistent_returns_false(self, manager):
        assert manager.delete_agent("deadbeef") is False


# ─────────────────────────── update_personality_traits ───────────────────────

class TestUpdatePersonalityTraits:
    def test_traits_updated_in_config(self, manager):
        agent = manager.create_agent("TraitBot", "gmail", "role")
        new_traits = {"tone": 8, "verbosity": 9,
                      "humor": 7, "empathy": 5, "proactiveness": 6}
        manager.update_personality_traits(agent["id"], new_traits)
        stored = manager.get_agent(agent["id"])["config"]["personality_traits"]
        assert stored["tone"] == 8
        assert stored["verbosity"] == 9

    def test_personality_md_rewritten(self, manager, tmp_path):
        agent = manager.create_agent("MDBot", "gmail", "role")
        manager.update_personality_traits(agent["id"], {"tone": 10})
        md = (tmp_path / "memory" / agent["id"] / "personality.md").read_text()
        assert "10" in md


# ─────────────────────────── AGENT_TYPES ─────────────────────────────────────

class TestAgentTypes:
    def test_has_six_types(self):
        assert len(AgentManager.AGENT_TYPES) == 9

    def test_all_types_have_required_keys(self):
        for atype, meta in AgentManager.AGENT_TYPES.items():
            assert "name" in meta, f"{atype} missing 'name'"
            assert "icon" in meta, f"{atype} missing 'icon'"
            assert "capabilities" in meta, f"{atype} missing 'capabilities'"

    def test_gmail_type_present(self):
        assert "gmail" in AgentManager.AGENT_TYPES


# ─────────────────────────── default traits ──────────────────────────────────

class TestDefaultPersonalityTraits:
    def test_has_five_traits(self):
        assert len(DEFAULT_PERSONALITY_TRAITS) == 5

    def test_all_values_in_range(self):
        for key, val in DEFAULT_PERSONALITY_TRAITS.items():
            assert 0 <= val <= 10, f"{key}={val} out of 0-10 range"

    def test_expected_keys_present(self):
        expected = {"tone", "verbosity", "humor", "empathy", "proactiveness"}
        assert set(DEFAULT_PERSONALITY_TRAITS.keys()) == expected
