# OctaMind — Agents Reference

For full parameter details on every tool, see [TOOL_REFERENCE.md](TOOL_REFERENCE.md).  
For implementation status and known limitations, see [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

---

## Email Agent (Gmail)

**Script:** `src/agent/ui/email_agent_ui.py`  
**Backend:** Gmail API via `src/email/`  
**LLM loop:** ReAct (up to 6 iterations, `max_tokens=3000`)

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
