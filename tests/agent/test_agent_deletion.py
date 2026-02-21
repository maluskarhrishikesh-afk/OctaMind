"""
Test Agent Deletion with Memory Cleanup

This script tests that deleting an agent also removes its memory.
"""

from src.agent.memory.agent_memory import get_agent_memory
from src.agent.core.agent_manager import get_agent_manager
import sys
from pathlib import Path
import time

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_agent_deletion():
    """Test creating, using, and deleting an agent"""

    print("🧪 Testing Agent Deletion with Memory Cleanup")
    print("=" * 70)

    manager = get_agent_manager()

    # Step 1: Create test agent
    print("\n1️⃣ Creating test agent...")
    agent = manager.create_agent(
        name="Test Delete Agent",
        agent_type="gmail",
        role="Test agent for deletion testing"
    )
    agent_id = agent['id']
    print(f"   ✅ Created agent: {agent_id}")

    # Step 2: Create memory for the agent
    print("\n2️⃣ Creating memory for agent...")
    memory = get_agent_memory(agent_id)

    # Add some interactions
    memory.add_interaction(
        command="Test command 1",
        action="test",
        result={"status": "success"}
    )
    memory.add_interaction(
        command="Test command 2",
        action="test",
        result={"status": "success"}
    )

    memory.update_long_term_memory("Test", "This is test data")
    print(f"   ✅ Created memory with 2 interactions")

    # Step 3: Verify memory folder exists
    memory_dir = Path("memory") / agent_id
    print(f"\n3️⃣ Verifying memory folder exists...")
    if memory_dir.exists():
        files = list(memory_dir.iterdir())
        print(f"   ✅ Memory folder exists: {memory_dir}")
        print(f"   📁 Files: {[f.name for f in files]}")
    else:
        print(f"   ❌ Memory folder not found!")
        return False

    # Step 4: Delete the agent
    print(f"\n4️⃣ Deleting agent {agent_id}...")
    success = manager.delete_agent(agent_id)

    if success:
        print(f"   ✅ Agent deleted from agents.json")
    else:
        print(f"   ❌ Failed to delete agent")
        return False

    # Step 5: Verify memory folder is deleted
    print(f"\n5️⃣ Verifying memory cleanup...")
    time.sleep(0.5)  # Small delay to ensure filesystem sync

    if not memory_dir.exists():
        print(f"   ✅ Memory folder deleted: {memory_dir}")
    else:
        print(f"   ❌ Memory folder still exists!")
        return False

    # Step 6: Verify agent is removed from list
    print(f"\n6️⃣ Verifying agent is removed from list...")
    agents = manager.list_agents()
    agent_ids = [a['id'] for a in agents]

    if agent_id not in agent_ids:
        print(f"   ✅ Agent removed from agents list")
    else:
        print(f"   ❌ Agent still in list!")
        return False

    print("\n" + "=" * 70)
    print("✅ All tests passed! Agent deletion works correctly.")
    print("\n📋 Summary:")
    print("   • Agent configuration deleted from agents.json")
    print("   • Memory folder completely removed")
    print("   • All memory files (interactions, personality, etc.) cleaned up")
    print("   • Storage optimized")

    return True


if __name__ == "__main__":
    try:
        success = test_agent_deletion()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
