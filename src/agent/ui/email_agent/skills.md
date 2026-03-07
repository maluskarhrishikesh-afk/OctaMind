# Email Agent — Tool Skills

## Category: Send & Compose

### send_email
- **signature**: `send_email(to, subject, message)`
- **description**: Send an email.
- **tags**: send, compose, write, mail, deliver, message

### send_email_with_attachment
- **signature**: `send_email_with_attachment(to, subject, message, attachment_path)`
- **description**: Send email with a local file attachment.
- **tags**: send, attachment, file, attach, mail, compose

### create_draft
- **signature**: `create_draft(to, subject, body)`
- **description**: Save an email as a draft.
- **tags**: draft, save, compose, later, prepare

### list_drafts
- **signature**: `list_drafts()`
- **description**: List all saved drafts.
- **tags**: drafts, list, saved, pending

### send_draft
- **signature**: `send_draft(draft_id)`
- **description**: Send a previously saved draft.
- **tags**: draft, send, publish, finalize

### schedule_email
- **signature**: `schedule_email(to, subject, body, send_time)`
- **description**: Schedule an email to be sent at a future time (send_time: ISO 8601, e.g. "2026-03-01T14:00:00").
- **tags**: schedule, later, timer, future, delay, planned

## Category: Read & Search

### list_emails
- **signature**: `list_emails(query="in:inbox", max_results=10)`
- **description**: List emails matching a Gmail query string.
- **tags**: list, search, inbox, query, find, filter, browse

### get_inbox_count
- **signature**: `get_inbox_count()`
- **description**: Return unread inbox count.
- **tags**: count, unread, inbox, how many, number

### get_todays_emails
- **signature**: `get_todays_emails()`
- **description**: Fetch emails received today.
- **tags**: today, recent, new, latest, current

### search_emails_with_attachments
- **signature**: `search_emails_with_attachments(file_type="")`
- **description**: Find emails that have file attachments.
- **tags**: attachment, file, search, find, download, has file

### fetch_emails_to_markdown
- **signature**: `fetch_emails_to_markdown(query="in:inbox", max_results=5, cap=20)`
- **description**: PREFERRED for multi-email summarization. Fetches all N emails matching a Gmail query in ONE call, saves them as a Markdown file, and returns file_path + structured list + full content. Do NOT call summarize_email in a loop.
- **tags**: fetch, bulk, markdown, multiple, batch, download, content

## Category: Summarize & Analyze

### summarize_email
- **signature**: `summarize_email(message_id)`
- **description**: Summarise a specific email by its ID.
- **tags**: summarize, summary, digest, brief, overview, tldr

### generate_daily_digest
- **signature**: `generate_daily_digest()`
- **description**: Generate a digest of today's emails.
- **tags**: digest, daily, summary, today, overview, report

### generate_weekly_report
- **signature**: `generate_weekly_report()`
- **description**: Generate a weekly email activity report.
- **tags**: weekly, report, activity, statistics, analytics

### extract_action_items
- **signature**: `extract_action_items(message_id)`
- **description**: Extract to-do items from a specific email.
- **tags**: action, todo, task, extract, items, follow-up

### get_all_pending_actions
- **signature**: `get_all_pending_actions()`
- **description**: List all pending action items from emails.
- **tags**: pending, action, todo, outstanding, tasks

### detect_urgent_emails
- **signature**: `detect_urgent_emails()`
- **description**: Surface emails marked or detected as urgent.
- **tags**: urgent, important, priority, critical, attention

### get_email_stats
- **signature**: `get_email_stats(days=7)`
- **description**: Return email volume statistics for the past N days.
- **tags**: stats, statistics, volume, analytics, count, metrics

### analyze_email_sentiment
- **signature**: `analyze_email_sentiment(message_id)`
- **description**: Detect tone of an email: urgent / positive / negative / neutral. No LLM required — fast keyword-based heuristic.
- **tags**: sentiment, tone, mood, positive, negative, urgent, neutral

### extract_urls_from_email
- **signature**: `extract_urls_from_email(message_id)`
- **description**: Extract all hyperlinks from an email body, classified as: links, tracking_pixels, unsubscribe_urls.
- **tags**: urls, links, extract, hyperlinks, tracking, unsubscribe

### extract_calendar_events
- **signature**: `extract_calendar_events(message_id)`
- **description**: Extract any calendar event details mentioned in a specific email.
- **tags**: calendar, event, extract, meeting, date, time, schedule

### get_email_chains_summary
- **signature**: `get_email_chains_summary(max_results=10)`
- **description**: List the most active email threads sorted by reply count. Useful for 'show me long conversations' or 'which threads need attention'.
- **tags**: threads, chains, conversations, active, busy, long, replies

### find_unanswered_emails
- **signature**: `find_unanswered_emails(days=3, max_results=20)`
- **description**: Surface sent emails that have received no reply in the last N days.
- **tags**: unanswered, no reply, waiting, follow-up, pending, sent

## Category: Delete & Manage

### delete_emails
- **signature**: `delete_emails(query, max_results=10)`
- **description**: Delete emails matching a Gmail query.
- **tags**: delete, remove, trash, cleanup, discard

### archive_emails
- **signature**: `archive_emails(query, max_results=50)`
- **description**: Remove emails matching a Gmail query from Inbox without deleting them (they remain in All Mail). Use for bulk clearing the inbox.
- **tags**: archive, remove, inbox, clear, bulk, cleanup

### empty_trash
- **signature**: `empty_trash()`
- **description**: Permanently delete all emails in Trash.
- **tags**: trash, empty, permanent, delete, cleanup

### batch_mark_spam
- **signature**: `batch_mark_spam(query, max_results=50)`
- **description**: Move emails matching a query to Spam.
- **tags**: spam, junk, block, mark, filter

### recover_deleted_emails
- **signature**: `recover_deleted_emails(query="", max_results=20)`
- **description**: Search Trash for emails matching query and restore them to Inbox. Use when user asks to 'recover', 'restore', or 'undo delete'.
- **tags**: recover, restore, undelete, undo, trash, rescue

### unsubscribe_email
- **signature**: `unsubscribe_email(message_id)`
- **description**: Extract the List-Unsubscribe header from an email and attempt one-click unsubscribe (RFC 8058). Use when user says 'unsubscribe me from X'.
- **tags**: unsubscribe, stop, opt-out, newsletter, mailing list

## Category: Labels & Organization

### create_label
- **signature**: `create_label(label_name)`
- **description**: Create a Gmail label / folder (creates it if it doesn't already exist).
- **tags**: label, folder, create, category, organize, tag

### move_emails_to_label
- **signature**: `move_emails_to_label(query, label_name, max_results=50)`
- **description**: Move emails matching a Gmail query into a label/folder (creates the label automatically if needed and removes them from INBOX).
- **tags**: label, move, categorize, organize, filter, sort

### create_smart_label_rule
- **signature**: `create_smart_label_rule(label_name, from_email="", subject_contains="", to_email="", also_archive=False)`
- **description**: Apply a label to all matching emails and instruct the user how to create a Gmail filter for future emails.
- **tags**: rule, filter, auto, label, smart, automate, organize

## Category: Threads

### thread_mute
- **signature**: `thread_mute(thread_id)`
- **description**: Mute a thread — future replies skip the Inbox.
- **tags**: mute, silence, ignore, thread, conversation

### thread_archive
- **signature**: `thread_archive(thread_id)`
- **description**: Archive an entire thread (remove from Inbox).
- **tags**: archive, thread, conversation, remove, inbox

### thread_delete
- **signature**: `thread_delete(thread_id)`
- **description**: Move an entire thread to Trash.
- **tags**: delete, thread, conversation, trash, remove

## Category: Contacts

### sync_contacts
- **signature**: `sync_contacts()`
- **description**: Sync Gmail contacts to the local cache using Google People API + email interaction mining.
- **tags**: contacts, sync, refresh, people, address book, update

### search_contacts
- **signature**: `search_contacts(query)`
- **description**: Search the local contacts cache by name or email address. Fast — uses the local file, no API call.
- **tags**: contacts, search, find, lookup, name, email, address

### list_contacts
- **signature**: `list_contacts(limit=50)`
- **description**: List the top contacts from the local cache sorted by interaction frequency.
- **tags**: contacts, list, frequent, top, people, address book

### get_frequent_contacts
- **signature**: `get_frequent_contacts()`
- **description**: Return a list of frequently emailed contacts.
- **tags**: contacts, frequent, top, regular, common

## Category: Vacation & Forwarding

### set_vacation_responder
- **signature**: `set_vacation_responder(enabled, subject="", body="", start_date="", end_date="", restrict_to_contacts=False)`
- **description**: Enable or disable Gmail's Out-of-Office / Vacation auto-reply.
- **tags**: vacation, ooo, out of office, auto-reply, away, responder

### get_vacation_responder
- **signature**: `get_vacation_responder()`
- **description**: Check the current state of the Gmail vacation / OOO responder.
- **tags**: vacation, ooo, status, check, auto-reply

### add_forwarding_address
- **signature**: `add_forwarding_address(forward_to)`
- **description**: Register a forwarding address (sends verification email to recipient).
- **tags**: forward, redirect, routing, address, setup

### enable_email_forwarding
- **signature**: `enable_email_forwarding(forward_to)`
- **description**: Enable auto-forwarding of all incoming email to an address (address must be pre-verified).
- **tags**: forward, auto, redirect, all mail, routing

## Category: Signature & Templates

### get_signature
- **signature**: `get_signature(send_as_email="me")`
- **description**: Get the current Gmail signature.
- **tags**: signature, sign, footer, current, view

### set_signature
- **signature**: `set_signature(signature_html, send_as_email="me")`
- **description**: Set the Gmail signature (HTML tags accepted).
- **tags**: signature, set, update, change, footer, customize

### save_email_template
- **signature**: `save_email_template(name, subject, body)`
- **description**: Save a reusable email template. Use {{variable}} placeholders.
- **tags**: template, save, reusable, pattern, boilerplate

### list_email_templates
- **signature**: `list_email_templates()`
- **description**: List all saved email templates.
- **tags**: template, list, saved, available

### send_from_template
- **signature**: `send_from_template(template_name, to, variables={})`
- **description**: Send an email using a saved template, substituting {{key}} placeholders.
- **tags**: template, send, use, apply, fill, variables

## Category: Reminders & Follow-up

### send_completion_reminder
- **signature**: `send_completion_reminder(message_id, days=3)`
- **description**: Set a follow-up reminder on a sent email. Triggers a self-reminder if no reply arrives within N days.
- **tags**: reminder, follow-up, track, reply, waiting, alert

## Category: Write & Report

### write_pdf_report
- **signature**: `write_pdf_report(path, title, content)`
- **description**: Write a formatted PDF report to a local file. Use when creating email summaries, digests, or analysis reports.
- **tags**: pdf, report, write, generate, summary, document, formatted

### write_text_file
- **signature**: `write_text_file(path, content)`
- **description**: Write plain text or Markdown content to a local file. Returns file_path.
- **tags**: text, write, save, file, output, markdown, txt

### deliver_file
- **signature**: `deliver_file(path)`
- **description**: Send a file to the user as a download (dashboard button / Telegram document). Call ONLY after write_pdf_report or write_text_file.
- **tags**: deliver, send, download, share, file, transfer

## Category: Context

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist the current email list for the next turn so the user can say "reply to the first one" without listing again.
- **tags**: context, save, cross-turn, persist, session, follow-up
