"""
Browser / Web skill orchestrator.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.workflows.skill_react_engine import run_skill_react

_TOOL_DOCS = """
browse_url(url, max_chars=3000) – Fetch and return readable text content from a URL.
search_web(query, num_results=5) – Search the web and return top result links + snippets.
extract_text(url, max_chars=5000) – Extract clean text from a web page (more thorough than browse_url).
get_page_links(url, internal_only=False) – List all hyperlinks on a page.
get_page_title(url) – Return just the <title> of a page.
get_page_metadata(url) – Return meta tags, Open Graph data, description etc.
find_on_page(url, search_term, context_chars=200) – Find occurrences of a term on a page.
extract_structured_data(url) – Extract JSON-LD / structured data from a page.
download_file_from_url(url, save_path) – Download a file from a URL to a local path.
summarize_page(url, max_words=200) – Return a short summary of a web page.
""".strip()

_SKILL_CONTEXT = """
You are the Browser / Web Research Skill Agent.
You can browse URLs and search the web to look up information, research topics, and gather data.

Typical flows:
- "Search for X" → search_web, then browse_url on the most relevant result for detail.
- "Summarise this article: <url>" → summarize_page or extract_text.
- "What links are on this page?" → get_page_links.

Always cite the source URL in your final_answer.
Keep responses concise — summarise rather than dumping raw page text.
""".strip()


def _get_tools() -> Dict[str, Any]:
    from src.browser import browser_service as bs  # noqa: PLC0415

    return {
        "browse_url": lambda url, max_chars=3000: bs.browse_url(url, max_chars),
        "search_web": lambda query, num_results=5: bs.search_web(query, num_results),
        "extract_text": lambda url, max_chars=5000: bs.extract_text(url, max_chars),
        "get_page_links": lambda url, internal_only=False: bs.get_page_links(url, internal_only),
        "get_page_title": lambda url: bs.get_page_title(url),
        "get_page_metadata": lambda url: bs.get_page_metadata(url),
        "find_on_page": lambda url, search_term, context_chars=200: bs.find_on_page(url, search_term, context_chars),
        "extract_structured_data": lambda url: bs.extract_structured_data(url),
        "download_file_from_url": lambda url, save_path: bs.download_file_from_url(url, save_path),
        "summarize_page": lambda url, max_words=200: bs.summarize_page(url, max_words),
    }


def execute_with_llm_orchestration(
    user_query: str,
    agent_id: Optional[str] = None,
    artifacts_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        return run_skill_react(
            skill_name="browser",
            skill_context=_SKILL_CONTEXT,
            tool_map=_get_tools(),
            tool_docs=_TOOL_DOCS,
            user_query=user_query,
            artifacts_out=artifacts_out,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"❌ Browser skill error: {exc}",
            "action": "react_response",
        }
