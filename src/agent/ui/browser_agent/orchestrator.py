"""
Browser Agent

Gives an OctaMind agent the ability to browse the web, search for information,
extract page text, inspect links, download files, and summarise content.

No credentials or API keys required — all tools use urllib from the standard
library; BeautifulSoup4 + requests are used automatically when installed.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger("browser_agent")

# ── Tool descriptions shown to the LLM ────────────────────────────────────────
_BROWSER_TOOLS_DESCRIPTION = """
1. **browse_url**(url: str, max_chars: int = 3000)
   - Fetch a web page and return its main readable content.
   - Use for: "open https://...", "go to ...", "read the page at ...", "what does X website say about Y"

2. **search_web**(query: str, num_results: int = 5)
   - Search the web using DuckDuckGo and return top result links + snippets.
   - Use for: "search for ...", "find information about ...", "look up ...", "Google ..."

3. **extract_text**(url: str, max_chars: int = 5000)
   - Extract a long clean plain-text version of a page — ideal for reading articles.
   - Use for: "read the full article at ...", "extract text from ...", "get content from ..."

4. **get_page_links**(url: str, internal_only: bool = False)
   - List all hyperlinks found on a page.
   - Use for: "what links are on ...", "list links from ...", "find all URLs on this page"

5. **get_page_title**(url: str)
   - Return just the page title tag.
   - Use for: "what is the title of ...", "page title for ..."

6. **get_page_metadata**(url: str)
   - Extract meta tags: description, og:title, keywords, author, canonical URL.
   - Use for: "meta data for ...", "page description of ...", "what are the keywords on ..."

7. **find_on_page**(url: str, search_term: str, context_chars: int = 200)
   - Find occurrences of a phrase on a page (like Ctrl+F).
   - Use for: "find X on this page", "does the page mention Y?", "search for Z on ..."

8. **extract_structured_data**(url: str)
   - Extract HTML tables and lists from a page.
   - Use for: "get tables from ...", "extract lists from ...", "structured data from ..."

9. **download_file_from_url**(url: str, save_path: str)
   - Download a file from a direct URL to a local path.
   - Use for: "download ... to ...", "save file from ...", "download PDF/CSV/image from ..."

10. **summarize_page**(url: str, max_words: int = 200)
    - Return a concise extractive summary of a web page.
    - Use for: "summarise ...", "give me a brief overview of ...", "what is this page about?"
"""


# ── Tool dispatcher ────────────────────────────────────────────────────────────

def _dispatch_tool(tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from src.browser import (
        browse_url, search_web, extract_text, get_page_links,
        get_page_title, get_page_metadata, find_on_page,
        extract_structured_data, download_file_from_url, summarize_page,
    )
    _MAP = {
        "browse_url":             lambda p: browse_url(**p),
        "search_web":             lambda p: search_web(**p),
        "extract_text":           lambda p: extract_text(**p),
        "get_page_links":         lambda p: get_page_links(**p),
        "get_page_title":         lambda p: get_page_title(**p),
        "get_page_metadata":      lambda p: get_page_metadata(**p),
        "find_on_page":           lambda p: find_on_page(**p),
        "extract_structured_data":lambda p: extract_structured_data(**p),
        "download_file_from_url": lambda p: download_file_from_url(**p),
        "summarize_page":         lambda p: summarize_page(**p),
    }
    fn = _MAP.get(tool)
    if fn is None:
        return {"status": "error", "message": f"Unknown browser tool: {tool}"}
    return fn(params)


# ── Main entry point ───────────────────────────────────────────────────────────

def execute_with_llm_orchestration(
    user_query: str,
    agent_id: str | None = None,
    artifacts_out: dict | None = None,
) -> Dict[str, Any]:
    """
    Execute a natural-language web browsing command.

    Steps:
      1. LLM selects the right tool + params (temperature=0.1).
      2. Tool is dispatched and executed.
      3. LLM composes a friendly, readable response (temperature=0.4).
    """
    from src.agent.llm.llm_parser import get_llm_client

    llm = get_llm_client()

    selection_prompt = f"""You are a web browsing assistant. Select ONE tool to handle the user's request.

Available tools:
{_BROWSER_TOOLS_DESCRIPTION}

User request: "{user_query}"

Respond with ONLY valid JSON:
{{
  "tool": "<tool_name>",
  "params": {{<key>: <value>, ...}},
  "reasoning": "<one sentence>"
}}

Rules:
- For open/visit/read a URL: use browse_url
- For find/search/look up information: use search_web
- For full article text: use extract_text
- For "search for X then read first result": use search_web (agent will follow up)
- For downloading a file: use download_file_from_url (save_path is required)
- Omit optional params with default values unless the user explicitly specified them
- URLs must include http:// or https://; add https:// if missing
"""

    _llm_available = True
    try:
        sel_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a precise web tool selector. Return ONLY valid JSON."},
                {"role": "user",   "content": selection_prompt},
            ],
            temperature=0.1,
            max_tokens=400,
            timeout=30,
        )
        sel_text  = sel_response.choices[0].message.content.strip()
        clean     = re.sub(r"^```[a-z]*\n?", "", sel_text)
        clean     = re.sub(r"\n?```$", "", clean).strip()
        selection = json.loads(clean)
        tool      = selection.get("tool", "search_web")
        params    = selection.get("params", {})
        logger.info("[browser_agent] Tool selected: %s params=%s", tool, params)
    except Exception as exc:
        logger.warning("[browser_agent] Tool selection failed: %s — fallback to search_web", exc)
        _llm_available = False
        tool   = "search_web"
        params = {"query": user_query}

    raw = _dispatch_tool(tool, params)

    # Attach to artifacts if provided
    if artifacts_out is not None:
        artifacts_out["browser_result"] = raw

    compose_prompt = f"""The user asked: "{user_query}"

The web browsing tool "{tool}" returned:
{json.dumps(raw, indent=2, default=str)[:4000]}

Write a clear, helpful response:
- Present web content in a readable, well-structured way
- For search results: list results with titles and URLs as markdown links
- For page content: extract and present the key information
- For tables: render as markdown tables if possible
- For errors: explain what went wrong and suggest alternatives
- Use **bold** for key terms, titles, and important data
- Do NOT copy raw JSON — synthesise the information naturally
- Keep the response focused on what the user actually asked
"""

    try:
        compose_response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a helpful web research assistant. Be clear and informative."},
                {"role": "user",   "content": compose_prompt},
            ],
            temperature=0.4,
            max_tokens=1500,
            timeout=30,
        )
        final_message = compose_response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[browser_agent] Response composition failed: %s", exc)
        _llm_available = False
        # Build a human-readable fallback without LLM
        if raw.get("status") == "error":
            final_message = raw.get("message", "The browser tool encountered an error.")
        elif tool == "search_web":
            results = raw.get("results", [])
            if results:
                lines = [f"Found {len(results)} result(s) for '{params.get('query', user_query)}':"]
                for r in results[:5]:
                    lines.append(f"- {r.get('title', 'No title')} — {r.get('url', '')}")
                final_message = "\n".join(lines)
            else:
                final_message = f"No search results found for '{params.get('query', user_query)}'. Please try a different query."
        elif "content" in raw:
            final_message = raw["content"][:800]
        elif "summary" in raw:
            final_message = raw["summary"]
        elif "title" in raw:
            final_message = f"Page title: {raw['title']}"
        else:
            final_message = f"Operation '{tool}' completed successfully."

    return {
        "status":        raw.get("status", "success"),
        "message":       final_message,
        "action":        "react_response",
        "raw":           raw,
        "tool_used":     tool,
        "llm_available": _llm_available,
    }
