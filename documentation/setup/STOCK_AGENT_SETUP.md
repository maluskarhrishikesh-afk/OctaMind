# Stock Market Analysis Agent — Setup Guide

This guide explains how to set up, configure, and test the Stock Market Analysis Agent in OctaMind.

> **Important:** This agent is **read-only analysis only**. It has no buy/sell, order placement, or brokerage integration of any kind.

---

## What the Stock Market Agent Does

| Tool | What it does |
|------|-------------|
| **get_quote** | Real-time price, change, volume, P/E ratio, market cap, sector |
| **get_historical_data** | OHLCV bar data for any period and interval |
| **technical_analysis** | RSI, MACD, Bollinger Bands, SMA-20/50/200 with signals |
| **risk_score** | Annualised volatility, Beta vs SPY, VaR 95%, Sharpe ratio, 1-10 risk score |
| **pattern_detection** | Support/resistance, trend direction, candlestick patterns (doji, hammer, engulfing) |
| **portfolio_analysis** | Sector allocation, pairwise correlation matrix, diversification score |
| **portfolio_suggestions** | Rebalancing hints, concentration warnings (informational only) |
| **sentiment_analysis** | News headline NLP sentiment scoring (positive/neutral/negative) |
| **compare_stocks** | Side-by-side metric comparison for 2–10 symbols |
| **market_overview** | Broad market snapshot: SPY, QQQ, DIA, IWM, VIX + mood indicator |

**Data source:** [yfinance](https://github.com/ranaroussi/yfinance) — free, no API key required.

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

1. **Install the package** (already done if you followed initial setup):

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

1. Open the OctaMind dashboard (`python start.py` or `streamlit run src/agent/ui/dashboard/app.py`)
2. Click **"+ Add Agent / Skill"**
3. In the skill catalogue, locate **📈 Stock Market Analysis**
4. Toggle it on for an existing Personal Assistant, or create a new one
5. Save — the PA now routes market analysis queries to the Stock Agent

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
```

---

## Architecture

```
User query
    │
    ▼
stock_agent/orchestrator.py
    execute_with_llm_orchestration(user_query, agent_id, artifacts_out)
    │
    ├─ Step 1: LLM tool selector (temperature=0.1, max_tokens=400)
    │          → chooses one of 10 analysis tools + params
    │          → extracts ticker symbol(s) from natural language
    │
    ├─ Step 2: _dispatch_tool(tool, params)
    │          → calls src/stock_market/stock_service.py
    │          → fetches data from Yahoo Finance via yfinance
    │          → computes indicators in pure Python (no extra ML deps)
    │
    └─ Step 3: LLM response composer (temperature=0.4, max_tokens=1500)
               → formats findings as clear, plain-language analysis
               → always includes "not financial advice" disclaimer
```

**Service layer:** `src/stock_market/stock_service.py`  
**Package init:** `src/stock_market/__init__.py`  
**Orchestrator:** `src/agent/ui/stock_agent/orchestrator.py`

---

## Technical Indicator Details

### RSI (Relative Strength Index, 14-day)
- `< 30` → Oversold signal
- `30–70` → Neutral
- `> 70` → Overbought signal

### MACD (12, 26, 9 EMA)
- Histogram `> 0` → Bullish momentum
- Histogram `< 0` → Bearish momentum

### Bollinger Bands (20-day SMA ± 2 std)
- Price above upper band → Overbought
- Price below lower band → Oversold

### Risk Score (1–10 composite)
- Derived from: annualised volatility, Beta vs SPY, daily VaR 95%
- Score 1–2: Very Low risk
- Score 3–4: Low
- Score 5–6: Moderate
- Score 7–8: High
- Score 9–10: Very High

---

## Running the Tests

### Unit tests (no LLM, requires internet for yfinance):
```bash
python -m pytest tests/stock_market/ -v
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
| Sentiment NLP | Keyword-based — not a trained ML model; indicative only |
| Pattern detection | Rule-based candlestick patterns only; no ML-based chart recognition |
| No persistence | Stock data is never saved to disk — all real-time on demand |

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
| `yfinance` | ≥0.2.40 | ✅ required | All market data, quotes, news |
| `math` | stdlib | ✅ always | Statistical calculations |
| `datetime` | stdlib | ✅ always | Date handling |
| pandas | transitive via yfinance | — | Returned by yfinance internally |

---

## Disclaimer

All output from this agent is **for informational and educational purposes only**. It does not constitute financial advice, investment recommendations, or trading signals. Always consult a qualified financial advisor before making investment decisions.
