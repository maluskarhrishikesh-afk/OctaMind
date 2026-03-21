# OctaMind Source Tree

This directory contains the runtime code for OctaMind. The current architecture is centered on Personal Assistants plus a catalog of stateless skill executors.

## Source Layout

```text
src/
├── agent/
│   ├── core/                    # Agent manager, process lifecycle, automation scheduler
│   ├── context/                 # Structured conversation state helpers
│   ├── hub/                     # Hub API, PA manager, auth session flow, processor
│   ├── llm/                     # Provider adapters and orchestration support
│   ├── logging/                 # Log setup and persistent JSON error registry integration
│   ├── manifest/                # Shared context manifest and cross-agent context storage
│   ├── memory/                  # Memory storage, consolidation, retrieval, and tooling
│   ├── runtime_paths.py         # Canonical helpers for `your_data/` and migrated runtime files
│   ├── system/                  # Keep-awake and system-level helpers
│   ├── ui/
│   │   ├── dashboard/           # Streamlit Agent Hub
│   │   ├── personal_assistant/  # Embedded PA workspace and live sync
│   │   ├── email_agent/         # Email skill orchestrator and prompts
│   │   ├── drive_agent/         # Drive skill orchestrator and prompts
│   │   ├── files_agent/         # Files skill orchestrator and prompts
│   │   ├── calendar_agent/      # Calendar skill orchestrator and prompts
│   │   ├── scheduler_agent/     # Smart scheduling skill orchestrator and prompts
│   │   ├── file_organizer_agent/# Approval-based folder organization skill
│   │   ├── habit_agent/         # Habit tracker skill orchestrator
│   │   ├── browser_agent/       # Web browsing skill orchestrator
│   │   ├── stock_agent/         # Stock analysis skill orchestrator
│   │   ├── linkedin_agent/      # LinkedIn skill orchestrator
│   │   └── whatsapp_agent/      # WhatsApp skill orchestrator
│   └── workflows/               # Skill registry, routing, DAG planning, workflow execution
├── browser/                     # HTTP-only web browsing and extraction services
├── calendar/                    # Google Calendar service layer
├── drive/                       # Google Drive service layer
├── email/                       # Gmail service layer and features
├── files/                       # Local filesystem tools and report writers
├── habit_tracker/               # Habit tracking service layer
├── linkedin/                    # LinkedIn publishing, scheduling, analytics
├── stock_market/                # Quotes, technicals, fundamentals, portfolio analysis
├── telegram/                    # Telegram messaging and scheduling services
└── whatsapp/                    # WhatsApp messaging, scheduling, and webhook services
```

## Runtime Model

- Personal Assistants own memory, identity, and conversation history.
- Skills are stateless executors selected by the workflow router.
- The skill registry in `src/agent/workflows/agent_registry.py` is the canonical list of routed skills.
- Runtime state and generated artifacts should be written through `src/agent/runtime_paths.py` helpers so they land under `your_data/`.

## Main Entry Points

- `start.py`: launches the dashboard, Hub API, keep-awake helper, and memory consolidation loop
- `stop.py`: stops the dashboard, tracked agent processes, and keep-awake helper
- `run_agent_hub.py`: runs the dashboard directly for local development
- `src/agent/hub/server.py`: FastAPI hub backend used by the dashboard and auth flows
- `src/agent/ui/dashboard/app.py`: Streamlit Agent Hub UI

## Current Routed Skills

The workflow router currently exposes these skills:

- `email`
- `drive`
- `whatsapp`
- `files`
- `document_parser`
- `calendar`
- `scheduler`
- `file_organizer`
- `habit_tracker`
- `browser`
- `stock_market`
- `linkedin`

Telegram integration is implemented in `src/telegram/` and is also surfaced through the Personal Assistant experience and dashboard controls.

## Data And State Conventions

- Use `your_data/` for generated files, reports, schedules, runtime state, and migrated live artifacts.
- Keep OAuth credentials and tokens in `config/`.
- Treat `memory/` as live Personal Assistant memory, not disposable cache.
- Use the persistent error registry in `errors/log_error_registry.json` for durable troubleshooting instead of relying only on truncated log files.

## Development Notes

- Prefer updating `src/agent/workflows/agent_registry.py` when adding or removing routed skills.
- When adding a new feature that writes files, route paths through `runtime_paths.py` instead of hardcoding the current working directory.
- When updating dashboard behavior, check both `src/agent/ui/dashboard/` and `src/agent/ui/personal_assistant/` because the embedded PA workspace now owns a significant part of the user experience.
- For setup and operator-facing documentation, update the files under `documentation/` at the same time so repo docs do not drift from shipped behavior.
