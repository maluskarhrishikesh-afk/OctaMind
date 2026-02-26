"""Stock Market Analysis service package — Octa Bot."""
from src.stock_market.stock_service import (
    get_quote,
    get_historical_data,
    technical_analysis,
    risk_score,
    pattern_detection,
    portfolio_analysis,
    portfolio_suggestions,
    sentiment_analysis,
    compare_stocks,
    market_overview,
    generate_full_report,
    resolve_ticker,
)
from src.stock_market.fundamental_service import fundamental_analysis

__all__ = [
    "get_quote",
    "get_historical_data",
    "technical_analysis",
    "risk_score",
    "pattern_detection",
    "portfolio_analysis",
    "portfolio_suggestions",
    "sentiment_analysis",
    "compare_stocks",
    "market_overview",
    "fundamental_analysis",
    "generate_full_report",
    "resolve_ticker",
]
