"""
Stock Market skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
resolve_ticker(query) – Convert a company name or fuzzy query to a stock ticker symbol.
get_quote(symbol) – Get the current price, change, volume and key stats for a ticker.
get_historical_data(symbol, period="1mo", interval="1d") – Fetch historical OHLCV data. period: 1d/5d/1mo/3mo/6mo/1y/2y/5y/10y/ytd/max. interval: 1m/2m/5m/15m/30m/60m/90m/1h/1d/5d/1wk/1mo/3mo.
technical_analysis(symbol, period="6mo") – RSI, MACD, Bollinger Bands, moving averages and trading signals.
risk_score(symbol, period="1y") – Volatility, beta, VaR, Sharpe ratio and overall risk score.
fundamental_analysis(symbol) – P/E, EPS, revenue, margins, ROE and moat score.
pattern_detection(symbol, period="3mo") – Detect chart patterns (head & shoulders, flags, etc.).
sentiment_analysis(symbol) – News-based sentiment score and recent headlines.
compare_stocks(symbols) – Side-by-side comparison of a list of tickers.
portfolio_analysis(symbols, period="1y") – Correlation, diversification and performance of a portfolio.
portfolio_suggestions(symbols) – Get optimisation and rebalancing suggestions.
market_overview(indices=None) – Snapshot of major indices and market breadth.
generate_full_report(symbol, output_path="") – Generate a comprehensive PDF research report for a stock.
""".strip()

_SKILL_CONTEXT = """
You are the Stock Market Skill Agent.
You provide financial data, technical analysis, fundamental research and market overviews
using real-time and historical data from Yahoo Finance.

Important disclaimers:
- Always include a brief disclaimer that this is not financial advice.
- Do not guarantee returns or make investment recommendations as certainties.

Typical flows:
- "What's the price of Apple?" → resolve_ticker("Apple") → get_quote("AAPL")
- "Analyse TSLA" → get_quote → technical_analysis → fundamental_analysis → final_answer
- "How risky is NVDA?" → risk_score
- "Compare MSFT and GOOGL" → compare_stocks(["MSFT","GOOGL"])
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.stock_market import stock_service as ss  # noqa: PLC0415
    from src.stock_market import fundamental_service as fs  # noqa: PLC0415

    def portfolio_analysis(symbols: List[str], period: str = "1y") -> dict:
        return ss.portfolio_analysis(symbols, period)

    def compare_stocks(symbols: List[str]) -> dict:
        return ss.compare_stocks(symbols)

    def portfolio_suggestions(symbols: List[str]) -> dict:
        return ss.portfolio_suggestions(symbols)

    return {
        "resolve_ticker": lambda query: ss.resolve_ticker(query),
        "get_quote": lambda symbol: ss.get_quote(symbol),
        "get_historical_data": lambda symbol, period="1mo", interval="1d": ss.get_historical_data(symbol, period, interval),
        "technical_analysis": lambda symbol, period="6mo": ss.technical_analysis(symbol, period),
        "risk_score": lambda symbol, period="1y": ss.risk_score(symbol, period),
        "fundamental_analysis": lambda symbol: fs.fundamental_analysis(symbol),
        "pattern_detection": lambda symbol, period="3mo": ss.pattern_detection(symbol, period),
        "sentiment_analysis": lambda symbol: ss.sentiment_analysis(symbol),
        "compare_stocks": compare_stocks,
        "portfolio_analysis": portfolio_analysis,
        "portfolio_suggestions": portfolio_suggestions,
        "market_overview": lambda indices=None: ss.market_overview(indices),
        "generate_full_report": lambda symbol, output_path="": ss.generate_full_report(symbol, output_path),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="stock",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Stock Market skill error: {exc}",
            "action": "react_response",
        }
