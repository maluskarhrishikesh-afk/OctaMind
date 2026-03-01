# WhatsApp Agent — Setup & Testing Guide

This guide walks you through setting up the Octa Bot WhatsApp Agent from
scratch using the **Meta WhatsApp Cloud API** (the official Business API).

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Step 1 — Create a Meta Developer App](#step-1--create-a-meta-developer-app)
3. [Step 2 — Get Your Credentials](#step-2--get-your-credentials)
4. [Step 3 — Configure Octa Bot](#step-3--configure-Octa Bot)
5. [Step 4 — Install Python Dependencies](#step-4--install-python-dependencies)
6. [Step 5 — Start the Webhook Server](#step-5--start-the-webhook-server)
7. [Step 6 — Expose the Webhook with ngrok](#step-6--expose-the-webhook-with-ngrok)
8. [Step 7 — Register the Webhook in Meta Console](#step-7--register-the-webhook-in-meta-console)
9. [Step 8 — Create a WhatsApp Agent in Octa Bot](#step-8--create-a-whatsapp-agent-in-Octa Bot)
10. [Step 9 — Add Test Recipients](#step-9--add-test-recipients)
11. [Testing Each Tool Category](#testing-each-tool-category)
12. [Production Migration (Optional)](#production-migration-optional)
13. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
Your Phone (WhatsApp)
        ¦  sends message
        ?
  Meta Cloud API ----------? Webhook POST ----------? FastAPI receiver
  (graph.facebook.com)        to ngrok URL             (port 9001)
                                                              ¦
                                                    writes to data/
                                                    whatsapp_messages.json
                                                              ¦
                                                              ?
  Meta Cloud API ?---- Octa Bot Agent ?---- WhatsApp Agent UI
  (sends messages)      (reads store)         (Streamlit, port 850x)
```

**Key points:**
- **Outbound messages** go directly: Octa Bot ? Meta API ? recipient
- **Inbound messages** arrive via webhook: Meta ? your webhook server ? local JSON store
- The local `data/whatsapp_messages.json` file is the single source of truth for message history
- The webhook server runs as a parallel process (port 9001 by default)

---

## Step 1 — Create a Meta Developer App

1. Go to [developers.facebook.com](https://developers.facebook.com) and log in with your Facebook account.

2. Click **My Apps ? Create App**.

3. Select **Business** as the app type.

4. Fill in the app name (e.g. "Octa Bot WhatsApp") and your business email, then click **Create App**.

5. From the app dashboard, click **Add a Product** and select **WhatsApp**.

6. Accept the Terms of Service when prompted.

You now have a WhatsApp Business Platform app.  Meta automatically provisions a **test phone number** for you — this is free and has a limit of 5 recipient numbers.

---

## Step 2 — Get Your Credentials

### 2a. Access Token

1. In your app dashboard, go to **WhatsApp ? API Setup**.

2. Under **Step 1: Select Phone Number**, you'll see the **temporary access token** (valid 24 hours).

   > ?? **For permanent access**, create a System User token:
   > - Go to **Business Settings ? System Users**
   > - Create a system user with **FULL CONTROL** permissions on your app
   > - Generate a token with scope `whatsapp_business_messaging` and `whatsapp_business_management`
   > - This token is permanent (does not expire)

3. Copy the access token — this is your `WHATSAPP_ACCESS_TOKEN`.

### 2b. Phone Number ID

1. Still on **WhatsApp ? API Setup**, look at **Step 1**.

2. The **Phone number ID** is shown below the phone number (it's a long numeric string like `123456789012345`).

3. Copy it — this is your `WHATSAPP_PHONE_NUMBER_ID`.

### 2c. Verify Token (you create this)

Make up any secret string to use as your webhook verify token (example: `Octa Bot_secret_2025`).  You'll enter this both here and in Meta console.

---

## Step 3 — Configure Octa Bot

Open `config/settings.json` and fill in the `whatsapp` section:

```json
{
  "whatsapp": {
    "access_token": "EAAxxxxxxxxxx...",
    "phone_number_id": "123456789012345",
    "verify_token": "Octa Bot_secret_2025",
    "webhook_port": 9001
  }
}
```

| Field | Description |
|-------|-------------|
| `access_token` | Your Meta access token (permanent system user token recommended) |
| `phone_number_id` | The Phone Number ID from WhatsApp ? API Setup (NOT the phone number itself) |
| `verify_token` | Any secret string you choose — must match what you put in Meta console |
| `webhook_port` | Port for the local webhook receiver (default 9001) |

---

## Step 4 — Install Python Dependencies

The WhatsApp agent requires two additional packages:

```bash
# Activate your virtual environment first
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux

# Install dependencies
pip install fastapi uvicorn requests python-dateutil
```

> `fastapi` + `uvicorn` — webhook receiver  
> `requests` — Meta Cloud API calls  
> `python-dateutil` — natural language date parsing for scheduler  

---

## Step 5 — Start the Webhook Server

The webhook server receives inbound messages from Meta.  Start it in a separate terminal:

```bash
# From the project root
python -m uvicorn src.whatsapp.webhook.receiver:app --host 0.0.0.0 --port 9001 --reload
```

Expected output:
```
INFO:     Started server process [XXXX]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:9001 (Press CTRL+C to quit)
```

Verify it's running: http://localhost:9001/health should return `{"status": "healthy"}`.

---

## Step 6 — Expose the Webhook with ngrok

Meta requires a **public HTTPS URL** for the webhook.  Use ngrok to create a tunnel:

```bash
# Install ngrok if not already installed: https://ngrok.com/download
ngrok http 9001
```

You'll see output like:
```
Forwarding  https://abc123def456.ngrok-free.app  ->  http://localhost:9001
```

Copy the HTTPS URL (e.g. `https://abc123def456.ngrok-free.app`) — you'll need it in the next step.

> ?? **ngrok free tier** resets the URL every time you restart.  For persistent URLs, use ngrok's paid plan or deploy the webhook to a cloud server.

---

## Step 7 — Register the Webhook in Meta Console

1. In your Meta app dashboard, go to **WhatsApp ? Configuration**.

2. Under **Webhook**, click **Edit**.

3. Fill in:
   - **Callback URL**: `https://abc123def456.ngrok-free.app/webhook`
   - **Verify Token**: the same string you put in `settings.json` (e.g. `Octa Bot_secret_2025`)

4. Click **Verify and Save**.

   Meta will send a GET request to your webhook URL.  The server will respond with the challenge if the verify token matches.  You should see **"Verified"** in the console.

5. Under **Webhook Fields**, click **Manage** and enable the `messages` field.

6. Click **Done**.

---

## Step 8 — Create a WhatsApp Agent in Octa Bot

1. Start the Octa Bot Agent Hub:
   ```bash
   streamlit run src/agent/ui/dashboard/app.py
   ```

2. In the dashboard, click **Create Agent**.

3. Fill in:
   - **Agent Name**: e.g. `My WhatsApp Agent`
   - **Agent Type**: `WhatsApp Agent` (??)
   - Adjust personality sliders as desired

4. Click **Create**.

5. Once created, click **Launch** on the agent card.  It will open in a new browser tab on its own port (e.g. `http://localhost:8503`).

---

## Step 9 — Add Test Recipients

The Meta sandbox allows you to send messages to up to **5 registered test phone numbers**.

1. In your Meta app, go to **WhatsApp ? API Setup ? Step 2: Send Messages**.

2. Under **To**, click **Manage phone number list**.

3. Add up to 5 phone numbers (these must be real WhatsApp accounts).

4. Each number will receive a verification code — they must opt in.

5. Once registered, you can send messages to these numbers via Octa Bot.

> ?? For production (sending to any number), you need to:
> - Complete Meta Business Verification
> - Submit your app for review
> - Use a real business phone number (not a test number)

---

## Testing Each Tool Category

Once the agent is running and webhook is configured, test the following commands in the WhatsApp Agent chat UI:

### ?? Core Messaging

```
Send hi to 919876543210
```
? Should send "hi" to that number via Meta API.

```
Show recent messages
```
? Shows the last 20 messages from your message store.

```
Show unread messages
```
? Lists messages you haven't read yet.

```
Mark as read wamid.xyz123
```
? Sends a read receipt for that message.

### ?? Contacts & Groups

```
List my contacts
```
? Shows all contacts discovered from your message history.

```
Who do I message most?
```
? Top 10 contacts by message volume.

```
Contact info for 919876543210
```
? Contact profile + recent message preview.

```
Show my groups
```
? All groups that have sent you messages.

### ?? Search & Retrieval

```
Search for invoice
```
? Full-text search across all messages.

```
Get conversation with 919876543210
```
? Full chat thread, oldest-first.

```
Messages from 2025-01-01 to 2025-01-31
```
? Date-range retrieval.

```
Show media messages
```
? All image/video/document/audio messages.

### ?? AI Smart Features

> These require the LLM to be configured (GitHub Models token in settings.json).

```
Summarize my chat with 919876543210
```
? 3-5 bullet point AI summary.

```
Action items from conversation with 919876543210
```
? Extract tasks and to-dos.

```
Draft a message to 919876543210 about the meeting tomorrow
```
? AI-drafted WhatsApp message.

```
How should I reply to message wamid.xyz123?
```
? 3 reply options (brief, professional, detailed).

```
Detect urgent messages
```
? AI scan for urgent/time-sensitive messages.

```
Translate message wamid.xyz123 to Hindi
```
? Language translation.

```
Sentiment of chat with 919876543210
```
? Sentiment score + emotional tone analysis.

### ? Scheduling

```
Schedule message to 919876543210 for tomorrow 9am saying Good morning!
```
? Creates a scheduled entry; the background thread dispatches it at the scheduled time.

```
Show scheduled messages
```
? Lists all pending sends.

```
Cancel scheduled message abc12345
```
? Cancels a queued message.

```
Enable auto-reply with message I'm busy, will reply soon
```
? Enables auto-reply for all inbound messages.

```
Disable auto-reply
```
? Turns off auto-reply.

### ?? Analytics

```
WhatsApp stats for last 30 days
```
? Volume, unread count, busiest day, message type breakdown.

```
Activity report for last week
```
? Messaging patterns by hour and day of week.

```
Who messages me most?
```
? Top 10 senders by message count.

```
Response time for 919876543210
```
? Average response time in minutes.

### ?? Cross-Agent

```
Forward message wamid.xyz123 to alice@example.com
```
? Requires a Gmail agent to be running and configured.

```
Share Drive file 1ABCdef123 with 919876543210
```
? Requires a Drive agent to be running and configured.

---

## Production Migration (Optional)

To send to any WhatsApp number (not just 5 test recipients):

1. **Complete Meta Business Verification** at business.facebook.com.

2. **Submit your app for App Review**.  You'll need:
   - A privacy policy URL
   - Description of how you use the WhatsApp API
   - Screen recordings showing the functionality

3. **Add a real phone number** (cannot be registered on personal WhatsApp).

4. **Apply for a verified business profile** to display your business name.

5. **Upgrade to a paid WhatsApp Business API plan** for higher message volumes.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `WhatsApp credentials not configured` banner | `access_token` or `phone_number_id` missing in settings.json | Fill in both fields |
| Webhook verification fails | Verify token mismatch | Check `verify_token` matches in settings.json AND Meta console |
| Messages not received | Webhook not running or not reachable | Ensure `uvicorn` is running and ngrok is active |
| `RuntimeError: WhatsApp API error` | Invalid access token | Token expired or wrong — regenerate in Meta console |
| `Could not parse send_time` | Unusual date format | Use ISO format: `2025-12-25 09:00` or simple phrases: `tomorrow 9am` |
| Outbound message succeeds but not delivered | Recipient not in test list | Add recipient to test numbers (Step 9) |
| `fastapi is not installed` | Missing dependency | Run `pip install fastapi uvicorn` |
| No messages after webhook setup | Webhook field not enabled | In Meta console: WhatsApp ? Configuration ? Webhook Fields ? enable `messages` |

### Checking the webhook is working

1. Send a WhatsApp message **to** your Meta test number from your phone.
2. Check the webhook server terminal — you should see:
   ```
   INFO: Inbound WhatsApp: from=919876543210 type=text body=Hello...
   ```
3. In the Octa Bot WhatsApp agent, type: `show unread messages`
4. The message you just sent should appear.

### Log files

- Webhook server: console output (uvicorn)
- WhatsApp agent: `whatsapp_agent.log` in the project root
- Message store: `data/whatsapp_messages.json`
- Scheduled messages: `data/whatsapp_scheduled.json`
- Auto-reply config: `data/whatsapp_auto_reply.json`
