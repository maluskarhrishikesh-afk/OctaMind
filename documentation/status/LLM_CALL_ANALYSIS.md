# LLM Call Analysis — Hybrid Planner + Deterministic Execution

> **Purpose:** This document explains how LLM calls happen in the new architecture that uses a single planning call, DAG-based execution, topological sort, and deterministic tool execution — with an optional fallback to ReAct only when required.

Last updated: 2026-03-15 (added sub-agent DAG planning — `skill_dag_engine.py`; email/files/drive now use 2 LLM calls per sub-agent instead of 4–10; updated all scenario counts and optimisation table)

---

## Executive Summary

| Request Type | Old (Pure ReAct) | New Hybrid | New + Sub-DAG |
|---|:---:|:---:|:---:|
| Casual chat | 2 calls | 1 call | 1 call |
| Single tool command | 3–7 calls | 1 call + sub-agent | **3 calls** |
| Two-agent task | 7–25 calls | 1 call + sub-agents | **5 calls** |
| Three-agent task | 9–31 calls | 1 call + sub-agents | **7 calls** |
| Complex / unknown task | 7–31 calls | 1–3 calls + sub-agents | **5–9 calls** |

> **Sub-agents** (drive, email, files) now use the **sub-agent DAG engine** (`skill_dag_engine.py`): exactly **2 LLM calls per sub-agent** (1 plan + 1 synthesis), regardless of how many tool steps the task requires.  The master orchestrator still sees a single task — the sub-agent internally expands it into a deterministic tool schedule.

> Fallback to `run_skill_react()` is automatic when DAG planning returns an invalid plan.

---

## New Architecture Overview

**Old (Pure ReAct):**

```
Master ReAct loop (1�12 LLM calls)
    ? detect agents needed (1 LLM call)
    ? delegate to sub-agent
        ? Sub ReAct loop (1�6 LLM calls)
            ? think ? tool ? think ? tool
    ? delegate to next sub-agent
        ? Sub ReAct loop (1�6 LLM calls)
    ? final_answer (1 LLM call)
```

**New (Hybrid Planner + Deterministic Execution):**

```
User Input
   ↓
Keyword Pre-Filter (0 LLM calls)
   ↓ [if agents clearly needed]
LLM Planner (1 call) → Structured DAG Plan (JSON with depends_on)
   ↓
Topological Sort (0 LLM calls — pure algorithm)
   ↓
Deterministic Execution Engine (0 orchestration LLM calls)
   +- Step 1: Sub-Agent A
   |      ↓ Plan step (1 call) → tools execute (0 calls) → Synthesize (1 call)
   +- Step 2: Sub-Agent B
   |      ↓ Plan step (1 call) → tools execute (0 calls) → Synthesize (1 call)
   +- Step 3: Sub-Agent C
          ↓ Plan step (1 call) → tools execute (0 calls) → Synthesize (1 call)
```

---

## Step 1 � Keyword Pre-Filter (0 LLM Calls)

Before any LLM call is made, a fast regex/keyword scan checks whether the command references no agents at all. This eliminates the old `detect_agents_needed()` LLM classification call for clear cases.

```
# router.py � keyword pre-filter runs before LLM routing
if keyword_pre_filter(command) == "no_agents":
    return None   # skip LLM entirely ? chat_response() handles it
```

- **Zero-keyword-match commands ? 0 LLM router calls** (then 1 call for the chat reply)
- Ambiguous commands ? LLM routing fires as before

---

## Step 2 � Planner Call (Single LLM Call)

The LLM receives the user command and returns a complete Directed Acyclic Graph (DAG) as structured JSON:

```json
[
  {
    "id": "download1",
    "agent": "drive",
    "instruction": "Download report.pdf from Google Drive",
    "depends_on": [],
    "description": "Download report.pdf"
  },
  {
    "id": "zip1",
    "agent": "files",
    "instruction": "Zip the file at {download1.file_path} into an archive",
    "depends_on": ["download1"],
    "description": "Zip downloaded file"
  },
  {
    "id": "email1",
    "agent": "email",
    "instruction": "Send the zip at {zip1.file_path} to {__user_email__} with subject ''Report''",
    "depends_on": ["zip1"],
    "description": "Email the zip"
  }
]
```

This is **one LLM call** that replaces the entire master orchestration loop.

---

## Step 3 � Topological Sort (0 LLM Calls)

The system resolves execution order algorithmically from the `depends_on` graph:

```
download1 ? zip1 ? email1
```

Steps with no shared dependencies are independent and can run concurrently. No LLM involvement.

---

## Step 4 � Deterministic Execution

Each step is dispatched to the registered agent executor. `{step_id.file_path}` tokens in instructions are resolved from the previous step''s output before the agent is called:

```python
# dag_planner.py � deterministic execution loop
for step in sorted_steps:
    resolved_instruction = resolve_tokens(step.instruction, context_results)
    executor = AGENT_REGISTRY[step.agent]
    result = executor(user_query=resolved_instruction, ...)
    context_results[step.id] = result
```

- **Zero orchestration LLM calls** during this phase
- Sub-agents (email, files, drive) now use their own **sub-agent DAG engine** — 2 LLM calls per sub-agent
- File paths and artifacts are wired between steps automatically

---

## LLM Calls Per Scenario (New System)

### 1. Casual Chat

```
Pre-filter: no agents detected ? 0 router calls
chat_response()               ? 1 call
-----------------------------------------
Total orchestration: 1 call
```

### 2. Single Tool Command
**Example:** "Send email to Alice"

```
Keyword pre-filter detects email → skip LLM router
DAG planner call               → 1 call
email sub-agent DAG            → 2 calls  (1 plan + 1 synthesize)
-----------------------------------------
Total: 3 calls  (was 3–8 with old system)
```

### 3. Two-Agent Command
**Example:** "Zip my Documents folder and email me the zip"

```
DAG planner call             → 1 call
Step: files sub-agent DAG    → 2 calls  (1 plan + 1 synthesize)
Step: email sub-agent DAG    → 2 calls  (1 plan + 1 synthesize)
-----------------------------------------
Total: 5 calls  (was 7–25 with old system)
```

### 4. Three-Agent Command
**Example:** "Download report.pdf from Drive, zip it, and email me"

```
DAG planner call             → 1 call
Step: drive sub-agent DAG    → 2 calls  (1 plan + 1 synthesize)
Step: files sub-agent DAG    → 2 calls  (1 plan + 1 synthesize)
Step: email sub-agent DAG    → 2 calls  (1 plan + 1 synthesize)
-----------------------------------------
Total: 7 calls  (was 9–31 with old system)
```

---

## When Do Additional Orchestration LLM Calls Happen?

Only these edge cases require extra calls at the orchestration level:

### Case A � Content Generation Required
**Example:** "Summarise report.pdf and send it to Alice"

The summarisation is handled inside the email agent''s sub-loop. No additional orchestration calls.

### Case B � Ambiguous User Input / Planning Failure

```
DAG planner call (failed or invalid) ? 1 call
Fallback: ReAct loop                 ? 1�12 calls
-----------------------------------------
Total: 2�13 calls  (worst-case same as old, but rare)
```

### Case C � Tool Failure Recovery

Handled by the sub-agent''s internal ReAct loop. The orchestration layer does not add extra LLM calls for retries.

---

## Comparison: Old vs New

### Old Pure ReAct Model � Worst Case (3-agent task)

```
detect_agents_needed()   =  1 call  (router)
react_workflow() loop    = 12 calls (master orchestrator)
drive sub-agent loop     =  6 calls
files sub-agent loop     =  6 calls
email sub-agent loop     =  6 calls
-----------------------------------------
Total worst case: 31 calls
```

**Problems with old model:**
- Master loop re-reasons about coordination at every turn
- Predictable workflows (zip ? email) still required multi-turn deliberation
- Delegation overhead: LLM call to decide what was already obvious from context
- Context window grows with every observation, increasing token cost

### New Hybrid Planner + DAG Model � Worst Case (3-agent task)

```
DAG planner call         =  1 call  (single orchestration call)
drive sub-agent loop     =  1�6 calls
files sub-agent loop     =  1�6 calls
email sub-agent loop     =  1�6 calls
-----------------------------------------
Total typical: 5�10 calls
Total worst case: 19 calls
```

**Fallback worst case (planning fails):**

```
DAG planner (failed)     =  1 call
ReAct fallback           = 12 + 6 + 6 + 6 = 30 calls
-----------------------------------------
Total: 31 calls  (same as before, but only when planning fails � rare)
```

---

## Why This Is Better

| Property | Old ReAct | New Hybrid |
|---|---|---|
| Orchestration calls | 1�12 per workflow | 1 (always) |
| Predictable flow | Re-reasoned every turn | Determined upfront |
| Execution order | Emergent from loop | Topological sort |
| Debuggability | Inspect LLM reasoning | Read structured DAG JSON |
| Parallelism | Sequential by design | Independent branches run concurrently |
| Cost (orchestration layer) | 12� master loop tokens | 1 plan call |
| Fallback safety | N/A | Full ReAct if DAG planning fails |

---

## Code Structure

| Layer | File | Function | LLM Calls |
|---|---|---|:---:|
| Intent pre-filter | `src/agent/workflows/router.py` | `keyword_pre_filter()` | 0 |
| Intent routing (if needed) | `src/agent/workflows/router.py` | `detect_agents_needed()` | 0–1 |
| DAG planning | `src/agent/workflows/dag_planner.py` | `plan_dag_workflow()` | 1 |
| Topological sort | `src/agent/workflows/dag_planner.py` | `topological_sort()` | 0 |
| Deterministic execution | `src/agent/workflows/dag_planner.py` | `execute_dag_workflow()` | 0 |
| **Sub-agent DAG planning** | **`src/agent/workflows/skill_dag_engine.py`** | **`run_skill_dag()`** | **2** |
| Sub-agent ReAct (fallback) | `src/agent/workflows/skill_react_engine.py` | `run_skill_react()` | 1–10 |
| ReAct fallback | `src/agent/workflows/master_orchestrator.py` | `react_workflow()` | 1–12 |
| Workflow entry point | `src/agent/workflows/master_orchestrator.py` | `run_workflow()` | � |

---

## Total LLM Call Counting (added 2026-03-01)

Every completed workflow now logs a total LLM call summary:

```
Total LLM calls: 4  (router=1  planner=1  sub_agents=2)
```

Counting breakdown:
- **`router=1`** � `detect_agents_needed()` always makes 1 call (unless keyword pre-filter exits early)
- **`planner=1`** � `plan_dag_workflow()` uses exactly 1 call
- **`sub_agents=N`** � sum of `llm_calls` returned by each `run_skill_react()` call
- **`planner=0`** when DAG planning fails and the ReAct fallback is used

This is visible in the logs next to the `Workflow complete:` line and makes optimization progress instantly measurable.

---

## Optimisation Summary

| Optimisation | Status | Saving |
|---|---|---|
| DAG planner replaces master ReAct loop | ✅ Implemented | Saves 1–11 orchestration calls per request |
| Keyword pre-filter before LLM router | ✅ Implemented | Saves 1 call for casual chat + obvious commands |
| Topological sort for dependency resolution | ✅ Implemented | 0 calls — purely algorithmic |
| Parallel execution of independent DAG branches | ✅ Architecture-ready | Speed improvement |
| ReAct fallback when DAG planning fails | ✅ Implemented | Graceful degradation |
| Total LLM call count logged per workflow | ✅ Implemented | Visibility into optimization progress |
| Python-bool JSON normalization in skill engine | ✅ Implemented | Prevents cascading unknown-action failures |
| Tilde path expansion in instruction resolver | ✅ Implemented | Prevents wrong path guesses by LLM |
| **Sub-agent DAG planning (email/files/drive)** | **✅ Implemented** | **Saves 2–8 calls per sub-agent vs ReAct loop** |
| Cached planning for repeated commands | ⏳ Future work | Would save 1 call on repeat queries |
| Sub-agent DAG for remaining skills (calendar, whatsapp, etc.) | ⏳ Future work | Same saving pattern for other agents |

---

## Final Architecture Decision

| Layer | Technology |
|---|---|
| Intent Pre-filter | Keyword regex (0 LLM calls) |
| Intent Routing (fallback only) | LLM (1 call) |
| Workflow Planning | LLM (1 call, JSON DAG output) |
| Dependency Resolution | Topological sort (algorithmic) |
| Orchestration Execution | Deterministic � no LLM |
| Sub-agent Tool Execution | Sub-agent DAG engine — 2 calls (email/files/drive); ReAct fallback for others |
| Error Handling | Retry + sub-agent loop recovery |
| Multi-agent coordination | DAG with depends_on, not nested master loops |
| Fallback | Full ReAct if DAG planning fails |

**Net effect:** The previous 1–12 master orchestration LLM calls collapse to exactly 1. Sub-agents (email, files, drive) now use the DAG engine — exactly 2 LLM calls each regardless of task complexity, saving 40–80% of sub-agent calls. Total system LLM calls reduce by **70–95%** for typical multi-agent workflows.
