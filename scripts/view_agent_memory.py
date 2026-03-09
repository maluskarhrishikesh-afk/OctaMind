"""
View Agent Memory - Display agent memory contents.

Usage:
    python scripts/view_agent_memory.py <agent_id>
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.memory.agent_memory import get_agent_memory


def view_memory(agent_id: str):
    """View all memory for an agent."""
    memory = get_agent_memory(agent_id)

    print(f"\n{'=' * 70}")
    print(f"AGENT MEMORY: {agent_id}")
    print(f"{'=' * 70}\n")

    print("SHORT-TERM MEMORY (Recent Interactions)")
    print("-" * 70)
    recent = memory.get_recent_interactions(10)
    if recent:
        for i, interaction in enumerate(recent, 1):
            timestamp = interaction.get("timestamp", "Unknown")
            command = interaction.get("command", "Unknown")
            action = interaction.get("action", "Unknown")
            status = interaction.get("status", "N/A")
            result = interaction.get("result", status)
            metadata = interaction.get("metadata", None)

            print(f"\n{i}. [{timestamp}]")
            print(f"   Command: {command}")
            print(f"   Action:  {action}")
            print(f"   Status:  {status}")
            print(f"   Result:  {result}")
            if metadata:
                print(f"   Meta:    {metadata}")
    else:
        print("   (No interactions recorded yet)")

    print("\n\nLONG-TERM MEMORY")
    print("-" * 70)
    print(memory.get_long_term_memory())

    print("\n\nPERSONALITY")
    print("-" * 70)
    print(memory.get_personality())

    print("\n\nHABITS & BEHAVIORS")
    print("-" * 70)
    print(memory.get_habits())

    print("\n\nCURRENT CONTEXT")
    print("-" * 70)
    print(memory.get_context())

    print(f"\n{'=' * 70}")
    print(f"Memory location: {memory.memory_dir}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/view_agent_memory.py <agent_id>")
        print("\nExample: python scripts/view_agent_memory.py gmail-octopus-001")

        memory_dir = PROJECT_ROOT / "memory"
        if memory_dir.exists():
            agents = [directory.name for directory in memory_dir.iterdir() if directory.is_dir()]
            if agents:
                print("\nAvailable agents with memory:")
                for agent in agents:
                    print(f"  - {agent}")
        sys.exit(1)

    view_memory(sys.argv[1])