"""Focused tests for browser and stock orchestrators."""

import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_browser_tool_docs_load_from_markdown():
    browser_orchestrator = importlib.import_module("src.agent.ui.browser_agent.orchestrator")

    docs = getattr(browser_orchestrator, "_get_tool_docs_for_dag")()

    assert "search_web(query, num_results=5)" in docs
    assert "summarize_page(url, max_words=200)" in docs
    assert "download_file_from_url(url, save_path)" in docs


def test_browser_agent_handles_price_comparison_query_without_llm(monkeypatch):
    browser_orchestrator = importlib.import_module("src.agent.ui.browser_agent.orchestrator")
    from src.browser import browser_service

    def fake_browse_url(url: str, max_chars: int = 3000):
        _ = (url, max_chars)
        return {
            "status": "success",
            "content": (
                'Showing 1 - 36 results Apple iPhone 13 Pro (256GB, Gold) ₹ 1,29,900.00 C Croma '
                'Apple iPhone 13 Pro 256Gb ₹ 1,04,900.00 B Best of Indian Products '
                'Apple iPhone 13 Pro (128GB) Blue ₹ 37,000.00 O Olx India '
                'Appi iPhone_13 Pro (256 GB) | Sierra ₹ 45,995.00 A Amazon.In '
            ),
        }

    monkeypatch.setattr(browser_service, "browse_url", fake_browse_url)

    result = browser_orchestrator.execute_with_llm_orchestration(
        "Can you compare the latest price of Apple iPhone 13 Pro on various websites and tell me where it is the cheapest?"
    )

    assert result["status"] == "success"
    assert result["tool_used"] == "browse_url"
    assert "Croma" in result["message"]
    assert "Olx India" in result["message"]
    assert "Cheapest comparable listing found: Olx India at ₹ 37,000.00." in result["message"]
    assert len(result["raw"]["comparisons"]) >= 3


def test_browser_agent_ignores_injected_session_state_for_price_queries(monkeypatch):
    browser_orchestrator = importlib.import_module("src.agent.ui.browser_agent.orchestrator")
    from src.browser import browser_service

    def fake_browse_url(url: str, max_chars: int = 3000):
        _ = max_chars
        assert "Session+State" not in url
        assert "Apple+iPhone+17+Pro" in url
        return {
            "status": "success",
            "content": (
                "Showing 1 - 36 results Apple iPhone 17 Pro (256GB) ₹ 1,39,900.00 C Croma "
                "Apple iPhone 17 Pro (256GB) ₹ 1,29,900.00 U Ubuy India "
            ),
        }

    monkeypatch.setattr(browser_service, "browse_url", fake_browse_url)

    result = browser_orchestrator.execute_with_llm_orchestration(
        "Can you compare the latest price of Apple iPhone 17 Pro on various websites and tell me where it is the cheapest?\n\n"
        "## Session State\n"
        '{"current_date": "2026-03-10", "last_assistant_action": "router_enrichment"}'
    )

    assert result["status"] == "success"
    assert result["raw"]["product"] == "Apple iPhone 17 Pro"
    assert "Ubuy India" in result["message"]


def test_stock_tool_docs_load_from_markdown():
    stock_orchestrator = importlib.import_module("src.agent.ui.stock_agent.orchestrator")

    docs = getattr(stock_orchestrator, "_get_tool_docs_for_dag")()

    assert "research_company_web(company_name, symbol=\"\", num_results=6, max_pages=4)" in docs
    assert "generate_full_report(query_or_symbol, output_path=\"\", send_to_email=\"\")" in docs
    assert "fundamental_analysis(symbol)" in docs


def test_resolve_ticker_prefers_indian_exact_name_match(monkeypatch):
    from src.stock_market import stock_service

    class FakeSearchResult:
        quotes = [
            {
                "exchange": "HKG",
                "quoteType": "EQUITY",
                "symbol": "6883.HK",
                "shortname": "ETERNAL BEAUTY",
                "longname": "Eternal Beauty Holdings Limited",
                "score": 20018.0,
            },
            {
                "exchange": "BSE",
                "quoteType": "EQUITY",
                "symbol": "ETERNAL.BO",
                "shortname": "Eternal Limited",
                "longname": "Eternal Limited",
                "prevName": "Zomato Limited",
                "score": 20006.0,
            },
        ]

    class FakeYF:
        @staticmethod
        def Search(query: str, max_results: int = 10):
            _ = (query, max_results)
            return FakeSearchResult()

    monkeypatch.setattr(stock_service, "_yf", lambda: FakeYF())

    assert stock_service.resolve_ticker("Eternal") == "ETERNAL.BO"


def test_research_company_web_extracts_overview_and_management_commentary(monkeypatch):
    stock_orchestrator = importlib.import_module("src.agent.ui.stock_agent.orchestrator")

    def fake_search(query: str, num_results: int = 5):
        _ = num_results
        if "management commentary" in query:
            return {
                "status": "success",
                "results": [
                    {
                        "title": "Intellect Design Arena Annual Report Management Commentary",
                        "url": "https://example.com/annual-report",
                        "snippet": "Management highlighted strong deal momentum and margin discipline.",
                    }
                ],
            }
        if "overview" in query:
            return {
                "status": "success",
                "results": [
                    {
                        "title": "Intellect Design Arena Company Overview",
                        "url": "https://example.com/company-overview",
                        "snippet": "The company provides banking technology platforms and financial software.",
                    }
                ],
            }
        return {
            "status": "success",
            "results": [
                {
                    "title": "Intellect Design Arena Quarterly Results Update",
                    "url": "https://example.com/results-update",
                    "snippet": "Recent updates referenced pipeline conversion and execution priorities.",
                }
            ],
        }

    def fake_summarize(url: str, max_words: int = 180):
        _ = max_words
        if "annual-report" in url:
            return {
                "status": "success",
                "summary": "Management commentary pointed to strong deal momentum, improving execution, and a focus on margin discipline.",
            }
        if "company-overview" in url:
            return {
                "status": "success",
                "summary": "Intellect Design Arena builds banking technology products and software platforms for financial institutions.",
            }
        return {
            "status": "success",
            "summary": "Recent market updates highlighted pipeline conversion and operating priorities.",
        }

    monkeypatch.setattr(stock_orchestrator, "_browser_search", fake_search)
    monkeypatch.setattr(stock_orchestrator, "_browser_summarize", fake_summarize)
    monkeypatch.setattr(
        stock_orchestrator,
        "_browser_agent_company_research",
        lambda company_name, symbol="": {
            "status": "success",
            "summary": f"Browser-agent memo for {company_name} {symbol}".strip(),
        },
    )

    result = stock_orchestrator.research_company_web(
        "Intellect Design Arena",
        symbol="INTELLECT.NS",
        num_results=4,
        max_pages=3,
    )

    assert result["status"] == "success"
    assert "banking technology" in result["company_overview"].lower()
    assert "margin discipline" in result["management_commentary"].lower()
    assert "browser-agent memo" in result["browser_agent_summary"].lower()
    assert result["sources"]


def test_generate_full_report_uses_browser_research_in_report(monkeypatch, tmp_path):
    stock_orchestrator = importlib.import_module("src.agent.ui.stock_agent.orchestrator")
    from src.stock_market import fundamental_service as fundamental_service
    from src.stock_market import stock_service

    monkeypatch.setattr(stock_service, "resolve_ticker", lambda query: "INTELLECT.NS")
    monkeypatch.setattr(
        stock_service,
        "get_quote",
        lambda symbol: {
            "status": "success",
            "symbol": symbol,
            "name": "Intellect Design Arena",
            "price": 1025.0,
            "currency": "INR",
            "change_pct": 1.8,
            "market_cap": 1000000000,
            "sector": "Technology",
            "industry": "Financial Software",
        },
    )
    monkeypatch.setattr(
        fundamental_service,
        "fundamental_analysis",
        lambda symbol: {
            "status": "success",
            "symbol": symbol,
            "name": "Intellect Design Arena",
            "currency": "INR",
            "quality_score": 7.6,
            "quality_label": "High Quality",
            "moat_label": "Narrow Moat",
            "roe_pct": 18.5,
            "operating_margin_pct": 19.2,
            "gross_margin_pct": 62.4,
            "revenue_growth_yoy_pct": 14.3,
            "earnings_growth_yoy_pct": 16.1,
            "pe_ratio": 28.5,
            "debt_to_equity": 0.22,
        },
    )
    monkeypatch.setattr(
        stock_service,
        "technical_analysis",
        lambda symbol, period="6mo": {
            "status": "success",
            "symbol": symbol,
            "trend": "Uptrend",
            "rsi": {"value": 61.0, "signal": "Bullish"},
            "macd": {"histogram": 1.25, "signal_text": "bullish"},
            "moving_averages": {"sma20": 990.0, "sma50": 955.0, "sma200": 880.0},
            "overall_signal": "Bullish",
        },
    )
    monkeypatch.setattr(
        stock_service,
        "risk_score",
        lambda symbol, period="1y": {
            "status": "success",
            "symbol": symbol,
            "risk_score": 4.1,
            "risk_level": "Moderate",
            "annual_volatility_pct": 24.0,
            "max_drawdown_pct": 18.0,
        },
    )
    monkeypatch.setattr(
        stock_service,
        "pattern_detection",
        lambda symbol, period="3mo": {
            "status": "success",
            "symbol": symbol,
            "support": 960.0,
            "resistance": 1085.0,
            "price_position": "above VWAP, near 20d resistance",
            "patterns": ["Bullish Engulfing - momentum shift"],
        },
    )
    monkeypatch.setattr(
        stock_service,
        "sentiment_analysis",
        lambda symbol: {
            "status": "success",
            "symbol": symbol,
            "overall_sentiment": "Positive",
            "aggregate_score": 0.41,
            "positive_headlines": 7,
            "negative_headlines": 2,
        },
    )
    monkeypatch.setattr(
        stock_orchestrator,
        "research_company_web",
        lambda company_name, symbol="", num_results=6, max_pages=4: {
            "status": "success",
            "company_name": company_name,
            "symbol": symbol,
            "company_overview": "The company builds banking technology products for financial institutions.",
            "management_commentary": "Management commentary highlighted strong deal momentum, improved execution, and margin discipline.",
            "market_context": "Recent commentary suggests healthy demand but continued execution expectations.",
            "overall_sentiment": "Positive",
            "sentiment_score": 3,
            "browser_agent_summary": "Browser agent says demand remains healthy, but execution discipline remains important.",
            "sources": [{"title": "Example", "url": "https://example.com", "category": "management_commentary", "summary": "Strong deal momentum."}],
        },
    )

    captured = {}

    def fake_write_pdf(path: str, title: str, content: str):
        captured["path"] = path
        captured["title"] = title
        captured["content"] = content
        return {"status": "success", "file_path": path, "path": path}

    monkeypatch.setattr(stock_orchestrator, "_write_pdf_report", fake_write_pdf)

    def raise_no_llm():
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(stock_orchestrator, "_load_report_llm", raise_no_llm)

    tools = getattr(stock_orchestrator, "_build_all_tools")()
    result = tools["generate_full_report"](
        "Intellect Design Arena",
        output_path=str(tmp_path / "intellect_report.pdf"),
    )

    assert result["status"] == "success"
    assert result["symbol"] == "INTELLECT.NS"
    assert captured["path"].endswith("intellect_report.pdf")
    assert result["markdown_path"].endswith("intellect_report.md")
    assert "## **Company Overview**" in captured["content"]
    assert "## **Competitive Position**" in captured["content"]
    assert "## **Final Investment Summary**" in captured["content"]
    assert "<span style=\"color:" in captured["content"]
    assert "MACD Histogram" in captured["content"]
    assert "deal momentum" in captured["content"].lower()
    assert "not financial advice" in captured["content"].lower()