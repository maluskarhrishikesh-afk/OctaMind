# Octa Bot — Architecture

Last updated: 2026-03-08

> **See also:** [DAG_WALKTHROUGH.md](DAG_WALKTHROUGH.md) for a complete step-by-step trace of the DAG algorithm through two worked examples (simple single-skill and complex multi-agent).

---

## System Overview

```
+----------------------------------------------------------+
�  Agent Hub Dashboard  (port 8501, always on)              �
�  Streamlit UI for creating / starting / stopping agents.  �
�  State persisted in running_agents.json.                  �
+----------------------------------------------------------+
                      �  subprocess.Popen per agent
 +-----------------------------------------------------------------------------------------------------------------------------------+
 �          �          �          �          �          �          �          �          �          �          �          �          �
Email     Drive      Files   WhatsApp  Telegram  Calendar  Browser   Stock    LinkedIn  Habit    Scheduler  Personal
Agent     Agent      Agent    Agent     Agent     Agent     Agent    Agent     Agent     Agent     Agent     Assistant
(each is an isolated Streamlit process with its own st.session_state)
```

**Skills vs Personal Assistants:**
- **Skills** (Email, Drive, Files, WhatsApp, Telegram, Calendar, Browser, Stock, LinkedIn, Habit, Scheduler) are stateless executors � no memory, no personality. They execute a single task and return.
- **Personal Assistants** have full 6-layer memory (working, episodic, semantic, personality, habits, consciousness) and a cross-domain `collective_consciousness.md`.

---

## Message Pipeline (per agent)

```
User types a message
        �
        ?
classify_intent()          LLM call: is this COMMAND or CHAT?
        �                  max_tokens=5, temperature=0
   CHAT � COMMAND
        �       �
        ?       ?
  llm.chat()  reason_and_act()           ReAct loop (up to 6 iterations)
  (casual)    +------------------+       Thought ? Action (tool call)
              � Tool executor    �  ?    ? Observation ? Thought ? ...
              � (Gmail/Drive API)�       until final_answer
              +------------------+
                      �
                      ?
            _compose_*_response()        Raw JSON result ? LLM ? friendly markdown
                      �
                      ?
               Streamlit chat UI
```

---

## Key Components

### `src/agent/llm/llm_parser.py` � `GitHubModelsLLM`

The single LLM client used by all agents.

| Method | Purpose | max_tokens | Notes |
|--------|---------|-----------|-------|
| `chat()` | Casual conversation | 300 | Uses full memory system prompt |

### `src/agent/ui/*/orchestrator.py` � ReAct Orchestrators

Each agent has its own orchestrator that:
1. Builds memory context from the agent's memory files
2. Calls `run_skill_dag()` (DAG planner) or `run_skill_react()` (ReAct loop) with tool docs loaded from `skills.md`
3. Returns `{"action": "react_response", "message": "<final_answer>"}` — a complete, LLM-formatted response

### `src/agent/ui/*/app.py` � Response Composition

After a tool result comes back, `_compose_*_response()` sends the raw JSON directly to the LLM with a formatting prompt. The LLM writes the final response (tables, bullets, emojis, bold). No hardcoded formatters.

### `src/agent/workflows/` � Multi-Agent Workflows

Multi-agent commands use a **two-level ReAct architecture**:

1. `router.py` ? `detect_agents_needed()` classifies the command (LLM, `max_tokens=5`)
2. `master_orchestrator.py` ? `react_workflow()` runs a **master ReAct loop** (up to 12 iterations). The orchestrator LLM sees only compact capability summaries (~10 tokens/agent) and uses `delegate_to_agent` or `final_answer` each turn.
3. Each `delegate_to_agent` call looks up the target in `agent_registry.py` and calls its `execute_with_llm_orchestration()`. This runs a **per-skill ReAct loop** via the shared `skill_react_engine.py` ? `run_skill_react()` (up to 6 iterations per skill).
4. Artifact handoff (e.g. a downloaded file path) is passed via an `artifacts_out` dict and reported back to the master loop as an observation. The master loop copies the path literally into the next delegation instruction.
5. The authenticated user's email address is injected into the master system prompt at runtime so `email me` instructions always resolve to the correct address.

**Context cost:** ~445 tokens for 2 agents (vs ~8,000 for a flat tool-list design). Adding an agent = one entry in `agent_registry.py`; orchestrator context does not grow.

**Shared skill engine:** `src/agent/workflows/skill_react_engine.py` — `run_skill_react()` is the shared ReAct loop used by every skill orchestrator and serves as the **fallback path**.

**Sub-agent DAG engine (new):** `src/agent/workflows/skill_dag_engine.py` — `run_skill_dag()` is the **primary path** for Email, Files and Drive agents. Instead of iterating 1-call-per-step, it uses exactly **2 LLM calls** per task regardless of complexity: one to plan a list of tool steps (JSON), then tools execute deterministically, then one synthesis call produces the friendly final answer. Falls back to `run_skill_react()` automatically if planning fails or returns an unknown tool.

Single-agent commands routed through the Personal Assistant bypass the multi-agent planner and call the individual skill's ReAct orchestrator directly.

---

## Multi-Agent Routing

```
User command
      �
      ?
detect_agents_needed()          (1 LLM call, max_tokens=5)
      �
   +------------------------------------------------+
   ?                     ?                           ?
 NEITHER             SINGLE AGENT               MULTI-AGENT
(casual chat)      (any single skill)           (2+ agents needed)
      �                  ?                           ?
      ?        execute_with_llm_orchestration() react_workflow()
 _chat_response()  run_skill_dag() [primary]    MASTER DAG plan
 (1 LLM call)      run_skill_react() [fallback]  then per-step dispatch
                   = 2 LLM calls/skill                �
                                          delegate_to_agent � N
                                                      �
                                     +----------------+----------------+
                                     ?                ?                ?
                                  Email            Drive          Files/WA/TG
                              run_skill_dag    run_skill_dag    run_skill_dag
                              2 calls each     2 calls each     2 calls each
                                     +----------------+----------------+
                                                      ?
                                           master: final_answer
```

**Worst-case LLM call count per flow (with sub-agent DAG):**

| Flow | Path | Typical calls | Max possible |
|------|------|:---:|:---:|
| Casual chat | chat_response | 2 | 2 |
| Single-skill command | skill DAG (2) | 3 | 4 |
| 2-agent command (e.g. zip + email) | master + 2 sub-agents DAG | 5 | 7 |
| 3-agent command | master + 3 sub-agents DAG | 7 | 10 |

*Master planner: 1 call. Each sub-agent DAG: 2 calls. Intent classify: 1 call. Fallback: ReAct (2–10 calls per agent).*

---

## Memory System

**Only Personal Assistants (PAs) have memory.** Skill agents (Email, Drive, WhatsApp, Telegram, Files) are stateless � they execute a single request with no context from past interactions.

Each PA has a dedicated memory folder at `memory/<pa_id>/`. The system uses 6 layers (7 for the PA hub with collective memory):

| File | Purpose | Sent to LLM |
|------|---------|------------|
| `working_memory.md` | Last 10 interactions | ? Always |
| `episodic_memory.md` | Timestamped events | On-demand recall only |
| `semantic_memory.md` | Learned facts about the user � preferences, recurring needs, background | ? Last 3000 chars |
| `personality.md` | Agent tone + identity. **PA hub: hard-coded protective persona, never overwritten by trait sliders** | ? Full file |
| `habits.md` | Confirmed user behavioural patterns � time-of-day, day-of-week, action type. Requires 3+ occurrences | ? Last 3000 chars |
| `consciousness.md` | Big-picture mental model of the user synthesised from ALL memory layers. Updated every 2�4 weeks | ? Full file |
| `collective_consciousness.md` | **PA hub only.** Synthesis of every skill agent�s `consciousness.md`. Cross-domain user model | ? Full file |

### Consolidation

A `ConsolidationRunner` daemon thread starts automatically when the dashboard boots. It:
1. Runs an immediate consolidation pass across all registered **Personal Assistants** on startup
2. Repeats every 24 hours � covers **all** PAs, including those not actively running

Consolidation cycle per agent:
1. Extract patterns from working memory ? update `semantic_memory.md`
2. Extract themes from episodic memory ? update `semantic_memory.md`
3. Detect habits (3+ occurrences, including day-of-week patterns) ? update `habits.md`
4. Apply 90-day decay (Low importance ? delete, Medium ? archive, High ? keep)
5. Update `consciousness.md` from all memory layers (if 2+ weeks since last update)
6. **PA hub only:** synthesise `collective_consciousness.md` from all skill `consciousness.md` files

### `_collective_memory_` Memory (Personal Assistant Hub)

The Personal Assistant hub�s memory files are created on first dashboard launch (not on first chat). Its `personality.md` is always restored to the hard-coded protective personal-assistant character on each init � it cannot be changed via the trait-slider UI.

---

## Process & Port Management

- **Dashboard:** always port `8501`
- **Agent sub-processes:** ports `8502�8599`, assigned dynamically
- **State file:** `running_agents.json` � tracks PID + port per agent, survives dashboard reruns
- **Watchdog:** each agent watches for browser disconnect and self-terminates + removes itself from state

---

## Log Files

Three categories of log files, **truncated on every `start.py` run**:

- `drive_agent.log`
- `email_agent.log`
- `whatsapp_agent.log`
- `telegram_agent.log`
- `files_agent.log`
- `personal_assistant.log`

## Files Agent — Search Strategy

The Files Agent uses two distinct search paths depending on what the user asks:

| Query type | Example | Tool called |
|---|---|---|
| Extension-based ("on my computer") | "Are there any image files on my computer?" | `search_file_all_drives("*", extensions=["jpg","jpeg","png",...], include_folders=False, limit=500)` |
| Single extension | "How many PDF files are on my computer?" | `search_file_all_drives("*", extensions=["pdf"], include_folders=False, limit=500)` |
| Keyword in filename | "How many payslips are on my computer?" | `search_file_all_drives("payslip", include_folders=False, limit=500)` |
| Multi-word keyword | "Are there any offer letters on my computer?" | `search_file_all_drives("offer letter", include_folders=False, limit=500)` |

**Key rules:**
- `search_file_all_drives` with `query="*"` matches every file on every drive; the `extensions` list does the filtering.
- Always set `limit=500` for counting/inventory queries (default `limit=20` is only for "find this one file" lookups).
- `search_by_extension` and `search_by_name` both default to `directory="~"` (home folder only) — **never** use them for "on my computer" queries that should scan all drives.
- Extension groups: **Image** → jpg/jpeg/png/gif/bmp/tiff/tif/webp/svg/ico · **Video** → mp4/avi/mov/mkv/wmv/flv/webm · **Document** → pdf/docx/doc/xlsx/xls/pptx/ppt/txt

---

## Memory Folder

PA memories are stored under `memory/<pa_id>/`. Only Personal Assistants have folders here � Skills are stateless and have no memory. Each PA folder holds 6 `.md` memory layers.

The `_collective_memory_` PA hub is the only agent that also maintains a `collective_consciousness.md` file, synthesising all skill consciousness files on each consolidation cycle.

---

## Skills.md — External Tool Metadata

Each skill agent maintains a `skills.md` file at `src/agent/ui/<agent>_agent/skills.md` that catalogues **every tool** the agent can call. This replaces the previous practice of hard-coding `_TOOL_DOCS` strings inside each orchestrator.

### Format

```markdown
## Category: Browse & Inspect

### list_directory
**signature**: list_directory(path, show_hidden=False, limit=200)
**description**: List files and sub-folders in a local directory.
**tags**: list, browse, folder, contents, directory
```

Each tool entry has:
| Field | Purpose |
|-------|---------|
| `### tool_name` | H3 header = tool identifier |
| `**signature**` | Function signature with parameters |
| `**description**` | One-line summary of what the tool does |
| `**tags**` | Comma-separated keywords for semantic matching |

Tools are grouped under `## Category:` headers (e.g., Browse & Inspect, Search, Archives & Compression).

### Current skills.md files

| Agent | File | Tools | Categories |
|-------|------|-------|------------|
| Files | `src/agent/ui/files_agent/skills.md` | 43 | 8 |
| Drive | `src/agent/ui/drive_agent/skills.md` | 30 | 8 |
| Email | `src/agent/ui/email_agent/skills.md` | 48 | 12 |

---

## Cosine-Similarity Tool Selection

Instead of sending **all** tool docs to the LLM on every request (wasting tokens and diluting focus), orchestrators now use cosine similarity to select only the most relevant tools for each user query.

### How it works

```
User query: "zip all the payslips and email them"
                    │
                    ▼
          skill_loader.py
          ┌─────────────────────────┐
          │ 1. Parse skills.md      │
          │ 2. Build search text    │
          │    per tool (name +     │
          │    description + tags)  │
          │ 3. Encode with          │
          │    SentenceTransformer  │
          │    (all-MiniLM-L6-v2)   │
          │ 4. FAISS IndexFlatIP    │
          │    cosine similarity    │
          │ 5. Return top-K tools   │
          └─────────────────────────┘
                    │
                    ▼
        Top 15 tool docs → ReAct prompt
        All tool docs    → DAG planner
```

### Key module: `src/agent/core/skill_loader.py`

| Function | Purpose |
|----------|---------|
| `load_tool_docs(agent, query, top_k, always_include, min_score)` | Filtered tool docs (ReAct) — top-K by similarity, then drops anything below `min_score` |
| `get_all_tool_docs(agent)` | Full tool list (DAG planner needs all tools to build a plan) |

### Why two strategies?

- **DAG planner** sees all tools because it plans upfront and must know the full inventory.
- **ReAct engine** sees only the top-K most relevant tools because it reasons step-by-step and benefits from a focused, less noisy tool list.

### Confidence threshold (anti-hallucination)

`load_tool_docs` applies a **minimum cosine-similarity score** (`min_score`, default **0.45**) after the top-K selection.  Tools scoring below this floor are logged with a `✗` marker and dropped:

```
│  #1  score=0.8714  ✓  tool=search_files
│  #2  score=0.6231  ✓  tool=zip_folder
│  #3  score=0.1102  ✗  tool=send_email      ← dropped (score < 0.45)
└─ [skill-loader] using 14/42 tools (min_score=0.45)
```

**Why this matters:**  Giving the LLM tools that have nothing to do with the query causes it to hallucinate calls to those tools, mix up argument names, or plan unnecessary extra steps.  A hard score floor keeps the prompt clean.

**Safety net:**  If the threshold filters out *everything*, the top-3 results are used unconditionally so the LLM always has at least one tool to work with.

### always_include (pinned tools)

Some tools must always be in the ReAct prompt regardless of query similarity:

| Agent | Pinned tools |
|-------|-------------|
| Files | `save_context`, `deliver_file`, `save_search_manifest` |
| Drive | `save_context` |
| Email | `save_context`, `deliver_file`, `write_pdf_report` |

### Hard-coded fallback removed

The original `_TOOL_DOCS` hard-coded string in each orchestrator was a copy-paste list that drifted out of sync with `skills.md` every time a new tool was added.  
`email_agent` and `files_agent` no longer fall back to it — if `skills.md` is missing, an `ERROR` log fires immediately and the call fails with a clear message instead of silently using an outdated tool list.  
(`whatsapp_agent` and `stock_agent` do not yet have `skills.md` files and still use their `_TOOL_DOCS`.)

---

## Log Analyser Dashboard

The Streamlit hub (`src/agent/ui/dashboard/`) now includes a built-in log viewer accessible via the **📊 Log Analyser** button in the sidebar.

### Module: `src/agent/ui/dashboard/log_viewer.py`

| Feature | Detail |
|---------|--------|
| File selector | All `logs/*.log` files, sorted by most-recently-modified first |
| Level filter | Multi-select: DEBUG / INFO / WARNING / ERROR / CRITICAL |
| Search | Full-text search with yellow match highlighting |
| View: Turns | Groups log lines by `corr=` correlation ID; shows per-turn user message, source, LLM-call count, and error indicators |
| View: Flat | Raw chronological stream, capped at 1,000 rendered rows |
| Stats bar | Total lines · Turns · LLM calls · Warnings · Errors · Error turns |
| LLM calls panel | Collapsible summary of every `llm.call` / `llm.response` line |
| Errors panel | Collapsible list of all ERROR/CRITICAL lines for quick triage |
| 🔄 Refresh | Manual one-click refresh |
| ⟳ Auto | Checkbox + interval select (3 / 5 / 10 / 30 s) for live tailing |
| 🏠 Home | Returns to the main Agent Hub without reloading |

### Log format parsed

```
[2026-03-07 15:39:41.123] INFO  | corr=ac699088 req=7f3a1b2c | skill_dag_engine       | │  ✔ [email] Plan contains 3 step(s)
```

Turn boundaries are detected via the `╔══…` / `║ TURN START` box-drawing lines emitted by `hub/processor.py`.

---

## Router — Keyword Stemming

The router's keyword pre-filter now applies minimal English stemming before matching.

**Problem:** User says "payslips" but keyword map has "payslip" → no match → skips LLM → fast-path to chat (wrong agent).

**Fix:** `_stem()` in `src/agent/workflows/router.py` strips common English suffixes:
- `-ies` → `-y` (e.g., "directories" → "directory")
- `-ves` → `-fe` (e.g., "archives" → "archive")
- `-ses`, `-xes`, `-zes` → trim 2 chars
- `-ing`, `-ed`, `-es`, `-s` → trim (with length guards)

Both the user's words **and** the keyword map words are expanded with their stemmed forms before intersection. This ensures plural/singular and verb-form variations match reliably.
