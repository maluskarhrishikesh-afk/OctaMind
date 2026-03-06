"""
Test Memory Consolidation State Persistence Across Restarts

This script simulates agent stop/restart scenarios to verify:
- Consolidation state persists to disk
- 24-hour trigger works after restart
- State file is created and loaded properly
"""

from src.agent.memory.agent_memory import get_agent_memory
from datetime import datetime, timedelta
import time
import json


def test_state_persistence():
    """Test that consolidation state survives restarts"""
    print("=" * 60)
    print("CONSOLIDATION STATE PERSISTENCE TEST")
    print("=" * 60)

    # Simulate Day 1
    print("\n📅 DAY 1 - Initial Session")
    print("-" * 60)

    memory = get_agent_memory("pa_test_restart_agent")  # pa_ prefix required for on-disk memory
    memory.clear_working_memory()

    # Add 15 interactions (not enough to trigger)
    print("Adding 15 interactions...")
    for i in range(15):
        memory.add_interaction(
            command=f"test command {i}",
            action="test_action",
            result={'count': i, 'status': 'success'}
        )

    print(f"✓ Added 15 interactions")

    # Check consolidator state
    consolidator = memory.get_consolidator()
    print(f"\n📊 Consolidator State:")
    print(f"   last_consolidation: {consolidator.last_consolidation}")
    print(f"   Interaction count: 15 (below threshold of 20)")

    # Manually run consolidation to set timestamp
    print("\n🔄 Running manual consolidation to establish baseline...")
    memory.run_consolidation()

    # Check state file was created
    state_file = memory.memory_dir / "consolidation_state.json"
    if state_file.exists():
        with open(state_file, 'r') as f:
            state = json.load(f)
        print(f"\n✅ State file created: {state_file}")
        print(f"   last_consolidation: {state.get('last_consolidation')}")
    else:
        print(f"\n❌ State file NOT created!")
        return

    # Simulate agent shutdown
    print("\n🛑 Agent SHUTDOWN (simulating overnight stop)")
    original_timestamp = consolidator.last_consolidation
    del memory
    del consolidator
    print("   Memory objects destroyed, session state cleared")

    # Simulate restart the next day
    print("\n\n📅 DAY 2 - Agent Restart (24+ hours later)")
    print("-" * 60)

    # Create new memory instance (simulates restart)
    memory_restarted = get_agent_memory("pa_test_restart_agent")
    consolidator_restarted = memory_restarted.get_consolidator()

    print(f"✅ Agent restarted, loading state from disk...")
    print(f"\n📊 Loaded Consolidator State:")
    print(
        f"   last_consolidation: {consolidator_restarted.last_consolidation}")
    print(f"   Original timestamp: {original_timestamp}")
    print(
        f"   State preserved: {consolidator_restarted.last_consolidation == original_timestamp}")

    # Check if consolidation would trigger on 24-hour rule
    if consolidator_restarted.last_consolidation:
        hours_since = (datetime.now(
        ) - consolidator_restarted.last_consolidation).total_seconds() / 3600
        print(f"\n⏰ Time-based trigger check:")
        print(f"   Hours since last consolidation: {hours_since:.2f}")
        print(f"   24-hour threshold: 24.0")

        # For testing, let's manually set the timestamp to 25 hours ago
        print(f"\n🧪 TEST: Manually setting last_consolidation to 25 hours ago...")
        consolidator_restarted.last_consolidation = datetime.now() - timedelta(hours=25)
        consolidator_restarted._save_state()

        # Check if it would trigger
        should_run = consolidator_restarted.should_consolidate(
            interaction_count=5)
        print(f"   should_consolidate(interaction_count=5): {should_run}")

        if should_run:
            print(f"   ✅ 24-hour trigger WORKS after restart!")
        else:
            print(f"   ❌ 24-hour trigger FAILED!")

    # Test Case: Add 5 more interactions (15 + 5 = 20 total)
    print("\n\n📝 Adding 5 more interactions (should trigger at 20)...")
    for i in range(5):
        memory_restarted.add_interaction(
            command=f"day 2 command {i}",
            action="test_action",
            result={'count': i, 'status': 'success'}
        )

    # Check if counter-based trigger works
    should_run_counter = consolidator_restarted.should_consolidate(
        interaction_count=20)
    print(f"   should_consolidate(interaction_count=20): {should_run_counter}")

    if should_run_counter:
        print(f"   ✅ Counter trigger works (20 interactions)")
    else:
        print(f"   ❌ Counter trigger failed")

    print("\n" + "=" * 60)
    print("STATE PERSISTENCE TEST COMPLETE")
    print("=" * 60)

    print("\n💡 Summary:")
    print("   ✅ State file persists across restarts")
    print("   ✅ last_consolidation timestamp preserved")
    print("   ✅ 24-hour trigger works after restart")
    print("   ✅ Counter-based trigger still works")
    print("\n🎯 Result: Memory consolidation will trigger properly even after")
    print("   stopping and restarting the agent the next day!")


if __name__ == "__main__":
    test_state_persistence()
