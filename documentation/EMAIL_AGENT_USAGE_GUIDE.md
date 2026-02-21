# OctaMind Email Agent — Usage & Testing Guide

> **Purpose:** How to run, interact with, and test every feature of the Gmail Email Agent.  
> **Last Updated:** 2026-02-21  
> **Covers:** Phase 1 core · Phase 2 smart features · Phase 3 analytics · Phase 4 sub-functions · Automations

---

## 🚀 Getting Started

### Launch Sequence
1. Double-click **`start.exe`** (or run `python start.py`) — this starts the dashboard (default port 8501).
2. In the OctaMind dashboard, click **➕ Create New Agent**, choose type **Gmail**, give it a name, and click **▶️ Start Agent**.
3. The email agent UI opens in a new browser tab on the next available port (8502+).
4. Ensure **`credentials.json`** (OAuth2) is in the project root and you have completed Gmail authentication (`token.json` exists).  
   → See [GMAIL_SETUP.md](GMAIL_SETUP.md) if you need to set up auth.

### Stop
- Click **⏹ Stop** on the dashboard, or run `python stop.py` / double-click **`stop.exe`**.

### Prerequisites Check
```
project root/
├── credentials.json   ← OAuth2 client secret from Google Cloud Console
├── token.json         ← auto-generated on first auth; must include Gmail scopes
├── .env               ← GITHUB_TOKEN for GPT-4o-mini LLM access
└── .venv/             ← Python virtual environment (must be activated)
```

---

## 💬 How the Agent Routes Requests

```
User message
    │
    ▼
handle_conversation()
    ├─ Contains email-action keyword AND email-context keyword?
    │       → execute_with_llm_orchestration()   (LLM picks a tool → Gmail API)
    └─ Pure conversation, greeting, memory query?
            → LLM Chat  (memory-aware, no API calls)
```

**Email-action keywords** (any of these routes to Gmail API):  
`count, list, show, send, delete, summarize, fetch, get, retrieve, find, read, check, view, draft, attachment, schedule, followup, follow-up, categorize, category, label, calendar, meeting, event, priority, urgent, reply, analytics, stats, contact, unsubscribe, newsletter, action item, task, remind, unanswered, pending, insight, download, vip, export, complete, mark done, filter, rule, ics, report, weekly, patterns, chart, visualize, response time, reschedule, dismiss, reminder`

**Email-context keywords** (must also be present):  
`email, inbox, message, unread, gmail, mail, sent, received, draft, folder`

---

## 🧪 Testing Walkthrough — Feature by Feature

Work through each section in order. Where a step says *"use the ID from the step above"*, copy the `` 🆔 ID: ... `` value shown in the previous response.

---

### ✅ 1. Inbox Statistics

| #   | Prompt                                      | Expected output              |
| --- | ------------------------------------------- | ---------------------------- |
| 1.1 | `How many emails do I have?`                | Total, unread, thread counts |
| 1.2 | `Show me my inbox statistics`               | Same structured breakdown    |
| 1.3 | `How many unread emails do I have?`         | Count for unread query       |
| 1.4 | `How many emails from no-reply@github.com?` | Filtered count               |

---

### ✅ 2. List / Search Emails

| #   | Prompt                               | Expected output                     |
| --- | ------------------------------------ | ----------------------------------- |
| 2.1 | `Show me 5 recent emails`            | List with subject, sender, date, ID |
| 2.2 | `List 5 unread emails`               | Unread only                         |
| 2.3 | `Get 3 read emails`                  | Read only                           |
| 2.4 | `What emails did I get today?`       | Today's emails (up to 1000)         |
| 2.5 | `Show emails from john@example.com`  | Filtered by sender                  |
| 2.6 | `List emails with subject "invoice"` | Filtered by subject keyword         |
| 2.7 | `Show emails with label:starred`     | Gmail query syntax passthrough      |

> **Note:** Each result shows `🆔 ID: <message_id>` — copy this for feature tests below.

---

### ✅ 3. Send Email

| #   | Prompt                                                                               | Expected output          |
| --- | ------------------------------------------------------------------------------------ | ------------------------ |
| 3.1 | `Send email to alice@example.com with subject "Test" and body "Hello from OctaMind"` | ✅ Message ID + Thread ID |
| 3.2 | `Mail bob@example.com saying "Quick reminder about 3pm"`                             | ✅ Sent confirmation      |

> **Defect check:** If you see `❌ Error`, verify the address is valid and `token.json` has `gmail.send` scope.

---

### ✅ 4. Delete Emails

| #   | Prompt                                             | Expected output                          |
| --- | -------------------------------------------------- | ---------------------------------------- |
| 4.1 | `Delete 2 emails`                                  | Moves 2 to Trash, shows subject + sender |
| 4.2 | `Delete unread emails from newsletter@example.com` | Filtered delete                          |
| 4.3 | `Trash 3 read emails`                              | Read-only filter delete                  |

> **Note:** Deletion moves to Trash (recoverable within 30 days).

---

### ✅ 5. Summarize Email / Thread

> **Prerequisite:** Run step 2.1 first and copy a `message_id`.

| #   | Prompt                           | Expected output                                                         |
| --- | -------------------------------- | ----------------------------------------------------------------------- |
| 5.1 | `Summarize email <message_id>`   | Subject · From · Date · Summary · Key points · Action items · Sentiment |
| 5.2 | `Summarize thread <thread_id>`   | Thread-level summary                                                    |
| 5.3 | `Generate my daily email digest` | Multi-email digest with priorities                                      |

---

### ✅ 6. Action Items

> **Prerequisite:** A `message_id` from listing emails.

| #   | Prompt                                             | Expected output                          |
| --- | -------------------------------------------------- | ---------------------------------------- |
| 6.1 | `What tasks do I have in email <message_id>?`      | Tasks with priority, deadline, `task_id` |
| 6.2 | `Show all pending action items from recent emails` | Scans 20 recent emails, lists all tasks  |
| 6.3 | `Show my saved tasks`                              | Tasks from `data/action_items.json`      |
| 6.4 | `Show completed tasks`                             | Filter saved tasks by status=complete    |
| 6.5 | `Mark task <task_id> as complete`                  | ✅ Status updated in JSON file            |

> **Defect check:** After 6.1, verify `data/action_items.json` was created and contains tasks with a `task_id` field.

---

### ✅ 7. Smart Reply

> **Prerequisite:** A `message_id`.

| #   | Prompt                                               | Expected output                            |
| --- | ---------------------------------------------------- | ------------------------------------------ |
| 7.1 | `Suggest how I should reply to email <message_id>`   | 3 options: Brief · Professional · Detailed |
| 7.2 | `Reply yes to email <message_id>`                    | ✅ Quick reply sent                         |
| 7.3 | `Send a quick acknowledgement to email <message_id>` | ✅ Acknowledgement sent                     |

> **Quick reply types:** `yes`, `no`, `acknowledged`, `thanks`, `will_do`, `reschedule`

---

### ✅ 8. Drafts

| #   | Prompt                                                                            | Expected output                            |
| --- | --------------------------------------------------------------------------------- | ------------------------------------------ |
| 8.1 | `Draft an email to test@example.com with subject "Draft Test" and body "Testing"` | ✅ Draft ID shown                           |
| 8.2 | `Show my drafts`                                                                  | List of drafts with ID, subject, recipient |
| 8.3 | `Send draft <draft_id>`                                                           | ✅ Draft sent                               |
| 8.4 | `Delete draft <draft_id>`                                                         | ✅ Draft deleted                            |

---

### ✅ 9. Attachments

| #   | Prompt                                                        | Expected output                               |
| --- | ------------------------------------------------------------- | --------------------------------------------- |
| 9.1 | `What attachments are in email <message_id>?`                 | Filename · size · attachment_id               |
| 9.2 | `Find emails with PDF attachments`                            | Emails matching `has:attachment filename:pdf` |
| 9.3 | `Find emails with attachments`                                | All emails with any attachment                |
| 9.4 | `Download attachment <attachment_id> from email <message_id>` | ✅ Save path shown                             |

---

### ✅ 10. Email Categorization & Filter Rules

| #    | Prompt                                                       | Expected output                                           |
| ---- | ------------------------------------------------------------ | --------------------------------------------------------- |
| 10.1 | `What category is email <message_id>?`                       | Category + confidence + Gmail label applied               |
| 10.2 | `Auto-label my recent emails`                                | N processed, M labelled                                   |
| 10.3 | `Create category filter rules`                               | Gmail native filters created from OctaMind label patterns |
| 10.4 | `Create filter rules for senders appearing at least 2 times` | Same with min_occurrences=2                               |

> **Defect check for 10.3/10.4:** Requires prior runs of `apply_smart_labels` to have created `OctaMind/<Category>` Gmail labels.

---

### ✅ 11. Calendar & Meeting Detection

> **Best with:** An email that contains a meeting invite or event details.

| #    | Prompt                                                          | Expected output                                        |
| ---- | --------------------------------------------------------------- | ------------------------------------------------------ |
| 11.1 | `Extract calendar events from email <message_id>`               | Title · date · time · location · participants          |
| 11.2 | `Should I add anything to my calendar from email <message_id>?` | Calendar suggestion or "no event found"                |
| 11.3 | `Export the calendar event from email <message_id> to ICS`      | ✅ `.ics` saved to `data/calendar_exports/`; path shown |

> **Defect check for 11.3:** Open the `.ics` file in Outlook/Apple Calendar to verify it imports correctly.  
> Google Calendar push: requires `https://www.googleapis.com/auth/calendar` scope in `token.json`; otherwise `.ics` only (agent notes this).

---

### ✅ 12. Follow-up Tracking

| #    | Prompt                                                   | Expected output                          |
| ---- | -------------------------------------------------------- | ---------------------------------------- |
| 12.1 | `Remind me to follow up on email <message_id> in 3 days` | ✅ Follow-up set; due date shown          |
| 12.2 | `What follow-ups do I have pending?`                     | Overdue (🔴) + upcoming (🟡) grouped       |
| 12.3 | `Which emails have I not received replies to?`           | Unanswered sent emails older than 3 days |
| 12.4 | `Send me a follow-up reminder for email <message_id>`    | ✅ Self-email sent; check your inbox      |
| 12.5 | `Mark follow-up done for email <message_id>`             | ✅ Status updated                         |
| 12.6 | `Dismiss the follow-up for email <message_id>`           | ✅ Follow-up dismissed                    |

---

### ✅ 13. Email Scheduling

| #    | Prompt                                                                                       | Expected output                      |
| ---- | -------------------------------------------------------------------------------------------- | ------------------------------------ |
| 13.1 | `Schedule email to alice@example.com subject "Scheduled Test" body "Hello" for tomorrow 9am` | ✅ Scheduled ID + send_time shown     |
| 13.2 | `Show my scheduled emails`                                                                   | Queue: ID · to · subject · send time |
| 13.3 | `Reschedule email <scheduled_id> to next Monday 10am`                                        | ✅ New send time confirmed            |
| 13.4 | `Cancel scheduled email <scheduled_id>`                                                      | ✅ Removed from queue                 |

> **Defect check:** After 13.1, verify `data/scheduled_emails.json` is created and contains the entry.

---

### ✅ 14. Contact Intelligence

| #    | Prompt                                   | Expected output                                    |
| ---- | ---------------------------------------- | -------------------------------------------------- |
| 14.1 | `Who do I email most frequently?`        | Top 10 contacts: name · email · count              |
| 14.2 | `Give me a summary for john@example.com` | Total · sent · received · VIP flag                 |
| 14.3 | `Who should be my VIP contacts?`         | Ranked suggestions by frequency                    |
| 14.4 | `Export my contacts to CSV`              | ✅ File at `data/exports/contacts_<timestamp>.csv`  |
| 14.5 | `Export top 50 contacts to JSON`         | ✅ File at `data/exports/contacts_<timestamp>.json` |

> **Defect check for 14.4/14.5:** Open the exported file in Excel/text editor to confirm it is well-formed.

---

### ✅ 15. Priority & Urgency

| #    | Prompt                                      | Expected output                        |
| ---- | ------------------------------------------- | -------------------------------------- |
| 15.1 | `Show me urgent emails that need attention` | List with score 🔴🟡🟢 + reason           |
| 15.2 | `How urgent is email <message_id>?`         | Score 1–10 + reason + urgency keywords |

---

### ✅ 16. Newsletter Management

| #    | Prompt                                          | Expected output           |
| ---- | ----------------------------------------------- | ------------------------- |
| 16.1 | `Find newsletters in my inbox`                  | Senders + email IDs       |
| 16.2 | `How do I unsubscribe from email <message_id>?` | Unsubscribe URL or mailto |

---

### ✅ 17. Email Analytics

| #    | Prompt                                              | Expected output                                                     |
| ---- | --------------------------------------------------- | ------------------------------------------------------------------- |
| 17.1 | `Show my email statistics for the last 30 days`     | Received · Sent · Unread · Avg/day · Busiest day/hour · Top senders |
| 17.2 | `Show email stats for the last 7 days`              | Same for 7-day window                                               |
| 17.3 | `Give me email productivity insights`               | Pattern insights + actionable suggestions                           |
| 17.4 | `Show me email patterns for the last 30 days`       | 4 chart datasets: volume · day of week · hourly · top senders       |
| 17.5 | `Generate my weekly email report`                   | 7-day report: totals · busiest day · top sender · insights          |
| 17.6 | `What was my response time for email <message_id>?` | Latency from received to your reply                                 |

---

## 🧠 Memory & Recall

| Prompt                                 | Expected output                            |
| -------------------------------------- | ------------------------------------------ |
| `Do you remember what we did earlier?` | Working/episodic memory summary            |
| `Did we talk about invoices before?`   | Relevant episodes returned                 |
| `What have we been doing lately?`      | Recent interaction timeline                |
| `What is OAuth?` *(conversational)*    | LLM answers directly — no Gmail API called |

**Memory files** (per agent, under `memory/<agent_id>/`):

| File                 | Purpose                                |
| -------------------- | -------------------------------------- |
| `episodic_memory.md` | Record of every interaction            |
| `working_memory.md`  | Short-term context for current session |
| `long_term.md`       | Distilled persistent knowledge         |
| `semantic_memory.md` | Factual knowledge base                 |
| `personality.md`     | Agent tone and style                   |

---

## 🗣️ Pure Conversational Queries (No Gmail API)

| Prompt                               |
| ------------------------------------ |
| `Hello!` / `Hi there`                |
| `Who are you?` / `What's your name?` |
| `What can you do?`                   |
| `Thank you!`                         |
| `Explain IMAP vs Gmail API`          |

---

## 📁 Generated Files Reference

| Path                                       | Created by           | Contents                                         |
| ------------------------------------------ | -------------------- | ------------------------------------------------ |
| `data/action_items.json`                   | Extract action items | Tasks with `task_id`, status, deadline, priority |
| `data/calendar_exports/<title>_<uuid>.ics` | Export to calendar   | iCalendar file importable into any calendar app  |
| `data/exports/contacts_<ts>.csv`           | Export contacts CSV  | Name, email, sent count, received count          |
| `data/exports/contacts_<ts>.json`          | Export contacts JSON | Same data in JSON format                         |
| `data/scheduled_emails.json`               | Schedule email       | Queue of pending scheduled sends                 |
| `data/followups.json`                      | Mark for follow-up   | Follow-up records with due date and status       |
| `email_agent.log`                          | Always               | Full debug log of every request and tool call    |

---

## ⚙️ Automations

Automations run in the background automatically on a configurable schedule. They are enabled and tuned from the **⚙️ Configure** panel on any Gmail agent card in the OctaMind dashboard.

### How to Enable an Automation
1. Open the OctaMind dashboard (`http://localhost:8501`).
2. Click **⚙️ Configure** on your Gmail agent card.
3. Select the **⚙️ Automations** tab.
4. Toggle the automation on. A ✅ indicator appears when enabled.
5. Click ▶ the ▼ **Settings** expander to set the **⏱ Run Frequency** and any additional parameters.
6. The scheduler picks up the new config within 30 seconds — no restart needed.

### Available Automations

| #   | Automation                       | Description                                                               | Default Frequency | Extra Settings                   |
| --- | -------------------------------- | ------------------------------------------------------------------------- | :---------------: | -------------------------------- |
| 1   | 🗑 **Auto-delete spam**           | Moves all messages in the Spam folder to Trash                            |      15 min       | —                                |
| 2   | 📁 **Auto-archive newsletters**   | Archives already-read Promotions emails out of the inbox                  |      30 min       | Archive label                    |
| 3   | 📋 **Daily email digest**         | Generates a daily summary and saves it to agent memory                    |       24 h        | —                                |
| 4   | ⭐ **Auto-label VIP emails**      | Stars emails from your top-10 frequent contacts                           |      15 min       | —                                |
| 5   | 🚩 **Flag old unread emails**     | Stars unread emails older than N days                                     |       24 h        | Age threshold (days)             |
| 6   | 📊 **Weekly productivity report** | Generates a 7-day analytics report and saves to memory                    |      7 days       | —                                |
| 7   | 🗂 **Auto-categorize emails**     | Applies OctaMind category labels to recent unread emails                  |      30 min       | —                                |
| 8   | 🔕 **Detect promotional senders** | Scans for newsletter senders and logs them in agent memory                |      7 days       | Confidence threshold             |
| 9   | 💬 **Auto-reply (Out of Office)** | Sends a configurable OOO reply to new unread emails, then marks them read |      15 min       | Reply message, Active-until date |
| 10  | 🧹 **Archive old read emails**    | Moves read emails older than N days out of the inbox                      |       24 h        | Age threshold (days)             |

### Run Frequency Options
Each automation can be set to run at: **30 s · 1 min · 5 min · 15 min (default) · 30 min · 1 h · 2 h · 6 h · 12 h · 24 h**

The frequency is stored per-automation in `memory/<agent_id>/automation_config.json` and takes effect on the next scheduler tick (≤ 30 seconds).

### Out of Office — Configuration Tips
- **Reply message**: Plain text body sent as the auto-reply. Keep it concise.
- **Active until**: ISO date (`2026-03-01`) — automation returns "period has ended" and stops replying after this date.
- The automation skips `noreply`, `no-reply`, `donotreply`, `notifications@`, and `mailer-daemon` senders automatically.
- After replying, the original email is marked as **read** so it is not replied to again on the next run.

### Automation Results in Agent Memory
Automations that generate content (`daily_digest`, `weekly_report`, `auto_unsubscribe`, `auto_categorize`) write a summary of their results to the agent's **episodic memory** (`memory/<agent_id>/episodic_memory.md`). You can query these via the chat UI:

| Prompt                               | What you get                               |
| ------------------------------------ | ------------------------------------------ |
| `What did today's email digest say?` | Latest daily digest content from memory    |
| `Show last weekly report`            | Weekly analytics from memory               |
| `What newsletters were detected?`    | Promotional senders logged by the detector |

---

## ⚠️ Troubleshooting

| Symptom                                              | Likely cause                                 | Fix                                                                                            |
| ---------------------------------------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `❌ Error: token expired`                             | OAuth token stale                            | Delete `token.json` and re-authenticate                                                        |
| `❌ Error: insufficient authentication scopes`        | Token missing a scope                        | Delete `token.json`, rerun with all scopes                                                     |
| Agent doesn't route to Gmail API                     | Missing email-context keyword                | Add "email" or "inbox" to your message                                                         |
| Calendar export says "calendar scope missing"        | `token.json` lacks calendar scope            | Re-auth adding `calendar` scope                                                                |
| `data/` files not created                            | Permissions or path issue                    | Ensure the working directory is writable                                                       |
| LLM picks wrong tool                                 | Ambiguous prompt                             | Add the feature keyword explicitly, use IDs                                                    |
| Scheduled emails not sent                            | Scheduler process not active                 | Agent must remain running; restart if needed                                                   |
| Phase 4 tool returns "error: not found"              | Required ID doesn't exist                    | Run the prerequisite step first to get a valid ID                                              |
| Automation ran but OOO reply not received            | Sender matched a skip-pattern                | Check sender address for `noreply`/`no-reply`/`donotreply` — these are intentionally skipped   |
| Automation shows "Sent 0 auto-reply" with errors     | `token.json` missing `gmail.send` scope      | Delete `token.json` and re-authenticate with the full scope list                               |
| Automation frequency change not taking effect        | Old `last_run` prevents immediate re-run     | Wait one full configured interval, or temporarily disable then re-enable the automation        |
| Newsletter archive automation archived unread emails | Occurs on config created before fix (Feb 21) | Toggle automation off then on again to reset; query is now `is:read label:promotions in:inbox` |

---

## 🔗 Related Documentation

- [GMAIL_SETUP.md](GMAIL_SETUP.md) — OAuth2 credentials and scope configuration
- [GMAIL_QUICKSTART.md](GMAIL_QUICKSTART.md) — 5-minute quick start
- [README_GMAIL_INTEGRATION.md](README_GMAIL_INTEGRATION.md) — API integration reference
- [MULTI_AGENT_PLATFORM.md](MULTI_AGENT_PLATFORM.md) — Dashboard and multi-agent setup
- [requirement/email-functionality.md](../requirement/email-functionality.md) — Feature implementation status (all ✅)
- [architecture/memory-system.md](../architecture/memory-system.md) — Memory architecture
