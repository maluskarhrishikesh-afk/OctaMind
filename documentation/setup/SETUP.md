# Octa Bot Setup Guide

Two things are typically configured before running Octa Bot:
1. **LLM provider credentials** in `config/settings.json`
2. **Google OAuth credentials** in `config/credentials.json` if you use Gmail, Drive, or Calendar

---

## 1. LLM Provider Credentials

Octa Bot uses [GitHub Models](https://github.com/marketplace/models) as its LLM provider (free tier: 150 requests/day).

### Configure `config/settings.json`

Copy `config/settings.example.json` to `config/settings.json` and fill in the values you need.

For the default GitHub Models setup, add your token under `llm_api_keys`:

```json
{
   "llm_api_keys": {
      "GITHUB_TOKEN": "ghp_your_token_here"
   }
}
```

`config/providers.json` controls which provider is active. `config/settings.json` supplies the credentials and provider-specific paths.

### Get a GitHub Models Token
1. Go to **GitHub ? Settings ? Developer settings ? Personal access tokens ? Tokens (classic)**
2. Click **Generate new token (classic)** � no special scopes required
3. Copy the token: `ghp_xxxxxxxxxxxx`

> **Rate limits (free tier):** 15 requests/minute, 150 requests/day.  
> When the limit is hit, agents will show: *"? API rate limit reached. Please wait X minutes."*  
> The counter resets every 24 hours.

### Model Used
Configured via `config/providers.json`. The API key is read from `config/settings.json` first and falls back to environment variables.

---

## 2. Google OAuth (Gmail + Drive + Calendar)

### Step 1 � Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the APIs you need:
   - [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
   - [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)

### Step 2 � OAuth Credentials

1. Go to **Credentials ? Create Credentials ? OAuth client ID**
2. Use **Desktop application** for the default local-callback flow
3. If you plan to use a public HTTPS callback, create a **Web application** client instead and add your public callback URL
4. Download the credentials file
5. Rename it `credentials.json` and place it at `config/credentials.json`

### Step 3 � First Run Authentication

On the first use of Gmail, Drive, or Calendar, Octa Bot opens the Google consent flow and stores a token for that service automatically.

Supported completion modes:
- Local browser callback on the OctaMind machine
- Telegram `/authcomplete <url>` pasteback flow
- Public HTTPS callback when `google.oauth_callback_base_url` is configured in `config/settings.json`

**Typical files after setup:**
```
config/credentials.json      # from Google Cloud (you provide this)
config/token.json            # Gmail token
config/drive_token.json      # Drive token
config/calendar_token.json   # Calendar token
config/settings.json         # your runtime credentials and paths
```

> Never commit `config/settings.json`, `config/credentials.json`, or token files.

### Token Refresh

If a token expires or stops working, delete the relevant file and re-run auth:
- `config/token.json` for Gmail
- `config/drive_token.json` for Drive
- `config/calendar_token.json` for Calendar

---

## 3. Verify Setup

Start the platform and launch an agent:

```bash
python start.py
```

In the Agent Hub, create a Gmail or Calendar-enabled assistant and try a real request such as *"How many emails do I have?"* or *"What is on my calendar today?"*.
