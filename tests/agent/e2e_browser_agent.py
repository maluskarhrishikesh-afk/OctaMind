"""
E2E tests for the Browser Agent.

These tests require:
  - A valid LLM API key configured in config/settings.json or environment
  - Network access (DuckDuckGo, example.com)

Run with:
    python -m pytest tests/agent/e2e_browser_agent.py -v -m e2e

Deselect from normal runs with:
    python -m pytest tests/ -m "not e2e"
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _run(query: str) -> dict:
    from src.agent.ui.browser_agent.orchestrator import execute_with_llm_orchestration
    return execute_with_llm_orchestration(query)


def _assert_shape(result: dict):
    """Every orchestrator result must have these keys."""
    assert "status"    in result, "Missing 'status' key"
    assert "message"   in result, "Missing 'message' key"
    assert "tool_used" in result, "Missing 'tool_used' key"
    assert "raw"       in result, "Missing 'raw' key"
    assert isinstance(result["message"], str), "'message' must be a string"
    assert len(result["message"]) > 0, "'message' must not be empty"


def _skip_if_no_llm(result: dict):
    """Skip the test with a clear message when the LLM API is unavailable (e.g. rate-limited)."""
    if not result.get("llm_available", True):
        pytest.skip("LLM API unavailable (rate-limited or unreachable) — skipping tool-selection assertion")


# ── E2E Scenarios ──────────────────────────────────────────────────────────────

@pytest.mark.e2e
def test_search_web_tool_selected():
    """
    "search for Python" → LLM should select search_web.
    Result should have a list of search results.
    """
    result = _run("search the web for Python programming language")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "search_web", (
        f"Expected search_web, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"search_web returned error: {raw}"
    assert isinstance(raw.get("results"), list), "Expected results list"
    assert raw["count"] >= 1, "Expected at least 1 search result"


@pytest.mark.e2e
def test_browse_url_tool_selected():
    """
    Requesting to browse a URL → LLM should select browse_url.
    """
    result = _run("browse https://example.com and tell me what it says")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "browse_url", (
        f"Expected browse_url, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"browse_url returned error: {raw}"
    assert raw.get("url") == "https://example.com"
    assert len(raw.get("content", "")) > 50, "Expected non-trivial page content"


@pytest.mark.e2e
def test_summarize_page_tool_selected():
    """
    "summarise example.com" → LLM should select summarize_page.
    """
    result = _run("summarise the page at https://example.com")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "summarize_page", (
        f"Expected summarize_page, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"summarize_page returned error: {raw}"
    assert isinstance(raw.get("summary"), str) and len(raw["summary"]) > 0


@pytest.mark.e2e
def test_get_page_title_tool_selected():
    """
    "what is the title of example.com" → LLM should select get_page_title.
    """
    result = _run("what is the title of https://example.com")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "get_page_title", (
        f"Expected get_page_title, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"get_page_title returned error: {raw}"
    assert "title" in raw and len(raw["title"]) > 0


@pytest.mark.e2e
def test_response_is_not_raw_json():
    """
    Final response message should be human-readable, not raw JSON.
    When the LLM is unavailable the orchestrator must still produce
    a readable fallback (not a raw dict repr).
    """
    result = _run("search the web for OpenAI")
    _assert_shape(result)
    msg = result["message"]
    # A compose step that just dumps JSON would end with "}" - real messages don't
    assert not msg.strip().startswith("{"), "Message looks like raw JSON"
    assert not msg.strip().startswith("["), "Message looks like raw JSON array"
