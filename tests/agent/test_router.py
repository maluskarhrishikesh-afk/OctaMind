"""
Unit tests for src/agent/workflows/router.py — keyword maps and trigger_keywords.

Covers:
  - Every agent in AGENT_REGISTRY has a non-empty "trigger_keywords" list
  - _build_keyword_map() merges description-derived words WITH trigger_keywords
  - _build_distinctive_keyword_map() always includes trigger_keywords regardless of IDF
  - Specific domain words that could be IDF-pruned are kept via trigger_keywords
    (e.g. "payslip" → files, "email" → email, "whatsapp" → whatsapp)
  - Agent name-derived tokens are always in the distinctive map

These are pure Python unit tests — no LLM required.
"""
from __future__ import annotations

import re
import pytest


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

    def test_description_words_also_present_in_keyword_map(self):
        """Words extracted from the agent description are still in the map alongside triggers."""
        from src.agent.workflows.router import _build_keyword_map
        km = _build_keyword_map()
        # "gmail" appears in email description AND trigger_keywords
        assert "gmail" in km.get("email", frozenset())

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

    def test_payslip_routes_to_files(self):
        agents = self._route_via_keywords("find my payslip")
        assert "files" in agents

    def test_whatsapp_routes_to_whatsapp(self):
        agents = self._route_via_keywords("send a whatsapp to Alice")
        assert "whatsapp" in agents

    def test_gmail_routes_to_email(self):
        agents = self._route_via_keywords("check my gmail inbox")
        assert "email" in agents

    def test_ticker_routes_to_stock_market(self):
        agents = self._route_via_keywords("analyse the ticker TSLA")
        assert "stock_market" in agents

    def test_linkedin_post_routes_to_linkedin(self):
        agents = self._route_via_keywords("publish a linkedin post")
        assert "linkedin" in agents

    def test_habit_streak_routes_to_habit_tracker(self):
        agents = self._route_via_keywords("show my habit streak for gym")
        assert "habit_tracker" in agents
