"""
Integration test: agent creation basics.

Skills (email, files, drive, …) are *stateless* — they do NOT create a
memory folder when instantiated.  Only PA agents (ids starting with "pa_")
and the shared multi-agent hub get on-disk memory.

Uses isolated storage (tmp_path + monkeypatch.chdir) so pytest runs never
write to the real agents.json or real memory/ folder.
"""

import sys
from pathlib import Path

import pytest

from src.agent.core.agent_manager import AgentManager

# Add project root to path (kept for __main__ usage)
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_skill_agent_creation_no_memory_folder(tmp_path, monkeypatch):
    """Creating a skill agent does NOT produce a memory folder (skills are stateless)."""

    monkeypatch.chdir(tmp_path)
    manager = AgentManager(storage_path=str(tmp_path / "agents.json"))

    agent = manager.create_agent(
        name="octopus-001",
        agent_type="email",
        role="Keep inbox organized and handle email tasks",
    )

    agent_id = agent["id"]
    assert agent["name"] == "octopus-001"
    assert agent["type"] == "email"

    # Skills are stateless: no memory folder should be created
    memory_dir = tmp_path / "memory" / agent_id
    assert not memory_dir.exists(), (
        f"Unexpected memory folder for skill agent at {memory_dir}. "
        "Only pa_-prefixed PA agents should have on-disk memory."
    )

    # Cleanup
    manager.delete_agent(agent_id)


if __name__ == "__main__":
    # Manual run — uses the real agents.json; cleans up afterwards
    from src.agent.core.agent_manager import get_agent_manager

    try:
        mgr = get_agent_manager()
        a = mgr.create_agent(
            name="octopus-001",
            agent_type="email",
            role="Keep inbox organized and handle email tasks",
        )
        print(f"Created agent {a['id']}")
        memory_dir = Path("memory") / a["id"]
        if not memory_dir.exists():
            print("✅ No memory folder created — correct (skills are stateless)")
        else:
            print("❌ Memory folder unexpectedly created for skill agent")
        mgr.delete_agent(a["id"])
        print("✅ Cleaned up.")
        import sys as _sys
        _sys.exit(0)
    except Exception:
        import traceback
        traceback.print_exc()
        import sys as _sys
        _sys.exit(1)
        traceback.print_exc()
        sys.exit(1)
