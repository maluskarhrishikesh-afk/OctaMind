"""
Stock Market Analysis Service — Octa Bot

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

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("stock_service")


def _log_analysis_step(step: str, symbol: str, status: str) -> None:
    """Emit a structured INFO log line for each analysis pipeline step."""
    try:
        from src.agent.logging.log_manager import bind_request, new_request_id
        bind_request(new_request_id())
    except Exception:
        pass
    logger.info("[stock_analysis] step=%s symbol=%s status=%s", step, symbol, status)


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


def resolve_ticker(query: str) -> str:
    """
    Resolve a company name or partial name to a yfinance ticker symbol.

    - If *query* already looks like a ticker symbol (uppercase letters/digits/dots/hyphens)
      it is returned as-is.
    - Otherwise yf.Search() is used to find the best match;
      NSE (.NS) equity results are preferred so Indian company names work naturally.

    Examples::

        resolve_ticker("Intellect Design Arena")  # → "INTELLECT.NS"
        resolve_ticker("TCS")                     # → "TCS.NS"
        resolve_ticker("AAPL")                    # → "AAPL"  (unchanged)
        resolve_ticker("Eternal")                 # → "ETERNAL.NS" (Zomato rename)
    """
    query = query.strip()
    if not query:
        return query
    # Already looks like a ticker: all-uppercase, optional exchange suffix (.NS, .BO, .L, ^VIX …)
    if re.match(r'^[A-Z0-9\.\-\^]{1,25}$', query):
        return query
    try:
        results = _yf().Search(query, max_results=10)
        quotes  = results.quotes if hasattr(results, 'quotes') else []
        if not quotes:
            logger.warning("[resolve_ticker] No results for '%s' — using as-is", query)
            return query.upper()
        # Prefer NSE equity (most Indian stocks are on NSE)
        nse = [
            q for q in quotes
            if q.get("exchange") in ("NSI", "NSE") and q.get("quoteType") == "EQUITY"
        ]
        if nse:
            symbol = nse[0]["symbol"]
            logger.info("[resolve_ticker] '%s' → %s (NSE)", query, symbol)
            return symbol
        # Fallback: first equity result on any exchange
        equity = [q for q in quotes if q.get("quoteType") == "EQUITY"]
        if equity:
            symbol = equity[0]["symbol"]
            logger.info("[resolve_ticker] '%s' → %s", query, symbol)
            return symbol
        # Last resort: first result regardless of type
        symbol = quotes[0]["symbol"]
        logger.info("[resolve_ticker] '%s' → %s (first result)", query, symbol)
        return symbol
    except Exception as exc:
        logger.warning("[resolve_ticker] Search failed for '%s': %s — using as-is", query, exc)
        return query.upper()


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

        rsi_signal = (
            "overbought"      if rsi_val > 70 else
            "near overbought" if rsi_val >= 65 else
            "oversold"        if rsi_val < 30 else
            "near oversold"   if rsi_val <= 35 else
            "neutral"
        )
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
                          Uses sample standard deviation (N−1 denominator).
                          Measures price dispersion; higher = more uncertainty.

    Beta vs SPY         = Cov_sample(stock, SPY) / Var_sample(SPY)
                          Sample covariance/variance (N−1). >1 → amplifies market;
                          <1 → more stable than market.

    Beta 60d (Rolling)  = Same formula over the most recent 60 trading days.
                          Shows how beta has shifted from the 1-year baseline.

    Beta Downside       = Beta computed only on days when SPY return was negative.
                          Captures tail-risk sensitivity; favoured by institutions.

    VaR 95% Parametric  = -(μ − 1.645 × σ_daily) × 100   (normality assumed)
    VaR 95% Historical  = −5th percentile of actual daily returns × 100
                          No normality assumption; more robust in fat-tail regimes.

    Sharpe Ratio        = (mean_daily_return − rf_daily) / daily_σ × √252
                          Uses arithmetic mean daily return annualised — NOT CAGR.
                          Risk-free rate: 4.5% p.a.

    Max Drawdown        = (peak_price − trough_price) / peak_price × 100
    Sortino Ratio       = excess_annual / downside_deviation_annual
    Calmar Ratio        = annualised_return / |max_drawdown|

    Composite Risk Score (1–10)
                        = weighted(vol_score×40% + beta_score×30% + var_score×30%)
                          Heuristic linear scaling. See docs for expert commentary.

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
        variance = sum((r - mean_ret) ** 2 for r in returns) / (n - 1)  # sample variance
        daily_vol = math.sqrt(variance)
        annual_vol = round(daily_vol * math.sqrt(252) * 100, 2)

        # Annualised return
        total_return = (closes[-1] / closes[0] - 1)
        annual_return = round(((1 + total_return) ** (252 / len(closes)) - 1) * 100, 2)

        # VaR 95% — parametric (assumes normal distribution)
        z95 = 1.645
        var_95 = round(-(mean_ret - z95 * daily_vol) * 100, 3)

        # VaR 95% — historical (5th percentile of actual returns; no normality assumption)
        sorted_rets = sorted(returns)
        hist_idx = max(0, int(len(sorted_rets) * 0.05) - 1)
        var_95_hist = round(-sorted_rets[hist_idx] * 100, 3)

        # Beta vs benchmark — use NIFTY 50 for Indian stocks, SPY for global
        _sym_upper = symbol.upper()
        _is_indian = _sym_upper.endswith(".NS") or _sym_upper.endswith(".BO")
        _benchmark_ticker = "^NSEI" if _is_indian else "SPY"
        _benchmark_label  = "NIFTY 50" if _is_indian else "SPY"
        spy_hist = yf.Ticker(_benchmark_ticker).history(period=period)
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
            # Sample covariance/variance (N-1) — finance convention
            cov = sum((a - m1) * (b - m2) for a, b in zip(r1, r2)) / (len(r1) - 1)
            spy_var = sum((b - m2) ** 2 for b in r2) / (len(r2) - 1)
            beta = round(cov / spy_var, 3) if spy_var != 0 else None

            # ── Rolling Beta 60d ──────────────────────────────────────────────
            roll_len = min(60, min_len)
            if roll_len > 10:
                r1_60 = r1[-roll_len:]
                r2_60 = r2[-roll_len:]
                m1_60 = sum(r1_60) / roll_len
                m2_60 = sum(r2_60) / roll_len
                cov_60 = sum((a - m1_60) * (b - m2_60) for a, b in zip(r1_60, r2_60)) / (roll_len - 1)
                var_60 = sum((b - m2_60) ** 2 for b in r2_60) / (roll_len - 1)
                beta_60d = round(cov_60 / var_60, 3) if var_60 != 0 else None
            else:
                beta_60d = None

            # ── Downside Beta (negative SPY days only) ────────────────────────
            neg_pairs = [(a, b) for a, b in zip(r1, r2) if b < 0]
            beta_downside = None
            if len(neg_pairs) > 10:
                nd_n = len(neg_pairs)
                nd_r1 = [p[0] for p in neg_pairs]
                nd_r2 = [p[1] for p in neg_pairs]
                nd_m1 = sum(nd_r1) / nd_n
                nd_m2 = sum(nd_r2) / nd_n
                nd_cov = sum((a - nd_m1) * (b - nd_m2) for a, b in zip(nd_r1, nd_r2)) / (nd_n - 1)
                nd_var = sum((b - nd_m2) ** 2 for b in nd_r2) / (nd_n - 1)
                beta_downside = round(nd_cov / nd_var, 3) if nd_var != 0 else None
        else:
            beta_60d = None
            beta_downside = None

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
            "Very Low"      if composite < 2.5 else
            "Low"           if composite < 4   else
            "Moderate"      if composite < 5.5 else
            "Moderate-High" if composite < 7   else
            "High"          if composite < 8.5 else
            "Very High"
        )

        return {
            "status":                "success",
            "symbol":                symbol.upper(),
            "benchmark":             _benchmark_label,
            "annual_volatility_pct": annual_vol,
            "annual_return_pct":     annual_return,
            "beta":                  beta,
            "beta_60d":              beta_60d,
            "beta_downside":         beta_downside,
            "var_95_daily_pct":      var_95,
            "var_95_hist_daily_pct": var_95_hist,
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
    Detect support/resistance, trend direction, candlestick patterns,
    pivot points, 52-week levels, VWAP, and Volume Profile (POC/Value Area).

    Calculations
    ------------
    Classic S&R     : rolling min(lows[-20]), max(highs[-20])

    Pivot Points    : Classic daily pivot from previous session OHLC
        P  = (H + L + C) / 3
        R1 = 2P − L,  R2 = P + (H − L),  R3 = H + 2(P − L)
        S1 = 2P − H,  S2 = P − (H − L),  S3 = L − 2(H − P)

    52-Week H/L     : from yfinance info (fiftyTwoWeekHigh/Low)

    VWAP (5-day)    : Σ(typical_price × volume) / Σ(volume)
                      typical_price = (H + L + C) / 3 per hourly bar
                      Uses 5-day hourly bars; acts as a rolling multi-day VWAP
                      (not a single-session reset VWAP — noted for expert review)

    Volume Profile  : Divides price range into 20 equal buckets.
                      Sums volume traded in each bucket over the period.
                      POC  = price level with highest volume concentration.
                      Value Area = price range containing 70% of total volume
                                   (expanded outward from POC — standard VA method).

    Args:
        symbol: Ticker symbol.
        period: Historical period for S&R + patterns (default "3mo").

    Returns detected patterns, support, resistance, pivot points,
    VWAP, volume profile, and 52-week levels.
    """
    import math as _math

    try:
        t = _ticker(symbol)
        hist = t.history(period=period)
        if hist.empty or len(hist) < 20:
            return {"status": "error", "symbol": symbol.upper(), "message": "Insufficient data."}

        closes  = list(hist["Close"].dropna())
        highs   = list(hist["High"].dropna())
        lows    = list(hist["Low"].dropna())
        opens   = list(hist["Open"].dropna())
        volumes = list(hist["Volume"].dropna()) if "Volume" in hist.columns else []

        # ── Classic S&R (rolling 20-period min/max) ────────────────────────────
        lookback   = min(20, len(closes))
        support    = round(min(lows[-lookback:]),  4)
        resistance = round(max(highs[-lookback:]), 4)
        latest     = closes[-1]

        # ── Pivot Points (Classic daily formula) ───────────────────────────────
        # Computed from the second-to-last bar ("previous session")
        pivot_points: Dict[str, Any] = {}
        if len(highs) >= 2:
            ph = highs[-2]
            pl = lows[-2]
            pc = closes[-2]
            P  = (ph + pl + pc) / 3
            pivot_points = {
                "pivot": round(P,                    4),
                "r1":    round(2 * P - pl,            4),
                "r2":    round(P + (ph - pl),         4),
                "r3":    round(ph + 2 * (P - pl),     4),
                "s1":    round(2 * P - ph,            4),
                "s2":    round(P - (ph - pl),         4),
                "s3":    round(pl - 2 * (ph - P),     4),
            }

        # ── 52-Week High / Low ─────────────────────────────────────────────────
        w52_high: Optional[float] = None
        w52_low:  Optional[float] = None
        try:
            info     = t.info
            w52_high = _safe_float(info.get("fiftyTwoWeekHigh"))
            w52_low  = _safe_float(info.get("fiftyTwoWeekLow"))
        except Exception:
            pass

        # ── VWAP — 5-day hourly rolling ────────────────────────────────────────
        # typical_price = (H + L + C) / 3
        # VWAP = Σ(TP × Volume) / Σ(Volume)
        # NOTE: This is a 5-day rolling VWAP, NOT a single-day VWAP that resets
        # at market open. Suitable for a multi-day trend reference.
        vwap_5d: Optional[float] = None
        try:
            intra = t.history(period="5d", interval="1h")
            if not intra.empty and "Volume" in intra.columns:
                ic = list(intra["Close"].dropna())
                ih = list(intra["High"].dropna())
                il = list(intra["Low"].dropna())
                iv = list(intra["Volume"].dropna())
                n  = min(len(ic), len(ih), len(il), len(iv))
                if n > 0:
                    total_vol = sum(iv[:n])
                    if total_vol > 0:
                        vwap_5d = round(
                            sum(((ih[i] + il[i] + ic[i]) / 3) * iv[i] for i in range(n)) / total_vol,
                            4,
                        )
        except Exception:
            pass

        # ── Volume Profile (POC + Value Area) ─────────────────────────────────
        # Bucket the price range into 20 equal-width bins.
        # Sum volume per bucket. POC = max-volume bucket.
        # Value Area = 70% of total volume centred on POC (standard VA algo).
        poc:              Optional[float] = None
        value_area_high:  Optional[float] = None
        value_area_low:   Optional[float] = None
        if volumes and len(volumes) >= len(closes):
            vols    = volumes[:len(closes)]
            p_min   = min(lows)
            p_max   = max(highs)
            n_buckets = 20
            bucket_sz = (p_max - p_min) / n_buckets if p_max != p_min else 1.0

            vol_buckets = [0.0] * n_buckets
            for i, cp in enumerate(closes):
                idx = min(int((cp - p_min) / bucket_sz), n_buckets - 1)
                vol_buckets[idx] += vols[i]

            poc_idx = vol_buckets.index(max(vol_buckets))
            poc     = round(p_min + (poc_idx + 0.5) * bucket_sz, 4)

            total_v  = sum(vol_buckets)
            target_v = total_v * 0.70
            va_vol   = vol_buckets[poc_idx]
            lo_idx, hi_idx = poc_idx, poc_idx

            while va_vol < target_v and (lo_idx > 0 or hi_idx < n_buckets - 1):
                up_vol   = vol_buckets[hi_idx + 1] if hi_idx < n_buckets - 1 else 0.0
                down_vol = vol_buckets[lo_idx - 1] if lo_idx > 0         else 0.0
                if up_vol >= down_vol and hi_idx < n_buckets - 1:
                    hi_idx += 1
                    va_vol += vol_buckets[hi_idx]
                elif lo_idx > 0:
                    lo_idx -= 1
                    va_vol += vol_buckets[lo_idx]
                else:
                    break  # no further expansion possible

            value_area_high = round(p_min + (hi_idx + 1) * bucket_sz, 4)
            value_area_low  = round(p_min +  lo_idx      * bucket_sz, 4)

        # ── Trend (SMA-20 slope) ───────────────────────────────────────────────
        sma20_now  = sum(closes[-20:]) / 20
        sma20_prev = sum(closes[-21:-1]) / 20 if len(closes) >= 21 else sma20_now
        if   sma20_now > sma20_prev * 1.001:
            trend = "uptrend"
        elif sma20_now < sma20_prev * 0.999:
            trend = "downtrend"
        else:
            trend = "sideways"

        # ── Candlestick Patterns ───────────────────────────────────────────────
        # Align all series to the shortest — yfinance may return different NaN patterns
        _n = min(len(closes), len(opens), len(highs), len(lows))
        closes = closes[-_n:]
        opens  = opens[-_n:]
        highs  = highs[-_n:]
        lows   = lows[-_n:]

        patterns: List[str] = []
        if _n >= 2:
            o, c, h, l = opens[-1], closes[-1], highs[-1], lows[-1]
            body   = abs(c - o)
            range_ = h - l if h != l else 0.0001

            if body / range_ < 0.1:
                patterns.append("Doji — indecision candle")

            lower_shadow = min(o, c) - l
            upper_shadow = h - max(o, c)
            if lower_shadow > 2 * body and upper_shadow < body and trend == "downtrend":
                patterns.append("Hammer — potential bullish reversal")
            if upper_shadow > 2 * body and lower_shadow < body and trend == "uptrend":
                patterns.append("Shooting Star — potential bearish reversal")

            o_prev, c_prev = opens[-2], closes[-2]
            if c_prev < o_prev and c > o and c > o_prev and o < c_prev:
                patterns.append("Bullish Engulfing — momentum shift")
            if c_prev > o_prev and c < o and c < o_prev and o > c_prev:
                patterns.append("Bearish Engulfing — momentum shift")

        # ── Price position context ─────────────────────────────────────────────
        tags = []
        if resistance and latest > resistance * 0.97:
            tags.append("near 20d resistance")
        elif support and latest < support * 1.03:
            tags.append("near 20d support")
        if pivot_points.get("r1") and latest >= pivot_points["r1"]:
            tags.append("above pivot R1")
        elif pivot_points.get("s1") and latest <= pivot_points["s1"]:
            tags.append("below pivot S1")
        if vwap_5d:
            tags.append("above VWAP" if latest >= vwap_5d else "below VWAP")
        if w52_high and abs(latest - w52_high) / w52_high < 0.03:
            tags.append("near 52W high")
        if w52_low and abs(latest - w52_low) / w52_low < 0.03:
            tags.append("near 52W low")
        price_position = ", ".join(tags) if tags else "mid-range"

        return {
            "status":          "success",
            "symbol":          symbol.upper(),
            "trend":           trend,
            # Classic rolling S&R
            "support":         support,
            "resistance":      resistance,
            # Classic pivot levels
            "pivot_points":    pivot_points,
            # 52-week extremes
            "week_52_high":    w52_high,
            "week_52_low":     w52_low,
            # VWAP
            "vwap_5d":         vwap_5d,
            # Volume Profile
            "volume_poc":      poc,
            "value_area_high": value_area_high,
            "value_area_low":  value_area_low,
            # Close + position summary
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

def _keyword_score_headline(title: str, pos_words: set, neg_words: set,
                             negation_words: set, intensifier_words: set) -> tuple:
    """
    Score a single headline using keyword NLP.
    Returns (item_score, label) where item_score ∈ [-1, +1].
    """
    raw_words = re.findall(r"\b\w+\b", title.lower())
    pos_score = 0.0
    neg_score = 0.0
    for idx, word in enumerate(raw_words):
        context        = raw_words[max(0, idx - 3):idx]
        is_negated     = any(w in negation_words   for w in context)
        is_intensified = any(w in intensifier_words for w in raw_words[max(0, idx - 2):idx])
        intensity      = 1.5 if is_intensified else 1.0
        if word in pos_words:
            if is_negated:
                neg_score += 1.0 * intensity
            else:
                pos_score += 1.0 * intensity
        elif word in neg_words:
            if is_negated:
                pos_score += 0.5 * intensity
            else:
                neg_score += 1.0 * intensity
    total = pos_score + neg_score
    score = round((pos_score - neg_score) / total, 3) if total > 0 else 0.0
    label = "Positive" if score > 0.10 else ("Negative" if score < -0.10 else "Neutral")
    return score, label


def _llm_classify_headlines(titles: List[str]) -> Optional[List[Dict]]:
    """
    Classify a list of news headlines using the configured LLM in one batch call.

    Sends all titles in a single prompt asking for JSON output:
    [{"index": 0, "label": "Positive|Negative|Neutral", "confidence": 0.0-1.0}, ...]

    Returns the list on success, None on any failure (caller falls back to keywords).
    """
    try:
        from src.agent.llm.llm_parser import get_llm_client
        llm = get_llm_client()

        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
        prompt = (
            "You are a financial news sentiment classifier. "
            "Classify each headline as Positive, Negative, or Neutral from the perspective of "
            "the company being mentioned. Consider the full headline including nuance and context.\n\n"
            "Headlines:\n"
            f"{numbered}\n\n"
            "Respond ONLY with a JSON array, one object per headline:\n"
            '[{"index": 0, "label": "Positive", "confidence": 0.85}, ...]\n'
            "Labels must be exactly: Positive, Negative, or Neutral. No other text."
        )
        resp = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON array. No markdown, no explanation."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
            max_tokens=600,
            timeout=20,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
        parsed = json.loads(raw)
        if isinstance(parsed, list) and len(parsed) == len(titles):
            return parsed
        return None
    except Exception as exc:
        logger.warning("[sentiment_analysis] LLM classification failed: %s — using keyword fallback", exc)
        return None


def sentiment_analysis(symbol: str) -> Dict[str, Any]:
    """
    Analyse recent news headlines for a stock.

    Sentiment Engine (two-tier)
    ---------------------------
    PRIMARY — LLM classification (OpenAI/configured model):
      All headlines are sent in ONE batch call to the LLM.
      The model classifies each headline as Positive / Negative / Neutral
      taking context, nuance, and sarcasm into account.
      Returns confidence per headline.

    FALLBACK — Keyword NLP (when LLM unavailable or errors):
      Rule-based scoring with:
      • Negation handling (3-word look-back: "not", "no", "never", ...)
      • Intensifier weighting (1.5× for "significantly", "sharply", ...)
      Degraded but always available.

    Both tiers
    ----------
    3. Recency decay applied per item:
       age ≤ 7d → 1.0×,  ≤ 14d → 0.8×,  >14d → 0.6×
    4. Publisher reliability boost:
       Reuters/Bloomberg/WSJ/FT/CNBC/Barron's/Forbes → 1.3×
    5. Weighted aggregate = Σ(score × weight) / Σ(weight)
       > +0.10 → Positive;  < −0.10 → Negative;  else Neutral

    Args:
        symbol: Ticker symbol.

    Returns news items, sentiments, aggregate score, and which engine was used.
    """
    POSITIVE_WORDS = {
        "beat", "beats", "growth", "profit", "profits", "record", "surge", "surges",
        "soar", "soars", "gain", "gains", "bull", "bullish", "upgrade", "upgrades",
        "strong", "stronger", "robust", "positive", "innovative", "innovation",
        "launch", "launches", "expand", "expansion", "exceed", "exceeds",
        "raised", "raise", "outperform", "outperforms", "recovery", "recovers",
        "partnership", "partnerships", "dividend", "dividends", "breakthrough",
        "milestone", "optimistic", "rally", "rallies", "accelerate", "accelerates",
        "improve", "improves", "improvement", "rebound", "rebounds", "advance",
        "advances", "boost", "boosts", "excellent", "exceptional", "impressive",
        "increase", "increases", "higher", "upbeat", "buoyant",
        "overweight", "top", "outperformance", "upward", "upside",
        "winning", "win", "wins", "bonus", "benefits", "surplus",
        "ahead", "returns", "inflow", "inflows", "demand", "resurgence", "adoption", "momentum",
    }
    NEGATIVE_WORDS = {
        "miss", "misses", "loss", "losses", "decline", "declines", "fall", "falls",
        "drop", "drops", "cut", "cuts", "layoff", "layoffs", "downgrade", "downgrades",
        "weak", "weaker", "negative", "lawsuit", "lawsuits", "recall", "recalls",
        "fraud", "penalty", "penalties", "fine", "fines", "ban", "bans",
        "warning", "warnings", "risk", "risks", "concern", "concerns", "below",
        "missed", "resign", "resigns", "investigate", "investigation",
        "crisis", "debt", "default", "disappointing", "disappoint", "disappoints",
        "shrink", "shrinks", "contraction", "contractions",
        "underperform", "underperforms", "bearish", "bear",
        "downside", "downward", "underweight",
        "slump", "slumps", "plunge", "plunges", "crash", "crashes",
        "recession", "slowdown", "sluggish", "volatile", "volatility",
        "uncertainty", "uncertain", "headwind", "headwinds", "pressure", "pressures",
        "halt", "halts", "suspended", "suspension", "charges", "charge",
        "impairment", "write-off", "write-down", "shortfall",
        "outflow", "outflows", "deficit", "probe", "subpoena",
    }
    NEGATION_WORDS    = {"not", "no", "never", "without", "fails", "fail", "despite", "lack", "lacks"}
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
                "news_items": [], "sentiment_engine": "none",
            }

        batch = news[:15]
        # yfinance 1.2+ nests fields under item["content"]; support both schemas
        titles = [
            (
                item.get("title") or
                item.get("content", {}).get("title") or ""
            ).strip()
            for item in batch
        ]
        now_ts = datetime.utcnow().timestamp()

        # ── Step 1: Try LLM batch classification (one API call) ───────────────
        llm_results = _llm_classify_headlines(titles)
        sentiment_engine = "llm" if llm_results is not None else "keyword"

        # Build index → {label, confidence} from LLM results
        llm_map: Dict[int, Dict] = {}
        if llm_results:
            for r in llm_results:
                try:
                    llm_map[int(r["index"])] = {
                        "label":      r.get("label", "Neutral"),
                        "confidence": float(r.get("confidence", 0.5)),
                    }
                except (KeyError, TypeError, ValueError):
                    pass

        # ── Step 2: Keyword scores always computed (numeric signal) ───────────
        scored_items = []
        for idx, item in enumerate(batch):
            title = titles[idx]

            # Always compute keyword score for numeric value
            kw_score, kw_label = _keyword_score_headline(
                title, POSITIVE_WORDS, NEGATIVE_WORDS, NEGATION_WORDS, INTENSIFIER_WORDS
            )

            # Primary label: LLM if available, else keyword
            if idx in llm_map:
                label      = llm_map[idx]["label"]
                confidence = llm_map[idx]["confidence"]
                # For numeric score: blend LLM direction with keyword magnitude
                llm_sign   = 1.0 if label == "Positive" else (-1.0 if label == "Negative" else 0.0)
                item_score = round(llm_sign * confidence, 3)
            else:
                label      = kw_label
                confidence = None
                item_score = kw_score

            # ── Recency decay ─────────────────────────────────────────────────
            # Support both old schema (epoch int) and new yfinance 1.2+ schema (ISO string)
            ts_raw = item.get("providerPublishTime") or item.get("content", {}).get("pubDate")
            pub_date_str   = ""
            recency_weight = 1.0
            if ts_raw:
                ts_epoch = None
                try:
                    ts_epoch = float(ts_raw)           # old schema: Unix epoch int
                except (TypeError, ValueError):
                    try:                               # new schema: ISO-8601 string
                        ts_epoch = datetime.strptime(
                            str(ts_raw)[:19], "%Y-%m-%dT%H:%M:%S"
                        ).timestamp()
                    except Exception:
                        pass
                if ts_epoch is not None:
                    try:
                        age_days = (now_ts - ts_epoch) / 86400
                        recency_weight = 1.0 if age_days <= 7 else (0.8 if age_days <= 14 else 0.6)
                        pub_date_str = datetime.utcfromtimestamp(ts_epoch).strftime("%Y-%m-%d")
                    except Exception:
                        pass

            # ── Publisher reliability boost ───────────────────────────────────
            publisher = (
                item.get("publisher") or
                item.get("content", {}).get("provider", {}).get("displayName") or ""
            ).lower()
            pub_weight = 1.3 if any(p in publisher for p in TRUSTED_PUBLISHERS) else 1.0

            total_weight = recency_weight * pub_weight

            entry: Dict[str, Any] = {
                "title":          title,
                "publisher":      (
                    item.get("publisher") or
                    item.get("content", {}).get("provider", {}).get("displayName") or ""
                ),
                "sentiment":      label,
                "score":          item_score,
                "weighted_score": round(item_score * total_weight, 3),
                "weight":         round(total_weight, 2),
                "published":      pub_date_str,
                "url":            (
                    item.get("link") or
                    item.get("content", {}).get("canonicalUrl", {}).get("url") or ""
                ),
            }
            if confidence is not None:
                entry["llm_confidence"] = round(confidence, 3)
            scored_items.append(entry)

        # ── Step 3: Weighted aggregate ────────────────────────────────────────
        total_w   = sum(i["weight"] for i in scored_items)
        agg_score = round(
            sum(i["score"] * i["weight"] for i in scored_items) / total_w, 3
        ) if total_w > 0 else 0.0
        overall = "Positive" if agg_score > 0.10 else ("Negative" if agg_score < -0.10 else "Neutral")

        pos_count = sum(1 for i in scored_items if i["sentiment"] == "Positive")
        neg_count = sum(1 for i in scored_items if i["sentiment"] == "Negative")
        neu_count = len(scored_items) - pos_count - neg_count

        engine_note = (
            "Sentiment classified by LLM (context-aware, handles nuance and sarcasm); "
            "numeric score uses LLM direction × confidence. Recency decay and publisher "
            "reliability weighting applied."
        ) if sentiment_engine == "llm" else (
            "LLM unavailable — keyword NLP fallback used (negation/intensifier aware). Indicative only."
        )

        return {
            "status":              "success",
            "symbol":              symbol.upper(),
            "overall_sentiment":   overall,
            "aggregate_score":     agg_score,
            "positive_headlines":  pos_count,
            "negative_headlines":  neg_count,
            "neutral_headlines":   neu_count,
            "sentiment_engine":    sentiment_engine,
            "news_items":          scored_items,
            "note":                engine_note,
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
    # Bind a fresh correlation ID for the entire report pipeline
    try:
        from src.agent.logging.log_manager import bind_correlation, bind_request, new_correlation_id, new_request_id
        bind_correlation(new_correlation_id())
    except Exception:
        pass

    _log_analysis_step("quote", symbol, "start")
    quote_data = get_quote(symbol)
    if quote_data.get("status") == "success":
        sections_included.append("market_snapshot")
        _log_analysis_step("quote", symbol, "ok")
    else:
        errors.append(f"quote: {quote_data.get('message', 'unknown error')}")
        _log_analysis_step("quote", symbol, f"error:{quote_data.get('message', '')}")
        quote_data = {}

    _log_analysis_step("technical", symbol, "start")
    tech_data = technical_analysis(symbol)
    if tech_data.get("status") == "success":
        sections_included.append("technical_analysis")
        _log_analysis_step("technical", symbol, "ok")
    else:
        errors.append(f"technical: {tech_data.get('message', 'unknown error')}")
        _log_analysis_step("technical", symbol, f"error")
        tech_data = {}

    _log_analysis_step("risk", symbol, "start")
    risk_data = risk_score(symbol)
    if risk_data.get("status") == "success":
        sections_included.append("risk_assessment")
        _log_analysis_step("risk", symbol, "ok")
    else:
        errors.append(f"risk: {risk_data.get('message', 'unknown error')}")
        _log_analysis_step("risk", symbol, "error")
        risk_data = {}

    _log_analysis_step("patterns", symbol, "start")
    pattern_data = pattern_detection(symbol)
    if pattern_data.get("status") == "success":
        sections_included.append("pattern_detection")
        _log_analysis_step("patterns", symbol, "ok")
    else:
        errors.append(f"patterns: {pattern_data.get('message', 'unknown error')}")
        _log_analysis_step("patterns", symbol, "error")
        pattern_data = {}

    _log_analysis_step("fundamental", symbol, "start")
    fund_data = fundamental_analysis(symbol)
    if fund_data.get("status") == "success":
        sections_included.append("fundamental_analysis")
        _log_analysis_step(
            "fundamental", symbol,
            f"ok quality={fund_data.get('quality_score')} moat={fund_data.get('moat_label')} "
            f"gross_margin={fund_data.get('gross_margin_pct')} op_margin={fund_data.get('operating_margin_pct')} "
            f"rev_growth={fund_data.get('revenue_growth_yoy_pct')} earnings_growth={fund_data.get('earnings_growth_yoy_pct')} "
            f"de={fund_data.get('debt_to_equity')} pe={fund_data.get('pe_ratio')}",
        )
    else:
        errors.append(f"fundamentals: {fund_data.get('message', 'unknown error')}")
        _log_analysis_step("fundamental", symbol, "error")
        fund_data = {}

    _log_analysis_step("sentiment", symbol, "start")
    sentiment_data = sentiment_analysis(symbol)
    if sentiment_data.get("status") == "success":
        sections_included.append("news_sentiment")
        _log_analysis_step(
            "sentiment", symbol,
            f"ok overall={sentiment_data.get('overall_sentiment')} score={sentiment_data.get('aggregate_score')}",
        )
    else:
        errors.append(f"sentiment: {sentiment_data.get('message', 'unknown error')}")
        _log_analysis_step("sentiment", symbol, "error")
        sentiment_data = {}

    # ── Step 7: ONE LLM call for plain-language narrative ──────────────────────
    narrative = ""
    _log_analysis_step("narrative_llm", symbol, "start" if llm_client else "skipped")
    if llm_client is not None:
        try:
            narrative = _build_narrative(
                symbol, quote_data, fund_data, tech_data, risk_data, pattern_data, sentiment_data, llm_client
            )
            _log_analysis_step("narrative_llm", symbol, f"ok chars={len(narrative)}")
        except Exception as exc:
            errors.append(f"narrative_llm: {exc}")
            _log_analysis_step("narrative_llm", symbol, f"error:{exc}")
            narrative = ""

    # ── Step 8: Build PDF ───────────────────────────────────────────────────────
    _log_analysis_step("build_pdf", symbol, "start")
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
            from src.email.gmail_service import send_email_with_attachment as _send_with_attachment
            subject = f"Octa Bot Stock Analysis: {symbol.upper()} — {datetime.utcnow().strftime('%d %b %Y')}"
            body = (
                f"Please find attached the Octa Bot stock analysis report for {symbol.upper()}.\n\n"
                f"DISCLAIMER: This report is for informational purposes only. It does not constitute "
                f"financial advice or a recommendation to buy, sell, or hold any security. "
                f"Please consult a SEBI-registered investment advisor before making any investment decision.\n\n"
                f"Generated at: {generated_at}"
            )
            _send_with_attachment(
                to=send_to_email,
                subject=subject,
                message=body,
                attachment_path=pdf_path,
            )
            emailed_to = send_to_email
            logger.info("[generate_full_report] Report emailed to %s", send_to_email)
        except Exception as exc:
            errors.append(f"email: {exc}")

    _log_analysis_step("build_pdf", symbol, "ok")
    logger.info(
        "[generate_full_report] COMPLETE symbol=%s price=%s quality=%s/%s moat=%s "
        "risk=%s sentiment=%s sections=%d pdf=%s errors=%d",
        symbol.upper(),
        quote_data.get("price", "N/A"),
        fund_data.get("quality_score", "N/A"),
        10,
        fund_data.get("moat_label", "N/A"),
        risk_data.get("risk_level", "N/A"),
        sentiment_data.get("overall_sentiment", "N/A"),
        len(sections_included),
        pdf_path,
        len(errors),
    )

    # ── Optional: capture summary in agent memory ──────────────────────────────
    try:
        from src.agent.memory.agent_memory import get_agent_memory
        import os
        agent_id = os.getenv("AGENT_ID", "_collective_memory_")
        mem = get_agent_memory(agent_id)
        mem.add_interaction(
            command=f"stock analysis {symbol.upper()}",
            action="generate_full_report",
            result={
                "status": "success",
                "symbol": symbol.upper(),
                "price": quote_data.get("price"),
                "quality_score": fund_data.get("quality_score"),
                "moat_label": fund_data.get("moat_label"),
                "risk_level": risk_data.get("risk_level"),
                "sentiment": sentiment_data.get("overall_sentiment"),
                "gross_margin_pct": fund_data.get("gross_margin_pct"),
                "revenue_growth_pct": fund_data.get("revenue_growth_yoy_pct"),
                "earnings_growth_pct": fund_data.get("earnings_growth_yoy_pct"),
                "pdf_path": pdf_path,
            },
            importance="High",
        )
    except Exception as _mem_err:
        logger.debug("[generate_full_report] Memory capture skipped: %s", _mem_err)

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

