"""Browser / Web skill orchestrator."""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any, Dict, Optional

from src.agent.telemetry import log_fallback_to_react, log_fast_path_hit
from src.agent.workflows.skill_dag_engine import run_skill_dag
from src.agent.workflows.skill_react_engine import run_skill_react

logger = logging.getLogger("browser.orchestrator")

_PRICE_SITE_CANDIDATES = (
    {"name": "Amazon", "domain": "amazon.com"},
    {"name": "Best Buy", "domain": "bestbuy.com"},
    {"name": "Walmart", "domain": "walmart.com"},
    {"name": "Target", "domain": "target.com"},
    {"name": "eBay", "domain": "ebay.com"},
)


def _return_fast_path_result(result: Dict[str, Any]) -> Dict[str, Any]:
    fast_path = str(result.get("_fast_path", "") or result.get("action", "unknown"))
    log_fast_path_hit("browser", fast_path)
    return result


def _strip_injected_context_blocks(user_query: str) -> str:
    text = str(user_query or "")
    marker_match = re.search(r"\n##\s+(?:session state|active context)\b", text, flags=re.IGNORECASE)
    if marker_match:
        text = text[:marker_match.start()]
    return text.strip()


def _is_price_comparison_query(user_query: str) -> bool:
    lowered = _strip_injected_context_blocks(user_query).lower()
    shopping_terms = (
        "cheapest",
        "price comparison",
        "compare price",
        "compare the latest price",
        "lowest price",
        "various websites",
        "where is it cheapest",
    )
    product_terms = ("price", "buy", "shopping", "website", "websites")
    return any(term in lowered for term in shopping_terms) or (
        any(term in lowered for term in product_terms) and any(term in lowered for term in ("compare", "cheapest", "lowest"))
    )


def _extract_product_query(user_query: str) -> str:
    product = _strip_injected_context_blocks(user_query)
    patterns = (
        r"^can you\s+",
        r"^please\s+",
        r"compare\s+the\s+latest\s+price\s+of\s+",
        r"compare\s+the\s+price\s+of\s+",
        r"compare\s+",
        r"latest\s+price\s+of\s+",
        r"price\s+of\s+",
        r"on\s+various\s+websites.*$",
        r"and\s+tell\s+me\s+where\s+it\s+is\s+the\s+cheapest.*$",
        r"where\s+is\s+it\s+the\s+cheapest.*$",
        r"where\s+is\s+it\s+cheapest.*$",
        r"\?$",
    )
    for pattern in patterns:
        product = re.sub(pattern, "", product, flags=re.IGNORECASE).strip()
    return re.sub(r"\s+", " ", product).strip(" .")


def _extract_price_candidates(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not text:
        return candidates

    pattern = re.compile(
        r"(?P<currency>\$|USD|Rs\.?|INR|₹|EUR|€|GBP|£)\s?(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        raw_currency = match.group("currency")
        amount_text = match.group("amount").replace(",", "")
        try:
            amount_value = float(amount_text)
        except ValueError:
            continue
        if amount_value <= 0:
            continue
        currency = raw_currency.upper()
        if raw_currency == "$":
            currency = "USD"
        elif raw_currency in {"₹", "RS", "RS.", "INR"}:
            currency = "INR"
        elif raw_currency in {"€", "EUR"}:
            currency = "EUR"
        elif raw_currency in {"£", "GBP"}:
            currency = "GBP"
        candidates.append(
            {
                "currency": currency,
                "amount": amount_value,
                "display": f"{raw_currency} {match.group('amount')}",
            }
        )
    return candidates


def _pick_best_price(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    snippet = str(result.get("snippet", "") or "")
    title = str(result.get("title", "") or "")
    text = f"{title} {snippet}"
    prices = _extract_price_candidates(text)
    if not prices:
        return None
    preferred = sorted(prices, key=lambda item: item["amount"])
    return preferred[0]


def _is_relevant_listing(product: str, title: str) -> bool:
    product_l = f" {product.lower()} "
    title_l = f" {title.lower()} "
    required_tokens = [token for token in re.findall(r"[a-z0-9]+", product_l) if len(token) > 1]
    overlap = sum(1 for token in required_tokens if token in title_l)
    if overlap < max(2, min(4, len(required_tokens))):
        return False
    if " pro max " not in product_l and " max " in title_l:
        return False
    return True


def _extract_bing_shopping_comparisons(product: str) -> list[dict[str, Any]]:
    from src.browser import browser_service as bs  # noqa: PLC0415

    shopping_url = f"https://www.bing.com/shop?q={urllib.parse.quote_plus(product)}"
    page = bs.browse_url(shopping_url, max_chars=15000)
    if page.get("status") != "success":
        return []

    text = str(page.get("content", "") or "")
    entry_pattern = re.compile(
        r'(?P<title>(?:Apple|iPhone|Open Box|New Condition|Refurbished|Renewed|Unlocked|New)[^₹$]{5,100}?)\s+'
        r'(?P<currency>₹|\$)\s?(?P<price>[0-9,]+(?:\.[0-9]{2})?)\s+[A-Z]\s+'
        r'(?P<merchant>[A-Za-z][A-Za-z .&-]{2,40}?)(?=\s+(?:Apple|iPhone|Open Box|New Condition|Refurbished|Renewed|Unlocked|New|Oops!|$))'
    )

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for match in entry_pattern.finditer(text):
        title = match.group("title").replace("�", "").strip()
        merchant = re.sub(r"\s+", " ", match.group("merchant")).strip()
        merchant = re.sub(
            r"\s+(?:Appi|Apple|iPhone|Open Box|New Condition|Refurbished|Renewed|Unlocked|New)\b.*$",
            "",
            merchant,
            flags=re.IGNORECASE,
        ).strip(" -")
        if not _is_relevant_listing(product, title):
            continue
        price_text = match.group("price").replace(",", "")
        try:
            amount = float(price_text)
        except ValueError:
            continue
        currency_symbol = match.group("currency")
        currency = "INR" if currency_symbol == "₹" else "USD"
        minimum_amount = 1000 if currency == "INR" else 50
        if amount < minimum_amount:
            continue

        key = (merchant.lower(), currency)
        candidate = {
            "site": merchant,
            "domain": "bing-shopping",
            "url": shopping_url,
            "currency": currency,
            "amount": amount,
            "display": f"{currency_symbol} {match.group('price')}",
            "title": title,
            "source": "bing_shopping",
        }
        existing = grouped.get(key)
        if existing is None or candidate["amount"] < existing["amount"]:
            grouped[key] = candidate

    return sorted(grouped.values(), key=lambda item: (item["currency"], item["amount"]))


def _format_price_comparison_message(product: str, comparisons: list[dict[str, Any]], notes: list[str]) -> str:
    if not comparisons:
        note_text = " ".join(notes).strip()
        return (
            f"I searched major retail sites for {product}, but I could not extract enough current comparable prices to name a cheapest seller. "
            f"{note_text}".strip()
        )

    by_currency: dict[str, list[dict[str, Any]]] = {}
    for item in comparisons:
        by_currency.setdefault(item["currency"], []).append(item)

    largest_group = max(by_currency.values(), key=len)
    sorted_group = sorted(largest_group, key=lambda item: item["amount"])
    cheapest = sorted_group[0]
    lines = [
        f"I compared current visible prices for {product} across retailer search results.",
        f"Cheapest comparable listing found: {cheapest['site']} at {cheapest['display']}.",
        "",
        "Price checks:",
    ]
    for item in sorted_group:
        lines.append(f"- {item['site']}: {item['display']} ({item['url']})")
    other_currencies = [currency for currency in by_currency if currency != cheapest["currency"]]
    if other_currencies:
        lines.append("")
        lines.append("I found additional listings in other currencies, but I did not rank them directly against the cheapest result.")
    if notes:
        lines.append("")
        lines.extend(f"- {note}" for note in notes[:3])
    return "\n".join(lines)


def _handle_price_comparison_query(user_query: str) -> Dict[str, Any]:
    from src.browser import browser_service as bs  # noqa: PLC0415

    product = _extract_product_query(user_query)
    comparisons = _extract_bing_shopping_comparisons(product)
    notes: list[str] = []

    if comparisons:
        message = _format_price_comparison_message(product or "the requested product", comparisons, ["Source used: Bing Shopping merchant listings."])
        return {
            "status": "success",
            "message": message,
            "action": "react_response",
            "_fast_path": "price_comparison",
            "tool_used": "browse_url",
            "raw": {
                "product": product,
                "comparisons": comparisons,
                "notes": ["Source used: Bing Shopping merchant listings."],
            },
            "llm_available": True,
        }

    for site in _PRICE_SITE_CANDIDATES:
        query = f'site:{site["domain"]} "{product}" price'
        search_result = bs.search_web(query, num_results=3)
        if search_result.get("status") != "success":
            notes.append(f"Search failed for {site['name']}.")
            continue

        site_match = None
        for result in search_result.get("results", []):
            url = str(result.get("url", "") or "")
            if site["domain"] not in url:
                continue
            picked = _pick_best_price(result)
            if not picked:
                continue
            site_match = {
                "site": site["name"],
                "domain": site["domain"],
                "url": url,
                **picked,
            }
            break

        if site_match:
            comparisons.append(site_match)
        else:
            notes.append(f"I could not read a reliable visible price from {site['name']} search results.")

    message = _format_price_comparison_message(product or "the requested product", comparisons, notes)
    return {
        "status": "success" if comparisons else "error",
        "message": message,
        "action": "react_response",
        "_fast_path": "price_comparison",
        "tool_used": "search_web",
        "raw": {
            "product": product,
            "comparisons": comparisons,
            "notes": notes,
        },
        "llm_available": True,
    }


def _load_skill_context() -> str:
    """Load the browser skill context from skill_context.md."""
    from pathlib import Path as _Path
    return (_Path(__file__).parent / "skill_context.md").read_text(encoding="utf-8").strip()


def _build_all_tools() -> Dict[str, Any]:
    from src.browser import browser_service as bs  # noqa: PLC0415

    return {
        "search_web": bs.search_web,
        "browse_url": bs.browse_url,
        "summarize_page": bs.summarize_page,
        "extract_text": bs.extract_text,
        "get_page_title": bs.get_page_title,
        "get_page_metadata": bs.get_page_metadata,
        "find_on_page": bs.find_on_page,
        "get_page_links": bs.get_page_links,
        "extract_structured_data": bs.extract_structured_data,
        "download_file_from_url": bs.download_file_from_url,
    }


def _get_tool_docs_for_dag() -> str:
    """Return full tool docs for the DAG planner."""
    from src.agent.core.skill_loader import get_all_tool_docs  # noqa: PLC0415

    docs = get_all_tool_docs("browser")
    if not docs:
        logger.error(
            "[browser-agent] skills.md returned no tools — check ui/browser_agent/skills.md exists. "
            "DAG planning will fail without tool docs."
        )
    return docs


def _get_tool_docs_for_react(user_query: str) -> str:
    """Return filtered tool docs for the ReAct engine."""
    from src.agent.core.skill_loader import load_tool_docs  # noqa: PLC0415

    docs = load_tool_docs(
        "browser",
        user_query,
        always_include=["search_web", "browse_url", "summarize_page"],
    )
    if not docs:
        logger.error(
            "[browser-agent] skills.md returned no filtered docs for query=%r — check ui/browser_agent/skills.md",
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
            "browser",
            user_query,
            always_include=["search_web", "browse_url", "summarize_page"],
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
    sanitized_query = _strip_injected_context_blocks(user_query)
    if _is_price_comparison_query(sanitized_query):
        return _return_fast_path_result(_handle_price_comparison_query(sanitized_query))

    all_tools = _build_all_tools()
    skill_context = _load_skill_context()
    dag_tool_docs = _get_tool_docs_for_dag()
    react_tool_docs = _get_tool_docs_for_react(sanitized_query)

    try:
        return run_skill_dag(
            skill_name="browser",
            skill_context=skill_context,
            tool_map=all_tools,
            tool_docs=dag_tool_docs,
            user_query=sanitized_query,
            artifacts_out=artifacts_out,
            react_tool_map=_get_tool_map_for_react(sanitized_query, all_tools),
            react_tool_docs=react_tool_docs,
        )
    except Exception as dag_exc:
        logger.warning("DAG path raised %s — falling back to ReAct", dag_exc)
        log_fallback_to_react("browser", "browser_orchestrator_exception")

    try:
        return run_skill_react(
            skill_name="browser",
            skill_context=skill_context,
            tool_map=_get_tool_map_for_react(sanitized_query, all_tools),
            tool_docs=react_tool_docs,
            user_query=sanitized_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Browser skill error: {exc}",
            "action": "react_response",
        }
