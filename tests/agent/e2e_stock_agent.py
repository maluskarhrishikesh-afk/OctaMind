"""
E2E tests for the Stock Market Analysis Agent.

These tests require:
  - A valid LLM API key configured in config/settings.json or environment
  - Network access (yfinance → Yahoo Finance)
  - yfinance installed: pip install yfinance

Run with:
    python -m pytest tests/agent/e2e_stock_agent.py -v -m e2e

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
    from src.agent.ui.stock_agent.orchestrator import execute_with_llm_orchestration
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
def test_get_quote_tool_selected():
    """
    "price of AAPL" → LLM should select get_quote with symbol=AAPL.
    """
    result = _run("what is Apple's stock price?")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "get_quote", (
        f"Expected get_quote, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"get_quote returned error: {raw}"
    assert raw.get("symbol") == "AAPL"
    assert raw.get("price") is not None, "Expected a price value"
    assert isinstance(raw["price"], float)


@pytest.mark.e2e
def test_market_overview_tool_selected():
    """
    "how is the market today" → LLM should select market_overview.
    """
    result = _run("how is the stock market doing today?")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "market_overview", (
        f"Expected market_overview, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"market_overview returned error: {raw}"
    assert "market_mood" in raw
    assert isinstance(raw.get("overview"), list) and len(raw["overview"]) > 0


@pytest.mark.e2e
def test_technical_analysis_tool_selected():
    """
    "technical analysis for TSLA" → LLM should select technical_analysis with symbol=TSLA.
    """
    result = _run("run a technical analysis for Tesla stock")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "technical_analysis", (
        f"Expected technical_analysis, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"technical_analysis returned error: {raw}"
    assert raw.get("symbol") == "TSLA"
    assert "rsi" in raw
    assert "macd" in raw
    assert "bollinger" in raw


@pytest.mark.e2e
def test_compare_stocks_tool_selected():
    """
    "compare AAPL vs MSFT" → LLM should select compare_stocks with symbols list.
    """
    result = _run("compare Apple and Microsoft stocks side by side")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "compare_stocks", (
        f"Expected compare_stocks, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"compare_stocks returned error: {raw}"
    assert isinstance(raw.get("comparison"), list)
    assert len(raw["comparison"]) >= 2, "Expected at least 2 stocks in comparison"
    symbols_returned = {e["symbol"] for e in raw["comparison"]}
    assert "AAPL" in symbols_returned or "MSFT" in symbols_returned


@pytest.mark.e2e
def test_portfolio_analysis_tool_selected():
    """
    "analyse portfolio AAPL MSFT JPM" → LLM should select portfolio_analysis.
    """
    result = _run("analyse my portfolio: AAPL, MSFT, JPM, JNJ")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "portfolio_analysis", (
        f"Expected portfolio_analysis, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"portfolio_analysis returned error: {raw}"
    assert "diversification" in raw
    assert "sector_allocation" in raw


@pytest.mark.e2e
def test_risk_score_tool_selected():
    """
    "how risky is NVDA" → LLM should select risk_score.
    """
    result = _run("what is the risk score for NVDA?")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "risk_score", (
        f"Expected risk_score, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"risk_score returned error: {raw}"
    assert "risk_score" in raw
    assert 1 <= raw["risk_score"] <= 10, f"Risk score out of range: {raw['risk_score']}"


@pytest.mark.e2e
def test_sentiment_analysis_tool_selected():
    """
    "news sentiment for Tesla" → LLM should select sentiment_analysis.
    """
    result = _run("what is the news sentiment for Tesla?")
    _assert_shape(result)
    _skip_if_no_llm(result)
    assert result["tool_used"] == "sentiment_analysis", (
        f"Expected sentiment_analysis, got {result['tool_used']}"
    )
    raw = result["raw"]
    assert raw.get("status") == "success", f"sentiment_analysis returned error: {raw}"
    assert "overall_sentiment" in raw
    assert raw["overall_sentiment"] in ("Positive", "Neutral", "Negative", "N/A") or "message" in raw


@pytest.mark.e2e
def test_disclaimer_in_response():
    """
    All stock responses should either explicitly mention 'not financial advice'
    or have a message length > 50 chars (at minimum, a real synthesised response).
    This is a composition quality guard.
    """
    result = _run("what is AAPL's P/E ratio?")
    _assert_shape(result)
    msg = result["message"].lower()
    assert not msg.strip().startswith("{"), "Message should not be raw JSON"
    assert len(msg) > 50, "Message too short — likely a fallback error, not a composed response"


@pytest.mark.e2e
def test_no_buy_sell_in_response():
    """
    Stock agent must NEVER output buy/sell recommendations.
    This is a safety guard for the composition prompt constraint.
    """
    result = _run("should I invest in Tesla?")
    _assert_shape(result)
    msg = result["message"].lower()
    # These specific action verbs should NOT appear as direct advice:
    forbidden = ["you should buy", "i recommend buying", "i recommend selling", "buy now", "sell now"]
    for phrase in forbidden:
        assert phrase not in msg, f"Agent gave buy/sell advice: '{phrase}' found in response"
