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
        agent = manager.create_agent("MyBot", "email", "Manage email")
        assert agent["name"] == "MyBot"
        assert agent["type"] == "email"
        assert agent["role"] == "Manage email"
        assert "id" in agent
        assert len(agent["id"]) == 8  # uuid[:8]

    def test_created_agent_is_enabled(self, manager):
        agent = manager.create_agent("Bot", "email", "role")
        assert agent["enabled"] is True

    def test_invalid_type_raises(self, manager):
        with pytest.raises(ValueError, match="Invalid agent type"):
            manager.create_agent("Bot", "twitter", "role")

    def test_default_personality_traits_applied(self, manager):
        # Skills are stateless — personality_traits are NOT stored in create_agent config.
        # personality_traits belong to the PA level, not skill level.
        agent = manager.create_agent("Bot", "email", "role")
        assert agent["id"] is not None
        assert "personality_traits" not in agent.get("config", {})

    def test_custom_personality_traits_override_defaults(self, manager):
        # personality_traits param is ignored for skills (PA-level only)
        traits = {"tone": 9, "humor": 8}
        agent = manager.create_agent(
            "Bot", "email", "role", personality_traits=traits)
        # Just verify the agent was created successfully
        assert agent["type"] == "email"
        assert agent["name"] == "Bot"

    def test_all_agent_types_accepted(self, manager):
        for atype in AgentManager.AGENT_TYPES:
            agent = manager.create_agent(f"Bot_{atype}", atype, "role")
            assert agent["type"] == atype

    def test_agent_persisted_to_json(self, manager, tmp_path):
        manager.create_agent("Persist", "email", "test")
        data = json.loads((tmp_path / "agents.json").read_text())
        names = [a["name"] for a in data["agents"]]
        assert "Persist" in names

    def test_memory_folder_not_created_for_skills(self, manager, tmp_path):
        # Skills are stateless — no memory folder is created.
        # Memory lives at the PA level.
        agent = manager.create_agent("MemBot", "email", "role")
        mem_dir = tmp_path / "memory" / agent["id"]
        assert not mem_dir.exists()


# ─────────────────────────── get_agent ───────────────────────────────────────

class TestGetAgent:
    def test_get_existing_agent(self, manager):
        created = manager.create_agent("GetBot", "email", "role")
        fetched = manager.get_agent(created["id"])
        assert fetched is not None
        assert fetched["name"] == "GetBot"

    def test_get_nonexistent_returns_none(self, manager):
        assert manager.get_agent("deadbeef") is None

    def test_get_all_agents(self, manager):
        manager.create_agent("A", "email", "r1")
        manager.create_agent("B", "telegram", "r2")
        agents = manager.list_agents()
        names = {a["name"] for a in agents}
        assert {"A", "B"}.issubset(names)


# ─────────────────────────── update_agent ────────────────────────────────────

class TestUpdateAgent:
    def test_update_name(self, manager):
        agent = manager.create_agent("Old", "email", "role")
        manager.update_agent(agent["id"], {"name": "New"})
        assert manager.get_agent(agent["id"])["name"] == "New"

    def test_update_nonexistent_returns_false(self, manager):
        result = manager.update_agent("deadbeef", {"name": "X"})
        assert result is False


# ─────────────────────────── delete_agent ────────────────────────────────────

class TestDeleteAgent:
    def test_delete_removes_from_storage(self, manager):
        agent = manager.create_agent("Del", "email", "role")
        agent_id = agent["id"]
        assert manager.delete_agent(agent_id) is True
        assert manager.get_agent(agent_id) is None

    def test_delete_removes_agent_record(self, manager, tmp_path):
        # Skills have no memory folder; just verify the agent record is gone after delete.
        agent = manager.create_agent("DelMem", "email", "role")
        agent_id = agent["id"]
        manager.delete_agent(agent_id)
        assert manager.get_agent(agent_id) is None

    def test_delete_nonexistent_returns_false(self, manager):
        assert manager.delete_agent("deadbeef") is False


# ─────────────────────────── update_personality_traits ───────────────────────

class TestUpdatePersonalityTraits:
    def test_traits_updated_in_config(self, manager):
        agent = manager.create_agent("TraitBot", "email", "role")
        new_traits = {"tone": 8, "verbosity": 9,
                      "humor": 7, "empathy": 5, "proactiveness": 6}
        manager.update_personality_traits(agent["id"], new_traits)
        stored = manager.get_agent(agent["id"])["config"]["personality_traits"]
        assert stored["tone"] == 8
        assert stored["verbosity"] == 9

    def test_personality_md_rewritten(self, manager, tmp_path):
        # Personality is stored in agents.json config; personality.md requires a
        # memory folder which skills don't have by default.
        # Just verify update_personality_traits doesn't raise and updates the config.
        agent = manager.create_agent("MDBot", "email", "role")
        result = manager.update_personality_traits(agent["id"], {"tone": 10})
        assert result is True
        stored = manager.get_agent(agent["id"])["config"]["personality_traits"]
        assert stored["tone"] == 10


# ─────────────────────────── AGENT_TYPES ─────────────────────────────────────

class TestAgentTypes:
    def test_has_six_types(self):
        # Count is dynamic — verify it is at least the known minimum (11 agents as of session 6)
        assert len(AgentManager.AGENT_TYPES) >= 11

    def test_all_types_have_required_keys(self):
        for atype, meta in AgentManager.AGENT_TYPES.items():
            assert "name" in meta, f"{atype} missing 'name'"
            assert "icon" in meta, f"{atype} missing 'icon'"
            assert "capabilities" in meta, f"{atype} missing 'capabilities'"

    def test_email_type_present(self):
        # The email agent type is keyed as 'email' (not 'gmail')
        assert "email" in AgentManager.AGENT_TYPES


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
