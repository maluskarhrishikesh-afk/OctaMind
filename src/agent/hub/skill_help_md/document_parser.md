---
key: document_parser
title: Document Parser
aliases:
  - document parser
  - document parsing
  - liteparse
  - parse pdf
  - pdf parser
---
**Document Parser Skill**

The Document Parser skill helps you read complex local documents while keeping layout intact.

**What it helps with**
- Parsing PDFs, DOCX files, spreadsheets, slide decks, and images with preserved structure
- Extracting text or JSON outputs from documents using LiteParse
- Producing a second normalized JSON with extracted key fields and heuristic tamper-risk checks
- Generating page screenshots for charts, diagrams, or visually important sections
- Batch-processing folders of documents into structured outputs

**Try asking things like**
- Parse this invoice PDF into JSON
- Parse this payslip and also create a clean key-fields JSON
- Extract the table from my bank statement
- Generate screenshots for page 2 of this contract

**Common mistakes**
- Say the file path or exact document name if there are several similar files.
- Say whether you want `JSON`, `text`, or `screenshots`.
- If LiteParse is not installed yet, ask me to check setup first.

**How to operate it safely**
- Keep source files read-only and work from generated outputs under `your_data/`.
- For folders, say whether you want the whole tree or only one extension like PDFs.
- If you need the generated output back in chat, say `send the parsed file here`.