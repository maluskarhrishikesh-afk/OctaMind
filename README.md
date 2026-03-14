# OctaMind

OctaMind is a multi-agent personal assistant platform that lets you operate Gmail, Google Drive, Google Calendar, Telegram, WhatsApp, LinkedIn, local files, web browsing, habit tracking, and stock analysis through natural language. The product centers on Personal Assistants, which hold identity, memory, and long-running context, while individual skills stay focused on execution.

## What Ships Today

- Agent Hub dashboard for creating, configuring, and launching Personal Assistants
- Embedded Personal Assistant workspace inside the dashboard
- Skill routing across email, drive, files, calendar, scheduler, file organizer, habit tracking, browser, stock market, LinkedIn, WhatsApp, and Telegram
- Persistent assistant memory plus cross-channel history merging for dashboard and Telegram
- Local runtime state and generated artifacts under `your_data/`
- Public research artifacts in `research/`

## Current Skill Catalog

| Skill | Primary use cases |
|------|-------------------|
| Email | Read, search, summarize, draft, reply, schedule, and report on Gmail |
| Google Drive | Search, upload, download, share, organize, and analyze Drive files |
| Files | Search across drives, inspect local files, zip or unzip, write reports, and deliver files back into the current chat |
| Calendar | Create, update, delete, list, and search Google Calendar events |
| Scheduler | Find the best slots, protect focus time, resolve conflicts, and optimize schedules |
| File Organizer | Propose folder cleanup or archival plans and apply them only after approval |
| Habit Tracker | Track habits, streaks, reports, and optional calendar-backed habit sessions |
| Browser | Search the web, extract page content, inspect metadata, and download public files |
| Stock Market | Read-only quotes, technicals, risk analysis, portfolio analysis, and PDF reports |
| LinkedIn | Draft, publish, schedule, and analyze LinkedIn posts and page activity |
| WhatsApp | Send, search, summarize, schedule, and analyze WhatsApp conversations |
| Telegram | Send, search, summarize, schedule, and manage Telegram chats and polls |

## Architecture At A Glance

- `start.py` launches the Streamlit Agent Hub on `http://localhost:8501`
- `start.py` also launches the Hub API on `http://localhost:8502`
- On Windows, a keep-awake helper is started by default unless disabled in `config/settings.json`
- Memory consolidation runs as a background process on startup and continues on an 8-hour loop
- Telegram pollers are managed per Personal Assistant from the dashboard, not directly by `start.py`
- Runtime outputs, operational state, archives, reports, and generated artifacts are stored under `your_data/`

## Quick Start

### 1. Prepare configuration

Copy the example settings file and add the credentials for the features you plan to use:

```bash
copy config\settings.example.json config\settings.json
```

At minimum, configure:

- `llm_api_keys.GITHUB_TOKEN` or another supported provider key
- `config/credentials.json` if you will use Gmail, Drive, or Calendar
- `whatsapp` settings if you will use the WhatsApp skill
- `linkedin` settings if you will use the LinkedIn skill

### 2. Use the project Python environment

This repository does not currently ship a single locked dependency manifest such as `requirements.txt` or `pyproject.toml`. Use the existing project environment you have been developing with, or install only the dependencies required by the features you enable. The setup guides below call out feature-specific packages where needed.

### 3. Start OctaMind

```bash
python start.py
```

This starts:

- the Agent Hub dashboard on port `8501`
- the Hub API on port `8502`
- the Windows keep-awake helper when enabled
- the background memory consolidation loop

To stop all tracked processes:

```bash
python stop.py
```

If you only want to run the dashboard directly for local development:

```bash
python run_agent_hub.py
```

## How To Use It

1. Open the Agent Hub in your browser.
2. Create a Personal Assistant.
3. Enable only the skills that assistant should use.
4. Open the embedded assistant workspace.
5. Ask for work in natural language, including cross-skill requests such as downloading a file and emailing it, finding time and booking a meeting, or generating a stock report and sending it onward.

## Repository Layout

```text
OctaMind/
├── start.py                         # Launch dashboard, API, keep-awake helper, consolidation loop
├── stop.py                          # Stop dashboard and tracked agent processes
├── run_agent_hub.py                 # Direct dashboard runner
├── config/                          # Example settings, provider config, OAuth tokens and credentials
├── docs/                            # Public website assets
├── documentation/                   # Setup, architecture, status, and reference documentation
├── errors/                          # Persistent JSON error registry and local error notes
├── research/                        # Published research PDFs only
├── src/
│   ├── agent/                       # Hub, routing, runtime management, memory, UI, logging
│   ├── browser/                     # Web browsing and page extraction services
│   ├── calendar/                    # Google Calendar integration
│   ├── drive/                       # Google Drive integration
│   ├── email/                       # Gmail integration
│   ├── files/                       # Local filesystem tools
│   ├── habit_tracker/               # Habit tracking services
│   ├── linkedin/                    # LinkedIn publishing and analytics
│   ├── stock_market/                # Market data, analysis, and reports
│   ├── telegram/                    # Telegram service layer
│   └── whatsapp/                    # WhatsApp service layer
├── tests/                           # Unit, integration, manual, and channel-specific tests
└── your_data/                       # Live assistant state, generated outputs, archives, reports
```

## Documentation Map

### Start here

- [documentation/setup/SETUP.md](documentation/setup/SETUP.md): shared setup for provider keys and Google OAuth
- [documentation/reference/AGENTS.md](documentation/reference/AGENTS.md): current skill catalog and routing surface
- [documentation/status/IMPLEMENTATION_STATUS.md](documentation/status/IMPLEMENTATION_STATUS.md): feature status, notable changes, and known limitations

### Feature setup guides

- [documentation/setup/EMAIL_SETUP.md](documentation/setup/EMAIL_SETUP.md)
- [documentation/setup/CALENDAR_SETUP.md](documentation/setup/CALENDAR_SETUP.md)
- [documentation/setup/TELEGRAM_SETUP.md](documentation/setup/TELEGRAM_SETUP.md)
- [documentation/setup/WHATSAPP_SETUP.md](documentation/setup/WHATSAPP_SETUP.md)
- [documentation/setup/FILES_SETUP.md](documentation/setup/FILES_SETUP.md)
- [documentation/setup/BROWSER_AGENT_SETUP.md](documentation/setup/BROWSER_AGENT_SETUP.md)
- [documentation/setup/STOCK_AGENT_SETUP.md](documentation/setup/STOCK_AGENT_SETUP.md)
- [documentation/setup/LINKEDIN_SETUP.md](documentation/setup/LINKEDIN_SETUP.md)

### Architecture and operations

- [documentation/architecture/ARCHITECTURE.md](documentation/architecture/ARCHITECTURE.md)
- [documentation/architecture/PA-DESIGN.md](documentation/architecture/PA-DESIGN.md)
- [documentation/architecture/memory-system.md](documentation/architecture/memory-system.md)
- [documentation/reference/TOOL_REFERENCE.md](documentation/reference/TOOL_REFERENCE.md)
- [documentation/reference/REPO_HYGIENE.md](documentation/reference/REPO_HYGIENE.md)

## Runtime Data And Hygiene

- Generated outputs and live runtime state should go under `your_data/`
- Do not blindly delete the core JSON state in `your_data/` because it stores assistant memory, jobs, conversations, and operation history
- Logs are truncated on startup, but normalized errors are preserved in `errors/log_error_registry.json`
- The `research/` folder is intentionally restricted to the published PDFs only

## Research Papers

- **DAG and Topological sort to reduce unnecessary reasoning by LLMs**  
	[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18911464.svg)](https://doi.org/10.5281/zenodo.18911464)  
	DOI: [10.5281/zenodo.18911464](https://doi.org/10.5281/zenodo.18911464)  
	PDF: [research/LLM_DAG_Orchestration.pdf](research/LLM_DAG_Orchestration.pdf)

- **Building Persistent AI Systems Without a Traditional Database**  
	[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19018414.svg)](https://doi.org/10.5281/zenodo.19018414)  
	DOI: [10.5281/zenodo.19018414](https://doi.org/10.5281/zenodo.19018414)  
	PDF: [research/Markdown_Native_Architecture.pdf](research/Markdown_Native_Architecture.pdf)
