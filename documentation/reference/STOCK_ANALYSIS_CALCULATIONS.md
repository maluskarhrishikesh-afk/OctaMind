# Stock Analysis — Calculation Methodology

> **Purpose:** This document describes every formula used by Octa Bot's stock market
> analysis engine.  All calculations are implemented in pure Python with no third-party
> statistical library (except `math`).  The intent is to allow domain experts to
> review, challenge, and improve these formulas.
>
> **Ethical notice:** Octa Bot does **not** produce buy/sell recommendations or price
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
6. [Analyst Quick Snapshot Verdict](#6-analyst-quick-snapshot-verdict)
7. [Data Source & Known Limitations](#7-data-source--known-limitations)

---

## 1. Technical Analysis

**Source file:** `src/stock_market/stock_service.py` ? `technical_analysis()`

### 1.1 RSI (Relative Strength Index)

The RSI measures the speed and magnitude of recent price changes on a scale of 0–100.

**Period:** 14 bars (days by default)

**Formula:**

```
For i in [1..N]:
    gain_i = max(close_i - close_{i-1},  0)
    loss_i = max(close_{i-1} - close_i,  0)

avg_gain = mean(gain[-14:])
avg_loss = mean(loss[-14:])

RS  = avg_gain / avg_loss
RSI = 100 - (100 / (1 + RS))
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
MACD line     = EMA(12) - EMA(26)
Signal line   = EMA(9) of MACD line
Histogram     = MACD line - Signal line
```

**EMA formula (used for all EMA calculations):**

```
multiplier = 2 / (span + 1)
EMA[0]     = close[0]
EMA[i]     = (close[i] - EMA[i-1]) × multiplier + EMA[i-1]
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
Lower Band    = SMA_20 - (2 × std_20)
Middle Band   = SMA_20
```

**Interpretation:**

| Price relative to band | Signal               |
|------------------------|----------------------|
| Above upper band       | Overbought           |
| Below lower band       | Oversold             |
| Between bands          | Normal range         |

**Note:** Standard Bollinger Bands use population stddev (dividing by N, not N-1), which
is what this implementation uses. Some vendors use sample stddev (N-1).

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

**Source file:** `src/stock_market/stock_service.py` ? `risk_score()`

**Inputs:** 1 year of daily closing prices fetched from yfinance.

### 2.1 Annual Volatility

```
daily_returns[i] = (close[i] - close[i-1]) / close[i-1]

mean_r   = mean(daily_returns)
variance = sum((r - mean_r)² for r in daily_returns) / (N - 1)   ? sample variance (N-1)
daily_s  = sqrt(variance)

annual_s = daily_s × sqrt(252) × 100      (in %)
```

**Why sample variance (N-1)?** Sample variance is the standard statistical estimator
for a population parameter from a finite sample. Using N (population variance) slightly
understimates variance. The difference is negligible for N~250, but using N-1 is the
accepted convention in academic finance.

---

### 2.2 Beta vs SPY

Beta measures the stock's sensitivity to broad market (S&P 500 proxied by SPY ETF).

```
Align stock and SPY daily returns to same length N.

cov(stock, SPY) = sum((stock_r[i] - mean_stock) × (SPY_r[i] - mean_SPY)) / (N - 1)   ? sample
var(SPY)        = sum((SPY_r[i] - mean_SPY)²) / (N - 1)                               ? sample

Beta = cov / var
```

| Beta Value | Interpretation                        |
|------------|---------------------------------------|
| > 1.5      | Amplifies market moves; high risk     |
| 1.0        | Moves in line with market             |
| 0.5–1.0    | Less volatile than market             |
| < 0        | Inverse relationship (rare)           |

**Beta 60d (Rolling):** Same formula applied to the most recent 60 trading days only.
Shows how a stock’s market sensitivity has shifted recently vs. the 1-year baseline.
Regime changes (e.g. sector rotation, macro events) are visible here before they show
in the full-period beta.

**Downside Beta:** Beta computed using only days when SPY’s daily return was negative.
Captures how much the stock amplifies market downturns (tail-risk sensitivity).
Downside Beta > 1-year Beta implies the stock falls harder than average on bad days.
Institutional risk models (e.g. BlackRock Aladdin) isolate downside beta for this reason.

**Known limitation:** Beta vs SPY is less meaningful for non-US stocks (e.g., RELIANCE.NS
should ideally be compared against NIFTY 50 / ^NSEI). A future improvement: auto-select
benchmark based on stock country.

---

### 2.3 Value-at-Risk (VaR 95%)

**Parametric VaR** assumes returns are normally distributed.

```
z95 = 1.645   (95th percentile of standard normal)

VaR_95_parametric = -(mean_r - z95 × daily_s) × 100    (in %)
```

**Historical VaR** (no normality assumption; more robust in fat-tail regimes):

```
sorted_returns = sort(daily_returns, ascending)
idx            = floor(N × 0.05) - 1

VaR_95_historical = -sorted_returns[idx] × 100    (in %)
```

Both are daily figures: "In 95% of trading days, the loss should not exceed this %."

**Known limitation (parametric):** Returns are not perfectly normal (fat tails exist).
Historical VaR is now provided alongside parametric as the more empirically grounded estimate.

---

### 2.4 Sharpe Ratio

Measures return earned per unit of total risk.

```
risk_free_annual = 4.5%   (approximate Indian/US short-term rate assumption)
risk_free_daily  = 0.045 / 252

Sharpe = (mean_daily_return - rf_daily) / daily_s × sqrt(252)
```

**Clarification:** Sharpe is based on the arithmetic mean daily return annualised
(µ????? × v252), not the CAGR-style geometric return used in `annual_return_pct`.
Geometric annualisation and arithmetic annualisation diverge at higher volatilities;
the arithmetic form is the standard convention in the Sharpe Ratio definition (Sharpe, 1994).

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
    drawdown = (peak - price) / peak
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

annual_excess_return = annual_return/100 - 0.045

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
vol_score   = clamp(round(annual_s / 5), 1, 10)
              [50% annual volatility ? score 10]

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
| = 8    | Very High   |

**Expert review note:** The weighting (40/30/30) and scaling factors (/5, ×3.5, /1.5)
are calibrated heuristically. An empirical calibration against historical risk events
across market caps would be valuable.

**On percentile normalization (expert suggestion):** A more rigorous alternative is to
normalise each metric to its percentile rank over a reference universe (large/mid/small
cap stocks), then composite as `0.4 × vol_percentile + 0.3 × beta_percentile + 0.3 × var_percentile`.
This removes arbitrary scaling constants. It is not currently implemented because computing
universe percentiles requires fetching and caching risk metrics for hundreds of reference
stocks at query time, which is prohibitive for a real-time single-stock tool. The heuristic
scaling is a pragmatic approximation; consider this a known limitation for institutional use.

---

## 3. Fundamental Analysis — Warren Buffett Framework

**Source file:** `src/stock_market/fundamental_service.py` ? `fundamental_analysis()`

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
| ROE                    | = 20%           | = 15%, < 20%    | < 15%       |
| Operating Margin       | = 25%           | = 15%, < 25%    | < 15%       |
| FCF Yield              | = 5%            | = 2%, < 5%      | < 2%        |
| Debt / Equity          | < 0.30          | < 0.50, = 0.30  | = 0.50      |
| Earnings Growth (YoY)  | = 15%           | = 8%, < 15%     | < 8%        |

**Total moat score = sum of above.**

| Score | Moat Label      |
|-------|-----------------|
| = 8   | Wide Moat       |
| = 5   | Narrow Moat     |
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
  value_sub_score = (pe_pts + peg_pts + pb_pts) / 6 × 10   ? 0–10

safety_sub_score:
  cr_pts   = 2 if current_ratio > 2 else (1 if > 1.5 else 0)
  qr_pts   = 2 if quick_ratio   > 1 else (1 if > 0.8 else 0)
  de_pts   = 2 if debt_equity   < 0.3 else (1 if < 0.7 else 0)
  safety_sub_score = (cr_pts + qr_pts + de_pts) / 6 × 10   ? 0–10

quality_score = moat_score × 0.50 + value_sub_score × 0.25 + safety_sub_score × 0.25
```

| quality_score | Quality Label |
|---------------|---------------|
| = 7           | High Quality  |
| = 4.5         | Fair Quality  |
| < 4.5         | Low Quality   |

---

## 4. Sentiment Analysis

**Source file:** `src/stock_market/stock_service.py` ? `sentiment_analysis()`

### 4.1 Sentiment Engine — Two-Tier Architecture

**PRIMARY: LLM Classification (OpenAI / configured model)**

All headlines are sent in a single batch API call.  The model receives a numbered
list of headlines and returns a JSON array:

```json
[{"index": 0, "label": "Positive", "confidence": 0.87}, ...]
```

Advantages over keywords:
- Understands negation, sarcasm, and irony in context
- Handles macro news ("Fed pauses hikes" ? positive for equities)
- Confidence score per classification
- Full sentence context rather than individual words

Numeric score when LLM is used:
```
llm_sign   = +1.0 (Positive) | -1.0 (Negative) | 0.0 (Neutral)
item_score = llm_sign × confidence
```

Temperature = 0.0 (deterministic).  Timeout = 20s.  Fails gracefully to keyword fallback.

**FALLBACK: Keyword NLP** (used when LLM unavailable or errors)

See Section 4.2 onwards. The fallback is always available with zero latency.

**Compliance note:** The LLM classification model is used strictly for textual sentiment
interpretation of news headlines and does not generate price forecasts or investment
recommendations. Sentiment scores are descriptive indicators only.

### 4.2 Keyword Word Scoring (Fallback)

For each headline title, words are tokenised as lowercase alphanumeric tokens.

- Each **POSITIVE_WORD** occurrence contributes **+1.0** to `pos_score`.
- Each **NEGATIVE_WORD** occurrence contributes **+1.0** to `neg_score`.
- Vocabulary size: ~60 positive words, ~60 negative words (financial/earnings domain).

```
item_score = (pos_score - neg_score) / (pos_score + neg_score)   if total > 0
           = 0.0                                                     otherwise
```

Range: [-1, +1].

### 4.3 Negation Handling (Fallback)

Context window: 3 words before the keyword.

If any of `{"not", "no", "never", "without", "fails", "fail", "despite", "lack", "lacks"}`
appears in the 3-word look-back:

- Positive word ? flipped: contributes **+1.0 to neg_score** (counts as negative).
- Negative word ? partially flipped: contributes **+0.5 to pos_score** (weakly positive).

The asymmetry (full flip for positive, half-flip for negative) reflects that "not bad"
is weakly positive but "not good" is strongly negative in financial context.

### 4.4 Intensifier Weighting (Fallback)

Words `{"significantly", "sharply", "dramatically", "substantially", "hugely",
"massively", "enormously", "considerably", "strongly", "greatly"}` appearing within
2 words before a keyword multiply that keyword's contribution by **1.5×**.

### 4.5 Recency Decay (both tiers)

Each news item's score is multiplied by a recency weight based on the item's
`providerPublishTime` Unix timestamp.

| Age (days from now) | Weight |
|---------------------|--------|
| = 7                 | 1.00   |
| 8–14                | 0.80   |
| > 14                | 0.60   |

### 4.6 Publisher Reliability (both tiers)

News from trusted financial publishers receives a **1.3× boost**:

> Reuters, Bloomberg, WSJ/Wall Street Journal, Financial Times/FT,
> CNBC, Barron's, Forbes, MarketWatch

### 4.7 Aggregate Score (both tiers)

```
total_weight  = S recency_weight × publisher_weight  for all items
agg_score     = S (item_score × total_weight) / total_weight

Label:
  agg_score > +0.10  ? Positive
  agg_score < -0.10  ? Negative
  else               ? Neutral
```

**Expert review note:** The keyword vocabulary is English-biased. Indian stocks may have
news in hybrid English/Hindi. Adding Hindi financial keywords or integrating a proper
NLP model (e.g. finBERT) would improve accuracy. The threshold 0.10 is heuristically set.

---

## 5. Pattern Detection

**Source file:** `src/stock_market/stock_service.py` ? `pattern_detection()`

### 5.1 Classic Support & Resistance

Rolling min/max of the last 20 periods:

```
support    = min(lows[-20:])
resistance = max(highs[-20:])
```

**Expert note:** This is the simplest form of S&R. See 5.2 for richer levels.

### 5.2 Pivot Points (Classic Daily)

Based on the **previous session's** High, Low, Close.

```
P  = (H + L + C) / 3          ? Pivot
R1 = 2P - L
R2 = P + (H - L)
R3 = H + 2×(P - L)
S1 = 2P - H
S2 = P - (H - L)
S3 = L - 2×(H - P)
```

R1/R2/R3 = resistance levels.  S1/S2/S3 = support levels.
Pivot (P) is the primary reference level: price above P is generally considered bullish.

**Expert note:** Classic pivots are the most widely used by prop desks and retail traders.
Fibonacci pivots (`R1 = P + 0.382×(H-L)`) and Woodie pivots (`P = (H+L+2C)/4`) are
alternatives — expert review invited on preference.

### 5.3 52-Week High / Low

Fetched directly from `yfinance Ticker.info` fields `fiftyTwoWeekHigh` / `fiftyTwoWeekLow`.
These represent the highest and lowest traded prices over the trailing 52 weeks.

### 5.4 VWAP (Volume-Weighted Average Price)

```
typical_price_i = (High_i + Low_i + Close_i) / 3

VWAP = S(typical_price_i × Volume_i) / S(Volume_i)
```

Computed over **5-day hourly bars** (fetched with `period="5d", interval="1h"`).

**Important note for expert review:** This is a *multi-day rolling VWAP*, NOT a
single-session VWAP that resets at market open each day. Single-session VWAP requires
intraday tick or minute data. The 5-day VWAP serves as a medium-term trend reference:
- Price consistently above 5D VWAP ? generally bullish momentum
- Price crossing below 5D VWAP ? caution signal

**Bar-based approximation:** This VWAP uses hourly bar typical prices, not tick-level
transaction prices. True institutional VWAP is computed as `S(price_i × volume_i) / S(volume_i)`
over every individual trade or minute bar. The typical-price hourly approximation is
acceptable for directional context but differs from exchange-reported VWAP by a small
margin depending on intraday price distribution.

For single-session VWAP, we would need `period="1d", interval="1m"` and compute daily.

### 5.5 Volume Profile & Point of Control (POC)

**Algorithm:**

1. Divide the full price range `[min(lows), max(highs)]` into **20 equal-width buckets**.
2. For each daily bar, assign its volume to the bucket containing that day's close price.
3. **POC** = midpoint of the bucket with the highest total volume.
4. **Value Area** = the contiguous range around POC containing **70% of total volume**.
   - Start at POC bucket.
   - At each step, expand upward or downward by one bucket, choosing whichever
     has more volume (standard VA expansion algorithm).
   - Stop when cumulative volume in range = 70% of total.
5. **VAH** (Value Area High) = top of the high-side bucket.
   **VAL** (Value Area Low) = bottom of the low-side bucket.

**Interpretation:**
- POC = price level where the most trading occurred over the period (high-value area).
- Price within Value Area = consensus range.
- Price outside Value Area = potential mean-reversion zone (informational only).

**Expert note:** 20 buckets over 3 months is a coarse resolution. Market Profile analysis
typically uses 30-minute TPO (Time Price Opportunity) charts. Volume Profile buckets should
ideally be based on intraday data at 15-minute resolution for precision.
Expert calibration on bucket count and timeframe welcome.

**Equal-width bucket limitation:** Buckets are equal-width price intervals (e.g. a $10
stock split into 20 × $0.50 buckets). Professional systems instead align buckets to the
tick size or use fixed price increments (e.g. $0.25 for a mid-cap). Equal-width can
overly compress low-priced small-cap stocks and spread high-priced stocks too thinly.
The current implementation is satisfactory for qualitative POC/value-area context.

### 5.6 Trend Direction

```
sma20_now  = mean(close[-20:])
sma20_prev = mean(close[-21:-1])

if   sma20_now > sma20_prev × 1.001:  trend = "Uptrend"
elif sma20_now < sma20_prev × 0.999:  trend = "Downtrend"
else:                                  trend = "Sideways"
```

The 0.1% threshold prevents noise from triggering trend changes.

### 5.7 Candlestick Patterns

Detected on the most recent candle using standard candlestick geometry.

**Doji:** Open ˜ Close (body = 10% of full candle range)

```
body  = |close - open|
range = high - low
Doji if range > 0 and body / range < 0.10
```

**Hammer:** Small body in upper third, long lower shadow (= 2× body)

```
lower_shadow = min(open, close) - low
body         = |close - open|
Hammer if lower_shadow >= 2 × body and body > 0
```

**Shooting Star:** Inverse of hammer — long upper shadow, small body at bottom

```
upper_shadow = high - max(open, close)
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

## 6. Analyst Quick Snapshot Verdict

The **Analyst Verdict** cell (BUY / HOLD / AVOID) on the report cover page is a
purely mechanical composite score — **not** an investment recommendation.
It summarises five independent signals into a single label so that the cover
page headlines the overall picture without a human having to hunt through
all sections.

### 6.1 Scoring Formula

```
verdict_score =
    technical_pts   (max 3)   +
    risk_pts        (max 3)   +
    quality_pts     (max 2)   +
    sentiment_pts   (max 2)   +
    revenue_pts     (max 2)           ? added 2026-02-26
```

| Signal | Rule | Points |
|--------|------|--------|
| **Technical** | Bullish trend | 3 |
| | Neutral trend | 1 |
| | Bearish trend | 0 |
| **Risk** | Low risk label | 3 |
| | Moderate risk label | 2 |
| | Risk label present but not low/moderate | 1 |
| | No risk data | 0 |
| **Quality** | Quality score = 7/10 | 2 |
| | Quality score = 5/10 | 1 |
| | Quality score < 5/10 or N/A | 0 |
| **Sentiment** | Positive news sentiment | 2 |
| | Neutral news sentiment | 1 |
| | Negative sentiment | 0 |
| **Revenue Growth** | YoY revenue growth = 20 % | 2 |
| | YoY revenue growth = 10 % | 1 |
| | YoY revenue growth < 10 % | 0 |

### 6.2 Verdict Thresholds

| Verdict | Condition | Colour |
|---------|-----------|--------|
| **BUY** | score = 10 | Green |
| **HOLD** | score = 7 | Amber |
| **AVOID** | score < 7 | Red |

Maximum possible score = 14.  The thresholds are calibrated so that a company
need only be *good on balance* (not perfect) to reach HOLD, and must be
clearly strong in most signals to reach BUY.

### 6.3 Why Revenue Growth Was Added

High-growth technology / SaaS companies often show:
* A single bad quarter of earnings (YoY earnings growth negative) due to
  investment cycles, exceptional items, or base effects.
* Strong top-line momentum (revenue growth 15–25 %) that is invisible in
  the original four-signal formula.

Without the revenue signal, such companies were mechanically scored AVOID
when the underlying thesis was growth-funded investment — as seen with
INTELLECT.NS in Feb 2026 (20 % YoY revenue growth, earnings decline from
heavy hiring, but analyst consensus strongly positive).  The revenue bonus
brings the verdict closer to the true fundamental picture.

> ??  The verdict is still informational-only.  A BUY label does NOT mean
> "buy the stock".  Consult a SEBI-registered advisor before making any
> investment decision.

---

## 7. Data Source & Known Limitations

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

*Last updated: 2026-02-26 — added Section 6 (Analyst Verdict formula + revenue growth signal), fixed gross_margin_pct key in executive summary, added structured per-step logging and memory capture to `generate_full_report`.*
*All calculation code versions are tracked in git history.*
