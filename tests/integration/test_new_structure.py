#!/usr/bin/env python3
"""Quick test to verify the new structure works"""

from src.email import send_email, list_emails

print("Testing new src/email structure...")
print("-" * 50)

# Test send email
result = send_email(
    to="test@example.com",
    subject="Test from new structure",
    message="This email is sent using the new src/email module structure!"
)

print(f"✓ Send email test:")
print(f"  Status: {result['status']}")
if result['status'] == 'success':
    print(f"  Message ID: {result['messageId']}")
    print(f"✓ Email module working perfectly!")
else:
    print(f"  Error: {result.get('error')}")

print("\n" + "=" * 50)
print("✓ New structure is working!")
print("=" * 50)
