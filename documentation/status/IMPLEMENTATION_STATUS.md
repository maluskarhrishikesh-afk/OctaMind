# Implementation Status

Single source of truth for what is and isn't implemented. Use this to avoid hallucinating features that don't exist.

Last updated: 2026-03-07 (Session 6 — 6 pipeline architecture gaps fixed: trigger_keywords routing, keyed context store, scope field, auto-write context safety net, clear-after-delivery, search_paths in Dashboard messages)  
Previous: 2026-03-06 (Session 5 — Calendar local timezone fix; copy destination Rule #1 fix; operation history stack with 30-day undo + list_file_operations tool; context audit history with 30-day auto-prune)  
Previous: 2026-03-02 (Session 4 — Calendar year bug fixed; "send here" routing fixed; enriched scheduling context now propagated to agent execution; search_by_name sorts non-.lnk first; search_file_all_drives skips .lnk; skill_dag .id example fixed to .path; server restart still required)  
Previous: 2026-03-02 (Session 3 — New Files tools: search_file_all_drives, deliver_file, write_pdf_report, write_excel_report, organize_folder; fixed list_laptop_structure to always auto-save report as file_path)  
Previous: 2026-03-02 (Bug fixes: calendar date-context loss, ReAct observation truncation, Telegram Markdown entity crash, DAG JSON fence parsing verified; added human-friendly per-request workflow summary log; DAG algorithm walkthrough document added)  
Previous: 2026-03-02 (Telegram UX overhaul: typing indicators, real-time progress editing, /reset & /agents commands, long-message splitting, file-artifact delivery; Dashboard download button for file artifacts; HubProcessor scheduling-context enrichment propagated to Telegram channel; `send_document_file` multipart upload added to telegram_service)  
Previous: 2026-03-01 (fixed Python-bool JSON parse bug in skill_react_engine causing cascading `unknown action ''` failures; fixed tilde path expansion in dag_planner instruction resolver; added total LLM call count to workflow completion log; fixed website unicode emoji rendering; updated quickstart to remove internal Python snippet)

---

## ✅ 2026-03-07 Session 6 — 6 Pipeline Architecture Gaps Fixed

### Gap 1 — trigger_keywords for reliable keyword-fallback routing

**Problem:** The keyword fallback in `router.py` was built purely from description text. High-value domain words like `"payslip"`, `"rsi"`, `"whatsapp"` were absent from description sentences and therefore invisible to the fallback router.

**Fix:**
- Added `"trigger_keywords": [...]` list to every agent in `src/agent/workflows/agent_registry.py` (11 agents — drive, email, whatsapp, files, calendar, scheduler, file_organizer, habit_tracker, browser, stock_market, linkedin)
- `_build_keyword_map()` in `router.py` now unions description-derived words with `trigger_keywords`
- `_build_distinctive_keyword_map()` treats `trigger_keywords` as always-distinctive — they bypass the IDF frequency filter entirely

---

### Gap 2 — Auto-write context safety net in processor.py

**Problem:** If a files-agent executor returned `search_paths` but the agent forgot to call `write_context()`, the next user turn had no context to act on ("copy them" → agent asks "which files?").

**Fix:**
- In `src/agent/hub/processor.py` → `_run_single_agent()`: after the executor returns, if `search_paths` is non-empty AND `read_context(agent=agent) is None`, auto-writes a minimal context entry with `topic="auto_search_result"`, `awaiting="file_action"`, `last_found_paths`, `last_found_folder`, `count`

---

### Gap 3 — scope field in write_context()

**Problem:** `write_context()` had no way to record whether a file search returned a single file, a single folder, or multiple folders — the DAG planner had to guess the correct zip strategy.

**Fix:**
- Added `scope: Optional[str]` parameter to `write_context()` in `src/agent/manifest/context_manifest.py`
- Valid values: `"single_file"` | `"single_folder"` | `"multi_folder"`
- The DAG planner reads `scope` from the context manifest to choose `zip_folder` vs `zip_files`

---

### Gap 4 — Keyed context store (schema_version=2)

**Problem:** `write_context()` overwrote the entire `octa_context.json` file. If a calendar agent set time-selection context and the files agent then wrote its own context in the same turn, the calendar context was destroyed.

**Fix:**
- `octa_context.json` is now a **keyed store**: top-level keys are agent names, each agent owns its own slot
- `write_context()` loads existing store → writes into `store[agent]` → saves back (other agents' slots untouched)
- `read_context(agent=None)` accepts optional `agent` arg; returns that agent's slot or most-recently-written entry
- `clear_context(agent=None)` accepts optional `agent` arg; removes just that slot (or entire file)
- Legacy flat (schema_version=1) payloads are auto-migrated on next `write_context()` call
- File format bumped to `schema_version: 2`

---

### Gap 5 — clear_context after multi-agent delivery

**Problem:** After a multi-agent workflow (e.g. find files → email them) delivered its result, the file-action context remained on disk. A later unrelated query could accidentally pick it up and try to act on stale paths.

**Fix:**
- In `src/agent/hub/processor.py` → `_dispatch()` multi-agent path: after `run_workflow()` returns with `file_artifacts` non-empty, calls `clear_context()` immediately

---

### Gap 6 — search_paths stored in Dashboard message dict

**Problem:** The Dashboard (`src/agent/ui/personal_assistant/app.py`) ran agent executors directly but discarded `found_paths` from the result. The download button had no file to offer.

**Fix:**
- Single-skill path: after executor returns, extracts `_pa_artifacts.get("found_paths", [])`
- Stores as `{"role": "assistant", "content": _save_msg, "search_paths": _found_paths}` (key only added when non-empty)
- Dashboard UI can read `search_paths` to render the download button

---

## 🐛 2026-03-06 Session 5 — Bug Fixes: Timezone, Copy Destination, Undo + Audit History

### 1. Calendar Timezone Fix (`src/calendar/calendar_service.py`)

**Problem:** All calendar operations used `timezone.utc` and injected `"timeZone": "UTC"` into Google Calendar API calls — events created/read at the wrong time on machines in non-UTC zones.

**Fix:**
- Added `_local_tz()` helper that returns `datetime.now().astimezone().tzinfo` (the system local timezone)
- Replaced every `timezone.utc` reference in: `_rfc3339()`, `_today_start()`, `list_events()`, `get_events_for_date()`, `create_event()`, `update_event()`, `create_recurring_event()`, `find_free_slots()`
- Removed `"timeZone": "UTC"` from all event body payloads

---

### 2. Copy Destination Prompt Fix (`src/agent/ui/files_agent/orchestrator.py`)

**Problem:** When the user named a destination folder (e.g. "copy them to Downloads/qwerty"), the orchestrator passed `"no arguments"` to `collect_files_from_manifest`, discarding the destination. Rule #1 default path was hard-coded to `~/Downloads/OctaMind`.

**Fix:**
- Rule #1 default path changed from `home / 'Downloads' / 'OctaMind'` → `data_dir` (`<workspace>/data/`)
- Prompt instruction updated: if user names a folder, pass it as the `destination` argument instead of `"no arguments"`

---

### 3. Operation History Stack (`src/files/features/file_ops.py`)

**Problem:** `last_operation.json` stored only a single entry — every new operation overwrote the previous one, making multi-step undo impossible and erasing the audit trail.

**New architecture:**
- `_OP_HISTORY_FILE` → `<workspace>/data/operation_history.json` (JSON array, newest first)
- `_OP_HISTORY_TTL_DAYS = 30` — entries older than 30 days pruned automatically
- `_log_operation(op_type, destination, count)` — pushes to front; auto-prunes on every write
- `undo_last_file_operation() → dict` — finds most-recent non-undone entry, deletes destination folder, marks `undone: true` + `undone_at` timestamp; entry kept for audit
- `list_file_operations(days=30) → dict` — LLM-callable audit viewer (newest-first)

**Orchestrator:** `list_file_operations` registered in `_TOOL_DOCS`, `_get_tools()`, tool map, and prompt instruction.

---

### 4. Context Audit History (`src/agent/manifest/context_manifest.py`)

**Problem:** `write_context()` only kept the current state — no way to query what context was active 2 hours ago or debug a conversation.

**New architecture:**
- `_CONTEXT_HISTORY_FILE = _MANIFEST_DIR / "octa_context_history.jsonl"` — append-only JSONL audit
- `_PRUNE_STAMP_FILE` — prevents pruning more than once/day
- `_AUDIT_TTL_DAYS = 30` — history retained for 30 days
- Every `write_context()` appends a lightweight audit line (strips `resolved_entities` to keep size minimal)
- `_should_run_prune() → bool` — checks stamp file before pruning
- `prune_context_history(days=30)` — removes lines older than TTL
- `get_context_history(days=30) → list` — returns parsed entries for LLM/debug queries

---

## 🛠️ 2026-03-02 Session 4 — Calendar Year Bug Fixed

### Root-cause diagnosis for 3 failing commands

| Command | Root Cause | Fix |
|---|---|---|
| Laptop scan → write notepad → email | `list_laptop_structure` only wrote a file when `output_file` was explicitly passed; if LLM omits it, no `file_path` is set and email agent has nothing to attach | Auto-generate report path under `~/\_octamind\_reports/` |
| Search payslip → send for download | `search_by_name` only scans `~`; no `deliver_file` tool to mark a found file for download | Added `search_file_all_drives` (all drives) + `deliver_file` |
| "5 th March" calendar date | Fix is in code (previous session) but **server was not restarted** — old `_TEMPORAL_PATTERN` still in memory | Restart required |

---

### New tools: `src/files/features/file_ops.py`

| Tool | Purpose |
|---|---|
| **`deliver_file(path)`** | Explicitly marks a local file for download delivery — sets `file_path` in result so Telegram auto-responder sends it as a document and Dashboard shows a download button |
| **`write_pdf_report(path, title, content)`** | Generates a formatted PDF using `fpdf2`; gracefully falls back to annotated `.txt` if library not installed |
| **`write_excel_report(path, sheet_data, title="")`** | Generates an `.xlsx` workbook from dict of sheet→rows using `openpyxl` |
| **`organize_folder(directory, by, dry_run=True)`** | Groups files into sub-folders by `extension` / `date` / `name` / `size`; always dry-runs first to show the plan |
| **`list_laptop_structure` (fixed)** | Now **always** auto-saves a `.txt` report to `~/\_octamind\_reports/laptop_structure_YYYYMMDD_HHMMSS.txt` even when `output_file` is omitted — `file_path` is always set in the result |

### New tool: `src/files/features/search.py`

| Tool | Purpose |
|---|---|
| **`search_file_all_drives(query, extensions=None, limit=20)`** | Searches ALL Windows drives (`A:`–`Z:`) and the full home tree for a file by name/pattern. Returns `file_path` pointing to the first match — artifact collector picks it up for automatic Telegram/Dashboard delivery |

### Registered in `src/agent/ui/files_agent/orchestrator.py`
All 5 new tools added to `_TOOL_DOCS`, `_build_skill_context()` rules, and `_get_tools()` dict.

### Updated `src/agent/workflows/agent_registry.py`
`files` description extended to name the new tools explicitly.

---

## 🗺️ Tool Gap Analysis — What needs pre-defined tools vs ReAct

### Why pre-defined tools are essential

The ReAct loop makes one LLM call per step. A complex command like "scan laptop → write report → email it" takes ≥ 3 iterations at the sub-agent level, PLUS master orchestrator iterations = 6–10 LLM calls total. Pre-defined tools collapse multi-step workflows into a single deterministic function call with 0 extra LLM calls.

### Tools already pre-defined (complete list)

**Files Agent:**
`list_directory` · `search_by_name` · `search_by_extension` · `search_by_date` · `search_by_size` · `find_duplicates` · `find_empty_folders` · `zip_folder` · `zip_files` · `unzip_file` · `list_archive_contents` · `write_text_file` · `list_laptop_structure` · `search_file_all_drives` · `deliver_file` · `write_pdf_report` · `write_excel_report` · `organize_folder`

**Email Agent:**
`send_email` · `send_email_with_attachment` · `list_emails` · `get_inbox_count` · `get_todays_emails` · `delete_emails` · `summarize_email` · `generate_daily_digest` · `create_draft` · `list_drafts` · `send_draft` · `extract_action_items` · `get_all_pending_actions`

**Calendar Agent:** `list_events` · `quick_add_event` · `find_free_slots` · `delete_event`

**Drive Agent:** `search_drive` · `list_drive_folder` · `download_file` · `upload_file` · `create_folder` · `move_file` · `copy_file` · `trash_file` · `share_file`

**Telegram Agent:** `send_text_message` · `send_file` · `get_recent_messages`

**Stock Agent:** pre-defined ticker analysis tools

### Tools still missing — need to be added (in priority order)

| Priority | Tool | Why pre-defined | Notes |
|---|---|---|---|
| 🔴 High | `search_by_content(keyword, directory, extensions)` | Searching inside PDF/docx/xlsx text; ReAct can't do this in one step | Needs `pdfplumber`/`python-docx` |
| 🔴 High | `extract_text_from_file(path)` | Read content of PDF, docx, xlsx for summarisation or emailing | Needs `pdfplumber`/`python-docx` |
| 🔴 High | `get_disk_usage(path=None)` | Instant size-per-drive/folder summary without scanning every file | `shutil.disk_usage` — trivial, 0 deps |
| 🟡 Medium | `find_large_files(directory, min_mb, recursive=True, limit=20)` | "What's taking up space?" — deterministic; ReAct would multi-iterate | Already in `search_by_size` but needs a convenience wrapper |
| 🟡 Medium | `take_screenshot(output_path="")` | Screen capture for reporting; LLM can't do this at all | Needs `Pillow`+`pygetwindow` |
| 🟡 Medium | `organize_system(scope="downloads"\|"desktop"\|"all", by=..., dry_run=True)` | Whole-system organise across multiple well-known dirs | Calls `organize_folder` in a loop |
| 🟡 Medium | `compress_old_files(directory, older_than_days, output_archive)` | Archive files not touched in N days | Deterministic; saves manual iteration |
| 🟠 Low | `write_csv_report(path, rows, headers)` | CSV export without Excel dependency | Pure stdlib `csv` module |
| 🟠 Low | `convert_file(source, target_format)` | Convert docx→pdf, jpg→png etc. | Needs `LibreOffice` or `Pillow` |
| 🟠 Low | `send_whatsapp_file(contact, path)` | File delivery via WhatsApp | Needs WhatsApp agent extension |

---

## �🐛 2026-03-02 Session 2 — Issue Fixes (Calendar date, Laptop scan, Telegram parity)

### Fix 1 — Calendar books on wrong date ("8 th March" not recognised; Dashboard ignored date entirely)

**Root cause A — Telegram path (`processor.py`):** `_TEMPORAL_PATTERN` did not match ordinal dates that have a space before the suffix (`"8 th March"`). `search()` returned the first (shortest) match like `"march"` alone instead of the full `"8 th March"`.

**Root cause B — Dashboard path (`personal_assistant/app.py`):** The Dashboard bypasses `HubProcessor` entirely and had its own `_enrich_scheduling_followup` that contained **no temporal extraction at all** — it only scanned assistant messages and returned the bare command without any date context.

| Change | File | Detail |
|---|---|---|
| **`_TEMPORAL_PATTERN` expanded** | `src/agent/hub/processor.py` | Added pattern variant for spaced ordinals: `\d{1,2}\s+(?:st\|nd\|rd\|th)\s+...`; switched from `search()` to `findall()` + `max(key=len)` to get longest/most-specific match |
| **Dashboard enrichment synced** | `src/agent/ui/personal_assistant/app.py` | Replaced old no-op function with full version: `_TEMPORAL_PATTERN`, both-role scanning, findall+longest-match, appends `" on {date}"` to command |

---

### Fix 2 — Files scan covered only Documents folder (not entire laptop)

**Root cause:** No deterministic tool existed. The ReAct loop let the LLM autonomously decide what to scan; it chose only the home directory, then only Documents.

| Change | File | Detail |
|---|---|---|
| **`list_laptop_structure()` added** | `src/files/features/file_ops.py` | Deterministic Python function; no LLM decision. Discovers all Windows drives `A:`–`Z:` (or `/` on Unix), lists each drive root one level deep, then scans 7 well-known user dirs (Home, Downloads, Desktop, Documents, Pictures, Music, Videos). Returns structured dict + plain-text report; optionally writes report to `output_file`. |
| **Tool registered in orchestrator** | `src/agent/ui/files_agent/orchestrator.py` | Added to `_TOOL_DOCS`, `_build_skill_context()` rules, `_get_tools()` dict with explicit note: *"Use when user asks about ALL folders/files on entire laptop"* |
| **Agent description updated** | `src/agent/workflows/agent_registry.py` | `"files"` entry now mentions `list_laptop_structure` (full laptop scan, all drives + user directories) |

---

### Fix 3 — Telegram "can't parse entities" crash + Dashboard/Telegram parity

**Root cause A — Telegram delivery (`auto_responder.py`):** After `edit_message_text()` failed with an entity error, the outer `except Exception:` block called `send_text(chat_id, first_chunk)` with the default `parse_mode="Markdown"` — same text, guaranteed same failure. Error notification calls also used `parse_mode="Markdown"`.

**Root cause B — Service layer (`telegram_service.py`):** `send_text()` and `edit_message_text()` always included `"parse_mode"` in the request payload even when the caller passed `None`; Telegram treats `parse_mode: null` unpredictably.

| Change | File | Detail |
|---|---|---|
| **`_plain_text()` helper + fallback hardened** | `src/telegram/auto_responder.py` | Added `_plain_text(text)` that strips `*_\`[]\` Markdown characters + HTML-escapes `<>`; all fallback `send_text()` calls now use `_plain_text(chunk)` + `parse_mode=None`; error-notification edit also uses `parse_mode=None` |
| **`parse_mode=None` support in service** | `src/telegram/telegram_service.py` | Both `send_text()` and `edit_message_text()` now have `parse_mode: Optional[str]`; `parse_mode` is **only added to payload** when non-`None` and non-empty — ensures truly plain-text delivery |

---

## 🐛 2026-03-02 — Bug Fixes & LLM Logging Improvements

### Bug Fix 1 — Calendar books on "today" instead of the intended date

**Root cause:** `_enrich_scheduling_followup()` in `processor.py` converted a bare time reply (e.g. `"2 PM to 3 PM"`) into a scheduling command but did NOT carry forward any temporal context from the conversation (e.g. "tomorrow", "Monday", "March 3rd").  The calendar agent's `quick_add_event` therefore defaulted to today.

| Change | File | Detail |
|---|---|---|
| **`_TEMPORAL_PATTERN` regex** | `processor.py` | New module-level regex matching day names, "tomorrow/today/tonight", ordinal dates, ISO dates, and `MM/DD` patterns |
| **Temporal context injection** | `processor.py` — `_enrich_scheduling_followup()` | Scans **both** user and assistant recent messages for the first temporal reference; if found, appends `on <date>` to the enriched command so the calendar agent receives the correct date |

---

### Bug Fix 2/3 — DAG planner falls back to ReAct due to JSON code-fence wrapping

**Root cause:** LLM occasionally wraps the JSON plan in ` ```json … ``` ` Markdown code fences.  
**Status:** Already fixed in `skill_dag_engine.py` — `_strip_fences()` is called on the raw LLM output before `_parse_plan()` is invoked.  No further changes needed; confirmed present.

---

### Bug Fix 3b — ReAct loop summarises the same email repeatedly

**Root cause:** `_format_observation()` in `skill_react_engine.py` showed only the first 3 items of a list, truncated to 400 chars.  With 5 email IDs the LLM never saw IDs 3–5, causing it to re-process the second email four times until the iteration limit was reached.

| Change | File | Detail |
|---|---|---|
| **Full list display** | `skill_react_engine.py` — `_format_observation()` | List results now serialised as pretty JSON showing **all** items, capped at 1 500 chars total (not 3 items × 400 chars) |
| **Larger dict cap** | `skill_react_engine.py` — `_format_observation()` | Dict results rendered as `json.dumps(indent=2)`, capped at 1 200 chars (was 600) |

---

### Bug Fix 4 — Telegram "can't parse entities" crash on Windows paths

**Root cause:** Windows file paths (e.g. `C:\Users\...\folder_and_file_list.txt`) contain backslashes that break Telegram's Markdown v1 entity parser.  Both `sendMessage` and `editMessageText` returned HTTP 400.

| Change | File | Detail |
|---|---|---|
| **Auto-retry in `send_text()`** | `telegram_service.py` | If the Telegram API returns an error containing "can't parse entities", the function retries the same message **without** `parse_mode` (plain text), ensuring delivery even when the message contains path strings or other Markdown-unsafe content |
| **Auto-retry in `edit_message_text()`** | `telegram_service.py` | Same retry logic applied to the edit-message endpoint |

---

### Improvement — Human-Friendly Per-Request Workflow Summary Log

**Rationale:** LLM call counts and agent execution info were buried in DEBUG-level lines across multiple files, making it hard to see at a glance what happened for a given request.

| Change | File | Detail |
|---|---|---|
| **`_log_workflow_summary()`** | `processor.py` | New helper that emits a compact box-drawing summary block via `logger.info` at the end of every dispatch (chat, single-skill, multi-agent) |
| **`t_dispatch` timer** | `processor.py` — `_dispatch()` | Local `perf_counter` start added at top of `_dispatch()`; elapsed time passed to the summary block |
| **LLM call propagation** | `processor.py` — `_run_single_agent()` | `llm_calls` from the executor result dict is now included in the `acts` list returned to `_dispatch()` |
| **`_AGENT_ICONS` mapping** | `processor.py` | Dict mapping agent names to representative emojis for display in the summary block |

Sample log output:

```
╔════════════════════════════════════════════╗
║  🤖  WORKFLOW COMPLETE                     ║
╠════════════════════════════════════════════╣
║  Status: ✅ success   Time: 2.41 s         ║
║  Mode:   ⚙️ Skill DAG                     ║
╠════════════════════════════════════════════╣
║  Agents: 📁 files                          ║
╠════════════════════════════════════════════╣
║  LLM Calls: 2 total                        ║
╚════════════════════════════════════════════╝
```

---

## 🆕 2026-03-02 — Telegram UX Overhaul & Dashboard File Downloads

### Telegram — Real-Time Progress & Commands

| Feature | File | Detail |
|---|---|---|
| **Typing indicator** | `auto_responder.py` | `send_chat_action_api(chat_id, "typing")` called immediately on every inbound message before any LLM work starts |
| **`⏳ Thinking…` placeholder** | `auto_responder.py` | A placeholder message is sent first; it is edited in-place as processing advances via `on_progress` callback |
| **Progress editing** | `auto_responder.py` → `processor.py` | `HubProcessor.process()` now accepts `on_progress: Callable[[str], None]`; milestones ("🔍 Analyzing…", "💬 Thinking…", "⚙️ Running X…", "📋 Planning…") are broadcast back to edit the placeholder |
| **`/reset` command** | `auto_responder.py` | Clears `_SESSION_HISTORY[session_id]` and hub_conversations.json via `clear_session()` in `processor.py` |
| **`/agents` command** | `auto_responder.py` | Reads `AGENT_REGISTRY` and replies with a formatted list of available skills + descriptions |
| **Updated `/start` welcome** | `auto_responder.py` | Lists `/reset` and `/agents` commands in the welcome message |
| **Long-message splitting** | `auto_responder.py` | `_split_message()` breaks responses > 4000 chars at paragraph/line boundaries; first chunk edits placeholder, overflow chunks sent as new messages |
| **File artifact delivery** | `auto_responder.py` | After reply, any `result.file_artifacts` paths are sent via `send_document_file()` multipart upload; failure sends a graceful fallback note |

### Telegram — Service Layer

| Feature | File | Detail |
|---|---|---|
| **`send_document_file()`** | `telegram_service.py` | Multipart POST to `sendDocument` for locally-generated files (e.g. PDFs, CSVs); accepts `chat_id`, `file_path`, optional `caption` |

### HubProcessor — Channel-Agnostic Improvements

| Feature | File | Detail |
|---|---|---|
| **`on_progress` callback** | `processor.py` | `HubProcessor.process()` and `_dispatch()` now accept an optional `on_progress` callable; called at 3–4 key milestones during routing and execution |
| **`file_artifacts` in `HubResponse`** | `processor.py` | New `file_artifacts: List[str]` field on `HubResponse` dataclass; populated from executor `artifacts_out["file_path"]` or step result `"file_path"` |
| **Scheduling enrichment in Telegram path** | `processor.py` | `_enrich_scheduling_followup()` (previously only in `app.py`) now called inside `_dispatch()` — bare time replies like "2 PM to 3 PM" are enriched with scheduling context on ALL channels, not just Dashboard |
| **`clear_session(session_id)`** | `processor.py` | Wipes `_SESSION_HISTORY[session_id]` and removes matching conversation from `hub_conversations.json` |

### Dashboard — File Download Button

| Feature | File | Detail |
|---|---|---|
| **Download button (single-skill)** | `app.py` | After single-skill executor runs, checks `result.get("file_path")`; if a local file is present, renders `st.download_button` with correct MIME type directly in the chat |
| **Download button (multi-skill workflow)** | `app.py` | Iterates `run_result["steps"]` for any `"file_path"` values; renders one `st.download_button` per artifact produced by the workflow |

---

## ✅ Fully Implemented


### Core Infrastructure
- [x] LLM client (`GitHubModelsLLM`) wrapping OpenAI SDK against GitHub Models endpoint
- [x] ReAct loop (`reason_and_act`) � up to 6 iterations, 45s timeout, `max_tokens=3000`
- [x] Intent classification (`classify_intent`) for multi-agent routing
- [x] Agent process isolation � each agent runs as a separate `subprocess.Popen`
- [x] Per-agent memory system (working, episodic, semantic, personality, habits, consciousness) � **Personal Assistants only; Skills are stateless executors with no memory**
- [x] Memory consolidation, decay, and archiving
- [x] **Global consolidation background thread** � starts at app launch, runs every 24 h across ALL Personal Assistants (including inactive ones)
- [x] Log files written to project root; truncated on every `start.py` launch
- [x] 429 rate-limit error surfaced to user with wait-time estimate
- [x] Single-agent shortcut in Personal Assistant Hub (bypasses planner for Drive-only or Email-only commands)
- [x] **Hybrid Planner + DAG architecture** (`dag_planner.py`) � replaces multi-turn master ReAct with a single planning call + deterministic execution; topological sort resolves step order (0 LLM calls); sub-agents still run focused ReAct loops for tool execution
- [x] **Keyword pre-filter** (`router.py` ? `keyword_pre_filter()`) � avoids LLM router call entirely for obvious agent-free messages
- [x] **`failed_step_ids` upstream failure propagation** � downstream DAG steps are skipped (not run with broken placeholder values) when an upstream step fails
- [x] **Python-bool JSON normalization** (`skill_react_engine._parse_json`) � `True`/`False`/`None` ? `true`/`false`/`null` before parsing; prevents cascading `unknown action ''` failures
- [x] **Tilde path expansion** (`dag_planner._resolve_instruction`) � `~/foo` ? `C:\Users\malus\foo` to prevent LLM from guessing wrong OS paths
- [x] **Total LLM call count logged** per workflow � `Total LLM calls: N (router=1 planner=1 sub_agents=N)` at workflow completion

### Drive Agent � 37 Tools
All tools described in TOOL_REFERENCE.md are implemented and wired to the Google Drive API.

| Category | Tools | Status |
|----------|-------|--------|
| Core file ops | list_files, search_files, get_file_info, upload_file, download_file, create_folder, move_file, copy_file, trash_file, restore_file, star_file, get_storage_quota | ? |
| Sharing | share_file, list_permissions, remove_permission, update_permission, make_public, remove_public | ? |
| Smart features | summarize_file, summarize_folder, find_duplicates, trash_duplicates, suggest_organization, auto_organize, bulk_rename, list_versions, get_version_info, restore_version, delete_old_versions | ? |
| Analytics | storage_breakdown, list_large_files, list_old_files, list_recently_modified, find_orphaned_files, sharing_report, generate_drive_report, get_usage_insights | ? |

### Email Agent � 47 Tools
All tools described in TOOL_REFERENCE.md are implemented and wired to the Gmail API.  
**Setup:** Full guide at `documentation/EMAIL_SETUP.md`.

| Category | Tools | Status |
|----------|-------|--------|
| Reading | get_todays_messages, list_message, count_messages, detect_urgent_emails, detect_newsletters, check_unanswered_emails | ? |
| Sending & drafts | send_message, create_draft, list_drafts, send_draft, delete_draft, quick_reply, generate_reply_suggestions, schedule_email, list_scheduled_emails, cancel_scheduled_email, update_scheduled_email | ? |
| Attachments | list_attachments, download_attachment, search_emails_with_attachments | ? |
| Organisation | auto_categorize_email, apply_smart_labels, create_category_rules, auto_prioritize | ? |
| Action items | extract_action_items, get_all_pending_actions, mark_action_complete, get_saved_tasks, mark_for_followup, get_pending_followups, send_followup_reminder, mark_followup_done, dismiss_followup | ? |
| Calendar | extract_calendar_events, suggest_calendar_entry, export_to_calendar | ? |
| Contacts & analytics | get_frequent_contacts, get_contact_summary, suggest_vip_contacts, export_contacts, extract_unsubscribe_link, calculate_response_time, get_email_stats, get_productivity_insights, visualize_patterns, generate_weekly_report | ? |

### WhatsApp Agent � 36 Tools
All tools described in WHATSAPP_SETUP.md are implemented and wired to the Meta WhatsApp Cloud API.

| Category | Tools | Status |
|----------|-------|--------|
| Core messaging | send_message, send_media, send_template, reply_to_message, get_messages, get_unread_messages, mark_as_read | ? |
| Contacts | list_contacts, get_contact_info, get_frequent_contacts, set_contact_name | ? |
| Groups | list_groups, get_group_info, get_group_messages | ? |
| Search & retrieval | search_messages, get_conversation, get_messages_by_date, get_media_messages | ? |
| AI smart features | summarize_conversation, extract_action_items, draft_message, generate_reply, detect_urgent_messages, extract_key_info, translate_message, sentiment_analysis | ? |
| Scheduling | schedule_message, list_scheduled_messages, cancel_scheduled_message, set_auto_reply, get_auto_reply_config | ? |
| Analytics | get_message_stats, get_response_time, get_activity_report, get_top_senders | ? |
| Cross-agent | forward_to_email, share_drive_file | ? |

**Webhook server:** FastAPI + uvicorn on port 9001; inbound messages stored in `data/whatsapp_messages.json`.  
**Credentials:** Configured in `config/settings.json["whatsapp"]` � `access_token` + `phone_number_id` required.  
**Setup:** Full guide at `documentation/WHATSAPP_SETUP.md`.

### Telegram Agent � 38 Tools
All tools described in TOOL_REFERENCE.md are implemented and wired to the Telegram Bot API via long-polling.

| Category | Tools | Status |
|----------|-------|--------|
| Core messaging | send_message, send_media, reply_to_message, forward_message, edit_message, delete_message, get_messages, get_unread_messages, get_chat_history, mark_as_read, send_chat_action | ? |
| Chats | list_chats, get_chat_info, get_chat_member_count, pin_message, unpin_message, leave_chat | ? |
| Media | send_photo, send_document, send_audio, get_media_messages | ? |
| Search & retrieval | search_messages, get_messages_by_date, get_pinned_messages, get_message_stats | ? |
| Polls | send_poll, stop_poll | ? |
| Scheduling | schedule_message, list_scheduled_messages, cancel_scheduled_message | ? |
| AI smart features | summarize_chat, detect_urgent_messages, draft_message, translate_message, sentiment_analysis, extract_action_items | ? |
| Cross-agent | forward_to_email, share_drive_file | ? |

**Polling:** Background thread runs `getUpdates` long-poll loop; messages stored in `data/telegram_messages.json`.  
**Credentials:** `TELEGRAM_BOT_TOKEN` env var or `config/settings.json["telegram"]["bot_token"]` � get token from **@BotFather**.  
**Composite IDs:** All stored messages are addressed as `"chat_id:message_id"` (e.g. `"1001:5"`).  
**Auto-responder (2026-03-02):** `auto_responder.py` rewritten — typing indicator, `⏳ Thinking…` placeholder edited in real-time, `/reset` (clear history), `/agents` (list skills), long-message splitting at 4000 chars, file-artifact delivery via `send_document_file()` multipart upload.

### Files Agent � 48 Tools
All tools use Python stdlib only (`pathlib`, `shutil`, `zipfile`, `hashlib`, `os`). No credentials required for 43/48 tools.

| Category | Tools | Status |
|----------|-------|--------|
| File operations | list_directory, get_file_info, copy_file, move_file, delete_file, create_folder, rename_file, open_file | ? |
| Search | search_by_name, search_by_extension, search_by_date, search_by_size, find_duplicates, find_empty_folders | ? |
| Archives | zip_files, zip_folder, unzip_file, list_archive_contents, get_archive_info | ? |
| Organiser | bulk_rename, organize_by_type, organize_by_date, move_files_matching, delete_files_matching, clean_empty_folders, deduplicate_files | ? |
| Disk | list_drives, get_disk_usage, get_directory_size, find_large_files, get_recently_modified | ? |
| Reader | read_text_file, get_file_stats, preview_csv, read_json_file, tail_log, calculate_file_hash | ? |
| AI smart features | summarize_file, analyze_folder, suggest_organization, generate_rename_suggestions, find_related_files, describe_file | ? |
| Cross-agent | zip_and_email, zip_and_upload_to_drive, email_file, upload_file_to_drive, send_file_via_whatsapp | ? |

**Credentials:** None required for core 43 tools. Gmail/Drive OAuth needed for 5 cross-agent tools.  
**Safety:** `_is_safe_path()` blocks ops on system directories; destructive ops default to `dry_run=True`.  
**Setup:** Full guide at `documentation/FILES_SETUP.md`.

### Calendar Agent (Google Calendar) � 19 Tools
All tools implemented and wired to Google Calendar API v3.

| Category | Tools | Status |
|----------|-------|--------|
| View & search | get_todays_events, get_tomorrows_events, get_upcoming_events, get_events_for_date, search_events, get_event, list_events | ? |
| Agenda | get_daily_agenda, get_weekly_agenda | ? |
| Create & modify | create_event, quick_add_event, update_event, delete_event, create_recurring_event | ? |
| Smart | find_free_slots, find_conflicts, set_reminder | ? |
| RSVP & management | accept_invite, decline_invite, list_calendars | ? |

**Auth:** `config/calendar_token.json` � generated on first OAuth flow; silently refreshed thereafter.  
**Preflight:** `_get_client()` raises `PermissionError` if not authorised � surfaces clean `auth_error` to user.  
**Setup:** See `documentation/setup/CALENDAR_SETUP.md`.

### Scheduler / Smart Calendar Agent � 8 Tools
New intelligence layer on top of the Calendar Agent. Uses same auth token.

| Category | Tools | Status |
|----------|-------|--------|
| Slot finding | suggest_meeting_time, find_mutual_availability | ? |
| Focus protection | protect_deep_work_block, schedule_recurring_focus_time | ? |
| Analysis | optimize_day_schedule, get_scheduling_insights | ? |
| Conflict resolution | smart_reschedule_conflicts | ? |
| Time blocks | create_time_block | ? |

**Registry key:** `scheduler`  
**Auth:** Reuses `config/calendar_token.json` � no additional OAuth setup.  
**Key difference from Calendar Agent:** Never just CRUD � always reasons and proposes optimal solutions.

### File Organizer Agent � 10 Tools
Approval-driven organisation with archival policies. No credentials required.

| Category | Tools | Status |
|----------|-------|--------|
| Plan workflow | scan_and_propose, preview_plan, apply_plan, discard_plan, list_plans | ? |
| Archival | archive_old_files, set_archival_policy, show_archival_policies, run_archival_policies | ? |
| App data | cleanup_app_data | ? |

**Registry key:** `file_organizer`  
**Data stores:** `data/organizer_pending_plans.json`, `data/organizer_archival_policies.json`  
**Safety:** Never calls `apply_plan` without explicit user confirmation; all destructive ops default to `dry_run=True`.

### Habit & Health Tracker Agent � 9 Tools
Completely new agent. No overlap with Calendar or Files agents.

| Category | Tools | Status |
|----------|-------|--------|
| Habit management | add_habit, delete_habit, get_habits | ? |
| Logging | log_completion, daily_checkin | ? |
| Progress tracking | get_streak, get_weekly_report, get_habit_analytics | ? |
| Calendar integration | schedule_habit_on_calendar | ? |

**Registry key:** `habit_tracker`  
**Service:** `src/habit_tracker/habit_service.py`  
**Data stores:** `data/habits.json` (definitions), `data/habit_logs.json` (daily logs)  
**No credentials required** for all 8 core tools; Calendar integration requires Calendar auth.

### Browser Agent � 10 Tools
HTTP-only web browsing. No credentials, no API keys, no headless browser required.

| Category | Tools | Status |
|----------|-------|--------|
| Page access | browse_url, extract_text, summarize_page | ? |
| Search | search_web | ? |
| Inspection | get_page_links, get_page_title, get_page_metadata, find_on_page | ? |
| Data extraction | extract_structured_data | ? |
| Downloads | download_file_from_url | ? |

**Registry key:** `browser`  
**Service:** `src/browser/browser_service.py`  
**Backend:** `urllib.request` (stdlib) + optional `beautifulsoup4` + `requests`  
**No credentials required.** No JavaScript execution � public HTTP pages only.

### Stock Market Analysis Agent � 10 Tools
Read-only analysis. No buy/sell, no brokerage integration.

| Category | Tools | Status |
|----------|-------|--------|
| Market data | get_quote, get_historical_data, market_overview | ? |
| Technical analysis | technical_analysis (RSI, MACD, Bollinger, SMA), pattern_detection | ? |
| Risk analysis | risk_score (volatility, Beta, VaR 95%, Sharpe) | ? |
| Portfolio | portfolio_analysis, portfolio_suggestions | ? |
| Intelligence | sentiment_analysis, compare_stocks | ? |

**Registry key:** `stock_market`  
**Service:** `src/stock_market/stock_service.py`  
**Data source:** `yfinance` (Yahoo Finance public API) � free, no API key required.  
**No credentials required.** All indicators computed in pure Python (no ML dependencies).  
**PDF Report Generation:** `generate_full_report(symbol)` runs all 10 analyses and builds a multi-page A4 PDF with cover page, Analyst Quick Snapshot, 7 analysis sections, charts, and risk tables. Output saved to `data/exports/`.

### LinkedIn Agent � 17 Tools
Fully implemented service + LLM orchestrator. Registered in agent_registry, agent_manager, and dashboard skill cards.

| Category | Tools | Status |
|----------|-------|--------|
| Posting | create_text_post, create_image_post, create_video_post, create_article_post, delete_post, list_published_posts | ? |
| AI generation | generate_ai_post_content (text via LLM), generate_ai_image (images via DALL�E 3) | ? |
| Scheduling | schedule_post, list_scheduled_posts, cancel_scheduled_post | ? |
| Analytics | get_post_analytics, get_page_analytics, get_org_followers | ? |
| Auth / profile | get_profile, get_access_token_url, exchange_code_for_token | ? |

**Registry key:** `linkedin`  
**Service:** `src/linkedin/linkedin_service.py`  
**Orchestrator:** `src/agent/ui/linkedin_agent/orchestrator.py`  
**UI:** `src/agent/ui/linkedin_agent/app.py` (standalone Streamlit UI)  
**Setup Guide:** `documentation/setup/LINKEDIN_SETUP.md`  
**Credentials:** LinkedIn OAuth access_token in `config/settings.json["linkedin"]["access_token"]` � required for all posting/analytics tools.  
**AI Text Generation:** Uses GitHub Models LLM (same as all other agents).  
**AI Image Generation:** Uses OpenAI DALL�E 3 � requires a **separate paid OpenAI API key** (`OPENAI_API_KEY` env var or `settings.json["openai_api_key"]`). NOT provided by GitHub Models.

### Personal Assistant Hub
- [x] Drive-only command routing ? Drive Agent direct
- [x] Email-only command routing ? Email Agent direct
- [x] NL-based cross-agent workflow planner (`plan_nl_workflow`) for combined commands
- [x] Agent capability registry (`agent_registry.py`) � ~10 tokens per agent, scales to N agents; **10 agents registered**: drive, email, whatsapp, files, calendar, scheduler, file_organizer, habit_tracker, browser, stock_market
- [x] Planning context: ~80 tokens for 8 agents (vs ~8,000 tokens in old flat-tool-list design)
- [x] Natural-language step format: orchestrator issues plain-English instructions, no tool signatures
- [x] Sequential multi-agent execution via `nl_step_runner.py` � each sub-agent runs its own full ReAct loop
- [x] Artifact handoff between agents (`artifacts_out` dict + `{output_key.field}` token substitution)
- [x] Drive ? Email file path handoff: `artifacts_out["file_path"]` populated from `download_file` result
- [x] Composed final response from all agent results
- [x] **Hard-coded `_collective_memory_` personality** � warm, proactive, protective personal-assistant character baked in as prose; immune to personality trait slider edits
- [x] **`collective_consciousness.md`** � synthesised from every sub-agent�s `consciousness.md` each consolidation cycle; gives the PA a cross-domain mental model of the user
- [x] **WhatsApp agent** registered in `agent_registry.py` � available for PA workflows
- [x] **Telegram agent** registered in `agent_registry.py` � available for PA workflows
- [x] **Files agent** registered in `agent_registry.py` � available for PA workflows
- [x] **Calendar agent** registered in `agent_registry.py` � Google Calendar CRUD via PA
- [x] **Scheduler agent** registered in `agent_registry.py` � intelligent scheduling, focus blocks, insights
- [x] **File Organizer agent** registered in `agent_registry.py` � approval-workflow file organization
- [x] **Habit Tracker agent** registered in `agent_registry.py` � habit tracking, streaks, weekly reports
- [x] **Browser agent** registered in `agent_registry.py` � web browsing, search, text extraction, downloads
- [x] **LinkedIn agent** registered in `agent_registry.py` � available for PA workflows (text posts, AI-generated content, scheduling, analytics)- [x] **`on_progress` callback in `HubProcessor.process()`** (2026-03-02) — callers can pass a `Callable[[str], None]`; fired at key milestones so Telegram (and future channels) can show live progress
- [x] **`file_artifacts` in `HubResponse`** (2026-03-02) — `List[str]` of local file paths produced by skill executors; populated from `artifacts_out["file_path"]` or step `"file_path"` field
- [x] **Scheduling enrichment in Telegram channel** (2026-03-02) — `_enrich_scheduling_followup()` now called in `HubProcessor._dispatch()`, not only in dashboard `app.py`
- [x] **`clear_session(session_id)`** (2026-03-02) — helper to wipe per-session history from memory + `hub_conversations.json`; used by `/reset` command
- [x] **Dashboard download button** (2026-03-02) — `st.download_button` rendered after any single-skill or multi-skill result that includes a `file_path` artifact
### UI
- [x] Streamlit chat UI for Drive Agent (port 8502)
- [x] Streamlit chat UI for Email Agent (port 8503)
- [x] Streamlit chat UI for WhatsApp Agent (WhatsApp green theme #25d366)
- [x] Streamlit chat UI for Telegram Agent (blue-grey theme)
- [x] Streamlit chat UI for Files Agent (blue theme #4a90d9 � no credentials required)
- [x] Streamlit chat UI for Multi-Agent / Personal Assistant (port 8504)
- [x] Agent Hub management UI (port 8501)
- [x] `start.py` / `stop.py` for launching/stopping all UIs
- [x] Per-agent personality trait sliders in Agent Hub

---

## ?? Partial / Known Limitations

### `create_video_post` (LinkedIn)
- Only **uploads an existing local video file** to LinkedIn � it does NOT generate or create a video.
- A request like "create a video about X and post it" will fail � Octa Bot cannot generate video content.
- Workaround: Record/create the video externally, then ask "post this video: /path/to/video.mp4".

### `generate_ai_image` (LinkedIn)
- Requires a **paid OpenAI API key** with DALL�E 3 access (`OPENAI_API_KEY`).
- Does NOT work with the GitHub Models token � DALL�E 3 is not available via GitHub Models.
- Configure `settings.json["linkedin"]["image_gen_backend"] = "openai"` and set `OPENAI_API_KEY`.

### `reply_to_message`
- Listed in tool description but **not wired in `_dispatch`** in `email_agent/orchestrator.py`.
- The LLM sees it as available, but calling it will return `Unknown tool: reply_to_message`.
- Workaround: Use `send_message` with a subject like `"Re: [original subject]"`.

### `download_file` (Drive)
- Downloads to a local path on the machine running the Streamlit server.
- When running from `start.exe`, the download location is relative to the executable directory.
- No in-UI file picker for destination � path must be specified in natural language or defaults to the project root.

### `download_attachment` (Email)
- Same constraint as Drive download � saves to server-side disk.
- No browser download prompt.

### `schedule_email`
- Scheduling is software-implemented (stored JSON, checked by a background scheduler).
- It is **not** a native Gmail scheduled send � it relies on the Octa Bot process being running at send time.
- If the application is closed before the scheduled time, the email will not be sent.

### `export_to_calendar`
- Google Calendar write access requires additional OAuth scope (`calendar.events`).
- The `.ics` file export works unconditionally.
- Calendar write is implemented but depends on the token having the right scope � if not authorised, only `.ics` is saved.

### `apply_smart_labels` / `create_category_rules`
- Creates Gmail labels in the user's account.
- Label creation is irreversible via this tool � there is no `delete_label` tool.

### `bulk_rename` / `auto_organize` / `trash_duplicates` / `delete_old_versions`
- All default to `dry_run=True`. The agent will show a preview.
- To apply changes, the user must explicitly confirm or re-request with "yes, proceed" / "do it for real."

### `visualize_patterns`
- Returns chart-ready JSON data, not an actual rendered chart.
- The Streamlit UI does not currently render this data as a visual � it displays as formatted text.

### Agent Hub Automation (`auto_run`)
- The `auto_run` config field exists in `agents.json` but the automation scheduler is **not actively running** in the current build.
- Manual commands via chat always work; background auto-run does not trigger automatically.

---

## ? Not Implemented

| Feature | Notes |
|---------|-------|
| Google Docs / Sheets editing | Drive agent can read/summarise but cannot write to Docs or Sheets content |
| Gmail label deletion | No `delete_label` tool exists |
| Multi-step email thread view | `list_message` returns individual messages, not full thread chains |
| Bulk email deletion/archiving | No `bulk_delete` or `bulk_archive` tool |
| Push notifications | No real-time inbox monitoring; all reads are on-demand |
| Voice input | Text-only chat interface |
| File preview in UI | Files are downloaded to disk; no in-browser preview |
| Cross-session memory search | Memory is loaded per-agent at startup; no semantic search across memory files |
| Drive ? Sheets data import | Cannot populate a Sheet from structured data |
| OAuth token refresh UI | Run `python setup_google_auth.py` from the project root to re-authorise Gmail and Drive |

---

## Known Bugs / Edge Cases

| Issue | Impact | Status |
|-------|--------|--------|
| GitHub Models token expired / bad credentials | LLM calls return 401 � all AI text generation fails (LLM-classified sentiment uses keyword fallback, posts fail to generate) | Refresh token: update `config/credentials.json` with a new GitHub Models API token |
| GitHub Models rate limit (150 req/day, 15 req/min) | All agents fail with 429 after limit | Surfaced to user with wait-time; no workaround except waiting or switching model |
| `max_tokens=3000` vs context window | Very long tool results may exceed context; LLM truncates | No chunking implemented |
| Memory consolidation agent | ~~Consolidation task runs on startup but output is not surfaced in UI~~ **FIXED** � `ConsolidationRunner` daemon thread boots with the dashboard and runs all agents every 24 h | Memory improves continuously even for idle agents |
| Log file locked on Windows | Logs in `src/` may stay locked if processes don't exit cleanly | Truncated on next `start.py` |

---

## LLM Configuration

| Setting | Value |
|---------|-------|
| Provider | GitHub Models (free tier) |
| Model | `gpt-4o` (via GitHub Models endpoint) |
| Rate limit | 15 requests/minute, 150 requests/day |
| `max_tokens` � ReAct loop | 3000 per iteration |
| `max_tokens` � compose response | 3000 |
| `max_tokens` � classify intent | 5 |
| ReAct max iterations | 6 |
| ReAct timeout | 45 seconds |
| Temperature � compose | 0.4 |

---

## API Scopes Required

### Google Drive
- `https://www.googleapis.com/auth/drive` (full Drive access)

### Gmail
- `https://www.googleapis.com/auth/gmail.modify` (read + send + labels)
- `https://www.googleapis.com/auth/gmail.send`

### Google Calendar (optional)
- `https://www.googleapis.com/auth/calendar.events` � required for `export_to_calendar` write path
- Without this scope, only `.ics` file export works

---

## File Structure Reference

```
src/
  agent/
    llm/
      llm_parser.py          # GitHubModelsLLM � all LLM calls go through here
    memory/                  # Memory system (load/save/consolidate)
      agent_memory.py        # AgentMemory � 6-layer per-agent storage + MULTI_AGENT_ID constant
      memory_consolidator.py # MemoryConsolidator � pattern extraction, habit detection, consciousness update
      consolidation_runner.py # ConsolidationRunner � daemon thread, runs all agents every 24 h
      collective_memory.py   # get_collective_context() � episodic snapshot for multi-agent LLM context
    ui/
      drive_agent/
        app.py               # Streamlit UI + _compose_drive_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 37 Drive tools + artifacts_out
      email_agent/
        app.py               # Streamlit UI + _compose_email_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 47 Gmail tools + artifacts_out
      whatsapp_agent/
        app.py               # Streamlit UI + _compose_whatsapp_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 36 WhatsApp tools
      telegram_agent/
        app.py               # Streamlit UI + _compose_telegram_response()
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 38 Telegram tools
      files_agent/
        app.py               # Streamlit UI
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 48 Files tools
      calendar_agent/
        orchestrator.py      # execute_with_llm_orchestration() + _dispatch() + 19 Calendar tools
      scheduler_agent/
        orchestrator.py      # execute_with_llm_orchestration() + 8 smart scheduling tools
      file_organizer_agent/
        orchestrator.py      # execute_with_llm_orchestration() + 10 approval-workflow tools
      habit_agent/
        orchestrator.py      # execute_with_llm_orchestration() + 9 habit tracking tools
      multi_agent/
        app.py               # Streamlit UI + routing + _compose_final_response() � Personal Assistant Chat UI
      dashboard/
        app.py               # Agent Hub Streamlit entry � boots ConsolidationRunner + PA memory on startup
    workflows/
      agent_registry.py      # AGENT_REGISTRY dict � one entry per agent (~10 tokens each)
      master_orchestrator.py # _build_planning_prompt() + plan_nl_workflow() + run_workflow()
      nl_step_runner.py      # run_nl_step() � resolves tokens, calls sub-agent, extracts artifacts
      workflow_context.py    # NLWorkflowStep, NLWorkflowPlan, WorkflowContext dataclasses
      router.py              # detect_agents_needed() � LLM-based DRIVE/EMAIL/BOTH/NEITHER
  drive/                     # Raw Google Drive API calls
  email/                     # Raw Gmail API calls
  whatsapp/                  # Meta WhatsApp Cloud API calls + webhook server (port 9001)
  telegram/                  # Telegram Bot API calls + long-poll background thread
  files/                     # Local filesystem operations (stdlib only)
agents.json                  # Agent registry (ids, types, config)
start.py                     # Launch all Streamlit UIs as subprocesses
stop.py                      # Kill all running agent processes
memory/<pa_id>/           # Per-PA 6-layer memory (working, episodic, semantic, personality, habits, consciousness)
                             # Only Personal Assistants have memory � Skills are stateless executors
                             # Active PA folders: pa_<id>/, _collective_memory_/
```
