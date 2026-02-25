"""
Stock Market Analysis Agent

READ-ONLY market analysis — no buy/sell order functionality.

Capabilities:
  - Real-time quotes and historical OHLCV data
  - Technical analysis (RSI, MACD, Bollinger Bands, SMA)
  - Risk scoring (volatility, Beta, VaR, Sharpe, Max Drawdown, Sortino, Calmar)
  - Pattern detection (support/resistance, candlestick patterns)
  - Portfolio analysis (sector allocation, correlation, diversification)
  - Portfolio suggestions (rebalancing hints, concentration warnings)
  - News sentiment analysis (keyword NLP with negation/recency on latest headlines)
  - Stock comparison (side-by-side metrics)
  - Market overview (S&P500, Nasdaq, Dow, Russell, VIX)
  - Fundamental analysis — Warren Buffett quality framework (ROE, moat, FCF, safety)
  - Full PDF report generation (all analyses in one document, optional email delivery)

Data source: yfinance (free, no API key required).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger("stock_agent")

# ── Tool descriptions ──────────────────────────────────────────────────────────
_STOCK_TOOLS_DESCRIPTION = """
1. **get_quote**(symbol: str)
   - Current price, change, volume, P/E, market cap, sector for a stock.
   - Use for: "price of AAPL", "what is TSLA trading at?", "quote for MSFT",
     "how is Amazon doing?", "stock info for [symbol]"

2. **get_historical_data**(symbol: str, period: str = "1mo", interval: str = "1d")
   - OHLCV bars for any period.
   - period: "1d","5d","1mo","3mo","6mo","1y","2y","5y","ytd","max"
   - interval: "1m","5m","15m","1h","1d","1wk","1mo"
   - Use for: "historical data for ...", "chart data for ...", "6 months of AAPL prices"

3. **technical_analysis**(symbol: str, period: str = "6mo")
   - RSI, MACD, Bollinger Bands, SMA-20/50/200 with buy/neutral/sell signals.
   - Use for: "technical analysis of ...", "RSI for ...", "MACD for ...",
     "moving averages for ...", "is [stock] overbought?"

4. **risk_score**(symbol: str, period: str = "1y")
   - Annualised volatility, Beta vs SPY, VaR 95%, Sharpe ratio, risk score 1-10.
   - Use for: "how risky is ...", "risk score for ...", "volatility of ...",
     "beta for ...", "is [stock] high risk?"

5. **pattern_detection**(symbol: str, period: str = "3mo")
   - Support/resistance levels, trend, candlestick patterns (doji, hammer, engulfing).
   - Use for: "chart patterns for ...", "support and resistance for ...",
     "trend analysis of ...", "are there any patterns for [symbol]?"

6. **portfolio_analysis**(symbols: list[str], period: str = "1y")
   - Sector allocation, correlation matrix, diversification score.
   - Use for: "analyse my portfolio", "portfolio of AAPL MSFT JPM",
     "how diversified is [list] portfolio?", "correlation between stocks"

7. **portfolio_suggestions**(symbols: list[str])
   - Rebalancing hints, sector concentration warnings, equal-weight target allocation.
   - Use for: "how should I rebalance ...", "any issues with my portfolio?",
     "suggestions for [list] holdings", "portfolio review"

8. **sentiment_analysis**(symbol: str)
   - News headline sentiment for a stock (positive / neutral / negative + score).
   - Use for: "sentiment for ...", "what is the news saying about ...",
     "is there positive news for [symbol]?", "news sentiment for ..."

9. **compare_stocks**(symbols: list[str])
   - Side-by-side: price, P/E, market cap, volume, 52-week range, sector.
   - Use for: "compare AAPL vs MSFT", "compare [list]", "which is better: X or Y?"
     (note: no buy/sell — comparison only)

10. **market_overview**(indices: list[str] = ["SPY","QQQ","DIA","IWM","^VIX"])
    - Broad market health: day change, YTD, market mood (bullish/bearish).
    - Use for: "market overview", "how is the market doing?", "market today",
      "S&P500 status", "is the market up or down?"

11. **fundamental_analysis**(symbol: str)
    - Warren Buffett-style quality analysis: ROE, ROA, margins, FCF yield, debt ratios,
      valuation multiples (P/E, P/B, PEG, EV/EBITDA), moat score (0–10), quality score.
    - Use for: "fundamentals of ...", "Buffett analysis of ...", "is [stock] a quality company?",
      "moat score for ...", "financial health of ...", "balance sheet analysis"

12. **generate_full_report**(symbol: str, output_dir: str = "data", send_to_email: str = None)
    - Runs ALL analyses (quote, technical, risk, patterns, fundamentals, sentiment),
      generates a comprehensive PDF report, optionally emails it.
    - Use for: "generate report for ...", "full analysis PDF for ...",
      "complete analysis of ...", "download report for ...",
      "send analysis report of [symbol] to [email]"
"""


# ── Tool dispatcher ────────────────────────────────────────────────────────────

def _dispatch_tool(tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from src.stock_market import (
        get_quote, get_historical_data, technical_analysis, risk_score,
        pattern_detection, portfolio_analysis, portfolio_suggestions,
        sentiment_analysis, compare_stocks, market_overview,
        fundamental_analysis, generate_full_report,
    )
    _MAP = {
        "get_quote":            lambda p: get_quote(**p),
        "get_historical_data":  lambda p: get_historical_data(**p),
        "technical_analysis":   lambda p: technical_analysis(**p),
        "risk_score":           lambda p: risk_score(**p),
        "pattern_detection":    lambda p: pattern_detection(**p),
        "portfolio_analysis":   lambda p: portfolio_analysis(**p),
        "portfolio_suggestions":lambda p: portfolio_suggestions(**p),
        "sentiment_analysis":   lambda p: sentiment_analysis(**p),
        "compare_stocks":       lambda p: compare_stocks(**p),
        "market_overview":      lambda p: market_overview(**p),
        "fundamental_analysis": lambda p: fundamental_analysis(**p),
        "generate_full_report": lambda p: generate_full_report(**p),
    }
    fn = _MAP.get(tool)
    if fn is None:
        return {"status": "error", "message": f"Unknown stock tool: {tool}"}
    return fn(params)


# ── Main entry point ───────────────────────────────────────────────────────────

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str | None = None,
    artifacts_out: dict | None = None,
) -> Dict[str, Any]:
    """
    Execute a natural-language stock market analysis request.

    Steps:
      1. LLM selects the right tool + params (temperature=0.1).
      2. Tool is dispatched (real-time yfinance data).
      3. LLM composes a clear, human-readable analysis (temperature=0.4).
    """
    from src.agent.llm.llm_parser import get_llm_client

    llm = get_llm_client()

    selection_prompt = f"""You are a stock market analysis assistant. Select ONE tool to handle the user's request.

Available tools:
{_STOCK_TOOLS_DESCRIPTION}

User request: "{user_query}"

Respond with ONLY valid JSON:
{{
  "tool": "<tool_name>",
  "params": {{<key>: <value>, ...}},
  "reasoning": "<one sentence>"
}}

Rules:
- Ticker symbols MUST be uppercase strings (e.g. "AAPL", "TSLA")
- For portfolio tools: symbols must be a JSON array e.g. ["AAPL","MSFT","JPM"]
- period values: "1d","5d","1mo","3mo","6mo","1y","2y","5y","ytd","max"
- NEVER suggest buy/sell — this is analysis only
- For vague "market" queries: use market_overview
- For single stock questions: use get_quote or technical_analysis
- For "full report", "PDF", "complete analysis": use generate_full_report
- For "fundamentals", "Buffett", "quality", "moat": use fundamental_analysis
- Omit optional params unless the user explicitly specified them
"""

    _llm_available = True
    try:
        sel_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a precise stock analysis tool selector. Return ONLY valid JSON."},
                {"role": "user",   "content": selection_prompt},
            ],
            temperature=0.1,
            max_tokens=400,
            timeout=30,
        )
        sel_text  = sel_response.choices[0].message.content.strip()
        clean     = re.sub(r"^```[a-z]*\n?", "", sel_text)
        clean     = re.sub(r"\n?```$", "", clean).strip()
        selection = json.loads(clean)
        tool      = selection.get("tool", "market_overview")
        params    = selection.get("params", {})
        logger.info("[stock_agent] Tool selected: %s params=%s", tool, params)
    except Exception as exc:
        logger.warning("[stock_agent] Tool selection failed: %s — fallback to market_overview", exc)
        _llm_available = False
        tool   = "market_overview"
        params = {}

    raw = _dispatch_tool(tool, params)

    # Attach to artifacts if provided
    if artifacts_out is not None:
        artifacts_out["stock_result"] = raw

    compose_prompt = f"""The user asked: "{user_query}"

The stock analysis tool "{tool}" returned:
{json.dumps(raw, indent=2, default=str)[:4000]}

Write a clear, professional market analysis response:
- Use **bold** for ticker symbols, key metrics, and important values
- Present numbers with appropriate precision (prices to 2 decimals, percentages to 2 decimals)
- Use 📈 for positive/bullish signals, 📉 for negative/bearish, ⚠️ for warnings, 📊 for data
- For technical analysis: explain what indicators mean in plain language
- For portfolio analysis: give clear diversity/risk assessment
- For risk scores: explain what the score/level means practically
- For sentiment: summarise overall tone with key headline examples
- NEVER recommend buying or selling — this is informational analysis only
- Add a disclaimer: "This is informational analysis only, not financial advice."
- Do NOT expose raw JSON or internal IDs
"""

    try:
        compose_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a professional market analyst. Be clear, factual, and informative. Never give buy/sell advice."},
                {"role": "user",   "content": compose_prompt},
            ],
            temperature=0.4,
            max_tokens=1500,
            timeout=30,
        )
        final_message = compose_response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[stock_agent] Response composition failed: %s", exc)
        _llm_available = False
        # Build a human-readable fallback without LLM
        if raw.get("status") == "error":
            final_message = raw.get("message", "The stock analysis tool encountered an error.")
        elif "market_mood" in raw:
            mood = raw.get("market_mood", "unknown")
            overview = raw.get("overview", [])
            lines = [f"Market mood today: **{mood}**"]
            for item in overview[:5]:
                lines.append(f"- {item.get('name','')}: {item.get('change_pct','')}")
            lines.append("\nThis is informational analysis only, not financial advice.")
            final_message = "\n".join(lines)
        elif "price" in raw:
            sym = raw.get("symbol", "")
            price = raw.get("price", 0)
            chg = raw.get("change_pct", "")
            final_message = (
                f"**{sym}**: ${price:.2f} ({chg} today)\n"
                "\nThis is informational analysis only, not financial advice."
            )
        elif "risk_score" in raw:
            final_message = (
                f"Risk score for {raw.get('symbol','')}: {raw.get('risk_score','N/A')}/10 "
                f"({raw.get('risk_label','')})\n"
                "\nThis is informational analysis only, not financial advice."
            )
        else:
            final_message = "Analysis completed.\n\nThis is informational analysis only, not financial advice."

    return {
        "status":        raw.get("status", "success"),
        "message":       final_message,
        "action":        "react_response",
        "raw":           raw,
        "tool_used":     tool,
        "llm_available": _llm_available,
    }
