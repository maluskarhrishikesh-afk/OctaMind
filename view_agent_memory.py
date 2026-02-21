"""
View Agent Memory - Display agent's memory contents

Usage:
    python view_agent_memory.py <agent_id>
"""

import json
from src.agent.memory.agent_memory import get_agent_memory
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def view_memory(agent_id: str):
    """View all memory for an agent"""

    memory = get_agent_memory(agent_id)

    print(f"\n{'='*70}")
    print(f"🧠 AGENT MEMORY: {agent_id}")
    print(f"{'='*70}\n")

    # Short-term memory
    print("📝 SHORT-TERM MEMORY (Recent Interactions)")
    print("-" * 70)
    recent = memory.get_recent_interactions(10)
    if recent:
        for i, interaction in enumerate(recent, 1):
            timestamp = interaction.get('timestamp', 'Unknown')
            command = interaction.get('command', 'Unknown')
            action = interaction.get('action', 'Unknown')
            status = interaction.get('status', 'N/A')
            result = interaction.get('result', status)
            metadata = interaction.get('metadata', None)

            print(f"\n{i}. [{timestamp}]")
            print(f"   Command: {command}")
            print(f"   Action:  {action}")
            print(f"   Status:  {status}")
            print(f"   Result:  {result}")
            if metadata:
                print(f"   Meta:    {metadata}")
    else:
        print("   (No interactions recorded yet)")

    # Long-term memory
    print(f"\n\n📚 LONG-TERM MEMORY")
    print("-" * 70)
    long_term = memory.get_long_term_memory()
    print(long_term)

    # Personality
    print(f"\n\n🎭 PERSONALITY")
    print("-" * 70)
    personality = memory.get_personality()
    print(personality)

    # Habits
    print(f"\n\n🔄 HABITS & BEHAVIORS")
    print("-" * 70)
    habits = memory.get_habits()
    print(habits)

    # Context
    print(f"\n\n🎯 CURRENT CONTEXT")
    print("-" * 70)
    context = memory.get_context()
    print(context)

    print(f"\n{'='*70}")
    print(f"📂 Memory location: {memory.memory_dir}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python view_agent_memory.py <agent_id>")
        print("\nExample: python view_agent_memory.py gmail-octopus-001")

        # List available agents
        memory_dir = Path("memory")
        if memory_dir.exists():
            agents = [d.name for d in memory_dir.iterdir() if d.is_dir()]
            if agents:
                print("\nAvailable agents with memory:")
                for agent in agents:
                    print(f"  - {agent}")
        sys.exit(1)

    agent_id = sys.argv[1]
    view_memory(agent_id)
