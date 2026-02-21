# Google Drive Agent Functionality Roadmap

**Last Updated:** February 21, 2026  
**Status:** Phase 1–4 Implemented ✅  
**Agent Type:** Google Drive Personal Assistant

---

## 📋 Implementation Status Overview

| Category                  | Total | Completed | In Progress | To Do |
| ------------------------- | ----- | --------- | ----------- | ----- |
| **Core File Operations**  | 8     | 8         | 0           | 0     |
| **Sharing & Permissions** | 6     | 6         | 0           | 0     |
| **Smart Organization**    | 6     | 6         | 0           | 0     |
| **AI-Powered Features**   | 5     | 5         | 0           | 0     |
| **Analytics & Insights**  | 5     | 5         | 0           | 0     |
| **Total**                 | 30    | 30        | 0           | 0     |

> ✅ All 30 features implemented across 4 phases. Files:
> - `src/drive/drive_auth.py` — OAuth (reuses `credentials.json`, saves `drive_token.json`)
> - `src/drive/drive_service.py` — Phase 1 core operations
> - `src/drive/features/sharing.py` — Phase 2 sharing & permissions
> - `src/drive/features/summarizer.py` — Phase 3 AI summarization
> - `src/drive/features/duplicates.py` — Phase 3 duplicate detection
> - `src/drive/features/organizer.py` — Phase 3 auto-organize & bulk rename
> - `src/drive/features/versions.py` — Phase 3 version history
> - `src/drive/features/analytics.py` — Phase 4 storage analytics
> - `src/drive/features/insights.py` — Phase 4 AI insights & drive report
> - `src/agent/ui/drive_agent/` — full UI subpackage (app, conversation, formatters, helpers, orchestrator)
> - `src/agent/ui/drive_agent_ui.py` — thin shim
> - Registered in `src/agent/core/process_manager.py` (`"google_drive"` → `drive_agent_ui.py`)

---

## ✅ IMPLEMENTED FEATURES

---

### Phase 1: Core File Operations (Essential — Must Have)

#### 1. List Files & Folders 📂
**Priority:** HIGHEST  
**Complexity:** Low  
**Estimated Time:** 2–3 hours

**Planned Functions:**
- `list_files(folder_id, max_results, file_type)` — list files in a folder (or root)
  - Returns: name, id, mimeType, size, modifiedTime, owners, shared, webViewLink
  - Supports filtering by: file type (doc/sheet/slide/pdf/image/video/all)
  - Supports sorting: by name, size, modified date
- `list_folders(parent_id)` — list only folders (recursive option)
- `get_file_metadata(file_id)` — full metadata for a single file

**Natural Language Examples:**
- "Show me all files in my Drive"
- "List all PDFs in the Reports folder"
- "What folders do I have?"

---

#### 2. Search Files 🔍
**Priority:** HIGHEST  
**Complexity:** Low  
**Estimated Time:** 2 hours

**Planned Functions:**
- `search_files(query, max_results)` — full-text + metadata search using Drive query syntax
  - Supports: name contains, fullText contains, mimeType, modifiedTime, size, owner, shared
- `search_by_name(name, fuzzy)` — name-only search with optional fuzzy matching
- `search_recent(days, max_results)` — files modified in the last N days
- `search_large_files(min_size_mb, max_results)` — find storage hogs

**Natural Language Examples:**
- "Find the file named quarterly report"
- "Search for all spreadsheets containing budget"
- "Show files modified in the last 7 days"

---

#### 3. Upload Files 📤
**Priority:** HIGH  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Planned Functions:**
- `upload_file(local_path, folder_id, file_name)` — upload any file to Drive
  - Supports: resumable uploads for files > 5MB
  - Returns: file_id, name, webViewLink, size, mimeType
- `upload_folder(local_folder_path, parent_folder_id)` — upload entire folder tree
- `create_google_doc(title, content, folder_id)` — create a new Google Doc with initial content
- `create_google_sheet(title, folder_id)` — create a new blank spreadsheet
- `create_google_slide(title, folder_id)` — create a new blank presentation

**Natural Language Examples:**
- "Upload report.pdf to my Reports folder"
- "Upload all files from my Desktop/Documents folder"
- "Create a new Google Doc called Meeting Notes"

---

#### 4. Download Files 📥
**Priority:** HIGH  
**Complexity:** Medium  
**Estimated Time:** 2–3 hours

**Planned Functions:**
- `download_file(file_id, save_path)` — download binary blob or export Google Workspace files
  - Auto-exports: Docs → PDF/DOCX, Sheets → XLSX/CSV, Slides → PDF/PPTX
  - Default save: `~/Downloads/OctaMind_Drive/`
- `download_folder(folder_id, local_path)` — recursively download entire folder
- `export_as(file_id, format, save_path)` — explicit format export (pdf / docx / xlsx / csv / pptx / txt)
- `get_download_link(file_id)` — returns temporary direct download URL

**Natural Language Examples:**
- "Download the Q1 report as PDF"
- "Download everything in the Archive folder"
- "Export the budget sheet as CSV"

---

#### 5. Create & Manage Folders 📁
**Priority:** HIGH  
**Complexity:** Low  
**Estimated Time:** 2 hours

**Planned Functions:**
- `create_folder(name, parent_id)` — create a folder at a given path
- `create_folder_path(path)` — create nested path like "Work/2026/Reports" in one call
- `rename_item(file_id, new_name)` — rename file or folder
- `get_folder_id(path)` — resolve folder name/path to folder_id
- `get_folder_size(folder_id)` — total storage size of a folder and all children

**Natural Language Examples:**
- "Create a folder called Q1 Reports inside Work"
- "Rename the folder Budget2025 to Budget2026"
- "How big is my Photos folder?"

---

#### 6. Move & Copy Files ✂️
**Priority:** HIGH  
**Complexity:** Low  
**Estimated Time:** 2 hours

**Planned Functions:**
- `move_file(file_id, destination_folder_id)` — move to new parent folder
- `copy_file(file_id, destination_folder_id, new_name)` — duplicate a file
- `move_files_bulk(query, destination_folder_id)` — move all files matching a search query
- `copy_folder(folder_id, destination_folder_id)` — deep-copy entire folder tree

**Natural Language Examples:**
- "Move the Q4 report to the Archive folder"
- "Copy the template to the 2026 folder"
- "Move all PDFs from Downloads to Reports"

---

#### 7. Delete & Trash Files 🗑️
**Priority:** HIGH  
**Complexity:** Low  
**Estimated Time:** 2 hours

**Planned Functions:**
- `trash_file(file_id)` — move to trash (recoverable)
- `delete_file_permanently(file_id)` — permanent deletion (requires confirmation)
- `trash_files_bulk(query, max_results)` — bulk trash matching files
- `empty_trash()` — permanently delete all trashed files
- `restore_from_trash(file_id)` — restore a trashed item
- `list_trash(max_results)` — list items currently in trash

**Safety note:** Bulk permanent deletion will always require a two-step confirmation, matching the `max_operations` guard pattern from the Gmail agent.

**Natural Language Examples:**
- "Delete the old draft report"
- "Trash all files in the Temp folder"
- "Empty my Drive trash"
- "Restore the file I just deleted"

---

#### 8. File Shortcuts & Stars ⭐
**Priority:** MEDIUM  
**Complexity:** Low  
**Estimated Time:** 1 hour

**Planned Functions:**
- `star_file(file_id)` / `unstar_file(file_id)` — add/remove star
- `list_starred()` — show all starred files and folders
- `create_shortcut(file_id, folder_id)` — Drive shortcut (like alias/symlink)

**Natural Language Examples:**
- "Star the marketing deck"
- "Show me all my starred files"

---

### Phase 2: Sharing & Permissions (Collaboration)

#### 9. Share Files & Folders 🔗
**Priority:** HIGH  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Planned Functions:**
- `share_file(file_id, email, role)` — share with a specific person
  - `role`: `viewer` / `commenter` / `editor` / `owner`
- `share_with_link(file_id, link_type)` — make shareable link
  - `link_type`: `anyone_view` / `anyone_comment` / `anyone_edit` / `restricted`
- `share_folder(folder_id, email, role, recursive)` — share entire folder tree
- `get_share_link(file_id)` — return existing shareable URL

**Natural Language Examples:**
- "Share the Q1 report with john@example.com as viewer"
- "Make the project folder editable by anyone with the link"
- "Get the share link for the budget spreadsheet"

---

#### 10. Manage Permissions 🔒
**Priority:** HIGH  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Planned Functions:**
- `list_permissions(file_id)` — list everyone who has access (role, email, expiry)
- `update_permission(file_id, permission_id, new_role)` — change someone's access level
- `revoke_permission(file_id, email)` — remove a specific person's access
- `revoke_all_sharing(file_id)` — make file fully private
- `set_expiry(file_id, permission_id, expiry_datetime)` — time-limited access
- `transfer_ownership(file_id, new_owner_email)` — transfer to another user

**Natural Language Examples:**
- "Who has access to the annual report?"
- "Remove John's access to the budget file"
- "Make the presentation private again"
- "Give Sarah edit access only until Friday"

---

### Phase 3: Smart Organization (AI-Powered)

#### 11. AI File Summarization 🧠
**Priority:** HIGH  
**Complexity:** High  
**Estimated Time:** 5 hours

**Planned Functions:**
- `summarize_file(file_id)` — export file content → LLM summary
  - Supported types: Google Docs, Sheets (first N rows), plain text, PDFs
  - Returns: summary, key_points, topics, word_count, estimated_read_time
- `summarize_folder(folder_id, max_files)` — batch-summarize and return a folder digest
- `get_file_keywords(file_id)` — extract top keywords/topics via LLM

**Natural Language Examples:**
- "Summarize the Q1 strategy document"
- "Give me an overview of everything in the Reports folder"
- "What topics does the research doc cover?"

---

#### 12. Duplicate File Detection 👯
**Priority:** MEDIUM  
**Complexity:** Medium  
**Estimated Time:** 3–4 hours

**Planned Functions:**
- `find_duplicates(folder_id)` — find files with the same name AND size (hash comparison for small files)
  - Returns: groups of duplicates with file IDs, sizes, locations, last accessed
- `find_duplicate_names(folder_id)` — return name-only duplicates (same name, possibly different content)
- `resolve_duplicates(keep_strategy)` — keep: `newest` / `oldest` / `largest` / manual list
  - Trashes duplicates with a confirmation step first

**Natural Language Examples:**
- "Find all duplicate files in my Drive"
- "Are there any duplicates in the Archive folder?"
- "Remove duplicate files, keeping the newest version"

---

#### 13. Auto-Organize Files 🗂️
**Priority:** MEDIUM  
**Complexity:** High  
**Estimated Time:** 5–6 hours

**Planned Functions:**
- `suggest_organization(folder_id)` — LLM analyses file names, types, dates → suggests folder structure
- `auto_organize(folder_id, dry_run)` — moves files into suggested categorized subfolders
  - Categories: by type (Docs/Images/Spreadsheets/PDFs), by year/month, by project keyword
  - `dry_run=True` shows plan without executing
- `organize_by_date(folder_id, granularity)` — move files into `YYYY/MM/` structure
- `organize_by_type(folder_id)` — group into type subfolders automatically

**Natural Language Examples:**
- "Suggest how I should organize my Downloads folder"
- "Auto-organize my Drive root into folders by file type"
- "Organize the uploads folder by year and month"

---

#### 14. Version History & Recovery 🕐
**Priority:** MEDIUM  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Planned Functions:**
- `list_versions(file_id)` — list all revisions with date, size, modifier
- `get_version(file_id, revision_id)` — download a specific historical version
- `restore_version(file_id, revision_id)` — revert file to older version
- `compare_versions(file_id, revision_id_a, revision_id_b)` — diff summary for Docs/text files
- `delete_old_versions(file_id, keep_last_n)` — prune old revisions to save storage

**Natural Language Examples:**
- "Show me the version history of the strategy doc"
- "Restore the report to how it was last Monday"
- "Download the version from February 15th"

---

#### 15. Bulk Rename 📝
**Priority:** LOW  
**Complexity:** Medium  
**Estimated Time:** 2 hours

**Planned Functions:**
- `bulk_rename(folder_id, pattern, replacement)` — regex-based rename across all files in folder
- `add_prefix(folder_id, prefix)` / `add_suffix(folder_id, suffix)` — batch add prefix/suffix
- `rename_by_date(folder_id)` — prepend file modified date to name (e.g. `2026-02-21_filename.pdf`)

**Natural Language Examples:**
- "Rename all files in Reports to add '2026_' prefix"
- "Add '_archived' suffix to all files in the old folder"

---

### Phase 4: Analytics & Insights

#### 16. Storage Analytics 📊
**Priority:** HIGH  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Planned Functions:**
- `get_storage_summary()` — used vs available, breakdown by file type, by owner, by folder
- `get_largest_files(max_results)` — sorted by size descending
- `get_storage_by_type()` — size breakdown: Docs / Sheets / Slides / PDFs / Images / Videos / Other
- `get_storage_trend(days)` — estimate storage growth rate based on recent uploads

**Natural Language Examples:**
- "How much Drive storage am I using?"
- "What's taking up the most space in my Drive?"
- "Show me my 20 largest files"

---

#### 17. Activity & Access Analytics 📈
**Priority:** MEDIUM  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Planned Functions:**
- `get_recent_activity(max_results)` — files viewed/edited recently (from Drive activity API)
- `get_most_accessed_files(days)` — most viewed/edited files in last N days
- `get_files_not_accessed(days)` — files not opened in N+ days (stale file candidates)
- `get_shared_files_report()` — all files/folders shared externally with who has access

**Natural Language Examples:**
- "What files have I accessed most this week?"
- "Show me all files I haven't opened in 6 months"
- "Which of my files are shared with people outside my org?"

---

#### 18. Orphan & Cleanup Detection 🧹
**Priority:** MEDIUM  
**Complexity:** Medium  
**Estimated Time:** 2–3 hours

**Planned Functions:**
- `find_orphaned_files()` — files not in any folder (root-level clutter)
- `find_empty_folders()` — folders containing zero files
- `find_old_files(older_than_days)` — files not modified in N+ days
- `generate_cleanup_report()` — combined report: duplicates + orphans + large files + old files
  - LLM formats into a readable summary with recommendations

**Natural Language Examples:**
- "Find all orphaned files in my Drive"
- "Show me empty folders I can delete"
- "Generate a Drive cleanup report"

---

#### 19. File Sharing Report 🔍
**Priority:** LOW  
**Complexity:** Medium  
**Estimated Time:** 2 hours

**Planned Functions:**
- `get_publicly_shared()` — all files/folders with `anyone with link` access
- `get_externally_shared()` — files shared with emails outside a specified domain
- `get_over_shared_files(threshold)` — files shared with more than N people
- `audit_permissions()` — full JSON report of all files + their current permissions

**Natural Language Examples:**
- "Which files are publicly accessible?"
- "Show me everything shared with people outside my company"
- "Audit all shared files in my Drive"

---

#### 20. Drive Productivity Insights 💡
**Priority:** LOW  
**Complexity:** High  
**Estimated Time:** 4 hours

**Planned Functions:**
- `get_productivity_insights()` — LLM-generated tips based on Drive usage patterns
  - Identifies: messy folder structure, too many root files, large old files, orphaned content
  - Returns: suggestions list with actionable recommendations
- `generate_weekly_drive_report()` — 7-day summary: uploads, downloads, shares, storage delta
- `estimate_clutter_score()` — 0–100 score representing organization quality

**Natural Language Examples:**
- "Give me Drive productivity insights"
- "Generate a weekly Drive report"
- "How organized is my Drive?"

---

## 🏗️ IMPLEMENTATION STRATEGY

### Phase 1: Core File Operations (Start Here)
1. ⬜ List Files & Folders
2. ⬜ Search Files
3. ⬜ Upload Files
4. ⬜ Download Files
5. ⬜ Create & Manage Folders
6. ⬜ Move & Copy Files
7. ⬜ Delete & Trash Files
8. ⬜ Shortcuts & Stars

### Phase 2: Sharing & Permissions
9.  ⬜ Share Files & Folders
10. ⬜ Manage Permissions

### Phase 3: Smart Organization (AI)
11. ⬜ AI File Summarization
12. ⬜ Duplicate Detection
13. ⬜ Auto-Organize Files
14. ⬜ Version History & Recovery
15. ⬜ Bulk Rename

### Phase 4: Analytics & Insights
16. ⬜ Storage Analytics
17. ⬜ Activity & Access Analytics
18. ⬜ Orphan & Cleanup Detection
19. ⬜ File Sharing Report
20. ⬜ Drive Productivity Insights

---

## 📁 PLANNED FILE STRUCTURE

```
src/
└── drive/
    ├── __init__.py                  # Exports all public functions
    ├── drive_service.py             # Core Google Drive API client + auth
    │                                #   list_files, search_files, upload, download
    │                                #   create_folder, move, copy, trash, star
    └── features/
        ├── __init__.py
        ├── sharing.py               # Phase 2 — share_file, manage_permissions, revoke
        ├── organizer.py             # Phase 3 — auto_organize, bulk_rename, organize_by_date
        ├── summarizer.py            # Phase 3 — summarize_file, summarize_folder (LLM)
        ├── duplicates.py            # Phase 3 — find_duplicates, resolve_duplicates
        ├── versions.py              # Phase 3 — list_versions, restore_version
        ├── analytics.py             # Phase 4 — storage_summary, largest_files, activity
        └── insights.py              # Phase 4 — productivity_insights, cleanup_report

src/agent/ui/
└── drive_agent/                     # New UI subpackage (follows email_agent/ pattern)
    ├── __init__.py
    ├── app.py                       # main() — Streamlit rendering loop
    ├── conversation.py              # handle_conversation()
    ├── formatters.py                # format_drive_result()
    ├── helpers.py                   # Logo + watchdog
    └── orchestrator.py              # execute_with_llm_orchestration()
```

---

## 🔧 TECHNICAL REQUIREMENTS

### Google Drive API Scopes Needed
```python
SCOPES = [
    "https://www.googleapis.com/auth/drive",             # Full Drive access
    # OR more specific scopes:
    "https://www.googleapis.com/auth/drive.file",        # Only files created by app
    "https://www.googleapis.com/auth/drive.metadata",    # Metadata only
    "https://www.googleapis.com/auth/drive.readonly",    # Read-only (for analytics phase)
]
```

**Recommended:** Start with `drive.file` + `drive.metadata.readonly` for core operations, expand to `drive` scope when sharing and deletion features are added.

### Google OAuth Setup
- Can **reuse the same `credentials.json`** used for Gmail — it is a Google OAuth 2.0 client, not service-specific.
- A separate `drive_token.json` should be generated (separate token from `token.json`) to avoid scope conflicts.
- **Google Drive API** must be enabled in Google Cloud Console (separate toggle from Gmail API).

### Python Library
```bash
pip install google-api-python-client google-auth google-auth-oauthlib
# Already installed from Gmail integration — no new dependencies needed
```

### LLM Integration
- Same `get_llm_client()` used for Gmail orchestration
- Drive-specific tool schema to be added to `orchestrate_mcp_tool()` system prompt
- File summarization exports content → sends to LLM → returns structured JSON

### File Size Handling
- **Small files (< 5MB):** Simple upload/download
- **Large files (> 5MB):** Resumable upload using `MediaFileUpload(resumable=True)`
- **Google Workspace files (Docs/Sheets/Slides):** Cannot be downloaded as-is — must export to a target format via `files.export()`

---

## 🔐 SAFETY CONSIDERATIONS

| Operation                 | Risk Level | Safety Measure                                      |
| ------------------------- | ---------- | --------------------------------------------------- |
| `delete_file_permanently` | 🔴 HIGH     | Two-step confirmation; `max_operations` cap         |
| `empty_trash`             | 🔴 HIGH     | Explicit confirmation + list preview shown first    |
| `trash_files_bulk`        | 🟡 MEDIUM   | `max_operations` limit; show count before execution |
| `revoke_all_sharing`      | 🟡 MEDIUM   | Show current permissions before revoking            |
| `auto_organize`           | 🟡 MEDIUM   | `dry_run=True` by default; show plan first          |
| `transfer_ownership`      | 🔴 HIGH     | Explicit email + confirmation required              |
| `upload_folder`           | 🟢 LOW      | Show estimated file count before starting           |

---

## 📝 NOTES & CONSIDERATIONS

### Differences vs Gmail Agent
- Drive files are **binary or Google Workspace format** — text extraction requires export step before LLM processing
- Drive **does not have a concept of "inbox"** — browsing starts at root or a named folder
- Drive queries use a **different syntax** than Gmail (e.g. `name contains 'report'` not `from:`)
- Some operations like folder listing are **recursive** and can be expensive — always include `max_results` guards

### UI/UX
- Drive agent UI should show a **folder breadcrumb** in the sidebar (current location)
- File results need a **quick-action row**: Download / Share / Summarize / Trash
- Large file/folder operations should stream progress updates in the chat

### Performance Optimizations
- Cache folder ID lookups (`_folder_id_cache`) to avoid repeated API round-trips
- Batch metadata fetches using `fields` parameter in Drive API
- Summarization: export and truncate to ~4000 tokens before sending to LLM

### Future Enhancements
- [ ] Real-time Drive change notifications (Drive Push Notifications / Webhooks)
- [ ] Google Workspace add-on integration
- [ ] Multi-account Drive support
- [ ] Collaborative folder monitoring — alert when shared files are modified
- [ ] Integration with Calendar agent (attach Drive files to calendar events)

---

## 🐛 KNOWN ISSUES (Pre-implementation)
- None — planning phase

---

## 📊 METRICS TO TRACK
- [ ] Files organized per session
- [ ] Storage freed (GB) via duplicate/cleanup features
- [ ] Share links generated
- [ ] Files summarized
- [ ] Average query-to-action latency
- [ ] User satisfaction rating

---

**Status:** Planning complete. Ready to begin Phase 1 implementation.
