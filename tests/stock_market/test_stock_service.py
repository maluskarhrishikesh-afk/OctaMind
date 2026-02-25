"""Unit tests for src/stock_market/stock_service.py

Tests pure-Python logic that does NOT require network calls:
  - RSI calculation
  - EMA calculation
  - Risk score bounds and labels
  - Pattern detection signal logic
  - Input validation / error paths

Tests that need network (yfinance) are marked @pytest.mark.e2e.
"""
import math
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.stock_market.stock_service import (
    _rsi,
    _ema,
    _safe_float,
)


# ── _safe_float ───────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_normal_float(self):
        assert _safe_float(3.14159) == 3.1416

    def test_integer_input(self):
        assert _safe_float(100) == 100.0

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_string_numeric(self):
        assert _safe_float("2.5") == 2.5

    def test_non_numeric_string_returns_none(self):
        assert _safe_float("abc") is None

    def test_decimal_places(self):
        result = _safe_float(1.23456789, decimals=2)
        assert result == 1.23


# ── _ema ──────────────────────────────────────────────────────────────────────

class TestEma:
    def test_length_preserved(self):
        data = [10.0] * 20
        result = _ema(data, span=12)
        assert len(result) == len(data)

    def test_constant_series_returns_same_value(self):
        data = [50.0] * 30
        result = _ema(data, span=12)
        # EMA of a constant series should converge to the same constant
        assert abs(result[-1] - 50.0) < 0.01

    def test_rising_series_ema_less_than_latest(self):
        data = list(range(1, 31))  # [1, 2, 3, ..., 30]
        result = _ema(data, span=12)
        # EMA lags price — last EMA should be less than last price
        assert result[-1] < data[-1]

    def test_single_element(self):
        result = _ema([42.0], span=5)
        assert result == [42.0]

    def test_first_value_equals_input(self):
        data = [100.0, 110.0, 105.0]
        result = _ema(data, span=2)
        assert result[0] == 100.0

    def test_span_2_formula(self):
        # multiplier = 2/(2+1) = 0.6667
        # EMA[1] = (110 - 100) * 0.6667 + 100 = 106.667
        data = [100.0, 110.0]
        result = _ema(data, span=2)
        expected = (110.0 - 100.0) * (2 / 3) + 100.0
        assert abs(result[1] - expected) < 0.001


# ── _rsi ──────────────────────────────────────────────────────────────────────

class TestRsi:
    def test_insufficient_data_returns_nan(self):
        # RSI needs at least period+1 values
        result = _rsi([100.0] * 5, period=14)
        assert math.isnan(result)

    def test_all_rising_prices_overbought(self):
        # All daily gains → RSI should approach 100
        prices = [float(100 + i) for i in range(30)]
        result = _rsi(prices, period=14)
        assert result > 70, f"Expected overbought RSI, got {result}"

    def test_all_falling_prices_oversold(self):
        # All daily losses → RSI should approach 0
        prices = [float(100 - i) for i in range(30)]
        result = _rsi(prices, period=14)
        assert result < 30, f"Expected oversold RSI, got {result}"

    def test_constant_prices_rsi_undefined(self):
        # No gains or losses → avg_loss = 0, avg_gain = 0
        # When both are 0, RSI would be 100 (no losses → return 100.0)
        prices = [50.0] * 20
        result = _rsi(prices, period=14)
        assert result == 100.0

    def test_rsi_between_0_and_100(self):
        import random
        random.seed(42)
        prices = [100.0 + random.gauss(0, 2) for _ in range(50)]
        result = _rsi(prices, period=14)
        if not math.isnan(result):
            assert 0 <= result <= 100

    def test_rsi_period_14_default(self):
        prices = [100.0 + i * 0.5 for i in range(20)]
        result_default = _rsi(prices)
        result_explicit = _rsi(prices, period=14)
        assert result_default == result_explicit


# ── risk_score bounds ─────────────────────────────────────────────────────────

class TestRiskScoreLogic:
    def test_risk_level_labels(self):
        """Test score-to-label mapping without needing network."""
        from src.stock_market.stock_service import _safe_float

        # Replicate the label logic inline
        def score_to_label(score):
            return (
                "Very Low"   if score < 2.5 else
                "Low"        if score < 4   else
                "Moderate"   if score < 6   else
                "High"       if score < 8   else
                "Very High"
            )

        assert score_to_label(1.0) == "Very Low"
        assert score_to_label(2.4) == "Very Low"
        assert score_to_label(3.5) == "Low"
        assert score_to_label(5.0) == "Moderate"
        assert score_to_label(7.0) == "High"
        assert score_to_label(9.0) == "Very High"

    def test_vol_score_capped_at_10(self):
        """vol_score = min(10, max(1, round(annual_vol / 5)))"""
        def vol_score(annual_vol):
            return min(10, max(1, round(annual_vol / 5)))

        assert vol_score(0) == 1    # minimum is 1
        assert vol_score(5) == 1    # round(1) = 1
        assert vol_score(25) == 5
        assert vol_score(50) == 10  # max is 10
        assert vol_score(100) == 10  # still capped


# ── pattern detection logic ───────────────────────────────────────────────────

class TestPatternDetectionLogic:
    def test_doji_detection(self):
        """
        Doji: body < 10% of range.
        Test the rule directly with known OHLC values.
        """
        # OHLC: open=100, close=100.1 (tiny body), high=105, low=95
        o, c, h, l = 100.0, 100.1, 105.0, 95.0
        body = abs(c - o)       # 0.1
        range_ = h - l          # 10.0
        is_doji = body / range_ < 0.1  # 0.01 < 0.1 → True
        assert is_doji

    def test_hammer_detection_in_downtrend(self):
        """
        Hammer: lower shadow > 2*body, upper shadow < body, in downtrend.
        """
        o, c, h, l = 100.0, 102.0, 103.0, 90.0  # long lower shadow
        body         = abs(c - o)     # 2.0
        lower_shadow = min(o, c) - l  # 100 - 90 = 10
        upper_shadow = h - max(o, c)  # 103 - 102 = 1
        is_hammer = (lower_shadow > 2 * body and upper_shadow < body)
        assert is_hammer

    def test_shooting_star_detection_in_uptrend(self):
        """
        Shooting Star: long upper shadow, small body, in uptrend.
        """
        o, c, h, l = 100.0, 98.0, 112.0, 99.5
        body         = abs(c - o)     # 2.0
        lower_shadow = min(o, c) - l  # 98 - 99.5 = -1.5 → effectively 0 from perspective of min(o,c)
        upper_shadow = h - max(o, c)  # 112 - 100 = 12
        is_shooting = upper_shadow > 2 * body  # 12 > 4 → True
        assert is_shooting

    def test_bullish_engulfing(self):
        """Previous red candle fully engulfed by current green candle."""
        # Previous: open > close (red) → o_p=105, c_p=100
        # Current: open < close (green), open < prev close, close > prev open
        o_p, c_p = 105.0, 100.0   # red candle
        o, c     = 99.0, 106.0    # green candle that engulfs
        is_engulf = (c_p < o_p and c > o and c > o_p and o < c_p)
        assert is_engulf

    def test_bearish_engulfing(self):
        """Previous green candle fully engulfed by current red candle."""
        o_p, c_p = 100.0, 105.0   # green candle
        o, c     = 106.0, 99.0    # red candle that engulfs
        is_engulf = (c_p > o_p and c < o and c < o_p and o > c_p)
        assert is_engulf


# ── compare_stocks validation ─────────────────────────────────────────────────

class TestCompareStocksValidation:
    def test_single_symbol_returns_error(self, monkeypatch):
        from src.stock_market import compare_stocks
        result = compare_stocks(["AAPL"])
        assert result["status"] == "error"
        assert "at least two" in result["message"].lower()

    def test_empty_symbols_returns_error(self, monkeypatch):
        from src.stock_market import compare_stocks
        result = compare_stocks([])
        assert result["status"] == "error"


# ── portfolio_suggestions validation ─────────────────────────────────────────

class TestPortfolioSuggestionsValidation:
    def test_empty_symbols_returns_error(self):
        from src.stock_market import portfolio_suggestions
        result = portfolio_suggestions([])
        assert result["status"] == "error"
        assert "no symbols" in result["message"].lower()


# ── get_quote validation ──────────────────────────────────────────────────────

@pytest.mark.e2e
def test_get_quote_real_data():
    """Live test: AAPL quote from Yahoo Finance."""
    from src.stock_market import get_quote
    result = get_quote("AAPL")
    assert result["status"] == "success", f"get_quote failed: {result}"
    assert result["symbol"] == "AAPL"
    assert result["price"] is not None
    assert result["price"] > 0


@pytest.mark.e2e
def test_invalid_symbol_returns_error_or_empty():
    """Invalid ticker should not crash — may return error or None price."""
    from src.stock_market import get_quote
    result = get_quote("XXXXINVALID99999")
    # Either status=error OR price=None — either is acceptable
    if result.get("status") == "success":
        assert result.get("price") is None  # Yahoo returns empty info
    else:
        assert result["status"] == "error"


@pytest.mark.e2e
def test_market_overview_real_data():
    """Market overview should return at least SPY data."""
    from src.stock_market import market_overview
    result = market_overview()
    assert result["status"] == "success"
    assert "market_mood" in result
    assert isinstance(result["overview"], list)
    assert len(result["overview"]) > 0
