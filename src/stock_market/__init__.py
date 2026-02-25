"""Stock Market Analysis service package — OctaMind."""
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
)

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
]
