"""
Tests for src/agent/llm/llm_parser.py

All OpenAI API calls are fully mocked — no GITHUB_TOKEN or network needed.

Covers:
  - GitHubModelsLLM.__init__: token requirement
  - GitHubModelsLLM.orchestrate_mcp_tool: JSON parsing, markdown stripping,
    error fallback, memory context forwarded to prompt
  - get_llm_client: returns GitHubModelsLLM, caches singleton
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_llm(token: str = "fake-token"):
    """Construct a GitHubModelsLLM with a mocked OpenAI client."""
    with patch.dict(os.environ, {"GITHUB_TOKEN": token}), \
            patch("src.agent.llm.llm_parser.OpenAI"):
        from src.agent.llm.llm_parser import GitHubModelsLLM
        return GitHubModelsLLM()


def _fake_completion(content: str):
    """Build a fake OpenAI completion response with the given message content."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── GitHubModelsLLM.__init__ ──────────────────────────────────────────────────

class TestGitHubModelsLLMInit:
    def test_raises_without_github_token(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with patch.dict(os.environ, env, clear=True), \
                patch("src.agent.llm.llm_parser.OpenAI"):
            from src.agent.llm.llm_parser import GitHubModelsLLM
            with pytest.raises(ValueError, match="GITHUB_TOKEN"):
                GitHubModelsLLM()

    def test_initialises_with_valid_token(self):
        llm = _make_llm()
        assert llm.token == "fake-token"
        assert llm.model == "gpt-4o-mini"


# ── orchestrate_mcp_tool ──────────────────────────────────────────────────────

_DUMMY_TOOLS = "1. **dummy_tool**(param: str)\n   - A test tool for unit tests.\n"


class TestOrchestrateMcpTool:
    def _run(self, llm, response_content: str, query: str = "test", memory: str = ""):
        llm.client.chat.completions.create.return_value = _fake_completion(
            response_content)
        return llm.orchestrate_mcp_tool(query, memory, tools_description=_DUMMY_TOOLS)

    def test_returns_correct_tool_for_list_query(self):
        llm = _make_llm()
        payload = json.dumps({
            "tool": "list_message",
            "params": {"query": "is:unread", "max_results": 10},
            "reasoning": "Listing unread emails"
        })
        result = self._run(llm, payload, query="show unread emails")
        assert result["tool"] == "list_message"
        assert result["params"]["query"] == "is:unread"
        assert "unread" in result["reasoning"].lower()

    def test_strips_markdown_code_block(self):
        llm = _make_llm()
        payload = "```json\n" + json.dumps({
            "tool": "send_message",
            "params": {"to": "a@b.com", "subject": "Hi", "message_text": "Hello"},
            "reasoning": "Sending email"
        }) + "\n```"
        result = self._run(llm, payload)
        assert result["tool"] == "send_message"

    def test_strips_plain_code_block(self):
        llm = _make_llm()
        payload = "```\n" + json.dumps({
            "tool": "count_messages",
            "params": {},
            "reasoning": "Counting"
        }) + "\n```"
        result = self._run(llm, payload)
        assert result["tool"] == "count_messages"

    def test_api_error_returns_fallback(self):
        llm = _make_llm()
        llm.client.chat.completions.create.side_effect = Exception(
            "connection reset")
        result = llm.orchestrate_mcp_tool(
            "count my emails", tools_description=_DUMMY_TOOLS)
        assert result["tool"] is None
        assert result["params"] == {}
        assert "reasoning" in result

    def test_invalid_json_returns_fallback(self):
        llm = _make_llm()
        llm.client.chat.completions.create.return_value = _fake_completion(
            "not-json{}")
        result = llm.orchestrate_mcp_tool(
            "something", tools_description=_DUMMY_TOOLS)
        assert result["tool"] is None

    def test_no_tools_description_returns_error(self):
        llm = _make_llm()
        result = llm.orchestrate_mcp_tool("show emails")
        assert result["tool"] is None
        assert "No tools_description" in result["reasoning"]

    def test_memory_context_forwarded_to_api(self):
        llm = _make_llm()
        llm.client.chat.completions.create.return_value = _fake_completion(
            json.dumps({"tool": "list_message", "params": {}, "reasoning": ""})
        )
        llm.orchestrate_mcp_tool(
            "show emails", memory_context="VIP: boss@corp.com", tools_description=_DUMMY_TOOLS)
        call_messages = llm.client.chat.completions.create.call_args.kwargs["messages"]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert "boss@corp.com" in user_msg["content"]

    def test_tools_description_included_in_system_prompt(self):
        llm = _make_llm()
        llm.client.chat.completions.create.return_value = _fake_completion(
            json.dumps({"tool": "dummy_tool", "params": {}, "reasoning": ""})
        )
        llm.orchestrate_mcp_tool(
            "do something", tools_description=_DUMMY_TOOLS)
        call_messages = llm.client.chat.completions.create.call_args.kwargs["messages"]
        system_msg = next(m for m in call_messages if m["role"] == "system")
        assert "dummy_tool" in system_msg["content"]

    def test_low_temperature_used(self):
        llm = _make_llm()
        llm.client.chat.completions.create.return_value = _fake_completion(
            json.dumps({"tool": "list_message", "params": {}, "reasoning": ""})
        )
        llm.orchestrate_mcp_tool("test", tools_description=_DUMMY_TOOLS)
        called_kwargs = llm.client.chat.completions.create.call_args.kwargs
        assert called_kwargs.get("temperature", 1) <= 0.3


# ── get_llm_client singleton ──────────────────────────────────────────────────

class TestGetLlmClient:
    def test_returns_github_models_llm_instance(self):
        import src.agent.llm.llm_parser as mod
        # Reset singleton so the test creates a fresh one
        mod._llm_client = None
        with patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}), \
                patch("src.agent.llm.llm_parser.OpenAI"):
            client = mod.get_llm_client()
        from src.agent.llm.llm_parser import GitHubModelsLLM
        assert isinstance(client, GitHubModelsLLM)

    def test_caches_singleton(self):
        import src.agent.llm.llm_parser as mod
        mod._llm_client = None
        with patch.dict(os.environ, {"GITHUB_TOKEN": "tok"}), \
                patch("src.agent.llm.llm_parser.OpenAI"):
            c1 = mod.get_llm_client()
            c2 = mod.get_llm_client()
        assert c1 is c2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
