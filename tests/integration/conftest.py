"""
Fixtures for integration tests.

These tests hit live Gmail — they pass when credentials are present and
gracefully skip (or produce no assertion failures) when they are not.
"""

import pytest

from src.email import list_emails


@pytest.fixture(scope="session")
def message_id():
    """Return the ID of the first email in the inbox.

    Skips the test if no emails are found or Gmail credentials are not set up.
    """
    try:
        emails = list_emails(query="", max_results=1)
        if not emails:
            pytest.skip(
                "No emails found in inbox — skipping live integration test")
        return emails[0]["id"]
    except Exception as exc:
        pytest.skip(
            f"Gmail not available ({exc}) — skipping live integration test")
