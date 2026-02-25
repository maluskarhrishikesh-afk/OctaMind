# Calendar Agent (Google Calendar) — Setup & Testing Guide

This guide walks you through connecting OctaMind to your Google Calendar and testing every feature of the Calendar Skill.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Step 1 — Google Cloud Project](#step-1--google-cloud-project)
- [Step 2 — Enable the Calendar API](#step-2--enable-the-calendar-api)
- [Step 3 — Add the Calendar Scope](#step-3--add-the-calendar-scope)
- [Step 4 — Configure OctaMind](#step-4--configure-octamind)
- [Step 5 — First-Run Authentication](#step-5--first-run-authentication)
- [Step 6 — Attach the Calendar Skill to a Personal Assistant](#step-6--attach-the-calendar-skill-to-a-personal-assistant)
- [Testing Each Tool Category](#testing-each-tool-category)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
OctaMind Calendar Skill
        │
        │  OAuth 2.0 (config/calendar_token.json)
        ▼
  Google Calendar API v3  ──────────────────────────────────►  Your Google calendars
  (googleapis.com)    list / create / update / delete events
```

**Key points:**
- The Calendar Skill **reuses the same `config/credentials.json`** as Gmail and Google Drive — if you have already gone through Google OAuth setup for email or Drive, the credentials file is already in place
- The first authorization generates `config/calendar_token.json` — subsequent starts refresh it silently
- No webhook needed — the skill queries the Calendar API on demand

---

## Step 1 — Google Cloud Project

If you already set up the Email or Drive agent you already have a project. Skip to **Step 2**.

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create (or select) a project
3. Download `credentials.json` → place it at `config/credentials.json`

---

## Step 2 — Enable the Calendar API

1. In [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Library**
2. Search for **Google Calendar API**
3. Click **Enable**

---

## Step 3 — Add the Calendar Scope

The Calendar Skill requests a single, full-access scope:

```
https://www.googleapis.com/auth/calendar
```

> **If you previously authorized only Gmail or Drive**, you need to re-authorize to add this scope. The easiest way is to delete `config/calendar_token.json` (if it exists) and re-run the auth flow described in Step 5.

**Add the scope to your OAuth Consent Screen (first time only):**

1. **APIs & Services** → **OAuth consent screen**
2. Click **Edit App**
3. Under **Scopes** click **Add or Remove Scopes**
4. Search for `calendar` → check **Google Calendar API** (`.../auth/calendar`)
5. Save

---

## Step 4 — Configure OctaMind

Open `config/settings.json` and confirm the `google` section looks like this (these paths should already be present after recent setup):

```json
"google": {
  "oauth_credentials_path": "config/credentials.json",
  "gmail_token_path": "config/token.json",
  "drive_token_path": "config/drive_token.json",
  "calendar_token_path": "config/calendar_token.json"
}
```

The `calendar_token_path` key is added automatically if you pulled the latest code. If it is missing, add it manually.

---

## Step 5 — First-Run Authentication

Run the Google auth helper from your project root:

```bash
python setup_google_auth.py
```

This opens a browser tab → sign in with the Google account whose calendar you want to use → grant the requested permissions.

**What happens:**
- `config/calendar_token.json` is created
- On subsequent starts the token refreshes automatically
- You can verify authorization worked with:

```bash
python -c "from src.calendar.calendar_auth import is_calendar_authorized; print(is_calendar_authorized())"
```

Expected output: `True`

---

## Step 6 — Attach the Calendar Skill to a Personal Assistant

1. Open the **OctaMind Dashboard** (`http://localhost:8501`)
2. Click the **Configure** tab for your Personal Assistant
3. Under **Skills**, enable **Calendar**
4. Click **💾 Save Changes**

The PA will now route any calendar-related requests through the Calendar Skill.

---

## Testing Each Tool Category

Open the PA chat and try the commands below.  Each command tests one or more Calendar tools.

### 1 — Viewing Today & Tomorrow

```
What's on my calendar today?
```
**Expected:** A formatted agenda for today.

```
Show me tomorrow's events
```
**Expected:** Tomorrow's events listed with times.

### 2 — List & Search

```
List my next 10 upcoming events
```
**Expected:** Up to 10 events with date, time, and title.

```
Search my calendar for "team meeting"
```
**Expected:** All events matching "team meeting".

### 3 — Create an Event

```
Create an event called "Project Review" on Friday at 3pm for 1 hour
```
**Expected:** Confirmation with the new event ID and a link.

### 4 — Quick Add (Natural Language)

```
Quick add: Lunch with Sarah tomorrow at noon
```
**Expected:** Event created using Google's natural-language quickAdd parser.

### 5 — Update an Event

```
Move "Project Review" to 4pm
```
**Expected:** Confirmation that the event time was updated.

### 6 — Delete an Event

```
Delete the meeting called "Project Review"
```
**Expected:** Confirmation of deletion.

### 7 — Recurring Events

```
Create a recurring Monday standup at 9am for 30 minutes, every week for the next 4 weeks
```
**Expected:** Recurring event created.

### 8 — Daily & Weekly Agenda

```
Show me my daily agenda for Monday
```
**Expected:** Full day schedule with event count, free time summary.

```
Show me my calendar for this week
```
**Expected:** Weekly overview grouped by day.

### 9 — Find Free Slots

```
Find a 2-hour free slot this week
```
**Expected:** List of available 2-hour windows during working hours.

### 10 — Conflict Detection

```
Do I have any scheduling conflicts this week?
```
**Expected:** List of overlapping events (or "No conflicts found").

### 11 — Set a Reminder

```
Add a 30-minute reminder to all events tomorrow
```
**Expected:** Reminders added to matching events.

### 12 — Accept / Decline Invites

```
Accept the invite for "Q3 Planning Session"
```
*or*
```
Decline the "Design Review" invite
```
**Expected:** RSVP status updated.

### 13 — List Calendars

```
Show all my calendars
```
**Expected:** List of all Google calendars with IDs and access roles.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| "Calendar is not authorized" | Token file missing or revoked | Run `python setup_google_auth.py` |
| "Calendar API has not been used" | API not enabled in Cloud Console | Enable **Google Calendar API** in APIs & Services |
| "Access blocked: app is not verified" | Consent screen not configured | Add your email as a test user in the OAuth Consent Screen |
| `InsecureTransportError` | Running setup without HTTPS | `set OAUTHLIB_INSECURE_TRANSPORT=1` then re-run the auth helper |
| Token keeps expiring | Credentials revoked by Google | Delete `config/calendar_token.json` and re-authorize |
| Events returned in wrong timezone | Calendar timezone mismatch | Check your Google Calendar timezone setting (Settings → Time Zone) |

### Re-authorizing from scratch

```bash
# Delete the old calendar token
del config\calendar_token.json

# Re-run the auth flow
python setup_google_auth.py
```

---

## Related Guides

- [Email Setup](EMAIL_SETUP.md) — Gmail Agent (shares the same credentials.json)
- [Files Setup](FILES_SETUP.md) — Local Files Agent (no auth required)
