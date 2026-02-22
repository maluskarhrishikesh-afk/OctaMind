# OctaMind

An AI-powered multi-agent platform for managing Gmail and Google Drive through natural language. Each agent runs as an isolated process with its own memory, personality, and context window.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirement/octaMind-requirement.txt

# 2. Configure (see documentation/SETUP.md)
#    — Add your GitHub token to .env
#    — Place credentials.json (Google OAuth) in the project root

# 3. Run
python start.py
```

`start.py` (or `start.exe`) launches the Agent Hub dashboard at **http://localhost:8501**, truncates all log files for a clean session, and opens the browser automatically.

---

## What It Does

From the **Agent Hub** you create and launch agents. Each agent opens in its own browser tab on a separate port.

| Agent | What it does |
|-------|-------------|
| **Email Agent** | Read, send, search, count, draft Gmail messages |
| **Drive Agent** | List, search, upload, download, share Google Drive files |
| **Multi-Agent Hub** | Cross-agent commands ("Download X and email it to Y") |

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
│   │   │   └── multi_agent/    # Multi-Agent Hub UI
│   │   └── workflows/          # Multi-agent workflow planner + executor
│   ├── email/                  # Gmail API service layer
│   └── drive/                  # Google Drive API service layer
│
├── tests/                      # Unit + integration tests
├── documentation/              # Developer documentation
└── architecture/               # Architecture deep-dives
```

---

## Documentation

| File | Contents |
|------|----------|
| [documentation/SETUP.md](documentation/SETUP.md) | Gmail OAuth credentials + GitHub Models token |
| [documentation/ARCHITECTURE.md](documentation/ARCHITECTURE.md) | How the system works (routing, ReAct, memory) |
| [documentation/AGENTS.md](documentation/AGENTS.md) | What each agent can do + example commands |
| [documentation/TOOL_REFERENCE.md](documentation/TOOL_REFERENCE.md) | Every tool — parameters, defaults, example prompts |
| [documentation/IMPLEMENTATION_STATUS.md](documentation/IMPLEMENTATION_STATUS.md) | What's implemented, what's not, known limits |
| [architecture/memory-system.md](architecture/memory-system.md) | Full memory architecture reference |

---

## Logs

Three log files are written to the project root and **auto-truncated on every start**:
`drive_agent.log` · `email_agent.log` · `multi_agent.log`
