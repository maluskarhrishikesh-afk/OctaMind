# Implementation Status

Single source of truth for what is and isn't implemented. Use this to avoid hallucinating features that don't exist.

Last updated: 2026-02-26 (fixed gross_margin_pct key in stock report executive summary; improved Analyst Verdict to include revenue growth signal; added structured per-step logging + memory capture to generate_full_report; fixed relative imports in dashboard and personal_assistant app.py; fixed start.exe launcher — now pure-stdlib, no heavy ML deps; fixed PA blank page — missing main() call and PA_ID env var)  
Previous: 2026-02-26 (added LinkedIn Agent, enhanced PDF report cover page, fixed volume-profile bug, fixed Executive Summary article count)

---

## ✅ Fully Implemented

### Core Infrastructure
- [x] LLM client (`GitHubModelsLLM`) wrapping OpenAI SDK against GitHub Models endpoint
- [x] ReAct loop (`reason_and_act`) — up to 6 iterations, 45s timeout, `max_tokens=3000`
- [x] Intent classification (`classify_intent`) for multi-agent routing
- [x] Agent process isolation — each agent runs as a separate `subprocess.Popen`
- [x] Per-agent memory system (working, episodic, semantic, personality, habits, consciousness) — **Personal Assistants only; Skills are stateless executors with no memory**
- [x] Memory consolidation, decay, and archiving
- [x] **Global consolidation background thread** — starts at app launch, runs every 24 h across ALL Personal Assistants (including inactive ones)
- [x] Log files written to project root; truncated on every `start.py` launch
- [x] 429 rate-limit error surfaced to user with wait-time estimate
- [x] Single-agent shortcut in Personal Assistant Hub (bypasses planner for Drive-only or Email-only commands)

### Drive Agent — 37 Tools
All tools described in TOOL_REFERENCE.md are implemented and wired to the Google Drive API.

| Category | Tools | Status |
|----------|-------|--------|
| Core file ops | list_files, search_files, get_file_info, upload_file, download_file, create_folder, move_file, copy_file, trash_file, restore_file, star_file, get_storage_quota | ✅ |
| Sharing | share_file, list_permissions, remove_permission, update_permission, make_public, remove_public | ✅ |
| Smart features | summarize_file, summarize_folder, find_duplicates, trash_duplicates, suggest_organization, auto_organize, bulk_rename, list_versions, get_version_info, restore_version, delete_old_versions | ✅ |
| Analytics | storage_breakdown, list_large_files, list_old_files, list_recently_modified, find_orphaned_files, sharing_report, generate_drive_report, get_usage_insights | ✅ |

### Email Agent — 47 Tools
All tools described in TOOL_REFERENCE.md are implemented and wired to the Gmail API.  
**Setup:** Full guide at `documentation/EMAIL_SETUP.md`.

| Category | Tools | Status |
|----------|-------|--------|
| Reading | get_todays_messages, list_message, count_messages, detect_urgent_emails, detect_newsletters, check_unanswered_emails | ✅ |
| Sending & drafts | send_message, create_draft, list_drafts, send_draft, delete_draft, quick_reply, generate_reply_suggestions, schedule_email, list_scheduled_emails, cancel_scheduled_email, update_scheduled_email | ✅ |
| Attachments | list_attachments, download_attachment, search_emails_with_attachments | ✅ |
| Organisation | auto_categorize_email, apply_smart_labels, create_category_rules, auto_prioritize | ✅ |
| Action items | extract_action_items, get_all_pending_actions, mark_action_complete, get_saved_tasks, mark_for_followup, get_pending_followups, send_followup_reminder, mark_followup_done, dismiss_followup | ✅ |
| Calendar | extract_calendar_events, suggest_calendar_entry, export_to_calendar | ✅ |
| Contacts & analytics | get_frequent_contacts, get_contact_summary, suggest_vip_contacts, export_contacts, extract_unsubscribe_link, calculate_response_time, get_email_stats, get_productivity_insights, visualize_patterns, generate_weekly_report | ✅ |

### WhatsApp Agent — 36 Tools
All tools described in WHATSAPP_SETUP.md are implemented and wired to the Meta WhatsApp Cloud API.

| Category | Tools | Status |
|----------|-------|--------|
| Core messaging | send_message, send_media, send_template, reply_to_message, get_messages, get_unread_messages, mark_as_read | ✅ |
| Contacts | list_contacts, get_contact_info, get_frequent_contacts, set_contact_name | ✅ |
| Groups | list_groups, get_group_info, get_group_messages | ✅ |
| Search & retrieval | search_messages, get_conversation, get_messages_by_date, get_media_messages | ✅ |
| AI smart features | summarize_conversation, extract_action_items, draft_message, generate_reply, detect_urgent_messages, extract_key_info, translate_message, sentiment_analysis | ✅ |
| Scheduling | schedule_message, list_scheduled_messages, cancel_scheduled_message, set_auto_reply, get_auto_reply_config | ✅ |
| Analytics | get_message_stats, get_response_time, get_activity_report, get_top_senders | ✅ |
| Cross-agent | forward_to_email, share_drive_file | ✅ |

**Webhook server:** FastAPI + uvicorn on port 9001; inbound messages stored in `data/whatsapp_messages.json`.  
**Credentials:** Configured in `config/settings.json["whatsapp"]` — `access_token` + `phone_number_id` required.  
**Setup:** Full guide at `documentation/WHATSAPP_SETUP.md`.

### Telegram Agent — 38 Tools
All tools described in TOOL_REFERENCE.md are implemented and wired to the Telegram Bot API via long-polling.

| Category | Tools | Status |
|----------|-------|--------|
| Core messaging | send_message, send_media, reply_to_message, forward_message, edit_message, delete_message, get_messages, get_unread_messages, get_chat_history, mark_as_read, send_chat_action | ✅ |
| Chats | list_chats, get_chat_info, get_chat_member_count, pin_message, unpin_message, leave_chat | ✅ |
| Media | send_photo, send_document, send_audio, get_media_messages | ✅ |
| Search & retrieval | search_messages, get_messages_by_date, get_pinned_messages, get_message_stats | ✅ |
| Polls | send_poll, stop_poll | ✅ |
| Scheduling | schedule_message, list_scheduled_messages, cancel_scheduled_message | ✅ |
| AI smart features | summarize_chat, detect_urgent_messages, draft_message, translate_message, sentiment_analysis, extract_action_items | ✅ |
| Cross-agent | forward_to_email, share_drive_file | ✅ |

**Polling:** Background thread runs `getUpdates` long-poll loop; messages stored in `data/telegram_messages.json`.  
**Credentials:** `TELEGRAM_BOT_TOKEN` env var or `config/settings.json["telegram"]["bot_token"]` — get token from **@BotFather**.  
**Composite IDs:** All stored messages are addressed as `"chat_id:message_id"` (e.g. `"1001:5"`).

### Files Agent — 48 Tools
All tools use Python stdlib only (`pathlib`, `shutil`, `zipfile`, `hashlib`, `os`). No credentials required for 43/48 tools.

| Category | Tools | Status |
|----------|-------|--------|
| File operations | list_directory, get_file_info, copy_file, move_file, delete_file, create_folder, rename_file, open_file | ✅ |
| Search | search_by_name, search_by_extension, search_by_date, search_by_size, find_duplicates, find_empty_folders | ✅ |
| Archives | zip_files, zip_folder, unzip_file, list_archive_contents, get_archive_info | ✅ |
| Organiser | bulk_rename, organize_by_type, organize_by_date, move_files_matching, delete_files_matching, clean_empty_folders, deduplicate_files | ✅ |
| Disk | list_drives, get_disk_usage, get_directory_size, find_large_files, get_recently_modified | ✅ |
| Reader | read_text_file, get_file_stats, preview_csv, read_json_file, tail_log, calculate_file_hash | ✅ |
| AI smart features | summarize_file, analyze_folder, suggest_organization, generate_rename_suggestions, find_related_files, describe_file | ✅ |
| Cross-agent | zip_and_email, zip_and_upload_to_drive, email_file, upload_file_to_drive, send_file_via_whatsapp | ✅ |

**Credentials:** None required for core 43 tools. Gmail/Drive OAuth needed for 5 cross-agent tools.  
**Safety:** `_is_safe_path()` blocks ops on system directories; destructive ops default to `dry_run=True`.  
**Setup:** Full guide at `documentation/FILES_SETUP.md`.

### Calendar Agent (Google Calendar) — 19 Tools
All tools implemented and wired to Google Calendar API v3.

| Category | Tools | Status |
|----------|-------|--------|
| View & search | get_todays_events, get_tomorrows_events, get_upcoming_events, get_events_for_date, search_events, get_event, list_events | ✅ |
| Agenda | get_daily_agenda, get_weekly_agenda | ✅ |
| Create & modify | create_event, quick_add_event, update_event, delete_event, create_recurring_event | ✅ |
| Smart | find_free_slots, find_conflicts, set_reminder | ✅ |
| RSVP & management | accept_invite, decline_invite, list_calendars | ✅ |

**Auth:** `config/calendar_token.json` — generated on first OAuth flow; silently refreshed thereafter.  
**Preflight:** `_get_client()` raises `PermissionError` if not authorised — surfaces clean `auth_error` to user.  
**Setup:** See `documentation/setup/CALENDAR_SETUP.md`.

### Scheduler / Smart Calendar Agent — 8 Tools
New intelligence layer on top of the Calendar Agent. Uses same auth token.

| Category | Tools | Status |
|----------|-------|--------|
| Slot finding | suggest_meeting_time, find_mutual_availability | ✅ |
| Focus protection | protect_deep_work_block, schedule_recurring_focus_time | ✅ |
| Analysis | optimize_day_schedule, get_scheduling_insights | ✅ |
| Conflict resolution | smart_reschedule_conflicts | ✅ |
| Time blocks | create_time_block | ✅ |

**Registry key:** `scheduler`  
**Auth:** Reuses `config/calendar_token.json` — no additional OAuth setup.  
**Key difference from Calendar Agent:** Never just CRUD — always reasons and proposes optimal solutions.

### File Organizer Agent — 10 Tools
Approval-driven organisation with archival policies. No credentials required.

| Category | Tools | Status |
|----------|-------|--------|
| Plan workflow | scan_and_propose, preview_plan, apply_plan, discard_plan, list_plans | ✅ |
| Archival | archive_old_files, set_archival_policy, show_archival_policies, run_archival_policies | ✅ |
| App data | cleanup_app_data | ✅ |

**Registry key:** `file_organizer`  
**Data stores:** `data/organizer_pending_plans.json`, `data/organizer_archival_policies.json`  
**Safety:** Never calls `apply_plan` without explicit user confirmation; all destructive ops default to `dry_run=True`.

### Habit & Health Tracker Agent — 9 Tools
Completely new agent. No overlap with Calendar or Files agents.

| Category | Tools | Status |
|----------|-------|--------|
| Habit management | add_habit, delete_habit, get_habits | ✅ |
| Logging | log_completion, daily_checkin | ✅ |
| Progress tracking | get_streak, get_weekly_report, get_habit_analytics | ✅ |
| Calendar integration | schedule_habit_on_calendar | ✅ |

**Registry key:** `habit_tracker`  
**Service:** `src/habit_tracker/habit_service.py`  
**Data stores:** `data/habits.json` (definitions), `data/habit_logs.json` (daily logs)  
**No credentials required** for all 8 core tools; Calendar integration requires Calendar auth.

### Browser Agent — 10 Tools
HTTP-only web browsing. No credentials, no API keys, no headless browser required.

| Category | Tools | Status |
|----------|-------|--------|
| Page access | browse_url, extract_text, summarize_page | ✅ |
| Search | search_web | ✅ |
| Inspection | get_page_links, get_page_title, get_page_metadata, find_on_page | ✅ |
| Data extraction | extract_structured_data | ✅ |
| Downloads | download_file_from_url | ✅ |

**Registry key:** `browser`  
**Service:** `src/browser/browser_service.py`  
**Backend:** `urllib.request` (stdlib) + optional `beautifulsoup4` + `requests`  
**No credentials required.** No JavaScript execution — public HTTP pages only.

### Stock Market Analysis Agent — 10 Tools
Read-only analysis. No buy/sell, no brokerage integration.

| Category | Tools | Status |
|----------|-------|--------|
| Market data | get_quote, get_historical_data, market_overview | ✅ |
| Technical analysis | technical_analysis (RSI, MACD, Bollinger, SMA), pattern_detection | ✅ |
| Risk analysis | risk_score (volatility, Beta, VaR 95%, Sharpe) | ✅ |
| Portfolio | portfolio_analysis, portfolio_suggestions | ✅ |
| Intelligence | sentiment_analysis, compare_stocks | ✅ |

**Registry key:** `stock_market`  
**Service:** `src/stock_market/stock_service.py`  
**Data source:** `yfinance` (Yahoo Finance public API) — free, no API key required.  
**No credentials required.** All indicators computed in pure Python (no ML dependencies).  
**PDF Report Generation:** `generate_full_report(symbol)` runs all 10 analyses and builds a multi-page A4 PDF with cover page, Analyst Quick Snapshot, 7 analysis sections, charts, and risk tables. Output saved to `data/exports/`.

### LinkedIn Agent — 17 Tools
Fully implemented service + LLM orchestrator. Registered in agent_registry, agent_manager, and dashboard skill cards.

| Category | Tools | Status |
|----------|-------|--------|
| Posting | create_text_post, create_image_post, create_video_post, create_article_post, delete_post, list_published_posts | ✅ |
| AI generation | generate_ai_post_content (text via LLM), generate_ai_image (images via DALL·E 3) | ✅ |
| Scheduling | schedule_post, list_scheduled_posts, cancel_scheduled_post | ✅ |
| Analytics | get_post_analytics, get_page_analytics, get_org_followers | ✅ |
| Auth / profile | get_profile, get_access_token_url, exchange_code_for_token | ✅ |

**Registry key:** `linkedin`  
**Service:** `src/linkedin/linkedin_service.py`  
**Orchestrator:** `src/agent/ui/linkedin_agent/orchestrator.py`  
**UI:** `src/agent/ui/linkedin_agent/app.py` (standalone Streamlit UI)  
**Setup Guide:** `documentation/setup/LINKEDIN_SETUP.md`  
**Credentials:** LinkedIn OAuth access_token in `config/settings.json["linkedin"]["access_token"]` — required for all posting/analytics tools.  
**AI Text Generation:** Uses GitHub Models LLM (same as all other agents).  
**AI Image Generation:** Uses OpenAI DALL·E 3 — requires a **separate paid OpenAI API key** (`OPENAI_API_KEY` env var or `settings.json["openai_api_key"]`). NOT provided by GitHub Models.

### Personal Assistant Hub
- [x] Drive-only command routing → Drive Agent direct
- [x] Email-only command routing → Email Agent direct
- [x] NL-based cross-agent workflow planner (`plan_nl_workflow`) for combined commands
- [x] Agent capability registry (`agent_registry.py`) — ~10 tokens per agent, scales to N agents; **10 agents registered**: drive, email, whatsapp, files, calendar, scheduler, file_organizer, habit_tracker, browser, stock_market
- [x] Planning context: ~80 tokens for 8 agents (vs ~8,000 tokens in old flat-tool-list design)
- [x] Natural-language step format: orchestrator issues plain-English instructions, no tool signatures
- [x] Sequential multi-agent execution via `nl_step_runner.py` — each sub-agent runs its own full ReAct loop
- [x] Artifact handoff between agents (`artifacts_out` dict + `{output_key.field}` token substitution)
- [x] Drive → Email file path handoff: `artifacts_out["file_path"]` populated from `download_file` result
- [x] Composed final response from all agent results
- [x] **Hard-coded `__multi_agent__` personality** — warm, proactive, protective personal-assistant character baked in as prose; immune to personality trait slider edits
- [x] **`collective_consciousness.md`** — synthesised from every sub-agent’s `consciousness.md` each consolidation cycle; gives the PA a cross-domain mental model of the user
- [x] **WhatsApp agent** registered in `agent_registry.py` — available for PA workflows
- [x] **Telegram agent** registered in `agent_registry.py` — available for PA workflows
- [x] **Files agent** registered in `agent_registry.py` — available for PA workflows
- [x] **Calendar agent** registered in `agent_registry.py` — Google Calendar CRUD via PA
- [x] **Scheduler agent** registered in `agent_registry.py` — intelligent scheduling, focus blocks, insights
- [x] **File Organizer agent** registered in `agent_registry.py` — approval-workflow file organization
- [x] **Habit Tracker agent** registered in `agent_registry.py` — habit tracking, streaks, weekly reports
- [x] **Browser agent** registered in `agent_registry.py` — web browsing, search, text extraction, downloads
- [x] **LinkedIn agent** registered in `agent_registry.py` — available for PA workflows (text posts, AI-generated content, scheduling, analytics)

### UI
- [x] Streamlit chat UI for Drive Agent (port 8502)
- [x] Streamlit chat UI for Email Agent (port 8503)
- [x] Streamlit chat UI for WhatsApp Agent (WhatsApp green theme #25d366)
- [x] Streamlit chat UI for Telegram Agent (blue-grey theme)
- [x] Streamlit chat UI for Files Agent (blue theme #4a90d9 — no credentials required)
- [x] Streamlit chat UI for Multi-Agent / Personal Assistant (port 8504)
- [x] Agent Hub management UI (port 8501)
- [x] `start.py` / `stop.py` for launching/stopping all UIs
- [x] Per-agent personality trait sliders in Agent Hub

---

## ⚠️ Partial / Known Limitations

### `create_video_post` (LinkedIn)
- Only **uploads an existing local video file** to LinkedIn — it does NOT generate or create a video.
- A request like "create a video about X and post it" will fail — Octa Bot cannot generate video content.
- Workaround: Record/create the video externally, then ask "post this video: /path/to/video.mp4".

### `generate_ai_image` (LinkedIn)
- Requires a **paid OpenAI API key** with DALL·E 3 access (`OPENAI_API_KEY`).
- Does NOT work with the GitHub Models token — DALL·E 3 is not available via GitHub Models.
- Configure `settings.json["linkedin"]["image_gen_backend"] = "openai"` and set `OPENAI_API_KEY`.

### `reply_to_message`
- Listed in tool description but **not wired in `_dispatch`** in `email_agent/orchestrator.py`.
- The LLM sees it as available, but calling it will return `Unknown tool: reply_to_message`.
- Workaround: Use `send_message` with a subject like `"Re: [original subject]"`.

### `download_file` (Drive)
- Downloads to a local path on the machine running the Streamlit server.
- When running from `start.exe`, the download location is relative to the executable directory.
- No in-UI file picker for destination — path must be specified in natural language or defaults to the project root.

### `download_attachment` (Email)
- Same constraint as Drive download — saves to server-side disk.
- No browser download prompt.

### `schedule_email`
- Scheduling is software-implemented (stored JSON, checked by a background scheduler).
- It is **not** a native Gmail scheduled send — it relies on the Octa Bot process being running at send time.
- If the application is closed before the scheduled time, the email will not be sent.

### `export_to_calendar`
- Google Calendar write access requires additional OAuth scope (`calendar.events`).
- The `.ics` file export works unconditionally.
- Calendar write is implemented but depends on the token having the right scope — if not authorised, only `.ics` is saved.

### `apply_smart_labels` / `create_category_rules`
- Creates Gmail labels in the user's account.
- Label creation is irreversible via this tool — there is no `delete_label` tool.

### `bulk_rename` / `auto_organize` / `trash_duplicates` / `delete_old_versions`
- All default to `dry_run=True`. The agent will show a preview.
- To apply changes, the user must explicitly confirm or re-request with "yes, proceed" / "do it for real."

### `visualize_patterns`
- Returns chart-ready JSON data, not an actual rendered chart.
- The Streamlit UI does not currently render this data as a visual — it displays as formatted text.

### Agent Hub Automation (`auto_run`)
- The `auto_run` config field exists in `agents.json` but the automation scheduler is **not actively running** in the current build.
- Manual commands via chat always work; background auto-run does not trigger automatically.

---

## ❌ Not Implemented

| Feature | Notes |
|---------|-------|
| Google Docs / Sheets editing | Drive agent can read/summarise but cannot write to Docs or Sheets content |
| Gmail label deletion | No `delete_label` tool exists |
| Multi-step email thread view | `list_message` returns individual messages, not full thread chains |
| Bulk email deletion/archiving | No `bulk_delete` or `bulk_archive` tool |
| Push notifications | No real-time inbox monitoring; all reads are on-demand |
| Voice input | Text-only chat interface |
| File preview in UI | Files are downloaded to disk; no in-browser preview |
| Cross-session memory search | Memory is loaded per-agent at startup; no semantic search across memory files |
| Drive → Sheets data import | Cannot populate a Sheet from structured data |
| OAuth token refresh UI | Run `python setup_google_auth.py` from the project root to re-authorise Gmail and Drive |

---

## Known Bugs / Edge Cases

| Issue | Impact | Status |
|-------|--------|--------|
| GitHub Models token expired / bad credentials | LLM calls return 401 — all AI text generation fails (LLM-classified sentiment uses keyword fallback, posts fail to generate) | Refresh token: update `config/credentials.json` with a new GitHub Models API token |
| GitHub Models rate limit (150 req/day, 15 req/min) | All agents fail with 429 after limit | Surfaced to user with wait-time; no workaround except waiting or switching model |
| `max_tokens=3000` vs context window | Very long tool results may exceed context; LLM truncates | No chunking implemented |
| Memory consolidation agent | ~~Consolidation task runs on startup but output is not surfaced in UI~~ **FIXED** — `ConsolidationRunner` daemon thread boots with the dashboard and runs all agents every 24 h | Memory improves continuously even for idle agents |
| Log file locked on Windows | Logs in `src/` may stay locked if processes don't exit cleanly | Truncated on next `start.py` |

---

## LLM Configuration

| Setting | Value |
|---------|-------|
| Provider | GitHub Models (free tier) |
| Model | `gpt-4o` (via GitHub Models endpoint) |
| Rate limit | 15 requests/minute, 150 requests/day |
| `max_tokens` — ReAct loop | 3000 per iteration |
| `max_tokens` — compose response | 3000 |
| `max_tokens` — classify intent | 5 |
| ReAct max iterations | 6 |
| ReAct timeout | 45 seconds |
| Temperature — compose | 0.4 |

---

## API Scopes Required

### Google Drive
- `https://www.googleapis.com/auth/drive` (full Drive access)

### Gmail
- `https://www.googleapis.com/auth/gmail.modify` (read + send + labels)
- `https://www.googleapis.com/auth/gmail.send`

### Google Calendar (optional)
- `https://www.googleapis.com/auth/calendar.events` — required for `export_to_calendar` write path
- Without this scope, only `.ics` file export works

---

## File Structure Reference

```
src/
  agent/
    llm/
      llm_parser.py          # GitHubModelsLLM — all LLM calls go through here
    memory/                  # Memory system (load/save/consolidate)
      agent_memory.py        # AgentMemory — 6-layer per-agent storage + MULTI_AGENT_ID constant
      memory_consolidator.py # MemoryConsolidator — pattern extraction, habit detection, consciousness update
      consolidation_runner.py # ConsolidationRunner — daemon thread, runs all agents every 24 h
      collective_memory.py   # get_collective_context() — episodic snapshot for multi-agent LLM context
    ui/
      drive_agent/
        app.py               # Streamlit UI + _compose_drive_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 37 Drive tools + artifacts_out
      email_agent/
        app.py               # Streamlit UI + _compose_email_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 47 Gmail tools + artifacts_out
      whatsapp_agent/
        app.py               # Streamlit UI + _compose_whatsapp_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 36 WhatsApp tools
      telegram_agent/
        app.py               # Streamlit UI + _compose_telegram_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 38 Telegram tools
      files_agent/
        app.py               # Streamlit UI
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 48 Files tools
      calendar_agent/
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 19 Calendar tools
      scheduler_agent/
        orchestrator.py      # execute_with_llm_orchestration() + 8 smart scheduling tools
      file_organizer_agent/
        orchestrator.py      # execute_with_llm_orchestration() + 10 approval-workflow tools
      habit_agent/
        orchestrator.py      # execute_with_llm_orchestration() + 9 habit tracking tools
      multi_agent/
        app.py               # Streamlit UI + routing + _compose_final_response() — Personal Assistant Chat UI
      dashboard/
        app.py               # Agent Hub Streamlit entry — boots ConsolidationRunner + PA memory on startup
    workflows/
      agent_registry.py      # AGENT_REGISTRY dict — one entry per agent (~10 tokens each)
      master_orchestrator.py # _build_planning_prompt() + plan_nl_workflow() + run_workflow()
      nl_step_runner.py      # run_nl_step() — resolves tokens, calls sub-agent, extracts artifacts
      workflow_context.py    # NLWorkflowStep, NLWorkflowPlan, WorkflowContext dataclasses
      router.py              # detect_agents_needed() — LLM-based DRIVE/EMAIL/BOTH/NEITHER
  drive/                     # Raw Google Drive API calls
  email/                     # Raw Gmail API calls
  whatsapp/                  # Meta WhatsApp Cloud API calls + webhook server (port 9001)
  telegram/                  # Telegram Bot API calls + long-poll background thread
  files/                     # Local filesystem operations (stdlib only)
agents.json                  # Agent registry (ids, types, config)
start.py                     # Launch all Streamlit UIs as subprocesses
stop.py                      # Kill all running agent processes
memory/<pa_id>/           # Per-PA 6-layer memory (working, episodic, semantic, personality, habits, consciousness)
                             # Only Personal Assistants have memory — Skills are stateless executors
                             # Active PA folders: pa_<id>/, __multi_agent__/
```
