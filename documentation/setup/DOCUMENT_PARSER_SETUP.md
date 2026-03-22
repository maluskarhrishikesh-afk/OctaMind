# Document Parser Skill - Setup and Testing Guide

## Overview

The Document Parser skill adds local document ingestion powered by LiteParse. It is designed for PDFs first, but can also handle Office files and images when the required local converters are installed.

Primary use cases:

- spatial text extraction from PDFs and scanned files
- OCR-backed parsing for invoices, statements, and reports
- page screenshots for charts, diagrams, signatures, and layout-sensitive review
- batch parsing of a folder into JSON or text outputs

This skill is local-first. Source documents stay on the machine.

---

## Quick Setup

### 1. Install LiteParse

Install Node.js first, then install the LiteParse CLI globally:

```bash
npm i -g @llamaindex/liteparse
```

This exposes the `lit` command used by OctaMind.

### 2. Optional: Office document support

LiteParse can convert Office documents to PDF before parsing.

On Windows, install LibreOffice:

```bash
choco install libreoffice-fresh
```

Then ensure the LibreOffice program directory is on `PATH`, typically:

```text
C:\Program Files\LibreOffice\program
```

### 3. Optional: image conversion support

If you want image-to-document parsing for formats like PNG, JPG, TIFF, or WebP, install ImageMagick:

```bash
choco install imagemagick.app
```

### 4. Optional: offline OCR setup

LiteParse uses Tesseract.js by default. On first use it may download language data. For offline environments, pre-download the `.traineddata` files and set:

```text
TESSDATA_PREFIX=C:\path\to\tessdata
```

### 5. Enable the Document Parser skill on a Personal Assistant

1. Open the Agent Hub.
2. Create a Personal Assistant or open an existing one.
3. Open the assistant configuration panel.
4. Enable **Document Parser** under **Skills**.
5. Save the changes.

Generated outputs default to `your_data/reports/document_parser/`, which is already ignored by Git.

For JSON parses, the skill now writes two artifacts by default:

- the raw LiteParse output, such as `report_liteparse.json`
- a companion structured summary, such as `report_structured.json`

The structured summary is designed for downstream automation. It includes normalized key fields, candidate labeled values, document-type hints, and heuristic tamper-consistency checks.

---

## What The Skill Exposes

- `check_liteparse_installation()`
- `parse_document_spatially(...)`
- `extract_document_key_fields(...)`
- `batch_parse_documents(...)`
- `screenshot_document_pages(...)`

The skill also includes supporting tools for finding documents, reading generated outputs, and delivering result files back into chat.

---

## Testing Checklist

### Verify installation

Ask:

```text
Check whether LiteParse is installed
```

Expected result:

- If installed: the assistant confirms the command is available.
- If missing: the assistant returns install guidance.

### Parse a single PDF

```text
Parse C:/Users/<YourName>/Documents/report.pdf into JSON
```

Expected result:

- a JSON output file created under `your_data/reports/document_parser/`
- a companion structured JSON with extracted key fields and tamper heuristics
- a preview of the parsed content or keys

### Parse a DOCX file

```text
Parse C:/Users/<YourName>/Documents/contract.docx into text
```

Expected result:

- successful parse if LibreOffice is installed and on `PATH`
- otherwise a clear failure pointing to LibreOffice setup

### Generate screenshots

```text
Generate screenshots for pages 1-2 of C:/Users/<YourName>/Documents/invoice.pdf
```

Expected result:

- page images created under `your_data/reports/document_parser/<name>_screenshots/`

### Batch parse a folder

```text
Batch parse all PDFs in C:/Users/<YourName>/Documents/Statements into JSON
```

Expected result:

- one output file per matching document under a batch output directory

---

## Operational Notes

- Keep large parsing jobs under `your_data/` and do not commit generated outputs.
- Prefer JSON output when the next step is extraction or structured post-processing.
- Prefer the companion structured JSON when another tool or workflow needs normalized fields instead of raw page text.
- Prefer text output when the next step is summarization.
- Use screenshots when the answer depends on charts, diagrams, handwriting, signatures, or cell color.
- Tamper detection here is heuristic only. For authenticity-sensitive workflows, combine these checks with digital signatures, PDF metadata inspection, or issuer-side verification.

---

## Troubleshooting

### `LiteParse is not available`

Install the CLI:

```bash
npm i -g @llamaindex/liteparse
```

### Office files fail to parse

Install LibreOffice and ensure its CLI folder is on `PATH`.

### Images fail to parse

Install ImageMagick.

### OCR is slow or inaccurate

- try restricting `target_pages`
- lower or raise `dpi` depending on the source quality
- configure a custom OCR server if you need higher throughput later