# OctaMind Manifest Architecture

*Last Updated: March 7, 2026*

> **Core Idea:** Separate the *reasoning layer* (LLM) from the *state layer* (Manifest).  
> The LLM thinks. The Manifest remembers.

---

## Table of Contents

- [OctaMind Manifest Architecture](#octamind-manifest-architecture)
  - [Table of Contents](#table-of-contents)
  - [1. The Problem This Solves](#1-the-problem-this-solves)
    - [What breaks without a Manifest](#what-breaks-without-a-manifest)
    - [What changes with a Manifest](#what-changes-with-a-manifest)
  - [2. What Is a Manifest?](#2-what-is-a-manifest)
  - [3. The Two Layers: Reasoning vs State](#3-the-two-layers-reasoning-vs-state)
  - [4. Manifest Types in OctaMind](#4-manifest-types-in-octamind)
    - [4.1 Context Manifest — Conversational State](#41-context-manifest--conversational-state)
    - [4.2 File Manifest — Search Results](#42-file-manifest--search-results)
    - [4.3 Operation Manifest — Undo / Rollback](#43-operation-manifest--undo--rollback)
    - [4.4 Job Manifest — Background Tasks](#44-job-manifest--background-tasks)
    - [4.5 Workflow Manifest — Multi-Step Pipelines](#45-workflow-manifest--multi-step-pipelines)
    - [4.6 Index Manifest — Local File Search Engine](#46-index-manifest--local-file-search-engine)
    - [4.7 Audit Manifest — Compliance Log](#47-audit-manifest--compliance-log)
  - [5. The Full Manifest Folder Structure](#5-the-full-manifest-folder-structure)
  - [6. Why This Architecture Is Correct](#6-why-this-architecture-is-correct)
    - [Comparison: How other systems handle state](#comparison-how-other-systems-handle-state)
    - [Why manifests beat "just use more session state"](#why-manifests-beat-just-use-more-session-state)
    - [The fundamental principle](#the-fundamental-principle)
  - [7. Implementation Status](#7-implementation-status)
    - [Context Manifest — Deployed Components (Phase 1 Complete)](#context-manifest--deployed-components-phase-1-complete)
  - [8. Implementation Roadmap](#8-implementation-roadmap)
    - [Phase 1 — Context Manifest ✅ COMPLETE](#phase-1--context-manifest--complete)
    - [Phase 2 — Operation Manifest + Undo ✅ COMPLETE (March 2026)](#phase-2--operation-manifest--undo--complete-march-2026)
    - [Phase 3 — Job Manifest (Async Tasks) ✅ COMPLETE (March 2026)](#phase-3--job-manifest-async-tasks--complete-march-2026)
    - [Phase 4 — Index + Audit (Power Features)](#phase-4--index--audit-power-features)

---

## 1. The Problem This Solves

### What breaks without a Manifest

**Scenario A — File Copy:**
```
User:  "Are there any image files on my computer?"
Agent: "Found 601 image files across jpg, png, gif, bmp..."
User:  "Can you copy them to a folder?"
Agent: "Could you please provide the destination folder name?" ← WRONG
```

The agent found 601 files. But in the next turn its working memory is gone.
The LLM has no idea what "them" refers to. It asks. The user is frustrated.

**Scenario B — Calendar Context:**
```
User:  "Check my calendar, do I have any free slots tomorrow?"
Agent: "Tomorrow you're free between 12 PM and 5 PM."
User:  "Book 2 PM."
Agent: "Sure! What date would you like to book 2 PM for?" ← WRONG
```

The agent already resolved "tomorrow" = March 6. But in the next turn it forgets.
It re-asks for the date. The user is frustrated again.

**Root cause:** The LLM's context window is **stateless between turns** by default.
Session state helps, but it is limited in size and lost when the process restarts.

### What changes with a Manifest

The agent **writes state to disk** after every meaningful action.
The next turn **reads from disk** before passing anything to the LLM.
The LLM receives fully resolved, unambiguous context — no need to ask.

```
User:  "Book 2 PM."
[System reads context_manifest.json → resolved_date = "2026-03-06"]
Agent: "Done! Booked for tomorrow, March 6 at 2 PM." ← CORRECT
```

---

## 2. What Is a Manifest?

A manifest is a **small structured file on disk** that stores the resolved
output of a previous agent action so the next turn can pick up exactly where
the last one left off.

**Properties of a good manifest:**
- Written **immediately** after an action completes (not deferred)
- **Human-readable** (JSON or plain text — no binary formats)
- **Overwritten** on each new action of the same type (no unbounded growth)
- **Versioned** with a timestamp so stale data can be detected
- **Namespaced** so manifests from different agents/actions don't collide

**Manifests are NOT:**
- A replacement for the memory system (memory = long-term; manifest = short-term state)
- A database (no indexing, no queries, no transactions)
- A cache (manifests are authoritative, not derived)

---

## 3. The Two Layers: Reasoning vs State

```
┌─────────────────────────────────────────────────────────┐
│                    REASONING LAYER                      │
│                                                         │
│   LLM (GPT-4o-mini)                                     │
│   • Understands user intent                             │
│   • Plans tool calls                                    │
│   • Synthesises a human-friendly response               │
│   • Knows HOW to act                                    │
│                                                         │
│   Input:  user message + manifest context (injected)    │
│   Output: tool calls + final message                    │
└────────────────────────┬────────────────────────────────┘
                         │  reads / writes
┌────────────────────────▼────────────────────────────────┐
│                      STATE LAYER                        │
│                                                         │
│   Manifest Files  (~/Downloads/OctaMind/)               │
│   • Stores WHAT was found / resolved / decided          │
│   • Deterministic — no inference needed to read it      │
│   • Survives process restarts                           │
│   • Not size-limited like LLM context window            │
│                                                         │
│   Manifests: context, files, operations, jobs,          │
│              workflows, index, audit                    │
└─────────────────────────────────────────────────────────┘
```

The critical boundary:
- The LLM **never stores state** — it reasons and responds.
- The Manifest **never reasons** — it stores and retrieves.

---

## 4. Manifest Types in OctaMind

### 4.1 Context Manifest — Conversational State

**File:** `<workspace>/data/octa_context.json`

**Purpose:** Store resolved entities and pending intent from the current
conversation so the next turn has full context without re-asking the user.

**Schema (v2 — keyed store, current):**

The file is a **keyed store** — each agent owns its own slot so multiple
agents' contexts can coexist without overwriting each other.

```json
{
  "calendar": {
    "schema_version": 2,
    "written_at": "2026-03-05T14:32:00",
    "expires_at": "2026-03-05T15:32:00",
    "agent": "calendar",
    "topic": "slot_booking",
    "scope": "single_file",
    "resolved_entities": {
      "tomorrow": "2026-03-06",
      "free_slots": [
        {"start": "12:00", "end": "17:00"}
      ],
      "subject": "meeting",
      "attendees": ["alice@example.com"]
    },
    "pending_selection": {
      "type": "time",
      "prompt": "Which time slot do you prefer?",
      "options": ["12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]
    },
    "awaiting": "time_selection"
  },
  "files": {
    "schema_version": 2,
    "written_at": "2026-03-05T14:33:10",
    "expires_at": "2026-03-05T15:33:10",
    "agent": "files",
    "topic": "file_search",
    "scope": "multi_folder",
    "resolved_entities": {
      "query": "payslip",
      "count": 3,
      "last_found_paths": ["C:\\Users\\...\\payslip_jan.pdf", "..."]
    },
    "awaiting": "file_action"
  }
}
```

**Key v2 properties:**
- Top-level keys are agent names (`"calendar"`, `"files"`, `"email"`, etc.)
- Each agent's slot is an independent context dict with its own `expires_at`
- `schema_version: 2` inside every slot
- `scope` field (optional): `"single_file"` | `"single_folder"` | `"multi_folder"` — used by the DAG planner to pick the correct zip strategy
- Legacy v1 flat payloads (single dict with `"written_at"` at root) are automatically migrated to a keyed slot on the next `write_context()` call

**API:**
```python
# Write — creates/updates this agent's slot (other agents' slots untouched)
write_context(agent="files", topic="file_search",
              resolved_entities={"query": "payslip", "count": 3},
              scope="multi_folder", awaiting="file_action")

# Read — agent-specific
ctx = read_context(agent="files")     # returns files' slot or None if expired
ctx = read_context()                  # returns most-recently-written slot (any agent)

# Clear — targeted or full
clear_context(agent="files")          # removes files' slot only
clear_context()                       # deletes the entire file
```

**Flow example — Calendar:**
```
Turn 1:
  User:  "Do I have free slots tomorrow?"
  Agent: Calls calendar API → finds free 12 PM–5 PM
         Writes context_manifest: resolved_entities.tomorrow = "2026-03-06",
                                  free_slots = [...],
                                  awaiting = "time_selection"
  Agent: "Tomorrow you're free 12 PM to 5 PM. Which time works?"

Turn 2:
  User:  "2 PM"
  [Code reads context_manifest → tomorrow = "2026-03-06", free_slots known]
  [Injects into LLM prompt: "Context: User previously asked about March 6.
   Free between 12 PM–5 PM. User now selected 2 PM."]
  Agent: Books slot for 2026-03-06 14:00
  Agent: "Done! Booked for tomorrow, March 6 at 2 PM." ✓
```

**More use cases for Context Manifest:**

| Domain      | Turn 1                               | Turn 2 (user's follow-up)     | What manifest stores                       |
|-------------|--------------------------------------|-------------------------------|--------------------------------------------|
| Calendar    | "Do I have free slots tomorrow?"     | "2 PM"                        | resolved_date, free_slots                  |
| Email       | "Show me emails from Alice today"    | "Reply to the first one"      | resolved_sender, resolved_date, email_ids  |
| Files       | "Find all large files on my C drive" | "Delete the top 5"            | found_paths, sorted_by_size                |
| Stock       | "What is Tesla's price trend?"       | "Set an alert at 250"         | resolved_ticker="TSLA", current_price      |
| Drive       | "List the files in my Projects folder"| "Share the second one"       | resolved_folder_id, listed_files           |
| WhatsApp    | "Show unread messages from Bob"      | "Reply: I'll call you later"  | resolved_contact, message_ids              |
| Habits      | "How am I doing on my gym habit?"    | "Mark today as done"          | resolved_habit_id, streak_count            |

**Every short reply that references a previous result benefits from the Context Manifest.**

**New API (March 2026):**
- `prune_context_history(days=30) → int` — removes entries older than N days; runs automatically (≤once/day) inside `write_context()`
- `get_context_history(days=30) → list` — audit viewer, newest-first (timestamps + labels only, no `resolved_entities`)

**Zero LLM-memory impact** — the history file is never injected into the prompt.

---

### 4.2 File Manifest — Search Results

**File:** `<workspace>/data/octa_manifest.txt`  
**Status:** ✅ IMPLEMENTED

**Purpose:** Store all file paths returned by a search so the next turn
can copy/move/zip all of them — not just the few that fit in the LLM reply.

**Format:** Plain text, one absolute path per line.
```
C:\Users\malus\Pictures\family\birthday.jpg
C:\Users\malus\Downloads\wallpaper.png
C:\Users\malus\Documents\scan_001.tiff
...
```

**Why plain text (not JSON)?**
- Readable with any tool (`notepad`, `cat`, `wc -l`)
- Easy to pipe into shell scripts
- Can contain 100,000+ entries without performance concerns
- `shutil.copy2` reads line-by-line — O(1) memory no matter how many files

**Enhanced schema (future):**
```json
{
  "schema_version": 2,
  "written_at": "2026-03-05T14:03:36",
  "query": "image files",
  "extensions_searched": ["jpg","jpeg","png","gif","bmp","tiff","webp","svg","ico"],
  "total_found": 601,
  "total_size_bytes": 154892314,
  "files": [
    {
      "path": "C:\\Users\\malus\\Pictures\\birthday.jpg",
      "size_bytes": 182477,
      "modified": "2025-12-25T18:30:00",
      "hash_md5": "a1b2c3d4..."
    }
  ]
}
```

Adding hash enables deduplication: if `hash_md5` already exists in manifest,
skip the copy — instant zero-cost duplicate detection.

---

### 4.3 Operation Manifest — Undo / Rollback

**File:** `<workspace>/data/operation_history.json`  
**Status:** ✅ LIVE (Phase 2 complete — March 2026)

**Purpose:** Record every copy/collect operation so it can be reversed with
a single "undo" command, and reviewed via the audit history.

**Schema (most-recent-first array, entries kept for 30 days):**
```json
[
  {
    "type":        "copy",
    "destination": "C:\\Users\\malus\\Downloads\\qwerty",
    "count":       802,
    "timestamp":   "2026-03-06T14:05:22",
    "undone":      false
  },
  {
    "type":        "copy",
    "destination": "C:\\Hrishikesh\\OctaMind\\data",
    "count":       601,
    "timestamp":   "2026-03-05T10:11:00",
    "undone":      true,
    "undone_at":   "2026-03-05T10:15:00"
  }
]
```

**Implemented API (`src/files/features/file_ops.py`):**
- `_log_operation(op_type, destination, count)` — pushes to front; prunes entries >30 days
- `undo_last_file_operation() → dict` — finds most-recent non-undone entry, deletes folder, marks `undone: true`
- `list_file_operations(days=30) → dict` — LLM-callable audit viewer, newest-first

**Enabled user commands:**
```
"Undo that"
"Undo the last copy"
"Show me what operations were done recently"
"What did you copy in the last week?"
```

**Auto-pruning:** entries older than 30 days removed on every `_log_operation()` call.

---

### 4.4 Job Manifest — Background Tasks

**File:** `<workspace>/data/octa_jobs.json`  
**Status:** ✅ LIVE (Phase 3 complete — March 2026)

**Purpose:** Long-running tasks (scanning all drives, generating a large
report, downloading many files) write progress to disk. The user can ask
for status at any time, even from a different session.

**Schema:**
```json
{
  "jobs": [
    {
      "job_id": "job_00101",
      "created_at": "2026-03-05T14:00:00",
      "updated_at": "2026-03-05T14:04:30",
      "agent": "files",
      "description": "Full disk image scan",
      "status": "running",
      "progress_pct": 67,
      "progress_detail": "Scanned 312 of 467 folders",
      "result_manifest": "~/Downloads/OctaMind/octa_manifest.txt",
      "started_by": "pa_7ea1659c",
      "estimated_done_at": "2026-03-05T14:06:00"
    }
  ]
}
```

**Enabled user commands:**
```
"Check status of my previous task"
"How far along is the scan?"
"Is the report ready yet?"
"Cancel job_00101"
```

This is how Manus and similar agent systems implement async tasks.
They never block on long operations — they write a job manifest and return
immediately. The background worker updates progress. The user polls status.

**Implemented API (`src/agent/manifest/job_manifest.py`):**
- `create_job(agent, description, session_id, pa_id, params) → job_id`
- `update_job(job_id, *, status, progress_pct, progress_detail, result_summary, result_manifest) → bool`
- `complete_job(job_id, result_summary, result_manifest) → bool`
- `fail_job(job_id, error) → bool`
- `get_job(job_id) → dict | None`
- `get_recent_jobs(limit) → list[dict]`
- `get_jobs_for_session(session_id, limit) → list[dict]`

**Background runner (`src/agent/manifest/job_runner.py`):**
- `submit_job(job_id, fn, session_id, pa_id)` — runs `fn()` in a daemon thread
- On completion: writes result to job manifest, notifies user via Telegram or Dashboard
- Concurrency limit: 4 simultaneous background jobs (threading.Semaphore)

**Integrated into Files Agent (`src/agent/ui/files_agent/orchestrator.py`):**
- `_is_heavy_scan(query)` — detects full-disk scan patterns
  ("on my computer", "across all drives", "entire laptop", etc.)
- `_try_background_job(query, artifacts_out)` — pre-flight check:
  returns an immediate acknowledgement and dispatches the scan to a background thread
- Execution order in `execute_with_llm_orchestration()`:
  1. Manifest-based copy bypass (no LLM)
  2. **Background scan dispatch** (heavy queries → daemon thread)
  3. Normal synchronous LLM execution (all other queries)

**Session routing (`src/agent/hub/processor.py`):**
- `_run_single_agent()` now seeds `_session_id`, `_pa_id`, `_source` into
  `artifacts_out` before every agent call so background jobs know who to notify

**Delivery policy improvements (same release):**
- `deliver_file()` is now strictly opt-in: ONLY triggered when the user explicitly says
  "send it", "download this", "give me the file", "deliver it".
  Count / search / analysis queries NEVER trigger file delivery.
- Multi-file delivery rule: collect → zip → deliver the zip ONCE. Never loop.

**Notification routing:**
- Session IDs follow the pattern `{source}_{identifier}` (e.g. `telegram_12345`)
- `_notify_user()` in job_runner.py extracts the source from the prefix and routes accordingly
- Telegram: calls `telegram_service.send_text(chat_id, message)` inside the job thread
  (inherits process env vars including `TELEGRAM_BOT_TOKEN` from the PA poller process)
- Other sources: result is in the job manifest; the client polls via `get_job(job_id)`

**Enabled user commands:**
```
"How many PDF files are there on my computer?"  → background scan, notification when done
"Find all image files on my laptop"             → background scan
"Search all drives for documents named report"  → background scan
"Scan my entire computer for large files"       → background scan
```

---

### 4.5 Workflow Manifest — Multi-Step Pipelines

**File:** `~/Downloads/OctaMind/octa_workflow_{id}.json`  
**Status:** 🔲 PLANNED

**Purpose:** When a task spans multiple agents and can fail midway, the
workflow manifest stores which stages completed so a retry starts from
the failure point — not from the beginning.

**Schema:**
```json
{
  "workflow_id": "wf_00201",
  "created_at": "2026-03-05T15:00:00",
  "description": "Collect PDFs → extract text → summarise → email",
  "status": "partial",
  "stages": [
    {
      "stage": "collect_pdfs",
      "status": "completed",
      "output_manifest": "octa_manifest.txt",
      "completed_at": "2026-03-05T15:01:10",
      "file_count": 23
    },
    {
      "stage": "extract_text",
      "status": "completed",
      "output_dir": "~/Downloads/OctaMind/extracted/",
      "completed_at": "2026-03-05T15:03:45"
    },
    {
      "stage": "summarise",
      "status": "failed",
      "error": "LLM rate limit",
      "retry_count": 1
    },
    {
      "stage": "email_results",
      "status": "pending"
    }
  ],
  "next_stage": "summarise"
}
```

**Enabled user commands:**
```
"Resume the summarisation task"
"What failed in the last workflow?"
"Retry from the summarisation step"
"Skip summarisation and just email the extracted text"
```

---

### 4.6 Index Manifest — Local File Search Engine

**File:** `~/Downloads/OctaMind/octa_index.json`  
**Status:** 🔲 PLANNED

**Purpose:** An incremental, hash-based index of the entire file system.
On first scan it takes time. On subsequent scans it only processes files
whose `last_modified` timestamp changed — massive performance gain.

**Schema:**
```json
{
  "schema_version": 1,
  "indexed_at": "2026-03-05T03:00:00",
  "total_files": 184231,
  "total_size_bytes": 492833710080,
  "files": [
    {
      "path": "C:\\Users\\malus\\Pictures\\vacation.jpg",
      "size_bytes": 4194304,
      "modified": "2025-08-14T19:22:00",
      "hash_md5": "e4d909c2...",
      "extension": ".jpg",
      "tags": ["image", "large"],
      "ai_summary": null
    }
  ]
}
```

**How incremental scanning works:**
```python
old_index = load_index()           # load previous run
current_files = os.walk(root)      # scan disk quickly (metadata only)

for fpath, mtime in current_files:
    old_entry = old_index.get(fpath)
    if old_entry and old_entry["modified"] == mtime:
        keep old_entry as-is        # no change → skip hash + AI
    else:
        recompute hash, AI summary  # changed or new file
```

This is how professional backup systems (rsync, Time Machine, Veeam) work.
On second scan of a 200 GB disk, only the ~50 changed files are processed.

**Deduplication via hash:**
```python
seen_hashes = {}
for entry in index["files"]:
    if entry["hash_md5"] in seen_hashes:
        entry["duplicate_of"] = seen_hashes[entry["hash_md5"]]
    else:
        seen_hashes[entry["hash_md5"]] = entry["path"]
```

**Enabled user commands:**
```
"Find all duplicate photos"                → filter index by duplicate_of
"Show me files I haven't opened in a year" → filter by last_accessed
"What are my 10 largest files?"            → sort index by size_bytes DESC
"Find all files tagged 'work'"             → filter by tags
"Reorganise only the files that changed since last week" → filter by modified
```

---

### 4.7 Audit Manifest — Compliance Log

**Status:** ✅ PARTIAL LIVE (March 2026) — two audit streams implemented:

| Stream | File | Implementation |
|--------|------|---------------|
| Context audit | `<workspace>/data/octa_context_history.jsonl` | `src/agent/manifest/context_manifest.py` |
| Operation audit | `<workspace>/data/operation_history.json` | `src/files/features/file_ops.py` |
| Full event audit | `<workspace>/data/octa_audit.jsonl` | 🔲 PLANNED |

**Context audit** (LIVE): every `write_context()` appends a lightweight JSONL line
(strips `resolved_entities` to keep size minimal). Auto-pruned to 30 days.

**Operation audit** (LIVE): every copy/collect operation is logged in a JSON array
(newest first, 30-day TTL). Used by `list_file_operations()` LLM tool.

**Full event audit** (PLANNED): append-only JSONL for all agent actions at the
tool-call granularity. Below is the planned per-event schema:

```json
{"event_id":"ev_0001","ts":"2026-03-06T14:03:36","agent":"files","action":"search_by_extension","input":{"ext":"jpg","directory":"~"},"output_summary":"found 100 files","user":"pa_7ea1659c","llm_calls":2}
{"event_id":"ev_0002","ts":"2026-03-06T14:03:50","agent":"files","action":"save_search_manifest","input":{"count":601},"output_summary":"manifest written","user":"pa_7ea1659c","llm_calls":0}
```

**Enabled user commands (live today):**
```
"What did you copy recently?"
"Show me operations from the last 3 days"
"Undo the last operation"
"Did you touch any files in Documents?"
```

---

## 5. The Full Manifest Folder Structure

```
<workspace>/data/
│
├── octa_manifest.txt              ← File search results (paths, one per line)
│                                     OVERWRITTEN on each new search
│
├── octa_context.json              ← Conversational context (resolved entities,
│                                     pending selections, awaiting state)
│                                     OVERWRITTEN on each new topic/turn
│
├── octa_context_history.jsonl     ← ✅ LIVE — append-only context audit log
│                                     Auto-pruned to 30 days
│
├── operation_history.json         ← ✅ LIVE — copy/undo operation history
│                                     Newest-first JSON array, 30-day TTL
│
├── octa_jobs.json                 ← ✅ LIVE — Background job registry (Phase 3)
│
├── octa_index.json                ← Local file search index / incremental (PLANNED)
│
├── octa_audit.jsonl               ← Full event audit log / append-only (PLANNED)
│
├── octa_workflow_{id}.json        ← Per-workflow manifest (PLANNED)
│
└── [copied files]                 ← Files copied by collect_files_from_manifest
```

**Naming conventions:**
- `octa_` prefix — all OctaMind manifests are easily identifiable
- Singular topic manifests (`context`, `jobs`, `index`) — one file, overwritten/updated
- Per-instance manifests (`workflow_{id}`) — one file per instance, deleted on completion
- Append-only logs (`audit.jsonl`) — `.jsonl` extension signals append-only semantics

---

## 6. Why This Architecture Is Correct

### Comparison: How other systems handle state

| System              | State Mechanism             | Analogy              |
|---------------------|-----------------------------|----------------------|
| LLM naive approach  | Entire history in context   | Trying to remember everything in your head |
| Session state only  | In-memory dict (lost on restart) | Sticky notes that fall off when you close the door |
| Database            | SQL/NoSQL (overkill for local) | Filing cabinet for every thought |
| **OctaMind Manifest** | **Structured files on disk** | **A notepad you always carry** |

### Why manifests beat "just use more session state"

1. **Size limit:** Session state caps at a few KB of serialised context. A file manifest
   can hold 600,000 paths. No cap.

2. **Restart survival:** Session state lives in `st.session_state` — it dies with the
   Python process. Manifests survive restarts, crashes, and OS reboots.

3. **Multi-agent access:** Multiple agents (files, calendar, email) can all read the
   same `octa_context.json`. Session state is isolated per agent process.

4. **Human-inspectable:** You can open `octa_manifest.txt` in Notepad right now and
   see exactly what the agent found. Session state is invisible.

5. **Deterministic:** Reading a manifest file cannot fail due to LLM hallucination.
   It either has the data or it doesn't.

### The fundamental principle

> **LLM context window = working memory (volatile, small, expensive)**  
> **Manifest files = notepad (persistent, unlimited, free)**  
>  
> A senior developer reviewing 500 files doesn't load all of them into their head.  
> They write a list, work through the list, tick items off.  
> The List is the manifest.

---

## 7. Implementation Status

| Manifest              | File                        | Status              | Notes                              |
|-----------------------|-----------------------------|---------------------|------------------------------------|
| File Manifest         | `octa_manifest.txt`         | ✅ LIVE             | `save_search_manifest()`, `collect_files_from_manifest()` |
| Context Manifest      | `octa_context.json`         | ✅ LIVE (Phase 1)   | Scheduler ✅ Email ✅ Drive ✅ Files ✅ |
| Operation Manifest    | `operation_history.json`    | ✅ LIVE (Phase 2)   | Undo/rollback + 30-day audit |
| Job Manifest          | `octa_jobs.json`            | ✅ LIVE (Phase 3)   | Async background tasks + Telegram notification |
| Workflow Manifest     | `octa_workflow_{id}.json`   | 🔲 PLANNED          | Multi-step pipeline recovery |
| Index Manifest        | `octa_index.json`           | 🔲 PLANNED          | Incremental file index + dedup |
| Audit Manifest        | `octa_audit.jsonl`          | ✅ PARTIAL (context + ops) | Full event log PLANNED |

### Context Manifest — Deployed Components (Phase 1 Complete)

| Component | File | Role |
|-----------|------|------|
| Core engine | `src/agent/manifest/context_manifest.py` | write/read/inject/clear + per-awaiting LLM instructions |
| Package marker | `src/agent/manifest/__init__.py` | Python package |
| Scheduler integration | `src/agent/ui/scheduler_agent/orchestrator.py` | Auto-wrap 4 calendar tools + `save_context` LLM tool |
| Email integration | `src/agent/ui/email_agent/orchestrator.py` | Auto-wrap `list_emails`, `get_todays_emails`, `fetch_emails_to_markdown` + `save_context` tool |
| Drive integration | `src/agent/ui/drive_agent/orchestrator.py` | Auto-wrap `list_files`, `search_files` + `save_context` tool |
| Files integration | `src/agent/ui/files_agent/orchestrator.py` | Auto-wrap `search_by_name`, `search_by_extension` + `save_context` tool |
| Central injection | `src/agent/hub/processor.py` (`_run_single_agent`) | Calls `inject_context_into_query()` before every agent dispatch |

---

## 8. Implementation Roadmap

### Phase 1 — Context Manifest ✅ COMPLETE

Resolves the calendar / email / files "follow-up ambiguity" class of bugs.

**What was built:**
- `src/agent/manifest/context_manifest.py` — Core engine (400+ lines)
  - `write_context(agent, topic, resolved_entities, awaiting, pending_selection, ttl_minutes=60)`
  - `read_context(max_age_minutes=60) → dict | None` — enforces TTL
  - `clear_context()`
  - `inject_context_into_query(user_query) → str` — prepends structured context block
  - `make_save_context_tool(agent) → Callable` — factory for LLM-callable explicit tool
  - `auto_save_*_context(result, query)` passthrough wrappers for each of the 4 agents
- Injected via `inject_context_into_query()` in `processor.py` — ALL agents benefit automatically
- Auto-wrap in 4 orchestrators: listing/search tools write context without LLM involvement
- Explicit `save_context` LLM tool in all 4 agents for edge cases auto-wrap misses
- 6 `awaiting` types with per-type LLM instructions:
  - `time_selection`, `event_selection`, `email_action`, `file_action`, `drive_file_action`, `confirmation`
- TTL: 60 minutes (configurable). Context file: `~/Downloads/OctaMind/octa_context.json`

**Architecture (dual-layer reliability):**
- **Layer 1 'auto-wrap'**: listing tools in orchestrators call `auto_save_*` as passthrough — context written WITHOUT LLM involvement. Guaranteed on every relevant call.
- **Layer 2 'LLM tool'**: `save_context` in every agent’s tool map — LLM can call explicitly for edge cases.

**Result:** "2 PM" after a calendar query automatically resolves to the correct date. Pronoun references ("reply to it", "share the second one", "copy them") resolve correctly without re-asking.

---

### Phase 2 — Operation Manifest + Undo ✅ COMPLETE (March 2026)

**What was built:**
- `src/files/features/file_ops.py`
  - `_log_operation(op_type, destination, count)` — pushes to front of `operation_history.json`; prunes >30-day entries
  - `undo_last_file_operation() → dict` — locates most-recent non-undone entry, deletes destination folder, marks `undone: true` + `undone_at`
  - `list_file_operations(days=30) → dict` — LLM-callable audit viewer, newest-first
- `src/agent/ui/files_agent/orchestrator.py` — registered `list_file_operations` as callable tool; fixed copy destination Rule #1 default to `data_dir`
- `src/agent/manifest/context_manifest.py`
  - `octa_context_history.jsonl` — lightweight append-only context audit (strips `resolved_entities`)
  - `prune_context_history(days=30)` — daily auto-prune on every `write_context()` call
  - `get_context_history(days=30) → list` — returns parsed entries for LLM/debug queries

**Result:** Users can say "undo the last copy", "show me recent operations", and "what did you copy last week?" — all resolved via on-disk history without LLM involvement.

---

### Phase 3 — Job Manifest (Async Tasks) ✅ COMPLETE (March 2026)

**What was built:**
- `src/agent/manifest/job_manifest.py` — Job manifest CRUD engine
  - `create_job(agent, description, session_id, pa_id, params) → job_id`
  - `update_job(job_id, *, status, progress_pct, progress_detail, …) → bool`
  - `complete_job(job_id, result_summary, result_manifest) → bool`
  - `fail_job(job_id, error) → bool`
  - `get_job(job_id) → dict | None`
  - `get_recent_jobs(limit) → list[dict]`
  - `get_jobs_for_session(session_id, limit) → list[dict]`
  - File: `<workspace>/data/octa_jobs.json`, newest-first JSON array, 200-job cap
- `src/agent/manifest/job_runner.py` — Background daemon thread pool
  - `submit_job(job_id, fn, session_id, pa_id)` — executes fn() in background thread
  - `_notify_user(session_id, pa_id, message)` — routes notification to Telegram or manifest poll
  - Concurrency limit: 4 slots (threading.Semaphore)
- `src/agent/ui/files_agent/orchestrator.py` — Pre-flight heavy-scan detection
  - `_is_heavy_scan(query)` + `_try_background_job(query, artifacts_out)`
  - Triggers on: "on my computer", "across all drives", "entire laptop/disk", "full disk scan"
  - Exempts scoped searches: "in Downloads", "in Documents", explicit drive path
- `src/agent/hub/processor.py` — Seeds `_session_id`, `_pa_id`, `_source` into
  `artifacts_out` before every agent call so background jobs know who to notify
- Delivery policy: `deliver_file()` is now strictly opt-in (no auto-send on search/count)

**Result:** "How many PDF files are there on my computer?" now returns immediately
with a job acknowledgement and sends a Telegram message when the scan completes.

---

### Phase 4 — Index + Audit (Power Features)

**What to build:**
- `src/agent/manifest/index_manifest.py` (incremental scanner)
- `src/agent/manifest/audit_manifest.py` (JSONL appender)
- Schedule index refresh nightly (piggyback on memory consolidation daemon)
- Expose audit queries as a tool: `get_agent_history(hours=24)`

---

*This document describes the complete Manifest Architecture for OctaMind.  
Each manifest type solves a specific class of "agent forgot what it was doing"
failures by moving state from volatile LLM context to persistent disk storage.*
