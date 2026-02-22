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

Each agent has a dedicated memory folder at `memory/<agent_id>/`. The system uses 6 layers:

| File | Purpose | Sent to LLM |
|------|---------|------------|
| `working_memory.md` | Last 10 interactions | ✅ Always |
| `episodic_memory.md` | Timestamped events | On-demand recall only |
| `semantic_memory.md` | Learned user facts | ✅ Last 3000 chars |
| `personality.md` | Agent's tone + identity | ✅ Full file |
| `habits.md` | Patterns after 3+ repetitions | ✅ Last 3000 chars |
| `consciousness.md` | Big-picture user model | ✅ Full file |

Consolidation runs automatically every 20 interactions or 24 hours (background thread). See [memory-system.md](../architecture/memory-system.md) for full details.

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
