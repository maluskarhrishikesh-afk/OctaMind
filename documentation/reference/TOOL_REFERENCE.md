# Tool Reference

Complete reference for every tool available in Octa Bot. All tools are invoked by natural language � you never call them directly.

---

## Drive Agent Tools

62 tools across 5 phases.

### Phase 1 � Core File Operations

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `list_files` | `max_results`, `query`, `folder_id` | 20, `""`, `"root"` | List files in a folder. Use `folder_id="trash"` to list trashed files. |
| `search_files` | `query`, `max_results` | required, 20 | Search by name or content. Pass plain text � do NOT use Drive query syntax. |
| `get_file_info` | `file_id` | required | Get metadata (name, type, size, owner, modified date) for a file. |
| `upload_file` | `local_path`, `name`, `folder_id` | required, None, None | Upload a local file to Drive. |
| `download_file` | `file_id`, `destination` | required, None | Download a Drive file locally. Can pass file name instead of ID � system resolves it. |
| `create_folder` | `name`, `parent_id` | required, None | Create a new folder. |
| `move_file` | `file_id`, `destination_folder_id` | both required | Move a file to a different folder. |
| `copy_file` | `file_id`, `name`, `folder_id` | required, None, None | Copy a file, optionally to a different folder. |
| `trash_file` | `file_id` | required | Send a file to trash (recoverable). |
| `restore_file` | `file_id` | required | Restore a trashed file. |
| `star_file` | `file_id`, `starred` | required, `True` | Star or unstar a file. |
| `get_storage_quota` | � | � | Return total and used Drive storage. |

**Example prompts:**
- "Show me all files" ? `list_files`
- "Find the Q3 report" ? `search_files(query="Q3 report")`
- "Download budget.xlsx" ? `download_file(file_id="budget.xlsx")` *(name lookup is automatic)*
- "Delete old_draft.docx" ? `trash_file`
- "How much storage am I using?" ? `get_storage_quota`

---

### Phase 2 � Sharing & Permissions

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `share_file` | `file_id`, `email`, `role`, `send_notification`, `message` | required, required, `"reader"`, `True`, None | Share a file. Roles: `reader`, `commenter`, `writer`. |
| `list_permissions` | `file_id` | required | List everyone who has access to a file. |
| `remove_permission` | `file_id`, `permission_id` | both required | Revoke a specific person's access. |
| `update_permission` | `file_id`, `permission_id`, `role` | all required | Change access level for an existing permission. |
| `make_public` | `file_id` | required | Give anyone-with-link access. |
| `remove_public` | `file_id` | required | Remove public access (revert to private). |

**Example prompts:**
- "Share report.pdf with alice@example.com as editor" ? `share_file(role="writer")`
- "Who can see my budget file?" ? `list_permissions`
- "Make the project deck public" ? `make_public`

---

### Phase 3 � Smart / AI Features

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `summarize_file` | `file_id` | required | AI-generated summary of a document's content. |
| `summarize_folder` | `folder_id` | `"root"` | Overview of a folder's contents. |
| `find_duplicates` | `folder_id`, `max_files` | `"root"`, 500 | Find files with identical names or hashes. |
| `trash_duplicates` | `folder_id`, `max_files`, `dry_run` | `"root"`, 500, `True` | Delete duplicate files. **`dry_run=True` by default** � shows preview without deleting. |
| `suggest_organization` | `folder_id`, `max_files` | `"root"`, 100 | AI suggestions for how to organise files into folders. |
| `auto_organize` | `folder_id`, `max_files`, `dry_run` | `"root"`, 100, `True` | Automatically move files into organised folders. **`dry_run=True` by default.** |
| `bulk_rename` | `folder_id`, `pattern`, `replacement`, `max_files`, `dry_run` | required�2, 100, `True` | Rename files matching a regex pattern. **`dry_run=True` by default.** |
| `list_versions` | `file_id` | required | List revision history for a file. |
| `get_version_info` | `file_id`, `revision_id` | both required | Metadata for a specific revision. |
| `restore_version` | `file_id`, `revision_id` | both required | Roll back a file to a previous revision. |
| `delete_old_versions` | `file_id`, `keep_latest`, `dry_run` | required, 5, `True` | Delete old revisions, keeping the N most recent. **`dry_run=True` by default.** |

**Example prompts:**
- "Summarize my project proposal" ? `summarize_file`
- "Find duplicate files" ? `find_duplicates`
- "Remove duplicates from my Photos folder" ? `trash_duplicates(dry_run=False)` *(ask user to confirm first)*
- "Show version history of budget.xlsx" ? `list_versions`

> **Note:** All destructive bulk operations (`trash_duplicates`, `auto_organize`, `bulk_rename`, `delete_old_versions`) default to `dry_run=True`. The agent will show a preview and ask for confirmation before making real changes.

---

### Phase 4 � Analytics & Insights

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `storage_breakdown` | � | � | Storage usage broken down by file type (Docs, Sheets, PDFs, etc.). |
| `list_large_files` | `min_size_mb`, `max_results` | 50, 50 | Files above a size threshold. |
| `list_old_files` | `days`, `max_results` | 365, 50 | Files not modified in N days. |
| `list_recently_modified` | `max_results` | 20 | Files modified most recently. |
| `find_orphaned_files` | `max_results` | 100 | Files that have no parent folder (floating files). |
| `sharing_report` | `max_files` | 200 | Summary of which files are shared vs private. |
| `generate_drive_report` | � | � | Full Drive health report (storage, old files, duplicates, sharing). |
| `get_usage_insights` | � | � | AI-generated tips and recommendations for Drive organisation. |

**Example prompts:**
- "What's taking up the most space?" ? `storage_breakdown` then `list_large_files`
- "Show files I haven't touched in a year" ? `list_old_files(days=365)`
- "Give me a full Drive report" ? `generate_drive_report`
- "Any tips on organising my Drive?" ? `get_usage_insights`

---

### Phase 5 — Batch Operations, Sharing Controls & Backup

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `batch_move_files` | `file_ids`, `folder_id` | both required | Move multiple files to a destination folder in one call. |
| `batch_delete_files` | `file_ids`, `permanent` | required, `False` | Trash or permanently delete multiple files. |
| `batch_copy_files` | `file_ids`, `folder_id`, `name_suffix` | required, `""`, `" (copy)"` | Copy multiple files, optionally into a folder. |
| `share_file` | `file_id`, `email`, `role`, `make_public` | required, `""`, `"reader"`, `False` | Share with a person or make public. Roles: `reader`, `commenter`, `writer`. |
| `manage_file_permissions` | `file_id`, `action`, `permission_id`, `new_role` | required, required, `""`, `"reader"` | List, remove, or update permissions. `action`: `list`/`remove`/`update`. |
| `revoke_access_all` | `file_id` | required | Remove ALL non-owner permissions (make file fully private). |
| `get_sharing_stats` | `file_id` | required | Show all permissions, roles, and whether the file is public. |
| `list_shared_with_me` | `max_results` | `20` | List Drive files shared with the authenticated user. |
| `find_large_files` | `folder_id`, `min_size_mb`, `max_results` | `"root"`, `10.0`, `25` | Find the largest files. Use to diagnose storage issues. |
| `find_drive_duplicates` | `folder_id`, `max_results` | `"root"`, `200` | Find duplicate files by name+size fingerprint. |
| `trash_drive_duplicates` | `folder_id`, `keep` | `"root"`, `"newest"` | Trash duplicates, keeping one per group. `keep`: `newest`/`oldest`. |
| `suggest_archival` | `folder_id`, `months_old`, `max_results` | `"root"`, `6`, `25` | Find files not modified in N months. Useful for archival decisions. |
| `convert_document` | `file_id`, `output_format`, `save_path` | required, `"pdf"`, `""` | Export Docs/Sheets/Slides to `pdf`/`docx`/`xlsx`/`pptx`/`csv`/`txt`. |
| `list_file_versions` | `file_id` | required | List all revision history for a file. |
| `cleanup_old_versions` | `file_id`, `keep_latest` | required, `3` | Delete old revisions, keeping the N most recent. |
| `backup_drive_to_local` | `folder_id`, `output_dir`, `max_files` | required, required, `100` | Download all files from a Drive folder to a local directory. |
| `sync_local_folder_to_drive` | `local_path`, `drive_folder_id`, `dry_run` | required, required, `True` | Upload new/modified local files to Drive. **Always `dry_run=True` first.** |

**Example prompts:**
- "Move files A, B, C to the Archive folder" → `batch_move_files`
- "Share budget.xlsx with alice@example.com as editor" → `share_file(role="writer")`
- "Make the proposal private" → `revoke_access_all`
- "Who can see my contract.pdf?" → `get_sharing_stats`
- "Convert my Google Doc to PDF" → `convert_document`
- "Which files haven't been opened in 6 months?" → `suggest_archival`
- "Back up my Projects folder locally" → `backup_drive_to_local`
- "Upload my local Reports folder to Drive" → `sync_local_folder_to_drive(dry_run=True)` then confirm

---

## Email Agent Tools

62 tools across 9 categories.

### Reading & Searching

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `get_todays_messages` | `max_results` | 1000 | Emails received since midnight today. |
| `list_message` | `query`, `max_results` | `""`, 10 | Gmail search. Supports full Gmail query syntax. |
| `count_messages` | `query` | `""` | Count matching emails (runs `list_message` with max 1000). |
| `detect_urgent_emails` | `max_results` | 20 | AI-detected high-priority / urgent emails. |
| `detect_newsletters` | `max_results` | 30 | Find newsletters and promotional emails. |
| `check_unanswered_emails` | `older_than_days` | 3 | Sent emails with no reply yet. |

**Gmail query examples for `list_message`:**
- `is:unread` � unread emails
- `from:alice@example.com` � from a specific sender
- `subject:invoice` � subject line match
- `after:2026/02/01` � received after a date
- `has:attachment` � emails with attachments
- `label:work` � a specific label
- `is:unread from:boss@company.com` � combining conditions

---

### Sending & Drafts

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `send_message` | `to`, `subject`, `message_text` | all required | Send an email immediately. |
| `create_draft` | `to`, `subject`, `body` | all required | Save an email as a draft (not sent). |
| `list_drafts` | `max_results` | 10 | List saved drafts. |
| `send_draft` | `draft_id` | required | Send a saved draft. |
| `delete_draft` | `draft_id` | required | Delete a draft. |
| `quick_reply` | `message_id`, `reply_type` | both required | Send a pre-built reply. Types: `yes`, `no`, `thanks`, `acknowledged`, `more_info_needed`, `on_it`, `meeting_confirm`, `meeting_decline`. |
| `generate_reply_suggestions` | `message_id` | required | Generate 3 AI reply options (brief / professional / detailed). |
| `schedule_email` | `to`, `subject`, `body`, `send_time` | all required | Schedule an email for later. `send_time` accepts ISO or natural language ("tomorrow 9am"). |
| `list_scheduled_emails` | � | � | Show all pending scheduled emails. |
| `cancel_scheduled_email` | `scheduled_id` | required | Cancel a scheduled email. |
| `update_scheduled_email` | `scheduled_id`, `send_time` | both required | Reschedule a pending email. |

---

### Attachments

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `list_attachments` | `message_id` | required | List all attachments in an email. |
| `download_attachment` | `message_id`, `attachment_id`, `filename`, `save_path` | first 3 required, None | Download an attachment to disk. |
| `search_emails_with_attachments` | `file_type`, `max_results` | `"all"`, 10 | Find emails with attachments. `file_type`: `pdf`, `doc`, `spreadsheet`, `image`, `zip`, `all`. |

---

### Organisation & Labels

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `auto_categorize_email` | `message_id` | required | Categorize one email: work / personal / bills / newsletters / social / notifications / spam. |
| `apply_smart_labels` | `batch_size` | 20 | Auto-categorize and apply Gmail labels to recent emails in bulk. |
| `create_category_rules` | `min_occurrences` | 3 | Create Gmail filters from patterns in already-categorized emails. |
| `auto_prioritize` | `message_id` | required | Score urgency of a specific email (1�10 scale). |

---

### Action Items & Follow-ups

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `extract_action_items` | `message_id` | required | Extract tasks, deadlines, to-dos from an email using AI. |
| `get_all_pending_actions` | `max_emails` | 20 | Scan recent emails for all pending action items. |
| `mark_action_complete` | `task_id` | required | Mark a saved task as completed. |
| `get_saved_tasks` | `status_filter` | `"pending"` | List saved tasks. `status_filter`: `pending`, `done`, `all`. |
| `mark_for_followup` | `message_id`, `days`, `note` | required, 3, `""` | Set a follow-up reminder for N days from now. |
| `get_pending_followups` | � | � | List all pending follow-up reminders. |
| `send_followup_reminder` | `message_id` | required | Send yourself an email reminder about a tracked follow-up. |
| `mark_followup_done` | `message_id` | required | Mark a follow-up as done. |
| `dismiss_followup` | `message_id` | required | Dismiss a follow-up (no longer needed). |

---

### Calendar Integration

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `extract_calendar_events` | `message_id` | required | Extract meeting / event details from an email. |
| `suggest_calendar_entry` | `message_id` | required | AI-suggested calendar entry based on email content. |
| `export_to_calendar` | `event_data`, `save_ics` | required, `True` | Export an event to Google Calendar and/or save as `.ics` file. |

---

### Contacts & Analytics

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `get_frequent_contacts` | `limit` | 10 | Top email contacts ranked by interaction frequency. |
| `get_contact_summary` | `email_address` | required | Interaction stats for one contact (email count, response time, etc.). |
| `suggest_vip_contacts` | � | � | Contacts with high interaction frequency (VIP list). |
| `export_contacts` | `format`, `limit` | `"csv"`, 100 | Export contact data to CSV or JSON file. |
| `extract_unsubscribe_link` | `message_id` | required | Extract the unsubscribe URL from a newsletter/promo email. |
| `calculate_response_time` | `message_id` | required | How quickly you responded to a specific email. |
| `get_email_stats` | `days` | 30 | Volume stats: received, sent, top senders, busiest day. |
| `get_productivity_insights` | � | � | AI productivity insights based on email patterns. |
| `visualize_patterns` | `days` | 30 | Chart-ready data for email volume, response time, peak hours. |
| `generate_weekly_report` | � | � | Full weekly email activity report. |

---

### Inbox Management & Organisation

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `archive_emails` | `query`, `max_results` | required, `50` | Remove matching emails from Inbox (non-destructive; stays in All Mail). |
| `unsubscribe_email` | `message_id` | required | Attempt one-click unsubscribe via `List-Unsubscribe` header. |
| `batch_mark_spam` | `query`, `max_results` | required, `50` | Move matching emails to Spam. |
| `recover_deleted_emails` | `query`, `max_results` | `""`, `20` | Find emails in Trash and restore them to Inbox. |
| `empty_trash` | — | — | Permanently delete all emails in Trash. |
| `thread_mute` | `thread_id` | required | Mute a thread — future replies bypass Inbox. |
| `thread_archive` | `thread_id` | required | Archive an entire thread. |
| `thread_delete` | `thread_id` | required | Move an entire thread to Trash. |
| `create_label` | `label_name` | required | Create a Gmail label (no-op if already exists). |
| `move_emails_to_label` | `query`, `label_name`, `max_results` | required, required, `50` | Move matching emails to a label, removing from Inbox. |
| `create_smart_label_rule` | `label_name`, `from_email`, `subject_contains`, `to_email`, `also_archive` | required, `""`, `""`, `""`, `False` | Apply label to matching emails + optionally archive. |

---

### Signatures, Forwarding & Templates

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `get_signature` | `send_as_email` | `"me"` | Read the current Gmail signature. |
| `set_signature` | `signature_html`, `send_as_email` | required, `"me"` | Set the Gmail signature (HTML accepted). |
| `add_forwarding_address` | `forward_to` | required | Register a forwarding address (sends verification email). |
| `enable_email_forwarding` | `forward_to` | required | Enable auto-forwarding to a pre-verified address. |
| `save_email_template` | `name`, `subject`, `body` | all required | Save a reusable template. Use `{{variable}}` placeholders. |
| `list_email_templates` | — | — | List all saved email templates. |
| `send_from_template` | `template_name`, `to`, `variables` | required, required, `{}` | Send using a saved template with variable substitution. |
| `set_vacation_responder` | `enabled`, `subject`, `body`, `start_date`, `end_date` | required, `""`, `""`, `""`, `""` | Enable/disable Out-of-Office auto-reply. |
| `get_vacation_responder` | — | — | Check OOO status (enabled/disabled, message, dates). |

---

### Smart Analysis

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `find_unanswered_emails` | `days`, `max_results` | `3`, `20` | Find sent emails with no reply in the last N days. |
| `send_completion_reminder` | `message_id`, `days` | required, `3` | Set a self-reminder on a sent email if no reply within N days. |
| `analyze_email_sentiment` | `message_id` | required | Classify email tone: `urgent`/`positive`/`negative`/`neutral`. No LLM required. |
| `extract_urls_from_email` | `message_id` | required | Extract all links from an email, classified as regular links, tracking pixels, unsubscribe URLs. |
| `get_email_chains_summary` | `max_results` | `10` | Return the most active email threads sorted by reply count. |
| `fetch_emails_to_markdown` | `query`, `max_results`, `cap` | `"in:inbox"`, `5`, `20` | Fetch N emails in one call as Markdown. **Preferred for multi-email summarisation.** |

**Example prompts:**
- "What emails have I not replied to in 3 days?" → `find_unanswered_emails`
- "Is this email urgent?" → `analyze_email_sentiment`
- "Extract all links from message X" → `extract_urls_from_email`
- "Show me my longest conversations" → `get_email_chains_summary`
- "Set up an OOO for next week" → `set_vacation_responder`
- "Remind me if Alice doesn't reply in 3 days" → `send_completion_reminder`
- "Unsubscribe from this newsletter" → `unsubscribe_email`
- "Archive all emails from no-reply@company.com" → `archive_emails`

38 tools across 8 categories. Messages are addressed by composite ID `"chat_id:message_id"`.

### Core Messaging (11 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `send_message` | `chat_id`, `text` | both required | Send a text message to a chat. |
| `send_media` | `chat_id`, `media_type`, `url`, `caption` | required � 3, None | Send a photo/document/audio by URL. |
| `reply_to_message` | `chat_id`, `message_id`, `text` | all required | Send a threaded/quoted reply. |
| `forward_message` | `from_chat_id`, `to_chat_id`, `message_id` | all required | Forward a message to another chat. |
| `edit_message` | `chat_id`, `message_id`, `new_text` | all required | Edit a previously sent message. |
| `delete_message` | `chat_id`, `message_id` | both required | Delete a message. |
| `get_messages` | `limit` | 20 | Get recent messages across all chats. |
| `get_unread_messages` | `limit` | 20 | Get unread inbound messages. |
| `get_chat_history` | `chat_id`, `limit` | required, 30 | Full conversation thread for a chat. |
| `mark_as_read` | `composite_id` | required | Mark a stored message as read (`"chat_id:message_id"`). |
| `send_chat_action` | `chat_id`, `action` | required, `"typing"` | Show a typing / uploading indicator. |

### Chats (6 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `list_chats` | � | � | List all known chats with message counts. |
| `get_chat_info` | `chat_id` | required | Get chat metadata from Telegram API. |
| `get_chat_member_count` | `chat_id` | required | Number of members in a group/channel. |
| `pin_message` | `chat_id`, `message_id` | both required | Pin a message (requires bot admin rights). |
| `unpin_message` | `chat_id`, `message_id` | both required | Unpin a message. |
| `leave_chat` | `chat_id` | required | Make the bot leave a group or channel. |

### Media (4 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `send_photo` | `chat_id`, `file_path`, `caption` | required � 2, None | Upload and send a photo. |
| `send_document` | `chat_id`, `file_path`, `caption` | required � 2, None | Upload and send any file as a document. |
| `send_audio` | `chat_id`, `file_path`, `caption` | required � 2, None | Upload and send an audio file. |
| `get_media_messages` | `limit` | 20 | List stored messages that contain media. |

### Search & Retrieval (4 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `search_messages` | `query`, `chat_id`, `limit` | required, None, 20 | Full-text search across stored messages. |
| `get_messages_by_date` | `chat_id`, `from_date`, `to_date`, `limit` | required � 2, None, 50 | Filter messages by date range (YYYY-MM-DD). |
| `get_pinned_messages` | `chat_id` | required | Retrieve the pinned message in a chat. |
| `get_message_stats` | � | � | Per-chat and overall message statistics. |

### Polls (2 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `send_poll` | `chat_id`, `question`, `options` | all required | Create an anonymous poll (2�10 options). |
| `stop_poll` | `chat_id`, `message_id` | both required | Close voting and return final results. |

### Scheduling (3 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `schedule_message` | `chat_id`, `text`, `send_time` | all required | Schedule a message for a future time. Natural language like "tomorrow 9am" is supported. |
| `list_scheduled_messages` | � | � | Show all pending scheduled messages. |
| `cancel_scheduled_message` | `job_id` | required | Cancel a pending scheduled message by job ID. |

### AI Smart Features (6 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `summarize_chat` | `chat_id`, `limit` | required, 30 | AI summary of recent conversation in bullet points. |
| `detect_urgent_messages` | `limit` | 20 | Identify messages that require immediate attention. |
| `draft_message` | `chat_id`, `context` | both required | Draft a reply message using conversation context. |
| `translate_message` | `composite_id`, `target_language` | both required | Translate a stored message to another language. |
| `sentiment_analysis` | `chat_id`, `limit` | required, 20 | Tone and sentiment analysis of a conversation. |
| `extract_action_items` | `chat_id`, `limit` | required, 30 | Extract todos and action items from a conversation. |

### Cross-Agent (2 tools)

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `forward_to_email` | `composite_id`, `recipient_email`, `subject` | required � 2, None | Forward a Telegram message as an email (requires Email Agent). |
| `share_drive_file` | `chat_id`, `drive_file_id`, `caption` | required � 2, None | Send a Google Drive share link to a Telegram chat (requires Drive Agent). |

**Example prompts:**
- "Send 'meeting confirmed' to chat 123456" ? `send_message`
- "Show my unread Telegram messages" ? `get_unread_messages`
- "Summarize chat 99887766" ? `summarize_chat`
- "Create a poll in 123456: Best day? Monday/Tuesday/Wednesday" ? `send_poll`
- "Schedule a reminder to chat 123456 for tomorrow 8am" ? `schedule_message`
- "Forward Telegram message 1001:5 to alice@example.com" ? `forward_to_email`

---

## Multi-Agent Hub

The Multi-Agent Hub connects the Drive Agent and Email Agent to handle commands that span both services.

### Routing Logic

| Detected keywords | Routed to |
|-------------------|-----------|
| Drive-only keywords (file, download, upload, folder, Drive, etc.) | Drive Agent directly |
| Email-only keywords (email, send, inbox, unread, Gmail, etc.) | Email Agent directly |
| Both drive + email keywords | Both agents via workflow planner |

Single-agent commands skip the workflow planner entirely and go straight to the target agent.

### Cross-Agent Workflows (require both agents)

| Command | What happens |
|---------|-------------|
| "Download the Q3 report and email it to alice@example.com" | Drive downloads ? Email sends with attachment path |
| "Find the invoice PDF and email it to bob@example.com" | Drive searches ? Email composes and sends |
| "Get the project proposal and draft an email to the team" | Drive retrieves ? Email creates draft |
| "Download the latest report and send a summary to manager@co.com" | Drive downloads ? AI summarises content ? Email sends summary |

### Constraints
- Max 6 ReAct loop iterations per agent call
- 45 second timeout per agent execution
- Results from agent 1 are passed as context to agent 2
- Final response is composed after both agents complete

---

## Files Agent Tools

43 tools across 7 categories.

### File & Folder Basics

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `list_directory` | `path`, `show_hidden`, `limit` | required, `False`, `200` | List files in a local directory. |
| `get_file_info` | `path` | required | Metadata for a file or folder (size, dates, type). |
| `copy_file` | `source`, `destination` | both required | Copy a file or folder. |
| `move_file` | `source`, `destination` | both required | Move or rename a file/folder. |
| `delete_file` | `path`, `permanent` | required, `False` | Delete a file. Default sends to Recycle Bin. |
| `create_folder` | `path` | required | Create a directory. |
| `rename_file` | `path`, `new_name` | both required | Rename a file or folder. |
| `open_file` | `path` | required | Open a file with its default application. |

---

### Search

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `search_by_name` | `query`, `directory`, `recursive`, `limit` | required, `"~"`, `True`, `50` | Find files/folders by name pattern. |
| `search_by_extension` | `ext`, `directory`, `recursive`, `limit` | required, `"~"`, `True`, `100` | Find all files with a given extension. |
| `search_by_date` | `directory`, `date_from`, `date_to`, `recursive`, `limit` | required, None, None, `True`, `50` | Find files modified in a date range. |
| `search_by_size` | `directory`, `min_bytes`, `max_bytes`, `recursive`, `limit` | required, None, None, `True`, `50` | Find files by size range. |
| `search_file_all_drives` | `query`, `extensions`, `limit` | required, None, `20` | Search ALL drives (C:, D:, …) for a file by name. |
| `search_files_by_content` | `query`, `directory`, `extensions`, `max_results`, `case_sensitive` | required, `"~"`, None, `50`, `False` | Grep-like search: find files whose text content contains the query. |

---

### Duplicates & Empty Folders

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `find_duplicates` | `directory`, `recursive` | required, `True` | Find duplicate files by hash (quick version). |
| `find_duplicate_files` | `directory`, `recursive`, `min_size_bytes` | required, `True`, `1024` | Full MD5-based duplicate finder — reports groups and wasted space. |
| `find_empty_folders` | `directory`, `recursive` | required, `True` | Find all empty directories. |

---

### Archives & Compression

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `zip_folder` | `folder_path`, `output_path` | required, `""` | Zip an entire folder into a `.zip` archive. |
| `zip_files` | `sources`, `output_path` | both required | Zip a list of files/folders into one archive. |
| `unzip_file` | `archive_path`, `destination` | required, `""` | Extract a zip archive. |
| `list_archive_contents` | `archive_path` | required | List zip contents without extracting. |
| `archive_old_files` | `folder`, `months_old`, `output_zip`, `dry_run` | required, `6`, `""`, `True` | Compress files older than N months. **Always `dry_run=True` first.** |

---

### Disk Usage & System

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `analyze_disk_usage` | `path`, `depth`, `top_n` | required, `2`, `20` | Recursive folder-size breakdown — shows biggest space consumers. |
| `get_drive_info` | — | — | Total/used/free space per drive (C:, D:, …). |
| `list_laptop_structure` | `include_hidden`, `output_file`, `depth` | `False`, `""`, `2` | Full laptop scan: lists all drives and user directories. Saves a `.txt` report. |
| `list_running_apps` | — | — | Show all running processes with PID, memory, and CPU usage. |
| `cleanup_temp_files` | `dry_run` | `True` | Remove OS temp files, `__pycache__` dirs. **Always `dry_run=True` first.** |
| `cleanup_app_caches` | `dry_run` | `True` | Remove Chrome/Edge/Firefox caches and AppData Temp. **Always `dry_run=True` first.** |

---

### File Operations & Utilities

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `batch_rename` | `directory`, `find`, `replace`, `dry_run`, `use_regex`, `extensions` | required×3, `True`, `False`, None | Rename files by find-and-replace in filename. **Always `dry_run=True` first.** |
| `secure_delete` | `path`, `passes` | required, `3` | Overwrite file with random bytes N times then delete. Use for sensitive data. |
| `get_file_hash` | `file_path`, `algorithm` | required, `"md5"` | Compute MD5/SHA256/SHA1 hash of a file. |
| `resolve_shortcut` | `lnk_path` | required | Resolve a Windows `.lnk` shortcut to its target path. |
| `monitor_folder` | `path`, `timeout_seconds`, `poll_interval` | required, `30`, `1.0` | Watch a folder for file changes (created/modified/deleted). |
| `organize_folder` | `directory`, `by`, `dry_run`, `include_hidden` | required, `"extension"`, `True`, `False` | Auto-organise files into subfolders by extension/date/name/size. |

---

### Reports & Delivery

| Tool | Parameters | Default | Description |
|------|-----------|---------|-------------|
| `write_text_file` | `path`, `content` | both required | Write text to a local `.txt` file. |
| `write_pdf_report` | `path`, `title`, `content` | all required | Generate a formatted PDF report. |
| `write_excel_report` | `path`, `sheet_data`, `title` | required×2, `""` | Generate an Excel `.xlsx` workbook. `sheet_data` is `{sheet_name: [list-of-dicts]}`. |
| `deliver_file` | `path` | required | Mark a file for download delivery to the user (Telegram doc / Dashboard button). |

**Example prompts:**
- "What's taking up space in my Downloads?" → `analyze_disk_usage`
- "Find all duplicate files on my PC" → `find_duplicate_files`
- "Search for files containing 'invoice'" → `search_files_by_content`
- "Rename all .txt files in this folder replacing 'draft' with 'final'" → `batch_rename(dry_run=True)` then confirm
- "Securely delete this sensitive file" → `secure_delete`
- "Show me what's eating my browser cache" → `cleanup_app_caches(dry_run=True)`
- "Archive files in my old_projects folder that haven't changed in 6 months" → `archive_old_files(dry_run=True)` then confirm
- "What apps are using the most memory?" → `list_running_apps`
- "What does this .lnk shortcut point to?" → `resolve_shortcut`
- "Watch my Downloads folder for new files" → `monitor_folder`
