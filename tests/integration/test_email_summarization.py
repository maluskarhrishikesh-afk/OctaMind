"""
Test Email Summarization Features

This script tests the new email summarization functionality.
"""

from src.email import (
    list_emails,
    summarize_email,
    summarize_thread,
    generate_daily_digest
)
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_list_emails():
    """Test listing emails to get message IDs"""
    print("\n" + "=" * 70)
    print("📧 Testing: List Recent Emails")
    print("=" * 70)

    try:
        emails = list_emails(query='', max_results=3)

        if not emails:
            print("❌ No emails found. Make sure your Gmail account has emails.")
            return None

        print(f"✅ Found {len(emails)} emails:")
        for i, email in enumerate(emails, 1):
            print(f"\n{i}. Subject: {email['subject']}")
            print(f"   From: {email['sender']}")
            print(f"   ID: {email['id']}")
            print(f"   Snippet: {email['snippet'][:100]}...")

        return emails[0]['id'] if emails else None

    except Exception as e:
        print(f"❌ Error listing emails: {e}")
        return None


def test_summarize_email(message_id):
    """Test single email summarization"""
    print("\n" + "=" * 70)
    print("📝 Testing: Email Summarization")
    print("=" * 70)

    try:
        result = summarize_email(message_id)

        if result.get('status') == 'error':
            print(f"❌ Error: {result.get('message')}")
            print(f"   Details: {result.get('error')}")
            return False

        print(f"✅ Email Summarization Successful!")
        print(f"\nSubject: {result.get('subject')}")
        print(f"From: {result.get('sender')}")
        print(f"Word Count: {result.get('word_count')}")
        print(f"\nSummary:\n{result.get('summary')}")

        if result.get('key_points'):
            print(f"\nKey Points:")
            for point in result['key_points']:
                print(f"  • {point}")

        if result.get('action_items'):
            print(f"\nAction Items:")
            for item in result['action_items']:
                print(f"  ✅ {item}")

        print(f"\nSentiment: {result.get('sentiment')}")

        if result.get('note'):
            print(f"\nNote: {result['note']}")

        return True

    except Exception as e:
        print(f"❌ Error summarizing email: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_daily_digest():
    """Test daily digest generation"""
    print("\n" + "=" * 70)
    print("📅 Testing: Daily Digest")
    print("=" * 70)

    try:
        result = generate_daily_digest(max_emails=10)

        if result.get('status') == 'error':
            print(f"❌ Error: {result.get('message')}")
            print(f"   Details: {result.get('error')}")
            return False

        print(f"✅ Daily Digest Generated!")
        print(f"\nDate: {result.get('date')}")
        print(f"Total Emails: {result.get('total_emails')}")
        print(f"\nSummary:\n{result.get('summary')}")

        if result.get('highlights'):
            print(f"\nHighlights:")
            for highlight in result['highlights']:
                print(f"  ⭐ {highlight}")

        if result.get('top_senders'):
            print(f"\nTop Senders:")
            for sender, count in result['top_senders']:
                print(f"  • {sender}: {count} email(s)")

        if result.get('note'):
            print(f"\nNote: {result['note']}")

        return True

    except Exception as e:
        print(f"❌ Error generating daily digest: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  Email Summarization Tests".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")

    # Test 1: List emails and get message ID
    message_id = test_list_emails()

    if not message_id:
        print("\n⚠️ Cannot proceed with summarization tests without email IDs")
        print("   Please ensure your Gmail account has some emails.")
        return

    # Test 2: Summarize single email
    test_summarize_email(message_id)

    # Test 3: Generate daily digest
    test_daily_digest()

    # Summary
    print("\n" + "=" * 70)
    print("✅ All Summarization Tests Completed!")
    print("=" * 70)
    print("\n💡 Tip: Try these commands in the Email Agent:")
    print("   • 'Summarize email [message_id]'")
    print("   • 'Generate daily digest'")
    print("   • 'Show me today's email summary'")
    print()


if __name__ == "__main__":
    main()
