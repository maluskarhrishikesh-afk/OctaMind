# Stock Agent — Tool Skills

## Category: Core Market Data

### resolve_ticker
- **signature**: `resolve_ticker(query)`
- **description**: Resolve a company name or fuzzy stock query to the most likely ticker symbol. Use when the user mentions a company name instead of a market symbol.
- **tags**: ticker, resolve symbol, company to ticker, stock symbol, company name

### get_quote
- **signature**: `get_quote(symbol)`
- **description**: Get the current market snapshot for a stock including price, change, volume, market cap, valuation basics, sector, and industry.
- **tags**: quote, stock price, current price, market cap, valuation, live price

### get_historical_data
- **signature**: `get_historical_data(symbol, period="1mo", interval="1d")`
- **description**: Fetch historical OHLCV data for a stock. Use when the user asks for price history, chart data, or period-based performance context.
- **tags**: history, ohlcv, stock chart, candles, historical data, time series

### market_overview
- **signature**: `market_overview(indices=None)`
- **description**: Return a broad market snapshot across major indices and risk proxies. Use when the user asks how the market is doing overall.
- **tags**: market overview, indices, market mood, nifty, sensex, nasdaq, dow, sp500

---

## Category: Analysis

### technical_analysis
- **signature**: `technical_analysis(symbol, period="6mo")`
- **description**: Compute technical indicators such as RSI, MACD, Bollinger Bands, moving averages, and signal interpretations.
- **tags**: technical analysis, rsi, macd, bollinger, moving average, chart signal

### risk_score
- **signature**: `risk_score(symbol, period="1y")`
- **description**: Compute volatility, drawdown, Sharpe ratio, VaR, and an overall risk level for the stock.
- **tags**: risk, volatility, drawdown, sharpe, var, downside, risk score

### fundamental_analysis
- **signature**: `fundamental_analysis(symbol)`
- **description**: Run Buffett-style fundamental analysis using profitability, growth, leverage, cash generation, moat score, and quality score formulas.
- **tags**: fundamentals, quality score, moat, roe, margins, earnings growth, revenue growth, pe, debt

### pattern_detection
- **signature**: `pattern_detection(symbol, period="3mo")`
- **description**: Detect chart patterns and trend structure from recent price action.
- **tags**: pattern detection, trend, support resistance, candlestick, chart pattern

### sentiment_analysis
- **signature**: `sentiment_analysis(symbol)`
- **description**: Analyse recent stock-related news headlines and classify the overall news sentiment.
- **tags**: sentiment, news sentiment, headlines, positive news, negative news, market sentiment

### research_company_web
- **signature**: `research_company_web(company_name, symbol="", num_results=6, max_pages=4)`
- **description**: Search the public web for company overview, investor-relations pages, annual report references, results commentary, and management commentary. Use this when the user wants richer business context beyond market data, especially for full stock analysis reports.
- **tags**: company research, browser, annual report, management commentary, investor relations, business model, web research

### generate_full_report
- **signature**: `generate_full_report(query_or_symbol, output_path="", send_to_email="")`
- **description**: Preferred tool for a complete stock analysis. It resolves the company, gathers quote, technical, risk, fundamental, and news-sentiment data, researches the company on the public web, and builds a proper report with sections like performance assessment, management commentary, overall sentiment, positives, risks, and takeaway. It also writes a PDF report and can optionally email it if `send_to_email` is provided.
- **tags**: full analysis, stock report, pdf report, company analysis, management commentary, proper report, send report, analysis pdf, equity report

---

## Category: Comparison & Portfolio

### compare_stocks
- **signature**: `compare_stocks(symbols)`
- **description**: Compare multiple stocks side by side on price, valuation, market cap, sector, and range positioning.
- **tags**: compare stocks, versus, side by side, comparison, peers, relative analysis

### portfolio_analysis
- **signature**: `portfolio_analysis(symbols, period="1y")`
- **description**: Analyse a multi-stock portfolio for diversification, sector concentration, and return correlations.
- **tags**: portfolio, diversification, correlation, allocation, concentration

### portfolio_suggestions
- **signature**: `portfolio_suggestions(symbols)`
- **description**: Generate informational portfolio observations about concentration, diversification gaps, and balance across sectors.
- **tags**: portfolio suggestions, rebalance, concentration, allocation, diversification hints

---

## Category: Context

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist resolved stock context for follow-up actions. Use when the user will likely ask another question about the same company or ticker.
- **tags**: context, remember ticker, follow-up, stock context