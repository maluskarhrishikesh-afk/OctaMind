"""
Browser Service — headless web access for Octa Bot.

All tools use urllib from the standard library as the primary backend,
with optional BeautifulSoup4 + requests for richer parsing when installed.
No API keys or credentials required.

Exposed tools:
  browse_url            fetch main content from any URL
  search_web            DuckDuckGo instant-answers / HTML-scrape results
  extract_text          clean text extraction from a URL
  get_page_links        list all hyperlinks found on a page
  get_page_title        return title tag of a page
  get_page_metadata     title, description, og:tags
  find_on_page          find occurrences of a phrase on a page
  extract_structured_data  extract tables and lists from a page
  download_file_from_url   download a file to a local path
  summarize_page        return a concise AI-ready snippet of page content
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger("browser_service")

# ── Internal helpers ───────────────────────────────────────────────────────────

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def _fetch_raw(url: str, timeout: int = 15) -> bytes:
    """Return raw bytes from URL using urllib."""
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    # Decompress gzip transparently
    try:
        import gzip
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
    except Exception:
        pass
    return data


def _fetch_html(url: str, timeout: int = 15) -> str:
    """Return decoded HTML string from URL."""
    raw = _fetch_raw(url, timeout=timeout)
    # Try to detect encoding from meta or default to utf-8
    try:
        raw.decode("utf-8")
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


# ── BeautifulSoup helpers (optional) ──────────────────────────────────────────

def _bs_available() -> bool:
    try:
        import bs4  # noqa: F401
        return True
    except ImportError:
        return False


def _soup(html_str: str):
    """Return a BeautifulSoup object or None if unavailable."""
    if not _bs_available():
        return None
    from bs4 import BeautifulSoup
    return BeautifulSoup(html_str, "html.parser")


def _strip_html_basic(html_str: str) -> str:
    """Fallback text extraction without BeautifulSoup."""
    # Remove scripts and styles
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_str, flags=re.DOTALL | re.IGNORECASE)
    # Remove all other tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_clean_text(html_str: str) -> str:
    """Extract readable text from HTML."""
    soup = _soup(html_str)
    if soup:
        # Remove script/style tags
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        return re.sub(r"\s+", " ", text).strip()
    return _strip_html_basic(html_str)


def _extract_title_from_html(html_str: str) -> str:
    soup = _soup(html_str)
    if soup:
        t = soup.find("title")
        if t and t.string:
            return t.string.strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", html_str, re.IGNORECASE | re.DOTALL)
    return html.unescape(m.group(1).strip()) if m else ""


# ── Tool implementations ───────────────────────────────────────────────────────

def browse_url(url: str, max_chars: int = 3000) -> Dict[str, Any]:
    """
    Fetch a web page and return its main readable content.

    Args:
        url:       Full URL including scheme (https://).
        max_chars: Truncate text to this many characters (default 3000).

    Returns dict with status, title, url, content, char_count.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        title = _extract_title_from_html(html_str)
        text = _extract_clean_text(html_str)
        snippet = text[:max_chars]
        return {
            "status":     "success",
            "url":        url,
            "title":      title,
            "content":    snippet,
            "char_count": len(text),
            "truncated":  len(text) > max_chars,
        }
    except urllib.error.HTTPError as exc:
        return {"status": "error", "message": f"HTTP {exc.code}: {exc.reason}", "url": url}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def search_web(query: str, num_results: int = 5) -> Dict[str, Any]:
    """
    Search the web using DuckDuckGo HTML search and return top results.

    Args:
        query:       Search query string.
        num_results: How many results to return (default 5, max 10).

    Returns dict with status, query, results (list of {title, url, snippet}).
    """
    num_results = min(max(1, num_results), 10)
    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded}"

    try:
        html_str = _fetch_html(search_url)
        results: List[Dict[str, str]] = []

        soup = _soup(html_str)
        if soup:
            for link in soup.select("a.result__a"):
                href = link.get("href", "")
                title = link.get_text(strip=True)
                # DuckDuckGo proxies links — extract real URL
                parsed = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(parsed.query)
                real_url = qs.get("uddg", [href])[0]
                # Get snippet from sibling
                parent = link.find_parent(class_=re.compile(r"result"))
                snippet_tag = parent.find(class_=re.compile(r"result__snippet")) if parent else None
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                if real_url and title:
                    results.append({"title": title, "url": real_url, "snippet": snippet})
                if len(results) >= num_results:
                    break
        else:
            # Regex fallback
            for m in re.finditer(
                r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                html_str, re.DOTALL
            ):
                href, raw_title = m.group(1), _strip_html_basic(m.group(2))
                parsed = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(parsed.query)
                real_url = qs.get("uddg", [href])[0]
                results.append({"title": raw_title, "url": real_url, "snippet": ""})
                if len(results) >= num_results:
                    break

        return {"status": "success", "query": query, "results": results, "count": len(results)}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "query": query}


def extract_text(url: str, max_chars: int = 5000) -> Dict[str, Any]:
    """
    Extract clean plain text from a URL — ideal for reading articles.

    Args:
        url:       Target URL.
        max_chars: Maximum characters to return (default 5000).

    Returns dict with status, url, text, word_count.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        text = _extract_clean_text(html_str)
        snippet = text[:max_chars]
        word_count = len(snippet.split())
        return {
            "status":     "success",
            "url":        url,
            "text":       snippet,
            "word_count": word_count,
            "truncated":  len(text) > max_chars,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def get_page_links(url: str, internal_only: bool = False) -> Dict[str, Any]:
    """
    Extract all hyperlinks from a page.

    Args:
        url:           Target URL.
        internal_only: If True, only return links on the same domain.

    Returns dict with status, url, links (list of {text, href}).
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        base_domain = urllib.parse.urlparse(url).netloc
        links: List[Dict[str, str]] = []

        soup = _soup(html_str)
        if soup:
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True)
                # Make absolute
                href = urllib.parse.urljoin(url, href)
                if internal_only and urllib.parse.urlparse(href).netloc != base_domain:
                    continue
                if href.startswith("http"):
                    links.append({"text": text[:120], "href": href})
        else:
            for m in re.finditer(r'href=["\']([^"\']+)["\']', html_str):
                href = urllib.parse.urljoin(url, m.group(1))
                if href.startswith("http"):
                    if internal_only and urllib.parse.urlparse(href).netloc != base_domain:
                        continue
                    links.append({"text": "", "href": href})

        # Deduplicate by href
        seen: set = set()
        unique_links = []
        for lnk in links:
            if lnk["href"] not in seen:
                seen.add(lnk["href"])
                unique_links.append(lnk)

        return {
            "status": "success",
            "url":    url,
            "links":  unique_links[:100],
            "count":  len(unique_links),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def get_page_title(url: str) -> Dict[str, Any]:
    """
    Return just the <title> of a page without fetching full content.

    Args:
        url: Target URL.

    Returns dict with status, url, title.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        title = _extract_title_from_html(html_str)
        return {"status": "success", "url": url, "title": title}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def get_page_metadata(url: str) -> Dict[str, Any]:
    """
    Extract meta tags: title, description, og:title, og:description, og:image,
    keywords, author, and canonical URL.

    Args:
        url: Target URL.

    Returns dict with status, url, and a metadata sub-dict.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        meta: Dict[str, str] = {}
        meta["title"] = _extract_title_from_html(html_str)

        soup = _soup(html_str)
        if soup:
            for tag in soup.find_all("meta"):
                name = (tag.get("name") or tag.get("property") or "").lower()
                content = tag.get("content", "")
                if not name or not content:
                    continue
                if name in ("description", "keywords", "author"):
                    meta[name] = content
                elif name in ("og:title", "og:description", "og:image", "og:url",
                              "twitter:title", "twitter:description"):
                    meta[name] = content
            canonical = soup.find("link", rel="canonical")
            if canonical and canonical.get("href"):
                meta["canonical"] = canonical["href"]
        else:
            for m in re.finditer(
                r'<meta\s+(?:name|property)=["\']([^"\']+)["\']\s+content=["\']([^"\']*)["\']',
                html_str, re.IGNORECASE
            ):
                meta[m.group(1).lower()] = m.group(2)

        return {"status": "success", "url": url, "metadata": meta}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def find_on_page(url: str, search_term: str, context_chars: int = 200) -> Dict[str, Any]:
    """
    Find all occurrences of search_term in a page's text (case-insensitive).

    Args:
        url:          Target URL.
        search_term:  Phrase to search for.
        context_chars: Characters of surrounding context per match (default 200).

    Returns dict with status, url, search_term, matches (list of snippet strings), count.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        text = _extract_clean_text(html_str)
        lower_text = text.lower()
        lower_term = search_term.lower()
        matches: List[str] = []
        start = 0
        while True:
            idx = lower_text.find(lower_term, start)
            if idx == -1:
                break
            ctx_start = max(0, idx - context_chars // 2)
            ctx_end = min(len(text), idx + len(search_term) + context_chars // 2)
            snippet = ("..." if ctx_start > 0 else "") + text[ctx_start:ctx_end] + ("..." if ctx_end < len(text) else "")
            matches.append(snippet)
            start = idx + len(search_term)
            if len(matches) >= 10:
                break

        return {
            "status":      "success",
            "url":         url,
            "search_term": search_term,
            "matches":     matches,
            "count":       len(matches),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def extract_structured_data(url: str) -> Dict[str, Any]:
    """
    Extract tables and lists from a page.

    Args:
        url: Target URL.

    Returns dict with status, url, tables (list of list-of-rows), lists (list of list-of-items).
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        tables: List[List[List[str]]] = []
        lists: List[List[str]] = []

        soup = _soup(html_str)
        if soup:
            for table in soup.find_all("table")[:10]:
                rows: List[List[str]] = []
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if cells:
                        rows.append(cells)
                if rows:
                    tables.append(rows)

            for ul in soup.find_all(["ul", "ol"])[:10]:
                items = [li.get_text(strip=True) for li in ul.find_all("li")]
                if items:
                    lists.append(items)
        else:
            # Regex extraction for plain HTML
            for m in re.finditer(r"<table[^>]*>(.*?)</table>", html_str, re.DOTALL | re.IGNORECASE):
                rows = []
                for row in re.finditer(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.DOTALL | re.IGNORECASE):
                    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row.group(1), re.DOTALL | re.IGNORECASE)
                    cells_clean = [_strip_html_basic(c) for c in cells]
                    if cells_clean:
                        rows.append(cells_clean)
                if rows:
                    tables.append(rows)

        return {
            "status": "success",
            "url":    url,
            "tables": tables[:5],
            "lists":  lists[:5],
            "table_count": len(tables),
            "list_count":  len(lists),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def download_file_from_url(url: str, save_path: str) -> Dict[str, Any]:
    """
    Download a file from URL to a local path.

    Args:
        url:       Direct URL to file.
        save_path: Absolute or relative local path to save to.

    Returns dict with status, url, save_path, file_size_bytes.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)) or ".", exist_ok=True)
        raw = _fetch_raw(url)
        with open(save_path, "wb") as f:
            f.write(raw)
        return {
            "status":          "success",
            "url":             url,
            "save_path":       os.path.abspath(save_path),
            "file_size_bytes": len(raw),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}


def summarize_page(url: str, max_words: int = 200) -> Dict[str, Any]:
    """
    Return a concise extractive summary of a web page (suitable for passing to LLM).

    Args:
        url:       Target URL.
        max_words: Approximate target word count (default 200).

    Returns dict with status, url, title, summary, word_count.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        html_str = _fetch_html(url)
        title = _extract_title_from_html(html_str)
        text = _extract_clean_text(html_str)

        # Extractive approach: split into sentences and take the first N words
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary_parts: List[str] = []
        word_count = 0
        for sent in sentences:
            words = sent.split()
            if word_count + len(words) > max_words:
                break
            summary_parts.append(sent)
            word_count += len(words)

        summary = " ".join(summary_parts)

        return {
            "status":     "success",
            "url":        url,
            "title":      title,
            "summary":    summary,
            "word_count": word_count,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "url": url}
