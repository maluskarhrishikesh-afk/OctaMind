"""
Fundamental Analysis — Warren Buffett Quality Framework
========================================================

All metrics are computed from publicly available financial data via yfinance.
No buy/sell recommendations. No price targets. Informational analysis only.

Philosophy (adapted from Benjamin Graham / Warren Buffett):
  1. Buy wonderful companies — predictable earnings, wide moat, low debt.
  2. Understand what you own — transparent, comprehensible business.
  3. Margin of safety — value the business independently of market price.

What this module computes (pure math, no LLM):
  - Quality metrics: ROE, ROA, margins, FCF yield, earnings growth
  - Safety metrics: debt levels, current ratio, interest coverage
  - Value metrics: P/E, P/B, PEG ratio
  - Moat score (0–10): wide/narrow/none
  - Buffett quality score (0–10): overall company quality rating

DISCLAIMER: This analysis is informational only. It is NOT financial advice.
            Past performance does not guarantee future results.
            Not compliant with jurisdiction-specific regulations without
            independent professional review.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

logger = logging.getLogger("fundamental_service")


# ── yfinance guard ─────────────────────────────────────────────────────────────

def _safe_float(val, decimals: int = 4) -> Optional[float]:
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, decimals)
    except (TypeError, ValueError):
        return None


def _pct(val, decimals: int = 2) -> Optional[float]:
    """Convert ratio to percentage, rounded."""
    raw = _safe_float(val)
    if raw is None:
        return None
    return round(raw * 100, decimals)


def _ticker(symbol: str):
    try:
        import yfinance as yf
        return yf.Ticker(symbol.upper().strip())
    except ImportError:
        raise ImportError("yfinance is not installed. Run: pip install yfinance")


# ── Moat scoring rubric ────────────────────────────────────────────────────────
# Each signal contributes 0, 1, or 2 points.  Maximum = 10 points.
#
# Moat indicators from Buffett/Morningstar framework:
#   1. Return on Equity (ROE) — efficiency of capital deployment
#   2. Operating Margin — pricing power / cost advantage
#   3. FCF Yield — real cash generation vs market price
#   4. Debt/Equity — financial safety, ability to survive downturns
#   5. Earnings Growth — consistency and direction of earnings

def _moat_score(
    roe: Optional[float],          # percent
    operating_margin: Optional[float],  # percent
    fcf_yield: Optional[float],    # percent
    debt_to_equity: Optional[float],
    earnings_growth: Optional[float],  # percent, YoY
) -> Dict[str, Any]:
    """
    Compute a 0–10 moat score from five quality signals.

    Each signal contributes 0.0–2.0 points on a gradient scale (no hard binary
    pass/fail).  The raw total is then normalised by the number of available
    signals so that missing data doesn't unfairly collapse the score.

    Gradient tiers (per signal, max 2.0 pts each):
      ROE:            ≥20% → 2.0 | ≥15% → 1.5 | ≥10% → 1.0 | ≥5% → 0.5 | <5% → 0
      Operating Mgn:  ≥25% → 2.0 | ≥15% → 1.5 | ≥10% → 1.0 | ≥5% → 0.5 | <5% → 0
      FCF Yield:      ≥5%  → 2.0 | ≥3%  → 1.5 | ≥1%  → 1.0 | ≥0% → 0.25| <0% → 0
      Debt/Equity:    <0.3 → 2.0 | <0.5 → 1.5 | <1.0 → 1.0 | <2.0→ 0.5 | ≥2.0 → 0
      Earnings Growth:≥15% → 2.0 | ≥8%  → 1.5 | ≥0%  → 0.5 | <0% → 0

    Normalisation: final_score = (earned / (n_available × 2)) × 10
    """
    breakdown: Dict[str, str] = {}
    raw_scores: Dict[str, float] = {}

    # ROE
    if roe is not None:
        if roe >= 20:
            raw_scores["roe"] = 2.0; breakdown["roe"] = f"{roe:.1f}% — Excellent (≥20%)"
        elif roe >= 15:
            raw_scores["roe"] = 1.5; breakdown["roe"] = f"{roe:.1f}% — Good (≥15%)"
        elif roe >= 10:
            raw_scores["roe"] = 1.0; breakdown["roe"] = f"{roe:.1f}% — Moderate (≥10%)"
        elif roe >= 5:
            raw_scores["roe"] = 0.5; breakdown["roe"] = f"{roe:.1f}% — Weak (≥5%)"
        else:
            raw_scores["roe"] = 0.0; breakdown["roe"] = f"{roe:.1f}% — Below threshold (<5%)"
    else:
        breakdown["roe"] = "N/A"

    # Operating Margin
    if operating_margin is not None:
        if operating_margin >= 25:
            raw_scores["operating_margin"] = 2.0; breakdown["operating_margin"] = f"{operating_margin:.1f}% — Strong pricing power (≥25%)"
        elif operating_margin >= 15:
            raw_scores["operating_margin"] = 1.5; breakdown["operating_margin"] = f"{operating_margin:.1f}% — Good margin (≥15%)"
        elif operating_margin >= 10:
            raw_scores["operating_margin"] = 1.0; breakdown["operating_margin"] = f"{operating_margin:.1f}% — Decent margin (≥10%)"
        elif operating_margin >= 5:
            raw_scores["operating_margin"] = 0.5; breakdown["operating_margin"] = f"{operating_margin:.1f}% — Thin margins (≥5%)"
        else:
            raw_scores["operating_margin"] = 0.0; breakdown["operating_margin"] = f"{operating_margin:.1f}% — Very thin/negative margins (<5%)"
    else:
        breakdown["operating_margin"] = "N/A"

    # FCF Yield
    if fcf_yield is not None:
        if fcf_yield >= 5:
            raw_scores["fcf_yield"] = 2.0; breakdown["fcf_yield"] = f"{fcf_yield:.1f}% — Strong FCF yield (≥5%)"
        elif fcf_yield >= 3:
            raw_scores["fcf_yield"] = 1.5; breakdown["fcf_yield"] = f"{fcf_yield:.1f}% — Good FCF yield (≥3%)"
        elif fcf_yield >= 1:
            raw_scores["fcf_yield"] = 1.0; breakdown["fcf_yield"] = f"{fcf_yield:.1f}% — Moderate FCF yield (≥1%)"
        elif fcf_yield >= 0:
            raw_scores["fcf_yield"] = 0.25; breakdown["fcf_yield"] = f"{fcf_yield:.1f}% — Low FCF yield (≥0%)"
        else:
            raw_scores["fcf_yield"] = 0.0; breakdown["fcf_yield"] = f"{fcf_yield:.1f}% — Negative FCF (<0%)"
    else:
        breakdown["fcf_yield"] = "N/A"

    # Debt/Equity (lower is better)
    if debt_to_equity is not None:
        if debt_to_equity < 0.30:
            raw_scores["debt_to_equity"] = 2.0; breakdown["debt_to_equity"] = f"{debt_to_equity:.2f} — Fortress balance sheet (<0.30)"
        elif debt_to_equity < 0.50:
            raw_scores["debt_to_equity"] = 1.5; breakdown["debt_to_equity"] = f"{debt_to_equity:.2f} — Strong balance sheet (<0.50)"
        elif debt_to_equity < 1.0:
            raw_scores["debt_to_equity"] = 1.0; breakdown["debt_to_equity"] = f"{debt_to_equity:.2f} — Manageable debt (<1.0)"
        elif debt_to_equity < 2.0:
            raw_scores["debt_to_equity"] = 0.5; breakdown["debt_to_equity"] = f"{debt_to_equity:.2f} — Elevated debt (<2.0)"
        else:
            raw_scores["debt_to_equity"] = 0.0; breakdown["debt_to_equity"] = f"{debt_to_equity:.2f} — High debt (≥2.0)"
    else:
        breakdown["debt_to_equity"] = "N/A"

    # Earnings Growth
    if earnings_growth is not None:
        if earnings_growth >= 15:
            raw_scores["earnings_growth"] = 2.0; breakdown["earnings_growth"] = f"{earnings_growth:.1f}% — Strong compounding (≥15%)"
        elif earnings_growth >= 8:
            raw_scores["earnings_growth"] = 1.5; breakdown["earnings_growth"] = f"{earnings_growth:.1f}% — Steady growth (≥8%)"
        elif earnings_growth >= 0:
            raw_scores["earnings_growth"] = 0.5; breakdown["earnings_growth"] = f"{earnings_growth:.1f}% — Flat growth (≥0%)"
        else:
            raw_scores["earnings_growth"] = 0.0; breakdown["earnings_growth"] = f"{earnings_growth:.1f}% — Declining earnings (<0%)"
    else:
        breakdown["earnings_growth"] = "N/A"

    # Normalise: if some signals unavailable, scale by available max so missing data
    # doesn't unfairly collapse the score
    if raw_scores:
        earned   = sum(raw_scores.values())
        possible = len(raw_scores) * 2.0          # max possible for available signals
        score    = round((earned / possible) * 10, 1)
    else:
        score = 0.0

    moat_label = (
        "Wide Moat"    if score >= 7 else
        "Narrow Moat"  if score >= 4 else
        "No Clear Moat"
    )

    return {
        "moat_score":  score,
        "moat_max":    10,
        "moat_label":  moat_label,
        "breakdown":   breakdown,
    }


# ── Main function ──────────────────────────────────────────────────────────────

def fundamental_analysis(symbol: str) -> Dict[str, Any]:
    """
    Warren Buffett–style fundamental quality analysis.

    Computes quality, safety, and value metrics entirely from publicly
    available financial data (no estimation, no price forecasting).

    Args:
        symbol: Ticker symbol (e.g. "AAPL", "MSFT", "RELIANCE.NS").

    Returns:
        Dict with:
          - quality metrics   (ROE, ROA, margins, FCF)
          - safety metrics    (debt levels, current ratio)
          - value metrics     (P/E, P/B, PEG ratio)
          - moat_score        (0–10 with label)
          - quality_score     (0–10 overall quality rating, Buffett-style)
          - quality_label     ("High", "Fair", "Low")
          - caveats           (list of data gaps or warnings)
    """
    try:
        t = _ticker(symbol)
        info = t.info

        # ── Quality Metrics ───────────────────────────────────────────────
        # ROE = Net Income / Shareholders' Equity
        # yfinance provides this directly as a decimal (0.1 = 10%)
        roe_raw        = _safe_float(info.get("returnOnEquity"))
        roe            = _pct(roe_raw)  # convert to percent

        # ROA = Net Income / Total Assets
        roa_raw        = _safe_float(info.get("returnOnAssets"))
        roa            = _pct(roa_raw)

        # Operating Margin = Operating Income / Revenue
        op_margin_raw  = _safe_float(info.get("operatingMargins"))
        op_margin      = _pct(op_margin_raw)

        # Net (Profit) Margin = Net Income / Revenue
        net_margin_raw = _safe_float(info.get("profitMargins"))
        net_margin     = _pct(net_margin_raw)

        # Gross Margin = Gross Profit / Revenue
        gross_margin_raw = _safe_float(info.get("grossMargins"))
        gross_margin   = _pct(gross_margin_raw)

        # EBITDA Margin = EBITDA / Revenue
        ebitda_margin_raw = _safe_float(info.get("ebitdaMargins"))
        ebitda_margin  = _pct(ebitda_margin_raw)

        # ── Safety Metrics ────────────────────────────────────────────────
        # Debt/Equity = Total Debt / Shareholders' Equity
        # yfinance returns this as a ratio (e.g. 0.55 means 55%)
        de_ratio       = _safe_float(info.get("debtToEquity"))
        # yfinance returns debtToEquity in percentage form (155 = 155%)
        # normalise to ratio regardless
        if de_ratio is not None and de_ratio > 20:
            de_ratio = round(de_ratio / 100, 4)   # yfinance gives 155.3 → 1.553

        # Current Ratio = Current Assets / Current Liabilities
        # Liquidity measure — ability to pay short-term obligations
        # > 1.5 is generally healthy; < 1.0 may indicate liquidity stress
        current_ratio  = _safe_float(info.get("currentRatio"))

        # Quick Ratio = (Current Assets − Inventory) / Current Liabilities
        quick_ratio    = _safe_float(info.get("quickRatio"))

        # ── Free Cash Flow ────────────────────────────────────────────────
        # FCF = Operating Cash Flow − Capital Expenditures
        # Positive FCF means the company generates real cash, not just accounting profit
        fcf_raw        = _safe_float(info.get("freeCashflow"))   # absolute value in currency
        market_cap     = _safe_float(info.get("marketCap"))
        fcf_yield: Optional[float] = None
        if fcf_raw is not None and market_cap and market_cap > 0:
            fcf_yield = round(fcf_raw / market_cap * 100, 2)    # as percentage

        # ── Value Metrics ─────────────────────────────────────────────────
        # Trailing P/E = Price / EPS (trailing 12 months)
        # Measures how much the market pays for every ₹/$ of earnings
        pe_ratio       = _safe_float(info.get("trailingPE"), 2)

        # Forward P/E = Price / Forecast EPS
        fwd_pe         = _safe_float(info.get("forwardPE"), 2)

        # Price/Book = Market Price / Book Value Per Share
        # Graham's classic value metric. P/B < 1.5 = potentially undervalued territory
        pb_ratio       = _safe_float(info.get("priceToBook"), 2)

        # PEG Ratio = P/E / Earnings Growth Rate
        # Peter Lynch popularised this. PEG < 1.0 = growth potentially undervalued
        # PEG < 1.5 = reasonable; > 2.0 = expensive relative to growth
        peg_ratio      = _safe_float(info.get("pegRatio"), 2)

        # Price/Sales = Market Cap / Revenue
        ps_ratio       = _safe_float(info.get("priceToSalesTrailing12Months"), 2)

        # Enterprise Value / EBITDA — useful for capital-intensive businesses
        ev_ebitda      = _safe_float(info.get("enterpriseToEbitda"), 2)

        # ── Growth Metrics ────────────────────────────────────────────────
        # Earnings Growth (YoY quarterly comparison from yfinance)
        earnings_growth_raw = _safe_float(info.get("earningsGrowth"))
        earnings_growth = _pct(earnings_growth_raw)  # convert to percent

        # Revenue Growth (YoY)
        revenue_growth_raw  = _safe_float(info.get("revenueGrowth"))
        revenue_growth  = _pct(revenue_growth_raw)

        # 5-year earnings growth estimate (analyst estimates, forward-looking)
        # We flag this clearly as an estimate, not a fact
        earnings_5y_est = _safe_float(info.get("fiveYearAvgDividendYield"))  # placeholder, yfinance doesn't provide clean 5yr EPS growth

        # ── Dividend ──────────────────────────────────────────────────────
        # Dividend Yield = Annual Dividend / Share Price
        # Buffett values consistent dividend payers as a sign of financial health
        # yfinance returns dividendYield already as a percentage decimal (0.58 = 0.58%).
        # Do NOT multiply by 100 — it is already in display-ready form.
        dividend_yield = round(_safe_float(info.get("dividendYield") or 0), 2)
        payout_ratio   = _pct(info.get("payoutRatio"))

        # ── Moat Score ────────────────────────────────────────────────────
        moat = _moat_score(
            roe=roe,
            operating_margin=op_margin,
            fcf_yield=fcf_yield,
            debt_to_equity=de_ratio,
            earnings_growth=earnings_growth,
        )

        # ── Overall Quality Score (0–10) ──────────────────────────────────
        # Composite from four pillars (max per pillar):
        #   Moat (4 pts)   : scaled from gradient _moat_score
        #   Growth (2 pts) : gross margin + revenue growth
        #   Value (2 pts)  : PEG / PE — rewards reasonable valuation
        #   Safety (2 pts) : current ratio + debt (normalised by availability)
        quality_sub = 0.0
        growth_sub  = 0.0
        value_sub   = 0.0
        safety_sub  = 0.0

        # Moat contribution (max 4.0)
        quality_sub = moat["moat_score"] * 0.40  # 10-pt scale × 0.4 → max 4.0

        # Growth (max 2.0): gross margin (max 1.0) + revenue growth (max 1.0)
        if gross_margin is not None:
            if gross_margin >= 40:
                growth_sub += 1.0
            elif gross_margin >= 25:
                growth_sub += 0.6
            elif gross_margin >= 15:
                growth_sub += 0.3
            else:
                growth_sub += 0.1
        if revenue_growth is not None:
            if revenue_growth >= 20:
                growth_sub += 1.0
            elif revenue_growth >= 12:
                growth_sub += 0.7
            elif revenue_growth >= 5:
                growth_sub += 0.4
            elif revenue_growth >= 0:
                growth_sub += 0.2

        # Value (max 2.0)
        if peg_ratio is not None:
            if peg_ratio < 1.0:
                value_sub = 2.0
            elif peg_ratio < 1.5:
                value_sub = 1.5
            elif peg_ratio < 2.5:
                value_sub = 0.75
        elif pe_ratio is not None:
            # Fallback: P/E vs generously reasonable threshold
            if pe_ratio < 15:
                value_sub = 1.5
            elif pe_ratio < 25:
                value_sub = 0.75

        # Safety (max 2.0): normalise by how many safety signals are available
        safety_pts = 0.0
        safety_max = 0.0
        if current_ratio is not None:
            safety_max += 1.0
            safety_pts += 1.0 if current_ratio >= 1.5 else (0.6 if current_ratio >= 1.0 else 0)
        if de_ratio is not None:
            safety_max += 1.0
            safety_pts += 1.0 if de_ratio < 0.30 else (0.6 if de_ratio < 0.50 else (0.3 if de_ratio < 1.0 else 0))
        # Scale to 2.0 proportionally; use neutral 1.0 when no safety data at all
        safety_sub = round((safety_pts / safety_max) * 2.0, 2) if safety_max > 0 else 1.0

        quality_score = round(min(10.0, quality_sub + growth_sub + value_sub + safety_sub), 1)
        quality_label = (
            "High Quality"  if quality_score >= 7   else
            "Fair Quality"  if quality_score >= 4.5 else
            "Low Quality"
        )

        # ── Caveats & Data Gaps ───────────────────────────────────────────
        caveats: list = []
        if roe is None:
            caveats.append("ROE not available — moat score may be understated")
        if fcf_yield is None:
            caveats.append("Free Cash Flow data not available — FCF yield could not be computed")
        if peg_ratio is None:
            caveats.append("PEG ratio not available — analyst estimates may be missing")
        if de_ratio is None:
            caveats.append("Debt/Equity not available — safety score may be incomplete")
        if earnings_growth is None:
            caveats.append("Earnings growth not available — moat growth signal not computed")
        caveats.append(
            "All metrics are trailing/LTM figures from public data. "
            "No forward price targets or investment recommendations are provided."
        )

        return {
            "status":          "success",
            "symbol":          symbol.upper(),
            "name":            info.get("longName") or info.get("shortName", symbol),
            "sector":          info.get("sector", "N/A"),
            "industry":        info.get("industry", "N/A"),
            "currency":        info.get("currency", "USD"),

            # Quality
            "roe_pct":         roe,
            "roa_pct":         roa,
            "gross_margin_pct":    gross_margin,
            "operating_margin_pct": op_margin,
            "net_margin_pct":  net_margin,
            "ebitda_margin_pct":   ebitda_margin,
            "fcf_abs":         fcf_raw,
            "fcf_yield_pct":   fcf_yield,

            # Safety
            "debt_to_equity":  de_ratio,
            "current_ratio":   current_ratio,
            "quick_ratio":     quick_ratio,

            # Value
            "pe_ratio":        pe_ratio,
            "forward_pe":      fwd_pe,
            "pb_ratio":        pb_ratio,
            "peg_ratio":       peg_ratio,
            "ps_ratio":        ps_ratio,
            "ev_ebitda":       ev_ebitda,

            # Growth
            "earnings_growth_yoy_pct": earnings_growth,
            "revenue_growth_yoy_pct":  revenue_growth,

            # Dividends
            "dividend_yield_pct": dividend_yield,
            "payout_ratio_pct":   payout_ratio,

            # Scores
            "moat_score":      moat["moat_score"],
            "moat_max":        10,
            "moat_label":      moat["moat_label"],
            "moat_breakdown":  moat["breakdown"],
            "quality_score":   quality_score,
            "quality_label":   quality_label,

            "caveats":         caveats,
        }

    except Exception as exc:
        logger.error("[fundamental_analysis] %s: %s", symbol, exc)
        return {"status": "error", "symbol": symbol.upper(), "message": str(exc)}
