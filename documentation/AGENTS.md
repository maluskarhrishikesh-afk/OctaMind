# OctaMind — Agents Reference

For full parameter details on every tool, see [TOOL_REFERENCE.md](TOOL_REFERENCE.md).  
For implementation status and known limitations, see [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

---

## Email Agent (Gmail)

**Script:** `src/agent/ui/email_agent_ui.py`  
**Backend:** Gmail API via `src/email/`  
**LLM loop:** ReAct (up to 6 iterations, `max_tokens=3000`)  
**Setup Guide:** [EMAIL_SETUP.md](EMAIL_SETUP.md)

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Read** | "List my emails from today" · "Show unread emails" · "Search for emails from Alice" |
| **Count** | "How many emails did I get today?" · "How many unread emails?" |
| **Send** | "Send an email to bob@example.com saying the meeting is at 3pm" |
| **Send with attachment** | "Email the Q3 report to alice@example.com" (after downloading from Drive) |
| **Draft** | "Create a draft to the team about the project update" |
| **Reply** | "Reply to the latest email from John saying I'll be there" |
| **Urgent** | "Show me any urgent emails" |
| **Action items** | "Extract action items from email {id}" |
| **Contacts** | "Export my frequent contacts" |
| **Stats** | "Give me my inbox statistics" |

### Tools Available

```
list_emails(query, max_results)
get_todays_emails(max_results)
get_inbox_count()
send_email(to, subject, message)
send_email_with_attachment(to, subject, message, attachment_path)
create_draft(to, subject, body)
reply_to_message(message_id, reply_text)
detect_urgent_emails(max_results)
extract_action_items(message_id)
get_all_pending_actions(max_emails)
generate_reply_suggestions(message_id)
list_attachments(message_id)
download_attachment(message_id, attachment_id, save_path)
get_email_stats()
export_contacts()
```

---

## Drive Agent (Google Drive)

**Script:** `src/agent/ui/drive_agent_ui.py`  
**Backend:** Drive API via `src/drive/`  
**LLM loop:** ReAct (up to 6 iterations, `max_tokens=3000`)  
**Setup Guide:** [EMAIL_SETUP.md — Drive section](EMAIL_SETUP.md#also-setting-up-google-drive)

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **List** | "List my recent files" · "List files in the Projects folder" |
| **Search** | "Find the Q3 report" · "Search for spreadsheets modified this week" |
| **Upload** | "Upload report.pdf to my Drive" |
| **Download** | "Download the budget spreadsheet" |
| **Organise** | "Create a folder called Archive" · "Move invoice.pdf to Finance folder" |
| **Share** | "Share the roadmap doc with alice@example.com as viewer" |
| **Storage** | "How much storage am I using?" · "Show me my largest files" |
| **Analyse** | "Find duplicate files" · "Summarise the Q3 presentation" |

### Tools Available

```
list_files(max_results, query, folder_id)
search_files(query, max_results)
get_file_info(file_id)
download_file(file_id, destination)
upload_file(local_path, name, folder_id)
create_folder(name, parent_id)
move_file(file_id, destination_folder_id)
copy_file(file_id, name, folder_id)
trash_file(file_id)
share_file(file_id, email, role)
get_storage_quota()
storage_breakdown()
list_large_files(min_size_mb)
list_recently_modified(days, max_results)
find_duplicates()
summarize_file(file_id)
generate_drive_report()
```

---

## WhatsApp Agent

**Script:** `src/agent/ui/whatsapp_agent_ui.py`  
**Backend:** Meta WhatsApp Cloud API via `src/whatsapp/`  
**LLM loop:** ReAct (same pattern as Email/Drive agents)  
**Setup guide:** [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md)

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Send** | "Send hi to 919876543210" · "Message Alice saying I'll be late" |
| **Read** | "Show unread messages" · "Show recent messages" |
| **Reply** | "Reply to message wamid.xxx saying thanks" |
| **Search** | "Search for invoice" · "Messages from last week" |
| **Contacts** | "List my contacts" · "Who messages me most?" |
| **Groups** | "Show my groups" · "Messages in group <id>" |
| **AI** | "Summarize chat with 919876543210" · "Draft a message about project update" |
| **Translate** | "Translate message wamid.xxx to Hindi" |
| **Schedule** | "Schedule message for tomorrow 9am" · "Show scheduled messages" |
| **Analytics** | "WhatsApp stats 30 days" · "Who messages me most?" |

### Tools Available (36 total)

```
# Core Messaging (7)
send_message(to, body)
send_media(to, media_type, url, caption, filename)
send_template(to, template_name, language_code)
reply_to_message(to, original_message_id, body)
get_messages(limit)
get_unread_messages(limit)
mark_as_read(message_id)

# Contacts (4)
list_contacts(limit)
get_contact_info(phone)
get_frequent_contacts(limit)
set_contact_name(phone, name)

# Groups (3)
list_groups(limit)
get_group_info(group_id)
get_group_messages(group_id, limit)

# Search (4)
search_messages(query, limit)
get_conversation(phone, limit)
get_messages_by_date(start_date, end_date, limit)
get_media_messages(limit)

# AI Smart Features (8)
summarize_conversation(phone, limit)
extract_action_items(phone, limit)
draft_message(to, context)
generate_reply(message_id)
detect_urgent_messages(limit)
extract_key_info(message_id)
translate_message(message_id, target_language)
sentiment_analysis(phone, limit)

# Scheduling (5)
schedule_message(to, body, send_time)
list_scheduled_messages()
cancel_scheduled_message(scheduled_id)
set_auto_reply(enabled, message)
get_auto_reply_config()

# Analytics (4)
get_message_stats(days)
get_response_time(phone)
get_activity_report(days)
get_top_senders(limit)

# Cross-Agent (2)
forward_to_email(message_id, to_email, subject)
share_drive_file(to, file_id, message)
```

### Architecture Notes

- **Inbound messages** arrive via a FastAPI webhook server (port 9001) and are stored in `data/whatsapp_messages.json`
- **Outbound messages** are sent directly via the Meta Graph API
- **Contacts and groups** are discovered automatically from incoming messages
- Requires `fastapi`, `uvicorn`, `requests`, and `python-dateutil` (not in base requirements)
- See [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md) for full setup, ngrok config, and testing guide

---

## Files Agent

**Script:** `src/agent/ui/files_agent_ui.py`  
**Backend:** Python stdlib (`pathlib`, `shutil`, `zipfile`, `hashlib`, `os`) — no credentials required  
**LLM loop:** ReAct (same pattern as Email/Drive/WhatsApp agents)  
**Setup guide:** [FILES_SETUP.md](FILES_SETUP.md)

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Files** | "List my Downloads folder" · "Copy report.pdf to D:/Backup" · "Rename old.txt to new.txt" |
| **Search** | "Find all PDFs in D:/Documents" · "Files modified last 7 days" · "Find large files on C:" |
| **Duplicates** | "Find duplicate files in D:/Photos" · "Find empty folders in C:/Users/me" |
| **Archives** | "Zip my Documents folder" · "Unzip archive.zip to D:/Extracted" · "List contents of backup.zip" |
| **Organise** | "Organise D:/Downloads by file type" · "Organise D:/Photos by date" · "Bulk rename files" |
| **Disk** | "Show all drives" · "Disk usage on C:" · "How big is my Documents folder?" |
| **Read** | "Read notes.txt" · "Preview data.csv" · "Tail app.log last 50 lines" |
| **AI** | "Summarize D:/Finance/budget.txt" · "Analyse my Downloads" · "Suggest how to organise D:/Desktop" |
| **Cross-agent** | "Email report.pdf to alice@example.com" · "Upload D:/report.pdf to Google Drive" |

### Tools Available (48 total)

```
# File Operations (8)
list_directory(path, limit, show_hidden)
get_file_info(path)
copy_file(source, destination, overwrite)
move_file(source, destination, overwrite)
delete_file(path, permanent)
create_folder(path)
rename_file(path, new_name)
open_file(path)

# Search (6)
search_by_name(root, pattern, limit, recursive)
search_by_extension(root, extensions, limit, recursive)
search_by_date(root, since, until, limit)
search_by_size(root, min_bytes, max_bytes, limit)
find_duplicates(root, limit)
find_empty_folders(root, limit)

# Archives (5)
zip_files(sources, output_path)
zip_folder(folder_path, output_path)
unzip_file(archive_path, destination)
list_archive_contents(archive_path)
get_archive_info(archive_path)

# Organiser (7)
bulk_rename(folder, pattern, replacement, dry_run)
organize_by_type(folder, dry_run)
organize_by_date(folder, dry_run)
move_files_matching(src_folder, dest_folder, pattern, dry_run)
delete_files_matching(folder, pattern, dry_run)
clean_empty_folders(folder, dry_run)
deduplicate_files(folder, dry_run)

# Disk (5)
list_drives()
get_disk_usage(path)
get_directory_size(path)
find_large_files(root, min_bytes, limit)
get_recently_modified(root, hours, limit)

# Reader (6)
read_text_file(path, max_lines, start_line)
get_file_stats(path)
preview_csv(path, rows)
read_json_file(path)
tail_log(path, lines)
calculate_file_hash(path, algorithm)

# AI Smart Features (6)
summarize_file(path, max_chars)
analyze_folder(path)
suggest_organization(path)
generate_rename_suggestions(folder, limit)
find_related_files(path, limit)
describe_file(path)

# Cross-Agent (5)
zip_and_email(source, to_email, subject, body)
zip_and_upload_to_drive(source, drive_folder_id)
email_file(file_path, to_email, subject, body)
upload_file_to_drive(file_path, drive_folder_id)
send_file_via_whatsapp(file_path, to)
```

### Architecture Notes

- **No credentials required** for core 43 tools — works on first launch
- **Cross-agent tools** (5) gracefully handle `ImportError` if Gmail/Drive/WhatsApp not configured
- **Safety:** `_is_safe_path()` blocks operations on `C:/Windows`, `C:/System32`, `C:/Program Files`, and similar Linux paths
- **Destructive operations** (delete, bulk remove, deduplicate) default to `dry_run=True`
- **Optional:** `send2trash` for Recycle Bin support (`pip install send2trash`)
- See [FILES_SETUP.md](FILES_SETUP.md) for a full testing guide with expected outputs

---

## Multi-Agent Hub

**Script:** `src/agent/ui/multi_agent_ui.py`  
**Purpose:** Commands that span both Gmail and Google Drive in one sentence

### Routing Logic

| Classified as | Action |
|--------------|--------|
| Email only | Calls Email Agent's ReAct orchestrator directly |
| Drive only | Calls Drive Agent's ReAct orchestrator directly |
| Both | Runs the workflow planner → sequential step execution |
| Neither | Casual chat via `llm.chat()` |

### Cross-Agent Example Commands

```
"Download the Q3 report from Drive and email it to alice@example.com"
"Find the invoice PDF and send it to bob@example.com"
"Save the attachment from email {id} to my Drive"
"Email me a Drive storage report"
"Share the roadmap with everyone who emailed me today"
```

### Workflow Step References

In multi-step workflows, the output of one step can be piped to the next using `{output_key}` syntax. For example:

```
Step 1: download_file → output_key: "downloaded_file"
Step 2: send_email_with_attachment → attachment_path: "{downloaded_file}"
```

---

## Agent Memory

Every agent (Email, Drive, or any custom agent) maintains its own memory folder at `memory/<agent_id>/`. Memory is loaded as context for every LLM call, so agents remember past interactions, user preferences, and learned patterns.

See [architecture/memory-system.md](../architecture/memory-system.md) for full details.

---

## Rate Limits

All agents share the same GitHub Models API token.

| Limit | Value |
|-------|-------|
| Per minute | 15 requests |
| Per day | 150 requests |
| Reset | Every 24 hours |

Each ReAct loop iteration is one API call. A typical 2-step task uses 2–4 calls. When the limit is hit, all agents show: *"⏳ API rate limit reached."*
