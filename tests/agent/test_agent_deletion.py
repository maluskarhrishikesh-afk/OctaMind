"""
Test Agent Deletion with Memory Cleanup.

Uses isolated storage (tmp_path + monkeypatch.chdir) so pytest runs never
write to the real agents.json or real memory/ folder.
"""

import sys
import time
from pathlib import Path

import pytest

from src.agent.core.agent_manager import AgentManager
from src.agent.memory.agent_memory import AgentMemory

# Add project root to path (kept for __main__ usage)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_agent_deletion(tmp_path, monkeypatch):
    """Test creating, using, and deleting an agent — in isolated tmp storage."""

    # Redirect all relative-path operations (agents.json + memory/) to tmp_path
    monkeypatch.chdir(tmp_path)
    manager = AgentManager(storage_path=str(tmp_path / "agents.json"))

    print("🧪 Testing Agent Deletion with Memory Cleanup")
    print("=" * 70)

    # Step 1: Create test agent
    print("\n1️⃣ Creating test agent...")
    agent = manager.create_agent(
        name="Test Delete Agent",
        agent_type="email",
        role="Test agent for deletion testing",
    )
    agent_id = agent["id"]
    print(f"   ✅ Created agent: {agent_id}")

    # Step 2: Create additional memory for the agent
    print("\n2️⃣ Creating memory for agent...")
    # Directly instantiate AgentMemory (bypasses the pa_-prefix guard used
    # by get_agent_memory; skills are stateless by design, but we still want
    # to verify that any stray memory folder is cleaned up on deletion).
    memory = AgentMemory(agent_id, memory_base_dir=str(tmp_path / "memory"))

    memory.add_interaction(
        command="Test command 1",
        action="test",
        result={"status": "success"},
    )
    memory.add_interaction(
        command="Test command 2",
        action="test",
        result={"status": "success"},
    )
    memory.update_long_term_memory("Test", "This is test data")
    print("   ✅ Created memory with 2 interactions")

    # Step 3: Verify memory folder exists
    memory_dir = tmp_path / "memory" / agent_id
    print("\n3️⃣ Verifying memory folder exists...")
    assert memory_dir.exists(), f"Memory folder not found at {memory_dir}"
    files = list(memory_dir.iterdir())
    print(
        f"   ✅ Memory folder exists with {len(files)} file(s): {[f.name for f in files]}")

    # Step 4: Delete the agent
    print(f"\n4️⃣ Deleting agent {agent_id}...")
    success = manager.delete_agent(agent_id)
    assert success, "delete_agent() returned False — deletion failed"
    print("   ✅ Agent deleted from agents.json")

    # Step 5: Verify memory folder is deleted
    print("\n5️⃣ Verifying memory cleanup...")
    time.sleep(0.1)
    assert not memory_dir.exists(
    ), f"Memory folder still exists at {memory_dir}"
    print("   ✅ Memory folder deleted")

    # Step 6: Verify agent is removed from list
    print("\n6️⃣ Verifying agent is removed from list...")
    agent_ids = [a["id"] for a in manager.list_agents()]
    assert agent_id not in agent_ids, "Agent still present in agents list after deletion"
    print("   ✅ Agent removed from agents list")

    print("\n" + "=" * 70)
    print("✅ All checks passed — deletion works correctly.")


if __name__ == "__main__":
    # Manual run — uses the real agents.json; cleans up afterwards
    from src.agent.core.agent_manager import get_agent_manager

    try:
        mgr = get_agent_manager()
        a = mgr.create_agent(
            name="Test Delete Agent",
            agent_type="gmail",
            role="Test agent for deletion testing",
        )
        agent_id = a["id"]
        print(f"Created: {agent_id}")
        mem = get_agent_memory(agent_id)
        mem.add_interaction("cmd", "test", {"status": "ok"})
        memory_dir = Path("memory") / agent_id
        print(f"Memory folder exists: {memory_dir.exists()}")
        ok = mgr.delete_agent(agent_id)
        print(f"Deleted: {ok}")
        print(f"Memory folder gone: {not memory_dir.exists()}")
        sys.exit(0 if ok else 1)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        sys.exit(1)
