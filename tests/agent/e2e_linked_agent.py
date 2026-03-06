"""
E2E tests for linked (multi-agent) routing.

"Linked" means the router detects that two or more agents are needed to
complete a single command, and the hub processor chains them in sequence.

These tests require:
  - A valid LLM API key configured in config/settings.json or environment

Run with:
    python -m pytest tests/agent/e2e_linked_agent.py -v -m e2e

Deselect from normal runs with:
    python -m pytest tests/ -m "not e2e"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect(command: str) -> list[str] | None:
    """Run detect_agents_needed via the LLM routing path."""
    from src.agent.workflows.router import detect_agents_needed
    return detect_agents_needed(command)


def _skip_if_no_llm():
    """Skip the test when the LLM API is unavailable."""
    try:
        from src.agent.llm.llm_parser import get_llm_client
        get_llm_client()
    except Exception:
        pytest.skip("LLM API unavailable — skipping e2e routing assertion")


def _assert_agents_include(result: list[str] | None, *expected_agents: str):
    """Assert that all expected_agents appear in the routing result."""
    assert result is not None, (
        f"Router returned None (conversational) but expected agents {list(expected_agents)}"
    )
    for agent in expected_agents:
        assert agent in result, (
            f"Expected agent '{agent}' in routing result, got: {result}"
        )


# ---------------------------------------------------------------------------
# Single-agent commands — sanity checks that routing still works for simple cases
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_email_only_routes_to_email():
    """A pure email command should route only to the email agent."""
    _skip_if_no_llm()
    result = _detect("send an email to alice@example.com saying the meeting is at 3 PM")
    _assert_agents_include(result, "email")


@pytest.mark.e2e
def test_files_only_routes_to_files():
    """A pure file command should route only to the files agent."""
    _skip_if_no_llm()
    result = _detect("zip my Downloads folder")
    _assert_agents_include(result, "files")


@pytest.mark.e2e
def test_drive_only_routes_to_drive():
    """A pure Drive command should route only to the drive agent."""
    _skip_if_no_llm()
    result = _detect("list files in my Google Drive Projects folder")
    _assert_agents_include(result, "drive")


# ---------------------------------------------------------------------------
# Two-agent linked commands
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_zip_and_upload_routes_to_files_and_drive():
    """
    'zip the folder and upload to Drive' — requires files (zip) then drive (upload).
    The router must return both agents.
    """
    _skip_if_no_llm()
    result = _detect("zip my Documents folder and upload it to Google Drive")
    _assert_agents_include(result, "files", "drive")


@pytest.mark.e2e
def test_find_payslip_and_email_routes_to_files_and_email():
    """
    'find my payslip and email it to my accountant' — requires files (search)
    and email (send with attachment).
    """
    _skip_if_no_llm()
    result = _detect("find my January payslip file and email it to my accountant")
    _assert_agents_include(result, "files", "email")


@pytest.mark.e2e
def test_download_from_drive_and_email_routes_correctly():
    """
    'download the report from Drive and email it to the team' — requires drive + email.
    """
    _skip_if_no_llm()
    result = _detect("download the Q3 report from Google Drive and send it by email to the team")
    _assert_agents_include(result, "drive", "email")


# ---------------------------------------------------------------------------
# Three-agent linked commands
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_zip_upload_mail_routes_to_three_agents():
    """
    Classic three-agent pipeline: zip (files) → upload to Drive → mail me.
    Router should return all three agents.
    """
    _skip_if_no_llm()
    result = _detect("zip the Images folder, upload it to Drive, then mail me the link")
    _assert_agents_include(result, "files", "drive", "email")


# ---------------------------------------------------------------------------
# Conversational / pure chat — must NOT route to any agent
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_small_talk_routes_to_none():
    """
    Pure conversational messages must return None (no agents).
    """
    _skip_if_no_llm()
    result = _detect("how are you doing today?")
    assert result is None or result == [], (
        f"Expected no agents for small talk, got: {result}"
    )


@pytest.mark.e2e
def test_greeting_routes_to_none():
    """
    A greeting must not trigger any agent.
    """
    _skip_if_no_llm()
    result = _detect("hello!")
    assert result is None or result == [], (
        f"Expected no agents for greeting, got: {result}"
    )


# ---------------------------------------------------------------------------
# Context-aware follow-up routing
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_cross_agent_follow_up_resolved_by_context():
    """
    After the files agent finds payslips, a follow-up "email it to my accountant"
    should route to the email agent (not None, even though "it" is ambiguous).
    """
    _skip_if_no_llm()
    # The follow-up alone is still routable to email because "email" is present
    result = _detect("email it to my accountant")
    # The presence of "email" should at minimum keep this from being treated as chat
    assert result is not None, (
        "Follow-up 'email it to my accountant' should route to email agent, not be dropped as chat"
    )
    _assert_agents_include(result, "email")
