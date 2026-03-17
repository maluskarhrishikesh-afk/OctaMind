# Email Agent — Tool Skills

## Category: Send & Compose

### send_email
- **signature**: `send_email(to, subject, message)`
- **description**: Compose and send an email to one or more recipients. Use when the user says "send an email to X", "email X saying Y", "write an email to X about Y", "mail this to X", "drop an email to X", "shoot an email to my boss", "tell X via email that...", "ping X over email". The `to` field accepts a single address or comma-separated list. The message can be plain text or HTML.
- **tags**: send, compose, write, mail, deliver, message, email to, drop a mail, shoot an email, tell via email, ping

### send_email_with_attachment
- **signature**: `send_email_with_attachment(to, subject, message, attachment_path)`
- **description**: Send an email that includes a local file as an attachment. This is the correct tool after generating a report, PDF, spreadsheet, or zip file ONLY when the user explicitly wants email delivery: they say "email", "mail", "forward", mention an inbox, or provide an email address. Do not use this for Telegram/dashboard delivery phrases like "send it to me", "give me the zip", or "share the file here" — those should use current-channel file delivery instead. Provide the full local path to the file to attach.
- **tags**: email attachment, mail attachment, attach and email, forward by email, send PDF by email, generated report email, summary attachment email

### create_draft
- **signature**: `create_draft(to, subject, body)`
- **description**: Save an email as a Gmail draft without sending it immediately. Use when the user says "draft an email to X", "save this as a draft", "prepare an email but don't send yet", "write a draft for later", "create a draft reply", "save my email as draft", "I'll send it later". The draft appears in Gmail Drafts folder.
- **tags**: draft, save, compose, later, prepare, don't send, write for later, save as draft

### list_drafts
- **signature**: `list_drafts()`
- **description**: Retrieve and display all saved Gmail drafts. Use when the user asks "show my drafts", "what drafts do I have", "list unsent emails", "do I have any drafts", "show pending emails", "what have I written but not sent yet", "show draft emails".
- **tags**: drafts, list, saved, pending, unsent, show drafts, what drafts

### send_draft
- **signature**: `send_draft(draft_id)`
- **description**: Send a previously saved Gmail draft email. Use when the user says "send the draft", "send my saved email", "publish the draft", "finalize and send the draft", "go ahead and send it now", "send draft email". Requires the draft_id returned by list_drafts or create_draft.
- **tags**: draft, send, publish, finalize, go ahead, send saved, send draft

### schedule_email
- **signature**: `schedule_email(to, subject, body, send_time)`
- **description**: Schedule an email to be automatically sent at a specific future date and time. Use when the user says "send this email tomorrow at 9am", "schedule an email for Monday", "send this at 3pm on Friday", "delay this email until next week", "send a birthday email on March 15th", "email X at 6pm tonight", "send later", "send at specific time". send_time must be ISO 8601 format e.g. "2026-03-15T09:00:00".
- **tags**: schedule, later, timer, future, delay, planned, tomorrow morning, at 9am, on Monday, send at, send later, specific time

---

## Category: Read & Search

### list_emails
- **signature**: `list_emails(query="in:inbox", max_results=10)`
- **description**: Search and list emails from Gmail using any Gmail search query string. Use when the user asks "find emails from X", "show emails about the project", "search for emails with subject Y", "find unread emails", "show emails from last week", "look up emails mentioning invoice", "find all emails from boss@company.com", or wants the latest inbox emails using a standard inbox query like `in:inbox`. Supports all Gmail operators: from:, to:, subject:, has:attachment, is:unread, before:, after:, label:, etc.
- **tags**: list, search, inbox, query, find, filter, browse, from, subject, unread, label, gmail search, find email, latest inbox emails, newest emails

### get_latest_emails
- **signature**: `get_latest_emails(n_emails=10)`
- **description**: Fetch the most recent emails in the inbox regardless of whether they arrived today. Use when the user says "show latest 10 emails", "list my newest emails", "what are my most recent emails", "show recent inbox messages", or "latest emails in my inbox".
- **tags**: latest emails, newest emails, recent inbox, most recent emails, top emails, latest 10 emails, newest inbox messages

### get_inbox_count
- **signature**: `get_inbox_count()`
- **description**: Return the total number of unread emails currently in the inbox. Use when the user asks "how many unread emails do I have", "what is my email count", "do I have any unread messages", "check my inbox count", "how full is my inbox", "any emails waiting for me", "how many emails unread".
- **tags**: count, unread, inbox, how many, number, check, waiting, full, inbox count

### count_matching_emails
- **signature**: `count_matching_emails(query="")`
- **description**: Return Gmail's server-side count estimate for emails matching a Gmail search query without listing the messages one by one. Use when the user asks "how many emails have I received from X", "count my emails from ClearTax", "how many messages mention invoice", "what is the total number of emails from boss@company.com", or any sender-specific / query-specific email count.
- **tags**: count, total, how many, from sender, by query, sender count, mailbox count, total matches, query count, count emails from, ClearTax, invoice emails

### get_todays_emails
- **signature**: `get_todays_emails(n_emails=50)`
- **description**: Fetch all emails received in the inbox today since midnight local time. Use when the user says "show me today's emails", "what emails did I get today", "list emails received today", "top 4 emails today", "top N emails today", "any new emails since morning", "what came in today", "did I receive anything today", "check today's mail", "morning email roundup", "emails from today", or "today's inbox update". Pass n_emails to limit quantity returned. Returns subject, sender, date, and snippet for each.
- **tags**: today, inbox, received, daily, morning, check, list, show, new, how many, top, what came in, since morning, today's mail, email roundup, inbox update

### search_emails_with_attachments
- **signature**: `search_emails_with_attachments(file_type="")`
- **description**: Find emails that have file attachments, optionally filtered by file type. Use when the user says "find emails with attachments", "do I have any emails with PDFs", "show emails that have files", "find emails with Excel sheets attached", "any emails with documents", "emails with photos", "emails containing files". Optionally pass file_type like "pdf", "xlsx", "jpg" to narrow.
- **tags**: attachment, file, search, find, download, has file, pdf, excel, document, photo, with file, containing attachment

### fetch_emails_to_markdown
- **signature**: `fetch_emails_to_markdown(query="in:inbox", max_results=5, cap=20)`
- **description**: PREFERRED tool for summarizing multiple emails in one call. It fetches all matching emails, saves the raw batch as Markdown, and returns structured email data plus ready-to-export `report_content` containing an overview, additional insights, per-email notes, and action items. Use when the user says "summarize them", "summarize my unread emails", "give me a summary of emails from X", "create a report from these emails", "what do my last 10 emails say", "bulk read emails", "summarize all emails from this week", or "make a PDF summary and send it to me". Do NOT call `summarize_email` in a loop for multi-email requests.
- **tags**: fetch, bulk, markdown, multiple, batch, summarize them, summarize emails, batch summary, report content, create report, read all, overview, insights, efficient, batch read, summary report

---

## Category: Summarize & Analyze

### summarize_email
- **signature**: `summarize_email(message_id)`
- **description**: Generate a concise summary of one specific email by its message ID. Use when the user refers to a single listed email with phrases like "summarize this email", "what does the second one say", "summarize the first one", "give me the gist of this message", "tldr of that email", "brief me on this one", or "what is email X about". For summarizing multiple emails together, use `fetch_emails_to_markdown` instead.
- **tags**: summarize, summary, digest, brief, overview, tldr, what does it say, gist, single email, second one, first one, that email, this email, selected email

### generate_daily_digest
- **signature**: `generate_daily_digest()`
- **description**: Create a comprehensive digest report of all today's emails grouped by sender, priority, and action items. Use when the user asks "give me a daily email digest", "summarize all of today's emails", "morning briefing on emails", "email report for today", "what happened in my inbox today", "daily email summary", "end of day email recap", "full summary of today's inbox".
- **tags**: digest, daily, summary, today, overview, report, morning briefing, end of day, recap, comprehensive, full summary

### generate_weekly_report
- **signature**: `generate_weekly_report()`
- **description**: Generate a full weekly email activity report covering volume, top senders, response rates, and trends. Use when the user asks "email report for this week", "how has my inbox been this week", "weekly email summary", "weekly email statistics", "how many emails did I get this week", "who emailed me most this week", "email activity this week".
- **tags**: weekly, report, activity, statistics, analytics, week, this week, how many this week, trends, volume, weekly summary

### extract_action_items
- **signature**: `extract_action_items(message_id)`
- **description**: Extract and list all to-do items, tasks, and follow-up actions mentioned in a specific email. Use when the user says "what do I need to do from this email", "extract action items from this email", "what tasks are in this email", "what did they ask me to do", "pull out the todos from this email", "any action items in this message", "what follow-ups from this email".
- **tags**: action, todo, task, extract, items, follow-up, what to do, tasks in email, action items, to-do

### get_all_pending_actions
- **signature**: `get_all_pending_actions()`
- **description**: List all pending action items and tasks extracted from recent emails across the inbox. Use when the user asks "what do I need to do based on my emails", "show outstanding email tasks", "list all pending email actions", "what follow-ups do I have from emails", "email todo list", "what tasks are waiting from email", "review all pending actions", "what's on my email to-do list".
- **tags**: pending, action, todo, outstanding, tasks, all emails, follow-up, waiting, review, email tasks, to-do list

### detect_urgent_emails
- **signature**: `detect_urgent_emails()`
- **description**: Surface emails that are flagged or detected as high-priority or urgent using subject line and sender heuristics. Use when the user says "any urgent emails", "are there important emails I should read", "anything critical in my inbox", "high priority emails", "emails needing immediate attention", "is there anything urgent today", "red flag emails", "urgent unread messages".
- **tags**: urgent, important, priority, critical, attention, high priority, immediate, red flag, must read, critical emails

### get_email_stats
- **signature**: `get_email_stats(days=7)`
- **description**: Return detailed email volume statistics for the past N days: total received, sent, unread, top senders, peak hours, label distribution. Use when the user asks "email statistics", "how many emails did I get this week", "email analytics", "inbox metrics", "email activity data", "how active has my inbox been", "how many emails per day on average", "email volume trends".
- **tags**: stats, statistics, volume, analytics, count, metrics, per day, email activity, how many this week, trends, email data

### analyze_email_sentiment
- **signature**: `analyze_email_sentiment(message_id)`
- **description**: Detect the tone and mood of a specific email: urgent, positive, negative, or neutral using fast keyword-based heuristics. Use when the user says "is this email aggressive", "what is the tone of this email", "is this email positive or negative", "is this a rude email", "does this email sound urgent", "check the sentiment", "how does this email feel", "is this a friendly email".
- **tags**: sentiment, tone, mood, positive, negative, urgent, neutral, rude, aggressive, feel, emotion, friendly, hostile

### extract_urls_from_email
- **signature**: `extract_urls_from_email(message_id)`
- **description**: Extract and classify all hyperlinks from an email body into links, tracking pixels, and unsubscribe URLs. Use when the user says "what links are in this email", "extract all URLs from this message", "show me the links", "is there a tracking pixel", "find the unsubscribe link", "are there any suspicious links in this email", "what websites are linked in this email".
- **tags**: urls, links, extract, hyperlinks, tracking, unsubscribe, suspicious links, what links, websites in email

### extract_calendar_events
- **signature**: `extract_calendar_events(message_id)`
- **description**: Detect and extract any calendar event details, meeting times, or date references mentioned in a specific email. Use when the user says "does this email mention a meeting", "extract meeting time from this email", "what event is in this email", "when is the meeting mentioned here", "add this email event to calendar", "what date and time is this email about", "is there a meeting invite in this email".
- **tags**: calendar, event, extract, meeting, date, time, schedule, when is the meeting, event in email, meeting invite

### get_email_chains_summary
- **signature**: `get_email_chains_summary(max_results=10)`
- **description**: List the most active email conversation threads sorted by reply count, with participant counts and latest message preview. Use when the user says "show my busiest email threads", "which conversations have the most replies", "active email chains", "long email threads", "what email discussions are happening", "which threads need attention", "show long conversations".
- **tags**: threads, chains, conversations, active, busy, long, replies, discussion, busiest, most replied, long conversations

### find_unanswered_emails
- **signature**: `find_unanswered_emails(days=3, max_results=20)`
- **description**: Find emails that you sent but have received no reply within the last N days. Use when the user says "what emails am I waiting on a reply for", "any unanswered emails I sent", "follow up on emails with no reply", "who hasn't replied to me", "show emails that need a follow-up", "pending responses from others", "emails I'm waiting on", "no reply yet from X".
- **tags**: unanswered, no reply, waiting, follow-up, pending, sent, response, who hasn't replied, still waiting, expecting reply

---

## Category: Delete & Manage

### delete_emails
- **signature**: `delete_emails(query, max_results=10)`
- **description**: Delete emails matching a Gmail search query by moving them to Trash. Use when the user says "delete all emails from X", "remove these spam emails", "trash emails about Y", "delete old promotional emails", "clean up emails from newsletter X", "remove emails older than 6 months", "get rid of these emails". Always confirm with user before bulk deletion.
- **tags**: delete, remove, trash, cleanup, discard, remove emails, clean up, get rid of, trash emails

### archive_emails
- **signature**: `archive_emails(query, max_results=50)`
- **description**: Remove emails from Inbox without deleting — they move to All Mail for safe archiving and remain searchable. Use when the user says "archive old emails", "clear my inbox", "archive everything from X", "move emails out of inbox", "archive read emails", "de-clutter my inbox", "bulk clear inbox", "archive promotional emails", "inbox zero".
- **tags**: archive, remove, inbox, clear, bulk, cleanup, de-clutter, clear inbox, move out, inbox zero

### empty_trash
- **signature**: `empty_trash()`
- **description**: Permanently and irreversibly delete all emails currently in the Gmail Trash folder. Use when the user says "empty my trash", "permanently delete trashed emails", "clear the trash folder", "wipe trash", "remove all deleted emails permanently". This action CANNOT be undone — always confirm first.
- **tags**: trash, empty, permanent, delete, cleanup, wipe, clear trash, purge, permanently delete

### batch_mark_spam
- **signature**: `batch_mark_spam(query, max_results=50)`
- **description**: Move emails matching a query to Gmail Spam folder in bulk. Use when the user says "mark all emails from X as spam", "send these to spam", "block newsletter X as spam", "filter junk from X to spam", "move promotional emails to spam", "report as junk", "bulk spam emails from X".
- **tags**: spam, junk, block, mark, filter, report, move to spam, bulk spam, mark as junk

### recover_deleted_emails
- **signature**: `recover_deleted_emails(query="", max_results=20)`
- **description**: Search Gmail Trash for emails matching a query and restore them to Inbox. Use when the user says "recover deleted email from X", "restore emails I deleted by mistake", "undo the delete", "recover emails about Y from trash", "get back the email I just deleted", "undelete email", "I accidentally deleted email from X".
- **tags**: recover, restore, undelete, undo, trash, rescue, get back, accidentally deleted, oops deleted

### unsubscribe_email
- **signature**: `unsubscribe_email(message_id)`
- **description**: Extract the List-Unsubscribe header from a specific email and attempt one-click unsubscribe per RFC 8058. Use when the user says "unsubscribe me from this", "stop these emails", "opt out of this newsletter", "unsubscribe from X mailing list", "how do I stop getting these emails", "I want to unsubscribe from this sender", "remove me from this list".
- **tags**: unsubscribe, stop, opt-out, newsletter, mailing list, no more emails, stop receiving, remove me from list

---

## Category: Labels & Organization

### create_label
- **signature**: `create_label(label_name)`
- **description**: Create a new Gmail label (equivalent to a folder or category). Use when the user says "create a label called X", "make a new Gmail folder", "add a label for work emails", "create a category for emails", "set up a label called Finance", "I want a Gmail folder named X". Creates label only if it doesn't already exist.
- **tags**: label, folder, create, category, organize, tag, new label, gmail folder, new category

### list_all_filters_and_labels
- **signature**: `list_all_filters_and_labels()`
- **description**: Show a read-only preview of every Gmail filter plus all user-created and system labels currently in the mailbox. Use when the user says "show me all my filters and labels", "preview my Gmail rules before deleting them", "list all mailbox filters", or "show me all labels first".
- **tags**: list filters, show filters, preview labels, show labels first, list all labels, mailbox preview, preview mailbox rules

### delete_all_filters
- **signature**: `delete_all_filters()`
- **description**: Delete every Gmail filter rule from the mailbox while preserving labels. Use when the user says "delete all the rules applied to my mailbox", "remove all Gmail filters", "clear all email rules", or "delete all mailbox rules but keep labels".
- **tags**: delete all rules, delete all filters, remove mailbox rules, clear gmail filters, delete rules only

### delete_all_filters_and_labels
- **signature**: `delete_all_filters_and_labels()`
- **description**: Delete every Gmail filter rule and every user-created Gmail label from the mailbox in one action. Use when the user says "delete all the rules and labels applied to my mailbox", "remove all my Gmail filters and labels", "clear all mailbox rules", "wipe all email automation and labels", or "reset my Gmail organization". This preserves Gmail system labels like Inbox, Sent, Trash, and Categories.
- **tags**: delete all rules, delete all filters, delete all labels, remove all mailbox rules, clear mailbox organization, wipe email automation, reset gmail labels, remove all filters and labels

### move_emails_to_label
- **signature**: `move_emails_to_label(query, label_name, max_results=50)`
- **description**: Apply a Gmail label to all emails matching a search query and remove them from Inbox. Use when the user says "move all emails from X to label Y", "organize project emails into folder Z", "label these emails as Work", "sort emails from boss into Management label", "put these emails in the Finance folder", "categorize emails about project into X label". Creates the label automatically if needed.
- **tags**: label, move, categorize, organize, filter, sort, move to folder, apply label, put emails in folder

### create_smart_label_rule
- **signature**: `create_smart_label_rule(label_name, from_email="", subject_contains="", to_email="", also_archive=False)`
- **description**: Apply a label to all matching existing emails and create a Gmail filter for all future incoming emails. Use when the user says "automatically label emails from X", "create a rule to always label emails about Y", "auto-organize emails from X into label Z", "set up a Gmail filter so emails from boss go to Management", "smart rule for newsletter X", "always put emails from X in Y folder".
- **tags**: rule, filter, auto, label, smart, automate, organize, automatic label, email filter, always label, gmail rule

### delete_smart_label_rule
- **signature**: `delete_smart_label_rule(from_email="", subject_contains="", to_email="", label_name="")`
- **description**: Delete an existing Gmail filter rule for future incoming emails without changing labels on already processed emails. Use when the user says "remove the rule for emails from X", "delete the Gmail filter from boss", "stop automatically moving emails from X", "undo the auto-label rule", "remove the filter we created earlier", or "stop future emails from going to this folder".
- **tags**: delete rule, remove rule, remove filter, delete gmail filter, stop auto label, undo rule, stop future emails, remove automation

---

## Category: Threads

### thread_mute
- **signature**: `thread_mute(thread_id)`
- **description**: Mute an email conversation thread so future replies bypass the Inbox silently. Use when the user says "mute this thread", "silence this conversation", "stop notifications for this chain", "I don't want to see this thread anymore", "ignore future replies in this thread", "mute this email chain", "don't notify me about this thread".
- **tags**: mute, silence, ignore, thread, conversation, stop notifications, don't bother me, hide thread

### thread_archive
- **signature**: `thread_archive(thread_id)`
- **description**: Archive an entire email conversation thread by removing it from Inbox without deleting. Use when the user says "archive this thread", "clear this conversation from inbox", "remove this email chain from inbox", "done with this thread", "archive the whole conversation", "close this thread", "move thread out of inbox".
- **tags**: archive, thread, conversation, remove, inbox, clear thread, close conversation, move thread

### thread_delete
- **signature**: `thread_delete(thread_id)`
- **description**: Move an entire email conversation thread to Gmail Trash. Use when the user says "delete this thread", "trash this entire conversation", "remove this whole email chain", "delete all emails in this thread", "get rid of this conversation entirely", "permanently remove this thread".
- **tags**: delete, thread, conversation, trash, remove, delete chain, remove all replies, trash thread

---

## Category: Contacts

### sync_contacts
- **signature**: `sync_contacts()`
- **description**: Sync Gmail contacts to the local cache by querying Google People API and mining email interaction history. Use when the user says "refresh my contacts", "update contacts from Gmail", "sync my address book", "my contacts are out of date", "update email contacts", "resync contacts list". Should be run periodically to keep contacts current.
- **tags**: contacts, sync, refresh, people, address book, update, resync, contacts out of date, refresh contacts

### search_contacts
- **signature**: `search_contacts(query)`
- **description**: Search the local contacts cache by name or email address for quick lookup without an API call. Use when the user asks "what is X's email address", "find contact named X", "look up Y's email", "do I have a contact for X", "what email does X use", "search for X in my contacts", "is X in my address book", "contact details for X".
- **tags**: contacts, search, find, lookup, name, email, address, what is X's email, find contact, contact details

### list_contacts
- **signature**: `list_contacts(limit=50)`
- **description**: List the top contacts from the local cache ranked by interaction frequency. Use when the user asks "who are my top contacts", "list my email contacts", "show my address book", "who do I email most frequently", "show my contact list", "who are my frequent email contacts", "display address book".
- **tags**: contacts, list, frequent, top, people, address book, who I email, show contacts, display contacts

### get_frequent_contacts
- **signature**: `get_frequent_contacts()`
- **description**: Return a ranked list of the most frequently emailed contacts based on interaction history. Use when the user asks "who do I email the most", "my most common email contacts", "top email recipients", "who are my regular contacts", "most emailed people", "frequent email collaborators", "who do I communicate with the most".
- **tags**: contacts, frequent, top, regular, common, most emailed, top recipients, communicate with most

---

## Category: Vacation & Forwarding

### set_vacation_responder
- **signature**: `set_vacation_responder(enabled, subject="", body="", start_date="", end_date="", restrict_to_contacts=False)`
- **description**: Enable or disable Gmail Out-of-Office / Vacation auto-reply for incoming emails. Use when the user says "set up out of office", "turn on vacation responder", "enable OOO reply", "set auto-reply for my leave", "I'm going on vacation set up auto-reply", "disable out of office when I return", "turn off OOO", "set vacation message starting Monday".
- **tags**: vacation, ooo, out of office, auto-reply, away, responder, on leave, holiday, enable ooo, disable ooo, vacation message

### get_vacation_responder
- **signature**: `get_vacation_responder()`
- **description**: Check whether Gmail Out-of-Office auto-reply is currently active and show its configured message. Use when the user asks "is my out of office on", "check vacation responder status", "is auto-reply enabled", "what does my OOO message say", "show vacation reply", "is OOO active right now".
- **tags**: vacation, ooo, status, check, auto-reply, is OOO on, what does my ooo say, ooo status

### add_forwarding_address
- **signature**: `add_forwarding_address(forward_to)`
- **description**: Register a new email forwarding destination address in Gmail, which sends a verification email to that address. Use when the user says "add a forwarding address", "I want to forward emails to X", "set up email forwarding to another account", "register X as a forward destination". Address must then be verified via the link in the verification email.
- **tags**: forward, redirect, routing, address, setup, forwarding address, add forward, forward to another account

### enable_email_forwarding
- **signature**: `enable_email_forwarding(forward_to)`
- **description**: Enable automatic forwarding of all incoming Gmail messages to a pre-verified address. Use when the user says "forward all my emails to X", "enable email forwarding", "auto-forward all inbox mail to X", "redirect all incoming email to X", "send copies to my other account". Target address must already be verified.
- **tags**: forward, auto, redirect, all mail, routing, enable forwarding, forward inbox, all emails to

---

## Category: Signature & Templates

### get_signature
- **signature**: `get_signature(send_as_email="me")`
- **description**: Retrieve and display the current Gmail email signature. Use when the user asks "show my email signature", "what is my Gmail signature", "what does my email sign-off say", "check my signature", "view current email footer", "what's at the bottom of my emails".
- **tags**: signature, sign, footer, current, view, show signature, email footer, sign-off

### set_signature
- **signature**: `set_signature(signature_html, send_as_email="me")`
- **description**: Update or replace the Gmail email signature (supports HTML formatting). Use when the user says "change my email signature", "update my signature", "set a new email sign-off", "add my phone number to my signature", "customize my email footer", "create a professional email signature", "update signature to include job title".
- **tags**: signature, set, update, change, footer, customize, professional email signature, sign-off, update footer

### save_email_template
- **signature**: `save_email_template(name, subject, body)`
- **description**: Save a reusable email template with {{variable}} placeholders for repeated use. Use when the user says "save this as an email template", "create a template for monthly reports", "make a reusable email format called X", "save this email format for future use", "I want to create a template called X", "build a recurring email template".
- **tags**: template, save, reusable, pattern, boilerplate, email format, recurring email, create template

### list_email_templates
- **signature**: `list_email_templates()`
- **description**: List all saved email templates with their names. Use when the user asks "show my email templates", "what templates do I have", "list saved email formats", "do I have any email templates", "show reusable emails", "what templates are available".
- **tags**: template, list, saved, available, show templates, what templates, list templates

### send_from_template
- **signature**: `send_from_template(template_name, to, variables={})`
- **description**: Send an email using a saved template, automatically substituting {{variable}} placeholders with provided values. Use when the user says "use the monthly report template to email X", "send the invoice template to Y", "fill in template X and send to Z", "use template X for this email", "apply the welcome template", "send using the report template".
- **tags**: template, send, use, apply, fill, variables, use template, send with template, apply template

---

## Category: Reminders & Follow-up

### send_completion_reminder
- **signature**: `send_completion_reminder(message_id, days=3)`
- **description**: Set a follow-up reminder on a sent email that triggers a self-notification if no reply arrives within N days. Use when the user says "remind me if X doesn't reply in 3 days", "set a follow-up on this sent email", "alert me if no response in 2 days", "track this email for a reply", "follow up if they don't respond", "set a reminder on this message".
- **tags**: reminder, follow-up, track, reply, waiting, alert, if no reply, respond by, follow up reminder

---

## Category: Write & Report

### write_pdf_report
- **signature**: `write_pdf_report(path, title, content)`
- **description**: Generate a formatted multi-page PDF report saved to a local file. Use after `fetch_emails_to_markdown` when the user wants a polished email summary, digest, overview, or analysis document as a PDF. Typical requests include "create a PDF summary", "make a report of these emails", "write the summary as a PDF", "save this digest as a PDF report", or "prepare a summary report I can send". Always call `deliver_file` afterwards if the user wants the file directly, or `send_email_with_attachment` if they want it emailed.
- **tags**: pdf, report, write, generate, summary, document, formatted, polished, create pdf, email report pdf, summary pdf, digest pdf, report document

### write_text_file
- **signature**: `write_text_file(path, content)`
- **description**: Write plain text or Markdown content to a local file and return the file path. Use for lightweight text or Markdown outputs when PDF is not required.
- **tags**: text, write, save, file, output, markdown, txt, plain text, text file

### deliver_file
- **signature**: `deliver_file(path)`
- **description**: Send a locally generated file to the user as a downloadable file via dashboard button or Telegram document. ONLY call AFTER write_pdf_report or write_text_file has already created the file. Use when the user says "send me the file", "download the report", "give me the PDF", "share the document", "I want to download it".
- **tags**: deliver, send, download, share, file, transfer, give me the file, download report, send pdf

---

## Category: Context

### save_context
- **signature**: `save_context(topic, resolved_entities, awaiting="")`
- **description**: Persist the current email list or email data as cross-turn context so the user can refer to emails across multiple conversational turns without repeating themselves. Call after listing emails so the next message can identify "reply to the first one", "forward the second email", "what about email 3". topic="email_listing", resolved_entities={"listed_emails":[...]}, awaiting="email_action".
- **tags**: context, save, cross-turn, persist, session, follow-up, remember emails, refer back, next turn
