# OctaMind DAG Algorithm — Step-by-Step Walkthrough

This document traces exactly what happens, decision by decision, for two complete requests — one simple (single skill), one complex (multi-agent). Every LLM call, every JSON payload, every function call is shown.

---

## Architecture Overview

```
User message
    │
    ▼
┌──────────────────────────────────────────────────┐
│  HubProcessor._dispatch()                        │
│                                                  │
│  1. _enrich_scheduling_followup()  (0 LLM)      │
│  2. detect_agents_needed()         (1 LLM)      │
│                                                  │
│  ┌────────────┬─────────────┬──────────────────┐│
│  │  No agents │ 1 agent     │ 2+ agents         ││
│  │  (chat)    │ (Skill DAG) │ (Workflow DAG)    ││
│  └────────────┴─────────────┴──────────────────┘│
└──────────────────────────────────────────────────┘
        │               │               │
        ▼               ▼               ▼
  _chat_response   _run_single_agent  run_workflow
  (1 LLM call)     │               (dag_planner.py)
                   ▼                    │
             run_skill_dag          1. plan_dag_workflow (1 LLM)
             (skill_dag_engine.py)  2. topological_sort (0 LLM)
             │                     3. execute_dag_workflow (0 LLM)
             1. _plan_steps (1 LLM)    ├─ sub-agent A → run_skill_dag
             2. tool execution (0 LLM) └─ sub-agent B → run_skill_dag
             3. _synthesize (1 LLM)
```

---

## Example 1 — Simple (Single Skill)

### User command
> "List my last 3 emails"

This touches only the Email agent, so it travels the single-skill path.

---

### Step 1 — Scheduling Enrichment (0 LLM calls)

**File:** `src/agent/hub/processor.py` — `_enrich_scheduling_followup()`

The command is tested against `_BARE_TIME_PATTERN`. "List my last 3 emails" is not a bare time string like "2 PM to 3 PM", so it is returned unchanged.

```
routing_message = "List my last 3 emails"   (unchanged)
```

---

### Step 2 — Router (1 LLM call)

**File:** `src/agent/workflows/router.py` — `detect_agents_needed()`

**Sub-step 2a — Keyword pre-filter (0 LLM calls)**

The command is tokenised. Word "emails" → matches the `email` agent's keyword set. Pre-filter passes; LLM call proceeds.

**Sub-step 2b — LLM routing call (LLM call #1)**

Prompt sent to the LLM:
```
You are a command router for a multi-agent AI system.

Available agents:
  "email": Reads, sends, and manages Gmail ...
  "files": Manages local files and folders ...
  "calendar": Creates and reads Google Calendar events ...
  ...

Your job: read the user command and return a JSON array of agent names
that are needed to fully complete it.
...

Command: List my last 3 emails
Answer:
```

LLM response:
```json
["email"]
```

**Result:** `agents_needed = ["email"]`  
Since `len(agents_needed) == 1`, the single-agent shortcut is taken.

---

### Step 3 — Single-Agent Dispatch (0 LLM calls)

**File:** `src/agent/hub/processor.py` — `_run_single_agent("email", req)`

The function looks up `"email"` in `AGENT_REGISTRY`, retrieves its executor callable, and calls:
```python
result = executor(
    user_query="List my last 3 emails",
    agent_id=None,
    artifacts_out={},
)
```

The email executor delegates to `run_skill_dag`.

---

### Step 3.5 — Orchestrator: Tool Set Preparation (0 LLM calls)

**File:** `src/agent/ui/email_agent/orchestrator.py` — `execute_with_llm_orchestration()`

Before calling `run_skill_dag`, the email orchestrator prepares **two separate tool sets** for the two possible execution paths:

```python
# Path A — DAG planning: ALL 53 tools (compact first-sentence format)
dag_tool_docs = get_all_tool_docs("email")
# e.g. each line: "get_todays_emails(n_emails=5) – Fetch the most recent inbound emails received today."

# Path B — ReAct fallback: FAISS top-15 filtered to this query
react_tool_docs = load_tool_docs("email", user_query,
                                 always_include=["save_context", "deliver_file"])
# e.g. 8 tools selected with scores ≥ 0.45
```

**Session State injection** also happens here. The query passed to the skill is actually:
```
List my last 3 emails

## Session State (structured — prefer these resolved values over raw text)
{
  "current_date": "2026-03-08",
  "current_time": "13:47",
  "timezone": "India Standard Time (UTC+05:30)",
  "active_date": "2026-03-08"
}
```

The `## Session State` block gives the planner access to today's date without the LLM having to infer or guess it. The `{__session__.current_date}` token can be used in DAG step kwargs.

**FAISS query stripping:** Before FAISS similarity search, `_strip_context_blocks()` removes the `## Session State` block so only the clean query `"List my last 3 emails"` is embedded — preventing the session JSON from diluting cosine scores.

---

### Step 4 — Skill DAG: Planning (1 LLM call)

**File:** `src/agent/workflows/skill_dag_engine.py` — `_plan_steps()`

The planner receives ALL email tools in **compact first-sentence-only format** (not the full rich FAISS descriptions). `_compact_tool_docs_for_planning()` trims each tool's description to its first sentence (≤ 90 chars), enabling all 53 tools to fit in a single prompt well under the 8,000 token limit.

**Prompt (simplified):**
```
You are a planning engine for the Email skill.

Available tools:
  get_todays_emails(n_emails=5) – Fetch the most recent inbound emails received today.
  list_emails(query, max_results) – List email summaries matching a search query.
  send_email(to, subject, body) – Compose and send an email.
  schedule_email(to, subject, body, send_at) – Schedule an email to be sent later.
  ... (all 53 tools, first sentence only)

Output ONLY the JSON array — no markdown fences, no extra text.

Request: List my last 3 emails
```

**Token budget:**
- 53 tools × ~40 chars compact = ~350 tokens (vs ~1,400 tokens with full descriptions)
- Skill context (first 2,000 chars only) = ~500 tokens
- Planning rules + prompt scaffolding = ~400 tokens
- `max_tokens=800` for the plan response
- **Total: ~2,050 tokens** — comfortably under the 8,000 token limit for gpt-4o-mini

**LLM response (LLM call #2):**
```json
[
  {
    "id": "s1",
    "tool": "list_emails",
    "kwargs": { "query": "", "max_results": 3 },
    "depends_on": [],
    "description": "List the 3 most recent emails"
  }
]
```

`_strip_fences()` removes any accidental code fences from the raw output. `_parse_plan()` validates the JSON and confirms every `"tool"` name exists in `tool_map`.

**Result:** `plan = [{"id": "s1", "tool": "list_emails", "kwargs": {"query": "", "max_results": 3}, ...}]`

---

### Step 5 — Skill DAG: Tool Execution (0 LLM calls)

**File:** `src/agent/workflows/skill_dag_engine.py` — deterministic loop

For each step in `plan`:

1. Resolve `{token}` references in kwargs (none here — first step has no dependencies).
2. Call the tool function directly:
   ```python
   result_s1 = list_emails(query="", max_results=3)
   ```
3. Store result in `step_results["s1"]`.
4. Propagate any `file_path` to `artifacts_out`.

**`result_s1` value (example):**
```json
[
  {
    "id": "18f4a9b2e1c0d5f3",
    "subject": "Project Alpha Update",
    "from": "alice@company.com",
    "snippet": "Hi, just wanted to update you on the latest sprint...",
    "date": "2026-03-01"
  },
  {
    "id": "18f4a7c3d2e1f092",
    "subject": "Invoice #2234",
    "from": "billing@vendor.com",
    "snippet": "Please find your invoice attached...",
    "date": "2026-03-01"
  },
  {
    "id": "18f4a5d4c3b2a1e0",
    "subject": "Weekend plans?",
    "from": "bob@personal.com",
    "snippet": "Hey, are you free Saturday?",
    "date": "2026-02-28"
  }
]
```

**Zero LLM calls** at this stage — pure Python function calls.

---

### Step 6 — Skill DAG: Synthesis (1 LLM call)

**File:** `src/agent/workflows/skill_dag_engine.py` — `_synthesize()`

The synthesizer receives:
- The original user query
- The plan (step descriptions)
- All accumulated `step_results`

It calls the LLM to turn the raw tool output into a friendly natural-language response.

**Prompt (simplified):**
```
The user asked: "List my last 3 emails"

Tool results:
Step s1 (list_emails): [{ "id": "18f4a9b2...", "subject": "Project Alpha Update", ...}, ...]

Write a helpful, friendly reply summarising what was found.
Do not expose raw IDs or JSON keys.
```

**LLM response (LLM call #3):**
```
Here are your 3 most recent emails:

1. **Project Alpha Update** — from alice@company.com (Mar 01)
   > Hi, just wanted to update you on the latest sprint...

2. **Invoice #2234** — from billing@vendor.com (Mar 01)
   > Please find your invoice attached...

3. **Weekend plans?** — from bob@personal.com (Feb 28)
   > Hey, are you free Saturday?
```

---

### Step 7 — Summary Log

**File:** `src/agent/hub/processor.py` — `_log_workflow_summary()`  
Called from `_dispatch()` before returning to the caller.

```
╔════════════════════════════════════════════╗
║  🤖  WORKFLOW COMPLETE                     ║
╠════════════════════════════════════════════╣
║  Status: ✅ success   Time: 1.83 s         ║
║  Mode:   ⚙️ Skill DAG                     ║
╠════════════════════════════════════════════╣
║  Agents: ✉️ email                         ║
╠════════════════════════════════════════════╣
║  LLM Calls: 2 total                        ║
╚════════════════════════════════════════════╝
```

> **Note:** The summary shows 2 LLM calls (skill planner + synthesizer). The router call (#1) is counted separately by `run_workflow` when a multi-agent path is used, but for single-agent paths the `_run_single_agent()` result dict reports only the skill-internal calls.

---

### Example 1 — LLM Call Budget

| # | Where | Purpose |
|---|---|---|
| 1 | `router.py` | Identify that "email" agent is needed |
| 2 | `skill_dag_engine.py` | Plan the sequence of email tools |
| 3 | `skill_dag_engine.py` | Synthesise tool results into friendly text |

**Total: 3 LLM calls** regardless of how many emails exist in the inbox.

---

---

## Example 2 — Complex (Multi-Agent)

### User command
> "Find all Python files in my Documents folder and email me the full list"

This spans two agents (files + email) and requires passing a file artifact between them.

---

### Step 1 — Scheduling Enrichment (0 LLM calls)

Not a bare time string → command passes through unchanged.

---

### Step 2 — Router (1 LLM call)

**File:** `src/agent/workflows/router.py` — `detect_agents_needed()`

**Keyword pre-filter:** "files" (from "Find files"), "email" (from "email me") → both match → LLM call proceeds.

**LLM routing call (LLM call #1):**

Prompt:
```
Command: Find all Python files in my Documents folder and email me the full list
Answer:
```

LLM response:
```json
["files", "email"]
```

**Result:** `agents_needed = ["files", "email"]`  
Since `len(agents_needed) > 1`, the multi-agent workflow path is taken.

---

### Step 3 — Master Workflow: User Email Resolution (0 LLM calls)

**File:** `src/agent/workflows/master_orchestrator.py` — `_get_user_email()`

A `users.getProfile` call to the Gmail API retrieves the user's own email address. This is stored in the workflow context as `__user_email__` and can be referenced with the token `{__user_email__}` in any agent instruction.

```python
user_email = "hrishikesh@example.com"
ctx.set("__user_email__", user_email)
```

No LLM needed — ordinary REST API call.

---

### Step 4 — Master Workflow: DAG Planning (1 LLM call)

**File:** `src/agent/workflows/dag_planner.py` — `plan_dag_workflow()`

The planner sends the command to the LLM together with every registered agent's capabilities and a description of the `{step_id.field}` token system for passing artifacts between steps.

**Prompt (key excerpt):**
```
Available agents:
  "files": Manages local files and folders — list, read, write, search, zip, unzip ...
  "email":  Reads, sends, manages Gmail ...

SYSTEM PATHS:
  Documents: C:\Users\hrishikesh\Documents

SPECIAL CONTEXT TOKENS:
  {__user_email__} — the authenticated user's own email address
  {<step_id>.file_path} — local file produced by a previous step

Command: Find all Python files in my Documents folder and email me the full list
```

**LLM response (LLM call #2):**
```json
[
  {
    "id": "find_py",
    "agent": "files",
    "instruction": "Search recursively in C:\\Users\\hrishikesh\\Documents for all files with the .py extension. Write their full paths, one per line, to a text file called python_files_list.txt in the same folder. Report the path to that file.",
    "depends_on": [],
    "description": "Find all .py files in Documents"
  },
  {
    "id": "send_list",
    "agent": "email",
    "instruction": "Send the text file at {find_py.file_path} as an attachment to {__user_email__} with subject 'Your Python Files List' and a brief friendly body.",
    "depends_on": ["find_py"],
    "description": "Email the .py file list"
  }
]
```

---

### Step 5 — Topological Sort (0 LLM calls)

**File:** `src/agent/workflows/dag_planner.py` — `topological_sort()`

Uses **Kahn's algorithm**. The dependency graph:

```
find_py  ──→  send_list
```

- `find_py` has no dependencies (in-degree = 0) → queued first
- `send_list` depends on `find_py` (in-degree = 1) → queued after `find_py` completes

**Sorted execution order:** `[find_py, send_list]`

If there were independent steps (no `depends_on`), they would also be sorted but could logically run in any order (sequential in current implementation).

---

### Step 6 — Execute Step "find_py" (files agent, 2 LLM calls internally)

**File:** `src/agent/workflows/dag_planner.py` — `execute_dag_workflow()`

The executor for the `files` agent is retrieved from `AGENT_REGISTRY` and called:

```python
raw_result = files_executor(
    user_query="Search recursively in C:\\Users\\hrishikesh\\Documents for all "
               "files with the .py extension. Write their full paths, one per "
               "line, to python_files_list.txt. Report the path to that file.",
    agent_id=None,
    artifacts_out=artifacts_out,   # mutable dict for file handoff
)
```

Internally this calls `run_skill_dag(skill_name="files", ...)`:

#### 6a — Files Skill Planner (LLM call #3)

The LLM receives the full list of files tools (find_files, list_folder, write_text_file, read_text_file, …) and the instruction above.

**LLM response:**
```json
[
  {
    "id": "f1",
    "tool": "find_files",
    "kwargs": {
      "root_path": "C:\\Users\\hrishikesh\\Documents",
      "pattern": "*.py",
      "recursive": true
    },
    "depends_on": [],
    "description": "Find .py files recursively"
  },
  {
    "id": "f2",
    "tool": "write_text_file",
    "kwargs": {
      "content": "{f1}",
      "filepath": "C:\\Users\\hrishikesh\\Documents\\python_files_list.txt"
    },
    "depends_on": ["f1"],
    "description": "Write paths to .txt file"
  }
]
```

#### 6b — Files Tool Execution (0 LLM calls)

**Step f1 — `find_files()`:**
```python
result_f1 = find_files(
    root_path="C:\\Users\\hrishikesh\\Documents",
    pattern="*.py",
    recursive=True,
)
```
Returns:
```json
{
  "status": "success",
  "results": [
    {"path": "C:\\Users\\hrishikesh\\Documents\\project\\main.py"},
    {"path": "C:\\Users\\hrishikesh\\Documents\\project\\utils\\helpers.py"},
    {"path": "C:\\Users\\hrishikesh\\Documents\\scripts\\backup.py"}
  ],
  "count": 3
}
```

**Step f2 — `write_text_file()`:**  
`{f1}` token is resolved to the JSON string of `result_f1` by `_resolve_kwargs()`.
```python
result_f2 = write_text_file(
    content="C:\\Users\\...\\main.py\nC:\\Users\\...\\helpers.py\nC:\\Users\\...\\backup.py",
    filepath="C:\\Users\\hrishikesh\\Documents\\python_files_list.txt",
)
```
Returns:
```json
{
  "status": "success",
  "file_path": "C:\\Users\\hrishikesh\\Documents\\python_files_list.txt",
  "message": "File written successfully."
}
```

The skill DAG engine detects `"file_path"` in `result_f2` and stores it in `artifacts_out`:
```python
artifacts_out["file_path"] = "C:\\Users\\hrishikesh\\Documents\\python_files_list.txt"
```

#### 6c — Files Skill Synthesize (LLM call #4)

The LLM receives all step results and produces:

```
I found **3 Python files** in your Documents folder and saved them to:
`C:\Users\hrishikesh\Documents\python_files_list.txt`

Files found:
- `C:\Users\hrishikesh\Documents\project\main.py`
- `C:\Users\hrishikesh\Documents\project\utils\helpers.py`
- `C:\Users\hrishikesh\Documents\scripts\backup.py`
```

`run_skill_dag` returns:
```python
{
    "status": "success",
    "message": "I found 3 Python files ...",
    "action": "react_response",
    "llm_calls": 2,
    "_dag_used": True,
}
```

`artifacts_out["file_path"]` now holds the .txt path.

---

### Step 7 — Token Resolution for Step "send_list"

**File:** `src/agent/workflows/dag_planner.py` — `_resolve_instruction_tokens()`

Before dispatching the email agent, the master executor resolves tokens in the instruction:

```
"Send the text file at {find_py.file_path} to {__user_email__} ..."
```

Lookups:
- `{find_py.file_path}` → reads `ctx_results["find_py"]["artifacts"]["file_path"]`  
  → `"C:\\Users\\hrishikesh\\Documents\\python_files_list.txt"`
- `{__user_email__}` → reads `ctx["__user_email__"]` → `"hrishikesh@example.com"`

**Resolved instruction:**
```
"Send the text file at C:\Users\hrishikesh\Documents\python_files_list.txt
as an attachment to hrishikesh@example.com with subject 'Your Python Files List'
and a brief friendly body."
```

---

### Step 8 — Execute Step "send_list" (email agent, 2 LLM calls internally)

The email executor receives the resolved instruction and calls `run_skill_dag(skill_name="email", ...)`:

#### 8a — Email Skill Planner (LLM call #5)

```json
[
  {
    "id": "e1",
    "tool": "send_email",
    "kwargs": {
      "to": "hrishikesh@example.com",
      "subject": "Your Python Files List",
      "body": "Hi! Here is the list of Python files I found in your Documents folder.",
      "attachment_path": "C:\\Users\\hrishikesh\\Documents\\python_files_list.txt"
    },
    "depends_on": [],
    "description": "Send email with .txt attachment"
  }
]
```

#### 8b — Email Tool Execution (0 LLM calls)

```python
result_e1 = send_email(
    to="hrishikesh@example.com",
    subject="Your Python Files List",
    body="Hi! Here is the list of Python files ...",
    attachment_path="C:\\Users\\hrishikesh\\Documents\\python_files_list.txt",
)
```
Returns:
```json
{
  "status": "success",
  "message": "Email sent successfully (message ID: 18f5b3c2d1e0a9f4)."
}
```

#### 8c — Email Skill Synthesize (LLM call #6)

LLM produces:
```
✅ Done! I've sent an email to **hrishikesh@example.com** with the subject
**"Your Python Files List"**, including the .txt file as an attachment.
```

`run_skill_dag` returns:
```python
{
    "status": "success",
    "message": "✅ Done! I've sent an email ...",
    "action": "react_response",
    "llm_calls": 2,
    "_dag_used": True,
}
```

---

### Step 9 — Final Answer Assembly (0 LLM calls)

**File:** `src/agent/workflows/master_orchestrator.py` — `_dag_final_answer()`

Both steps succeeded. For a two-step workflow, a structured markdown summary is assembled algorithmically from step messages:

```
**All steps completed successfully:**
✅ [files] Find all .py files in Documents — I found 3 Python files ...
✅ [email] Email the .py file list — ✅ Done! I've sent an email ...
```

Then `_render_workflow_output()` in `processor.py` sees `final_answer` is non-empty and returns it directly — **no extra LLM call**.

---

### Step 10 — Summary Log

```
╔════════════════════════════════════════════╗
║  🤖  WORKFLOW COMPLETE                     ║
╠════════════════════════════════════════════╣
║  Status: ✅ success   Time: 8.72 s         ║
║  Mode:   📋 Multi-Agent DAG               ║
╠════════════════════════════════════════════╣
║  Agents: 📁 files  ✉️ email               ║
╠════════════════════════════════════════════╣
║  LLM Calls: 4 total                        ║
╚════════════════════════════════════════════╝
```

> **Note:** The summary shows 4 sub-agent LLM calls (2 per skill). The router call (#1) and master planner call (#2) are tracked separately in `master_orchestrator.run_workflow()` and shown in the INFO log line: `Total LLM calls: 6 (router=1 planner=1 sub_agents=4)`.

---

### Example 2 — LLM Call Budget

| # | Where | Purpose |
|---|---|---|
| 1 | `router.py` | Identify agents needed: `["files", "email"]` |
| 2 | `dag_planner.py` | Produce the multi-agent DAG with `depends_on` |
| 3 | `skill_dag_engine.py` (files) | Plan files tool sequence |
| 4 | `skill_dag_engine.py` (files) | Synthesise files results into text |
| 5 | `skill_dag_engine.py` (email) | Plan email tool sequence |
| 6 | `skill_dag_engine.py` (email) | Synthesise email results into text |

**Total: 6 LLM calls** regardless of how many Python files are found.

Old multi-turn master ReAct loop for the same request: **8–12 LLM calls**.  
DAG planner savings: ~50 % reduction.

---

## Comparison Table

| Property | Example 1 (Simple) | Example 2 (Complex) |
|---|---|---|
| Agents involved | 1 (email) | 2 (files + email) |
| Path taken | Single-agent shortcut | Multi-agent DAG |
| Master planner call | No | Yes (1 call) |
| Skill planner calls | 1 | 2 (1 per agent) |
| Tool execution | 1 tool | 4 tools (2+2) |
| Skill synthesize calls | 1 | 2 (1 per agent) |
| Final synthesis call | No | No (algorithmic) |
| **Total LLM calls** | **3** | **6** |
| Artifact handoff | Not applicable | `{find_py.file_path}` token |
| Fallback triggered | No | No |

---

## How Token Resolution Works

When step B's instruction contains `{find_py.file_path}`, the master executor resolves it just before calling step B:

```python
# Simplified from dag_planner.py _resolve_instruction_tokens()
token = "find_py.file_path"
parts = token.split(".")         # ["find_py", "file_path"]
value = ctx_results["find_py"]   # the full step result dict
value = value["artifacts"]       # → {"file_path": "C:\\...\\python_files_list.txt"}
value = value["file_path"]       # → "C:\\...\\python_files_list.txt"
```

The resolved string is substituted literally into the instruction before it is sent to the sub-agent. No LLM call is needed for the substitution.

---

## Fallback: When DAG Planning Fails

If the master planner LLM call fails, or if `_parse_plan()` cannot produce a valid plan (empty list, unknown tool names, etc.), the system falls back gracefully:

**Single-skill fallback:**  
`run_skill_dag()` → DAG plan fails → calls `run_skill_react()` instead.  
`run_skill_react()` uses a classic up-to-6-iteration ReAct loop within the skill.  
LLM call count becomes 1 (router) + 1 (failed planner) + up to 6 (ReAct) = up to 8 calls.

**Multi-agent fallback:**  
`plan_dag_workflow()` → DAG plan fails → `react_workflow()` is called.  
The master ReAct loop runs with up to 12 iterations, delegating to sub-agents as needed.  
LLM call count becomes 1 (router) + up to 12 (master ReAct) + up to 6/agent (skill ReAct each) = significantly more.

The fallback is logged at WARNING level and the execution_mode in the result dict is set to `"react_fallback"` so you can see it in logs.

---

## Why DAG Uses All Tools, Not FAISS

A common question: *"The ReAct engine uses FAISS to filter to 15 tools — why doesn't DAG planning do the same?"*

**The core reason: multi-step dependency visibility.**

Consider: *"Find all PDF files from last week and email me the list."*

- FAISS embedding of this query strongly matches file-search tools (`search_by_date`, `search_by_extension`)
- It might score `schedule_email` or `generate_pdf_report` below threshold and drop them
- The DAG planner would then be unable to plan the `search → email` chain, since `schedule_email` is missing from its tool list

With ALL tools visible, the planner correctly produces:
```json
[{"id": "s1", "tool": "search_by_date", ...}, {"id": "s2", "tool": "schedule_email", ...}]
```

**Why FAISS is valuable for ReAct (but not DAG):**

ReAct iterates: each iteration is one LLM call that sees the tool list. Reducing from 50 tools to 15 saves ~500 tokens multiplied by up to 6 iterations = ~3,000 tokens total. That matters.

DAG planning is a **single LLM call**. The compact format (`_compact_tool_docs_for_planning()`) already reduces 50 tools to ~350 tokens — small enough that applying FAISS saves only ~100 more tokens while risking broken multi-step plans.

**Summary:**

| Property | DAG Planning | ReAct Engine |
|---|---|---|
| Tool selection | ALL tools (compact first-sentence) | FAISS top-15 (full rich descriptions) |
| LLM calls that see the tool list | 1 | Up to 6 |
| Risk of missing tools | None | Acceptable (single-step oriented) |
| Token cost per call | ~350 tokens | ~3,500 tokens (15 detailed tools) |
| Fallback if wrong tool chosen | DAG → ReAct fallback | Next iteration can correct |

---

## Session State vs Manifests: Complementary Roles

Every skill query is annotated with a `## Session State` JSON block. This works alongside (not instead of) the manifest system:

```
Session State = per-turn entity extraction from conversation history
Manifests     = persistent disk state written by previous tool calls
```

**Session State carries** (extracted by `ConversationStateTracker`):
- `current_date`, `current_time`, `timezone` — resolves "today", "this week"
- `active_date`, `mentioned_dates` — resolves "March 15", "next Friday", "tomorrow" → ISO date
- `active_time_start/end` — resolves "at 2 PM" → "14:00"
- `mentioned_emails` — resolves "to John" → `john@example.com` (from earlier in conversation)
- `last_found_paths`, `last_found_folder` — extracted from previous assistant reply text

**Manifests carry** (written by tool calls):
- `octa_manifest.txt` — all file paths from the most recent file search (unlimited size)
- `octa_context.json` — agent-namespaced resolved entities (calendar slots, email IDs)
- `operation_history.json` — copy/move history for undo
- `octa_jobs.json` — background task status

**Overlap at `last_found_paths`:** Both sources provide file paths. `_merge_manifest_into_session()` in `skill_dag_engine.py` resolves this by replacing session-state paths with manifest paths whenever the manifest was written in the last 30 minutes (fresher = wins). This prevents stale session state from pointing at old results when a background job updated the manifest.

---

## Key Files Reference

| File | Role |
|---|---|
| `src/agent/hub/processor.py` | Entry point: enrichment, routing dispatch, summary log |
| `src/agent/workflows/router.py` | Classifies command → list of agent names (1 LLM call) |
| `src/agent/workflows/master_orchestrator.py` | Multi-agent: plan + execute + final answer assembly |
| `src/agent/workflows/dag_planner.py` | DAGStep/DAGPlan data classes; topological sort; `plan_dag_workflow`; `execute_dag_workflow` |
| `src/agent/workflows/skill_dag_engine.py` | Per-agent: 2-call plan→execute→synthesise loop; `_compact_tool_docs_for_planning()` |
| `src/agent/workflows/skill_react_engine.py` | Fallback: per-agent ReAct loop (up to 6 iterations) |
| `src/agent/workflows/agent_registry.py` | Maps agent name → executor callable + capabilities text |
| `src/agent/core/skill_loader.py` | FAISS tool selection; `_strip_context_blocks()` strips session state before embedding |
| `src/agent/context/conversation_state.py` | Extracts structured entities (dates, emails, paths) → `## Session State` block |
