# OctaMind — Architecture

Last updated: 2026-02-23

---

## System Overview

```
┌─────────────────────────────────────────────────────┐
│  Agent Hub Dashboard  (port 8501, always on)         │
│  Streamlit UI for creating / starting / stopping     │
│  agents. State persisted in running_agents.json.     │
└────────────────────┬────────────────────────────────┘
                     │  subprocess.Popen per agent
        ┌────────────┼────────────┬─────────────────┐
        ▼            ▼            ▼                 ▼
   Email Agent   Drive Agent  Multi-Agent     Generic Agent
   port: dynamic port: dynamic  Hub            port: dynamic
   (isolated Streamlit process with own st.session_state)
```

Each agent is a **completely isolated process** — separate port, separate Streamlit session, separate LLM context. They share no in-memory state.

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

When a command needs **both** Drive + Email the orchestrator plans in natural language, not tool signatures:

1. `router.py` → `detect_agents_needed()` classifies the command (LLM, `max_tokens=5`)
2. `master_orchestrator.py` → `plan_nl_workflow()` asks the LLM to produce a step plan using only compact capability summaries (~10 tokens/agent). **No tool signatures appear in the orchestrator context.**
3. Each step is executed by `nl_step_runner.py` → `run_nl_step()`, which looks up the target agent in `agent_registry.py` and calls its `execute_with_llm_orchestration()`. The sub-agent runs its own full ReAct loop with its own tool list and memory.
4. Artifact handoff (e.g. a downloaded file path) is carried via an `artifacts_out` dict and resolved as `{output_key.file_path}` tokens in subsequent step instructions.

**Context cost:** ~445 tokens for 2 agents (vs ~8,000 for the previous flat-tool-list design). Adding an agent = one entry in `agent_registry.py`; orchestrator context does not grow.

Single-agent commands routed through the Multi-Agent Hub bypass the planner and call the individual agent's ReAct orchestrator directly.

---

## Multi-Agent Routing

```
User command
      │
      ▼
detect_agents_needed()
      │
   ┌──┴──────────────┬────────────────┐
   ▼                  ▼                ▼
 NEITHER            EMAIL/DRIVE only   BOTH
(casual chat)       (single agent)    (NL workflow planner)
      │                  │                 │
      ▼                  ▼                 ▼
 _chat_response()   execute_with_         plan_nl_workflow()
                    llm_orchestration()   context: ~10 tokens/agent
                    (ReAct loop)                │
                                               ▼
                                         run_nl_step() × N
                                               │
                                     ┌────────┴────────┐
                                     ▼                ▼
                              drive_agent           email_agent
                              execute_with_         execute_with_
                              llm_orchestration()   llm_orchestration()
                              37 tools              47 tools
                              own ReAct loop        own ReAct loop
                              artifacts_out →→→→→ {file_path} resolved
                                                    in next instruction
```

---

## Memory System

Each agent has a dedicated memory folder at `memory/<agent_id>/`. The system uses 6 layers (7 for the multi-agent hub):

| File | Purpose | Sent to LLM |
|------|---------|------------|
| `working_memory.md` | Last 10 interactions | ✅ Always |
| `episodic_memory.md` | Timestamped events | On-demand recall only |
| `semantic_memory.md` | Learned facts about the user — preferences, recurring needs, background | ✅ Last 3000 chars |
| `personality.md` | Agent tone + identity. **Multi-agent: hard-coded protective persona, never overwritten by trait sliders** | ✅ Full file |
| `habits.md` | Confirmed user behavioural patterns — time-of-day, day-of-week, action type. Requires 3+ occurrences | ✅ Last 3000 chars |
| `consciousness.md` | Big-picture mental model of the user synthesised from ALL memory layers. Updated every 2–4 weeks | ✅ Full file |
| `collective_consciousness.md` | **Multi-agent only.** Synthesis of every sub-agent's `consciousness.md`. Cross-domain user model | ✅ Full file |

### Consolidation

A `ConsolidationRunner` daemon thread starts automatically when the dashboard boots. It:
1. Runs an immediate consolidation pass across all registered agents on startup
2. Repeats every 24 hours — covers **all** agents, including those not actively running

Consolidation cycle per agent:
1. Extract patterns from working memory → update `semantic_memory.md`
2. Extract themes from episodic memory → update `semantic_memory.md`
3. Detect habits (3+ occurrences, including day-of-week patterns) → update `habits.md`
4. Apply 90-day decay (Low importance → delete, Medium → archive, High → keep)
5. Update `consciousness.md` from all memory layers (if 2+ weeks since last update)
6. **Multi-agent only:** synthesise `collective_consciousness.md` from all agent `consciousness.md` files

### `__multi_agent__` Memory

The multi-agent hub's memory files are created on first dashboard launch (not on first chat). Its `personality.md` is always restored to the hard-coded protective personal-assistant character on each init — it cannot be changed via the trait-slider UI.

---

## Process & Port Management

- **Dashboard:** always port `8501`
- **Agent sub-processes:** ports `8502–8599`, assigned dynamically
- **State file:** `running_agents.json` — tracks PID + port per agent, survives dashboard reruns
- **Watchdog:** each agent watches for browser disconnect and self-terminates + removes itself from state

---

## Log Files

Three files written to the project root, **truncated on every `start.py` run**:

- `drive_agent.log`
- `email_agent.log`
- `multi_agent.log`
