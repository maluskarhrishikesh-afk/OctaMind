"""Browser service package — web browsing tools for Octa Bot."""
from src.browser.browser_service import (
    browse_url,
    search_web,
    extract_text,
    get_page_links,
    get_page_title,
    get_page_metadata,
    find_on_page,
    extract_structured_data,
    download_file_from_url,
    summarize_page,
)

__all__ = [
    "browse_url",
    "search_web",
    "extract_text",
    "get_page_links",
    "get_page_title",
    "get_page_metadata",
    "find_on_page",
    "extract_structured_data",
    "download_file_from_url",
    "summarize_page",
]
