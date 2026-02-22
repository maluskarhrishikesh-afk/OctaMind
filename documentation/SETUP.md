# OctaMind — Setup Guide

Two things need to be configured before running OctaMind:
1. **GitHub Models token** — powers the AI (LLM calls)
2. **Google OAuth credentials** — connects to Gmail and Google Drive

---

## 1. GitHub Models Token (LLM)

OctaMind uses [GitHub Models](https://github.com/marketplace/models) as its LLM provider (free tier: 150 requests/day).

### Get a Token
1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token (classic)** — no special scopes required
3. Copy the token: `ghp_xxxxxxxxxxxx`

### Configure It
Create a `.env` file in the project root:
```
GITHUB_TOKEN=ghp_your_token_here
```

> **Rate limits (free tier):** 15 requests/minute, 150 requests/day.  
> When the limit is hit, agents will show: *"⏳ API rate limit reached. Please wait X minutes."*  
> The counter resets every 24 hours.

### Model Used
Configured in `credentials.json` → `"model"` field. Default: `gpt-4o-mini`.

---

## 2. Google OAuth (Gmail + Drive)

### Step 1 — Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable two APIs:
   - [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)

### Step 2 — OAuth Credentials

1. Go to **Credentials → Create Credentials → OAuth client ID**
2. Application type: **Desktop application**
3. Download the credentials file
4. Rename it `credentials.json` and place it in the project root

### Step 3 — First Run Authentication

On the first run, a browser window opens asking for Google account permissions. Grant access — this creates `token.json` automatically. All subsequent runs use the saved token.

**Files in project root after setup:**
```
credentials.json    ← from Google Cloud (you provide this)
token.json          ← auto-generated on first auth
.env                ← your GitHub token
```

> ⚠️ Never commit `credentials.json`, `token.json`, or `.env` — they are in `.gitignore`.

### Token Refresh

If `token.json` expires or stops working, delete it and restart any agent — the browser auth flow will run again automatically.

---

## 3. Verify Setup

Start the platform and launch an agent:

```bash
python start.py
```

In the Agent Hub, create a Gmail agent and start it. If you can ask *"How many emails do I have?"* and get a real number back, everything is working.
