"""
Test LLM-based email command parsing using GitHub Models API
"""

from src.agent.llm.llm_parser import parse_with_llm
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_llm_parser():
    """Test various command types with LLM parser"""

    test_commands = [
        "Count all emails",
        "Show me 10 latest emails",
        "Delete all emails from LinkedIn",
        "Send email to john@example.com with subject Test and message Hello World",
        "List unread emails",
        "Could you please delete all messages from Quora?",
        "I need to see my recent emails",
        "Help me clean up emails from Facebook notifications",
    ]

    print("Testing LLM Email Command Parser")
    print("=" * 60)

    for i, command in enumerate(test_commands, 1):
        print(f"\n{i}. Command: {command}")
        try:
            result = parse_with_llm(command)
            print(f"   Action: {result.get('action')}")
            print(f"   Params: {result.get('params')}")
        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    test_llm_parser()
