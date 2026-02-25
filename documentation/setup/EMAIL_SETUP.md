# Email Agent (Gmail) — Setup & Testing Guide

This guide walks you through connecting OctaMind to your Gmail account and testing every feature of the Email Agent.

---

## Table of Contents

- [Email Agent (Gmail) — Setup \& Testing Guide](#email-agent-gmail--setup--testing-guide)
  - [Table of Contents](#table-of-contents)
  - [Architecture Overview](#architecture-overview)
  - [Step 1 — Create a Google Cloud Project](#step-1--create-a-google-cloud-project)
  - [Step 2 — Enable the Gmail API](#step-2--enable-the-gmail-api)
  - [Step 3 — Create OAuth Credentials](#step-3--create-oauth-credentials)
    - [3a. Configure the OAuth Consent Screen (first time only)](#3a-configure-the-oauth-consent-screen-first-time-only)
    - [3b. Create the OAuth Client ID](#3b-create-the-oauth-client-id)
  - [Step 4 — Place the Credentials File](#step-4--place-the-credentials-file)
  - [Step 5 — Configure OctaMind](#step-5--configure-octamind)
  - [Step 6 — First-Run Authentication](#step-6--first-run-authentication)
    - [Trigger the consent flow](#trigger-the-consent-flow)
    - [What happens](#what-happens)
    - [Token refresh](#token-refresh)
  - [Step 7 — Create a Gmail Agent in OctaMind](#step-7--create-a-gmail-agent-in-octamind)
  - [Testing Each Tool Category](#testing-each-tool-category)
    - [Reading \& Counting](#reading--counting)
    - [Sending \& Drafts](#sending--drafts)
    - [Scheduling](#scheduling)
    - [Attachments](#attachments)
    - [Smart Organisation \& Labelling](#smart-organisation--labelling)
    - [Action Items \& Follow-ups](#action-items--follow-ups)
    - [AI Smart Features](#ai-smart-features)
    - [Contacts \& Analytics](#contacts--analytics)
  - [Also Setting Up Google Drive](#also-setting-up-google-drive)
    - [Enable the Drive API](#enable-the-drive-api)
    - [Create a Drive Agent](#create-a-drive-agent)
  - [Troubleshooting](#troubleshooting)
    - [Useful diagnostic commands](#useful-diagnostic-commands)
    - [Re-authorising from scratch](#re-authorising-from-scratch)

---

## Architecture Overview

```
OctaMind Email Agent
        │
        │  OAuth 2.0 (token.json)
        ▼
  Gmail API  ──────────────────────────────────────────────────────►  Your Gmail inbox
  (googleapis.com)       read / send / draft / label / delete
        │
        ▼
  Local data files
  data/action_items.json   ← extracted tasks from emails
  data/exports/            ← exported contacts (CSV / JSON)
```

**Key points:**
- **No webhook is needed** — the agent polls Gmail on demand rather than receiving push events
- **All data stays local** — OctaMind never stores emails; it calls the Gmail API at query time
- Authentication uses the standard **OAuth 2.0 "Desktop application" flow**
- The same `credentials.json` file is shared by both the Gmail agent and the Drive agent
- Gmail and Drive use **separate token files** (`token.json` vs `drive_token.json`)

---

## Step 1 — Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and sign in with the **same Google account** you want the agent to access.

2. Click the project selector at the top → **New Project**.

3. Give it a name (e.g. "OctaMind") and click **Create**.

4. Make sure the new project is selected in the project selector.

---

## Step 2 — Enable the Gmail API

1. In the left menu, go to **APIs & Services → Library**.

2. Search for **"Gmail API"** and click the result.

3. Click **Enable**.

> If you also want to set up the Drive agent (recommended), repeat for **"Google Drive API"** at this point — it uses the same `credentials.json`.

---

## Step 3 — Create OAuth Credentials

### 3a. Configure the OAuth Consent Screen (first time only)

1. Go to **APIs & Services → OAuth consent screen**.

2. Choose **External** as the user type (unless your account is part of a Google Workspace org).

3. Fill in the required fields:
   - **App name:** OctaMind (or anything you like)
   - **User support email:** your email address
   - **Developer contact information:** your email address

4. Click **Save and Continue** through the Scopes and Test Users screens (no changes needed for a personal project).

5. On the **Test Users** page, add **your own Gmail address** as a test user, then click **Save and Continue**.

### 3b. Create the OAuth Client ID

1. Go to **APIs & Services → Credentials**.

2. Click **Create Credentials → OAuth client ID**.

3. Set **Application type** to **Desktop application**.

4. Give it a name (e.g. "OctaMind Desktop") and click **Create**.

5. A dialog appears with your Client ID and Client Secret — click **Download JSON**.

6. The downloaded file will be named something like `client_secret_xxxxxx.json`.

---

## Step 4 — Place the Credentials File

Rename the downloaded file to `credentials.json` and place it in the `config/` folder of the project:

```
OctaMind/
├── config/
│   ├── credentials.json    ← place it here  ✅
│   ├── settings.json
│   └── ...
```

> The fallback is the project root (`OctaMind/credentials.json`), but `config/credentials.json` is preferred and is already listed in `.gitignore`.

---

## Step 5 — Configure OctaMind

Open `config/settings.json` and verify the `google` section exists (it should already be there):

```json
{
  "google": {
    "oauth_credentials_path": "config/credentials.json",
    "gmail_token_path": "config/token.json",
    "drive_token_path": "config/drive_token.json"
  }
}
```

| Field | Description |
|-------|-------------|
| `oauth_credentials_path` | Path to the `credentials.json` file you downloaded |
| `gmail_token_path` | Where OctaMind stores the Gmail OAuth token (auto-created on first run) |
| `drive_token_path` | Where OctaMind stores the Drive OAuth token (auto-created on first Drive run) |

You do not need to change these values unless you move the credentials file.

---

## Step 6 — First-Run Authentication

The first time any Gmail action is triggered, OctaMind opens a browser window for the OAuth consent flow.

### Trigger the consent flow

Start OctaMind and launch a Gmail agent (see Step 7), then send it any command — for example:

```
How many emails do I have?
```

### What happens

1. A browser window opens automatically showing Google's consent screen.
2. Click your Gmail account (the one you added as a test user in Step 3a).
3. Click **Continue** (you may see a warning that the app is unverified — click "Advanced → Go to OctaMind (unsafe)" for a personal test app).
4. Grant the requested Gmail permissions and click **Allow**.
5. The browser shows a success page; OctaMind saves a `token.json` file in `config/` and retries your command.

**Files created after authentication:**

```
config/
├── credentials.json    ← from Google Cloud (you provided this)
├── token.json          ← auto-generated on first Gmail auth  ✅
```

> ⚠️ Never commit `credentials.json` or `token.json` — they give access to your Gmail account. Both are already in `.gitignore`.

### Token refresh

Tokens refresh automatically when they expire. If the token ever becomes invalid (e.g. you revoked access in your Google Account settings), delete `config/token.json` and send any command — the browser flow will run again.

---

## Step 7 — Create a Gmail Agent in OctaMind

1. Start OctaMind:
   ```bash
   python start.py
   ```

2. Open the Agent Hub at [http://localhost:8501](http://localhost:8501).

3. Click **+ New Agent**.

4. Choose **Gmail** as the agent type.

5. Give it a name and role, e.g.:
   - Name: `inbox-assistant`
   - Role: `Keep my inbox organised and help me reply to emails`

6. Click **Create** then **Start** to launch the agent's chat UI.

7. The agent opens on its own port (e.g. `http://localhost:8503`).

---

## Testing Each Tool Category

Work through the commands below to verify all 47 tools are working correctly.

### Reading & Counting

| What to test | Example command |
|---|---|
| Inbox count | `How many emails do I have?` |
| Today's emails | `Show me today's emails` |
| Unread messages | `List my unread emails` |
| Search by sender | `Emails from alice@example.com` |
| Search by subject | `Find emails about project update` |
| Count unread | `How many unread emails do I have?` |

Expected: A numbered list of emails with IDs, subjects, and senders.

---

### Sending & Drafts

| What to test | Example command |
|---|---|
| Send an email | `Send an email to yourself@gmail.com with subject "Test" saying "Hello from OctaMind"` |
| Create a draft | `Create a draft to yourself@gmail.com about tomorrow's meeting` |
| List drafts | `Show my drafts` |
| Send a draft | `Send draft <draft_id>` |
| Delete a draft | `Delete draft <draft_id>` |

> Use your own email address as recipient for safe testing.

---

### Scheduling

| What to test | Example command |
|---|---|
| Schedule an email | `Schedule an email to yourself@gmail.com saying "Reminder" for 5 minutes from now` |
| List scheduled | `Show my scheduled emails` |
| Cancel scheduled | `Cancel scheduled email <id>` |
| Update scheduled | `Update scheduled email <id> to send tomorrow at 9am` |

> ⚠️ Scheduled emails are software-implemented (stored in a local JSON file). The OctaMind process must be running at the scheduled send time — this is not a native Gmail scheduled send.

---

### Attachments

| What to test | Example command |
|---|---|
| List attachments | `List attachments in email <message_id>` |
| Download attachment | `Download attachment <attachment_id> from email <message_id> to C:/Downloads/file.pdf` |
| Search emails with attachments | `Show emails that have attachments` |

> To get a message ID, first run `List my emails` and copy an ID from the output.

---

### Smart Organisation & Labelling

| What to test | Example command |
|---|---|
| Detect urgent emails | `Are there any urgent emails?` |
| Detect newsletters | `Which emails are newsletters?` |
| Auto-categorise | `Categorise my recent emails` |
| Apply smart labels | `Apply smart labels to my inbox` |
| Auto-prioritise | `Prioritise my unread emails` |
| Create category rules | `Create automatic category rules based on my email patterns` |

---

### Action Items & Follow-ups

| What to test | Example command |
|---|---|
| Extract action items | `Extract action items from email <message_id>` |
| Pending actions | `Show all my pending action items` |
| Mark action complete | `Mark action <task_id> as done` |
| Mark for follow-up | `Mark email <message_id> for follow-up` |
| Pending follow-ups | `Show emails I need to follow up on` |
| Send follow-up reminder | `Send a follow-up reminder for email <message_id>` |
| Dismiss follow-up | `Dismiss follow-up for email <message_id>` |

---

### AI Smart Features

| What to test | Example command |
|---|---|
| Generate reply suggestions | `Suggest replies to email <message_id>` |
| Quick reply | `Quick reply to <message_id> saying I'll call you back` |
| Check unanswered emails | `Which emails haven't I replied to?` |
| Calendar events | `Extract calendar events from email <message_id>` |
| Export to calendar | `Add the event from email <message_id> to my calendar` |

---

### Contacts & Analytics

| What to test | Example command |
|---|---|
| Frequent contacts | `Who do I email most?` |
| Contact summary | `Show me a summary for alice@example.com` |
| VIP suggestions | `Suggest VIP contacts based on my email patterns` |
| Export contacts | `Export my frequent contacts` |
| Email stats | `Give me my inbox statistics` |
| Response time | `What's my average email response time?` |
| Productivity insights | `Show my email productivity insights` |
| Visualise patterns | `Visualise my email patterns` |
| Weekly report | `Generate my weekly email report` |

---

## Also Setting Up Google Drive

The Drive agent uses the **same `credentials.json` file** — no need to go through the Google Cloud setup again.  It gets its own token file (`drive_token.json`), created on first use.

### Enable the Drive API

1. Go to **APIs & Services → Library** in Google Cloud Console.
2. Search for **"Google Drive API"** and click **Enable**.

### Create a Drive Agent

1. In the Agent Hub, click **+ New Agent** and choose **Google Drive**.
2. Give it a name and start it.
3. Send any command (e.g. `List my recent files`) — the browser auth flow will open again, this time requesting Drive access. Grant it.
4. `config/drive_token.json` is created automatically.

**Files after both agents are authenticated:**

```
config/
├── credentials.json     ← shared by Gmail + Drive
├── token.json           ← Gmail token
└── drive_token.json     ← Drive token
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Browser doesn't open on first run | `credentials.json` not found | Check it's at `config/credentials.json`; verify path in `config/settings.json` |
| `Error 400: redirect_uri_mismatch` | Wrong application type | Re-create the OAuth client as **Desktop application**, not Web application |
| `Access blocked: OctaMind has not completed the Google verification process` | App in "testing" mode | In OAuth Consent Screen → Test Users, add your email; or click "Advanced → Go to OctaMind (unsafe)" |
| `Token has been expired or revoked` | Token invalidated | Delete `config/token.json` and send any command to re-authenticate |
| `credentials.json` not found error at startup | File in wrong location | Move it to `config/credentials.json` and confirm `settings.json` points there |
| `Quota exceeded` Gmail API error | Too many calls in a short window | The free Gmail API has usage limits; wait a minute and retry |
| Scheduled email never sent | OctaMind was not running at send time | This is a software scheduler — keep OctaMind running; restart and check `data/scheduled_emails.json` |
| `download_attachment` saves to wrong place | Path is relative to server process | Use an absolute path, e.g. `C:/Users/YourName/Downloads/receipt.pdf` |
| `export_to_calendar` only saves a file | Calendar write scope not granted | The `.ics` file can be imported manually into Google Calendar; full write requires re-auth after adding the Calendar API |
| Agent shows "Rate limit reached" mid-conversation | GitHub Models free tier limit (150 req/day) | Wait for the daily counter to reset; or switch to a paid provider in `config/credentials.json` |

### Useful diagnostic commands

Check that authentication is working from the terminal:

```bash
# From the project root with venv active
python -c "from src.email.gmail_auth import get_gmail_service; svc = get_gmail_service(); print(svc.users().getProfile(userId='me').execute())"
```

If this prints your email address and mailbox stats, the Gmail connection is healthy.

```bash
# Check Drive authentication
python -c "from src.drive.drive_auth import get_drive_service; svc = get_drive_service(); print(svc.about().get(fields='user').execute())"
```

If this prints your name and email, Drive is healthy.

### Re-authorising from scratch

To fully reset OAuth for Gmail:

```bash
# Delete the Gmail token — next command will trigger browser auth again
del config\token.json
```

To fully reset OAuth for Drive:

```bash
del config\drive_token.json
```

To reset both:

```bash
del config\token.json config\drive_token.json
```
