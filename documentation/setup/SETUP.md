# OctaMind Setup Guide

Use this guide for the shared setup required by most OctaMind deployments. Feature-specific setup steps are documented in the dedicated guides under `documentation/setup/`.

## What You Usually Need

Before running OctaMind, configure:

1. **LLM provider credentials** in `config/settings.json`
2. **Google OAuth credentials** in `config/credentials.json` if you will use Gmail, Drive, or Calendar
3. **Optional feature sections** in `config/settings.json` for WhatsApp or LinkedIn if you enable those skills

## 1. Create `config/settings.json`

Copy the example file:

```bash
copy config\settings.example.json config\settings.json
```

The example already includes the current top-level sections used by the codebase:

- `llm_api_keys`
- `google`
- `runtime`
- `whatsapp`
- `linkedin`

## 2. Configure An LLM Provider

OctaMind defaults to GitHub Models, but the active provider is selected through `config/providers.json`. Credentials are loaded from `config/settings.json` first and can fall back to environment variables.

Minimal GitHub Models example:

```json
{
  "llm_api_keys": {
    "GITHUB_TOKEN": "ghp_your_token_here"
  }
}
```

### GitHub Models token

1. Open GitHub settings.
2. Go to developer settings.
3. Create a classic personal access token.
4. Put the token under `llm_api_keys.GITHUB_TOKEN`.

If you switch providers later, keep `config/providers.json` and `config/settings.json` in sync.

## 3. Configure Google OAuth

If you will use Gmail, Drive, or Calendar:

1. Create or reuse a Google Cloud project.
2. Enable the Gmail API, Google Drive API, and Google Calendar API as needed.
3. Create OAuth credentials.
4. Save the credentials file as `config/credentials.json`.

OctaMind supports three completion modes for Google auth:

- local browser callback on the OctaMind machine
- Telegram `/authcomplete <url>` completion
- public HTTPS callback when `google.oauth_callback_base_url` is configured

Typical files after first successful auth:

```text
config/credentials.json
config/token.json
config/drive_token.json
config/calendar_token.json
config/settings.json
```

Never commit real credentials or token files.

If a token becomes invalid, delete the corresponding token file and run the auth flow again.

## 4. Optional Feature Configuration

### WhatsApp

Fill the `whatsapp` section in `config/settings.json` if you enable the WhatsApp skill. The full webhook and Meta Cloud API setup is covered in [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md).

### LinkedIn

Fill the `linkedin` section in `config/settings.json` if you enable the LinkedIn skill. The OAuth and page setup is covered in [LINKEDIN_SETUP.md](LINKEDIN_SETUP.md).

### Runtime

The `runtime.keep_awake_when_running` flag controls whether the Windows keep-awake helper is launched with OctaMind.

## 5. Start OctaMind

Run:

```bash
python start.py
```

What this does today:

- starts the Streamlit Agent Hub on port `8501`
- starts the Hub API on port `8502`
- starts the Windows keep-awake helper when enabled
- starts the memory consolidation background loop
- opens the dashboard in your browser when ready

To stop the tracked runtime processes:

```bash
python stop.py
```

If you want only the dashboard process for local UI work:

```bash
python run_agent_hub.py
```

## 6. Verify The Installation

1. Start OctaMind.
2. Open the Agent Hub.
3. Create a Personal Assistant.
4. Enable the skills you want that assistant to use.
5. Open the assistant workspace and try a real request.

Good smoke tests:

- Email: "How many unread emails do I have?"
- Calendar: "What is on my calendar today?"
- Files: "Search my laptop for PDF invoices"
- Browser: "Search the web for the latest Python release"

## Setup Guides By Feature

- [EMAIL_SETUP.md](EMAIL_SETUP.md)
- [CALENDAR_SETUP.md](CALENDAR_SETUP.md)
- [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)
- [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md)
- [FILES_SETUP.md](FILES_SETUP.md)
- [BROWSER_AGENT_SETUP.md](BROWSER_AGENT_SETUP.md)
- [STOCK_AGENT_SETUP.md](STOCK_AGENT_SETUP.md)
- [LINKEDIN_SETUP.md](LINKEDIN_SETUP.md)

## Important Repository Reality

The repository does not currently include a single unified dependency manifest such as `requirements.txt` or `pyproject.toml`. If you are onboarding a fresh machine, use the existing team Python environment or install the dependencies required by the features you plan to enable.
