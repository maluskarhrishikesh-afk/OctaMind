# Browser Agent — Setup Guide

This guide explains how to set up, configure, and test the Browser Agent in Octa Bot.

---

## What the Browser Agent Does

The Browser Agent gives any Octa Bot Personal Assistant the ability to interact with the web:

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

The Browser Agent works with **zero extra dependencies** using Python's built-in `urllib.request`. When `beautifulsoup4` and `requests` are installed (recommended), parsing is significantly richer.

```bash
# Recommended — already installed by setup process
pip install beautifulsoup4 requests
```

Check installation:
```bash
python -c "import bs4; print('bs4 OK:', bs4.__version__)"
python -c "import requests; print('requests OK:', requests.__version__)"
```

### No API Keys or Credentials Required

The Browser Agent requires no API keys, OAuth tokens, or account setup. It works entirely using HTTP requests.

---

## Installation

1. **Packages are already installed** if you ran `pip install yfinance beautifulsoup4 requests` during project setup.

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

1. Open the Octa Bot dashboard (`python start.py` or `streamlit run src/agent/ui/dashboard/app.py`)
2. Click **"+ Add Agent / Skill"**
3. In the skill catalogue, locate **?? Web Browser**
4. Toggle it on for an existing Personal Assistant, or create a new one with it pre-selected
5. Save — the PA now routes web-related queries to the Browser Agent

---

## Example Queries

Once added to a PA, the Browser Agent understands natural language:

```
"Search for the latest news about artificial intelligence"
"Browse https://python.org and tell me what's new"
"What is the title of https://github.com?"
"Find all links on https://example.com"
"Download https://example.com/file.pdf to data/downloads/file.pdf"
"Summarise the article at [URL]"
"Find where it mentions 'pricing' on https://company.com/products"
"Get the metadata for https://openai.com"
```

---

## Architecture

```
User query
    ¦
    ?
browser_agent/orchestrator.py
    execute_with_llm_orchestration(user_query, agent_id, artifacts_out)
    ¦
    +- Step 1: LLM tool selector (temperature=0.1, max_tokens=400)
    ¦          ? chooses one of 10 tools + params
    ¦
    +- Step 2: _dispatch_tool(tool, params)
    ¦          ? calls src/browser/browser_service.py
    ¦          ? uses urllib.request (stdlib) + optional bs4
    ¦
    +- Step 3: LLM response composer (temperature=0.4, max_tokens=1500)
               ? returns human-readable message
```

**Service layer:** `src/browser/browser_service.py`  
**Package init:** `src/browser/__init__.py`  
**Orchestrator:** `src/agent/ui/browser_agent/orchestrator.py`

---

## Running the Tests

### Unit tests (no LLM, no network):
```bash
python -m pytest tests/agent/test_browser_service.py -v
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
| JavaScript-rendered pages | Pages requiring JS execution (SPAs) will return sparse content — the agent uses HTTP-only, not a real browser |
| Rate limiting / CAPTCHAs | Some sites block automated requests; the agent will return an HTTP error with an explanation |
| Login-required pages | No session/cookie/login support; public pages only |
| Very large pages | Content is truncated at `max_chars` (default 3000 for `browse_url`) |
| File download paths | `download_file_from_url` requires a valid local path — create directories beforehand or specify an existing folder |

---

## Troubleshooting

**`bs4` not found / using fallback parser:**
```bash
pip install beautifulsoup4
```

**HTTP 403 Forbidden:**
Some sites block automated user agents. The Browser Agent already sends a realistic browser User-Agent string, but some sites require additional headers or JS execution. Try a different URL or use `search_web` to find a mirror.

**Connection timeout:**
Default timeout is 15 seconds. For slow sites this may not be enough — the error message will say "timed out".

**No search results:**
DuckDuckGo HTML search is used. If DuckDuckGo is unavailable in your region, use `browse_url` directly with a known URL instead.

---

## Dependency Summary

| Package | Version | Required | Purpose |
|---------|---------|----------|---------|
| `urllib.request` | stdlib | ? always | HTTP fetching |
| `beautifulsoup4` | =4.12 | ? recommended | Rich HTML parsing |
| `requests` | =2.31 | ? recommended | Richer HTTP client |
| Playwright / Selenium | — | ? not used | Full browser (not needed) |
