# Files Agent — Setup & Testing Guide

## Overview

The Files Agent is a local-file-system management agent for Octa Bot. It needs **no credentials and no API setup** — it works immediately after you create a Files Agent in the Agent Hub. The only optional dependency is an LLM provider (for the AI smart features in the last section), and `send2trash` for Recycle Bin support.

---

## Quick Setup

### 1. Install optional packages (recommended)

```bash
pip install send2trash
```

`send2trash` enables safe deletion (Recycle Bin instead of permanent delete). Without it, deletes are **permanent** by default.

### 2. Create a Files Agent in the Agent Hub

1. Open the **Agent Hub** (`http://localhost:8501`)
2. Click **+ Create Agent**
3. Select agent type: **Files Agent**
4. Give it a name (e.g., "My Files Agent")
5. Click **Create Agent**
6. Click **Start** to launch the agent's chat UI

The Files Agent opens in its own browser tab (port auto-assigned). No environment variables or credentials needed.

---

## Testing Checklist

Work through each section below to verify every feature category works.

---

### Category 1 — File & Folder Operations (8 tools)

Open the Files Agent chat and type these commands one by one:

```
List my Downloads folder
```
**Expected:** A folder listing showing files and subfolders.

```
Get info on C:/Windows/notepad.exe
```
**Expected:** File metadata — size, dates, extension, type.

```
Create folder C:/Users/<YourName>/Desktop/Octa Bot_Test
```
**Expected:** "Folder created successfully."

```
Copy C:/Windows/notepad.exe to C:/Users/<YourName>/Desktop/Octa Bot_Test/notepad_copy.exe
```
**Expected:** "File copied."

```
Rename C:/Users/<YourName>/Desktop/Octa Bot_Test/notepad_copy.exe to test_copy.exe
```
**Expected:** "File renamed."

```
Move C:/Users/<YourName>/Desktop/Octa Bot_Test/test_copy.exe to C:/Users/<YourName>/Desktop/
```
**Expected:** "File moved."

```
Delete C:/Users/<YourName>/Desktop/test_copy.exe
```
**Expected:** "Moved to Recycle Bin." (or "Deleted." if send2trash not installed)

---

### Category 2 — Search & Find (6 tools)

```
Find files named notepad in C:/Windows
```
**Expected:** List of matching files.

```
Find all PDF files in C:/Users/<YourName>/Documents
```
**Expected:** List of PDF files (or "No files found" if none exist).

```
Find files modified in the last 7 days in C:/Users/<YourName>
```
**Expected:** Files modified this week.

```
Find files larger than 50 MB in C:/Users/<YourName>
```
**Expected:** Large file list.

```
Find duplicate files in C:/Users/<YourName>/Downloads
```
**Expected:** Groups of identical files by MD5 hash, or "No duplicates found."

```
Find empty folders in C:/Users/<YourName>/Documents
```
**Expected:** List of empty directories, or "No empty folders found."

---

### Category 3 — Archives (5 tools)

First, create a test folder with content:
```
Create folder C:/Users/<YourName>/Desktop/ZipTest
```

Then:
```
Zip C:/Users/<YourName>/Desktop/ZipTest to C:/Users/<YourName>/Desktop/ZipTest.zip
```
**Expected:** "Archive created. X files zipped."

```
List contents of C:/Users/<YourName>/Desktop/ZipTest.zip
```
**Expected:** File list inside the archive.

```
Get archive info for C:/Users/<YourName>/Desktop/ZipTest.zip
```
**Expected:** File count, compressed/uncompressed sizes, compression ratio.

```
Unzip C:/Users/<YourName>/Desktop/ZipTest.zip to C:/Users/<YourName>/Desktop/ZipTest_Extracted
```
**Expected:** "Extracted X files."

---

### Category 4 — Organise & Bulk (7 tools)

> ⚠️ All destructive tools default to **dry run**. The agent will show a preview. To apply, reply "yes, do it" or add "dry_run=False".

```
Organise C:/Users/<YourName>/Downloads by file type (dry run)
```
**Expected:** Preview list showing which files would move to which folders (Images, Documents, etc.).

```
Organise C:/Users/<YourName>/Downloads by date (dry run)
```
**Expected:** Preview list showing YYYY/MM folder structure.

```
Bulk rename files in C:/Users/<YourName>/Desktop/Octa Bot_Test with prefix Test_
```
**Expected:** Preview of `Test_<original_name>` renames.

```
Move all PDF files from C:/Users/<YourName>/Downloads to C:/Users/<YourName>/Documents/PDFs (dry run)
```
**Expected:** Preview of files that would be moved.

```
Clean empty folders in C:/Users/<YourName>/Octa Bot_Test
```
**Expected:** "Found X empty folders to remove" or "No empty folders."

```
Deduplicate files in C:/Users/<YourName>/Downloads (dry run)
```
**Expected:** Preview showing which duplicate copies would be removed.

---

### Category 5 — Disk & Space (5 tools)

```
Show all drives
```
**Expected:** List of drives (C:, D:, etc.) with sizes and free space.

```
Disk usage on C:
```
**Expected:** Used / free / total with percentage.

```
How big is my Documents folder?
```
**Expected:** Total size of C:/Users/<YourName>/Documents.

```
Find large files on C: drive
```
**Expected:** Top files by size (may take a moment on large drives).

```
Files modified recently in C:/Users/<YourName>
```
**Expected:** Files modified in the last 24–48 hours.

---

### Category 6 — Read & Analyse (6 tools)

```
Read C:/Windows/System32/drivers/etc/hosts
```
**Expected:** Hosts file contents displayed as text.

```
Preview C:/Users/<YourName>/Documents/some_file.csv
```
*(Use any CSV file you have)*  
**Expected:** Headers + first 10 rows.

```
Read JSON file C:/path/to/any/config.json
```
**Expected:** Pretty-printed JSON.

```
Tail C:/path/to/logfile.log last 20 lines
```
**Expected:** Last 20 lines of the log.

```
MD5 hash of C:/Windows/notepad.exe
```
**Expected:** Hex MD5 digest string.

```
Get file stats for C:/Users/<YourName>/Documents
```
**Expected:** inode, permissions, size, timestamps.

---

### Category 7 — AI Features (6 tools)

> Requires LLM provider configured in `config/settings.json`.

```
Summarize C:/Users/<YourName>/Documents/any_text_file.txt
```
**Expected:** 3–5 sentence AI summary.

```
Analyse my Downloads folder
```
**Expected:** AI report: folder size, file type breakdown, 3 insights, organisation suggestions.

```
Suggest how to organise C:/Users/<YourName>/Desktop
```
**Expected:** Actionable organisation advice.

```
Suggest better names for files in C:/Users/<YourName>/Downloads
```
**Expected:** Table of current → suggested names.

```
Find files related to notepad.exe in C:/Windows
```
**Expected:** Files with similar names (token-overlap based).

```
Describe C:/Windows/notepad.exe
```
**Expected:** AI description of what kind of file it is based on name, extension, and first few lines.

---

### Category 8 — Cross-Agent Tools (5 tools)

These require the corresponding agent to be configured:

| Tool | Required setup |
|------|---------------|
| `email_file` | Gmail OAuth (`config/token.json` exists) |
| `upload_file_to_drive` | Drive OAuth (`config/drive_token.json` exists) |
| `zip_and_email` | Gmail OAuth |
| `zip_and_upload_to_drive` | Drive OAuth |
| `send_file_via_whatsapp` | Returns helpful error (WhatsApp needs public URL, not local path) |

**Test — email a file:**
```
Email C:/Users/<YourName>/Desktop/any_file.txt to your-email@gmail.com
```
**Expected:** "Email sent with attachment."

**Test — upload to Drive:**
```
Upload C:/Users/<YourName>/Desktop/any_file.txt to Google Drive
```
**Expected:** "File uploaded to Drive. File ID: ..."

**Test — zip and email:**
```
Zip C:/Users/<YourName>/Documents and email to your-email@gmail.com
```
**Expected:** Zips the folder, attaches it to an email, sends.

---

## Error Reference

| Error message | Cause | Fix |
|---------------|-------|-----|
| `Path not found: ...` | Path doesn't exist | Use an absolute path with full drive letter |
| `Permission denied` | Can't read/write | Run as administrator or use a different folder |
| `Operation blocked: path is a protected system directory` | Tried to modify Windows/System32 | Use a non-system path |
| `send2trash not installed` | Soft-delete unavailable | `pip install send2trash` or pass `permanent=True` |
| `LLM not configured` | AI tools fail | Add LLM key to `config/settings.json` |
| `ImportError: src.email` | Cross-agent email fails | Follow Gmail OAuth setup in `documentation/SETUP.md` |
| `ImportError: src.drive` | Cross-agent Drive fails | Follow Drive OAuth setup in `documentation/SETUP.md` |

---

## Notes

- All paths should be **absolute** (e.g., `C:/Users/YourName/Documents`). Relative paths are resolved from the project root.
- Tilde expansion works: `~/Documents` maps to your home directory.
- The agent remembers past interactions via the memory system — you can ask follow-up questions like "what did you find?" after a search.
- Max search results: 500 files per query (hard cap to prevent full-drive scans).
- Max file read: 5 MB (hard cap — larger files return a truncation notice).
