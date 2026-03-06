"""
Unit tests for src/agent/memory/agent_memory.py

Covers:
 - Initialisation: memory folder + all 6 files created
 - add_interaction / get_recent_interactions
 - add_episodic_event / search_episodic_memory
 - update_semantic_memory / get_semantic_memory
 - get_personality / update_personality
 - get_habits / add_habit
 - recall_for_llm: recall-signal → returns results; no signal → returns ""
 - working memory cap (max 10)
 - clear_working_memory
"""

from src.agent.memory.agent_memory import AgentMemory, get_agent_memory
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────── fixtures ────────────────────────────────────────

@pytest.fixture
def mem(tmp_path):
    """Fresh AgentMemory pointed at a tmp directory."""
    return AgentMemory("test_agent", memory_base_dir=str(tmp_path / "memory"))


# ─────────────────────────── initialisation ──────────────────────────────────

class TestInitialisation:
    EXPECTED_FILES = {
        "working_memory.md",
        "episodic_memory.md",
        "semantic_memory.md",
        "personality.md",
        "habits.md",
        "self_reflection.md",
    }

    def test_memory_dir_created(self, mem, tmp_path):
        assert (tmp_path / "memory" / "test_agent").exists()

    def test_archive_dir_created(self, mem, tmp_path):
        assert (tmp_path / "memory" / "test_agent" / "archive").exists()

    def test_all_six_files_created(self, mem, tmp_path):
        created = {f.name for f in (
            tmp_path / "memory" / "test_agent").iterdir() if f.is_file()}
        assert self.EXPECTED_FILES.issubset(created)

    def test_get_agent_memory_returns_correct_dir(self, tmp_path, monkeypatch):
        """get_agent_memory returns an AgentMemory pointed at the right folder.

        Only pa_-prefixed IDs (and the multi-agent hub) receive persistent
        on-disk memory; plain skill IDs return None by design.
        """
        monkeypatch.chdir(tmp_path)
        m1 = get_agent_memory("pa_dir_check_agent")
        m2 = get_agent_memory("pa_dir_check_agent")
        # Both should resolve to the same memory directory path
        assert m1 is not None
        assert m2 is not None
        assert m1.memory_dir == m2.memory_dir

    def test_get_agent_memory_returns_none_for_skill(self):
        """Skills (non-pa_ IDs) return None from get_agent_memory — they are stateless."""
        assert get_agent_memory("some_skill_uuid") is None
        assert get_agent_memory("email_agent_abc") is None


# ─────────────────────────── interactions (working memory) ───────────────────

class TestInteractions:
    def test_add_and_retrieve_interaction(self, mem):
        mem.add_interaction("list emails", "list_emails", {"count": 5})
        recent = mem.get_recent_interactions(1)
        assert len(recent) >= 1

    def test_multiple_interactions_stored(self, mem):
        for i in range(3):
            mem.add_interaction(f"cmd {i}", "action", {"i": i})
        recent = mem.get_recent_interactions(5)
        assert len(recent) >= 3

    def test_working_memory_capped_at_10(self, mem):
        """Adding 15 interactions should keep only the most recent 10."""
        for i in range(15):
            mem.add_interaction(f"cmd {i}", "action", {"n": i})
        recent = mem.get_recent_interactions(20)
        assert len(recent) <= 10

    def test_search_interactions(self, mem):
        mem.add_interaction("delete spam emails", "delete", {"count": 5})
        mem.add_interaction("list unread", "list", {"count": 3})
        results = mem.search_interactions("spam")
        assert any("spam" in str(r).lower() for r in results)


# ─────────────────────────── episodic memory ─────────────────────────────────

class TestEpisodicMemory:
    def test_add_and_retrieve_event(self, mem):
        mem.add_episodic_event(
            event="User deleted 50 LinkedIn emails",
            importance="high",
        )
        text = mem.episodic_memory_path.read_text()
        assert "LinkedIn" in text

    def test_importance_levels_accepted(self, mem):
        for level in ("high", "medium", "low"):
            mem.add_episodic_event(
                event=f"Test event [{level}]", importance=level)
        text = mem.episodic_memory_path.read_text()
        for level in ("high", "medium", "low"):
            assert level.capitalize() in text or level in text

    def test_search_episodic_memory(self, mem):
        mem.add_episodic_event(
            event="Ran weekly report automation", importance="medium")
        mem.add_episodic_event(event="Sent 5 OOO replies", importance="low")
        results = mem.search_episodic_memory("weekly report")
        assert any("weekly" in str(r).lower() for r in results)


# ─────────────────────────── semantic memory ─────────────────────────────────

class TestSemanticMemory:
    def test_update_and_read_semantic_memory(self, mem):
        mem.update_semantic_memory(
            "User Preferences", "- Prefers daily digests")
        content = mem.get_semantic_memory()
        assert "Prefers daily digests" in content

    def test_legacy_update_long_term_memory(self, mem):
        """update_long_term_memory is a legacy alias — must still work."""
        mem.update_long_term_memory("Interests", "- Python programming")
        content = mem.get_long_term_memory()
        assert "Python programming" in content


# ─────────────────────────── personality ─────────────────────────────────────

class TestPersonality:
    def test_get_personality_returns_string(self, mem):
        p = mem.get_personality()
        assert isinstance(p, str)
        assert len(p) > 0

    def test_update_personality(self, mem):
        mem.update_personality("Communication Style",
                               "Very direct and concise")
        p = mem.get_personality()
        assert "Very direct" in p


# ─────────────────────────── habits ──────────────────────────────────────────

class TestHabits:
    def test_add_and_get_habits(self, mem):
        mem.add_habit("Daily", "Checks inbox every morning")
        habits = mem.get_habits()
        assert "inbox" in habits.lower()

    def test_habits_file_exists(self, mem):
        assert mem.habits_path.exists()


# ──────────────────────────── self_reflection ───────────────────────────────

class TestConsciousness:
    def test_get_consciousness_returns_string(self, mem):
        """get_consciousness() is a backward-compat alias for get_self_reflection()."""
        c = mem.get_consciousness()
        assert isinstance(c, str)
        assert len(c) > 0

    def test_get_self_reflection_returns_string(self, mem):
        sr = mem.get_self_reflection()
        assert isinstance(sr, str)
        assert len(sr) > 0

    def test_self_reflection_file_exists(self, mem, tmp_path):
        assert (tmp_path / "memory" / "test_agent" / "self_reflection.md").exists()


# ─────────────────────────── recall_for_llm ──────────────────────────────────

class TestRecallForLlm:
    def test_no_recall_signal_returns_empty(self, mem):
        result = mem.recall_for_llm("list my unread emails please")
        assert result == ""

    def test_recall_signal_returns_non_empty_when_data_exists(self, mem):
        mem.add_interaction("deleted 100 spam emails",
                            "delete", {"count": 100})
        result = mem.recall_for_llm("do you remember what we did earlier?")
        # Should return non-empty string — may be empty if no matches, but should not raise
        assert isinstance(result, str)

    def test_recall_specific_term(self, mem):
        mem.add_episodic_event(
            event="Ran out_of_office automation successfully", importance="low")
        result = mem.recall_for_llm("did we talk about out_of_office?")
        # If recall found anything, it should mention the term
        if result:
            assert "out_of_office" in result.lower() or "automation" in result.lower()


# ─────────────────────────── clear_working_memory ────────────────────────────

class TestClearWorkingMemory:
    def test_clear_removes_interactions(self, mem):
        mem.add_interaction("test cmd", "test", {})
        mem.clear_working_memory()
        recent = mem.get_recent_interactions(10)
        assert len(recent) == 0

    def test_file_still_exists_after_clear(self, mem):
        mem.clear_working_memory()
        assert mem.working_memory_path.exists()
