"""
Unit tests for src/agent/workflows/router.py — deterministic routing built from
curated trigger keywords and agent-name tokens.

Covers:
    - Every agent in AGENT_REGISTRY has a non-empty "trigger_keywords" list
    - _build_keyword_map() uses trigger_keywords plus agent-name tokens
    - _build_distinctive_keyword_map() preserves strong domain signals
    - Specific domain words that could be IDF-pruned are kept via trigger_keywords
        (e.g. "payslip" → files, "email" → email, "whatsapp" → whatsapp)
    - Mailbox-style date/range/spam queries collapse to the email agent only

These are pure Python unit tests — no LLM required.
"""
from __future__ import annotations

import re
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_router_caches():
    """Force rebuild of the lazy keyword-map caches between tests."""
    import src.agent.workflows.router as r
    r._KEYWORD_MAP = None
    r._DISTINCTIVE_KEYWORD_MAP = None


def _tokenise(phrase: str) -> set[str]:
    """Split a phrase into lowercase alpha tokens of length ≥ 3 (mirrors router logic)."""
    return set(re.findall(r"[a-z]{3,}", phrase.lower()))


# ---------------------------------------------------------------------------
# Registry shape tests
# ---------------------------------------------------------------------------

class TestAgentRegistryTriggerKeywords:

    def test_all_agents_have_trigger_keywords_field(self):
        """Every entry in AGENT_REGISTRY must have a 'trigger_keywords' key."""
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        for name, info in AGENT_REGISTRY.items():
            assert "trigger_keywords" in info, (
                f"Agent '{name}' is missing 'trigger_keywords' key in AGENT_REGISTRY"
            )

    def test_all_agents_trigger_keywords_nonempty(self):
        """Every agent's trigger_keywords list must have at least one entry."""
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        for name, info in AGENT_REGISTRY.items():
            kws = info.get("trigger_keywords", [])
            assert isinstance(kws, list) and len(kws) > 0, (
                f"Agent '{name}' has an empty trigger_keywords list"
            )

    def test_all_agents_trigger_keywords_are_strings(self):
        """Every element of trigger_keywords must be a non-empty string."""
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        for name, info in AGENT_REGISTRY.items():
            for kw in info.get("trigger_keywords", []):
                assert isinstance(kw, str) and kw.strip(), (
                    f"Agent '{name}' has a non-string or empty trigger keyword: {kw!r}"
                )


# ---------------------------------------------------------------------------
# _build_keyword_map tests
# ---------------------------------------------------------------------------

class TestKeywordMap:

    def setup_method(self):
        _reset_router_caches()

    def test_keyword_map_has_all_agents(self):
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        assert set(km.keys()) == set(AGENT_REGISTRY.keys())

    def test_trigger_keywords_present_in_keyword_map(self):
        """Trigger keywords that wouldn't naturally appear in the description are in the map."""
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        # "payslip" is a curated trigger_keyword for files — not in its description text
        assert "payslip" in km.get("files", frozenset()), (
            "'payslip' should be in the files keyword map via trigger_keywords"
        )

    def test_agent_name_tokens_present_in_keyword_map(self):
        """Agent-name tokens stay routable even if not repeated in trigger phrases."""
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        assert "market" in km.get("stock_market", frozenset())

    def test_description_noise_does_not_leak_into_keyword_map(self):
        """Description-only words like 'list' or 'show' should not create fallback matches."""
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        assert "list" not in km.get("drive", frozenset())
        assert "show" not in km.get("whatsapp", frozenset())

    def test_email_trigger_keywords_in_map(self):
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        email_kws = km.get("email", frozenset())
        for kw in ("email", "gmail", "inbox", "draft"):
            tokens = _tokenise(kw)
            assert tokens & email_kws, (
                f"Expected token(s) from '{kw}' to be in email keyword map"
            )

    def test_whatsapp_trigger_keywords_in_map(self):
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        wa_kws = km.get("whatsapp", frozenset())
        assert "whatsapp" in wa_kws

    def test_stock_ticker_keywords_in_map(self):
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        stock_kws = km.get("stock_market", frozenset())
        for kw in ("ticker", "portfolio", "rsi"):
            assert kw in stock_kws, f"Expected '{kw}' in stock_market keyword map"


# ---------------------------------------------------------------------------
# _build_distinctive_keyword_map tests
# ---------------------------------------------------------------------------

class TestDistinctiveKeywordMap:

    def setup_method(self):
        _reset_router_caches()

    def test_distinctive_map_has_all_agents(self):
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        assert set(dm.keys()) == set(AGENT_REGISTRY.keys())

    def test_trigger_keywords_bypass_idf_filter(self):
        """
        "payslip" can appear in multiple agent descriptions or be a common word,
        but it is a trigger_keyword for files so it MUST survive the IDF filter.
        """
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        assert "payslip" in dm.get("files", frozenset()), (
            "'payslip' should NOT be removed by IDF from files distinctive map"
        )

    def test_email_trigger_keyword_survives_idf(self):
        """
        'email' appears in many agents' descriptions but IS a trigger_keyword
        for the email agent — so it must remain in the email distinctive map.
        """
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        assert "email" in dm.get("email", frozenset()), (
            "'email' should survive IDF filtering because it is in email trigger_keywords"
        )

    def test_whatsapp_in_distinctive_map(self):
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        assert "whatsapp" in dm.get("whatsapp", frozenset())

    def test_agent_name_tokens_always_distinctive(self):
        """
        Each agent's own name-derived tokens (e.g. 'stock' for stock_market)
        are always included as distinctive regardless of IDF score.
        """
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        # "stock" and "market" derived from "stock_market" name
        assert "stock" in dm.get("stock_market", frozenset()) or \
               "market" in dm.get("stock_market", frozenset()), (
            "Name-derived tokens of 'stock_market' should be in distinctive map"
        )

    def test_habit_trigger_keywords_in_distinctive_map(self):
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        habit_kws = dm.get("habit_tracker", frozenset())
        assert "habit" in habit_kws or "habits" in habit_kws, (
            "'habit' / 'habits' should be in habit_tracker distinctive map"
        )

    def test_linkedin_trigger_keywords_in_distinctive_map(self):
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        li_kws = dm.get("linkedin", frozenset())
        assert "linkedin" in li_kws

    def test_drive_trigger_keywords_in_distinctive_map(self):
        from src.agent.workflows.router import _build_distinctive_keyword_map
        dm = _build_distinctive_keyword_map()
        drive_kws = dm.get("drive", frozenset())
        assert "drive" in drive_kws or "gdrive" in drive_kws


# ---------------------------------------------------------------------------
# keyword_fallback routing integration
# ---------------------------------------------------------------------------

class TestKeywordFallbackRouting:
    """
    Tests the keyword-based fallback routing (no LLM). Verifies that
    specific phrases route to the expected agents via keyword matching.
    """

    def setup_method(self):
        _reset_router_caches()

    def _route_via_keywords(self, command: str) -> list[str]:
        """Run ONLY the keyword-fallback path (no LLM call)."""
        from src.agent.workflows.router import _get_keyword_map
        kws = command.lower()
        tokens = set(re.findall(r"[a-z]{3,}", kws))
        km = _get_keyword_map()
        matched = [agent for agent, agent_kws in km.items() if tokens & agent_kws]
        return matched


def test_normalize_followup_agents_keeps_current_channel_delivery_on_files() -> None:
    from src.agent.workflows.router import _normalize_followup_agents

    normalized = _normalize_followup_agents(
        "Zip that and send it to me",
        active_context={"agent": "files"},
        agents=["files", "email"],
    )

    assert normalized == ["files"]


def test_normalize_followup_agents_preserves_email_when_explicit() -> None:
    from src.agent.workflows.router import _normalize_followup_agents

    normalized = _normalize_followup_agents(
        "Zip that and email it to me",
        active_context={"agent": "files"},
        agents=["files", "email"],
    )

    assert normalized == ["files", "email"]


def test_classify_and_route_filename_search_uses_files_only() -> None:
    from src.agent.workflows.router import classify_and_route

    result = classify_and_route(
        "Is there any image file on my computer which contains octa in its filename?"
    )

    assert result.category == "fresh_task"
    assert result.agents == ["files"]


def test_classify_and_route_todays_email_query_uses_email_only() -> None:
    from src.agent.workflows.router import classify_and_route

    result = classify_and_route("List all the email that I received today?")

    assert result.category == "fresh_task"
    assert result.agents == ["email"]


def test_classify_and_route_yesterdays_email_query_uses_email_only() -> None:
    from src.agent.workflows.router import classify_and_route

    result = classify_and_route("Show me yesterday's emails")

    assert result.category == "fresh_task"
    assert result.agents == ["email"]


def test_classify_and_route_date_range_email_query_uses_email_only() -> None:
    from src.agent.workflows.router import classify_and_route

    result = classify_and_route("List emails between 2026-03-01 and 2026-03-10")

    assert result.category == "fresh_task"
    assert result.agents == ["email"]


def test_classify_and_route_spam_email_query_uses_email_only() -> None:
    from src.agent.workflows.router import classify_and_route

    result = classify_and_route("Show spam emails from last week")

    assert result.category == "fresh_task"
    assert result.agents == ["email"]


def test_classify_message_marks_pronoun_request_as_context_followup() -> None:
    from src.agent.workflows.router import _classify_message
    from src.agent.workflows.agent_registry import registered_agents

    result = _classify_message(
        "Can you send it to me?",
        active_context={"agent": "files", "topic": "auto_search_result", "awaiting": "file_action"},
        session_state=None,
        valid=set(registered_agents()),
    )

    assert result.category == "context_followup"
    assert result.source == "pronoun_followup"


def test_resolve_context_stage_binds_default_agent_from_active_context() -> None:
    from src.agent.workflows.router import ClassificationStageResult, _resolve_context_stage
    from src.agent.workflows.agent_registry import registered_agents

    resolved = _resolve_context_stage(
        "Can you send it to me?",
        ClassificationStageResult(category="context_followup", reason="pronoun", source="test"),
        active_context={"agent": "files", "topic": "auto_search_result", "awaiting": "file_action"},
        session_state=None,
        valid=set(registered_agents()),
    )

    assert resolved.category == "context_followup"
    assert resolved.context_agent == "files"
    assert resolved.default_agents == ["files"]


def test_run_routing_pipeline_uses_context_agent_when_planning_falls_back(monkeypatch) -> None:
    from src.agent.workflows.router import run_routing_pipeline

    def raise_get_llm_client():
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("src.agent.llm.llm_parser.get_llm_client", raise_get_llm_client)

    pipeline = run_routing_pipeline(
        "Can you send it to me?",
        active_context={
            "agent": "files",
            "topic": "auto_search_result",
            "awaiting": "file_action",
            "resolved_entities": {"found_count": 1},
        },
    )

    assert pipeline.classification.category == "context_followup"
    assert pipeline.context_resolution.default_agents == ["files"]
    assert pipeline.planning.source == "keyword_fallback"
    assert pipeline.intent.category == "context_followup"
    assert pipeline.intent.agents == ["files"]


def test_classify_message_marks_numeric_pending_selection_as_context_followup() -> None:
    from src.agent.workflows.router import _classify_message
    from src.agent.workflows.agent_registry import registered_agents

    result = _classify_message(
        "1",
        active_context={
            "agent": "email",
            "topic": "mailbox_preferences",
            "awaiting": "email_action",
            "pending_selection": {"kind": "mailbox_preferences", "step": 0},
        },
        session_state=None,
        valid=set(registered_agents()),
    )

    assert result.category == "context_followup"
    assert result.source == "pending_selection"


def test_classify_and_route_mailbox_preference_edit_uses_email_only() -> None:
    from src.agent.workflows.router import classify_and_route

    result = classify_and_route("change newsletters to archive")

    assert result.category == "fresh_task"
    assert result.agents == ["email"]


def test_classify_and_route_organize_mailbox_uses_email_only() -> None:
    from src.agent.workflows.router import classify_and_route

    result = classify_and_route("please organize my mailbox")

    assert result.category == "fresh_task"
    assert result.agents == ["email"]


def test_keyword_fallback_payslip_routes_to_files() -> None:
    test_case = TestKeywordFallbackRouting()
    test_case.setup_method()
    agents = test_case._route_via_keywords("find my payslip")
    assert "files" in agents


def test_keyword_fallback_whatsapp_routes_to_whatsapp() -> None:
    test_case = TestKeywordFallbackRouting()
    test_case.setup_method()
    agents = test_case._route_via_keywords("send a whatsapp to Alice")
    assert "whatsapp" in agents


def test_keyword_fallback_gmail_routes_to_email() -> None:
    test_case = TestKeywordFallbackRouting()
    test_case.setup_method()
    agents = test_case._route_via_keywords("check my gmail inbox")
    assert "email" in agents


def test_keyword_fallback_ticker_routes_to_stock_market() -> None:
    test_case = TestKeywordFallbackRouting()
    test_case.setup_method()
    agents = test_case._route_via_keywords("analyse the ticker TSLA")
    assert "stock_market" in agents


def test_keyword_fallback_linkedin_post_routes_to_linkedin() -> None:
    test_case = TestKeywordFallbackRouting()
    test_case.setup_method()
    agents = test_case._route_via_keywords("publish a linkedin post")
    assert "linkedin" in agents


def test_keyword_fallback_habit_streak_routes_to_habit_tracker() -> None:
    test_case = TestKeywordFallbackRouting()
    test_case.setup_method()
    agents = test_case._route_via_keywords("show my habit streak for gym")
    assert "habit_tracker" in agents
