# OctaMind Agents Reference

This document describes the current skill surface exposed through OctaMind Personal Assistants. The authoritative routing list lives in `src/agent/workflows/agent_registry.py`.

For tool-by-tool parameter details, see [TOOL_REFERENCE.md](TOOL_REFERENCE.md). For known limitations and recent changes, see [../status/IMPLEMENTATION_STATUS.md](../status/IMPLEMENTATION_STATUS.md).

## How The Product Is Organized

- **Personal Assistants** hold memory, identity, channel history, and long-running context.
- **Skills** are stateless executors chosen by the workflow router.
- The Agent Hub lets you create a Personal Assistant, enable the skills it should use, and open the embedded assistant workspace.

## Current Skill Catalog

| Skill key | UI orchestrator | Purpose | Typical tasks | Setup guide |
|----------|------------------|---------|---------------|-------------|
| `email` | `src/agent/ui/email_agent/orchestrator.py` | Gmail operations | read inbox, search threads, draft, reply, schedule mail, extract actions | [../setup/EMAIL_SETUP.md](../setup/EMAIL_SETUP.md) |
| `drive` | `src/agent/ui/drive_agent/orchestrator.py` | Google Drive operations | search files, upload, download, share, summarize, analyze storage | [../setup/EMAIL_SETUP.md](../setup/EMAIL_SETUP.md) |
| `files` | `src/agent/ui/files_agent/orchestrator.py` | Local filesystem operations | search across drives, zip or unzip, inspect files, write reports, deliver downloads | [../setup/FILES_SETUP.md](../setup/FILES_SETUP.md) |
| `calendar` | `src/agent/ui/calendar_agent/orchestrator.py` | Google Calendar operations | create events, list agendas, search events, manage recurring items | [../setup/CALENDAR_SETUP.md](../setup/CALENDAR_SETUP.md) |
| `scheduler` | `src/agent/ui/scheduler_agent/orchestrator.py` | Intelligent scheduling | find best slots, protect focus time, analyze meeting load, resolve conflicts | [../setup/CALENDAR_SETUP.md](../setup/CALENDAR_SETUP.md) |
| `file_organizer` | `src/agent/ui/file_organizer_agent/orchestrator.py` | Approval-based organization | scan folders, preview plans, archive old files, run archival policies | [../setup/FILES_SETUP.md](../setup/FILES_SETUP.md) |
| `habit_tracker` | `src/agent/ui/habit_agent/orchestrator.py` | Habit tracking | add habits, log completions, review streaks, generate reports | [../setup/CALENDAR_SETUP.md](../setup/CALENDAR_SETUP.md) |
| `browser` | `src/agent/ui/browser_agent/orchestrator.py` | HTTP-only browsing | search the web, inspect pages, extract text, download public files | [../setup/BROWSER_AGENT_SETUP.md](../setup/BROWSER_AGENT_SETUP.md) |
| `stock_market` | `src/agent/ui/stock_agent/orchestrator.py` | Read-only stock analysis | quotes, technicals, fundamentals, portfolio analysis, PDF reports | [../setup/STOCK_AGENT_SETUP.md](../setup/STOCK_AGENT_SETUP.md) |
| `linkedin` | `src/agent/ui/linkedin_agent/orchestrator.py` | LinkedIn publishing | create posts, schedule content, generate copy, review analytics | [../setup/LINKEDIN_SETUP.md](../setup/LINKEDIN_SETUP.md) |
| `whatsapp` | `src/agent/ui/whatsapp_agent/orchestrator.py` | WhatsApp messaging | send messages, summarize chats, schedule messages, analyze activity | [../setup/WHATSAPP_SETUP.md](../setup/WHATSAPP_SETUP.md) |

## Channel Integrations

### Telegram

Telegram support is implemented in `src/telegram/` and managed per Personal Assistant from the dashboard. It is part of the shipped runtime even though the workflow registry is centered on routed skill executors.

Use Telegram when you want:

- inbound and outbound bot conversations
- scheduled Telegram messages
- poll management
- dashboard and Telegram conversation history merged back into the Personal Assistant workspace

Setup guide: [../setup/TELEGRAM_SETUP.md](../setup/TELEGRAM_SETUP.md)

### WhatsApp

WhatsApp is both a routed skill and a channel integration. It depends on the Meta Cloud API webhook configuration described in the setup guide.

## Personal Assistant Responsibilities

The Personal Assistant layer is responsible for:

- preserving conversation history and memory
- loading and merging context from dashboard and Telegram sessions
- selecting the right skills for a request
- coordinating multi-step workflows such as finding files and emailing them, or generating a report and sending it onward

Primary UI module: `src/agent/ui/personal_assistant/app.py`

## Skill Selection Rules Of Thumb

Use `calendar` when the request is about direct calendar CRUD operations.

Use `scheduler` when the request needs reasoning about availability, focus protection, tradeoffs, or optimization.

Use `files` for direct local file actions and download delivery.

Use `file_organizer` when the user wants a proposed folder cleanup plan or archival workflow with explicit approval before changes.

Use `browser` for public-web research and page extraction.

Use `stock_market` for read-only market analysis and report generation, never for order execution.

## Notes For Maintainers

- Update `src/agent/workflows/agent_registry.py` first when the routed skill surface changes.
- Keep this document aligned with the dashboard skill catalog in `src/agent/ui/dashboard/app.py`.
- If a skill gains or loses a setup dependency, update the linked setup guide and the root `README.md` in the same change.