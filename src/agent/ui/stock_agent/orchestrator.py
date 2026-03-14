"""Stock Market skill orchestrator."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agent.runtime_paths import get_your_data_dir
from src.agent.workflows.skill_dag_engine import run_skill_dag
from src.agent.workflows.skill_react_engine import run_skill_react

logger = logging.getLogger("stock.orchestrator")

_POSITIVE_RESEARCH_TERMS = (
    "growth", "strong", "improved", "record", "healthy", "robust", "resilient",
    "expansion", "momentum", "profit", "margin expansion", "order book", "pipeline",
    "wins", "tailwind", "opportunity", "optimistic", "confident",
)
_NEGATIVE_RESEARCH_TERMS = (
    "slowdown", "weak", "decline", "pressure", "challenging", "headwind", "delay",
    "drop", "contraction", "risk", "concern", "volatile", "cautious", "softness",
    "margin pressure", "uncertain", "litigation", "debt", "loss",
)


def _load_skill_context() -> str:
    """Load the stock skill context from skill_context.md."""
    return (Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return cleaned or "stock_report"


def _clean_text_block(text: str, limit: int = 400) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _collect_unique_sentences(chunks: List[str], max_items: int = 3) -> List[str]:
    collected: List[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        normalized = re.sub(r"\s+", " ", str(chunk or "")).strip()
        if not normalized:
            continue
        parts = re.split(r"(?<=[.!?])\s+|\s*[•;]\s*", normalized)
        for part in parts:
            sentence = re.sub(r"\s+", " ", part).strip(" -")
            if len(sentence) < 35:
                continue
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            collected.append(sentence)
            if len(collected) >= max_items:
                return collected
    return collected


def _classify_research_category(title: str, url: str, query: str) -> str:
    haystack = f"{title} {url} {query}".lower()
    if any(keyword in haystack for keyword in (
        "management commentary", "management discussion", "annual report", "investor",
        "earnings call", "shareholder", "results", "conference call", "presentation",
    )):
        return "management_commentary"
    if any(keyword in haystack for keyword in (
        "about", "company", "overview", "profile", "business model", "wikipedia",
    )):
        return "company_overview"
    return "market_context"


def _score_research_result(result: Dict[str, Any], company_name: str, query: str) -> int:
    title = str(result.get("title", "") or "")
    url = str(result.get("url", "") or "")
    snippet = str(result.get("snippet", "") or "")
    haystack = f"{title} {url} {snippet} {query}".lower()
    company_tokens = [
        token for token in re.findall(r"[a-z0-9]+", company_name.lower()) if len(token) > 2
    ]

    score = sum(2 for token in company_tokens if token in haystack)
    if any(keyword in haystack for keyword in ("annual report", "management", "investor", "presentation", "results", "commentary")):
        score += 5
    if any(keyword in haystack for keyword in ("overview", "about", "profile", "business model", "wikipedia")):
        score += 3
    if any(keyword in haystack for keyword in ("moneycontrol", "screener", "trendlyne", "reuters", "bloomberg", "economictimes", "business-standard")):
        score += 2
    if any(keyword in haystack for keyword in ("linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com")):
        score -= 3
    return score


def _score_research_sentiment(chunks: List[str]) -> Dict[str, Any]:
    total_score = 0
    lowered_chunks = [str(chunk or "").lower() for chunk in chunks if str(chunk or "").strip()]
    for chunk in lowered_chunks:
        total_score += sum(1 for term in _POSITIVE_RESEARCH_TERMS if term in chunk)
        total_score -= sum(1 for term in _NEGATIVE_RESEARCH_TERMS if term in chunk)

    if total_score >= 2:
        label = "Positive"
    elif total_score <= -2:
        label = "Negative"
    else:
        label = "Mixed"

    return {
        "overall_sentiment": label,
        "sentiment_score": total_score,
    }


def _browser_search(query: str, num_results: int = 5) -> Dict[str, Any]:
    from src.browser import browser_service as bs  # noqa: PLC0415

    return bs.search_web(query, num_results)


def _browser_summarize(url: str, max_words: int = 180) -> Dict[str, Any]:
    from src.browser import browser_service as bs  # noqa: PLC0415

    return bs.summarize_page(url, max_words)


def _extract_browser_agent_summary(result: Dict[str, Any]) -> str:
    parts: List[str] = []
    if not isinstance(result, dict):
        return ""

    message = str(result.get("message", "") or "").strip()
    if message:
        parts.append(message)

    raw = result.get("raw")
    if isinstance(raw, dict):
        for key in ("summary", "content", "report_content", "message"):
            value = str(raw.get(key, "") or "").strip()
            if value and value not in parts:
                parts.append(value)

    combined = "\n\n".join(parts).strip()
    if any(token in combined.lower() for token in ("llm error", "ratelimitreached", "iteration limit", "planning llm call failed")):
        return ""
    return _clean_text_block(combined, limit=2500) if combined else ""


def _browser_agent_company_research(company_name: str, symbol: str = "") -> Dict[str, Any]:
    from src.agent.ui.browser_agent import orchestrator as browser_orchestrator  # noqa: PLC0415

    target = company_name or symbol
    if symbol:
        target = f"{target} ({symbol})"

    query = (
        f"Research {target} for an equity-analysis document. Search the public web and summarise in plain English with short sections covering: "
        "Company Overview, Business Model, Industry Context, Management Commentary, Growth Drivers, Risks, Institutional Activity if publicly mentioned, and Recent News Sentiment. "
        "Prefer investor-relations pages, annual reports, quarterly results, exchange filings, Reuters, Bloomberg, and other major business press. "
        "Be explicit when information is limited. Do not give buy, sell, or hold advice."
    )

    try:
        result = browser_orchestrator.execute_with_llm_orchestration(query)
        summary = _extract_browser_agent_summary(result)
        return {
            "status": "success" if summary else "error",
            "summary": summary,
            "raw": result,
        }
    except Exception as exc:
        logger.warning("[stock-report] Browser agent research failed: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
            "summary": "",
        }


def _load_report_llm():
    from src.agent.llm.llm_parser import get_llm_client  # noqa: PLC0415

    return get_llm_client()


def _write_pdf_report(path: str, title: str, content: str) -> Dict[str, Any]:
    from src.files.features.file_ops import write_pdf_report as _write  # noqa: PLC0415

    return _write(path, title, content)


def _send_report_email(to: str, subject: str, message: str, attachment_path: str) -> Dict[str, Any]:
    from src.email.gmail_service import _get_client  # noqa: PLC0415

    svc = _get_client()
    normalized_to = str(to or "").strip()
    if normalized_to.lower() in {"me", "myself", "my email", "my email address"}:
        try:
            profile = svc.gmail_service.users().getProfile(userId="me").execute()
            normalized_to = str(profile.get("emailAddress", "") or "").strip() or normalized_to
        except Exception:
            pass
    return svc.send_email_with_attachment(normalized_to, subject, message, attachment_path)


def research_company_web(
    company_name: str,
    symbol: str = "",
    num_results: int = 6,
    max_pages: int = 4,
) -> Dict[str, Any]:
    company_name = str(company_name or "").strip()
    symbol = str(symbol or "").strip().upper()
    if not company_name and not symbol:
        return {"status": "error", "message": "company_name or symbol is required for company web research."}

    search_target = company_name or symbol
    browser_agent_research = _browser_agent_company_research(company_name, symbol)
    queries = [
        f'"{search_target}" company overview business model',
        f'"{search_target}" management commentary annual report',
        f'"{search_target}" latest quarterly results investor presentation',
    ]

    candidates: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()

    for query in queries:
        search_result = _browser_search(query, num_results=min(max(1, num_results), 8))
        if search_result.get("status") != "success":
            continue
        for result in search_result.get("results", []):
            url = str(result.get("url", "") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            enriched = dict(result)
            enriched["query"] = query
            enriched["score"] = _score_research_result(enriched, search_target, query)
            candidates.append(enriched)

    if not candidates and not browser_agent_research.get("summary"):
        return {
            "status": "error",
            "message": f"No useful web research results found for {search_target}.",
            "company_name": search_target,
            "symbol": symbol,
        }

    top_candidates = sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)[: max(1, max_pages)]
    source_entries: List[Dict[str, Any]] = []
    company_chunks: List[str] = []
    management_chunks: List[str] = []
    market_chunks: List[str] = []

    for candidate in top_candidates:
        title = str(candidate.get("title", "") or "")
        url = str(candidate.get("url", "") or "")
        snippet = _clean_text_block(str(candidate.get("snippet", "") or ""), limit=260)
        summary_result = _browser_summarize(url, max_words=180)
        summary_text = _clean_text_block(summary_result.get("summary") or snippet, limit=420)
        category = _classify_research_category(title, url, str(candidate.get("query", "")))

        if category == "company_overview":
            company_chunks.append(summary_text or snippet)
        elif category == "management_commentary":
            management_chunks.append(summary_text or snippet)
        else:
            market_chunks.append(summary_text or snippet)

        source_entries.append({
            "title": title,
            "url": url,
            "category": category,
            "summary": summary_text or snippet,
        })

    company_points = _collect_unique_sentences(company_chunks, max_items=3)
    management_points = _collect_unique_sentences(management_chunks, max_items=3)
    market_points = _collect_unique_sentences(market_chunks, max_items=3)
    sentiment = _score_research_sentiment(
        company_chunks + management_chunks + market_chunks + [entry.get("title", "") for entry in source_entries]
    )

    return {
        "status": "success",
        "company_name": search_target,
        "symbol": symbol,
        "company_overview": " ".join(company_points) or "Limited public overview data was gathered from the current web sources.",
        "management_commentary": " ".join(management_points) or "No clear management-commentary source was found in the selected public results.",
        "market_context": " ".join(market_points) or "Limited additional market-context commentary was available from the selected public results.",
        "overall_sentiment": sentiment["overall_sentiment"],
        "sentiment_score": sentiment["sentiment_score"],
        "sources": source_entries,
        "browser_agent_summary": browser_agent_research.get("summary", ""),
        "browser_agent_status": browser_agent_research.get("status", "error"),
    }


def _performance_assessment(
    company_name: str,
    fundamentals: Dict[str, Any],
    risk: Dict[str, Any],
    news_sentiment: Dict[str, Any],
) -> str:
    positive_signals = 0
    negative_signals = 0
    evidence: List[str] = []

    revenue_growth = fundamentals.get("revenue_growth_yoy_pct")
    earnings_growth = fundamentals.get("earnings_growth_yoy_pct")
    quality_score = fundamentals.get("quality_score")
    moat_label = fundamentals.get("moat_label")
    risk_level = str(risk.get("risk_level", "") or "")
    headline_sentiment = str(news_sentiment.get("overall_sentiment", "") or "")

    if revenue_growth is not None:
        if revenue_growth >= 10:
            positive_signals += 1
            evidence.append(f"revenue growth is running at {revenue_growth:.1f}% YoY")
        elif revenue_growth < 0:
            negative_signals += 1
            evidence.append(f"revenue growth is negative at {revenue_growth:.1f}% YoY")

    if earnings_growth is not None:
        if earnings_growth >= 10:
            positive_signals += 1
            evidence.append(f"earnings growth is healthy at {earnings_growth:.1f}% YoY")
        elif earnings_growth < 0:
            negative_signals += 1
            evidence.append(f"earnings growth is under pressure at {earnings_growth:.1f}% YoY")

    if quality_score is not None:
        if quality_score >= 7:
            positive_signals += 1
            evidence.append(f"quality score is solid at {quality_score}/10")
        elif quality_score < 4.5:
            negative_signals += 1
            evidence.append(f"quality score is modest at {quality_score}/10")

    if moat_label and "wide" in moat_label.lower():
        positive_signals += 1
        evidence.append(f"the company is classified as having a {moat_label.lower()}")
    elif moat_label and "no clear" in moat_label.lower():
        negative_signals += 1
        evidence.append(f"the moat assessment is only '{moat_label}'")

    if risk_level:
        if risk_level.lower() in {"high", "very high"}:
            negative_signals += 1
            evidence.append(f"market risk is currently assessed as {risk_level.lower()}")
        elif risk_level.lower() in {"very low", "low"}:
            positive_signals += 1
            evidence.append(f"market risk is currently assessed as {risk_level.lower()}")

    if headline_sentiment == "Positive":
        positive_signals += 1
        evidence.append("recent headline sentiment is positive")
    elif headline_sentiment == "Negative":
        negative_signals += 1
        evidence.append("recent headline sentiment is negative")

    if positive_signals > negative_signals:
        lead = f"The available evidence suggests {company_name} has had a relatively strong recent period."
    elif negative_signals > positive_signals:
        lead = f"The current data paints a mixed-to-soft operating picture for {company_name}."
    else:
        lead = f"The available data suggests a mixed year for {company_name}, with both constructive and cautious signals."

    if evidence:
        return f"{lead} Key evidence: " + "; ".join(evidence[:4]) + "."
    return lead


def _extract_keyword_sentences(
    chunks: List[str],
    keywords: List[str],
    max_items: int = 3,
) -> List[str]:
    matches: List[str] = []
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for sentence in _collect_unique_sentences(chunks, max_items=12):
        lowered_sentence = sentence.lower()
        if any(keyword in lowered_sentence for keyword in lowered_keywords):
            matches.append(sentence)
        if len(matches) >= max_items:
            break
    return matches


def _fmt_metric(value: Any, suffix: str = "", decimals: int = 2) -> str:
    try:
        return f"{float(value):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_market_cap(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"

    for threshold, suffix in ((1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M")):
        if abs(number) >= threshold:
            return f"{number / threshold:,.2f}{suffix}"
    return f"{number:,.0f}"


def _styled_heading(text: str, level: int = 2) -> str:
    level = 1 if level < 1 else min(level, 3)
    return f"{'#' * level} **{text}**"


def _tone_color(tone: str) -> str:
    palette = {
        "risk": "#b42318",
        "good": "#15803d",
        "warn": "#b54708",
        "info": "#1d4ed8",
        "muted": "#475467",
    }
    return palette.get(tone, palette["info"])


def _styled_label(label: str, tone: str = "info") -> str:
    if tone not in {"risk", "good"}:
        return f"**{label}**"
    return f'<span style="color:{_tone_color(tone)}"><strong>{label}</strong></span>'


def _styled_metric_line(
    label: str,
    value: Any,
    *,
    tone: str = "info",
    suffix: str = "",
    decimals: int = 2,
    unavailable_note: str = "Unavailable from the current provider payload; verify from filings or an alternate source.",
) -> str:
    formatted = _fmt_metric(value, suffix, decimals)
    if formatted == "N/A":
        return f"- {_styled_label(label, tone)} N/A. {unavailable_note}"
    return f"- {_styled_label(label, tone)} {formatted}"


def _dedupe_preserve(items: List[str]) -> List[str]:
    unique: List[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = re.sub(r"\s+", " ", str(item or "")).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _infer_business_model_fallback(sector: str, industry: str) -> str:
    haystack = f"{sector} {industry}".lower()
    if any(token in haystack for token in ("software", "application", "saas", "technology")):
        return "- The available evidence points to a software/platform-led business with revenue likely tied to product deployments, licences, support, and enterprise relationships."
    if any(token in haystack for token in ("internet retail", "retail", "e-commerce", "restaurants", "consumer cyclical")):
        return "- The available evidence points to a consumer-internet or platform-commerce model where scale, demand density, and execution efficiency matter more than traditional asset intensity."
    if any(token in haystack for token in ("bank", "financial", "fintech", "insurance")):
        return "- The available evidence points to a financial-services or fintech model driven by product distribution, transaction flows, and institutional customer relationships."
    return "- The available evidence was not rich enough to map the revenue model precisely, so this section should be treated as provisional."


def _infer_competitive_position_fallback(sector: str, industry: str) -> List[str]:
    haystack = f"{sector} {industry}".lower()
    if any(token in haystack for token in ("software", "application", "saas", "technology", "fintech")):
        return [
            "- Competitive position likely depends on product depth, implementation quality, switching costs, and the ability to win repeat enterprise mandates.",
            "- In software-heavy categories, investors should compare growth durability and margin profile against global and local peers rather than price action alone.",
        ]
    if any(token in haystack for token in ("internet retail", "retail", "e-commerce", "consumer cyclical")):
        return [
            "- Competitive position likely depends on demand density, logistics execution, customer retention, and the ability to scale efficiently.",
            "- In platform-commerce models, market share gains can matter, but investors also need to watch contribution margins and capital discipline.",
        ]
    return [
        "- Competitive-position evidence was limited in this run, so investors should compare the business against peers on growth, margins, and balance-sheet resilience.",
    ]


def _format_risk_bullets(
    fundamentals: Dict[str, Any],
    risk: Dict[str, Any],
    quote: Dict[str, Any],
) -> List[str]:
    debt_to_equity = fundamentals.get("debt_to_equity")
    current_ratio = fundamentals.get("current_ratio")
    pe_ratio = fundamentals.get("pe_ratio")
    quality_score = fundamentals.get("quality_score")
    beta = risk.get("beta")
    volatility = risk.get("annual_volatility_pct")
    sector = quote.get("sector") or fundamentals.get("sector") or "the sector"
    industry = quote.get("industry") or fundamentals.get("industry") or "the industry"

    financial_risk = (
        f"Financial risk: leverage/liquidity need monitoring because debt to equity is {_fmt_metric(debt_to_equity, '', 2)} and current ratio is {_fmt_metric(current_ratio, '', 2)}."
        if debt_to_equity is not None or current_ratio is not None
        else "Financial risk: full liquidity coverage was not available, so balance-sheet resilience should be verified separately."
    )
    industry_risk = f"Industry disruption risk: {industry} remains exposed to shifts in demand, competition, technology, and pricing behaviour."
    regulatory_risk = f"Regulatory risk: {sector} businesses can face compliance, disclosure, taxation, or policy changes that affect profitability or operating flexibility."
    execution_risk = (
        f"Execution risk: the modest quality score of {_fmt_metric(quality_score, '', 1)}/10 suggests operational consistency and competitive execution should not be taken for granted."
        if quality_score is not None and quality_score < 6
        else "Execution risk: growth and margins still need to hold up in live operating conditions, especially if the market is pricing in continued improvement."
    )
    valuation_risk = (
        f"Valuation risk: P/E at {_fmt_metric(pe_ratio, '', 2)} leaves less room for execution misses if earnings expectations soften."
        if pe_ratio is not None and pe_ratio > 30
        else "Valuation risk: even a reasonable multiple can compress if growth slows or sentiment turns risk-off."
    )
    market_risk = (
        f"Market risk: beta is {_fmt_metric(beta, '', 3)} and annual volatility is {_fmt_metric(volatility, '%', 2)}, so mark-to-market swings may be material."
        if beta is not None or volatility is not None
        else "Market risk: share-price volatility should still be expected even when business fundamentals appear stable."
    )
    return [financial_risk, industry_risk, regulatory_risk, execution_risk, valuation_risk, market_risk]


def _normalize_report_headings(text: str) -> str:
    normalized = re.sub(r"<[^>]+>", "", str(text or ""))
    normalized = normalized.replace("**", "")
    return normalized.lower()


def _build_report_payload(
    company_name: str,
    symbol: str,
    quote: Dict[str, Any],
    fundamentals: Dict[str, Any],
    technical: Dict[str, Any],
    risk: Dict[str, Any],
    pattern_detection: Dict[str, Any],
    news_sentiment: Dict[str, Any],
    web_research: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "company_name": company_name,
        "symbol": symbol,
        "quote": {
            "price": quote.get("price"),
            "currency": quote.get("currency"),
            "change_pct": quote.get("change_pct"),
            "market_cap": quote.get("market_cap"),
            "sector": quote.get("sector"),
            "industry": quote.get("industry"),
        },
        "fundamentals": {
            "quality_score": fundamentals.get("quality_score"),
            "quality_label": fundamentals.get("quality_label"),
            "moat_label": fundamentals.get("moat_label"),
            "roe_pct": fundamentals.get("roe_pct"),
            "operating_margin_pct": fundamentals.get("operating_margin_pct"),
            "gross_margin_pct": fundamentals.get("gross_margin_pct"),
            "net_margin_pct": fundamentals.get("net_margin_pct"),
            "ebitda_margin_pct": fundamentals.get("ebitda_margin_pct"),
            "fcf_yield_pct": fundamentals.get("fcf_yield_pct"),
            "revenue_growth_yoy_pct": fundamentals.get("revenue_growth_yoy_pct"),
            "earnings_growth_yoy_pct": fundamentals.get("earnings_growth_yoy_pct"),
            "pe_ratio": fundamentals.get("pe_ratio"),
            "pb_ratio": fundamentals.get("pb_ratio"),
            "peg_ratio": fundamentals.get("peg_ratio"),
            "ev_ebitda": fundamentals.get("ev_ebitda"),
            "debt_to_equity": fundamentals.get("debt_to_equity"),
            "current_ratio": fundamentals.get("current_ratio"),
            "quick_ratio": fundamentals.get("quick_ratio"),
        },
        "technical": {
            "trend": technical.get("trend"),
            "rsi": technical.get("rsi"),
            "overall_signal": technical.get("overall_signal") or technical.get("signal"),
        },
        "pattern_detection": {
            "support": pattern_detection.get("support"),
            "resistance": pattern_detection.get("resistance"),
            "patterns": pattern_detection.get("patterns"),
            "price_position": pattern_detection.get("price_position"),
        },
        "risk": {
            "risk_score": risk.get("risk_score"),
            "risk_level": risk.get("risk_level"),
            "annual_volatility_pct": risk.get("annual_volatility_pct"),
            "max_drawdown_pct": risk.get("max_drawdown_pct"),
            "beta": risk.get("beta"),
            "beta_60d": risk.get("beta_60d"),
            "beta_downside": risk.get("beta_downside"),
            "var_95_daily_pct": risk.get("var_95_daily_pct"),
            "var_95_hist_daily_pct": risk.get("var_95_hist_daily_pct"),
            "sharpe_ratio": risk.get("sharpe_ratio"),
            "sortino_ratio": risk.get("sortino_ratio"),
            "calmar_ratio": risk.get("calmar_ratio"),
        },
        "news_sentiment": {
            "overall_sentiment": news_sentiment.get("overall_sentiment"),
            "aggregate_score": news_sentiment.get("aggregate_score"),
            "positive_headlines": news_sentiment.get("positive_headlines"),
            "negative_headlines": news_sentiment.get("negative_headlines"),
            "news_items": news_sentiment.get("news_items", [])[:5],
        },
        "web_research": {
            "company_overview": web_research.get("company_overview"),
            "management_commentary": web_research.get("management_commentary"),
            "market_context": web_research.get("market_context"),
            "overall_sentiment": web_research.get("overall_sentiment"),
            "browser_agent_summary": web_research.get("browser_agent_summary"),
            "sources": web_research.get("sources", [])[:4],
        },
    }


def _run_analysis_stage(llm: Any, stage_name: str, stage_instruction: str, payload: Dict[str, Any]) -> str:
    response = llm.client.chat.completions.create(
        model=llm.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior equity research analyst. "
                    "Use only the supplied evidence. Interpret the data, explain what it means, and highlight investor implications. "
                    "Do not give buy, sell, or hold recommendations. Return concise markdown bullets only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Stage: {stage_name}\n"
                    f"Instruction: {stage_instruction}\n\n"
                    "When analysing metrics, follow this chain: interpret the metric, compare it to what investors would generally expect for the category, then explain the implication. "
                    "Be explicit when data is limited.\n\n"
                    f"DATA:\n{json.dumps(payload, indent=2, ensure_ascii=False)}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=320,
        timeout=40,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
    return re.sub(r"\n?```$", "", content).strip()


def _build_stage_analyses(llm: Any, payload: Dict[str, Any]) -> Dict[str, str]:
    stages = {
        "business_quality": (
            "Analyse the business model, moat, competitive position, and management commentary. Include where the company appears strong, where evidence is thin, and what investors should monitor."
        ),
        "financial_strength": (
            "Evaluate revenue growth, earnings growth, margins, returns, leverage, and liquidity. Focus on financial strength and balance-sheet resilience."
        ),
        "valuation_and_growth": (
            "Assess valuation using P/E, P/B, PEG, EV/EBITDA, and growth metrics. Explain whether expectations look modest, fair, or demanding and what could justify them."
        ),
        "risk_and_sentiment": (
            "Identify at least 5 concrete risks covering financial risk, industry disruption, regulatory risk, execution or customer concentration risk, valuation risk, and market risk. Also assess recent sentiment and technical context."
        ),
    }
    analyses: Dict[str, str] = {}
    for stage_name, instruction in stages.items():
        analyses[stage_name] = _run_analysis_stage(llm, stage_name, instruction, payload)
    return analyses


def _write_markdown_report(path: Path, content: str) -> Dict[str, Any]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content or "").strip() + "\n", encoding="utf-8")
        return {
            "status": "success",
            "file_path": str(path),
            "message": f"Markdown report written to {path.name}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Could not write markdown report: {exc}",
        }


def _resolve_output_paths(symbol: str, output_path: str = "") -> Dict[str, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"stock_analysis_{_slugify(symbol)}_{timestamp}"
    root_dir = get_your_data_dir("reports")

    if output_path:
        candidate = Path(output_path).expanduser()
        if candidate.suffix.lower() == ".pdf":
            pdf_path = candidate
            md_path = candidate.with_suffix(".md")
        elif candidate.suffix.lower() == ".md":
            md_path = candidate
            pdf_path = candidate.with_suffix(".pdf")
        else:
            pdf_path = candidate / f"{base_name}.pdf"
            md_path = candidate / f"{base_name}.md"
    else:
        pdf_path = root_dir / f"{base_name}.pdf"
        md_path = root_dir / f"{base_name}.md"

    return {
        "pdf": pdf_path,
        "markdown": md_path,
    }


def _build_fallback_report_content(
    company_name: str,
    symbol: str,
    quote: Dict[str, Any],
    fundamentals: Dict[str, Any],
    technical: Dict[str, Any],
    risk: Dict[str, Any],
    pattern_detection: Dict[str, Any],
    news_sentiment: Dict[str, Any],
    web_research: Dict[str, Any],
) -> str:
    price = quote.get("price")
    currency = quote.get("currency") or fundamentals.get("currency") or ""
    quality_score = fundamentals.get("quality_score")
    moat_label = fundamentals.get("moat_label") or "N/A"
    revenue_growth = fundamentals.get("revenue_growth_yoy_pct")
    earnings_growth = fundamentals.get("earnings_growth_yoy_pct")
    risk_level = risk.get("risk_level") or "N/A"
    risk_score = risk.get("risk_score")
    rsi_data = technical.get("rsi") or {}
    rsi_value = rsi_data.get("value") if isinstance(rsi_data, dict) else rsi_data
    rsi_signal = rsi_data.get("signal") if isinstance(rsi_data, dict) else None
    browser_summary = web_research.get("browser_agent_summary", "")
    quote_sector = quote.get("sector") or fundamentals.get("sector") or "N/A"
    quote_industry = quote.get("industry") or fundamentals.get("industry") or "N/A"
    market_cap = _fmt_market_cap(quote.get("market_cap"))
    current_ratio = fundamentals.get("current_ratio")
    quick_ratio = fundamentals.get("quick_ratio")
    debt_to_equity = fundamentals.get("debt_to_equity")
    roe_pct = fundamentals.get("roe_pct")
    gross_margin = fundamentals.get("gross_margin_pct")
    operating_margin = fundamentals.get("operating_margin_pct")
    net_margin = fundamentals.get("net_margin_pct")
    ebitda_margin = fundamentals.get("ebitda_margin_pct")
    fcf_yield = fundamentals.get("fcf_yield_pct")
    pe_ratio = fundamentals.get("pe_ratio")
    pb_ratio = fundamentals.get("pb_ratio")
    peg_ratio = fundamentals.get("peg_ratio")
    ev_ebitda = fundamentals.get("ev_ebitda")
    trend = technical.get("trend") or "N/A"
    overall_signal = technical.get("overall_signal") or technical.get("signal") or "N/A"
    moving_averages = technical.get("moving_averages") or {}
    macd = technical.get("macd") or {}
    support = pattern_detection.get("support")
    resistance = pattern_detection.get("resistance")
    patterns = pattern_detection.get("patterns") or []
    price_position = pattern_detection.get("price_position") or "N/A"
    news_items = news_sentiment.get("news_items") or []
    top_news = [
        item.get("title")
        for item in news_items[:3]
        if isinstance(item, dict) and item.get("title")
    ]

    qualitative_chunks = [
        web_research.get("company_overview", ""),
        web_research.get("management_commentary", ""),
        web_research.get("market_context", ""),
        browser_summary,
    ]
    business_model_points = _extract_keyword_sentences(
        qualitative_chunks,
        ["subscription", "saas", "license", "platform", "software", "bank", "client", "customers", "recurring", "maintenance", "digital"],
    )
    growth_driver_points = _extract_keyword_sentences(
        qualitative_chunks,
        ["growth", "pipeline", "deal", "expansion", "new product", "demand", "opportunity", "launch", "tailwind", "momentum"],
    )
    management_points = _dedupe_preserve(
        _collect_unique_sentences([web_research.get("management_commentary", ""), browser_summary], max_items=4)
    )
    institutional_points = _extract_keyword_sentences(
        qualitative_chunks,
        ["institution", "mutual fund", "fii", "dii", "shareholding", "promoter", "holding", "investor"],
    )
    governance_points = _extract_keyword_sentences(
        qualitative_chunks,
        ["promoter", "governance", "board", "regulatory", "penalty", "litigation", "insider", "management"],
    )
    competitive_points = _extract_keyword_sentences(
        qualitative_chunks,
        ["compet", "peer", "rival", "market share", "switching cost", "pricing power", "demand density", "retention"],
    )
    explicit_risk_points = _format_risk_bullets(fundamentals, risk, quote)

    positives = _dedupe_preserve([
        f"Quality score is {quality_score}/10 with moat assessment '{moat_label}'." if quality_score is not None and quality_score >= 7 else "",
        f"Revenue growth is {_fmt_metric(revenue_growth, '%', 1)} YoY." if revenue_growth is not None and revenue_growth > 8 else "",
        f"Earnings growth is {_fmt_metric(earnings_growth, '%', 1)} YoY." if earnings_growth is not None and earnings_growth > 8 else "",
        f"Gross margin is {_fmt_metric(gross_margin, '%', 1)} and operating margin is {_fmt_metric(operating_margin, '%', 1)}." if gross_margin is not None and operating_margin is not None and (gross_margin >= 35 or operating_margin >= 12) else "",
        *growth_driver_points,
    ])
    watchpoints = _dedupe_preserve([
        f"Quality score is only {quality_score}/10 with moat assessment '{moat_label}'." if quality_score is not None and quality_score < 5 else "",
        f"Revenue growth is {_fmt_metric(revenue_growth, '%', 1)} YoY." if revenue_growth is not None and revenue_growth < 0 else "",
        f"Earnings growth is {_fmt_metric(earnings_growth, '%', 1)} YoY." if earnings_growth is not None and earnings_growth < 0 else "",
        f"Risk level is {risk_level} with risk score {_fmt_metric(risk_score, '', 1)}/10." if risk_score is not None else f"Risk level is {risk_level}." if risk_level != "N/A" else "",
        f"Debt to equity is {_fmt_metric(debt_to_equity, '', 2)} and current ratio is {_fmt_metric(current_ratio, '', 2)}." if debt_to_equity is not None and (debt_to_equity > 1 or (current_ratio is not None and current_ratio < 1)) else "",
        web_research.get("market_context", ""),
        *explicit_risk_points,
    ])

    valuation_view: List[str] = []
    if pe_ratio is not None:
        if pe_ratio <= 20:
            valuation_view.append(f"P/E at {_fmt_metric(pe_ratio, '', 2)} is not obviously stretched on an absolute basis.")
        elif pe_ratio <= 35:
            valuation_view.append(f"P/E at {_fmt_metric(pe_ratio, '', 2)} suggests the market is paying for growth, so execution needs to stay strong.")
        else:
            valuation_view.append(f"P/E at {_fmt_metric(pe_ratio, '', 2)} points to a demanding valuation that leaves less room for disappointment.")
    if peg_ratio is not None:
        if peg_ratio <= 1.5:
            valuation_view.append(f"PEG ratio of {_fmt_metric(peg_ratio, '', 2)} looks reasonable relative to growth.")
        elif peg_ratio > 2.5:
            valuation_view.append(f"PEG ratio of {_fmt_metric(peg_ratio, '', 2)} suggests valuation is rich relative to current growth inputs.")
    if not valuation_view:
        valuation_view.append("Valuation coverage is partial in this run because not every market multiple was available from the source data.")

    summary_points = [
        _performance_assessment(company_name, fundamentals, risk, news_sentiment),
        f"Current price is {_fmt_metric(price, f' {currency}', 2)} and market capitalisation is {market_cap}." if price is not None else "",
        f"The business sits in {quote_sector} / {quote_industry}." if quote_sector != "N/A" or quote_industry != "N/A" else "",
    ]

    report_lines = [
        _styled_heading(f"{company_name} ({symbol}) Stock Analysis Report", level=1),
        "",
        _styled_heading("Executive Summary"),
        *[line for line in summary_points if line],
        "",
        _styled_heading("Company Overview"),
        f"- {_styled_label('Company:', 'info')} {company_name}",
        f"- {_styled_label('Symbol:', 'info')} {symbol}",
        f"- {_styled_label('Sector / Industry:', 'info')} {quote_sector} / {quote_industry}",
        f"- {_styled_label('Market Capitalization:', 'info')} {market_cap}",
        f"- {_styled_label('Current Price:', 'info')} {_fmt_metric(price, f' {currency}', 2)}",
        web_research.get("company_overview") or "- A detailed company overview could not be established from the public-web sources used in this run.",
        "",
        _styled_heading("Business Model Analysis"),
        *([f"- {item}" for item in business_model_points] if business_model_points else [_infer_business_model_fallback(quote_sector, quote_industry)]),
        "",
        _styled_heading("Industry Analysis"),
        f"- {_styled_label('Classification:', 'info')} The company is currently classified under {quote_sector} / {quote_industry} in market data.",
        f"- {_styled_label('Public-Web Context:', 'info')} {web_research.get('market_context') or 'limited context was gathered from the current browser run.'}",
        f"- {_styled_label('Additional Public-Web Insight:', 'info')} {browser_summary}" if browser_summary else f"- {_styled_label('Additional Public-Web Insight:', 'info')} A separate browser-derived industry note was not available in this run.",
        "",
        _styled_heading("Financial Analysis"),
        _styled_metric_line("Revenue Growth:", revenue_growth, tone="info", suffix="% YoY", decimals=1),
        _styled_metric_line("Earnings Growth:", earnings_growth, tone="info", suffix="% YoY", decimals=1),
        _styled_metric_line("ROE:", roe_pct, tone="info", suffix="%", decimals=1),
        _styled_metric_line("Gross Margin:", gross_margin, tone="info", suffix="%", decimals=1),
        _styled_metric_line("EBITDA Margin:", ebitda_margin, tone="info", suffix="%", decimals=1),
        _styled_metric_line("Operating Margin:", operating_margin, tone="info", suffix="%", decimals=1),
        _styled_metric_line("Net Margin:", net_margin, tone="info", suffix="%", decimals=1),
        _styled_metric_line("Free Cash Flow Yield:", fcf_yield, tone="info", suffix="%", decimals=2),
        f"- {_styled_label('Quality Score:', 'good' if quality_score is not None and quality_score >= 7 else 'risk' if quality_score is not None and quality_score < 5 else 'warn')} {_fmt_metric(quality_score, '', 1)}/10 ({fundamentals.get('quality_label') or 'N/A'})",
        "",
        _styled_heading("Balance Sheet Strength"),
        _styled_metric_line("Debt to Equity:", debt_to_equity, tone="info", suffix="", decimals=2, unavailable_note="Provider data did not expose leverage cleanly in this run; verify balance-sheet debt and lease liabilities from filings."),
        _styled_metric_line("Current Ratio:", current_ratio, tone="info", suffix="", decimals=2, unavailable_note="Short-term liquidity data was missing from the provider payload in this run."),
        _styled_metric_line("Quick Ratio:", quick_ratio, tone="info", suffix="", decimals=2, unavailable_note="Quick-ratio inputs were missing from the provider payload in this run."),
        (
            "- The balance sheet looks relatively controlled based on leverage and liquidity ratios."
            if debt_to_equity is not None and current_ratio is not None and debt_to_equity < 0.5 and current_ratio >= 1.0
            else "- Balance-sheet interpretation is constrained because one or more liquidity or leverage fields were unavailable or less comfortable."
        ),
        "",
        _styled_heading("Valuation Analysis"),
        _styled_metric_line("P/E:", pe_ratio, tone="info", suffix="", decimals=2),
        _styled_metric_line("P/B:", pb_ratio, tone="info", suffix="", decimals=2),
        _styled_metric_line("PEG:", peg_ratio, tone="info", suffix="", decimals=2),
        _styled_metric_line("EV/EBITDA:", ev_ebitda, tone="info", suffix="", decimals=2),
        *[f"- {item}" for item in valuation_view],
        "",
        _styled_heading("Growth Drivers"),
        *([f"- {item}" for item in growth_driver_points] if growth_driver_points else ["- Clear growth catalysts were not richly documented in the gathered web material, so growth must be inferred mainly from recent revenue and earnings trends."]),
        "",
        _styled_heading("Risk Analysis"),
        *([f"- {item}" for item in watchpoints] if watchpoints else ["- No single risk dominated the available dataset, but macro, execution, and valuation risk remain relevant in most equity cases."]),
        _styled_metric_line("Annual Volatility:", risk.get('annual_volatility_pct'), tone="risk", suffix="%", decimals=2),
        _styled_metric_line("Max Drawdown:", risk.get('max_drawdown_pct'), tone="risk", suffix="%", decimals=2),
        _styled_metric_line("Beta:", risk.get('beta'), tone="risk", suffix="", decimals=3),
        "",
        _styled_heading("Competitive Position"),
        *([f"- {item}" for item in competitive_points] if competitive_points else _infer_competitive_position_fallback(quote_sector, quote_industry)),
        "",
        _styled_heading("Management Quality"),
        *([f"- {item}" for item in management_points] if management_points else ["- Public management commentary was limited, so management-quality assessment remains partial."]),
        *([f"- {item}" for item in governance_points] if governance_points else ["- No major governance or insider-activity signal stood out from the gathered web material."]),
        "",
        _styled_heading("Technical Analysis"),
        f"- {_styled_label('Trend:', 'info')} {trend if trend != 'N/A' else 'N/A. Technical trend could not be inferred cleanly from the current payload.'}",
        f"- {_styled_label('Overall Signal:', 'info')} {overall_signal if overall_signal != 'N/A' else 'N/A. No consolidated technical signal was available in this run.'}",
        f"- {_styled_label('RSI:', 'info')} {_fmt_metric(rsi_value, '', 1)} ({rsi_signal or 'N/A'})",
        f"- {_styled_label('MACD Histogram:', 'info')} {_fmt_metric(macd.get('histogram'), '', 3)} ({macd.get('signal_text') or 'N/A'})",
        f"- {_styled_label('SMA 20 / 50 / 200:', 'info')} {_fmt_metric(moving_averages.get('sma20'), '', 2)} / {_fmt_metric(moving_averages.get('sma50'), '', 2)} / {_fmt_metric(moving_averages.get('sma200'), '', 2)}",
        f"- {_styled_label('Support / Resistance:', 'info')} {_fmt_metric(support, '', 2)} / {_fmt_metric(resistance, '', 2)}",
        f"- {_styled_label('Price Position:', 'info')} {price_position}",
        *([f"- {item}" for item in patterns] if patterns else ["- No major chart pattern stood out from the latest pattern scan."]),
        "",
        _styled_heading("Institutional Activity"),
        *([f"- {item}" for item in institutional_points] if institutional_points else ["- No dedicated FII, DII, or mutual-fund holdings dataset is wired into this run; only public-web mentions were checked and they were limited."]),
        "",
        _styled_heading("News & Sentiment Analysis"),
        f"- {_styled_label('Headline Sentiment:', 'good' if str(news_sentiment.get('overall_sentiment', 'N/A')) == 'Positive' else 'risk' if str(news_sentiment.get('overall_sentiment', 'N/A')) == 'Negative' else 'info')} {news_sentiment.get('overall_sentiment', 'N/A')}",
        f"- {_styled_label('Aggregate Sentiment Score:', 'info')} {_fmt_metric(news_sentiment.get('aggregate_score', news_sentiment.get('sentiment_score')), '', 2)}",
        f"- {_styled_label('Browser/Web Tone:', 'info')} {web_research.get('overall_sentiment', 'N/A')}",
        *([f"- {headline}" for headline in top_news] if top_news else ["- No recent headline list was available in the sentiment payload."]),
        "",
        _styled_heading("SWOT Analysis"),
        _styled_heading("Strengths", level=3),
        *([f"- {item}" for item in positives[:3]] if positives else ["- Financial quality and market positioning strengths were not strong enough to state with high confidence from the current data."]),
        _styled_heading("Weaknesses", level=3),
        *([f"- {item}" for item in watchpoints[:2]] if watchpoints else ["- Weakness signals were limited in the current run."]),
        _styled_heading("Opportunities", level=3),
        *([f"- {item}" for item in growth_driver_points[:2]] if growth_driver_points else ["- Opportunity set appears tied mainly to continued execution, demand conversion, and sector growth."]),
        _styled_heading("Threats", level=3),
        *([f"- {item}" for item in watchpoints[2:4]] if len(watchpoints) > 2 else ["- Threats include execution misses, valuation compression, and general market risk."]),
        "",
        _styled_heading("Final Investment Summary"),
        _styled_heading("Bull Case", level=3),
        *([f"- {item}" for item in positives[:3]] if positives else ["- Upside case depends on sustained execution and market support."]),
        _styled_heading("Bear Case", level=3),
        *([f"- {item}" for item in watchpoints[:3]] if watchpoints else ["- Downside case centers on execution, market sentiment, and valuation compression."]),
        _styled_heading("Portfolio Fit", level=3),
        (
            f"- {_styled_label('Portfolio Fit:', 'info')} The stock appears more aligned with investors seeking business and earnings growth than with pure income-oriented portfolios."
            if (revenue_growth or 0) > 8 and (fundamentals.get('dividend_yield_pct') or 0) < 2
            else f"- {_styled_label('Portfolio Fit:', 'info')} Portfolio fit is mixed and depends on whether the investor prioritises quality, valuation discipline, or income."
        ),
        _styled_heading("Overall View", level=3),
        f"- {_styled_label('Overall View:', 'info')} The company should be judged through business quality, management execution, financial resilience, and sentiment together rather than on price action alone.",
        f"- {_styled_label('Disclaimer:', 'muted')} This report is informational only and not financial advice.",
    ]
    return "\n".join(report_lines)


def _generate_report_markdown(
    company_name: str,
    symbol: str,
    quote: Dict[str, Any],
    fundamentals: Dict[str, Any],
    technical: Dict[str, Any],
    risk: Dict[str, Any],
    pattern_detection: Dict[str, Any],
    news_sentiment: Dict[str, Any],
    web_research: Dict[str, Any],
) -> str:
    fallback = _build_fallback_report_content(
        company_name,
        symbol,
        quote,
        fundamentals,
        technical,
        risk,
        pattern_detection,
        news_sentiment,
        web_research,
    )

    payload = _build_report_payload(
        company_name,
        symbol,
        quote,
        fundamentals,
        technical,
        risk,
        pattern_detection,
        news_sentiment,
        web_research,
    )

    try:
        llm = _load_report_llm()
        stage_analyses = _build_stage_analyses(llm, payload)
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior equity research analyst. Return markdown only. "
                        "Do not recommend buying, selling, or holding. Do not give price targets. "
                        "Use the supplied evidence only, reason like an analyst, and say when evidence is limited."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Write a comprehensive stock-analysis report with these exact sections:\n"
                        "## **Executive Summary**\n"
                        "## **Company Overview**\n"
                        "## **Business Model Analysis**\n"
                        "## **Industry Analysis**\n"
                        "## **Financial Analysis**\n"
                        "## **Balance Sheet Strength**\n"
                        "## **Valuation Analysis**\n"
                        "## **Growth Drivers**\n"
                        "## **Risk Analysis**\n"
                        "## **Competitive Position**\n"
                        "## **Management Quality**\n"
                        "## **Technical Analysis**\n"
                        "## **Institutional Activity**\n"
                        "## **News & Sentiment Analysis**\n"
                        "## **SWOT Analysis**\n"
                        "## **Final Investment Summary**\n\n"
                        "Use the supplied evidence only, be explicit when evidence is limited, and do not recommend buying, selling, or holding. "
                        "For every major section: interpret the data, explain what it means, and provide investor insight instead of merely describing metrics. "
                        "For valuation, compare current multiples against what investors would generally expect for the company's category and explain whether expectations look modest, fair, or demanding. "
                        "For risk analysis, explicitly cover financial risk, industry disruption risk, regulatory risk, execution or customer concentration risk, valuation risk, and market risk. "
                        "Use bold headings and subheadings. Keep color use minimal: only highlight the main risk markers and the main constructive markers, not every metric line. "
                        "In the final summary, use bull-case and bear-case framing plus a portfolio-fit note, not an investment recommendation. "
                        "End with a one-line disclaimer that the report is informational only and not financial advice.\n\n"
                        f"STAGE ANALYSES:\n{json.dumps(stage_analyses, indent=2, ensure_ascii=False)}\n\n"
                        f"DATA:\n{json.dumps(payload, indent=2, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1100,
            timeout=40,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()
        required_headings = (
            "## executive summary",
            "## company overview",
            "## business model analysis",
            "## industry analysis",
            "## financial analysis",
            "## balance sheet strength",
            "## valuation analysis",
            "## growth drivers",
            "## risk analysis",
            "## competitive position",
            "## management quality",
            "## technical analysis",
            "## institutional activity",
            "## news & sentiment analysis",
            "## swot analysis",
            "## final investment summary",
        )
        normalized_content = _normalize_report_headings(content)
        if all(heading in normalized_content for heading in required_headings):
            return content
    except Exception as exc:
        logger.warning("[stock-report] LLM synthesis failed, using fallback report: %s", exc)

    return fallback


def _build_all_tools() -> Dict[str, Any]:
    from src.agent.manifest.context_manifest import auto_save_stock_context, make_save_context_tool  # noqa: PLC0415
    from src.stock_market import fundamental_service as fs  # noqa: PLC0415
    from src.stock_market import stock_service as ss  # noqa: PLC0415

    def get_quote(symbol: str) -> dict:
        result = ss.get_quote(symbol)
        return auto_save_stock_context(result, symbol)

    def technical_analysis(symbol: str, period: str = "6mo") -> dict:
        result = ss.technical_analysis(symbol, period)
        return auto_save_stock_context(result, symbol)

    def fundamental_analysis_wrapped(symbol: str) -> dict:
        result = fs.fundamental_analysis(symbol)
        return auto_save_stock_context(result, symbol)

    def generate_full_report(
        query_or_symbol: str,
        output_path: str = "",
        send_to_email: str = "",
    ) -> dict:
        resolved_symbol = ss.resolve_ticker(query_or_symbol)
        quote = ss.get_quote(resolved_symbol)
        fundamentals = fs.fundamental_analysis(resolved_symbol)
        technical = ss.technical_analysis(resolved_symbol)
        risk = ss.risk_score(resolved_symbol)
        pattern_detection = ss.pattern_detection(resolved_symbol)
        news_sentiment = ss.sentiment_analysis(resolved_symbol)

        company_name = (
            quote.get("name")
            or fundamentals.get("name")
            or str(query_or_symbol or resolved_symbol).strip()
        )
        web_research = research_company_web(company_name, resolved_symbol)
        report_content = _generate_report_markdown(
            company_name,
            resolved_symbol,
            quote,
            fundamentals,
            technical,
            risk,
            pattern_detection,
            news_sentiment,
            web_research if web_research.get("status") == "success" else {},
        )

        report_title = f"{company_name} ({resolved_symbol}) Stock Analysis Report"
        output_paths = _resolve_output_paths(resolved_symbol, output_path)
        markdown_result = _write_markdown_report(output_paths["markdown"], report_content)
        pdf_result = _write_pdf_report(str(output_paths["pdf"]), report_title, report_content)
        if pdf_result.get("status") != "success":
            return {
                "status": "error",
                "message": pdf_result.get("message", "Could not write stock analysis PDF report."),
                "symbol": resolved_symbol,
            }

        email_result = None
        if str(send_to_email or "").strip():
            email_result = _send_report_email(
                send_to_email,
                subject=report_title,
                message=(
                    f"Attached is the stock analysis report for {company_name} ({resolved_symbol}).\n\n"
                    "This report is informational only and not financial advice."
                ),
                attachment_path=str(pdf_result.get("file_path") or pdf_result.get("path") or output_paths["pdf"]),
            )

        return {
            "status": "success",
            "symbol": resolved_symbol,
            "company_name": company_name,
            "report_title": report_title,
            "report_content": report_content,
            "file_path": str(pdf_result.get("file_path") or pdf_result.get("path") or output_paths["pdf"]),
            "pdf_path": str(pdf_result.get("file_path") or pdf_result.get("path") or output_paths["pdf"]),
            "markdown_path": str(markdown_result.get("file_path") or output_paths["markdown"]),
            "analysis_document_path": str(markdown_result.get("file_path") or output_paths["markdown"]),
            "web_research": web_research,
            "overall_sentiment": news_sentiment.get("overall_sentiment") or web_research.get("overall_sentiment"),
            "management_commentary": web_research.get("management_commentary"),
            "browser_agent_summary": web_research.get("browser_agent_summary"),
            "emailed_to": (email_result or {}).get("to") if isinstance(email_result, dict) else None,
            "message": f"Generated a full stock analysis report for {company_name} ({resolved_symbol}).",
        }

    def portfolio_analysis(symbols: List[str], period: str = "1y") -> dict:
        return ss.portfolio_analysis(symbols, period)

    def compare_stocks(symbols: List[str]) -> dict:
        return ss.compare_stocks(symbols)

    def portfolio_suggestions(symbols: List[str]) -> dict:
        return ss.portfolio_suggestions(symbols)

    return {
        "resolve_ticker": ss.resolve_ticker,
        "get_quote": get_quote,
        "get_historical_data": lambda symbol, period="1mo", interval="1d": ss.get_historical_data(symbol, period, interval),
        "technical_analysis": technical_analysis,
        "risk_score": lambda symbol, period="1y": ss.risk_score(symbol, period),
        "fundamental_analysis": fundamental_analysis_wrapped,
        "pattern_detection": lambda symbol, period="3mo": ss.pattern_detection(symbol, period),
        "sentiment_analysis": ss.sentiment_analysis,
        "research_company_web": research_company_web,
        "compare_stocks": compare_stocks,
        "portfolio_analysis": portfolio_analysis,
        "portfolio_suggestions": portfolio_suggestions,
        "market_overview": lambda indices=None: ss.market_overview(indices),
        "generate_full_report": generate_full_report,
        "save_context": make_save_context_tool("stock"),
    }


def _get_tool_docs_for_dag() -> str:
    """Return full tool docs for the DAG planner."""
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415

    docs = get_all_tool_docs("stock")
    if not docs:
        logger.error(
            "[stock-agent] skills.md returned no tools — check ui/stock_agent/skills.md exists. "
            "DAG planning will fail without tool docs."
        )
    return docs


def _get_tool_docs_for_react(user_query: str) -> str:
    """Return filtered tool docs for the ReAct engine."""
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415

    docs = load_tool_docs(
        "stock",
        user_query,
        always_include=["save_context", "research_company_web", "generate_full_report"],
    )
    if not docs:
        logger.error(
            "[stock-agent] skills.md returned no filtered docs for query=%r — check ui/stock_agent/skills.md",
            user_query[:60],
        )
    return docs


def _get_tool_map_for_react(
    user_query: str,
    all_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a FAISS-filtered tool map for the ReAct engine."""
    if all_tools is None:
        all_tools = _build_all_tools()
    try:
        from src.agent.core.skill_loader import select_tool_names  # noqa: PLC0415

        selected = select_tool_names(
            "stock",
            user_query,
            always_include=["save_context", "research_company_web", "generate_full_report"],
        )
        filtered = {name: all_tools[name] for name in selected if name in all_tools}
        if filtered:
            return filtered
    except Exception as exc:
        logger.warning("[tool-map] FAISS filtering failed (%s) — using full tool map", exc)
    return all_tools


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    del agent_id
    all_tools = _build_all_tools()
    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(user_query)

    try:
        return run_skill_dag(
            skill_name="stock",
            skill_context=skill_context,
            tool_map=all_tools,
            tool_docs=dag_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(user_query, all_tools),
            react_tool_docs=react_tool_docs,
        )
    except Exception as dag_exc:
        logger.warning("DAG path raised %s — falling back to ReAct", dag_exc)

    try:
        return run_skill_react(
            skill_name="stock",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(user_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Stock Market skill error: {exc}",
            "action": "react_response",
        }
