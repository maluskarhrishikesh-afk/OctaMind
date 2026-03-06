# OctaMind Request Pipeline — Full Architecture Walkthrough

> **Scope** — This document explains exactly what happens, step by step, for three
> representative user messages.  It describes every data structure that gets written
> and read, every LLM call that is made, and how the final answer is produced.
> Use it to evaluate whether the current architecture is sound or needs refactoring.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Scenario A — Fresh File Search](#2-scenario-a--fresh-file-search)
3. [Scenario B — Context Follow-up (Zip + Email)](#3-scenario-b--context-follow-up-zip--email)
4. [Scenario C — Normal Conversation](#4-scenario-c--normal-conversation)
5. [Data Structures Reference](#5-data-structures-reference)
6. [LLM Call Budget Summary](#6-llm-call-budget-summary)
7. [Architecture Assessment — Gaps Fixed](#7-architecture-assessment--gaps-fixed)
8. [More Examples in Plain Language](#8-more-examples-in-plain-language)

---

## 1. System Overview

Every user message enters a single pipeline regardless of source (Telegram, Dashboard,
Hub API).  The layers in execution order are:

```
User Message
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  HubRequest  (processor.py › _process_message)                      │
│  • Wraps message + source + agent_id + session_id                   │
│  • Loads last N conversation turns as `history`                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  _dispatch()  — the routing brain                                   │
│                                                                     │
│  Step 1 │ _enrich_scheduling_followup()                             │
│         │   Turns bare "2PM–3PM" into "Schedule a 2PM–3PM block"    │
│                                                                     │
│  Step 2 │ _build_sq()  — Session State builder                      │
│         │   Scans the last 10 history messages + current command    │
│         │   Extracts: dates, times, file paths, e-mails             │
│         │   Returns an enriched query string with a JSON block      │
│                                                                     │
│  Step 3 │ read_context()  — Context Manifest reader                 │
│         │   Loads data/octa_context.json if <60 min old             │
│         │   Contains: agent, topic, resolved_entities, awaiting     │
│                                                                     │
│  Step 4 │ classify_and_route()  — Unified Intent Classifier         │
│         │   LLM call (max_tokens=100) → JSON {category, agents}     │
│         │   category ∈ { "chat", "fresh_task", "context_followup" } │
│                                                                     │
│  Step 5 │ Route on category + agent count                           │
│         │   chat            → _chat_response()                      │
│         │   1 agent         → _run_single_agent()                   │
│         │   N agents        → run_workflow() → DAG pipeline         │
└─────────────────────────────────────────────────────────────────────┘
```

### Persistent State Files

| File | Written by | Read by | Purpose |
|---|---|---|---|
| `data/octa_context.json` | Agent orchestrators (after tool results) | `_dispatch` + agent orchestrators | Cross-turn context: found files, listed emails, etc. |
| `data/octa_manifest.txt` | Files agent (`search_files` tool) | Files agent (`collect_files_from_manifest`) | Full list of file paths from the last search |
| `data/octa_context_history.jsonl` | `write_context()` | Audit/debug only | Append-only history of every context write |
| `data/hub_conversations.json` | HubProcessor | HubProcessor | Full turn history per session |

---

## 2. Scenario A — Fresh File Search

**User message:** `"Are there any payslips on my computer?"`

### Step 1 — Scheduling Enrichment

`_enrich_scheduling_followup("Are there any payslips on my computer?", history)`

→ No time-slot pattern found.  Returns the original message unchanged.

**routing_message** = `"Are there any payslips on my computer?"`

---

### Step 2 — Session State Build

`_build_sq("Are there any payslips on my computer?", history)`

The `ConversationStateTracker` scans the last 10 history messages plus the current
command.  For a fresh conversation (no prior messages):

```json
{
  "current_date": "2026-03-06",
  "timezone": "IST (UTC+05:30)"
}
```

No dates, times, file paths, or e-mail addresses are found.  The enriched query
becomes:

```
Are there any payslips on my computer?

## Session State
{"current_date": "2026-03-06", "timezone": "IST (UTC+05:30)"}
```

---

### Step 3 — Context Manifest Read

`read_context()` opens `data/octa_context.json`.

→ Either the file does not exist (first run) or it has expired.  
**`_active_ctx = None`**

---

### Step 4 — Intent Classification

`classify_and_route("Are there any payslips on my computer?", active_context=None, session_state={...})`

**Fast-path check:** `active_context is None` AND `keyword_pre_filter()` returns `True`
(the word "payslips" is not in the broad keyword map, but "computer" also isn't —
actually "files" doesn't appear either, so keyword_pre_filter may return False).

> The keyword pre-filter uses words extracted from agent descriptions.  Words
> like "files", "computer", "payslips", "search" may or may not match depending
> on the registry content.  When they don't match, the fast-path fires:
> `active_context is None AND keyword_pre_filter() == False → category = "chat"`.
>
> **This is why the LLM call is essential for Scenario A.**  The keyword pre-filter
> is a performance optimisation for obvious conversational messages, not a reliable
> router for task messages.

When `keyword_pre_filter()` returns `False` but the message is clearly a task, the
fast-path incorrectly returns `chat`. The LLM call must succeed to route correctly.

**LLM call — the intent prompt sent to gpt-4o-mini (max_tokens=100):**

```
You are an intent classifier for a multi-agent AI assistant…

ACTIVE CONTEXT: none — this is the user's first message or the context expired.

AVAILABLE AGENTS: files, email, calendar, drive, whatsapp, scheduler, …

Classify the intent into exactly one of three categories:
  CHAT             — general knowledge / small talk, no tools needed
  FRESH_TASK       — new actionable request, needs one or more agents
  CONTEXT_FOLLOWUP — acting on results from the PREVIOUS turn …

User message: "Are there any payslips on my computer?"
…
```

**LLM response:**

```json
{
  "category": "fresh_task",
  "agents": ["files"],
  "reason": "User wants to search for payslip files on the local computer"
}
```

**Result:** `intent.category = "fresh_task"`, `intent.agents = ["files"]`

`agents_needed = ["files"]`

---

### Step 5 — Single-Agent Routing

`len(agents_needed) == 1` → calls `_run_single_agent("files", req, query=enriched_query)`

#### Step 5a — Context Manifest Injection

Before passing the query to the files agent, `inject_context_into_query()` is called.
Since `_active_ctx is None`, nothing is prepended.

**effective_query** (passed to files agent) =
```
Are there any payslips on my computer?

## Session State
{"current_date": "2026-03-06", "timezone": "IST (UTC+05:30)"}
```

#### Step 5b — Files Agent ReAct Loop

`run_skill_react(skill_name="files", user_query=effective_query, …)`

The files agent receives a system prompt describing all its tools
(`search_file`, `search_file_all_drives`, `list_directory`, `zip_folder`, etc.)
and runs a ReAct loop:

**Iteration 1 — LLM decides:**
```json
{
  "thought": "I should search across all drives for payslip files",
  "action": "call_tool",
  "params": {
    "tool": "search_file_all_drives",
    "kwargs": {"query": "payslip", "extensions": [".pdf", ".docx", ".xlsx"]}
  }
}
```

**Tool executes:** Scans C:\, D:\ etc. for files matching "payslip".

**Tool result fed back as observation:**
```json
[
  {"path": "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Dec.pdf", "size": 245120},
  {"path": "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Nov.pdf", "size": 238400},
  {"path": "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Oct.pdf", "size": 241500}
]
```

**Iteration 2 — LLM composes final answer:**
```json
{
  "thought": "Found 3 payslip files. I'll report them to the user.",
  "action": "final_answer",
  "params": {
    "message": "✅ Found **3 payslip files** on your computer:\n\n1. `Payslip_2025_Dec.pdf` — C:\\Hrishikesh\\Neo\\Payslips\\\n2. `Payslip_2025_Nov.pdf` — same folder\n3. `Payslip_2025_Oct.pdf` — same folder\n\nAll files are in `C:\\Hrishikesh\\Neo\\Payslips`."
  }
}
```

#### Step 5c — Context Manifest Written (critical for Scenario B)

After the search tool returns results, the files agent orchestrator calls
`write_context()` to persist what was found:

```json
{
  "schema_version": 1,
  "written_at":     "2026-03-06T14:23:11",
  "expires_at":     "2026-03-06T15:23:11",
  "agent":          "files",
  "topic":          "file_search",
  "resolved_entities": {
    "query":          "payslip",
    "count":          3,
    "last_found_folder": "C:\\Hrishikesh\\Neo\\Payslips",
    "last_found_paths": [
      "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Dec.pdf",
      "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Nov.pdf",
      "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Oct.pdf"
    ],
    "listed_files": [
      {"path": "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Dec.pdf", "type": "file"},
      {"path": "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Nov.pdf", "type": "file"},
      {"path": "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Oct.pdf", "type": "file"}
    ]
  },
  "awaiting": "file_action"
}
```

Simultaneously, `data/octa_manifest.txt` is written:
```
C:\Hrishikesh\Neo\Payslips\Payslip_2025_Dec.pdf
C:\Hrishikesh\Neo\Payslips\Payslip_2025_Nov.pdf
C:\Hrishikesh\Neo\Payslips\Payslip_2025_Oct.pdf
```

#### Step 5d — Pass-back to Hub

`_run_single_agent()` returns:
- `reply` = the formatted markdown message
- `search_paths` = list of 3 found file paths (stored on the conversation turn as `search_paths`)
- `file_artifacts` = `[]` (search results are context-only, not delivered)

The hub appends the assistant message to `hub_conversations.json` **with**
`search_paths` embedded, making them available to `ConversationStateTracker` in
the next turn.

#### Final Response to User

```
✅ Found 3 payslip files on your computer:

1. Payslip_2025_Dec.pdf — C:\Hrishikesh\Neo\Payslips\
2. Payslip_2025_Nov.pdf — same folder
3. Payslip_2025_Oct.pdf — same folder

All files are in C:\Hrishikesh\Neo\Payslips.
```

**LLM calls for Scenario A: 2** (1 intent classifier + 1–2 files ReAct iterations)

---

## 3. Scenario B — Context Follow-up (Zip + Email)

**User message:** `"Can you zip that and mail it to me?"` *(immediately after Scenario A)*

### Step 1 — Scheduling Enrichment

No time-slot pattern → unchanged.  
**routing_message** = `"Can you zip that and mail it to me?"`

---

### Step 2 — Session State Build

History now contains the previous turn (assistant replied about payslips).
The assistant message was stored with `search_paths`:

```python
{
  "role": "assistant",
  "content": "✅ Found 3 payslip files…",
  "search_paths": [
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Dec.pdf",
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Nov.pdf",
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Oct.pdf"
  ]
}
```

`ConversationStateTracker.build()` scans this and extracts:

```json
{
  "current_date":      "2026-03-06",
  "timezone":          "IST (UTC+05:30)",
  "last_found_paths":  [
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Dec.pdf",
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Nov.pdf",
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Oct.pdf"
  ],
  "last_found_folder": "C:\\Hrishikesh\\Neo\\Payslips",
  "last_assistant_action": "searched"
}
```

**enriched_query:**
```
Can you zip that and mail it to me?

## Session State
{
  "current_date": "2026-03-06",
  "timezone": "IST (UTC+05:30)",
  "last_found_paths": ["C:\\...\\Payslip_2025_Dec.pdf", ...],
  "last_found_folder": "C:\\Hrishikesh\\Neo\\Payslips",
  "last_assistant_action": "searched"
}
```

---

### Step 3 — Context Manifest Read

`read_context()` loads `data/octa_context.json` (written in Scenario A, still valid).

```python
_active_ctx = {
  "agent":    "files",
  "topic":    "file_search",
  "awaiting": "file_action",
  "resolved_entities": {
    "last_found_folder": "C:\\Hrishikesh\\Neo\\Payslips",
    "last_found_paths":  [...],
    "count": 3
  }
}
```

---

### Step 4 — Intent Classification

`classify_and_route("Can you zip that and mail it to me?", active_context=_active_ctx, session_state={...})`

The active context is NOT None so the fast-path is skipped.

**LLM intent prompt (summarised):**

```
ACTIVE CONTEXT (from previous turn):
  agent:    files
  topic:    file_search
  awaiting: file_action
  entities: {last_found_folder: "C:\Hrishikesh\Neo\Payslips", count: 3}

User message: "Can you zip that and mail it to me?"

Classify: CHAT | FRESH_TASK | CONTEXT_FOLLOWUP
```

**LLM response:**

```json
{
  "category": "context_followup",
  "agents":   ["files", "email"],
  "reason":   "User is acting on previously found payslip files — zip the found folder and email"
}
```

`agents_needed = ["files", "email"]`

---

### Step 5 — Multi-Agent Workflow (DAG Pipeline)

`len(agents_needed) == 2` → calls `run_workflow(enriched_query)`

#### Step 5a — DAG Planning (single LLM call)

`plan_dag_workflow(enriched_query)` sends a prompt to gpt-4o-mini with:
- Full agent capability descriptions (all registered agents)
- The enriched query including the `## Session State` block
- System path constants (Downloads, Desktop, etc.)
- Examples of fresh-search vs follow-up distinction

The DAG planner reads the `## Session State` block and sees `last_found_folder`.
It recognises `"zip that and mail it"` as a follow-up (pronoun "that"), not a
new search.

**DAG Planner LLM output:**

```json
[
  {
    "id":          "zip1",
    "agent":       "files",
    "instruction": "Zip the folder C:\\Hrishikesh\\Neo\\Payslips into an archive. Save the zip at C:\\Users\\malus\\Downloads\\Payslips.zip",
    "depends_on":  [],
    "description": "Zip payslips folder"
  },
  {
    "id":          "email1",
    "agent":       "email",
    "instruction": "Send {zip1.file_path} as an attachment to {__user_email__} with subject \"Payslips\"",
    "depends_on":  ["zip1"],
    "description": "Email the zip to user"
  }
]
```

#### Step 5b — Topological Sort

Kahn's algorithm processes the dependency graph:
- `zip1` has no dependencies → in-degree = 0 → executes first
- `email1` depends on `zip1` → in-degree = 1 → executes after

**Sorted execution order:** `[zip1, email1]`

#### Step 5c — Step Execution: zip1 (files agent)

Before calling the agent, `_resolve_instruction()` substitutes tokens:
- `{__user_email__}` → user's email from settings
- No `{step_id.field}` tokens in `zip1` (it's the first step)

**Resolved instruction:**
```
Zip the folder C:\Hrishikesh\Neo\Payslips into an archive.
Save the zip at C:\Users\malus\Downloads\Payslips.zip
```

`run_skill_react(skill_name="files", user_query=resolved_instruction)`

**Files agent ReAct — Iteration 1:**
```json
{
  "thought": "I'll zip the folder using zip_folder tool",
  "action": "call_tool",
  "params": {
    "tool": "zip_folder",
    "kwargs": {
      "folder_path": "C:\\Hrishikesh\\Neo\\Payslips",
      "output_path": "C:\\Users\\malus\\Downloads\\Payslips.zip"
    }
  }
}
```

**Tool result:**
```json
{
  "status":    "success",
  "file_path": "C:\\Users\\malus\\Downloads\\Payslips.zip",
  "size_mb":   0.7,
  "files_in":  3
}
```

**Files agent ReAct — Iteration 2:**
```json
{
  "thought": "Zip created successfully at the specified path",
  "action":  "final_answer",
  "params":  {"message": "✅ Created Payslips.zip (0.7 MB, 3 files)"}
}
```

`ctx_results["zip1"]` is set to:
```python
{
  "text":      "✅ Created Payslips.zip (0.7 MB, 3 files)",
  "artifacts": {"file_path": "C:\\Users\\malus\\Downloads\\Payslips.zip"}
}
```

#### Step 5d — Step Execution: email1 (email agent)

`_resolve_instruction()` substitutes the `{zip1.file_path}` token:

**Resolved instruction:**
```
Send C:\Users\malus\Downloads\Payslips.zip as an attachment to hrishikesh@example.com
with subject "Payslips"
```

`run_skill_react(skill_name="email", user_query=resolved_instruction)`

**Email agent ReAct — Iteration 1:**
```json
{
  "thought": "I'll send the zip file as an email attachment to the user",
  "action": "call_tool",
  "params": {
    "tool": "send_email",
    "kwargs": {
      "to":          "hrishikesh@example.com",
      "subject":     "Payslips",
      "message":     "Please find attached your payslip files.",
      "attachments": ["C:\\Users\\malus\\Downloads\\Payslips.zip"]
    }
  }
}
```

**Tool result:**
```json
{"status": "success", "message_id": "msg_abc123"}
```

**Email agent ReAct — Iteration 2:**
```json
{
  "thought": "Email sent successfully",
  "action":  "final_answer",
  "params":  {"message": "✅ Email sent to hrishikesh@example.com with Payslips.zip attached"}
}
```

#### Step 5e — Result Rendering

`_render_workflow_output()` takes the two step results and formats them:

```
✅ Payslips zipped and emailed successfully!

📋 **Step 1 — Zip payslips folder** *(files)*
  Created `Payslips.zip` (3 files, 0.7 MB) at Downloads/Payslips.zip

📧 **Step 2 — Email the zip to user** *(email)*
  Sent to hrishikesh@example.com with subject "Payslips"
```

#### Final Response to User

```
✅ Payslips zipped and emailed successfully!

📋 Step 1 — Zip payslips folder (files)
  Created Payslips.zip (3 files, 0.7 MB)

📧 Step 2 — Email the zip to user (email)
  Sent to hrishikesh@example.com with subject "Payslips"
```

**LLM calls for Scenario B: 4** (1 intent + 1 DAG plan + 1–2 files ReAct + 1–2 email ReAct)

---

## 4. Scenario C — Normal Conversation

**User message:** `"Do you know about cricket?"`

### Step 1 — Scheduling Enrichment

No time-slot → unchanged.  
**routing_message** = `"Do you know about cricket?"`

---

### Step 2 — Session State Build

```json
{"current_date": "2026-03-06", "timezone": "IST (UTC+05:30)"}
```

No special entities found.

---

### Step 3 — Context Manifest Read

Assume Scenario A was run earlier but the context has expired (TTL 60 min).  
**`_active_ctx = None`**

---

### Step 4 — Intent Classification

`classify_and_route("Do you know about cricket?", active_context=None, session_state={...})`

**Fast-path check:**
- `active_context is None` ✓
- `keyword_pre_filter("Do you know about cricket?")` scans agent description keywords.
  "cricket", "know", "about" → none match any agent keyword (after updated stop-words
  removed "about" from matching).
- `keyword_pre_filter()` returns `False`

**Fast-path fires immediately — zero LLM calls:**

```python
return IntentResult(
    category = "chat",
    agents   = [],
    reason   = "fast-path: no agent keywords and no active context"
)
```

---

### Step 5 — Conversational Response

`agents_needed = None` → calls `_chat_response(req, history)`

This calls the LLM with:
- The assistant's persona system prompt
- Last N turns of conversation history
- Any recalled long-term memory from the agent's memory store

**LLM response:**
```
Yes! Cricket is one of the world's most popular sports, especially in South Asia,
Australia, England, and the Caribbean.  …
```

No context manifest is written (there are no "results" to follow up on).

**Final Response to User:**

```
Yes! Cricket is one of the world's most popular sports…
```

**LLM calls for Scenario C: 1** (0 intent (fast-path) + 1 conversational LLM)

---

## 5. Data Structures Reference

### 5.1 Intent Result (`IntentResult` dataclass)

```python
@dataclass
class IntentResult:
    category: str          # "chat" | "context_followup" | "fresh_task"
    agents: List[str]      # e.g. [] | ["files"] | ["files", "email"]
    reason: str            # human-readable explanation (for logs)

    # Derived properties
    is_chat:             bool  # category == "chat"
    is_context_followup: bool  # category == "context_followup"
    is_fresh_task:       bool  # category == "fresh_task"
```

### 5.2 Context Manifest (`data/octa_context.json`) — Keyed Store

> **Updated (schema v2):** The file now stores one entry per agent so that an
> email search and a file search can coexist without overwriting each other.

```json
{
  "files": {
    "schema_version": 2,
    "written_at":     "2026-03-06T14:23:11",
    "expires_at":     "2026-03-06T15:23:11",
    "agent":          "files",
    "topic":          "file_search",
    "scope":          "single_folder",
    "awaiting":       "file_action",
    "resolved_entities": {
      "query":             "payslip",
      "count":             3,
      "last_found_folder": "C:\\Hrishikesh\\Neo\\Payslips",
      "last_found_paths":  ["C:\\...\\Payslip_Dec.pdf", "…"],
      "listed_files": [
        {"path": "C:\\...\\Payslip_Dec.pdf", "type": "file"}
      ]
    }
  },
  "email": {
    "schema_version": 2,
    "written_at":     "2026-03-06T14:21:05",
    "expires_at":     "2026-03-06T15:21:05",
    "agent":          "email",
    "topic":          "email_list",
    "awaiting":       "email_action",
    "resolved_entities": {
      "listed_emails": [
        {"id": "msg_001", "subject": "Q4 Report", "sender": "boss@company.com"}
      ]
    }
  }
}
```

Key fields for each entry:
- `agent` — which agent wrote this entry (used to gate injection: avoid injecting
  file-action instructions when the email agent is executing)
- `scope` — *(new)* `"single_file"`, `"single_folder"`, or `"multi_folder"`.
  The DAG planner uses this directly so it doesn't need to guess from a path list.
- `awaiting` — tells the next-turn LLM what kind of action is expected
  (`"file_action"`, `"email_action"`, `"time_selection"`, etc.)
- `expires_at` — stale context is silently discarded (default 60-minute window)

**`read_context(agent=X)`** returns only that agent's entry.  
**`read_context()`** (no argument) returns the most recently written entry across all agents.  
**`clear_context(agent=X)`** removes only that agent's slot.  
**`clear_context()`** deletes the entire file.

### 5.3 Session State JSON (injected into every agent query)

```json
{
  "current_date":         "2026-03-06",
  "timezone":             "IST (UTC+05:30)",
  "active_date":          "2026-03-06",
  "active_time_start":    "14:00",
  "last_found_paths": [
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Dec.pdf",
    "C:\\Hrishikesh\\Neo\\Payslips\\Payslip_2025_Nov.pdf"
  ],
  "last_found_folder":    "C:\\Hrishikesh\\Neo\\Payslips",
  "last_assistant_action": "searched",
  "mentioned_files":      ["payslip.pdf"],
  "mentioned_emails":     ["alice@example.com"]
}
```

This JSON block is appended to every query sent to every agent so tool calls
receive exact values (ISO dates, 24h times, absolute paths) rather than
natural-language descriptions.

### 5.4 DAG Plan (produced by `plan_dag_workflow()`)

```json
[
  {
    "id":          "zip1",
    "agent":       "files",
    "instruction": "Zip C:\\Hrishikesh\\Neo\\Payslips into C:\\Users\\malus\\Downloads\\Payslips.zip",
    "depends_on":  [],
    "description": "Zip payslips folder"
  },
  {
    "id":          "email1",
    "agent":       "email",
    "instruction": "Send {zip1.file_path} as attachment to {__user_email__} subject: Payslips",
    "depends_on":  ["zip1"],
    "description": "Email zip"
  }
]
```

`{zip1.file_path}` is a **context token** — resolved at execution time from
`ctx_results["zip1"]["artifacts"]["file_path"]` before the email agent runs.

### 5.5 How Context is Injected into Agent Queries

Before each agent call, `inject_context_into_query()` runs:

1. Reads `data/octa_context.json`
2. Checks `agent` field matches the current executing agent (prevents cross-agent
   tool hallucination — the drive agent should not see file-action instructions)
3. If matched and not expired, prepends a block to the query:

```
## Context from Previous Turn
Agent: files
Topic: file_search
Awaiting: file_action
The user is acting on files from the previous search.
File paths are stored in the file manifest (octa_manifest.txt).
Call collect_files_from_manifest() to copy, or use files from `listed_files`...
[awaiting-specific instructions]
Resolved entities: {count: 3, last_found_folder: "C:\...", ...}
```

This gives the agent's ReAct LLM the full context without the user needing to
repeat the file paths or details.

---

## 6. LLM Call Budget Summary

| Scenario | Intent | DAG Plan | Agent ReAct | Total |
|---|---|---|---|---|
| A — File search | 1 | 0 | 2 (files: 2 iters) | **3** |
| B — Zip + email  | 1 | 1 | 4 (files: 2, email: 2) | **6** |
| C — Cricket chat | 0 (fast-path) | 0 | 1 (chat LLM) | **1** |

Notes:
- The intent classifier uses `max_tokens=100` (much cheaper than agent calls)
- The DAG planner uses `max_tokens=2000` (one call replaces a multi-turn master loop)
- Each agent ReAct iteration is `max_tokens=800`
- Fast-path saves 1 LLM call for all pure-conversational messages

---

## 7. Architecture Assessment — Gaps Fixed

All six gaps identified in the original assessment have now been implemented.
This section documents what each problem was and exactly what was changed to resolve it.

---

### What Works Well (unchanged)

1. **Single routing decision point** — `classify_and_route()` handles all three
   intent types in one place, with no bolt-on overrides scattered across files.

2. **Context-aware routing** — The router reads the live context manifest before
   deciding, so "zip that" after a file search correctly becomes `context_followup`
   rather than an ambiguous pronoun.

3. **Session State** — Absolute file paths, ISO dates, and email addresses are
   extracted from history and injected into every agent query, eliminating the
   "tell me the date again" problem.

4. **DAG planner** — Replaces the old 1–12 call master ReAct loop with a single
   plan + deterministic execution.  Dependency tokens (`{zip1.file_path}`) allow
   clean handoffs between agents.

5. **Context manifest TTL** — Stale context (>60 min) is automatically discarded,
   preventing old search results from polluting new conversations.

---

### Gaps — All Fixed

#### Gap 1 — Keyword Pre-filter Too Broad / Too Narrow
**Status: ✅ FIXED** — `src/agent/workflows/agent_registry.py` + `router.py`

**What was wrong:** `keyword_pre_filter()` extracted words from agent description
text.  Innocuous words like "files" appeared in 6+ agent descriptions.  Worse,
IDF filtering sometimes *removed* important routing words like "email" because they
appeared in many descriptions.

**What was fixed:**
- Each agent in `AGENT_REGISTRY` now has a `"trigger_keywords"` list of words that
  *always* route to that agent, regardless of how common those words are.
  Example: `files` has `["payslip", "invoice", "zip", "folder", "disk"]`,
  `email` has `["email", "gmail", "inbox", "attachment", "draft"]`.
- `_build_keyword_map()` and `_build_distinctive_keyword_map()` in `router.py`
  both union in these curated keywords.  They bypass the IDF filter entirely so
  high-frequency important words are never silently dropped.

---

#### Gap 2 — Agent May Forget to Call `write_context()`
**Status: ✅ FIXED** — `src/agent/hub/processor.py` (`_run_single_agent`)

**What was wrong:** If an agent returned results but forgot to call
`write_context()`, the follow-up turn ("zip them") saw no context and triggered a
brand-new search instead of acting on the found files.

**What was fixed:**
- After every single-agent execution, `_run_single_agent()` now checks whether
  `search_paths` is non-empty and whether the manifest has an entry for that agent.
- If paths were returned but no context was written, a minimal safety-net entry is
  auto-written with `awaiting: "file_action"` and the found paths.

---

#### Gap 3 — No Way to Tell if Results Span One or Many Folders
**Status: ✅ FIXED** — `src/agent/manifest/context_manifest.py`

**What was wrong:** The DAG planner had to guess whether to call `zip_folder()`
(one folder) or `collect_files_from_manifest()` (files spread across folders) by
reasoning about path strings — something an LLM can get wrong.

**What was fixed:** `write_context()` now accepts a `scope` parameter
(`"single_file"`, `"single_folder"`, `"multi_folder"`).  Stored in the manifest.
The DAG planner reads `scope` and makes the strategy choice deterministically.

---

#### Gap 4 — Writing Context for One Agent Wiped Another Agent's Context
**Status: ✅ FIXED** — `src/agent/manifest/context_manifest.py`

**What was wrong:** `data/octa_context.json` was a flat object — one agent's write
wiped the previous agent's context.

**What was fixed:** The file is now a **keyed store** — each agent owns its own slot:
```json
{"files": { … }, "email": { … }}
```
All read/write/inject/clear functions updated; old flat-format files are migrated
automatically on first write.

---

#### Gap 5 — Context File Never Cleared After a Completed Task
**Status: ✅ FIXED** — `src/agent/hub/processor.py` (`_dispatch`)

**What was wrong:** After a multi-agent delivery (zip → email), the manifest still
said `awaiting: "file_action"` for up to 60 minutes.

**What was fixed:** At the end of `_dispatch()`, when `file_artifacts` is non-empty
(something was actually delivered), `clear_context()` is called immediately.

---

#### Gap 6 — Dashboard Did Not Store `search_paths` in Conversation History
**Status: ✅ FIXED** — `src/agent/ui/personal_assistant/app.py`

**What was wrong:** The Hub path (Telegram) stored `search_paths` on every
assistant message.  The Dashboard (Streamlit) only stored `content` — file paths
were lost so follow-ups like "zip them" would fail on the Dashboard.

**What was fixed:** After single-skill execution, `found_paths` is read from the
executor's `_pa_artifacts` dict and stored in the message entry under
`"search_paths"` — same key as the Hub path uses.

---

### Summary

| Gap | Problem | Fix Location | Status |
|-----|---------|--------------|--------|
| 1 | Keyword fallback misroutes when LLM is down | `agent_registry.py` + `router.py` | ✅ Fixed |
| 2 | Agent forgets `write_context()` → follow-up fails | `processor.py` `_run_single_agent` | ✅ Fixed |
| 3 | DAG planner guesses zip strategy from path list | `context_manifest.py` `write_context` | ✅ Fixed |
| 4 | File context wipes email context (and vice versa) | `context_manifest.py` (keyed store) | ✅ Fixed |
| 5 | Stale file context lingers after delivery | `processor.py` `_dispatch` | ✅ Fixed |
| 6 | Dashboard loses `search_paths` from history | `app.py` single-skill path | ✅ Fixed |

---

## 8. More Examples in Plain Language

This section explains what OctaMind does for common requests, written without
technical terms.  Think of it as: "what's actually happening when you send this?"

---

### Example 1 — "What time is my dentist appointment tomorrow?"

**You asked:** A question about your Google Calendar.

**What happens step by step:**
1. OctaMind reads your message and spots "appointment" and "tomorrow" — both are in
   the Calendar skill's keyword list.
2. It decides: Calendar skill is needed (fast — no AI routing call required).
3. The Calendar skill calls Google Calendar, finds tomorrow's events, filters for
   "dentist" in the title.
4. It saves the event details to a short-term memory note so you can say
   "remind me 1 hour before" next and it won't ask you again.
5. You get: "Your dentist appointment is at 3:00 PM tomorrow — Dr. Patel,
   City Dental Clinic."

---

### Example 2 — "Find my payslips and email them to John"

**You asked:** A two-part task: find local files AND send an email.

**What happens:**
1. "payslip" → Files skill.  "email" → Email skill.  Two skills → plan created.
2. **Step 1 (Files):** Searches all drives, finds three PDFs in `Documents/Payslips/`.
   Saves a note: *"3 payslips found, single folder, ready for action."*
3. **Step 2 (Email):** Zips the three PDFs, sends as an attachment to John.
4. After John's email is sent, the saved note is deleted — task complete.
5. You get: "✅ Found 3 payslips, zipped them, and emailed to john@example.com."

---

### Example 3 — "Show me my unread emails" → "Reply to the one from Alice"

**Two separate messages.  OctaMind connects them automatically.**

**First message:**
- Fetches unread emails, shows them numbered.
- Saves a note: *"showed 3 emails, user is about to act on one of them."*

**Second message:**
- Reads the saved note — already knows which emails were listed.
- Matches "Alice" to email #1 without asking you for Alice's address again.
- Sends the reply.

**Why it works even if you also searched files in between:** The notes system now
keeps Email context and Files context in separate slots — they don't overwrite
each other anymore.  (This is what Gap 4 fixed.)

---

### Example 4 — "Schedule a focus block from 2 PM to 4 PM tomorrow"

**You asked:** Create a named time block on your calendar.

**What happens:**
1. "2 PM to 4 PM tomorrow" is expanded to the exact ISO date and times using today's
   date before any AI even looks at it.
2. Routes to the Scheduler skill (handles smart blocks, not just basic events).
3. Checks your calendar for conflicts.
4. Creates the block: "Focus Time — 2:00 PM to 4:00 PM, Thu Mar 7."
5. You get: "✅ Added a 2-hour Focus Block on Thursday."

---

### Example 5 — "How are you doing today?"

**You asked:** Pure conversation — no task at all.

**What happens:**
1. OctaMind scans the message for any skill keywords.
   "how", "are", "doing", "today" → none match any skill.
2. Instant decision (no AI routing call needed): this is just a chat message.
3. The conversational AI replies with your assistant's personality.
4. You get a friendly response.

**Total AI calls: 1** — just the chat reply.  Zero routing AI wasted.

---

### Example 6 — "Log my gym workout for today"

**You asked:** Mark a habit as done.

**What happens:**
1. "gym", "workout", "log" → all in the Habit Tracker's keyword list.
2. Habit Tracker finds your "Gym" habit, marks today as done.
3. Checks your streak — you're on day 12!
4. You get: "✅ Logged Gym for today! 🔥 Current streak: 12 days."

---

### Example 7 — "Get me the full stock analysis for Tesla and email it to me"

**You asked:** Research + delivery across two skills.

**What happens:**
1. "Tesla", "analysis" → Stock Market skill.  "email" → Email skill.
2. **Step 1 (Stock):** Fetches price, calculates technical indicators, scores risk,
   reads news sentiment, builds a PDF report.
3. **Step 2 (Email):** Attaches the PDF, sends to your email.
4. Context cleared after delivery.
5. You get: "Tesla analysis complete.  PDF sent to you@example.com."

---

### Example 8 — "Are there any payslip files?" → "Zip them and upload to Drive"

**Two messages — the second one refers back to the first.**

**First message:**
- "payslip" hits the Files skill's curated keyword list (Gap 1 fix) — routes
  correctly even without an AI call.
- Finds 3 PDFs in one folder, saves a note with `scope: "single_folder"`.

**Second message:**
- "zip" → Files.  "upload to Drive" → Drive.  Two-step plan.
- **Step 1:** Planner reads `scope: "single_folder"` (Gap 3 fix) — picks
  `zip_folder()` directly instead of guessing from path strings.
- **Step 2:** Uploads `Payslips.zip` to Google Drive.
- Note cleared after upload (Gap 5 fix).
- You get: "Payslips.zip (3 files, 0.7 MB) uploaded to Google Drive."
