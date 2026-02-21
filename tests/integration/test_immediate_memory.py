"""
Quick test to verify memory is created on agent creation.

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


def test_immediate_memory_creation(tmp_path, monkeypatch):
    """Test that memory is created immediately when agent is created."""

    # Redirect all relative-path operations (agents.json + memory/) to tmp_path
    monkeypatch.chdir(tmp_path)
    manager = AgentManager(storage_path=str(tmp_path / "agents.json"))

    print("🧪 Testing Immediate Memory Creation")
    print("=" * 70)

    print("\n📋 Creating agent 'octopus-001'...")
    agent = manager.create_agent(
        name="octopus-001",
        agent_type="gmail",
        role="Keep inbox organized and handle email tasks",
    )

    agent_id = agent["id"]
    print(f"✅ Agent created with ID: {agent_id}")
    print(f"   Name: {agent['name']}")
    print(f"   Type: {agent['type']}")

    # Check if memory folder exists (relative to tmp_path via monkeypatch.chdir)
    memory_dir = tmp_path / "memory" / agent_id
    print("\n📂 Checking memory folder...")

    assert memory_dir.exists(), f"Memory folder not found at {memory_dir}"

    files = list(memory_dir.iterdir())
    print(f"✅ Memory folder created: {memory_dir}")
    print("\n📄 Memory files:")
    for file in files:
        print(f"   • {file.name}")

    assert len(
        files) > 0, "Memory folder is empty — expected at least one memory file"
    print("\n✅ Memory created immediately on agent creation!")


if __name__ == "__main__":
    # Manual run — uses the real agents.json; cleans up afterwards
    from src.agent.core.agent_manager import get_agent_manager

    try:
        mgr = get_agent_manager()
        a = mgr.create_agent(
            name="octopus-001",
            agent_type="gmail",
            role="Keep inbox organized and handle email tasks",
        )
        print(f"Created agent {a['id']}")
        memory_dir = Path("memory") / a["id"]
        if memory_dir.exists():
            print(f"✅ Memory folder OK: {list(memory_dir.iterdir())}")
        else:
            print("❌ Memory folder missing")
        mgr.delete_agent(a["id"])
        print("✅ Cleaned up.")
        sys.exit(0)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        sys.exit(1)
