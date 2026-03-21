# Document Parser Skill — Tool Skills

## Category: Discovery

### check_liteparse_installation
- **signature**: `check_liteparse_installation()`
- **description**: Check whether the LiteParse CLI is available on this machine and return install guidance when it is missing. Use when the user asks to parse PDFs, OCR invoices, extract tables from documents, or generate screenshots from pages and you need to verify the local LiteParse dependency first.
- **tags**: liteparse, installation, setup, dependency, parse pdf, ocr, document parser, local cli, availability

### list_directory
- **signature**: `list_directory(path, show_hidden=False, limit=200)`
- **description**: List the contents of a local folder. Use when the user wants to browse a document folder before parsing or confirm which files are present.
- **tags**: folder, browse, list documents, directory, inspect folder

### search_by_name
- **signature**: `search_by_name(query, directory="~", recursive=True, limit=50)`
- **description**: Find a document or folder by name. Use when the user refers to a file like `invoice.pdf`, `contract.docx`, or a folder of reports.
- **tags**: find document, search file, invoice, contract, report, locate pdf, locate docx

### search_by_extension
- **signature**: `search_by_extension(ext, directory="~", recursive=True, limit=100)`
- **description**: Find documents by extension. Use when the user asks for all PDFs, DOCX files, spreadsheets, slides, or images in a folder before batch parsing.
- **tags**: pdf, docx, xlsx, pptx, image, extension, batch parse folder

## Category: Parsing

### parse_document_spatially
- **signature**: `parse_document_spatially(path, output_format="json", output_path="", target_pages="", max_pages=1000, dpi=150, ocr_enabled=True, ocr_language="en", precise_bounding_boxes=True, preserve_small_text=False, timeout_seconds=600)`
- **description**: Parse a local document with LiteParse while preserving layout and spatial structure. Use when the user wants to summarize a contract, extract invoice fields, inspect a table, convert a document to structured JSON/text, or OCR a scanned PDF. Outputs go under `your_data/reports/document_parser/` by default.
- **tags**: liteparse, parse pdf, parse docx, parse xlsx, parse pptx, spatial text, bounding boxes, ocr, invoice to json, contract summary, table extraction

### batch_parse_documents
- **signature**: `batch_parse_documents(input_dir, output_dir="", output_format="json", recursive=True, extension="", max_pages=1000, dpi=150, ocr_enabled=True, ocr_language="en", timeout_seconds=1200)`
- **description**: Parse an entire folder of documents with LiteParse. Use when the user wants to process a batch of PDFs, invoices, reports, or mixed Office/image files into text or JSON outputs.
- **tags**: batch parse, parse folder, all pdfs, multiple documents, ingestion, bulk ocr, document pipeline

### screenshot_document_pages
- **signature**: `screenshot_document_pages(path, output_dir="", target_pages="", dpi=200, image_format="png", timeout_seconds=900)`
- **description**: Generate page screenshots from a document with LiteParse. Use when the user wants visual reasoning over a chart, diagram, highlighted cell, signature area, or a specific page layout that text extraction alone may miss.
- **tags**: screenshot pdf, page image, chart inspection, diagram, visual reasoning, highlighted cell, document page

## Category: Output Inspection

### read_text_file
- **signature**: `read_text_file(path, max_lines=200)`
- **description**: Read a text output file. Use to inspect LiteParse text exports or generated notes before summarizing them to the user.
- **tags**: read text output, inspect parse output, text export

### read_json_file
- **signature**: `read_json_file(path)`
- **description**: Read a JSON output file. Use to inspect LiteParse JSON exports, page structures, or extracted metadata before summarizing.
- **tags**: read json output, inspect parsed json, structured extraction

### deliver_file
- **signature**: `deliver_file(path)`
- **description**: Deliver a generated parse result or screenshot bundle back to the user for download in the current chat. Only call this after a parse or screenshot tool has created the file.
- **tags**: send file, download parsed output, deliver json, deliver screenshots