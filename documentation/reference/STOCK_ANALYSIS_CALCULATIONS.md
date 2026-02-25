# Stock Analysis — Calculation Methodology

> **Purpose:** This document describes every formula used by OctaMind's stock market
> analysis engine.  All calculations are implemented in pure Python with no third-party
> statistical library (except `math`).  The intent is to allow domain experts to
> review, challenge, and improve these formulas.
>
> **Ethical notice:** OctaMind does **not** produce buy/sell recommendations or price
> targets.  All outputs are informational only and are not SEBI-registered investment advice.

---

## Table of Contents

1. [Technical Analysis](#1-technical-analysis)
   - 1.1 RSI
   - 1.2 MACD
   - 1.3 Bollinger Bands
   - 1.4 Moving Averages
2. [Risk Assessment](#2-risk-assessment)
   - 2.1 Annual Volatility
   - 2.2 Beta vs SPY
   - 2.3 Value-at-Risk (VaR 95%)
   - 2.4 Sharpe Ratio
   - 2.5 Max Drawdown
   - 2.6 Sortino Ratio
   - 2.7 Calmar Ratio
   - 2.8 Composite Risk Score
3. [Fundamental Analysis — Warren Buffett Framework](#3-fundamental-analysis--warren-buffett-framework)
   - 3.1 Profitability
   - 3.2 Financial Safety
   - 3.3 Valuation Multiples
   - 3.4 Growth
   - 3.5 Dividend
   - 3.6 Moat Score
   - 3.7 Quality Score
4. [Sentiment Analysis](#4-sentiment-analysis)
   - 4.1 Word Scoring
   - 4.2 Negation Handling
   - 4.3 Intensifier Weighting
   - 4.4 Recency Decay
   - 4.5 Publisher Reliability
   - 4.6 Aggregate Score
5. [Pattern Detection](#5-pattern-detection)
   - 5.1 Support & Resistance
   - 5.2 Trend Direction
   - 5.3 Candlestick Patterns
6. [Data Source & Known Limitations](#6-data-source--known-limitations)

---

## 1. Technical Analysis

**Source file:** `src/stock_market/stock_service.py` → `technical_analysis()`

### 1.1 RSI (Relative Strength Index)

The RSI measures the speed and magnitude of recent price changes on a scale of 0–100.

**Period:** 14 bars (days by default)

**Formula:**

```
For i in [1..N]:
    gain_i = max(close_i − close_{i-1},  0)
    loss_i = max(close_{i-1} − close_i,  0)

avg_gain = mean(gain[-14:])
avg_loss = mean(loss[-14:])

RS  = avg_gain / avg_loss
RSI = 100 − (100 / (1 + RS))
```

**Interpretation thresholds:**

| RSI Value    | Signal     |
|-------------|------------|
| > 70         | Overbought |
| < 30         | Oversold   |
| 30 – 70      | Neutral    |

**Known limitation:** Standard RSI uses Wilder's smoothed averages (EMA-based); this
implementation uses a simple rolling mean for the 14-period window. This may give slightly
more reactive readings. A future improvement would use Wilder's smoothing:
`avg_gain = (prev_avg_gain × 13 + current_gain) / 14`.

---

### 1.2 MACD (Moving Average Convergence/Divergence)

MACD identifies momentum changes using two exponential moving averages.

**Parameters:** EMA(12), EMA(26), Signal line EMA(9)

```
MACD line     = EMA(12) − EMA(26)
Signal line   = EMA(9) of MACD line
Histogram     = MACD line − Signal line
```

**EMA formula (used for all EMA calculations):**

```
multiplier = 2 / (span + 1)
EMA[0]     = close[0]
EMA[i]     = (close[i] − EMA[i-1]) × multiplier + EMA[i-1]
```

**Interpretation:**

| Condition                         | Signal   |
|----------------------------------|----------|
| MACD > Signal                    | Bullish  |
| MACD < Signal                    | Bearish  |
| Histogram crossing zero upward   | Momentum turning bullish |
| Histogram crossing zero downward | Momentum turning bearish |

---

### 1.3 Bollinger Bands

Bollinger Bands show volatility by placing bands ±2 standard deviations around a 20-day SMA.

**Parameters:** Period = 20, standard deviations = 2

```
SMA_20        = mean(close[-20:])
std_20        = population_std(close[-20:])

Upper Band    = SMA_20 + (2 × std_20)
Lower Band    = SMA_20 − (2 × std_20)
Middle Band   = SMA_20
```

**Interpretation:**

| Price relative to band | Signal               |
|------------------------|----------------------|
| Above upper band       | Overbought           |
| Below lower band       | Oversold             |
| Between bands          | Normal range         |

**Note:** Standard Bollinger Bands use population stddev (dividing by N, not N−1), which
is what this implementation uses. Some vendors use sample stddev (N−1).

---

### 1.4 Moving Averages

Simple moving averages computed over the last N closing prices.

```
SMA_n = mean(close[-n:])
```

Periods computed: **20, 50, 200** days.

Signals are noted as "above" or "below" each SMA.

---

## 2. Risk Assessment

**Source file:** `src/stock_market/stock_service.py` → `risk_score()`

**Inputs:** 1 year of daily closing prices fetched from yfinance.

### 2.1 Annual Volatility

```
daily_returns[i] = (close[i] − close[i-1]) / close[i-1]

mean_r   = mean(daily_returns)
variance = mean((r − mean_r)² for r in daily_returns)   ← population variance
daily_σ  = sqrt(variance)

annual_σ = daily_σ × sqrt(252) × 100      (in %)
```

**Why 252?** The US and most exchanges have ~252 trading days per year.
Indian exchanges (NSE/BSE): ~250 trading days — minor underestimation for Indian stocks.

---

### 2.2 Beta vs SPY

Beta measures the stock's sensitivity to broad market (S&P 500 proxied by SPY ETF).

```
Align stock and SPY daily returns to same length N.

cov(stock, SPY) = mean((stock_r[i] − mean_stock) × (SPY_r[i] − mean_SPY))
var(SPY)        = mean((SPY_r[i] − mean_SPY)²)

Beta = cov / var
```

| Beta Value | Interpretation                        |
|------------|---------------------------------------|
| > 1.5      | Amplifies market moves; high risk     |
| 1.0        | Moves in line with market             |
| 0.5–1.0    | Less volatile than market             |
| < 0        | Inverse relationship (rare)           |

**Known limitation:** Beta vs SPY is less meaningful for non-US stocks (e.g., RELIANCE.NS
should ideally be compared against NIFTY 50 / ^NSEI). A future improvement: auto-select
benchmark based on stock country.

---

### 2.3 Value-at-Risk (VaR 95%)

Parametric VaR assumes returns are normally distributed.

```
z₉₅ = 1.645   (95th percentile of standard normal)

VaR_95_daily = −(mean_r − z₉₅ × daily_σ) × 100    (in %)
```

**Interpretation:** "In 95% of trading days, the loss should not exceed this percentage."

**Known limitation:** Returns are not perfectly normal (fat tails exist). Historical VaR
or Cornish-Fisher VaR would be more robust. Expert review invited on this choice.

---

### 2.4 Sharpe Ratio

Measures return earned per unit of total risk.

```
risk_free_annual = 4.5%   (approximate Indian/US short-term rate assumption)
risk_free_daily  = 0.045 / 252

annual_return    = ((close[-1] / close[0]) ^ (252 / N) − 1) × 100

Sharpe = (mean_daily_return − rf_daily) / daily_σ × sqrt(252)
```

| Sharpe   | Quality         |
|----------|-----------------|
| > 2      | Excellent       |
| 1–2      | Good            |
| 0–1      | Adequate        |
| < 0      | Below risk-free |

**Expert note:** The risk-free rate is hardcoded at 4.5%. This should ideally be updated
periodically or pulled from a yield curve. Please flag if you'd like dynamic rate lookup.

---

### 2.5 Max Drawdown

Maximum observed peak-to-trough decline in closing price over the period.

```
peak       = close[0]
max_dd     = 0.0

for price in close_prices:
    if price > peak:
        peak = price
    drawdown = (peak − price) / peak
    if drawdown > max_dd:
        max_dd = drawdown

max_drawdown_pct = max_dd × 100
```

**Interpretation:** Max drawdown of 30% means if you held from the peak, you would have
lost 30% at the worst point before any recovery.

---

### 2.6 Sortino Ratio

Like Sharpe, but only penalises downside (negative) return volatility.

```
negative_returns = [r for r in daily_returns if r < 0]

downside_var_daily   = sum(r² for r in negative_returns) / total_N
downside_dev_annual  = sqrt(downside_var_daily) × sqrt(252)

annual_excess_return = annual_return/100 − 0.045

Sortino = annual_excess_return / downside_dev_annual
```

**Why total_N in denominator?** Using total N (not just the count of negative returns)
scales the downside deviation correctly relative to full-period risk.

**Interpretation:** Higher is better. Sortino > Sharpe usually means gains are volatile
but losses are not — a desirable asymmetry.

---

### 2.7 Calmar Ratio

Return earned per unit of maximum drawdown risk.

```
Calmar = (annual_return / 100) / (max_drawdown_pct / 100)
       = annual_return / max_drawdown_pct
```

| Calmar  | Interpretation      |
|---------|---------------------|
| > 3     | Very strong         |
| 1–3     | Satisfactory        |
| < 1     | Drawdown exceeds gain |

---

### 2.8 Composite Risk Score (1–10)

```
vol_score   = clamp(round(annual_σ / 5), 1, 10)
              [50% annual volatility → score 10]

beta_score  = clamp(round(Beta × 3.5), 1, 10)

var_score   = clamp(round(VaR_95_daily / 1.5), 1, 10)

composite   = 0.40 × vol_score + 0.30 × beta_score + 0.30 × var_score
```

| Score  | Risk Level  |
|--------|-------------|
| < 2.5  | Very Low    |
| 2.5–4  | Low         |
| 4–6    | Moderate    |
| 6–8    | High        |
| ≥ 8    | Very High   |

**Expert review note:** The weighting (40/30/30) and scaling factors (/5, ×3.5, /1.5)
are calibrated heuristically. An empirical calibration against historical risk events
across market caps would be valuable.

---

## 3. Fundamental Analysis — Warren Buffett Framework

**Source file:** `src/stock_market/fundamental_service.py` → `fundamental_analysis()`

All data fetched from `yfinance Ticker.info`.

### 3.1 Profitability

| Metric              | Formula / Source                                   |
|---------------------|----------------------------------------------------|
| ROE (%)             | `returnOnEquity × 100` from yfinance               |
| ROA (%)             | `returnOnAssets × 100` from yfinance               |
| Gross Margin (%)    | `grossMargins × 100` from yfinance                 |
| Operating Margin (%)| `operatingMargins × 100` from yfinance             |
| Net Margin (%)      | `profitMargins × 100` from yfinance                |
| EBITDA Margin (%)   | `ebitda / totalRevenue × 100` (self-computed)      |
| FCF Yield (%)       | `freeCashflow / marketCap × 100` (self-computed)   |

**Note:** yfinance `returnOnEquity` is a decimal (e.g. 0.35 = 35%); multiplied by 100.

---

### 3.2 Financial Safety

| Metric          | Formula / Source                               |
|-----------------|------------------------------------------------|
| Debt/Equity     | `debtToEquity / 100` (yfinance returns 155.3 for 155.3%) |
| Current Ratio   | `currentRatio` from yfinance                   |
| Quick Ratio     | `quickRatio` from yfinance                     |

**Data quality note:** yfinance's `debtToEquity` is inconsistently normalised across
tickers — sometimes returned as a ratio (1.55) and sometimes as a percentage (155.3).
The code applies a heuristic: if value > 20, divide by 100. Expert validation welcomed.

---

### 3.3 Valuation Multiples

| Metric         | Source key in yfinance info                  |
|----------------|----------------------------------------------|
| P/E (TTM)      | `trailingPE`                                 |
| Forward P/E    | `forwardPE`                                  |
| P/B            | `priceToBook`                                |
| PEG Ratio      | `pegRatio`                                   |
| P/S            | `priceToSalesTrailing12Months`               |
| EV/EBITDA      | `enterpriseToEbitda`                         |

---

### 3.4 Growth

| Metric                  | Source                      |
|-------------------------|-----------------------------|
| Earnings Growth (YoY %) | `earningsGrowth × 100`      |
| Revenue Growth (YoY %)  | `revenueGrowth × 100`       |

**Known limitation:** yfinance growth figures are trailing 12-month YoY, not forward-looking.

---

### 3.5 Dividend

| Metric             | Formula                                    |
|--------------------|--------------------------------------------|
| Dividend Yield (%) | `dividendYield × 100`                      |
| Payout Ratio (%)   | `payoutRatio × 100`                        |

---

### 3.6 Moat Score (0–10)

Economic moat is a qualitative concept (durable competitive advantage) quantified here
via 5 measurable proxies.  Each signal contributes a maximum of 2 points.

| Signal                 | 2 pts           | 1 pt            | 0 pts       |
|------------------------|-----------------|-----------------|-------------|
| ROE                    | ≥ 20%           | ≥ 15%, < 20%    | < 15%       |
| Operating Margin       | ≥ 25%           | ≥ 15%, < 25%    | < 15%       |
| FCF Yield              | ≥ 5%            | ≥ 2%, < 5%      | < 2%        |
| Debt / Equity          | < 0.30          | < 0.50, ≥ 0.30  | ≥ 0.50      |
| Earnings Growth (YoY)  | ≥ 15%           | ≥ 8%, < 15%     | < 8%        |

**Total moat score = sum of above.**

| Score | Moat Label      |
|-------|-----------------|
| ≥ 8   | Wide Moat       |
| ≥ 5   | Narrow Moat     |
| < 5   | No Clear Moat   |

**Expert review note:** Warren Buffett's actual moat analysis is qualitative (brand,
network effects, switching costs, cost advantages, regulatory moats). The above proxies
are a numerical approximation.  Thresholds were set by reviewing Buffett's historical
holdings and their typical metric ranges.  Please discuss with experts whether different
thresholds better suit Indian market context.

---

### 3.7 Quality Score (0–10)

Composite score combining moat, value, and safety.

```
value_sub_score:
  pe_pts   = 2 if pe < 15 else (1 if pe < 25 else 0)
  peg_pts  = 2 if peg < 1  else (1 if peg < 2  else 0)
  pb_pts   = 2 if pb < 1.5 else (1 if pb < 3   else 0)
  value_sub_score = (pe_pts + peg_pts + pb_pts) / 6 × 10   → 0–10

safety_sub_score:
  cr_pts   = 2 if current_ratio > 2 else (1 if > 1.5 else 0)
  qr_pts   = 2 if quick_ratio   > 1 else (1 if > 0.8 else 0)
  de_pts   = 2 if debt_equity   < 0.3 else (1 if < 0.7 else 0)
  safety_sub_score = (cr_pts + qr_pts + de_pts) / 6 × 10   → 0–10

quality_score = moat_score × 0.50 + value_sub_score × 0.25 + safety_sub_score × 0.25
```

| quality_score | Quality Label |
|---------------|---------------|
| ≥ 7           | High Quality  |
| ≥ 4.5         | Fair Quality  |
| < 4.5         | Low Quality   |

---

## 4. Sentiment Analysis

**Source file:** `src/stock_market/stock_service.py` → `sentiment_analysis()`

### 4.1 Word Scoring

For each headline title, words are tokenised as lowercase alphanumeric tokens.

- Each **POSITIVE_WORD** occurrence contributes **+1.0** to `pos_score`.
- Each **NEGATIVE_WORD** occurrence contributes **+1.0** to `neg_score`.
- Vocabulary size: ~60 positive words, ~60 negative words (financial/earnings domain).

```
item_score = (pos_score − neg_score) / (pos_score + neg_score)   if total > 0
           = 0.0                                                     otherwise
```

Range: [−1, +1].

### 4.2 Negation Handling

Context window: 3 words before the keyword.

If any of `{"not", "no", "never", "without", "fails", "fail", "despite", "lack", "lacks"}`
appears in the 3-word look-back:

- Positive word → flipped: contributes **+1.0 to neg_score** (counts as negative).
- Negative word → partially flipped: contributes **+0.5 to pos_score** (weakly positive).

The asymmetry (full flip for positive, half-flip for negative) reflects that "not bad"
is weakly positive but "not good" is strongly negative in financial context.

### 4.3 Intensifier Weighting

Words `{"significantly", "sharply", "dramatically", "substantially", "hugely",
"massively", "enormously", "considerably", "strongly", "greatly"}` appearing within
2 words before a keyword multiply that keyword's contribution by **1.5×**.

### 4.4 Recency Decay

Each news item's score is multiplied by a recency weight based on the item's
`providerPublishTime` Unix timestamp.

| Age (days from now) | Weight |
|---------------------|--------|
| ≤ 7                 | 1.00   |
| 8–14                | 0.80   |
| > 14                | 0.60   |

### 4.5 Publisher Reliability

News from trusted financial publishers receives a **1.3× boost**:

> Reuters, Bloomberg, WSJ/Wall Street Journal, Financial Times/FT,
> CNBC, Barron's, Forbes, MarketWatch

### 4.6 Aggregate Score

```
total_weight  = Σ recency_weight × publisher_weight  for all items
agg_score     = Σ (item_score × total_weight) / total_weight

Label:
  agg_score > +0.10  → Positive
  agg_score < −0.10  → Negative
  else               → Neutral
```

**Expert review note:** The keyword vocabulary is English-biased. Indian stocks may have
news in hybrid English/Hindi. Adding Hindi financial keywords or integrating a proper
NLP model (e.g. finBERT) would improve accuracy. The threshold 0.10 is heuristically set.

---

## 5. Pattern Detection

**Source file:** `src/stock_market/stock_service.py` → `pattern_detection()`

### 5.1 Support & Resistance

Rolling min/max of the last 20 periods:

```
support    = min(lows[-20:])
resistance = max(highs[-20:])
```

**Expert note:** This is the simplest form of S&R. Real technical analysts use cluster
zones, pivot points, Fibonacci retracements. Future improvement: pivot points formula
`P = (H + L + C) / 3`.

### 5.2 Trend Direction

```
sma20_now  = mean(close[-20:])
sma20_prev = mean(close[-21:-1])

if   sma20_now > sma20_prev × 1.001:  trend = "Uptrend"
elif sma20_now < sma20_prev × 0.999:  trend = "Downtrend"
else:                                  trend = "Sideways"
```

The 0.1% threshold prevents noise from triggering trend changes.

### 5.3 Candlestick Patterns

Detected on the most recent candle using standard candlestick geometry.

**Doji:** Open ≈ Close (body ≤ 10% of full candle range)

```
body  = |close − open|
range = high − low
Doji if range > 0 and body / range < 0.10
```

**Hammer:** Small body in upper third, long lower shadow (≥ 2× body)

```
lower_shadow = min(open, close) − low
body         = |close − open|
Hammer if lower_shadow >= 2 × body and body > 0
```

**Shooting Star:** Inverse of hammer — long upper shadow, small body at bottom

```
upper_shadow = high − max(open, close)
Shooting Star if upper_shadow >= 2 × body and body > 0
```

**Bullish Engulfing:** Current candle's body completely engulfs previous candle's body,
and sentiment flips from bearish to bullish.

```
Bullish Engulfing if:
  prev_open > prev_close   (prev was bearish)
  AND curr_close > curr_open   (curr is bullish)
  AND curr_open  < prev_close  (current opens below prev close)
  AND curr_close > prev_open   (current closes above prev open)
```

**Bearish Engulfing:** Mirror of bullish engulfing.

---

## 6. Data Source & Known Limitations

| Item                  | Detail                                                   |
|-----------------------|----------------------------------------------------------|
| **Data provider**     | yfinance (unofficial Yahoo Finance API wrapper)          |
| **Refresh frequency** | Real-time during market hours; 15-min delay for free data |
| **Historical limit**  | Up to "max" (~20 years for large caps)                   |
| **Indian stocks**     | Suffix: `.NS` (NSE), `.BO` (BSE)  e.g. `RELIANCE.NS`   |
| **Currencies**        | USD for US stocks; INR for Indian stocks (from yfinance) |
| **yfinance stability**| Unofficial API; may break if Yahoo Finance changes schema |

### Known Gaps & Planned Improvements

| Gap                             | Impact        | Planned Fix                              |
|---------------------------------|---------------|------------------------------------------|
| Beta vs SPY for Indian stocks   | Medium        | Use ^NSEI benchmark for Indian tickers   |
| Drawdown: only 1-year look-back | Medium        | Allow configurable period                |
| Sortino: uses 0% target return  | Low           | Allow user-specified target/MAR          |
| Sentiment: English only         | High (India)  | Add Hindi financial vocabulary           |
| Sentiment: no context window    | Medium        | Sentence-level model (finBERT)           |
| Beta/YTD not available all tickers | Low        | Graceful fallback already in code        |
| yfinance D/E normalisation bug  | Medium        | Heuristic fix in place; needs validation |
| RSI: simple mean vs Wilder      | Low           | Implement Wilder's smoothing             |
| VaR: parametric (normal dist)   | Medium        | Consider Historical VaR fallback         |

---

*Last updated: auto-generated by OctaMind development session.*
*All calculation code versions are tracked in git history.*
