"""
Test script to verify COUNT action parsing
"""

from src.agent.ui.email_agent_ui import parse_email_command, execute_email_action, format_email_result


def test_count_command():
    print("Testing COUNT action parsing")
    print("=" * 50)

    # Test different count commands
    test_commands = [
        "Can you count the total number of emails?",
        "How many emails do I have?",
        "Show total count of emails",
        "Count my emails"
    ]

    for cmd in test_commands:
        print(f"\nCommand: {cmd}")
        parsed = parse_email_command(cmd, "")
        print(f"Parsed action: {parsed['action']}")

        if parsed['action'] == 'count':
            result = execute_email_action(parsed)
            formatted = format_email_result(result, 'count')
            print(f"Result:\n{formatted}")
        else:
            print(f"ERROR: Expected 'count' but got '{parsed['action']}'")


if __name__ == "__main__":
    test_count_command()
