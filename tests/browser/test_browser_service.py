"""Unit tests for src/browser/browser_service.py

Tests service layer logic that does NOT require LLM or network calls.
Network-dependent tests use monkeypatching.
"""
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.browser.browser_service import (
    _strip_html_basic,
    _extract_title_from_html,
    _extract_clean_text,
)


# ── _strip_html_basic ──────────────────────────────────────────────────────────

class TestStripHtmlBasic:
    def test_removes_script_tags(self):
        html = "<html><script>alert('x')</script><p>Hello</p></html>"
        result = _strip_html_basic(html)
        assert "alert" not in result
        assert "Hello" in result

    def test_removes_style_tags(self):
        html = "<html><style>body{color:red}</style><p>World</p></html>"
        result = _strip_html_basic(html)
        assert "color" not in result
        assert "World" in result

    def test_strips_all_tags(self):
        html = "<div><span>foo</span><a href='#'>bar</a></div>"
        result = _strip_html_basic(html)
        assert "<" not in result
        assert "foo" in result
        assert "bar" in result

    def test_decodes_html_entities(self):
        html = "<p>AT&amp;T &lt;rocks&gt; &quot;indeed&quot;</p>"
        result = _strip_html_basic(html)
        assert "AT&T" in result
        assert "<rocks>" in result
        assert '"indeed"' in result

    def test_collapses_whitespace(self):
        html = "<p>  Hello   World  </p>"
        result = _strip_html_basic(html)
        assert "  " not in result  # double space collapsed
        assert "Hello World" in result

    def test_empty_input(self):
        result = _strip_html_basic("")
        assert result == ""

    def test_plain_text_unchanged(self):
        result = _strip_html_basic("plain text here")
        assert "plain text here" in result


# ── _extract_title_from_html ───────────────────────────────────────────────────

class TestExtractTitleFromHtml:
    def test_extracts_title(self):
        html = "<html><head><title>My Page Title</title></head><body></body></html>"
        assert _extract_title_from_html(html) == "My Page Title"

    def test_title_with_entities(self):
        html = "<title>Tom &amp; Jerry</title>"
        assert _extract_title_from_html(html) == "Tom & Jerry"

    def test_no_title_returns_empty(self):
        html = "<html><body><p>No title here</p></body></html>"
        assert _extract_title_from_html(html) == ""

    def test_case_insensitive(self):
        html = "<HTML><HEAD><TITLE>Caps Title</TITLE></HEAD></HTML>"
        assert _extract_title_from_html(html) == "Caps Title"

    def test_strips_whitespace(self):
        html = "<title>  Padded Title  </title>"
        assert _extract_title_from_html(html) == "Padded Title"


# ── browse_url error handling ──────────────────────────────────────────────────

class TestBrowseUrlErrors:
    def test_bad_scheme_gets_https_prefix(self, monkeypatch):
        """browse_url should prepend https:// if scheme missing."""
        import urllib.error
        from src.browser import browser_service as bs

        called_urls = []

        def fake_fetch(url, timeout=15):
            called_urls.append(url)
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.browse_url("example.com")
        assert called_urls[0].startswith("https://")
        assert result["status"] == "error"
        assert "404" in result["message"]

    def test_network_error_returns_error_dict(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            raise ConnectionError("network failure")

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.browse_url("https://example.com")
        assert result["status"] == "error"
        assert "message" in result

    def test_successful_browse_structure(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            return "<html><head><title>Test Page</title></head><body><p>Hello world content here.</p></body></html>"

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.browse_url("https://example.com")
        assert result["status"] == "success"
        assert result["title"] == "Test Page"
        assert "Hello world" in result["content"]
        assert result["url"] == "https://example.com"


# ── extract_text ───────────────────────────────────────────────────────────────

class TestExtractText:
    def test_returns_text_key(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            return "<html><body><p>Article text here. More content follows.</p></body></html>"

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.extract_text("https://example.com")
        assert result["status"] == "success"
        assert "text" in result
        assert "word_count" in result
        assert result["word_count"] > 0

    def test_truncation_flag(self, monkeypatch):
        from src.browser import browser_service as bs
        long_text = "word " * 2000
        html = f"<html><body><p>{long_text}</p></body></html>"

        def fake_fetch(url, timeout=15):
            return html

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.extract_text("https://example.com", max_chars=100)
        assert result["truncated"] is True
        assert len(result["text"]) <= 100


# ── find_on_page ───────────────────────────────────────────────────────────────

class TestFindOnPage:
    def test_finds_occurrences(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            return "<html><body><p>Python is great. I love Python. Python forever.</p></body></html>"

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.find_on_page("https://example.com", "Python")
        assert result["status"] == "success"
        assert result["count"] == 3
        assert len(result["matches"]) == 3

    def test_case_insensitive_search(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            return "<html><body><p>PYTHON python Python</p></body></html>"

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.find_on_page("https://example.com", "python")
        assert result["count"] == 3

    def test_no_match_returns_empty_list(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            return "<html><body><p>Hello World</p></body></html>"

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.find_on_page("https://example.com", "notfound")
        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["matches"] == []


# ── get_page_links ─────────────────────────────────────────────────────────────

class TestGetPageLinks:
    def test_extracts_absolute_links(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            return """<html><body>
                <a href="https://python.org">Python</a>
                <a href="https://github.com">GitHub</a>
            </body></html>"""

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.get_page_links("https://example.com")
        assert result["status"] == "success"
        hrefs = [lnk["href"] for lnk in result["links"]]
        assert "https://python.org" in hrefs
        assert "https://github.com" in hrefs

    def test_deduplicates_links(self, monkeypatch):
        from src.browser import browser_service as bs

        def fake_fetch(url, timeout=15):
            return """<html><body>
                <a href="https://python.org">Link 1</a>
                <a href="https://python.org">Link 2</a>
            </body></html>"""

        monkeypatch.setattr(bs, "_fetch_html", fake_fetch)
        result = bs.get_page_links("https://example.com")
        hrefs = [lnk["href"] for lnk in result["links"]]
        assert hrefs.count("https://python.org") == 1
