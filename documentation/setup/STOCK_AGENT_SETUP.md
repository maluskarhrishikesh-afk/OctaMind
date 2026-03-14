# Stock Market Analysis Agent Setup Guide

This guide explains how to set up, configure, and test the Stock Market Analysis Agent in OctaMind.

> **Important:** This agent is read-only. It has no buy/sell, order placement, or brokerage integration of any kind.

---

## What the Stock Market Agent Does

| Tool | What it does |
|------|-------------|
| **resolve_ticker** | Resolve a company name like "Intellect Design Arena" to the most likely ticker |
| **get_quote** | Real-time price, change, volume, P/E ratio, market cap, sector |
| **get_historical_data** | OHLCV bar data for any period and interval |
| **fundamental_analysis** | Buffett-style quality, moat, growth, leverage, and valuation checks |
| **technical_analysis** | RSI, MACD, Bollinger Bands, SMA-20/50/200 with signals |
| **risk_score** | Annualised volatility, Beta vs SPY, VaR 95%, Sharpe ratio, 1-10 risk score |
| **pattern_detection** | Support/resistance, trend direction, candlestick patterns (doji, hammer, engulfing) |
| **portfolio_analysis** | Sector allocation, pairwise correlation matrix, diversification score |
| **portfolio_suggestions** | Rebalancing hints, concentration warnings (informational only) |
| **sentiment_analysis** | News headline NLP sentiment scoring (positive/neutral/negative) |
| **compare_stocks** | Side-by-side metric comparison for 2�10 symbols |
| **market_overview** | Broad market snapshot: SPY, QQQ, DIA, IWM, VIX + mood indicator |
| **research_company_web** | Investor-relations, annual-report, and management-commentary research from the public web |
| **generate_full_report** | End-to-end report generation that combines market data and browser-backed company research |

**Data sources:** [yfinance](https://github.com/ranaroussi/yfinance) for market data and the Browser service for public-web company research. No API key required.

---

## Requirements

### Python Package

```bash
pip install yfinance
```

Verify:
```bash
python -c "import yfinance as yf; t = yf.Ticker('AAPL'); print(t.info.get('shortName'))"
# Should print: Apple Inc.
```

**No API keys, brokerage accounts, or paid subscriptions required.**

yfinance fetches data from Yahoo Finance's public API endpoints.

### Python Version

Python 3.9+. (Already required by OctaMind core.)

---

## Installation

1. Install the required packages:

```bash
pip install yfinance beautifulsoup4 requests
```

2. **Verify agent registration:**

```bash
python -c "
from src.agent.workflows.agent_registry import AGENT_REGISTRY
print('stock_market' in AGENT_REGISTRY)  # Should print: True
"
```

3. **Run a quick smoke test:**

```bash
python -c "
from src.stock_market import get_quote, market_overview
q = get_quote('AAPL')
print(q['status'], q['price'])
m = market_overview()
print(m['market_mood'])
"
```

---

## Enabling the Stock Market Skill in the UI

1. Open the OctaMind dashboard with `python start.py`
2. Create a Personal Assistant or open an existing one
3. In the assistant configuration panel, enable **Stock Market Analysis** under **Skills**
4. Save the changes
5. Open the assistant workspace - market analysis requests will now route to the Stock Market skill

---

## Example Queries

Once added to a PA, the Stock Agent understands natural language:

```
"What is Apple's stock price?"
"How is the market doing today?"
"Technical analysis for TSLA"
"Is MSFT overbought? Show me the RSI"
"Risk score for NVDA"
"Analyse my portfolio: AAPL, MSFT, JPM, JNJ"
"Compare AAPL vs GOOGL vs MSFT"
"What are the chart patterns for AMZN?"
"News sentiment for Tesla"
"Show me 6 months of historical data for SPY"
"Any issues with my portfolio? I hold AAPL, TSLA, NVDA, META"
"Give me a market overview"
"What is the support and resistance for Netflix?"
"Bollinger Bands for Amazon"
"Analyse Intellect Design Arena"
"Generate a stock report for Nvidia"
```

---

## Architecture

```
User query
    |
stock_agent/orchestrator.py
    execute_with_llm_orchestration(user_query, agent_id, artifacts_out)
    |
    +- Loads tool docs from src/agent/ui/stock_agent/skills.md
    +- Resolves company names to tickers when needed
    +- Runs market/fundamental/technical/risk analysis via src/stock_market/stock_service.py
    +- Uses browser-backed company research for richer full-company reports
    +- Returns informational analysis with a not-financial-advice disclaimer
```

**Service layer:** `src/stock_market/stock_service.py`  
**Package init:** `src/stock_market/__init__.py`  
**Orchestrator:** `src/agent/ui/stock_agent/orchestrator.py`  
**Tool docs:** `src/agent/ui/stock_agent/skills.md`

---

## Technical Indicator Details

### RSI (Relative Strength Index, 14-day)
- `< 30` ? Oversold signal
- `30�70` ? Neutral
- `> 70` ? Overbought signal

### MACD (12, 26, 9 EMA)
- Histogram `> 0` ? Bullish momentum
- Histogram `< 0` ? Bearish momentum

### Bollinger Bands (20-day SMA � 2 std)
- Price above upper band ? Overbought
- Price below lower band ? Oversold

### Risk Score (1�10 composite)
- Derived from: annualised volatility, Beta vs SPY, daily VaR 95%
- Score 1�2: Very Low risk
- Score 3�4: Low
- Score 5�6: Moderate
- Score 7�8: High
- Score 9�10: Very High

---

## Running the Tests

### Unit tests (no LLM, requires internet for yfinance):
```bash
python -m pytest tests/stock_market/ -v
```

### Orchestrator regression tests:
```bash
python -m pytest tests/agent/test_browser_stock_orchestrators.py -k stock -v
```

### E2E test (requires LLM + internet):
```bash
python -m pytest tests/agent/e2e_stock_agent.py -v -m e2e
```

### Run all stock tests:
```bash
python -m pytest tests/ -k "stock" -v
```

---

## Known Limitations

| Limitation | Notes |
|-----------|-------|
| Data delay | Yahoo Finance free tier has ~15 min delay for some exchanges |
| Market hours | Quotes return last close price outside trading hours |
| Cryptocurrency | yfinance supports crypto tickers (e.g. "BTC-USD") but data quality varies |
| Non-US stocks | International tickers need exchange suffix: "RELIANCE.NS" (NSE), "SAP.DE" (Xetra) |
| Sentiment NLP | Keyword-based - not a trained ML model; indicative only |
| Pattern detection | Rule-based candlestick patterns only; no ML-based chart recognition |
| Full reports | `generate_full_report` can save PDF and Markdown outputs under `your_data/reports/` |
| No trading actions | The agent never places orders or gives buy/sell/hold instructions |

---

## Troubleshooting

**`yfinance` ImportError:**
```bash
pip install yfinance
```

**Empty data / "No historical data returned":**
- Check ticker symbol is correct (e.g. `GOOGL` not `GOOGLE`)
- Some OTC or international tickers may not be on Yahoo Finance
- Try `get_quote('AAPL')` as a baseline verification

**`KeyError` on `info` fields:**
- Some tickers (ETFs, crypto) may return different sets of `info` fields
- The service handles missing keys gracefully with `None` fallbacks

**Rate limiting from Yahoo Finance:**
- yfinance may get throttled if many calls are made quickly
- The agent makes one yfinance call per tool invocation (by design)

---

## Dependency Summary

| Package | Version | Required | Purpose |
|---------|---------|----------|---------|
| `yfinance` | =0.2.40 | ? required | All market data, quotes, news |
| `math` | stdlib | ? always | Statistical calculations |
| `datetime` | stdlib | ? always | Date handling |
| pandas | transitive via yfinance | � | Returned by yfinance internally |

---

## Disclaimer

All output from this agent is for informational and educational purposes only. It does not constitute financial advice, investment recommendations, or trading signals. Always consult a qualified financial advisor before making investment decisions.
