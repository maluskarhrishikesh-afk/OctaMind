# Octa Bot — Agents Reference

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

## Telegram Agent

**Script:** `src/agent/ui/telegram_agent_ui.py`  
**Backend:** Telegram Bot API via `src/telegram/`  
**LLM loop:** ReAct (same pattern as Email/Drive/WhatsApp agents)  
**Setup guide:** Add `"telegram": {"bot_token": "..."}` to `config/settings.json`. Get a token from **@BotFather** on Telegram.

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Send** | "Send hi to chat 123456" · "Message -100987654 saying the meeting is moved" |
| **Read** | "Show unread Telegram messages" · "Show recent messages" |
| **Reply** | "Reply to Telegram message 1001:5 saying thanks" |
| **Chats** | "List my Telegram chats" · "Get info about chat 123456" |
| **Media** | "Send photo to 123456" · "Show media messages" |
| **Search** | "Search Telegram for invoice" · "Messages from last week" |
| **Polls** | "Create a poll in chat 123456 about best day" · "Stop poll message 10" |
| **Schedule** | "Schedule Telegram message for tomorrow 9am" · "List scheduled messages" |
| **AI** | "Summarize Telegram chat 123456" · "Draft a Telegram message about project update" |
| **Translate** | "Translate Telegram message 1001:3 to Hindi" |
| **Sentiment** | "Analyse sentiment of chat 123456" · "Find urgent Telegram messages" |
| **Cross-agent** | "Forward Telegram message 1001:5 to bob@example.com" · "Share Drive file abc123 to chat 456" |

### Tools Available (38 total)

```
# Core Messaging (11)
send_message(chat_id, text)
send_media(chat_id, media_type, url, caption)
reply_to_message(chat_id, message_id, text)
forward_message(from_chat_id, to_chat_id, message_id)
edit_message(chat_id, message_id, new_text)
delete_message(chat_id, message_id)
get_messages(limit)
get_unread_messages(limit)
get_chat_history(chat_id, limit)
mark_as_read(composite_id)
send_chat_action(chat_id, action)

# Chats (6)
list_chats()
get_chat_info(chat_id)
get_chat_member_count(chat_id)
pin_message(chat_id, message_id)
unpin_message(chat_id, message_id)
leave_chat(chat_id)

# Media (4)
send_photo(chat_id, file_path, caption)
send_document(chat_id, file_path, caption)
send_audio(chat_id, file_path, caption)
get_media_messages(limit)

# Search & Retrieval (4)
search_messages(query, chat_id, limit)
get_messages_by_date(chat_id, from_date, to_date, limit)
get_pinned_messages(chat_id)
get_message_stats()

# Polls (2)
send_poll(chat_id, question, options)
stop_poll(chat_id, message_id)

# Scheduling (3)
schedule_message(chat_id, text, send_time)
list_scheduled_messages()
cancel_scheduled_message(job_id)

# AI Smart Features (6)
summarize_chat(chat_id, limit)
detect_urgent_messages(limit)
draft_message(chat_id, context)
translate_message(composite_id, target_language)
sentiment_analysis(chat_id, limit)
extract_action_items(chat_id, limit)

# Cross-Agent (2)
forward_to_email(composite_id, recipient_email, subject)
share_drive_file(chat_id, drive_file_id, caption)
```

### Architecture Notes

- **Inbound messages** are fetched via long-polling (`getUpdates`) and stored in `data/telegram_messages.json`
- **Message IDs** in tool calls use composite format `"chat_id:message_id"` (e.g. `"1001:5"`)
- **Poller** runs as a background thread; automatically starts when the agent UI launches
- **Credentials:** Set `TELEGRAM_BOT_TOKEN` env var, or add `"telegram": {"bot_token": "..."}` to `config/settings.json`
- Get a bot token from **@BotFather** on Telegram: `/newbot` command

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

## Calendar Skill (Google Calendar)

**Module:** `src/agent/ui/calendar_agent/orchestrator.py`  
**Backend:** Google Calendar API v3 via `src/calendar/`  
**LLM orchestration:** Single-pass tool selection + response composition (no ReAct loop needed for calendar ops)  
**Setup Guide:** [CALENDAR_SETUP.md](../setup/CALENDAR_SETUP.md)

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **View today/tomorrow** | "What's on my calendar today?" · "Show me tomorrow's events" |
| **List & search** | "List my next 10 events" · "Search my calendar for team meeting" |
| **Date-specific** | "What do I have on Friday?" · "Events for 2025-07-15" |
| **Create** | "Create a meeting called Project Review on Friday at 3pm for 1 hour" |
| **Quick add** | "Add lunch with Sarah tomorrow at noon" (natural-language parse) |
| **Update** | "Move the standup to 10am" · "Change the title to Sprint Planning" |
| **Delete** | "Delete the Project Review meeting" |
| **Recurring** | "Create a weekly standup every Monday at 9am for the next 4 weeks" |
| **Agenda** | "Show my daily agenda for Monday" · "Show this week's calendar" |
| **Free slots** | "Find a 2-hour free slot this week" |
| **Conflicts** | "Do I have any scheduling conflicts this week?" |
| **Reminders** | "Add a 30-minute reminder to my afternoon meeting" |
| **RSVP** | "Accept the Q3 Planning Session invite" · "Decline the Design Review" |
| **Calendars** | "List all my calendars" |

### Tools Available (19 total)

```
list_events(max_results, time_min, time_max, calendar_id, query)
get_todays_events(calendar_id)
get_tomorrows_events(calendar_id)
get_upcoming_events(days, max_results, calendar_id)
get_events_for_date(date, calendar_id)
search_events(query, max_results, calendar_id)
get_event(event_id, calendar_id)
create_event(summary, start_datetime, end_datetime, description, location, attendees, calendar_id)
quick_add_event(text, calendar_id)
update_event(event_id, summary, start_datetime, end_datetime, description, location, calendar_id)
delete_event(event_id, calendar_id)
create_recurring_event(summary, start_datetime, end_datetime, recurrence_rule, description, calendar_id)
list_calendars()
find_free_slots(duration_minutes, days_ahead, calendar_id)
find_conflicts(days_ahead, calendar_id)
get_daily_agenda(date, calendar_id)
get_weekly_agenda(weeks_ahead, calendar_id)
set_reminder(event_id, minutes_before, calendar_id)
accept_invite(event_id, calendar_id)
decline_invite(event_id, calendar_id)
```

### Architecture Notes

- **Reuses `config/credentials.json`** — same Google Cloud project as Gmail and Drive; only one Cloud project needed
- **Token:** `config/calendar_token.json` — generated on first auth, silently refreshed thereafter
- **Skill (stateless):** Calendar has no memory of its own; all context lives in the Personal Assistant that calls it
- **Auth preflight:** If `config/calendar_token.json` is missing or invalid, the orchestrator returns a structured `auth_error` that the PA surfaces as a re-authorization prompt
- **`quick_add_event`:** Uses Google's server-side natural-language parser (same as typing in Google Calendar's "quick add" box)
- **`find_free_slots`:** Computes 30-min-granularity windows across 09:00–17:00 working hours by default
- Scopes required: `https://www.googleapis.com/auth/calendar`

---

## Scheduler / Smart Calendar Agent

**Module:** `src/agent/ui/scheduler_agent/orchestrator.py`  
**Backend:** Google Calendar API v3 via `src/calendar/` (re-uses Calendar Agent's auth token)  
**Registry key:** `scheduler`  
**LLM orchestration:** Single-pass tool selection + response composition

> **Different from Calendar Agent:** The Calendar Agent handles CRUD on individual events. The Scheduler Agent adds an **intelligence layer** — it reasons *over* your calendar to find optimal times, protect focus, and resolve conflicts.

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Find meeting time** | "Find a good time for a 1hr meeting next week" · "When am I free on Wednesday?" |
| **Multi-attendee** | "Find a time for a meeting with alice@example.com and bob@company.com" |
| **Focus blocks** | "Protect my Thursday morning for deep work" · "Block 2 hours for focused coding tomorrow" |
| **Day optimisation** | "Analyse my Monday schedule" · "How can I improve my Wednesday?" |
| **Conflicts** | "Smart-resolve my scheduling conflicts" · "Fix my double bookings this week" |
| **Time blocks** | "Block 2 hours for admin tasks Friday afternoon" · "Add a review block Thursday at 4pm" |
| **Insights** | "How heavy is my meeting load?" · "Give me scheduling insights for the next 2 weeks" |
| **Recurring focus** | "Block every Monday and Wednesday morning 9–11am for deep work" |

### Tools Available (8 total)

```
suggest_meeting_time(title, duration_minutes, within_days, preferred_hours_start, preferred_hours_end, avoid_back_to_back)
find_mutual_availability(attendees, duration_minutes, within_days, preferred_hours_start, preferred_hours_end)
protect_deep_work_block(date_str, duration_hours, focus_topic, preferred_start_hour)
optimize_day_schedule(date_str)                         # read-only analysis + suggestions
smart_reschedule_conflicts(within_days)                 # proposes alternatives, no auto-apply
create_time_block(title, date_str, start_time, duration_minutes, block_type, color)
get_scheduling_insights(within_days)
schedule_recurring_focus_time(title, days_of_week, start_time, duration_minutes)
```

### Architecture Notes

- **Shares the Calendar Agent's auth token** (`config/calendar_token.json`) — no extra OAuth setup
- **`optimize_day_schedule`** is read-only — it returns observations and suggestions without modifying events
- **`smart_reschedule_conflicts`** proposes a plan without applying it — the user reviews and confirms
- **Scoring algorithm:** meeting slots are scored by time-of-day preference, mid-week preference, and back-to-back penalty
- **`find_mutual_availability`** searches your own calendar; for true cross-calendar availability, attendees must share their Google Calendar or reply via invite

---

## File Organizer Agent

**Module:** `src/agent/ui/file_organizer_agent/orchestrator.py`  
**Backend:** Python stdlib (`pathlib`, `shutil`) — no credentials required  
**Registry key:** `file_organizer`  
**Data stores:** `data/organizer_pending_plans.json`, `data/organizer_archival_policies.json`  

> **Different from Files Agent:** The Files Agent performs immediate actions. The File Organizer Agent uses a **conversational approval workflow** — scan → propose → preview → approve → apply. It also manages archival policies and maintains Octa Bot's own `data/` directory.

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Scan & propose** | "Organise my Downloads folder" · "Categorise my Documents by type" |
| **Preview** | "Show me what plan a1b2c3d4 will do" · "Preview the organisation" |
| **Apply** | "Apply plan a1b2c3d4" · "Yes, go ahead with the organisation" |
| **Discard** | "Cancel plan X" · "Forget the organisation plan" |
| **Archive old files** | "Archive files older than 3 months in Downloads" · "Show what would be archived" |
| **App data cleanup** | "Clean up Octa Bot data" · "What can I clean up in the app data?" |
| **Archival policies** | "Auto-archive Downloads files older than 60 days" · "Show my archive rules" |
| **Run policies** | "Run my archival policies" · "Apply all archive rules" |
| **List plans** | "Show pending plans" · "What organisation plans do I have?" |

### Tools Available (10 total)

```
scan_and_propose(directory, strategy, max_files)          # strategy: by_type | by_date | by_name_prefix
preview_plan(plan_id, max_show)                           # show first N moves without applying
apply_plan(plan_id)                                       # MODIFIES FILES — only on explicit confirmation
discard_plan(plan_id)                                     # remove a pending plan
list_plans()                                              # show all pending + recently applied plans
archive_old_files(directory, days_old, destination, dry_run)
cleanup_app_data(dry_run)                                 # Octa Bot data/ directory maintenance
set_archival_policy(directory, days_old, destination, description)
show_archival_policies()
run_archival_policies(dry_run)
```

### Architecture Notes

- **Plans are persisted** to `data/organizer_pending_plans.json` — survive session restarts
- **Never auto-applies:** the LLM is instructed never to call `apply_plan` unless the user explicitly confirms with words like "apply", "yes go ahead", "execute plan X"
- **`dry_run=True`** is the default for all destructive operations
- **Strategies:** `by_type` uses extension→category map; `by_date` groups to `YYYY-MM/` folders; `by_name_prefix` groups to alphabetical prefix folders
- **`cleanup_app_data`** targets Octa Bot's own `data/exports/` (files older than 30 days) and applied plan records

---

## Habit & Health Tracker Agent

**Module:** `src/agent/ui/habit_agent/orchestrator.py`  
**Service:** `src/habit_tracker/habit_service.py`  
**Registry key:** `habit_tracker`  
**Data stores:** `data/habits.json` (habit definitions), `data/habit_logs.json` (daily completion logs)  

> **Completely new** — no overlap with Calendar Agent or Files Agent. Tracks daily habits, streaks, check-ins, and weekly reports. Optionally schedules habit sessions on Google Calendar.

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Add habit** | "Add habit Morning Run" · "Track daily meditation at 7am" · "Start a reading habit" |
| **Log completion** | "Log morning run done" · "Mark yoga complete" · "I finished reading today, ran 5km" |
| **Check-in** | "Daily check-in" · "What habits are pending today?" |
| **View habits** | "Show my habits" · "What habits do I have?" · "Today's habit list" |
| **Streaks** | "What's my meditation streak?" · "How many days in a row for running?" |
| **Reports** | "Weekly habit report" · "How did I do this week?" · "Last week's habits" |
| **Analytics** | "30-day stats for morning run" · "Analyse my yoga habit" |
| **Calendar sync** | "Schedule my run on Thursday at 7am on Google Calendar" |
| **Delete** | "Remove habit Morning Run" · "Stop tracking yoga" |

### Tools Available (9 total)

```
add_habit(name, frequency, target_time, description, unit, target_count)
  # frequency: "daily" | "weekly" | "weekdays" | "weekends"
log_completion(habit_name, completed, count, notes, log_date)
get_habits(include_inactive)                         # lists all habits with today's completion status
daily_checkin()                                      # shows pending habits for today
get_streak(habit_name)                               # current + longest streak
get_weekly_report(weeks_back)                        # weeks_back=0: this week, 1: last week
get_habit_analytics(habit_name, days)                # detailed stats for one habit over N days
delete_habit(habit_name)                             # deactivates (preserves logs)
schedule_habit_on_calendar(habit_name, date_str, time, duration_minutes)
```

### Data Format

`data/habits.json` — flat list of habit objects:
```json
{
  "id": "a1b2c3d4",
  "name": "Morning Run",
  "frequency": "daily",
  "target_time": "07:00",
  "unit": "km",
  "target_count": 5,
  "active": true,
  "created_at": "2026-02-25"
}
```

`data/habit_logs.json` — flat list of daily log entries:
```json
{
  "habit_id": "a1b2c3d4",
  "habit_name": "Morning Run",
  "date": "2026-02-25",
  "completed": true,
  "count": 5,
  "notes": "Felt great",
  "logged_at": "2026-02-25T07:45:00"
}
```

### Architecture Notes

- **No credentials required** for all core tools
- **Google Calendar integration** (`schedule_habit_on_calendar`) requires Calendar to be authorised
- **Duplicate log handling:** logging a habit twice on the same day *updates* the existing entry (last log wins)
- **Streak calculation:** counts consecutive days backwards from today; today counts even if not yet logged
- **`delete_habit`** sets `active=False` and preserves all logs for analytics continuity

---

## Personal Assistant Hub

**Script:** `src/agent/ui/personal_assistant_ui.py`  
**Purpose:** Commands that span both Gmail and Google Drive in one sentence

### Routing Logic

| Classified as | Action |
|--------------|--------|
| Email only | Calls Email Agent’s ReAct orchestrator directly |
| Drive only | Calls Drive Agent’s ReAct orchestrator directly |
| WhatsApp only | Calls WhatsApp Agent’s ReAct orchestrator directly |
| Telegram only | Calls Telegram Agent’s ReAct orchestrator directly |
| Files only | Calls Files Agent’s ReAct orchestrator directly |
| Cross-agent | Runs the NL workflow planner → sequential step execution |
| Neither | Casual chat via `llm.chat()` |

### Cross-Agent Example Commands

```
"Download the Q3 report from Drive and email it to alice@example.com"
"Find the invoice PDF and send it to bob@example.com"
"Save the attachment from email {id} to my Drive"
"Email me a Drive storage report"
"Share the roadmap with everyone who emailed me today"
"Send a WhatsApp message to Alice with the Drive file link"
"Forward the Telegram message to my email"
"Zip my Downloads folder and upload it to Google Drive, then email me the link"
```

### Workflow Step References

In multi-step workflows, the output of one step can be piped to the next using `{output_key}` syntax. For example:

```
Step 1: download_file → output_key: "downloaded_file"
Step 2: send_email_with_attachment → attachment_path: "{downloaded_file}"
```

---

## Browser Agent (Web Browsing)

**Orchestrator:** `src/agent/ui/browser_agent/orchestrator.py`  
**Service layer:** `src/browser/browser_service.py`  
**Setup Guide:** [BROWSER_AGENT_SETUP.md](BROWSER_AGENT_SETUP.md)  
**Dependencies:** `beautifulsoup4`, `requests` (optional but recommended) — no API keys required

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Browse** | "Open https://news.ycombinator.com" · "What does the Python docs say about decorators?" |
| **Search** | "Search for latest AI news" · "Look up Python string formatting" |
| **Extract** | "Read the full article at [URL]" · "Get the text from this page" |
| **Links** | "What links are on hacker news?" · "List all URLs on this page" |
| **Metadata** | "What is the description of openai.com?" · "Page metadata for github.com" |
| **Find** | "Does the page mention 'pricing'?" · "Find where it talks about fees" |
| **Structured** | "Extract tables from Wikipedia's stock market page" |
| **Download** | "Download the PDF from [URL] to data/downloads/report.pdf" |
| **Summarise** | "Summarise https://arxiv.org/abs/xxxx" |

### Tools Available

| Tool | Parameters | Description |
|------|-----------|-------------|
| `browse_url` | `url`, `max_chars=3000` | Fetch readable content from any URL |
| `search_web` | `query`, `num_results=5` | DuckDuckGo web search |
| `extract_text` | `url`, `max_chars=5000` | Clean long-form text extraction |
| `get_page_links` | `url`, `internal_only=False` | All hyperlinks on a page |
| `get_page_title` | `url` | Page `<title>` tag |
| `get_page_metadata` | `url` | Meta description, og:tags, keywords |
| `find_on_page` | `url`, `search_term`, `context_chars=200` | Phrase search within page |
| `extract_structured_data` | `url` | HTML tables and lists |
| `download_file_from_url` | `url`, `save_path` | Download binary/text file |
| `summarize_page` | `url`, `max_words=200` | Extractive page summary |

### Limitations

- JavaScript-heavy single-page apps (SPAs) may return minimal content (HTTP-only, no JS engine)
- Login-required pages are not accessible
- Some sites block automated requests (returns HTTP 403)

---

## Stock Market Analysis Agent

**Orchestrator:** `src/agent/ui/stock_agent/orchestrator.py`  
**Service layer:** `src/stock_market/stock_service.py`  
**Setup Guide:** [STOCK_AGENT_SETUP.md](STOCK_AGENT_SETUP.md)  
**Dependencies:** `yfinance` — free, no API key required  
**Scope:** READ-ONLY analysis. No buy/sell, no order placement, no brokerage integration.

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Quotes** | "What is Apple's stock price?" · "TSLA quote" · "How is Amazon trading?" |
| **History** | "6 months of AAPL prices" · "MSFT historical data for 1 year" |
| **Technical** | "Technical analysis for NVDA" · "Is Tesla overbought?" · "MACD for SPY" |
| **Risk** | "How risky is TSLA?" · "Risk score for Amazon" · "Volatility of NVDA" |
| **Patterns** | "Chart patterns for AAPL" · "Support and resistance for NFLX" |
| **Portfolio** | "Analyse my portfolio: AAPL MSFT JPM JNJ" · "How diversified is my holding?" |
| **Suggestions** | "Any issues with my portfolio?" · "Rebalancing hints for AAPL TSLA META" |
| **Sentiment** | "News sentiment for Tesla" · "What are people saying about Apple?" |
| **Compare** | "Compare AAPL vs GOOGL vs MSFT" · "Side-by-side: TSLA vs RIVN" |
| **Market** | "How is the market today?" · "Market overview" · "Is the S&P500 up?" |

### Tools Available

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_quote` | `symbol` | Price, change, P/E, market cap, sector |
| `get_historical_data` | `symbol`, `period="1mo"`, `interval="1d"` | OHLCV bars |
| `technical_analysis` | `symbol`, `period="6mo"` | RSI, MACD, Bollinger, SMA |
| `risk_score` | `symbol`, `period="1y"` | Volatility, Beta, VaR, Sharpe, 1-10 score |
| `pattern_detection` | `symbol`, `period="3mo"` | Support/resistance, trend, candlesticks |
| `portfolio_analysis` | `symbols: list`, `period="1y"` | Sector allocation, correlation, diversification |
| `portfolio_suggestions` | `symbols: list` | Rebalancing hints, concentration warnings |
| `sentiment_analysis` | `symbol` | NLP sentiment on latest news headlines |
| `compare_stocks` | `symbols: list` | Side-by-side metric table |
| `market_overview` | `indices: list` | SPY/QQQ/DIA/IWM/VIX snapshot + mood |

### Technical Indicators

| Indicator | Bullish | Neutral | Bearish |
|-----------|---------|---------|---------|
| RSI | < 30 (oversold) | 30–70 | > 70 (overbought) |
| MACD histogram | > 0 | ≈ 0 | < 0 |
| Bollinger | Below lower band | Mid-range | Above upper band |
| Price vs SMA | Above | — | Below |

### PDF Report Generation

Use `generate_full_report` to produce a full multi-page A4 PDF analysis:

| Command example | What it does |
|---|---|
| "Full analysis of TCS" | Runs all 10 analyses, builds PDF, returns file path |
| "Stock report for Reliance" | Same — triggers PDF build |
| "Email me the AAPL report at me@example.com" | Builds PDF then emails it (requires Gmail auth) |

The PDF cover page includes an **Analyst Quick Snapshot** with: Technical Signal, Risk Level, Quality Score, Sentiment, 52W Price Position, and an Analyst Verdict (BUY / HOLD / AVOID) derived from composite scoring.

### Disclaimer

All output is informational and educational only. Not financial advice. Always consult a qualified financial advisor before making investment decisions.

---

## LinkedIn Agent

**Orchestrator:** `src/agent/ui/linkedin_agent/orchestrator.py`  
**Service layer:** `src/linkedin/linkedin_service.py`  
**UI:** `src/agent/ui/linkedin_agent/app.py`  
**Setup Guide:** [LINKEDIN_SETUP.md](../setup/LINKEDIN_SETUP.md)  
**Credentials:** LinkedIn OAuth `access_token` in `config/settings.json["linkedin"]`

### What It Can Do

| Category | Example commands |
|----------|----------------|
| **Text posts** | "Post on LinkedIn about the benefits of AI automation" |
| **Image posts** | "Generate an image and post about Octa Bot on LinkedIn" |
| **Video posts** | "Post this video to LinkedIn: /path/to/video.mp4" *(upload only — no video generation)* |
| **Article sharing** | "Share this article on LinkedIn: https://..." |
| **AI content** | "Write a professional LinkedIn post about productivity tools" |
| **AI images** | "Generate a LinkedIn banner image for a FinTech product" *(requires OpenAI DALL·E 3 key)* |
| **Scheduling** | "Schedule a post for Monday 9 AM about team culture" |
| **Analytics** | "How is my LinkedIn page performing this month?" |
| **Post metrics** | "Show analytics for my last post" |
| **OAuth setup** | "Get LinkedIn authorization URL" |

### Tools Available

```
create_text_post(text, visibility)
create_image_post(text, image_path, image_title, image_description, visibility)
create_video_post(text, video_path, video_title, video_description, visibility)
create_article_post(text, article_url, article_title, article_description, visibility)
delete_post(post_id)
list_published_posts(count)
generate_ai_post_content(topic, tone, length, include_hashtags, target_audience)
generate_ai_image(prompt, output_path, size)
schedule_post(text, scheduled_time, post_type, ...)
list_scheduled_posts()
cancel_scheduled_post(scheduled_id)
get_post_analytics(post_id)
get_page_analytics(granularity, start_days_ago)
get_org_followers()
get_profile()
get_access_token_url(state)
exchange_code_for_token(code)
```

### ⚠️ Key Limitations

| Limitation | Detail |
|---|---|
| **No video generation** | `create_video_post` uploads an existing local MP4 — it cannot generate a video from text/script |
| **AI images need OpenAI key** | `generate_ai_image` uses DALL·E 3 which requires a **paid OpenAI API key**, not GitHub Models |
| **LinkedIn OAuth required** | All posting/analytics tools need a valid LinkedIn `access_token` configured |
| **Token expiry** | LinkedIn tokens expire every 60 days — re-run the OAuth flow to refresh |

### Required LinkedIn API Scopes

| Scope | Purpose |
|-------|---------|
| `w_member_social` | Post as personal profile |
| `w_organization_social` | Post as company page |
| `r_organization_social` | Page analytics, followers |
| `r_liteprofile` | Profile info |

---

## Agent Memory

Every agent (Email, Drive, WhatsApp, Telegram, Files, or any custom agent) maintains its own memory folder at `memory/<agent_id>/`. Memory is loaded as context for every LLM call, so agents remember past interactions, user preferences, and learned patterns.

Only production agents have persistent memory folders. Test or temporary agents do not retain memory across sessions.

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
