# Browser Agent — Tool Skills

## Category: Search & Discover

### search_web
- **signature**: `search_web(query, num_results=5)`
- **description**: Search the public web and return the most relevant result links with titles and snippets. Use when the user asks to search online, look something up on the internet, find recent information, or discover relevant pages before opening one in detail.
- **tags**: search, web search, internet search, online lookup, latest information, browse web, find pages, duckduckgo

### browse_url
- **signature**: `browse_url(url, max_chars=3000)`
- **description**: Fetch a page and return readable text content from the URL. Use when the user already has a URL and wants to know what the page says without dumping raw HTML.
- **tags**: browse url, open website, read page, inspect website, visit page, url content

### summarize_page
- **signature**: `summarize_page(url, max_words=200)`
- **description**: Produce a concise extractive summary of a page. Use when the user wants a quick summary of an article, company page, blog post, press release, or any specific URL.
- **tags**: summarize url, article summary, page summary, quick gist, web summary

---

## Category: Read & Inspect

### extract_text
- **signature**: `extract_text(url, max_chars=5000)`
- **description**: Extract clean plain text from a web page. Use when the user needs more detailed readable text than a short browse snippet, such as for reports, analysis, or downstream summarization.
- **tags**: extract text, article text, clean text, readable content, page body

### get_page_title
- **signature**: `get_page_title(url)`
- **description**: Return the page title only. Use when the user asks for the title of a page or wants a quick check of what a URL points to.
- **tags**: title, page title, website title, what is this page

### get_page_metadata
- **signature**: `get_page_metadata(url)`
- **description**: Extract metadata like title, description, canonical URL, and Open Graph tags. Use when the user needs page metadata, article description, or social-card information.
- **tags**: metadata, description, og tags, canonical, meta tags, page info

### find_on_page
- **signature**: `find_on_page(url, search_term, context_chars=200)`
- **description**: Find occurrences of a phrase on a page with surrounding context. Use when the user asks whether a page mentions a person, company, keyword, section, or topic.
- **tags**: find on page, search term, keyword on page, mention check, context search

### get_page_links
- **signature**: `get_page_links(url, internal_only=False)`
- **description**: List hyperlinks found on a page. Use when the user wants all links from a page, internal navigation links, or candidate next pages to inspect.
- **tags**: links, hyperlinks, internal links, outbound links, page links

### extract_structured_data
- **signature**: `extract_structured_data(url)`
- **description**: Extract tables and list-like structured content from a page. Use when the user needs page tables, bullet lists, or structured facts rather than freeform prose.
- **tags**: structured data, tables, lists, extract table, extract bullets, web data

---

## Category: Download

### download_file_from_url
- **signature**: `download_file_from_url(url, save_path)`
- **description**: Download a remote file to a local path. Use when the user wants a file from the web saved locally for later use.
- **tags**: download, save file, url download, fetch file, local file