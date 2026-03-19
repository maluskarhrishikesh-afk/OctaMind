# Telegram Agent � Setup & Testing Guide

This guide walks you through creating a Telegram bot, connecting it to OctaMind,
and verifying every feature of the Telegram Agent.

---

## Table of Contents

- [Telegram Agent � Setup \& Testing Guide](#telegram-agent--setup--testing-guide)
  - [Table of Contents](#table-of-contents)
  - [Architecture Overview](#architecture-overview)
  - [Step 1 � Create a Telegram Bot via @BotFather](#step-1--create-a-telegram-bot-via-botfather)
  - [Step 2 � Get Your Bot Token](#step-2--get-your-bot-token)
  - [Step 3 � Confirm OctaMind is Running](#step-3--confirm-octamind-is-running)
  - [Step 4 - Add The Telegram Token To A Personal Assistant](#step-4---add-the-telegram-token-to-a-personal-assistant)
  - [Step 5 � Install Python Dependencies](#step-5--install-python-dependencies)
  - [Step 6 - Enable Telegram For A Personal Assistant](#step-6---enable-telegram-for-a-personal-assistant)
  - [Step 7 � Find Your Chat ID](#step-7--find-your-chat-id)
    - [Method A � Message the bot, then ask OctaMind](#method-a--message-the-bot-then-ask-octamind)
    - [Method B � Use the Bot API directly](#method-b--use-the-bot-api-directly)
  - [Testing Each Tool Category](#testing-each-tool-category)
    - [Category 1 � Messaging \& Sending](#category-1--messaging--sending)
    - [Category 2 � Reading \& Inbox](#category-2--reading--inbox)
    - [Category 3 � Search](#category-3--search)
    - [Category 4 � Chats \& Groups](#category-4--chats--groups)
    - [Category 5 � Media](#category-5--media)
    - [Category 6 � Polls](#category-6--polls)
    - [Category 7 � AI Smart Features](#category-7--ai-smart-features)
    - [Category 8 � Scheduling](#category-8--scheduling)
    - [Category 9 � Cross-Agent Actions](#category-9--cross-agent-actions)
  - [Troubleshooting](#troubleshooting)
    - [? "Not configured" badge in the UI](#-not-configured-badge-in-the-ui)
    - [? Bot token test fails (`getMe` error)](#-bot-token-test-fails-getme-error)
    - [? "Show recent messages" returns empty](#-show-recent-messages-returns-empty)
    - [? Poller doesn't start](#-poller-doesnt-start)
    - [? Messages sent but not received back](#-messages-sent-but-not-received-back)
    - [Useful diagnostic commands](#useful-diagnostic-commands)

---

## Architecture Overview

```
Your Telegram account
        �   sends message
        ?
  Telegram Bot API  ----------------------------------------------------------?
  (api.telegram.org)         Long-polling getUpdates (every 2 s)
                                                                               �
                                                              +----------------+
                                                              ?
                                                   OctaMind Background Poller
                                                   (src/telegram/polling/poller.py)
                                                              �
                                                   writes to message_store (in-memory)
                                                              �
  Telegram Bot API ?---- OctaMind Agent ?---- Telegram Agent UI
  (sends messages)       (reads store)         (Streamlit, port 850x)
```

**Key points:**
- **No webhook is needed** - the agent uses Telegram long-polling through `getUpdates`.
- Telegram bots are managed **per Personal Assistant** from the dashboard.
- Each PA bot gets its own poller process, message store, and structured log file.
- **Outbound messages** go directly from the PA poller to the Telegram Bot API.
- **Inbound messages** are persisted to the PA-specific store under `your_data/tg_<pa_id>.json`.
- Duplicate inbound Telegram updates are deduplicated before auto-reply dispatch, so one update should not produce two assistant replies.

---

## Step 1 � Create a Telegram Bot via @BotFather

1. Open Telegram (desktop or mobile) and search for **@BotFather**.

2. Start a chat with BotFather and send:
   ```
   /newbot
   ```

3. BotFather will ask for a **name** (display name, e.g. `OctaMind Agent`).

4. Then it asks for a **username** � must end in `bot` (e.g. `OctaMind_myname_bot`).

5. BotFather replies with:
   ```
   Done! Congratulations on your new bot. You will find it at t.me/OctaMind_myname_bot.
   Use this token to access the HTTP API:
   7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

6. **Copy the token** � you will need it in Step 4.

> ?? The bot username must be globally unique.
> If the name is taken, try adding your initials or a number.

---

## Step 2 � Get Your Bot Token

The token looks like: `7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

- The part before the `:` is the **bot ID**.
- **Keep this token private** � anyone with it can send messages as your bot.
- If you ever leak it, revoke and regenerate with `/revoke` inside BotFather.

---

## Step 3 � Confirm OctaMind is Running

Make sure OctaMind is already set up with a working LLM key:

1. Open `config/settings.json` and confirm `llm_api_keys.GITHUB_TOKEN` is filled in.
2. Start OctaMind:
  ```powershell
  .\.venv\Scripts\python.exe start.py
  ```
   The dashboard opens at `http://localhost:8501`.

> For Telegram access while you are away, start OctaMind with `start.py` or the updated `run_agent_hub.py`, not a raw Streamlit command. Those launchers start the Hub API and, on Windows, the keep-awake helper that prevents idle sleep while OctaMind is running.

> Hard limit: if Windows enters real sleep or hibernation, Telegram cannot reach OctaMind because the laptop stops polling Telegram and stops serving the Hub API. The practical fix is to prevent idle sleep while OctaMind is meant to stay reachable, or use Wake-on-LAN / a permanently-on host.

---

## Step 4 - Add The Telegram Token To A Personal Assistant

OctaMind now expects Telegram bot tokens to be configured on the Personal Assistant that will own that bot.

1. Open the dashboard at `http://localhost:8501`.
2. Create a Personal Assistant or open an existing one.
3. On the assistant card, expand **Add Telegram token** if the bot is not configured yet.
4. Paste the token from BotFather and save it.
5. Start the bot from that same assistant card.

Notes:

- This keeps each Telegram bot scoped to a single Personal Assistant.
- The poller fails fast if the assistant has no valid token.
- The legacy `TELEGRAM_BOT_TOKEN` environment variable still exists for lower-level service calls, but the operational path for PA bots is the per-assistant token saved with the assistant config.

---

## Step 5 � Install Python Dependencies

The Telegram agent uses only the standard `requests` library, which is already
included in OctaMind's base requirements.  No extra packages are needed.

Verify the install is complete:

```powershell
.\.venv\Scripts\python.exe -c "import requests; print('requests OK:', requests.__version__)"
```

---

## Step 6 - Enable Telegram For A Personal Assistant

1. Open the **Agent Hub** at `http://localhost:8501`.

2. Create a Personal Assistant or open an existing one.

3. Open the assistant configuration panel.

4. Enable **Telegram** if it is available in your current deployment configuration.

5. Save the changes.

6. Use the dashboard controls for Telegram on that assistant to start or reconnect the bot integration.

7. Open the assistant workspace and test Telegram-related requests.

> The long-polling loop starts when you press **Start Bot** on the assistant card.
> You will see log lines like `[Poller] Background polling loop started.`
> in `logs/<assistant_name>.log` such as `logs/My_Assistant.log`.
> On Windows, `start.py` and `run_agent_hub.py` also launch a keep-awake helper by default so the laptop stays reachable when locked and idle.

---

## Step 7 � Find Your Chat ID

Most Telegram commands require a **chat_id** (an integer like `123456789`).

### Method A � Message the bot, then ask OctaMind

1. In your Telegram app, open your newly created bot (`t.me/OctaMind_myname_bot`) and send it any message, e.g. `hello`.

2. In the same Telegram chat, type:
   ```
  /status
   ```
  The bot confirms that the PA poller is running and that sleep protection is active when enabled.

3. Note your chat_id � it will be the same every time you message this bot from your account.

### Method B � Use the Bot API directly

Open this URL in your browser (replace `TOKEN` with your bot token):
```
https://api.telegram.org/botTOKEN/getUpdates
```
After sending a message to the bot, the response contains:
```json
{
  "result": [{
    "message": {
      "from": { "id": 123456789 }   ? this is your chat_id
    }
  }]
}
```

> **Groups & channels:** group chat_ids are **negative** integers
> (e.g. `-1001234567890`). Get them the same way after adding the bot to the group.

---

## Testing Each Tool Category

Open the OctaMind Telegram Agent chat and run the commands below.
Replace `YOUR_CHAT_ID` with the chat_id discovered in Step 7.

---

### Category 1 � Messaging & Sending

```
Send hello world to YOUR_CHAT_ID
```
**Expected:** "Message sent" confirmation. Check Telegram � the bot should have sent the message.

```
Send *bold text* and _italic_ to YOUR_CHAT_ID
```
**Expected:** Message delivered with Markdown formatting applied.

```
Reply to message 1 in chat YOUR_CHAT_ID saying Got it!
```
**Expected:** Quoted reply appears in the Telegram chat.

```
Edit message 1 in chat YOUR_CHAT_ID to say Updated text
```
**Expected:** The message text is changed in Telegram.

```
Forward message 1 from chat YOUR_CHAT_ID to YOUR_CHAT_ID
```
**Expected:** A forwarded copy of the message appears.

```
Delete message 1 from chat YOUR_CHAT_ID
```
**Expected:** "Message deleted" confirmation. The message disappears in Telegram.

---

### Category 2 � Reading & Inbox

First, send 2�3 messages to your bot from Telegram, then:

```
Show unread messages
```
**Expected:** A list of messages that haven't been marked as read yet.

```
Show recent messages
```
**Expected:** The last 20 messages received by the bot.

```
Get chat history with YOUR_CHAT_ID
```
**Expected:** Full thread of messages from that chat.

```
Mark message YOUR_CHAT_ID:1 as read
```
**Expected:** "Marked as read." The message no longer appears in unread list.

```
How many messages are in my inbox
```
**Expected:** A count of stored messages.

---

### Category 3 � Search

Send a few messages containing "meeting" and "invoice" to your bot first.

```
Search telegram for meeting
```
**Expected:** Messages containing the word "meeting".

```
Find messages containing invoice
```
**Expected:** Messages with "invoice".

```
Messages from last week in chat YOUR_CHAT_ID
```
**Expected:** Messages filtered by date range.

```
Telegram stats
```
**Expected:** Per-chat breakdown of message counts.

---

### Category 4 � Chats & Groups

```
List my chats
```
**Expected:** All chats that have sent at least one message to the bot.

```
Info about chat YOUR_CHAT_ID
```
**Expected:** Chat metadata (name, type, member count for groups) fetched live from the API.

To test group commands, add your bot to a Telegram group first (the group must grant the bot **administrator** rights for pin/leave actions):

```
Admins of chat GROUP_CHAT_ID
```
**Expected:** List of group administrators.

```
Pin message 1 in chat GROUP_CHAT_ID
```
**Expected:** "Message pinned." (requires bot to be admin).

---

### Category 5 � Media

```
Send photo to YOUR_CHAT_ID from https://picsum.photos/400/300
```
**Expected:** A photo appears in Telegram.

```
Send document to YOUR_CHAT_ID from https://www.w3.org/WAI/WCAG21/Techniques/pdf/pdf-sample.pdf
```
**Expected:** A PDF delivered as a document.

```
Show media messages in chat YOUR_CHAT_ID
```
**Expected:** List of messages that contain photos, videos, or documents.

To get a file download URL, find a `file_id` from a received media message:

```
Get download URL for file_id AgACAgIxxxxxxx
```
**Expected:** A `https://api.telegram.org/file/bot.../` URL.

---

### Category 6 � Polls

```
Create poll in chat YOUR_CHAT_ID asking "Best OctaMind feature?" with options Email Drive Telegram
```
**Expected:** A Telegram poll appears in the chat with three options.

Note the **message_id** of the poll from the confirmation, then:

```
Stop poll message POLL_MESSAGE_ID in chat YOUR_CHAT_ID
```
**Expected:** "Poll closed." results are finalized in Telegram.

---

### Category 7 � AI Smart Features

These require a working LLM key in `settings.json`. Send 5�10 messages to your bot first.

```
Summarize chat YOUR_CHAT_ID
```
**Expected:** A 3�5 sentence AI summary of the conversation.

```
Action items from chat YOUR_CHAT_ID
```
**Expected:** A bulleted list of tasks/commitments extracted from the messages.

```
Draft a message to chat YOUR_CHAT_ID about the upcoming project deadline
```
**Expected:** An AI-written message (shown as a preview � you confirm before sending).

```
Detect urgent messages
```
**Expected:** Messages flagged as time-sensitive or requiring immediate action.

```
Sentiment of chat YOUR_CHAT_ID
```
**Expected:** Mood analysis (e.g. "Generally positive with some neutral exchanges").

```
Translate message YOUR_CHAT_ID:1 to Spanish
```
**Expected:** The message text translated to Spanish.

---

### Category 8 � Scheduling

```
Schedule message to YOUR_CHAT_ID for 1 minute from now saying Scheduled test
```
**Expected:** "Scheduled." After ~1 minute, the message appears in Telegram.

```
Show scheduled messages
```
**Expected:** List of pending scheduled messages with their send times.

```
Cancel scheduled message SCHEDULE_ID
```
**Expected:** "Cancelled." Take the schedule ID from the "Show scheduled messages" output.

---

### Category 9 � Cross-Agent Actions

These require at least one Gmail or Drive agent to also be running.

```
Email message YOUR_CHAT_ID:1 to your@email.com
```
**Expected:** The Telegram message content is sent as an email (requires Gmail agent running).

```
Share Drive file DRIVE_FILE_ID in chat YOUR_CHAT_ID
```
**Expected:** A shareable Drive link is sent to the Telegram chat (requires Drive agent running).

---

## Troubleshooting

### ? "Not configured" badge in the UI

- Check that the Personal Assistant has a saved Telegram bot token.
- Use the assistant card in the dashboard to save the token and then start the bot.

---

### ? Bot token test fails (`getMe` error)

```powershell
.\.venv\Scripts\python.exe -c "
from src.telegram.telegram_service import get_me
print(get_me())
"
```
- If you see `401 Unauthorized` ? the token is invalid. Regenerate with `/revoke` in BotFather.
- If you see a connection error ? check your internet connection or proxy settings.

---

### ? "Show recent messages" returns empty

The PA-specific message store is empty until that assistant's poller receives messages.
1. Confirm the poller is running: the UI should show the poller status in the sidebar.
2. Send a fresh message to the bot from your Telegram app.
3. Wait 2�3 seconds, then run `Show recent messages` again.

---

### ? Poller doesn't start

Check the assistant-specific log file such as `logs/My_Assistant.log` for errors. Common causes:
- Invalid token (poller fails on the first `getUpdates` call).
- Another instance is already polling the same token - Telegram only allows one active `getUpdates` session per bot.

---

### ? Messages sent but not received back

The bot cannot receive messages **in a private chat** unless the user has started the conversation first (sent at least one message to the bot).  Make sure you open the bot in Telegram and send it a message before testing inbound reads.

---

### Useful diagnostic commands

```powershell
# Confirm token is loaded
.\.venv\Scripts\python.exe -c "import json, pathlib; data=json.loads(pathlib.Path('your_data/assistants.json').read_text(encoding='utf-8')); print(bool((((data[0].get('config') or {}).get('telegram') or {}).get('bot_token') or '').strip()))"

# Confirm bot identity
.\.venv\Scripts\python.exe -c "from src.telegram.telegram_service import get_me; import json; print(json.dumps(get_me(), indent=2))"

# Check message store
.\.venv\Scripts\python.exe -c "import json, pathlib; p=pathlib.Path('your_data/tg_pa_61cd192c.json'); print(p.exists())"

# Run the Telegram agent tests
.\.venv\Scripts\python.exe -m pytest tests/telegram/ -q
```

---

*Last updated: March 2026*
