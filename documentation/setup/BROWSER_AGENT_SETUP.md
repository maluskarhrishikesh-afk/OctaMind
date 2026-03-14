# Browser Agent Setup Guide

This guide explains how to set up, configure, and test the Browser Agent in OctaMind.

---

## What the Browser Agent Does

The Browser Agent gives any OctaMind Personal Assistant the ability to search the web, inspect URLs, extract readable content, and download files from public pages.

| Tool | What it does |
|------|-------------|
| **browse_url** | Fetch the main readable content from any web page |
| **search_web** | Search via DuckDuckGo and return top results with snippets |
| **extract_text** | Clean, long plain-text extraction from articles/pages |
| **get_page_links** | List all hyperlinks found on a page |
| **get_page_title** | Return the `<title>` tag of a page |
| **get_page_metadata** | Extract meta description, og:tags, keywords, canonical URL |
| **find_on_page** | Find phrase occurrences on a page (Ctrl+F equivalent) |
| **extract_structured_data** | Pull HTML tables and lists from a page |
| **download_file_from_url** | Download a file from a direct URL to a local path |
| **summarize_page** | Concise extractive summary of any web page |

---

## Requirements

### Python Packages

The Browser Agent works with Python's built-in HTTP stack. When `beautifulsoup4` and `requests` are installed, parsing and extraction are more reliable.

```bash
# Recommended
pip install beautifulsoup4 requests
```

Check installation:
```bash
python -c "import bs4; print('bs4 OK:', bs4.__version__)"
python -c "import requests; print('requests OK:', requests.__version__)"
```

### No API Keys or Credentials Required

The Browser Agent requires no API keys, OAuth tokens, or browser automation setup. It works entirely through HTTP requests.

---

## Installation

1. Install the optional parsing packages if they are not already present.

2. **Verify the agent is registered:**

```bash
python -c "
from src.agent.workflows.agent_registry import AGENT_REGISTRY
print('browser' in AGENT_REGISTRY)  # Should print: True
"
```

3. **Test the service layer directly:**

```bash
python -c "
from src.browser import search_web, browse_url
r = search_web('Python programming', num_results=3)
print(r['status'], '-', r['count'], 'results')
"
```

---

## Enabling the Browser Skill in the UI

1. Open the OctaMind dashboard with `python start.py`
2. Create a Personal Assistant or open an existing one
3. In the assistant configuration panel, enable **Web Browser** under **Skills**
4. Save the changes
5. Open the assistant workspace - web-related queries will now route to the Browser skill

---

## Example Queries

Once added to a PA, the Browser Agent understands natural language:

```
"Search for the latest news about artificial intelligence"
"Browse https://python.org and tell me what's new"
"What is the title of https://github.com?"
"Find all links on https://example.com"
"Download https://example.com/file.pdf to your_data/downloads/file.pdf"
"Summarise the article at [URL]"
"Find where it mentions 'pricing' on https://company.com/products"
"Get the metadata for https://openai.com"
```

---

## Architecture

```
User query
    |
browser_agent/orchestrator.py
    execute_with_llm_orchestration(user_query, agent_id, artifacts_out)
    |
    +- Loads tool docs from src/agent/ui/browser_agent/skills.md
    +- Uses direct shortcuts for some high-confidence queries before the LLM planner
    +- Dispatches to src/browser/browser_service.py
    +- Composes a human-readable answer with source-aware output
```

**Service layer:** `src/browser/browser_service.py`  
**Package init:** `src/browser/__init__.py`  
**Orchestrator:** `src/agent/ui/browser_agent/orchestrator.py`  
**Tool docs:** `src/agent/ui/browser_agent/skills.md`

---

## Running the Tests

### Unit tests (no LLM, no network):
```bash
python -m pytest tests/browser/test_browser_service.py -v
```

### Orchestrator regression tests:
```bash
python -m pytest tests/agent/test_browser_stock_orchestrators.py -k browser -v
```

### E2E test (requires LLM and network):
```bash
python -m pytest tests/agent/e2e_browser_agent.py -v -m e2e
```

### Run both:
```bash
python -m pytest tests/ -k "browser" -v
```

---

## Known Limitations

| Limitation | Notes |
|-----------|-------|
| JavaScript-rendered pages | Pages requiring JS execution (SPAs) will return sparse content - the agent is HTTP-only, not a headless browser |
| Rate limiting / CAPTCHAs | Some sites block automated requests; the agent will return an HTTP error with an explanation |
| Login-required pages | No session/cookie/login support; public pages only |
| Very large pages | Content is truncated at `max_chars` (default 3000 for `browse_url`) |
| File download paths | `download_file_from_url` requires a valid local path - create directories beforehand or specify an existing folder |

---

## Troubleshooting

**`bs4` not found / using fallback parser:**
```bash
pip install beautifulsoup4
```

**HTTP 403 Forbidden:**
Some sites block automated user agents. The Browser Agent already sends a realistic browser User-Agent string, but some sites require additional headers or JS execution. Try a different URL or use `search_web` to find a mirror.

**Connection timeout:**
Default timeout is 15 seconds. For slow sites this may not be enough � the error message will say "timed out".

**No search results:**
DuckDuckGo HTML search is used. If DuckDuckGo is unavailable in your region, use `browse_url` directly with a known URL instead.

---

## Dependency Summary

| Package | Version | Required | Purpose |
|---------|---------|----------|---------|
| `urllib.request` | stdlib | ? always | HTTP fetching |
| `beautifulsoup4` | =4.12 | ? recommended | Rich HTML parsing |
| `requests` | =2.31 | ? recommended | Richer HTTP client |
| Playwright / Selenium | � | ? not used | Full browser (not needed) |
