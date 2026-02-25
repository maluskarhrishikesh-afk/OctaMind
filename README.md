# OctaMind

An AI-powered platform for managing Gmail, Google Drive, WhatsApp, Telegram, and your local filesystem through natural language. **Personal Assistants** have memory, personality, and context. **Skills** (Email, Drive, WhatsApp, Telegram, Files) are stateless executors that the Personal Assistant orchestrates.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirement/octaMind-requirement.txt

# 2. Configure (see documentation/SETUP.md)
#    — Add your GitHub token to config/settings.json
#    — Place credentials.json (Google OAuth) in config/
#    — Run python setup_google_auth.py to authorize Gmail + Drive

# 3. Run
python start.py
```

`start.py` (or `start.exe`) launches the Agent Hub dashboard at **http://localhost:8501**, truncates all log files for a clean session, and opens the browser automatically.

---

## What It Does

From the **Agent Hub** you create and launch agents. Each agent opens in its own browser tab on a separate port.

| Agent | What it does |
|-------|-------------|
| **Email Agent** | Read, send, search, count, draft, schedule Gmail messages (47 tools) |
| **Drive Agent** | List, search, upload, download, share, organise Google Drive files (37 tools) |
| **WhatsApp Agent** | Send/read messages, schedule, auto-reply, contacts, analytics (36 tools) |
| **Telegram Agent** | Send/read messages, schedule, polls, media, analytics (38 tools) |
| **Files Agent** | Browse, copy, zip, organise, search your local filesystem (48 tools) |
| **Personal Assistant** | Cross-agent commands ("Download X and email it to Y", "Zip folder and upload to Drive") |

All agents understand **natural language** — no commands to memorise.

---

## Project Structure

```
OctaMind/
├── start.py                    # Launch entry point
├── stop.py                     # Stop all running agents
├── credentials.json            # Google OAuth credentials (do not commit)
├── token.json                  # OAuth token (auto-generated)
├── .env                        # GITHUB_TOKEN (do not commit)
├── agents.json                 # Registry of all created agents
│
├── src/
│   ├── agent/
│   │   ├── core/               # Process manager, agent registry
│   │   ├── llm/                # LLM client (GitHub Models), ReAct loop
│   │   ├── memory/             # 6-layer cognitive memory system
│   │   ├── ui/
│   │   │   ├── dashboard/      # Agent Hub UI
│   │   │   ├── email_agent/    # Email Agent UI + orchestrator
│   │   │   ├── drive_agent/    # Drive Agent UI + orchestrator
│   │   │   ├── whatsapp_agent/ # WhatsApp Agent UI + orchestrator
│   │   │   ├── telegram_agent/ # Telegram Agent UI + orchestrator
│   │   │   ├── files_agent/    # Files Agent UI + orchestrator
│   │   │   └── multi_agent/    # Personal Assistant Hub UI
│   │   └── workflows/          # Multi-agent workflow planner + executor
│   ├── email/                  # Gmail API service layer
│   ├── drive/                  # Google Drive API service layer
│   ├── whatsapp/               # Meta WhatsApp Cloud API + webhook server
│   └── telegram/               # Telegram Bot API + long-poll thread
│
├── memory/                     # Per-PA cognitive memory (Personal Assistants only; Skills are stateless)
├── tests/                      # Unit + integration tests
├── documentation/              # Developer documentation
└── docs/                       # Public-facing website (index.html)
```

---

## Documentation

| File | Contents |
|------|----------|
| [documentation/setup/SETUP.md](documentation/setup/SETUP.md) | Gmail OAuth credentials + GitHub Models token |
| [documentation/setup/EMAIL_SETUP.md](documentation/setup/EMAIL_SETUP.md) | Gmail + Drive OAuth setup |
| [documentation/setup/WHATSAPP_SETUP.md](documentation/setup/WHATSAPP_SETUP.md) | WhatsApp Business API + webhook setup |
| [documentation/setup/TELEGRAM_SETUP.md](documentation/setup/TELEGRAM_SETUP.md) | Telegram Bot token setup |
| [documentation/architecture/ARCHITECTURE.md](documentation/architecture/ARCHITECTURE.md) | How the system works (routing, ReAct, memory) |
| [documentation/reference/AGENTS.md](documentation/reference/AGENTS.md) | What each agent can do + example commands |
| [documentation/reference/TOOL_REFERENCE.md](documentation/reference/TOOL_REFERENCE.md) | Every tool — parameters, defaults, example prompts |
| [documentation/status/IMPLEMENTATION_STATUS.md](documentation/status/IMPLEMENTATION_STATUS.md) | What’s implemented, what’s not, known limits |
| [documentation/architecture/memory-system.md](documentation/architecture/memory-system.md) | Full memory architecture reference |

---

## Logs

Log files are written to the project root and **auto-truncated on every start**:
`email_agent.log` · `drive_agent.log` · `whatsapp_agent.log` · `telegram_agent.log` · `files_agent.log` · `personal_assistant.log`
