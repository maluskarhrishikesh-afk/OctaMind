# Octa Bot — Architecture

Last updated: 2026-02-27

---

## System Overview

```
┌──────────────────────────────────────────────────────────┐
│  Agent Hub Dashboard  (port 8501, always on)              │
│  Streamlit UI for creating / starting / stopping agents.  │
│  State persisted in running_agents.json.                  │
└─────────────────────┬────────────────────────────────────┘
                      │  subprocess.Popen per agent
 ┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
 │          │          │          │          │          │          │          │          │          │          │          │          │
Email     Drive      Files   WhatsApp  Telegram  Calendar  Browser   Stock    LinkedIn  Habit    Scheduler  Personal
Agent     Agent      Agent    Agent     Agent     Agent     Agent    Agent     Agent     Agent     Agent     Assistant
(each is an isolated Streamlit process with its own st.session_state)
```

**Skills vs Personal Assistants:**
- **Skills** (Email, Drive, Files, WhatsApp, Telegram, Calendar, Browser, Stock, LinkedIn, Habit, Scheduler) are stateless executors — no memory, no personality. They execute a single task and return.
- **Personal Assistants** have full 6-layer memory (working, episodic, semantic, personality, habits, consciousness) and a cross-domain `collective_consciousness.md`.

---

## Message Pipeline (per agent)

```
User types a message
        │
        ▼
classify_intent()          LLM call: is this COMMAND or CHAT?
        │                  max_tokens=5, temperature=0
   CHAT │ COMMAND
        │       │
        ▼       ▼
  llm.chat()  reason_and_act()           ReAct loop (up to 6 iterations)
  (casual)    ┌──────────────────┐       Thought → Action (tool call)
              │ Tool executor    │  →    → Observation → Thought → ...
              │ (Gmail/Drive API)│       until final_answer
              └──────────────────┘
                      │
                      ▼
            _compose_*_response()        Raw JSON result → LLM → friendly markdown
                      │
                      ▼
               Streamlit chat UI
```

---

## Key Components

### `src/agent/llm/llm_parser.py` — `GitHubModelsLLM`

The single LLM client used by all agents.

| Method | Purpose | max_tokens | Notes |
|--------|---------|-----------|-------|
| `chat()` | Casual conversation | 300 | Uses full memory system prompt |
| `classify_intent()` | COMMAND vs CHAT | 5 | Deterministic, temp=0 |
| `reason_and_act()` | ReAct tool loop | 3000 per iter | Up to 6 iterations |
| `orchestrate_mcp_tool()` | Single tool dispatch | 300 | Used by legacy path |

### `src/agent/ui/*/orchestrator.py` — ReAct Orchestrators

Each agent has its own orchestrator that:
1. Builds memory context from the agent's memory files
2. Runs `reason_and_act()` with the agent's tool list
3. Returns `{"action": "react_response", "message": "<final_answer>"}` — a complete, LLM-formatted response

### `src/agent/ui/*/app.py` — Response Composition

After a tool result comes back, `_compose_*_response()` sends the raw JSON directly to the LLM with a formatting prompt. The LLM writes the final response (tables, bullets, emojis, bold). No hardcoded formatters.

### `src/agent/workflows/` — Multi-Agent Workflows

Multi-agent commands use a **two-level ReAct architecture**:

1. `router.py` → `detect_agents_needed()` classifies the command (LLM, `max_tokens=5`)
2. `master_orchestrator.py` → `react_workflow()` runs a **master ReAct loop** (up to 12 iterations). The orchestrator LLM sees only compact capability summaries (~10 tokens/agent) and uses `delegate_to_agent` or `final_answer` each turn.
3. Each `delegate_to_agent` call looks up the target in `agent_registry.py` and calls its `execute_with_llm_orchestration()`. This runs a **per-skill ReAct loop** via the shared `skill_react_engine.py` → `run_skill_react()` (up to 6 iterations per skill).
4. Artifact handoff (e.g. a downloaded file path) is passed via an `artifacts_out` dict and reported back to the master loop as an observation. The master loop copies the path literally into the next delegation instruction.
5. The authenticated user's email address is injected into the master system prompt at runtime so `email me` instructions always resolve to the correct address.

**Context cost:** ~445 tokens for 2 agents (vs ~8,000 for a flat tool-list design). Adding an agent = one entry in `agent_registry.py`; orchestrator context does not grow.

**Shared skill engine:** `src/agent/workflows/skill_react_engine.py` — `run_skill_react()` is the single ReAct loop implementation used by every skill orchestrator. Each skill passes its own `tool_map` and `skill_context`. This removes code duplication across agents.

Single-agent commands routed through the Personal Assistant bypass the multi-agent planner and call the individual skill's ReAct orchestrator directly.

---

## Multi-Agent Routing

```
User command
      │
      ▼
detect_agents_needed()          (1 LLM call, max_tokens=5)
      │
   ┌──┴──────────────────┬──────────────────────────┐
   ▼                     ▼                           ▼
 NEITHER             SINGLE AGENT               MULTI-AGENT
(casual chat)      (any single skill)           (2+ agents needed)
      │                  ▼                           ▼
      ▼        execute_with_llm_orchestration() react_workflow()
 _chat_response()  run_skill_react()            MASTER ReAct loop
 (1 LLM call)      up to 6 LLM calls/skill      up to 12 iterations
                                                      │
                                          delegate_to_agent × N
                                                      │
                                     ┌────────────────┼────────────────┐
                                     ▼                ▼                ▼
                                  Email            Drive          Files/WA/TG
                              run_skill_react  run_skill_react  run_skill_react
                              up to 6 calls    up to 6 calls    up to 6 calls
                                     └────────────────┼────────────────┘
                                                      ▼
                                           master: final_answer
                                           (LLM composes summary)
```

**Worst-case LLM call count per flow:**

| Flow | Path | Typical calls | Max possible |
|------|------|:---:|:---:|
| Casual chat | chat_response | 2 | 2 |
| Single-skill command | skill ReAct only | 2–4 | 7 |
| 2-agent command (e.g. zip + email) | master + 2 sub-agents | 5–8 | 25 |
| 3-agent command | master + 3 sub-agents | 7–12 | 31 |

*Master loop: up to 12 calls. Each sub-agent: up to 6 calls. Intent classify: 1 call.*

---

## Memory System

**Only Personal Assistants (PAs) have memory.** Skill agents (Email, Drive, WhatsApp, Telegram, Files) are stateless — they execute a single request with no context from past interactions.

Each PA has a dedicated memory folder at `memory/<pa_id>/`. The system uses 6 layers (7 for the PA hub with collective memory):

| File | Purpose | Sent to LLM |
|------|---------|------------|
| `working_memory.md` | Last 10 interactions | ✅ Always |
| `episodic_memory.md` | Timestamped events | On-demand recall only |
| `semantic_memory.md` | Learned facts about the user — preferences, recurring needs, background | ✅ Last 3000 chars |
| `personality.md` | Agent tone + identity. **PA hub: hard-coded protective persona, never overwritten by trait sliders** | ✅ Full file |
| `habits.md` | Confirmed user behavioural patterns — time-of-day, day-of-week, action type. Requires 3+ occurrences | ✅ Last 3000 chars |
| `consciousness.md` | Big-picture mental model of the user synthesised from ALL memory layers. Updated every 2–4 weeks | ✅ Full file |
| `collective_consciousness.md` | **PA hub only.** Synthesis of every skill agent’s `consciousness.md`. Cross-domain user model | ✅ Full file |

### Consolidation

A `ConsolidationRunner` daemon thread starts automatically when the dashboard boots. It:
1. Runs an immediate consolidation pass across all registered **Personal Assistants** on startup
2. Repeats every 24 hours — covers **all** PAs, including those not actively running

Consolidation cycle per agent:
1. Extract patterns from working memory → update `semantic_memory.md`
2. Extract themes from episodic memory → update `semantic_memory.md`
3. Detect habits (3+ occurrences, including day-of-week patterns) → update `habits.md`
4. Apply 90-day decay (Low importance → delete, Medium → archive, High → keep)
5. Update `consciousness.md` from all memory layers (if 2+ weeks since last update)
6. **PA hub only:** synthesise `collective_consciousness.md` from all skill `consciousness.md` files

### `__multi_agent__` Memory (Personal Assistant Hub)

The Personal Assistant hub’s memory files are created on first dashboard launch (not on first chat). Its `personality.md` is always restored to the hard-coded protective personal-assistant character on each init — it cannot be changed via the trait-slider UI.

---

## Process & Port Management

- **Dashboard:** always port `8501`
- **Agent sub-processes:** ports `8502–8599`, assigned dynamically
- **State file:** `running_agents.json` — tracks PID + port per agent, survives dashboard reruns
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

## Memory Folder

PA memories are stored under `memory/<pa_id>/`. Only Personal Assistants have folders here — Skills are stateless and have no memory. Each PA folder holds 6 `.md` memory layers.

The `__multi_agent__` PA hub is the only agent that also maintains a `collective_consciousness.md` file, synthesising all skill consciousness files on each consolidation cycle.
