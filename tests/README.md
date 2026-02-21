# Tests

This directory contains all test files organized by functionality.

## Structure

### `email/`
Tests for Gmail integration and email operations:
- `test_email_body.py` - Test email body content extraction
- `test_inbox_count.py` - Test inbox statistics/counting
- `test_delete_emails.py` - Test email deletion with confirmation
- `test_delete_all_sender.py` - Test deleting all emails from a specific sender
- `test_parallel_delete.py` - Test parallel deletion performance
- `test_gmail_setup.py` - Test Gmail API setup and authentication
- `send_octopus_email.py` - Utility to send test emails
- `show_latest_emails.py` - Utility to display latest emails
- `check_authenticated_account.py` - Utility to check authenticated Gmail account

### `agent/`
Tests for email agent functionality:
- `test_count_action.py` - Test COUNT action parsing and execution

### `integration/`
Integration tests for the complete system:
- `test_new_structure.py` - Test modular code structure and imports

## Running Tests

To run tests, execute them from the project root:

```bash
# Run a specific test
py tests/email/test_inbox_count.py

# Run all email tests
py tests/email/test_email_body.py
py tests/email/test_inbox_count.py
# etc.
```

## Test Utilities

- `send_octopus_email.py` - Sends a test email to verify sending functionality
- `show_latest_emails.py` - Shows the latest emails in your mailbox
- `check_authenticated_account.py` - Displays the currently authenticated Gmail account
