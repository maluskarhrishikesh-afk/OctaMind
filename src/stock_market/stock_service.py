"""
Stock Market Analysis Service — OctaMind

All analysis is READ-ONLY. No buy/sell order functionality whatsoever.

Available tools:
  get_quote               current price, change, volume, market cap
  get_historical_data     OHLCV data for any period
  technical_analysis      RSI, MACD, Bollinger Bands, moving averages
  risk_score              volatility, Beta, VaR, Sharpe ratio
  pattern_detection       support/resistance, trend, candlestick patterns
  portfolio_analysis      diversification, correlation, sector allocation
  portfolio_suggestions   rebalancing hints, over/underweight flags
  sentiment_analysis      news headline NLP sentiment for a stock
  compare_stocks          side-by-side metric comparison
  market_overview         broad market health snapshot (SPY, QQQ, etc.)

Requires: pip install yfinance
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("stock_service")


# ── yfinance guard ─────────────────────────────────────────────────────────────

def _yf():
    """Import yfinance lazily, give a clear error if missing."""
    try:
        import yfinance as yf
        return yf
    except ImportError:
        raise ImportError(
            "yfinance is not installed. Run: pip install yfinance"
        )


def _ticker(symbol: str):
    return _yf().Ticker(symbol.upper().strip())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_float(val, decimals: int = 4) -> Optional[float]:
    try:
        v = float(val)
        return round(v, decimals)
    except (TypeError, ValueError):
        return None


def _ema(series, span: int):
    """Exponential moving average on a list of floats."""
    multiplier = 2 / (span + 1)
    ema_vals = []
    for i, val in enumerate(series):
        if i == 0:
            ema_vals.append(val)
        else:
            ema_vals.append((val - ema_vals[-1]) * multiplier + ema_vals[-1])
    return ema_vals


def _rsi(closes: List[float], period: int = 14) -> float:
    """Compute RSI for last bar."""
    if len(closes) < period + 1:
        return float("nan")
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


# ── Tool: get_quote ─────────────────────────────────────────────────────────────

def get_quote(symbol: str) -> Dict[str, Any]:
    """
    Get the current quote for a stock symbol.

    Args:
        symbol: Ticker symbol (e.g. "AAPL", "TSLA", "MSFT").

    Returns price, change, change_pct, volume, market_cap, pe_ratio, 52w_high/low.
    """
    try:
        t = _ticker(symbol)
        info = t.info
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        prev  = info.get("regularMarketPreviousClose") or info.get("previousClose", price)
        change = _safe_float(price - prev) if price and prev else None
        change_pct = _safe_float((price - prev) / prev * 100) if price and prev and prev != 0 else None
        return {
            "status":        "success",
            "symbol":        symbol.upper(),
            "name":          info.get("longName") or info.get("shortName", symbol),
            "price":         _safe_float(price),
            "currency":      info.get("currency", "USD"),
            "change":        change,
            "change_pct":    change_pct,
            "volume":        info.get("volume"),
            "avg_volume":    info.get("averageVolume"),
            "market_cap":    info.get("marketCap"),
            "pe_ratio":      _safe_float(info.get("trailingPE")),
            "eps":           _safe_float(info.get("epsTrailingTwelveMonths")),
            "dividend_yield":_safe_float(info.get("dividendYield", 0), 4),
            "52w_high":      _safe_float(info.get("fiftyTwoWeekHigh")),
            "52w_low":       _safe_float(info.get("fiftyTwoWeekLow")),
            "sector":        info.get("sector", ""),
            "industry":      info.get("industry", ""),
        }
    except Exception as exc:
        return {"status": "error", "symbol": symbol.upper(), "message": str(exc)}


# ── Tool: get_historical_data ───────────────────────────────────────────────────

def get_historical_data(symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
    """
    Get OHLCV historical data for a symbol.

    Args:
        symbol:   Ticker symbol.
        period:   "1d","5d","1mo","3mo","6mo","1y","2y","5y","ytd","max"
        interval: "1m","5m","15m","1h","1d","1wk","1mo"

    Returns list of OHLCV bars.
    """
    try:
        t = _ticker(symbol)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            return {"status": "error", "symbol": symbol.upper(), "message": "No historical data returned."}

        bars = []
        for dt, row in hist.iterrows():
            bars.append({
                "date":   str(dt.date()) if hasattr(dt, "date") else str(dt),
                "open":   _safe_float(row["Open"]),
                "high":   _safe_float(row["High"]),
                "low":    _safe_float(row["Low"]),
                "close":  _safe_float(row["Close"]),
                "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else None,
            })

        return {
            "status":   "success",
            "symbol":   symbol.upper(),
            "period":   period,
            "interval": interval,
            "bars":     bars,
            "count":    len(bars),
        }
    except Exception as exc:
        return {"status": "error", "symbol": symbol.upper(), "message": str(exc)}


# ── Tool: technical_analysis ────────────────────────────────────────────────────

def technical_analysis(symbol: str, period: str = "6mo") -> Dict[str, Any]:
    """
    Compute technical indicators: RSI, MACD, Bollinger Bands, SMA-20/50/200.

    Args:
        symbol: Ticker symbol.
        period: Historical period for calculation (default "6mo").

    Returns dict of indicators with buy/neutral/sell signals for each.
    """
    try:
        t = _ticker(symbol)
        hist = t.history(period=period)
        if hist.empty or len(hist) < 20:
            return {"status": "error", "symbol": symbol.upper(), "message": "Insufficient data for technical analysis."}

        closes = [float(c) for c in hist["Close"].dropna()]
        latest = closes[-1]

        # SMA
        sma20  = round(sum(closes[-20:]) / 20, 4) if len(closes) >= 20 else None
        sma50  = round(sum(closes[-50:]) / 50, 4) if len(closes) >= 50 else None
        sma200 = round(sum(closes[-200:]) / 200, 4) if len(closes) >= 200 else None

        # RSI
        rsi_val = _rsi(closes, 14)

        # MACD (12,26,9)
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        macd_line  = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
        signal_line = _ema(macd_line, 9)
        macd_val   = round(macd_line[-1], 4)
        signal_val = round(signal_line[-1], 4)
        macd_hist  = round(macd_val - signal_val, 4)

        # Bollinger Bands (20-day)
        mean20 = sma20 or latest
        std20  = (sum((c - mean20) ** 2 for c in closes[-20:]) / 20) ** 0.5
        bb_upper = round(mean20 + 2 * std20, 4)
        bb_lower = round(mean20 - 2 * std20, 4)

        # Signals
        def price_vs_ma(price, ma):
            if ma is None:
                return "N/A"
            return "above" if price > ma else "below"

        rsi_signal = "overbought" if rsi_val > 70 else ("oversold" if rsi_val < 30 else "neutral")
        macd_signal = "bullish" if macd_hist > 0 else "bearish"
        bb_signal   = "overbought" if latest > bb_upper else ("oversold" if latest < bb_lower else "neutral")

        return {
            "status":        "success",
            "symbol":        symbol.upper(),
            "latest_close":  round(latest, 4),
            "rsi":           {"value": rsi_val, "signal": rsi_signal},
            "macd":          {"macd": macd_val, "signal": signal_val, "histogram": macd_hist, "signal_text": macd_signal},
            "bollinger":     {"upper": bb_upper, "middle": round(mean20, 4), "lower": bb_lower, "signal": bb_signal},
            "moving_averages": {
                "sma20":  sma20,  "vs_sma20":  price_vs_ma(latest, sma20),
                "sma50":  sma50,  "vs_sma50":  price_vs_ma(latest, sma50),
                "sma200": sma200, "vs_sma200": price_vs_ma(latest, sma200),
            },
        }
    except Exception as exc:
        return {"status": "error", "symbol": symbol.upper(), "message": str(exc)}


# ── Tool: risk_score ─────────────────────────────────────────────────────────────

def risk_score(symbol: str, period: str = "1y") -> Dict[str, Any]:
    """
    Compute risk metrics for a stock.

    Calculated metrics
    ------------------
    Annual Volatility   = daily_std × √252 × 100
                          Measures price dispersion; higher = more uncertainty.

    Beta vs SPY         = Cov(stock_returns, SPY_returns) / Var(SPY_returns)
                          >1 → amplifies market moves; <1 → more stable than market.

    VaR 95% (daily)     = -(μ − 1.645 × σ_daily) × 100
                          Parametric; represents worst expected daily loss 95% of time.

    Sharpe Ratio        = (annualised_return − risk_free) / annual_volatility
                          Risk-free rate: 4.5% p.a.  >1 = good; <0 = losing vs risk-free.

    Max Drawdown        = (peak_price − trough_price) / peak_price × 100
                          Maximum observed loss from a historical peak to a trough.

    Sortino Ratio       = (annualised_return − risk_free) / downside_deviation
                          Like Sharpe but penalises only negative-return volatility.
                          downside_deviation = std(min(r, 0)) × √252

    Calmar Ratio        = annualised_return / |max_drawdown|
                          Return earned per unit of maximum drawdown risk.

    Composite Risk Score (1–10)
                        = weighted(vol_score×40% + beta_score×30% + var_score×30%)
                          where each component is linearly scaled to [1, 10].

    Args:
        symbol: Ticker symbol.
        period: Historical period (default "1y").

    Returns risk metrics and a narrative risk_level label.
    """
    import math

    try:
        yf = _yf()
        t = _ticker(symbol)
        hist = t.history(period=period)
        if hist.empty or len(hist) < 30:
            return {"status": "error", "symbol": symbol.upper(), "message": "Insufficient data for risk analysis."}

        closes = [float(c) for c in hist["Close"].dropna()]
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

        n = len(returns)
        mean_ret = sum(returns) / n
        variance = sum((r - mean_ret) ** 2 for r in returns) / n
        daily_vol = math.sqrt(variance)
        annual_vol = round(daily_vol * math.sqrt(252) * 100, 2)

        # Annualised return
        total_return = (closes[-1] / closes[0] - 1)
        annual_return = round(((1 + total_return) ** (252 / len(closes)) - 1) * 100, 2)

        # VaR 95% (parametric, daily)
        z95 = 1.645
        var_95 = round(-(mean_ret - z95 * daily_vol) * 100, 3)

        # Beta vs SPY
        spy_hist = yf.Ticker("SPY").history(period=period)
        beta = None
        if not spy_hist.empty:
            spy_closes = [float(c) for c in spy_hist["Close"].dropna()]
            spy_returns = [(spy_closes[i] - spy_closes[i - 1]) / spy_closes[i - 1]
                          for i in range(1, min(n + 1, len(spy_closes)))]
            min_len = min(len(returns), len(spy_returns))
            r1 = returns[-min_len:]
            r2 = spy_returns[-min_len:]
            m1 = sum(r1) / len(r1)
            m2 = sum(r2) / len(r2)
            cov = sum((a - m1) * (b - m2) for a, b in zip(r1, r2)) / len(r1)
            spy_var = sum((b - m2) ** 2 for b in r2) / len(r2)
            beta = round(cov / spy_var, 3) if spy_var != 0 else None

        # Sharpe ratio (risk-free = 4.5% annual)
        rf_daily = 0.045 / 252
        sharpe = round((mean_ret - rf_daily) / daily_vol * math.sqrt(252), 3) if daily_vol > 0 else None

        # ── Max Drawdown ────────────────────────────────────────────────────────
        # Walk through close prices; track running peak and measure drawdowns.
        peak = closes[0]
        max_dd = 0.0
        for price in closes:
            if price > peak:
                peak = price
            dd = (peak - price) / peak
            if dd > max_dd:
                max_dd = dd
        max_drawdown_pct = round(max_dd * 100, 2)

        # ── Sortino Ratio ───────────────────────────────────────────────────────
        # Downside deviation uses only returns below zero (target return = 0).
        negative_returns = [r for r in returns if r < 0]
        sortino = None
        if negative_returns:
            downside_var = sum(r ** 2 for r in negative_returns) / len(returns)
            downside_dev_annual = math.sqrt(downside_var) * math.sqrt(252)
            if downside_dev_annual > 0:
                annual_excess = (annual_return / 100) - 0.045  # above risk-free
                sortino = round(annual_excess / downside_dev_annual, 3)

        # ── Calmar Ratio ────────────────────────────────────────────────────────
        calmar = None
        if max_drawdown_pct > 0:
            calmar = round((annual_return / 100) / (max_drawdown_pct / 100), 3)

        # Composite risk score 1-10 (40% vol, 30% beta, 30% VaR)
        vol_score  = min(10, max(1, round(annual_vol / 5)))      # 50% ann vol → score 10
        beta_score = min(10, max(1, round((beta or 1.0) * 3.5)))
        var_score  = min(10, max(1, round(var_95 / 1.5)))
        composite  = round(vol_score * 0.40 + beta_score * 0.30 + var_score * 0.30, 1)

        risk_level = (
            "Very Low"   if composite < 2.5 else
            "Low"        if composite < 4   else
            "Moderate"   if composite < 6   else
            "High"       if composite < 8   else
            "Very High"
        )

        return {
            "status":                "success",
            "symbol":                symbol.upper(),
            "annual_volatility_pct": annual_vol,
            "annual_return_pct":     annual_return,
            "beta":                  beta,
            "var_95_daily_pct":      var_95,
            "sharpe_ratio":          sharpe,
            "sortino_ratio":         sortino,
            "max_drawdown_pct":      max_drawdown_pct,
            "calmar_ratio":          calmar,
            "risk_score":            composite,
            "risk_level":            risk_level,
        }
    except Exception as exc:
        return {"status": "error", "symbol": symbol.upper(), "message": str(exc)}


# ── Tool: pattern_detection ─────────────────────────────────────────────────────

def pattern_detection(symbol: str, period: str = "3mo") -> Dict[str, Any]:
    """
    Detect support/resistance, trend direction, and basic candlestick patterns
    (doji, hammer, engulfing, shooting star).

    Args:
        symbol: Ticker symbol.
        period: Historical period (default "3mo").

    Returns detected patterns, support, resistance, and trend.
    """
    try:
        t = _ticker(symbol)
        hist = t.history(period=period)
        if hist.empty or len(hist) < 20:
            return {"status": "error", "symbol": symbol.upper(), "message": "Insufficient data."}

        closes = list(hist["Close"].dropna())
        highs  = list(hist["High"].dropna())
        lows   = list(hist["Low"].dropna())
        opens  = list(hist["Open"].dropna())

        # Support & Resistance (rolling 20-period min/max)
        lookback = min(20, len(closes))
        support    = round(min(lows[-lookback:]), 4)
        resistance = round(max(highs[-lookback:]), 4)
        latest     = closes[-1]

        # Trend (SMA 20 direction)
        sma20_now  = sum(closes[-20:]) / 20
        sma20_prev = sum(closes[-21:-1]) / 20 if len(closes) >= 21 else sma20_now
        trend = "uptrend" if sma20_now > sma20_prev else ("downtrend" if sma20_now < sma20_prev else "sideways")

        patterns: List[str] = []
        # Check last candle(s)
        if len(closes) >= 2:
            o, c, h, l = opens[-1], closes[-1], highs[-1], lows[-1]
            body  = abs(c - o)
            range_ = h - l if h != l else 0.0001

            # Doji: very small body
            if body / range_ < 0.1:
                patterns.append("Doji — indecision candle")

            # Hammer (bullish): small body, long lower shadow, in downtrend
            lower_shadow = min(o, c) - l
            upper_shadow = h - max(o, c)
            if lower_shadow > 2 * body and upper_shadow < body and trend == "downtrend":
                patterns.append("Hammer — potential bullish reversal")

            # Shooting Star (bearish): long upper shadow, small body, in uptrend
            if upper_shadow > 2 * body and lower_shadow < body and trend == "uptrend":
                patterns.append("Shooting Star — potential bearish reversal")

            # Bullish Engulfing
            if len(closes) >= 2:
                o_prev, c_prev = opens[-2], closes[-2]
                if c_prev < o_prev and c > o and c > o_prev and o < c_prev:
                    patterns.append("Bullish Engulfing — buy signal")

            # Bearish Engulfing
            if len(closes) >= 2:
                o_prev, c_prev = opens[-2], closes[-2]
                if c_prev > o_prev and c < o and c < o_prev and o > c_prev:
                    patterns.append("Bearish Engulfing — sell pressure signal")

        price_position = (
            "near resistance" if latest > resistance * 0.97 else
            "near support"    if latest < support * 1.03    else
            "mid-range"
        )

        return {
            "status":          "success",
            "symbol":          symbol.upper(),
            "trend":           trend,
            "support":         support,
            "resistance":      resistance,
            "latest_close":    round(latest, 4),
            "price_position":  price_position,
            "patterns":        patterns if patterns else ["No strong candlestick pattern detected"],
        }
    except Exception as exc:
        return {"status": "error", "symbol": symbol.upper(), "message": str(exc)}


# ── Tool: portfolio_analysis ─────────────────────────────────────────────────────

def portfolio_analysis(symbols: List[str], period: str = "1y") -> Dict[str, Any]:
    """
    Analyse a portfolio: sector allocation, pairwise correlations, diversification score.

    Args:
        symbols: List of ticker symbols e.g. ["AAPL","MSFT","JPM","JNJ"].
        period:  Historical period for correlation (default "1y").

    Returns sector breakdown, correlation matrix, and a diversification rating.
    """
    if not symbols:
        return {"status": "error", "message": "No symbols provided."}
    if len(symbols) < 2:
        return {"status": "error", "message": "Portfolio analysis requires at least 2 symbols."}

    try:
        yf = _yf()
        sectors: Dict[str, List[str]] = {}
        returns_map: Dict[str, List[float]] = {}

        for sym in symbols:
            t = yf.Ticker(sym.upper())
            info = t.info
            sector = info.get("sector", "Unknown")
            sectors.setdefault(sector, []).append(sym.upper())

            hist = t.history(period=period)
            closes = [float(c) for c in hist["Close"].dropna()]
            if len(closes) > 1:
                returns_map[sym.upper()] = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

        # Pairwise correlations
        import math
        syms = [s.upper() for s in symbols if s.upper() in returns_map]
        corr_matrix: Dict[str, Dict[str, float]] = {}
        for s1 in syms:
            corr_matrix[s1] = {}
            for s2 in syms:
                r1 = returns_map[s1]
                r2 = returns_map[s2]
                min_len = min(len(r1), len(r2))
                if min_len < 10:
                    corr_matrix[s1][s2] = None
                    continue
                r1, r2 = r1[-min_len:], r2[-min_len:]
                m1, m2 = sum(r1) / len(r1), sum(r2) / len(r2)
                cov = sum((a - m1) * (b - m2) for a, b in zip(r1, r2)) / len(r1)
                s1_std = math.sqrt(sum((a - m1) ** 2 for a in r1) / len(r1))
                s2_std = math.sqrt(sum((b - m2) ** 2 for b in r2) / len(r2))
                corr = round(cov / (s1_std * s2_std), 3) if s1_std * s2_std != 0 else 1.0
                corr_matrix[s1][s2] = corr

        # Diversification score: penalise high correlations
        corr_vals = [abs(corr_matrix[s1][s2]) for s1 in syms for s2 in syms if s1 != s2 and corr_matrix[s1].get(s2) is not None]
        avg_corr = round(sum(corr_vals) / len(corr_vals), 3) if corr_vals else 1.0
        num_sectors = len(sectors)
        diversity_score = round(min(10, (1 - avg_corr) * 5 + num_sectors * 0.5), 1)
        diversity_label = (
            "Poor"      if diversity_score < 3 else
            "Fair"      if diversity_score < 5 else
            "Good"      if diversity_score < 7 else
            "Excellent"
        )

        return {
            "status":             "success",
            "symbols":            [s.upper() for s in symbols],
            "sector_allocation":  {k: v for k, v in sectors.items()},
            "num_sectors":        num_sectors,
            "correlation_matrix": corr_matrix,
            "avg_correlation":    avg_corr,
            "diversification_score": diversity_score,
            "diversification":    diversity_label,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Tool: portfolio_suggestions ─────────────────────────────────────────────────

def portfolio_suggestions(symbols: List[str]) -> Dict[str, Any]:
    """
    Provide rebalancing hints and flag over/underweight positions.
    Assumes equal-weight target. No buy/sell advice — informational only.

    Args:
        symbols: List of ticker symbols.

    Returns diversification insights, concentration warnings, and suggested adjustments.
    """
    if not symbols:
        return {"status": "error", "message": "No symbols provided."}

    try:
        yf = _yf()
        data: Dict[str, Dict] = {}
        sector_map: Dict[str, List[str]] = {}
        for sym in symbols:
            t = yf.Ticker(sym.upper())
            info = t.info
            market_cap = info.get("marketCap", 0) or 0
            sector = info.get("sector", "Unknown")
            sector_map.setdefault(sector, []).append(sym.upper())
            data[sym.upper()] = {
                "name":       info.get("shortName", sym),
                "sector":     sector,
                "market_cap": market_cap,
            }

        n = len(symbols)
        target_weight = round(100 / n, 1)

        suggestions: List[str] = []

        # Sector concentration
        for sector, syms in sector_map.items():
            weight = round(len(syms) / n * 100, 1)
            if weight > 40:
                suggestions.append(
                    f"⚠️ High sector concentration: {weight}% in {sector} "
                    f"({', '.join(syms)}). Consider diversifying across more sectors."
                )

        if len(sector_map) == 1:
            suggestions.append("⚠️ All holdings are in the same sector — zero sector diversification.")

        # Small portfolio
        if n < 5:
            suggestions.append(
                f"ℹ️ Portfolio has only {n} holding(s). "
                "Portfolios with 15–25 diversified stocks historically reduce unsystematic risk significantly."
            )

        # Large-cap vs mixed
        large_caps = [s for s, d in data.items() if d["market_cap"] > 10e9]
        if len(large_caps) == n:
            suggestions.append(
                "ℹ️ Portfolio is 100% large-cap. Consider adding mid/small-cap exposure for growth potential."
            )

        if not suggestions:
            suggestions.append("✅ Portfolio looks reasonably diversified. No immediate concentration issues detected.")

        return {
            "status":         "success",
            "symbols":        [s.upper() for s in symbols],
            "target_weight_pct": target_weight,
            "holdings":       data,
            "suggestions":    suggestions,
            "note":           "This is informational only. Not financial advice.",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Tool: sentiment_analysis ─────────────────────────────────────────────────────

def sentiment_analysis(symbol: str) -> Dict[str, Any]:
    """
    Analyse recent news headlines for a stock and compute a sentiment score.

    Algorithm
    ---------
    1. Fetch up to 15 recent news items from yfinance.

    2. For each headline:
       a. Tokenise to lowercase words.
       b. Check for negation context: if one of ["not","no","never","without",
          "fails","disappoint","miss"] appears within 3 words before a
          POSITIVE keyword → flip that keyword's contribution to negative.
       c. Check for intensifiers: "significantly", "sharply", "dramatically",
          "substantially", "hugely" within 2 words before any keyword → 1.5×.
       d. Count positive_score and negative_score (with flips/weights).
       e. item_score = (pos_score − neg_score) / (pos_score + neg_score)
          Range [−1, +1].  Neutral when both = 0.

    3. Recency decay applied to each item's score:
       age_days ≤ 7  → weight 1.0
       age_days ≤ 14 → weight 0.8
       age_days > 14 → weight 0.6

    4. Publisher reliability boost: Reuters, Bloomberg, WSJ, Financial Times,
       CNBC, Forbes, Barron's → weight × 1.3.

    5. Weighted aggregate score = Σ(item_score × total_weight) / Σ(weights).
       Threshold: > +0.10 → Positive; < −0.10 → Negative; else Neutral.

    Args:
        symbol: Ticker symbol.

    Returns news items, individual sentiments, and aggregate score.
    """
    POSITIVE_WORDS = {
        # Earnings / growth
        "beat", "beats", "growth", "profit", "profits", "record", "surge", "surges",
        "soar", "soars", "gain", "gains", "bull", "bullish", "upgrade", "upgrades",
        "strong", "stronger", "robust", "positive", "innovative", "innovation",
        "launch", "launches", "expand", "expansion", "exceed", "exceeds",
        "raised", "raise", "outperform", "outperforms", "recovery", "recovers",
        "partnership", "partnerships", "dividend", "dividends", "breakthrough",
        "milestone", "optimistic", "rally", "rallies", "accelerate", "accelerates",
        "improve", "improves", "improvement", "rebound", "rebounds", "advance",
        "advances", "boost", "boosts", "excellent", "exceptional", "impressive",
        "increase", "increases", "higher", "upbeat", "buoyant", "strong",
        "overweight", "buy", "top", "outperformance", "upward", "upside",
        "record-high", "all-time-high", "winning", "win", "wins", "profit",
        "bonus", "benefits", "surplus", "revenue-beat", "guidance-raise",
        "better-than-expected", "ahead", "returns", "inflow", "inflows",
        "cash-flow", "demand", "resurgence", "adoption", "momentum",
    }
    NEGATIVE_WORDS = {
        # Losses / risk
        "miss", "misses", "loss", "losses", "decline", "declines", "fall", "falls",
        "drop", "drops", "cut", "cuts", "layoff", "layoffs", "downgrade", "downgrades",
        "weak", "weaker", "negative", "lawsuit", "lawsuits", "recall", "recalls",
        "fraud", "penalty", "penalties", "fine", "fines", "ban", "bans",
        "warning", "warnings", "risk", "risks", "concern", "concerns", "below",
        "missed", "resign", "resigns", "investigate", "investigation",
        "crisis", "debt", "default", "disappointing", "disappoint",
        "disappoints", "shrink", "shrinks", "contraction", "contractions",
        "underperform", "underperforms", "bearish", "bear", "bearish",
        "downside", "downward", "underweight", "sell", "short",
        "slump", "slumps", "plunge", "plunges", "crash", "crashes",
        "recession", "slowdown", "weak", "sluggish", "volatile", "volatility",
        "uncertainty", "uncertain", "headwind", "headwinds", "pressure",
        "pressures", "halt", "halts", "suspended", "suspension", "charges",
        "charge", "impairment", "write-off", "write-down", "shortfall",
        "miss", "below-expectations", "guidance-cut", "downward-revision",
        "outflow", "outflows", "deficit", "probe", "subpoena",
    }
    NEGATION_WORDS = {"not", "no", "never", "without", "fails", "fail", "despite", "lack", "lacks"}
    INTENSIFIER_WORDS = {"significantly", "sharply", "dramatically", "substantially", "hugely",
                         "massively", "enormously", "considerably", "strongly", "greatly"}
    TRUSTED_PUBLISHERS = {"reuters", "bloomberg", "wsj", "wall street journal", "financial times",
                          "ft", "cnbc", "barrons", "barron's", "forbes", "marketwatch"}

    try:
        t = _ticker(symbol)
        news = t.news

        if not news:
            return {
                "status": "success", "symbol": symbol.upper(),
                "message": "No recent news found.",
                "overall_sentiment": "Neutral", "aggregate_score": 0.0,
                "positive_headlines": 0, "negative_headlines": 0, "neutral_headlines": 0,
                "news_items": [],
            }

        now_ts = datetime.utcnow().timestamp()
        scored_items = []

        for item in news[:15]:
            title = (item.get("title") or "").strip()
            raw_words = re.findall(r"\b\w+\b", title.lower())

            pos_score = 0.0
            neg_score = 0.0

            for idx, word in enumerate(raw_words):
                # look-back window (up to 3 positions)
                context_start = max(0, idx - 3)
                context = raw_words[context_start:idx]

                is_negated    = any(w in NEGATION_WORDS       for w in context)
                is_intensified = any(w in INTENSIFIER_WORDS   for w in raw_words[max(0, idx - 2):idx])
                intensity = 1.5 if is_intensified else 1.0

                if word in POSITIVE_WORDS:
                    if is_negated:
                        neg_score += 1.0 * intensity  # flip
                    else:
                        pos_score += 1.0 * intensity
                elif word in NEGATIVE_WORDS:
                    if is_negated:
                        pos_score += 0.5 * intensity  # partial flip (negated negative = weakly positive)
                    else:
                        neg_score += 1.0 * intensity

            total = pos_score + neg_score
            item_score = round((pos_score - neg_score) / total, 3) if total > 0 else 0.0
            label = "Positive" if item_score > 0.10 else ("Negative" if item_score < -0.10 else "Neutral")

            # Recency decay
            ts = item.get("providerPublishTime") or item.get("content", {}).get("pubDate")
            pub_date_str = ""
            recency_weight = 1.0
            if ts:
                try:
                    age_days = (now_ts - float(ts)) / 86400
                    recency_weight = 1.0 if age_days <= 7 else (0.8 if age_days <= 14 else 0.6)
                    pub_date_str = datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d")
                except (TypeError, ValueError):
                    pass

            # Publisher boost
            publisher = (item.get("publisher") or "").lower()
            pub_weight = 1.3 if any(p in publisher for p in TRUSTED_PUBLISHERS) else 1.0

            total_weight = recency_weight * pub_weight

            scored_items.append({
                "title":          title,
                "publisher":      item.get("publisher", ""),
                "sentiment":      label,
                "score":          item_score,
                "weighted_score": round(item_score * total_weight, 3),
                "weight":         round(total_weight, 2),
                "published":      pub_date_str,
                "url":            item.get("link", "") or item.get("clickThroughUrl", {}).get("url", ""),
            })

        # Weighted aggregate
        total_w  = sum(i["weight"] for i in scored_items)
        agg_score = round(
            sum(i["score"] * i["weight"] for i in scored_items) / total_w, 3
        ) if total_w > 0 else 0.0
        overall = "Positive" if agg_score > 0.10 else ("Negative" if agg_score < -0.10 else "Neutral")

        pos_count = sum(1 for i in scored_items if i["sentiment"] == "Positive")
        neg_count = sum(1 for i in scored_items if i["sentiment"] == "Negative")
        neu_count = len(scored_items) - pos_count - neg_count

        return {
            "status":              "success",
            "symbol":              symbol.upper(),
            "overall_sentiment":   overall,
            "aggregate_score":     agg_score,
            "positive_headlines":  pos_count,
            "negative_headlines":  neg_count,
            "neutral_headlines":   neu_count,
            "news_items":          scored_items,
            "note": (
                "Sentiment is keyword-based NLP with negation handling, recency decay, "
                "and publisher reliability weighting. Indicative only."
            ),
        }
    except Exception as exc:
        return {"status": "error", "symbol": symbol.upper(), "message": str(exc)}


# ── Tool: compare_stocks ──────────────────────────────────────────────────────────

def compare_stocks(symbols: List[str]) -> Dict[str, Any]:
    """
    Side-by-side comparison of key metrics for a list of stocks.

    Args:
        symbols: 2–10 ticker symbols.

    Returns a comparison table with price, P/E, market cap, volume, 52w change, sector.
    """
    if not symbols or len(symbols) < 2:
        return {"status": "error", "message": "Provide at least two symbols to compare."}

    try:
        yf = _yf()
        comparison = []
        for sym in symbols[:10]:
            info = yf.Ticker(sym.upper()).info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            w52_high = info.get("fiftyTwoWeekHigh")
            w52_low  = info.get("fiftyTwoWeekLow")
            w52_chg  = None
            if price and w52_low and w52_high and w52_low > 0:
                w52_chg = round((price - w52_low) / (w52_high - w52_low) * 100, 1)  # position in 52w range

            comparison.append({
                "symbol":        sym.upper(),
                "name":          info.get("shortName", sym),
                "price":         _safe_float(price),
                "currency":      info.get("currency", "USD"),
                "pe_ratio":      _safe_float(info.get("trailingPE")),
                "market_cap":    info.get("marketCap"),
                "volume":        info.get("volume"),
                "52w_high":      _safe_float(w52_high),
                "52w_low":       _safe_float(w52_low),
                "52w_range_pct": w52_chg,
                "sector":        info.get("sector", ""),
                "dividend_yield":_safe_float(info.get("dividendYield", 0), 4),
            })
        return {"status": "success", "symbols": [s.upper() for s in symbols], "comparison": comparison}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Tool: market_overview ────────────────────────────────────────────────────────

def market_overview(indices: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Broad market health snapshot using major ETFs/indices as proxies.

    Args:
        indices: Ticker list (default: ["SPY","QQQ","DIA","IWM","VIX"]).

    Returns current price, day change, YTD performance, and a market mood label.
    """
    if not indices:
        indices = ["SPY", "QQQ", "DIA", "IWM", "^VIX"]

    try:
        yf = _yf()
        overview = []
        vix_level = None
        for sym in indices:
            t   = yf.Ticker(sym)
            info = t.info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            prev  = info.get("regularMarketPreviousClose") or info.get("previousClose", price)
            chg_pct = round((price - prev) / prev * 100, 2) if price and prev and prev != 0 else None

            # YTD
            hist = t.history(period="ytd")
            ytd_chg = None
            if not hist.empty:
                ytd_start = float(hist["Close"].iloc[0])
                ytd_chg = round((float(hist["Close"].iloc[-1]) / ytd_start - 1) * 100, 2)

            entry = {
                "symbol":      sym,
                "price":       _safe_float(price),
                "day_change_pct": chg_pct,
                "ytd_change_pct": ytd_chg,
            }
            if sym in ("^VIX", "VIX"):
                vix_level = price
                entry["label"] = "Volatility Index"
            overview.append(entry)

        # Market mood
        spy_entry = next((e for e in overview if "SPY" in e["symbol"]), None)
        spy_chg = (spy_entry or {}).get("day_change_pct", 0) or 0

        mood = (
            "Strongly Bullish" if spy_chg > 1.5 else
            "Bullish"          if spy_chg > 0.3 else
            "Neutral"          if spy_chg > -0.3 else
            "Bearish"          if spy_chg > -1.5 else
            "Strongly Bearish"
        )
        if vix_level and vix_level > 30:
            mood += " (High Volatility ⚠️)"

        return {
            "status":  "success",
            "overview": overview,
            "market_mood": mood,
            "note":    "SPY=S&P500, QQQ=Nasdaq, DIA=Dow Jones, IWM=Russell2000, VIX=Volatility",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Tool: generate_full_report ────────────────────────────────────────────────


def generate_full_report(
    symbol: str,
    output_dir: str = "data",
    send_to_email: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Generate a comprehensive PDF analysis report for a stock.

    Pipeline (all math first, LLM last)
    ------------------------------------
    Step 1 — get_quote(symbol)
    Step 2 — technical_analysis(symbol)
    Step 3 — risk_score(symbol)
    Step 4 — pattern_detection(symbol)
    Step 5 — fundamental_analysis(symbol)  [Warren Buffett metrics]
    Step 6 — sentiment_analysis(symbol)    [enhanced keyword NLP]
    Step 7 — ONE LLM call to produce a plain-language narrative
              (if llm_client is provided; otherwise narrative is blank)
    Step 8 — build PDF via report_generator.build_report()
    Step 9 — optionally: gmail_service.send_email_with_attachment()

    The LLM is given ONLY pre-computed numbers and STRICTLY instructed:
      • NO buy/sell recommendations
      • NO price targets
      • NO investment advice
    This ensures SEBI compliance and factual accuracy.

    Args:
        symbol:        Ticker symbol (e.g. "AAPL", "RELIANCE.NS").
        output_dir:    Directory in which to save the PDF (created if absent).
        send_to_email: If set, email the PDF to this address using the Gmail agent.
        llm_client:    Optional callable(prompt: str) -> str for narrative generation.
                       If None, an empty narrative is used.

    Returns:
        {
          "status":       "success" | "error",
          "symbol":       str,
          "pdf_path":     str,          # absolute path to saved PDF
          "generated_at": str,          # ISO timestamp
          "emailed_to":   str | None,
          "sections":     list[str],    # sections included in report
          "errors":       list[str],    # non-fatal data-fetch warnings
        }
    """
    from src.stock_market.fundamental_service import fundamental_analysis

    try:
        from src.stock_market.report_generator import build_report
    except ImportError:
        return {
            "status": "error",
            "symbol": symbol.upper(),
            "message": "reportlab is required. Run: pip install reportlab",
        }

    errors = []
    sections_included = []
    generated_at = datetime.utcnow().isoformat() + "Z"

    # ── Step 1–6: Run all analyses (pure math, no LLM) ─────────────────────────
    logger.info("[generate_full_report] Fetching quote for %s", symbol)
    quote_data = get_quote(symbol)
    if quote_data.get("status") == "success":
        sections_included.append("market_snapshot")
    else:
        errors.append(f"quote: {quote_data.get('message', 'unknown error')}")
        quote_data = {}

    logger.info("[generate_full_report] Running technical analysis for %s", symbol)
    tech_data = technical_analysis(symbol)
    if tech_data.get("status") == "success":
        sections_included.append("technical_analysis")
    else:
        errors.append(f"technical: {tech_data.get('message', 'unknown error')}")
        tech_data = {}

    logger.info("[generate_full_report] Running risk score for %s", symbol)
    risk_data = risk_score(symbol)
    if risk_data.get("status") == "success":
        sections_included.append("risk_assessment")
    else:
        errors.append(f"risk: {risk_data.get('message', 'unknown error')}")
        risk_data = {}

    logger.info("[generate_full_report] Running pattern detection for %s", symbol)
    pattern_data = pattern_detection(symbol)
    if pattern_data.get("status") == "success":
        sections_included.append("pattern_detection")
    else:
        errors.append(f"patterns: {pattern_data.get('message', 'unknown error')}")
        pattern_data = {}

    logger.info("[generate_full_report] Running fundamental analysis for %s", symbol)
    fund_data = fundamental_analysis(symbol)
    if fund_data.get("status") == "success":
        sections_included.append("fundamental_analysis")
    else:
        errors.append(f"fundamentals: {fund_data.get('message', 'unknown error')}")
        fund_data = {}

    logger.info("[generate_full_report] Running sentiment analysis for %s", symbol)
    sentiment_data = sentiment_analysis(symbol)
    if sentiment_data.get("status") == "success":
        sections_included.append("news_sentiment")
    else:
        errors.append(f"sentiment: {sentiment_data.get('message', 'unknown error')}")
        sentiment_data = {}

    # ── Step 7: ONE LLM call for plain-language narrative ──────────────────────
    narrative = ""
    if llm_client is not None:
        try:
            logger.info("[generate_full_report] Requesting LLM narrative for %s", symbol)
            narrative = _build_narrative(
                symbol, quote_data, fund_data, tech_data, risk_data, pattern_data, sentiment_data, llm_client
            )
        except Exception as exc:
            errors.append(f"narrative_llm: {exc}")
            narrative = ""

    # ── Step 8: Build PDF ───────────────────────────────────────────────────────
    logger.info("[generate_full_report] Building PDF for %s", symbol)
    pdf_path = build_report(
        symbol       = symbol,
        quote        = quote_data,
        fundamentals = fund_data,
        technical    = tech_data,
        risk         = risk_data,
        patterns     = pattern_data,
        sentiment    = sentiment_data,
        narrative    = narrative,
        output_dir   = output_dir,
    )
    sections_included.append("executive_summary")

    # ── Step 9: Optional email ─────────────────────────────────────────────────
    emailed_to = None
    if send_to_email:
        try:
            from src.email.gmail_service import GmailService
            gs = GmailService()
            subject = f"OctaMind Stock Analysis: {symbol.upper()} — {datetime.utcnow().strftime('%d %b %Y')}"
            body = (
                f"Please find attached the OctaMind stock analysis report for {symbol.upper()}.\n\n"
                f"DISCLAIMER: This report is for informational purposes only. It does not constitute "
                f"financial advice or a recommendation to buy, sell, or hold any security. "
                f"Please consult a SEBI-registered investment advisor before making any investment decision.\n\n"
                f"Generated at: {generated_at}"
            )
            gs.send_email_with_attachment(
                to=send_to_email,
                subject=subject,
                body=body,
                attachment_path=pdf_path,
            )
            emailed_to = send_to_email
            logger.info("[generate_full_report] Report emailed to %s", send_to_email)
        except Exception as exc:
            errors.append(f"email: {exc}")

    return {
        "status":       "success",
        "symbol":       symbol.upper(),
        "pdf_path":     pdf_path,
        "generated_at": generated_at,
        "emailed_to":   emailed_to,
        "sections":     sections_included,
        "errors":       errors,
    }


def _build_narrative(
    symbol: str,
    quote:       Dict,
    fundamentals: Dict,
    technical:   Dict,
    risk:        Dict,
    patterns:    Dict,
    sentiment:   Dict,
    llm_client,
) -> str:
    """
    Build a plain-language summary by calling the LLM exactly once.

    The prompt includes ONLY the pre-computed numbers.
    The LLM is STRICTLY instructed NOT to recommend buying/selling
    or provide price targets (SEBI compliance).

    Args:
        llm_client: callable(prompt: str) -> str

    Returns:
        Multi-paragraph narrative string.
    """
    price     = quote.get("price", "N/A")
    currency  = quote.get("currency", "")
    q_score   = fundamentals.get("quality_score", "N/A")
    q_label   = fundamentals.get("quality_label", "")
    moat      = fundamentals.get("moat_label", "N/A")
    roe       = fundamentals.get("roe_pct", "N/A")
    op_margin = fundamentals.get("operating_margin_pct", "N/A")
    pe        = fundamentals.get("pe_ratio", "N/A")
    max_dd    = risk.get("max_drawdown_pct", "N/A")
    sharpe    = risk.get("sharpe_ratio", "N/A")
    sortino   = risk.get("sortino_ratio", "N/A")
    risk_lvl  = risk.get("risk_level", "N/A")
    rsi_val   = (technical.get("rsi") or {}).get("value", "N/A")
    rsi_sig   = (technical.get("rsi") or {}).get("signal", "N/A")
    trend     = patterns.get("trend", "N/A")
    overall_sent = sentiment.get("overall_sentiment", "N/A")
    agg_sent     = sentiment.get("aggregate_score", "N/A")

    prompt = f"""You are an objective financial data analyst. Write a 3–4 paragraph plain-language 
summary of the following pre-computed analysis for {symbol.upper()}.

IMPORTANT RULES — YOU MUST FOLLOW THESE WITHOUT EXCEPTION:
1. Do NOT recommend buying, selling, or holding any stock.
2. Do NOT give price targets or earnings forecasts.
3. Do NOT provide investment advice of any kind.
4. State only what the numbers show. Use hedged language ("the data suggests", "historically...").
5. End with a clear disclaimer that this is informational only.

COMPUTED DATA SUMMARY:
- Current Price       : {price} {currency}
- Quality Score       : {q_score}/10  ({q_label})
- Economic Moat       : {moat}
- ROE                 : {roe}%
- Operating Margin    : {op_margin}%
- P/E Ratio           : {pe}
- Risk Level          : {risk_lvl}
- Max Drawdown (1Y)   : {max_dd}%
- Sharpe Ratio        : {sharpe}
- Sortino Ratio       : {sortino}
- RSI (14)            : {rsi_val}  [{rsi_sig}]
- Price Trend         : {trend}
- News Sentiment      : {overall_sent} (score {agg_sent})

Write the summary now. Do not include section headers like "Executive Summary".
Plain prose only. Be factual and concise."""

    try:
        response = llm_client(prompt)
        return str(response).strip()
    except Exception:
        return ""

