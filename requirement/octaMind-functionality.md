# OctaMind — Functionality Tracker

> **Purpose:** Reference document listing what has been built, what is in-progress,
> and what is planned. Updated daily as work progresses.
>
> **Last updated:** 2026-02-21 (Personality traits + Automation scheduler + Configure panel + Automation bug fixes + Run-frequency selector)

---

## ✅ Completed Features

### 1. Agent Hub Dashboard (`src/agent/agent_dashboard.py`)
- Multi-agent management dashboard running on **port 8501**
- Create agents of any type via a form (name, type, role, advanced config)
- Agent cards showing name, type, role, status (🟢 Running / ⚫ Stopped)
- **▶️ Start Agent** button — spawns agent in a dedicated window (own port)
- **⏹️ Stop Agent** button — terminates the agent process
- **🗑️ Delete** with two-step confirmation (also stops agent if running)
- Filter agents by type and status (Running / Stopped / All)
- Search agents by name or type
- Dashboard **stays alive** after starting/stopping agents (no page redirect)
- Sidebar shows total agents count and running count
- **Pink octopus logo** (🐙, gradient #ff69b4 → #c2185b) in header and sidebar
- Page icon changed to 🐙; product name "OctaMind" in hot-pink (#e91e8c)

### 2. Process Manager (`src/agent/core/process_manager.py`)
- Spawns per-agent Streamlit subprocesses on unique ports (8502–8599)
- Port assignment: auto-finds next free port in range
- Persists running-agent state to `running_agents.json` (survives dashboard reruns)
- `start_agent(agent_id, agent_name, agent_type)` → returns pid, port, url
- `stop_agent(agent_id)` → kills subprocess (Windows `taskkill /F /T`)
- `get_agent_status(agent_id)` → returns status dict or None if stopped
- `cleanup_stale()` → removes entries for processes that have already died
- **`remove_agent_from_state(agent_id)`** → removes entry without killing process (used by browser-close watchdog)
- Automatically selects the correct Streamlit script per agent type

### 3. Agent Manager (`src/agent/core/agent_manager.py`)
- CRUD for agent configurations stored in `agents.json`
- Agent types: Gmail, Google Drive, Slack, Calendar, **Stock Market** (new), Custom
- Auto-creates memory folder on agent creation
- Singleton `get_agent_manager()` function

### 4. **Cognitive Memory Architecture** (`src/agent/memory/agent_memory.py`)
- **Implements memory_architecture.md specification completely**
- Six memory layers per agent (following cognitive science model):
  - **`working_memory.md`** — Short-term, RAM-like (max 10 recent items, auto-trimmed)
  - **`episodic_memory.md`** — Time-based events with **importance scoring** (High/Medium/Low)
  - **`semantic_memory.md`** — Distilled knowledge about user (not raw logs)
  - **`personality.md`** — Assistant behavior profile (rarely changes)
  - **`habits.md`** — Behavioral patterns (updated only after 3+ confirmations)
  - **`consciousness.md`** — Meta summary layer (highest abstraction, periodically updated)
- **Memory flow implemented:** working → episodic → semantic → consciousness
- **LLM context character caps** — prevents token overflow:
  - `_LLM_PERSONALITY_CAP = 1500` chars (~375 tokens)
  - `_LLM_CONSCIOUSNESS_CAP = 1000` chars (~250 tokens)
  - `_LLM_SEMANTIC_CAP = 3000` chars (~750 tokens)
  - `_LLM_HABITS_CAP = 1500` chars (~375 tokens)
  - `_tail()` helper returns last N chars (most-recent first)
- **`recall_for_llm(query)`** — On-demand episodic search:
  - Detects recall-signal words ("remember", "did we", "earlier", etc.)
  - Searches working + episodic + semantic memory
  - Injects only matching results as `## On-Demand Memory Recall` block for that turn only
  - Returns `""` if no recall signal detected (zero overhead on normal commands)
- **Forgetting mechanism** with 90-day decay period and importance-based retention
- **Archive folder** for old episodic memories
- **Smart `remember(query)` method** — Intelligently handles memory queries:
  - **General recall** ("what did we do earlier?", "do you remember?") → Shows recent activity
  - **Specific search** ("emails from John") → Searches for matching terms
  - **Context-aware** — Removes stop words, detects intent
  - Searches all layers: working memory, episodic memory, semantic memory
- **`add_episodic_event()`** — Adds events with importance scoring
- **`get_full_context_for_llm()`** — Loads personality, consciousness, working memory, semantic memory (with caps, not full episodic)
- **Backward compatibility** — Legacy method names (short_term, long_term, context) still work
- Memory files auto-created with proper templates on agent initialization

### 5. Gmail Agent Chat UI (`src/agent/ui/email_agent_ui.py`)
- Full chat interface using `st.chat_message()` and `st.chat_input()`
- Welcome message on first load — includes **agent's own name** (from `AGENT_NAME` env var)
- Agent **addresses itself by its configured name** in all responses (greetings, identity, welcome)
- **Memory-aware conversations** — `get_full_context_for_llm()` + `recall_for_llm()` on every turn
- Conversational handler (`handle_conversation()`) for small talk:
  - Greetings, "how are you", "who are you", "what can you do", thanks, goodbyes
  - **Memory queries** — "remember", "recall", "do you know", "did we", "have we", "earlier"
  - Short non-email messages get a gentle nudge, not an error
- Email command router for: count, list, send, delete, summarize, daily digest
- Results displayed as chat bubbles (not separate sections)
- Clear Chat button
- Command history in sidebar expander
- LLM parser (GitHub Models) with rule-based fallback
- **Pink octopus logo** in header and sidebar; page icon 🐙
- **Browser-close watchdog** (`_start_browser_watchdog`): background thread detects when all sessions disconnect and auto-exits the process, removing itself from `running_agents.json`

### 6. Generic Agent Chat UI (`src/agent/ui/generic_agent_ui.py`)
- Universal chat interface for non-Gmail agent types
- Supports: Google Drive, Slack, Calendar, Stock Market, Custom
- Each type has its own icon, colour, greeting, and capabilities list
- **Memory-aware conversations** — Handles "Do you remember...?" queries
- Conversational handler with agent-type-aware replies
- Agent **uses its configured name** (`AGENT_NAME` env var) in all replies
- **Sidebar shows all 6 memory layers** (updated to match cognitive architecture):
  - Personality, Habits, Working, Episodic, Semantic, Consciousness
- Stores interactions in agent memory with importance scoring
- **Pink octopus logo** in header and sidebar; page icon 🐙
- **Browser-close watchdog** (`_start_browser_watchdog`): auto-exits when browser disconnects

### 7. Launch Executables (`start.exe` / `stop.exe`)
- **`start.exe`** — double-click to launch OctaMind:
  - Detects if dashboard is already running (port 8501 in use) — just opens browser if so
  - Finds the project `.venv` automatically (same folder as the exe)
  - Sets `PYTHONPATH` and spawns the Streamlit dashboard as a hidden background process
  - Waits up to 15 seconds for the server to be ready, then opens `http://localhost:8501` in the default browser
  - Console window shows start-up progress
- **`stop.exe`** — double-click to stop OctaMind:
  - Reads `running_agents.json`, kills every tracked agent process (by PID)
  - Kills the dashboard on port 8501
  - Sweeps ports 8502–8599 for any remaining agent windows
  - Clears `running_agents.json`
- Both built with **PyInstaller `--onefile`**, custom icon = `octopus.ico`
- Both exe files live at the **project root** (next to `agents.json`)
- Source scripts: `start.py` / `stop.py` at project root

### 8. Memory Consolidation Engine (`src/agent/memory/memory_consolidator.py`)
- **5-step consolidation** runs after 20 interactions or 24 hours:
  1. Working → Semantic: Extract patterns from recent interactions
  2. Episodic → Semantic: Surface repeated themes across events
  3. Habit detection: Confirm behavioral patterns (3+ occurrences required)
  4. **90-day decay** (✅ fully implemented):
     - Low + 90 days → **deleted** permanently
     - Medium + 90 days → **archived** to `archive/episodic_YYYY_MM.md`
     - High → kept forever in main `episodic_memory.md`
     - `_serialize_episodic_event()` helper for markdown round-trip
  5. Consciousness update: Meta-summary every 14 days
- Consolidation state persisted in `consolidation_state.json`
- Triggered from both `email_agent_ui.py` and `generic_agent_ui.py`

### 9. Email Agent Usage Documentation (`documentation/EMAIL_AGENT_USAGE_GUIDE.md`)
- Comprehensive "how to use" guide for the Gmail email agent
- Covers: counting, listing, sending, deleting, summarizing emails
- Natural language prompt examples for every feature
- Memory/recall prompts and explanations
- Sidebar reference, tips, Gmail query syntax examples
- Backend function reference table
- Known limitations and planned Phase 2 features

### 10. Email Features Modular Sub-package (`src/email/features/`) — **NEW (2026-02-21)**
13 standalone feature modules implemented and fully wired into the agent's LLM orchestrator and UI:

| Module               | Class                 | Key Functions                                                                     |
| -------------------- | --------------------- | --------------------------------------------------------------------------------- |
| `action_items.py`    | `ActionItemExtractor` | `extract_action_items(msg_id)`, `get_all_pending_actions()`                       |
| `smart_reply.py`     | `SmartReplyGenerator` | `generate_reply_suggestions(msg_id)`, `quick_reply(msg_id, type)`                 |
| `drafts.py`          | `DraftManager`        | `create_draft()`, `list_drafts()`, `send_draft()`, `delete_draft()`               |
| `attachments.py`     | `AttachmentManager`   | `list_attachments()`, `download_attachment()`, `search_emails_with_attachments()` |
| `categorizer.py`     | `EmailCategorizer`    | `auto_categorize_email()`, `apply_smart_labels()`                                 |
| `calendar_detect.py` | `CalendarDetector`    | `extract_calendar_events()`, `suggest_calendar_entry()`                           |
| `followup.py`        | `FollowupTracker`     | `mark_for_followup()`, `get_pending_followups()`, `check_unanswered_emails()`     |
| `scheduler.py`       | `EmailScheduler`      | `schedule_email()`, `list_scheduled_emails()`, `cancel_scheduled_email()`         |
| `contacts.py`        | `ContactIntelligence` | `get_frequent_contacts()`, `get_contact_summary()`                                |
| `priority.py`        | `PriorityDetector`    | `detect_urgent_emails()`, `auto_prioritize()`                                     |
| `unsubscribe.py`     | `UnsubscribeDetector` | `detect_newsletters()`, `extract_unsubscribe_link()`                              |
| `analytics.py`       | `EmailAnalytics`      | `get_email_stats(days)`, `get_productivity_insights()`                            |

**Integration points:**
- All 13 modules imported by `src/email/features/__init__.py` (package with full `__all__`)
- `GmailServiceClient` in `gmail_service.py` has lazy delegation methods for all 34 new operations (via generic `_feature()` lazy loader pattern)
- `src/email/__init__.py` re-exports all 34 new functions
- `llm_parser.py` → `orchestrate_mcp_tool()` extended with 30 tool definitions (was 5)
- `email_agent_ui.py` → `execute_with_llm_orchestration()` handles all 30 new tools; `format_email_result()` delegates to `_format_new_feature_result()` which formats all new action types
- `handle_conversation()` keyword list expanded with 20+ new email action words

**Technical patterns used:**
- Each module: Class + Optional singleton + module-level convenience functions
- LLM calls: `GitHubModelsLLM` via `get_llm_client()`, temperature = 0.1 for analysis, 0.7 for generation
- Persistent storage: `data/email_followups.json`, `data/email_schedule.json`
- Scheduler: daemon thread (60s check loop), `threading.Lock` for thread-safe JSON I/O
- Gmail labels: `OctaMind/<Category>` with color coding, cached to avoid repeated API calls
- Attachment downloads: default to `~/Downloads/OctaMind_Attachments`, auto-increment on conflict

### 12. Agent Personality Traits — Structured Sliders
- **Five personality traits** configurable at agent creation time (and editable later via Configure panel):
  | Trait         | Scale                    | Effect on agent behaviour                    |
  | ------------- | ------------------------ | -------------------------------------------- |
  | Tone          | 0=Formal ↔10=Casual      | Adjusts formality of language                |
  | Verbosity     | 0=Brief ↔10=Detailed     | Controls response length                     |
  | Humor         | 0=Serious ↔10=Witty      | Adds/removes wit and lightness               |
  | Empathy       | 0=Neutral ↔10=Warm       | Adjusts warmth and emotional acknowledgement |
  | Proactiveness | 0=Reactive ↔10=Proactive | Controls how much the agent volunteers info  |
- Traits stored in `agents.json` under `config.personality_traits`
- On agent creation, `_build_personality_md()` renders a structured Markdown table and writes it to `memory/<agent_id>/personality.md`
- Combined with existing LLM context caps so personality is injected every turn (last 1 500 chars)
- **`update_personality_traits(agent_id, traits)`** on `AgentManager` persists changes and rewrites `personality.md` atomically
- Default trait values: `{tone:3, verbosity:5, humor:2, empathy:6, proactiveness:5}`

### 13. Automation Scheduler & Configure Panel

**Configure Panel (`show_configure_panel()` in `agent_dashboard.py`)**
- Accessed via ⚙️ Configure button on any agent card — shows full configuration interface inline
- Two-tab layout:
  - **🎭 Personality Traits** — sliders pre-filled from stored traits, **Save Personality** persists to `agents.json` + `personality.md`
  - **⚙️ Automations** — agent-type-aware list of recurring automations with toggles + optional settings
- Configure button toggles to **✖ Close Config** when open; closes cleanly on re-click

**Automation Scheduler (`src/agent/core/automation_scheduler.py`)**
- Lightweight background daemon thread (no external dependencies — pure Python `threading`)
- Singleton per agent process — started once via `start_scheduler(agent_id)`, called from `email_agent_ui.py` on startup
- Checks all enabled automations every **30 seconds** (was 60 s; lowered to support the 30-second frequency option)
- Per-automation state stored in `memory/<agent_id>/automation_config.json`
- Reads config fresh on every tick (picks up live changes from Configure panel immediately)
- Writes `last_run` ISO timestamp after each successful execution
- Both interval scheduling and "never ran → run now" logic implemented
- `_is_due()` reads `interval_minutes` from the saved config entry first, falls back to the catalog default

**Gmail Automations (`src/agent/core/automations/gmail_automations.py`)**
10 built-in automations for Gmail agents:

| #   | Automation ID              | Label                        | Default Interval | Configurable Params              |
| --- | -------------------------- | ---------------------------- | :--------------: | -------------------------------- |
| 1   | `auto_delete_spam`         | 🗑 Auto-delete spam           |      15 min      | —                                |
| 2   | `auto_archive_newsletters` | 📁 Auto-archive newsletters   |      30 min      | Archive label name               |
| 3   | `daily_digest`             | 📋 Daily email digest         |       24 h       | —                                |
| 4   | `auto_label_vip`           | ⭐ Auto-label VIP emails      |      15 min      | —                                |
| 5   | `flag_old_unread`          | 🚩 Flag old unread emails     |       24 h       | Age threshold (days)             |
| 6   | `weekly_report`            | 📊 Weekly productivity report |      7 days      | —                                |
| 7   | `auto_categorize`          | 🗂 Auto-categorize by domain  |      30 min      | —                                |
| 8   | `auto_unsubscribe`         | 🔕 Detect promotional senders |      7 days      | Confidence threshold (0.5–1.0)   |
| 9   | `out_of_office`            | 💬 Auto-reply (Out of Office) |      15 min      | Reply message, active-until date |
| 10  | `archive_old_read`         | 🧹 Archive old read emails    |       24 h       | Age threshold (days)             |

- Each automation logs result to Python logger and writes episodic memory events where appropriate
- Automations are **agent-type-aware** — the catalog system (`automation_config.py`) allows future agent types to register their own automations without touching existing code
- Enabling/disabling a toggle in the Configure panel saves immediately to `automation_config.json` — the scheduler picks it up on the next 30-second tick
- **⏱ Run Frequency selector** — Settings expander shown for all enabled automations; 10 options from 30 s to 24 h; persisted as `interval_minutes` in `automation_config.json`

**Automation Config (`src/agent/core/automations/automation_config.py`)**
- `AUTOMATION_CATALOG` dict: agent_type → {automation_id → metadata, defaults, param_schema}
- `load_automation_config(agent_id)` / `save_automation_config(agent_id, config)` — JSON I/O
- `update_automation_state(agent_id, auto_id, enabled, params, interval_minutes)` — atomic single-automation update; optional `interval_minutes` float is persisted alongside params and read by the scheduler
- `get_automations_for_agent_type(agent_type)` — returns the relevant catalog subset

```bash
# Option A — double-click (no terminal needed)
start.exe    ← launches dashboard, opens browser
stop.exe     ← stops everything

# Option B — terminal
$env:PYTHONPATH = "C:\Hrishikesh\OctaMind"
& .venv\Scripts\Activate.ps1
python -m streamlit run src/agent/agent_dashboard.py --server.port 8501
```

---

## 🔄 In Progress / Partially Working

| Feature                 | Status               | Notes                                                                                                        |
| ----------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------ |
| Non-Gmail agent actions | UI ready, no backend | Responds in chat but can't perform real actions yet                                                          |
| Episodic insights       | Hardcoded            | `insight = "User performed {action}"` — LLM-generated insights not yet done                                  |
| Slim routing context    | Not started          | `execute_with_llm_orchestration()` sends full context; a `get_routing_context_for_llm()` slim variant needed |

---

## 📋 Planned (Requirement Phase 2+)

| #   | Feature                                                                    |
| --- | -------------------------------------------------------------------------- |
| 1   | Google Drive integration — list/upload/download files                      |
| 2   | Slack integration — send/read messages                                     |
| 3   | Calendar integration — create/list events (Google Calendar API)            |
| 4   | Stock Market integration — live price data (Yahoo Finance / Alpha Vantage) |
| 5   | Agent auto-run on dashboard startup (if `auto_run: true` in config)        |
| 6   | Inter-agent communication (agents can trigger each other)                  |
| 7   | Agent activity log / audit trail                                           |
| 8   | Automations for Drive / Slack / Calendar / Stock Market agent types        |
| 9   | LLM-generated episodic insights (replace hardcoded summary string)         |
| 10  | Slim routing context variant for `execute_with_llm_orchestration()`        |

---

## 🗂️ Project File Reference

```
src/
  agent/
    core/
      agent_manager.py       ← Agent CRUD + AGENT_TYPES + personality_traits + update_personality_traits()
      process_manager.py     ← Subprocess spawn/stop/track
      automation_scheduler.py← ⭐ Background daemon scheduler (pure Python threading, 60-s tick)
      automations/
        __init__.py          ← Package re-exports
        automation_config.py ← AUTOMATION_CATALOG + JSON config I/O per agent
        gmail_automations.py ← 10 Gmail automation handler functions + HANDLER_MAP
    memory/
      agent_memory.py        ← ⭐ Cognitive memory system (6 layers, caps, recall_for_llm)
      memory_consolidator.py ← 5-step consolidation + ✅ 90-day decay with archival
    llm/
      llm_parser.py          ← GitHub Models LLM parser (chat + orchestration)
    ui/
      agent_dashboard.py     ← ⭐ Main hub dashboard (port 8501) — personality sliders + configure panel
      email_agent_ui.py      ← Gmail agent chat (port 8502+) — scheduler wired on startup
      generic_agent_ui.py    ← Universal agent chat (non-Gmail) with memory
      gemma_chat_ui.py       ← Local Gemma model chat
    assets/
      octopus.png            ← Pink octopus logo (used in all windows)
      octopus.ico            ← Converted icon (used by start.exe / stop.exe)
  email/
    gmail_auth.py            ← OAuth2 authentication
    gmail_service.py         ← Gmail API operations + delegation to all 13 features
    email_summarizer.py      ← Email summarisation (renamed from gmail_summarizer.py)
    features/
      __init__.py            ← Package (exports all 13 modules, full __all__)
      action_items.py        ← ActionItemExtractor — task/deadline extraction from email
      smart_reply.py         ← SmartReplyGenerator — 3-tone reply suggestions + quick replies
      drafts.py              ← DraftManager — Gmail Drafts CRUD
      attachments.py         ← AttachmentManager — list/download/search attachments
      categorizer.py         ← EmailCategorizer — LLM category + OctaMind/ Gmail labels
      calendar_detect.py     ← CalendarDetector — extract meeting events from email
      followup.py            ← FollowupTracker — follow-up reminders (JSON persistence)
      scheduler.py           ← EmailScheduler — schedule emails for later (daemon thread)
      contacts.py            ← ContactIntelligence — frequent contacts + VIP detection
      priority.py            ← PriorityDetector — urgency score 1-10 via LLM
      unsubscribe.py         ← UnsubscribeDetector — newsletter detection + unsubscribe links
      analytics.py           ← EmailAnalytics — email stats + productivity insights

memory/
  <agent_id>/
    working_memory.md        ← Short-term, RAM-like (max 10 items)
    episodic_memory.md       ← Events with importance scoring (auto-decayed after 90 days)
    semantic_memory.md       ← Distilled user knowledge
    personality.md           ← Assistant behavior profile
    habits.md                ← Behavioral patterns (3+ confirmations)
    consciousness.md         ← Meta summary layer
    consolidation_state.json ← Last consolidation timestamp + interaction counter
    archive/
      episodic_YYYY_MM.md    ← Medium-importance events archived by month

documentation/
  EMAIL_AGENT_USAGE_GUIDE.md ← ⭐ How to use the email agent (prompts, features, tips)
  GMAIL_SETUP.md             ← OAuth2 credentials setup
  GMAIL_QUICKSTART.md        ← 5-minute quick start
  README_GMAIL_INTEGRATION.md← API reference

requirement/
  memory_architecture.md     ← ⭐ Cognitive architecture specification (fully implemented)
  email-functionality.md     ← Email feature roadmap (next: Action Item Extraction)
  octaMind-requirement.txt   ← Original product requirements
  octaMind-functionality.md  ← This file

architecture/
  memory-system.md           ← v1.1 — Living reference for memory system (auto-updated)

start.py / start.exe         ← Launch OctaMind (double-click)
stop.py  / stop.exe          ← Stop OctaMind (double-click)
agents.json                  ← Agent configurations
running_agents.json          ← Live process tracking (pid + port)
```

---

## 📝 Recent Changes (2026-02-21) — Automation Bug Fixes + Run-Frequency Selector

### Automation Bug Fixes (`src/agent/core/automations/gmail_automations.py`)
- **`out_of_office`** — Fixed critical bug: `send_email()` was called with `body=reply_message` but the parameter is `message=`; was silently `TypeError`-ing on every run so no reply was ever sent
- **`out_of_office`** — Added deduplication: marks replied emails as read (`UNREAD` label removed) so the same email is never replied to again on the next tick
- **`out_of_office`** — Inner `except Exception: pass` → `logger.error()` + error summary in the return string
- **`auto_archive_newsletters`** — Query now filters `is:read label:promotions in:inbox` (was archiving all promotions incl. unread)
- **`daily_digest`** — Digest content now saved to episodic memory (up to 600 chars); return value includes digest preview
- **`auto_categorize`** — Per-email `except Exception: pass` → `logger.warning()` so failures appear in logs
- **`weekly_report`** + **`auto_unsubscribe`** — Memory-write `except Exception: pass` → `logger.warning()` in both

### Run-Frequency Selector (`src/agent/ui/agent_dashboard.py`)
- Added **⏱ Run Frequency** selectbox in the Settings expander for every enabled automation
- 10 presets: 30 s, 1 min, 5 min, 15 min (default), 30 min, 1 h, 2 h, 6 h, 12 h, 24 h
- Persisted as `interval_minutes` (float) in `automation_config.json`
- Settings expander now shown for **all** enabled automations (previously only for automations with `param_schema`)
- Scheduler tick lowered from 60 s → 30 s to support sub-minute frequency

---

## 📝 Recent Changes (2026-02-21) — Personality + Automations

### Personality Traits
- Added 5-trait personality slider system (tone, verbosity, humor, empathy, proactiveness)
- `_build_personality_md()` helper renders structured `personality.md` from traits on agent creation
- `update_personality_traits()` on `AgentManager` for post-creation edits
- `DEFAULT_PERSONALITY_TRAITS` dict exported for use in UI
- `create_agent()` signature extended with `personality_traits` optional param

### Automation Scheduler
- New `src/agent/core/automation_scheduler.py` — singleton daemon thread, 60-second tick
- New `src/agent/core/automations/` package with `automation_config.py` + `gmail_automations.py`
- 10 Gmail automations registered in `AUTOMATION_CATALOG`
- Scheduler started in `email_agent_ui.py::main()` via `start_scheduler(agent_id)`
- Per-agent config in `memory/<agent_id>/automation_config.json`

### Configure Panel
- `show_configure_panel(agent)` function added to `agent_dashboard.py`
- Two-tab UI: Personality Traits (sliders + save) and Automations (live toggles + param settings)
- Configure button toggles to ✖ Close Config when open
- Removed "coming soon" placeholder entirely

---

## 📝 Recent Changes (2026-02-21) — Email Features Modular Sub-package
- Created `src/email/features/` sub-package with 13 feature modules
- Each module follows: Class + singleton + convenience functions pattern
- Persistent storage for follow-up tracker and email scheduler (`data/` folder)
- Background daemon thread for scheduled email delivery (60s check loop)
- Updated `gmail_service.py` → added `_feature()` lazy loader + 34 delegation methods
- Updated `src/email/__init__.py` → exports all 34 new functions
- Extended `llm_parser.py` → `orchestrate_mcp_tool()` system prompt now has 30 tool definitions
- Updated `email_agent_ui.py`:
  - Imports all 34 new feature functions
  - Added 30 new `elif tool_name ==` handlers in `execute_with_llm_orchestration()`
  - Added `_format_new_feature_result()` helper called by `format_email_result()`
  - Expanded `handle_conversation()` keyword list

---

## 📝 Recent Changes (2026-02-20)

### src/agent Subpackage Restructure
- Moved flat `src/agent/*.py` files into sub-packages: `core/`, `memory/`, `llm/`, `ui/`
- Updated all imports across 9 files
- Rebuilt `start.exe` / `stop.exe` with PyInstaller after restructure

### Memory System Improvements
- **LLM context caps** — `personality` (1500), `consciousness` (1000), `semantic` (3000), `habits` (1500) chars
- **`_tail()` helper** — returns last N chars keeping most-recent content in context
- **`recall_for_llm(query)`** — on-demand episodic search injected for recall-signal turns only
- Wired `recall_for_llm()` into `email_agent_ui.py::handle_conversation()`
- Deleted 12 stale legacy files (`short_term.md`, `long_term.md`, `context.md`) from all agent folders

### 90-Day Decay Mechanism — Fully Implemented
- Added `_serialize_episodic_event()` static helper to `MemoryConsolidator`
- `_apply_decay_mechanism()` now actually rewrites `episodic_memory.md` after decay classification
- Medium-importance old events moved to `archive/episodic_YYYY_MM.md` grouped by month
- Low-importance old events deleted permanently (no file write)
- Removed the `# TODO` comment — decay is now fully functional

### Email Agent Usage Documentation — New File
- Created `documentation/EMAIL_AGENT_USAGE_GUIDE.md`
- Covers all email commands with natural language prompt examples
- Memory/recall prompts explained
- Tips, Gmail query syntax, backend function reference
- Known limitations and Phase 2 feature roadmap

### Architecture Documentation Updated
- `architecture/memory-system.md` updated to v1.1 with all above changes
- `requirement/memory_architecture.md` updated to reflect current implementation

---

## 📝 Recent Changes (2026-02-19)

### Cognitive Memory Architecture Implementation
- **Aligned with memory_architecture.md specification**
- Renamed memory files to match architecture:
  - `short_term.md` → `working_memory.md`
  - `long_term.md` → `semantic_memory.md`
  - `context.md` → merged into `working_memory.md`
  - Added `episodic_memory.md` (with importance scoring)
  - Added `consciousness.md` (meta summary layer)
- **"Do you remember...?" functionality** — Agents can now search all memory layers
- **Memory search** across working, episodic, and semantic layers
- **Importance scoring** for episodic events (High/Medium/Low)
- **Memory flow** properly structured (working → episodic → semantic → consciousness)
- **Both agent UIs updated** to handle memory queries and display new memory structure
- **Backward compatibility maintained** — Old method names still work

### Smart Memory Recall Enhancement
- **Fixed general recall queries** — Now handles "what did we do earlier?" correctly
- **Intent detection** — Distinguishes between general recall and specific searches
- **Context-aware search** — Removes stop words, extracts meaningful terms
- **Automatic recent activity summary** — Shows last 10 interactions for general queries
- **Better user experience** — No more "no memories found" for valid recall requests
