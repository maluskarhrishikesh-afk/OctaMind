# OctaMind — Project Architecture

> Last updated: February 2026 — added personality traits + automation scheduler
> Purpose: Living reference for structure, responsibilities, data-flow, and extension points.

---

## Table of Contents

- [OctaMind — Project Architecture](#octamind--project-architecture)
  - [Table of Contents](#table-of-contents)
  - [1. High-Level Overview](#1-high-level-overview)
  - [2. Repository Layout](#2-repository-layout)
  - [3. Root-Level Files](#3-root-level-files)
  - [4. `src/agent` — Agent Engine](#4-srcagent--agent-engine)
    - [4.1 `core/`](#41-core)
    - [4.2 `memory/`](#42-memory)
    - [4.3 `llm/`](#43-llm)
    - [4.4 `ui/`](#44-ui)
    - [4.5 `assets/`](#45-assets)
  - [5. `src/email` — Gmail Integration](#5-srcemail--gmail-integration)
  - [6. `tests/`](#6-tests)
  - [7. `memory/` — Runtime Agent Memory Store](#7-memory--runtime-agent-memory-store)
  - [8. Data \& Config Files](#8-data--config-files)
  - [9. Component Dependency Map](#9-component-dependency-map)
  - [10. Key Data Flows](#10-key-data-flows)
    - [10.1 Creating an Agent](#101-creating-an-agent)
    - [10.2 Starting an Agent](#102-starting-an-agent)
    - [10.3 Gmail Agent Conversation Turn](#103-gmail-agent-conversation-turn)
    - [10.4 Memory Consolidation](#104-memory-consolidation)
  - [11. How to Add New Features](#11-how-to-add-new-features)
    - [Add a new agent type (e.g., "github")](#add-a-new-agent-type-eg-github)
    - [Add a new memory layer](#add-a-new-memory-layer)
    - [Add a new LLM provider](#add-a-new-llm-provider)
    - [Add an email capability](#add-an-email-capability)
    - [Add a test](#add-a-test)

---

## 1. High-Level Overview

OctaMind is a **multi-agent AI platform** built on Streamlit. Each agent is:
- Defined in `agents.json` (metadata + type)
- Given a persistent multi-layer memory folder under `memory/<agent_id>/`
- Run as an isolated Streamlit subprocess on its own port (8502–8599)
- Managed through a central dashboard served on port **8501**

```
User
 │
 ▼
start.py / run_agent_hub.py
 │  launches
 ▼
src/agent/ui/agent_dashboard.py   ← port 8501 (main hub)
 │  spawns via process_manager
 ├─► src/agent/ui/email_agent_ui.py    ← port 850x (Gmail agent)
 └─► src/agent/ui/generic_agent_ui.py  ← port 850x (all other agents)
         │
         ├── src/agent/core/agent_manager.py   (CRUD agents.json)
         ├── src/agent/memory/agent_memory.py  (read/write memory/)
         ├── src/agent/memory/memory_consolidator.py
         └── src/agent/llm/llm_parser.py       (GitHub Models API)
                                │
                         src/email/            (Gmail operations)
```

---

## 2. Repository Layout

```
OctaMind/
├── start.py                    Entry point – launch dashboard, open browser
├── stop.py                     Gracefully kill all OctaMind processes
├── run_agent_hub.py            Alternative launcher (no browser open)
├── download_model.py           CLI wrapper to download Gemma model
├── view_agent_memory.py        CLI tool to inspect an agent's memory
│
├── agents.json                 Persistent registry of all created agents
├── running_agents.json         PID/port map of currently running agents
├── credentials.json            Google OAuth2 client credentials
├── token.json                  Google OAuth2 access/refresh token
├── .env                        API keys (GITHUB_TOKEN, etc.)
│
├── src/                        All importable source code
│   ├── agent/                  Agent engine (see §4)
│   └── email/                  Gmail integration (see §5)
│
├── memory/                     Runtime per-agent memory (see §7)
├── model_cache/                Locally cached HuggingFace models
├── architecture/               Architecture documentation (this folder)
│   ├── project-structure.md   ← YOU ARE HERE
│   └── memory-system.md        Deep-dive on the memory layer
├── documentation/              User-facing guides and setup docs
├── requirement/                Product requirements and feature specs
└── tests/                      Automated tests (see §6)
```

---

## 3. Root-Level Files

| File                   | What it does                                                                                                                                 |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `start.py`             | Activates venv, starts Streamlit on port 8501, waits for readiness, opens browser. Compiled to `start.exe` via PyInstaller for distribution. |
| `stop.py`              | Reads `running_agents.json`, kills all agent PIDs, then kills port 8501 (dashboard). Compiled to `stop.exe`.                                 |
| `run_agent_hub.py`     | Simpler launcher — just `streamlit run` the dashboard (no auto-browser). Useful in development.                                              |
| `download_model.py`    | CLI shim → calls `src/agent/llm/model_downloader.py:main()` to pull Gemma from HuggingFace.                                                  |
| `view_agent_memory.py` | Debug utility — prints all memory layers for a given `agent_id` to stdout.                                                                   |
| `test_*.py` (root)     | Integration-level smoke tests run directly (not via pytest runner).                                                                          |
| `agents.json`          | Array of agent dicts: `id`, `name`, `type`, `role`, `created_at`, `enabled`, `config`. Source of truth for agent list.                       |
| `running_agents.json`  | Auto-managed by `process_manager.py`. Maps `agent_id → {pid, port}`. Cleared on stop.                                                        |
| `.env`                 | `GITHUB_TOKEN` for GitHub Models LLM API. Never committed.                                                                                   |
| `credentials.json`     | Google OAuth2 client secret (Desktop App). Needed for Gmail auth.                                                                            |
| `token.json`           | Auto-generated OAuth token. Refreshed automatically by `gmail_auth.py`.                                                                      |

---

## 4. `src/agent` — Agent Engine

The agent engine is split into four sub-packages, each with its own `__init__.py`.  
The parent `src/agent/__init__.py` re-exports all public symbols so callers can use either path.

```
src/agent/
├── __init__.py          Re-exports everything from sub-packages
├── assets/              Static files (logo, favicon)
├── core/                Lifecycle & process management
├── memory/              Multi-layer memory system
├── llm/                 LLM backends & local model utilities
└── ui/                  Streamlit UIs
```

---

### 4.1 `core/`

**Responsibility:** Agent CRUD and subprocess lifecycle.

| File                 | Class / Key Functions                                                                                 | Purpose                                                                                                                                                     |
| -------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent_manager.py`   | `AgentManager`, `get_agent_manager()`                                                                 | Creates, lists, updates, deletes agents in `agents.json`. Also initialises the memory folder when an agent is created. Singleton via `get_agent_manager()`. |
| `process_manager.py` | `start_agent()`, `stop_agent()`, `get_agent_status()`, `cleanup_stale()`, `remove_agent_from_state()` | Spawns/kills per-agent Streamlit subprocesses. Persists PID+port state to `running_agents.json`. Resolves which UI script to launch based on `agent_type`.  |

**Agent type → UI script mapping** (defined in `process_manager.py`):

| Agent type                                                    | Streamlit script                   |
| ------------------------------------------------------------- | ---------------------------------- |
| `gmail`                                                       | `src/agent/ui/email_agent_ui.py`   |
| `google_drive`, `slack`, `calendar`, `stock_market`, `custom` | `src/agent/ui/generic_agent_ui.py` |

**To add a new agent type:** add an entry to `AgentManager.AGENT_TYPES` in `agent_manager.py` and add the mapping in `_AGENT_SCRIPTS` in `process_manager.py`.

---

### 4.2 `memory/`

**Responsibility:** Persistent multi-layer memory for each agent. See [`memory-system.md`](memory-system.md) for the full spec.

| File                     | Class / Key Functions               | Purpose                                                                                                                                                                                                                        |
| ------------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `agent_memory.py`        | `AgentMemory`, `get_agent_memory()` | Manages all memory layers as markdown files under `memory/<agent_id>/`. Provides read/write APIs for each layer. Triggers consolidation.                                                                                       |
| `memory_consolidator.py` | `MemoryConsolidator`                | Background consolidation engine — extracts patterns from working memory → semantic memory, detects habits (3+ confirmations), applies 90-day decay, updates consciousness layer. Called via `AgentMemory.run_consolidation()`. |

**Memory layers** (stored as `.md` files):

| File                 | Layer                         | Auto-managed by          |
| -------------------- | ----------------------------- | ------------------------ |
| `working_memory.md`  | Current session context       | Agent UI on each message |
| `short_term.md`      | Recent interactions           | Agent UI                 |
| `episodic_memory.md` | Memorable events              | Agent UI                 |
| `semantic_memory.md` | Extracted patterns/facts      | `MemoryConsolidator`     |
| `long_term.md`       | Stable knowledge              | `MemoryConsolidator`     |
| `habits.md`          | Detected behavioural patterns | `MemoryConsolidator`     |
| `personality.md`     | Stable personality traits     | Manual / consolidation   |
| `context.md`         | Agent-specific config context | Manual                   |
| `consciousness.md`   | Meta-summary of self          | `MemoryConsolidator`     |

---

### 4.3 `llm/`

**Responsibility:** All LLM and model-handling logic.

| File                  | Class / Key Functions                                                        | Purpose                                                                                                                                                                     |
| --------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `llm_parser.py`       | `GitHubModelsLLM`, `get_llm_client()`                                        | Wraps the GitHub Models API (OpenAI-compatible). Handles tool-call parsing, structured JSON extraction, and email command classification. Singleton via `get_llm_client()`. |
| `gemma_runner.py`     | `load_model_and_processor()`, `generate_response()`, `find_local_snapshot()` | Loads Google Gemma 3 4B from local `model_cache/` using HuggingFace Transformers + optional 4-bit BitsAndBytes. Runs inference.                                             |
| `model_downloader.py` | `download_gemma()`, `HARD_CODED_HF_TOKEN`                                    | Downloads Gemma weights from HuggingFace Hub into `model_cache/`. Called by `download_model.py`.                                                                            |
| `gemma_chat_ui.py`    | `load_model_and_processor()`, `generate_response()`, `main()`                | Standalone Streamlit chat UI that loads Gemma locally. Independent from the agent system — used for direct local model experimentation.                                     |

**LLM selection logic:**  
- Production agents use `GitHubModelsLLM` (cloud, low-latency, no GPU needed).  
- `gemma_runner.py` / `gemma_chat_ui.py` are for local GPU testing only.

---

### 4.4 `ui/`

**Responsibility:** All Streamlit frontends.

| File                  | Purpose                                                                                                                                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `agent_dashboard.py`  | Main hub (port 8501). Lists all agents, shows status badges, provides Start/Stop/Open controls, and the "Create Agent" form. Imports from `core/`.                                                                                   |
| `email_agent_ui.py`   | Full Gmail agent chat UI. Handles natural-language email commands (send, list, count, delete, summarise, digest). Uses `llm_parser.py` for LLM-orchestrated routing and `src/email/` for Gmail API calls. Reads/writes agent memory. |
| `generic_agent_ui.py` | Fallback chat UI for all non-Gmail agent types (Drive, Slack, Calendar, etc.). Shows agent memory, personality, and context. Responds conversationally via LLM.                                                                      |

All three UI files:
- Load `octopus.png` from `../assets/` (one level up from `ui/`)
- Accept `AGENT_ID`, `AGENT_NAME`, `AGENT_TYPE` from environment variables set by `process_manager.py`
- Start a browser watchdog that stops the Streamlit process if the browser tab closes

---

### 4.5 `assets/`

| File                | Usage                                      |
| ------------------- | ------------------------------------------ |
| `octopus.png`       | Page icon and header logo in all three UIs |
| `octamind_logo.svg` | SVG variant for future use                 |
| `octopus.ico`       | Windows taskbar icon (used by PyInstaller) |

---

## 5. `src/email` — Gmail Integration

**Responsibility:** All Gmail API interaction and email summarisation.

| File                  | Class / Key Functions                                                                                                                                                                      | Purpose                                                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gmail_auth.py`       | `get_gmail_service()`                                                                                                                                                                      | OAuth2 flow using `credentials.json` + `token.json`. Returns an authenticated `googleapiclient` Gmail service object. Auto-refreshes expired tokens.                               |
| `gmail_service.py`    | `GmailServiceClient`, `send_email()`, `list_emails()`, `get_inbox_count()`, `get_todays_emails()`, `delete_emails()`, `summarize_email()`, `summarize_thread()`, `generate_daily_digest()` | High-level Gmail operations. Module-level helper functions delegate to a singleton `GmailServiceClient`. Used directly by `email_agent_ui.py`.                                     |
| `gmail_summarizer.py` | `EmailSummarizer`                                                                                                                                                                          | LLM-powered email summarization (single email, thread, or daily digest). Uses `GitHubModelsLLM` from `src/agent/llm/llm_parser.py` with graceful fallback to rule-based summaries. |
| `mcp_server.py`       | `GmailContext`, `list_message()`, `send_message()`                                                                                                                                         | Standalone **Model Context Protocol (MCP)** server exposing Gmail as an MCP tool. Independent of the agent UI — used for MCP-compatible clients (e.g., Claude Desktop).            |
| `__init__.py`         | Re-exports `GmailServiceClient` and all helper functions                                                                                                                                   | Public interface of the email package.                                                                                                                                             |

---

## 6. `tests/`

```
tests/
├── __init__.py
├── README.md
├── agent/
│   ├── test_agent_deletion.py     Tests agent delete + memory folder cleanup
│   ├── test_agent_memory.py       Tests memory read/write per layer
│   ├── test_count_action.py       Tests COUNT email command parsing
│   └── test_llm_parser.py         Tests LLM-based command classification
└── integration/
    └── test_new_structure.py      Smoke test for the reorganised package structure
```

Root-level `test_*.py` scripts are heavier integration tests run manually:

| Script                          | What it tests                                             |
| ------------------------------- | --------------------------------------------------------- |
| `test_email_summarization.py`   | Full email summarize + digest pipeline against live Gmail |
| `test_immediate_memory.py`      | Memory folder is created immediately on agent creation    |
| `test_memory_consolidation.py`  | Full consolidation cycle (patterns, habits, decay)        |
| `test_restart_consolidation.py` | Consolidation state persists across simulated restarts    |

---

## 7. `memory/` — Runtime Agent Memory Store

Auto-created and managed. **Do not edit manually during a running session.**

```
memory/
└── <agent_id>/          One folder per agent (8-char UUID prefix)
    ├── working_memory.md
    ├── short_term.md
    ├── episodic_memory.md
    ├── semantic_memory.md
    ├── long_term.md
    ├── habits.md
    ├── personality.md
    ├── context.md
    ├── consciousness.md
    ├── consolidation_state.json   (timer / trigger state for consolidator)
    └── archive/                   Old versions of memory files
```

When an agent is **deleted** via the dashboard, its entire `memory/<agent_id>/` folder is removed by `AgentManager.delete_agent()`.

---

## 8. Data & Config Files

| File                                   | Format      | Managed by           | Contains                      |
| -------------------------------------- | ----------- | -------------------- | ----------------------------- |
| `agents.json`                          | JSON array  | `AgentManager`       | Agent definitions             |
| `running_agents.json`                  | JSON dict   | `process_manager`    | `{agent_id: {pid, port}}`     |
| `.env`                                 | Key=Value   | Developer            | `GITHUB_TOKEN`                |
| `credentials.json`                     | Google JSON | Google Cloud Console | OAuth2 client secret          |
| `token.json`                           | Google JSON | `gmail_auth.py`      | OAuth2 access + refresh token |
| `memory/<id>/consolidation_state.json` | JSON        | `MemoryConsolidator` | Last-run timestamps, counters |

---

## 9. Component Dependency Map

```
start.py / stop.py / run_agent_hub.py
    └── (shell: streamlit run)
            │
            ▼
    ui/agent_dashboard.py
        ├── core/agent_manager.py ──► agents.json
        └── core/process_manager.py ──► running_agents.json
                │ (subprocess: streamlit run)
                ▼
        ui/email_agent_ui.py          ui/generic_agent_ui.py
            ├── llm/llm_parser.py          ├── llm/llm_parser.py
            ├── memory/agent_memory.py     ├── memory/agent_memory.py
            ├── core/process_manager.py    └── core/agent_manager.py
            └── src/email/
                    ├── gmail_auth.py
                    ├── gmail_service.py
                    └── gmail_summarizer.py
                            └── llm/llm_parser.py

memory/agent_memory.py
    └── memory/memory_consolidator.py   (lazy import, called periodically)

llm/gemma_runner.py ◄── llm/gemma_chat_ui.py   (standalone, no agent dependency)
llm/model_downloader.py ◄── download_model.py
```

---

## 10. Key Data Flows

### 10.1 Creating an Agent

```
Dashboard (Create form)
  → show_create_agent_form() — personality sliders (optional, defaults pre-filled)
  → AgentManager.create_agent(name, type, role, config, personality_traits)
      → writes entry to agents.json  (includes config.personality_traits)
      → calls get_agent_memory(agent_id)
          → creates memory/<agent_id>/ with all template .md files
      → calls _build_personality_md(name, role, traits)
          → overwrites personality.md with structured trait table
  → UI re-renders agent card
```

### 10.2 Starting an Agent

```
Dashboard (Start button)
  → process_manager.start_agent(agent_id, name, type)
      → resolves script path from _AGENT_SCRIPTS[type]
      → subprocess.Popen(streamlit run <script> --server.port <free_port>)
          sets env: AGENT_ID, AGENT_NAME, AGENT_TYPE, PYTHONPATH
      → writes {agent_id: {pid, port}} to running_agents.json
  → Dashboard shows "Open" button with URL
```

### 10.3 Gmail Agent Conversation Turn

```
User types message
  → handle_conversation()
      → execute_with_llm_orchestration(user_query)
          → GitHubModelsLLM.parse_email_command(query)
              → GitHub Models API → returns {action, params}
          → execute_email_action(action, params)
              → src/email/gmail_service → Gmail API
          → format_email_result(result)
      → AgentMemory.add_to_working_memory(turn)
      → every 20 turns → AgentMemory.run_consolidation()
  → Response rendered in chat
```

### 10.4 Memory Consolidation

```
AgentMemory.run_consolidation()
  → MemoryConsolidator.should_consolidate()  (20 interactions OR 24h elapsed)
  → MemoryConsolidator.consolidate()
      → _extract_patterns_from_working_memory()  → updates semantic_memory.md
      → _extract_patterns_from_episodic()        → updates semantic_memory.md
      → _detect_habits()                          → updates habits.md (3+ needed)
      → _apply_memory_decay()                     → removes >90-day entries
      → _update_consciousness_layer()             → updates consciousness.md
  → saves consolidation_state.json
```

```
Agent UI process starts
  → main()  (email_agent_ui.py)
      → start_scheduler(agent_id)           ← starts AutomationScheduler daemon thread
          → AutomationScheduler._run_loop()  ← every 60 s:
              → load_automation_config(agent_id)  ← reads memory/<id>/automation_config.json
              → for each enabled automation whose interval has elapsed:
                  → handler(agent_id, params)      ← Gmail automation function
                  → _touch_last_run(automation_id) ← writes last_run to config
```

### 10.5 Configure Panel

```
Dashboard (⚙️ Configure button)
  → st.session_state.configure_agent_id = agent_id
  → show_configure_panel(agent)
      → Personality tab:
          → sliders pre-filled from agent['config']['personality_traits']
          → Save → AgentManager.update_personality_traits(agent_id, new_traits)
                   → updates agents.json
                   → rewrites memory/<id>/personality.md
      → Automations tab:
          → catalog = get_automations_for_agent_type(agent_type)
          → toggle → update_automation_state(agent_id, auto_id, enabled, params)
                     → writes memory/<id>/automation_config.json
                     (scheduler picks up change on next 60-s tick)
```

---

## 11. How to Add New Features

### Add a new agent type (e.g., "github")

1. **Register the type** — add to `AgentManager.AGENT_TYPES` in `src/agent/core/agent_manager.py`:
   ```python
   "github": {"label": "GitHub", "icon": "🐙", "description": "..."}
   ```
2. **Map to a UI** — add to `_AGENT_SCRIPTS` in `src/agent/core/process_manager.py`:
   ```python
   "github": "src/agent/ui/github_agent_ui.py",
   ```
3. **Create the UI** — add `src/agent/ui/github_agent_ui.py` modelled on `generic_agent_ui.py`.
4. **Add business logic** — if it needs a new service (like email needs `src/email/`), create `src/github/` with its own `__init__.py`.

---

### Add a new memory layer

1. Add the template to the file-creation loop in `AgentMemory.__init__()` → `_create_memory_files()`.
2. Add read/write methods to `AgentMemory` following the existing pattern.
3. Optionally hook `MemoryConsolidator` to populate it automatically.
4. Document the new layer in [`memory-system.md`](memory-system.md).

---

### Add a new LLM provider

1. Create a new class in `src/agent/llm/llm_parser.py` (or a new file in `src/agent/llm/`).
2. Implement the same interface as `GitHubModelsLLM`: `chat()`, `parse_email_command()`.
3. Update `get_llm_client()` to return the new class based on an env-var or config setting.

---

### Add an email capability

1. Add the operation to `GmailServiceClient` in `src/email/gmail_service.py`.
2. Expose it as a module-level function and export it from `src/email/__init__.py`.
3. Add the new action to the routing logic in `execute_with_llm_orchestration()` in `src/agent/ui/email_agent_ui.py`.
4. Update the LLM system prompt in `llm_parser.py` to recognise the new command.

---

### Add an automation for a new agent type

1. **Define the catalog** — add a new dict to `AUTOMATION_CATALOG` in `src/agent/core/automations/automation_config.py`:
   ```python
   "google_drive": {
       "sync_recent_files": {
           "label": "📥 Sync recent files",
           "description": "Download files modified in the last N days",
           "interval_minutes": 60,
           "default_params": {"days": 1},
           "param_schema": {
               "days": {"type": "number", "label": "Lookback (days)", "min": 1, "max": 30},
           },
       },
   }
   ```
2. **Write the handler** — create `src/agent/core/automations/drive_automations.py` following the same pattern as `gmail_automations.py`.
3. **Register the handler** — import the new `HANDLER_MAP` in `AutomationScheduler._load_handlers()` inside `automation_scheduler.py`.
4. **Wire the scheduler** — call `start_scheduler(agent_id)` in the new agent's UI `main()` function.
5. **Test** — add a toggle in the Configure panel (it will appear automatically, no UI code needed).

---

### Add a test

- **Unit test** → `tests/agent/` (use existing files as templates, run with `pytest`)
- **Integration / smoke test** → root-level `test_*.py` (run directly with `python`)

---

*For the memory layer internals (file formats, consolidation thresholds, decay curves), see [`memory-system.md`](memory-system.md).*
