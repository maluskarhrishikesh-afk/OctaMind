"""
Test Agent Memory System
"""

from src.agent.memory.agent_memory import get_agent_memory
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_memory_system():
    """Test the agent memory system"""

    print("🧠 Testing Agent Memory System")
    print("=" * 60)

    # Create memory for test agent
    agent_id = "test_agent_001"
    memory = get_agent_memory(agent_id)

    print(f"\n✅ Created memory for agent: {agent_id}")
    print(f"📂 Memory location: {memory.memory_dir}")

    # Test short-term memory
    print("\n1. Testing Short-Term Memory...")
    memory.add_interaction(
        command="Delete all emails from LinkedIn",
        action="delete",
        result={"status": "success", "deleted_count": 50},
        metadata={"sender": "LinkedIn"}
    )

    memory.add_interaction(
        command="Count my emails",
        action="count",
        result={"status": "success", "total": 1234, "unread": 42}
    )

    recent = memory.get_recent_interactions(2)
    print(f"   ✅ Added 2 interactions")
    print(f"   📝 Recent: {len(recent)} interactions stored")

    # Test long-term memory
    print("\n2. Testing Long-Term Memory...")
    memory.update_long_term_memory(
        "User Preferences",
        "- User prefers to delete promotional emails weekly\n- Likes seeing full email body"
    )
    print("   ✅ Updated preferences")

    # Test personality
    print("\n3. Testing Personality...")
    personality = memory.get_personality()
    print(f"   ✅ Personality loaded ({len(personality)} chars)")

    # Test habits
    print("\n4. Testing Habits...")
    memory.add_habit(
        "Trigger-Based",
        "When inbox > 1000 emails, suggest cleanup"
    )
    print("   ✅ Added habit")

    # Test context
    print("\n5. Testing Context...")
    memory.update_context(
        "Working Memory",
        "- Last action: Deleted 50 LinkedIn emails\n- User seems focused on inbox cleanup"
    )
    print("   ✅ Updated context")

    # Get full context for LLM
    print("\n6. Testing LLM Context...")
    llm_context = memory.get_full_context_for_llm()
    print(f"   ✅ Generated LLM context ({len(llm_context)} chars)")
    print("\n   Preview:")
    print("   " + "\n   ".join(llm_context.split('\n')[:15]))
    print("   ...")

    print("\n" + "=" * 60)
    print(f"✅ All tests passed!")
    print(f"📂 Check memory files at: {memory.memory_dir}")
    print("\nMemory files created:")
    for file in memory.memory_dir.iterdir():
        print(f"  - {file.name}")


if __name__ == "__main__":
    test_memory_system()
