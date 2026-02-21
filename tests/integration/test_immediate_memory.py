"""
Quick test to verify memory is created on agent creation
"""

from src.agent.core.agent_manager import get_agent_manager
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_immediate_memory_creation():
    """Test that memory is created immediately when agent is created"""

    print("🧪 Testing Immediate Memory Creation")
    print("=" * 70)

    manager = get_agent_manager()

    print("\n📋 Creating agent 'octopus-001'...")
    agent = manager.create_agent(
        name="octopus-001",
        agent_type="gmail",
        role="Keep inbox organized and handle email tasks"
    )

    agent_id = agent['id']
    print(f"✅ Agent created with ID: {agent_id}")
    print(f"   Name: {agent['name']}")
    print(f"   Type: {agent['type']}")

    # Check if memory folder exists
    memory_dir = Path("memory") / agent_id
    print(f"\n📂 Checking memory folder...")

    if memory_dir.exists():
        print(f"✅ Memory folder created: {memory_dir}")
        files = list(memory_dir.iterdir())
        print(f"\n📄 Memory files:")
        for file in files:
            print(f"   • {file.name}")
        print(f"\n✅ SUCCESS: Memory created immediately on agent creation!")
    else:
        print(f"❌ FAIL: Memory folder not found at {memory_dir}")
        return False

    print("\n" + "=" * 70)
    print("✅ Test passed! Memory is now created immediately.")
    return True


if __name__ == "__main__":
    try:
        success = test_immediate_memory_creation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
