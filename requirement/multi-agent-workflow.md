# Multi-Agent Workflow — Requirements & Implementation Plan

## What Is This?

Right now, OctaMind has separate agents — Email Agent and Drive Agent — each with their own chat window. They work in isolation. This feature will let agents **work together** to complete tasks that span more than one service, all from a single command.

**Example:**
> "Download the Q1 Budget from Drive and email it to boss@company.com"

Today, users have to:
1. Open Drive Agent → download the file
2. Switch to Email Agent → attach the file → send it

With this feature, one command does all of it automatically.

---

## Why This Matters

This is a major differentiator for OctaMind. No mainstream AI assistant today handles cross-service workflows this naturally. It turns OctaMind from a collection of separate tools into one unified AI operating system.

---

## Chosen Approach: Dedicated Multi-Agent Chat Window

### Why This Approach

A dedicated chat window for multi-agent work is the right design because it keeps things explicit and clean:
- **No confusion** — the user always knows what mode they are in
- **Individual agent chats stay pure** — Email chat only does email, Drive chat only does Drive
- **Intentional entry point** — the user consciously chooses to run a cross-agent workflow
- **Scales naturally** — adding Calendar, Slack, or any future agent just means hooking it into this one window
- **Easier to debug** — if something goes wrong, the user knows exactly where to look

### How It Works (User's View)

```
Dashboard
├── Email Agent card   [Start] → Opens Email chat   (single agent, same as today)
├── Drive Agent card   [Start] → Opens Drive chat   (single agent, same as today)
│
└── [⚡ Multi-Agent] button   → Opens Multi-Agent Chat window  ← NEW
```

**Single agent scenario (unchanged):**
User starts only the Email Agent → opens Email chat → types email commands → works exactly as today.

**Multi-agent scenario:**
User starts Email Agent + Drive Agent → a **"⚡ Multi-Agent"** button appears on the dashboard → user clicks it → a new dedicated chat window opens → user types their cross-agent command there.

> "Download the Q1 Budget from Drive and email it to cfo@company.com"

The multi-agent window:
1. Detects this needs Drive + Email
2. Confirms both agents are running (starts them silently if not)
3. Plans the steps: Search → Download → Email
4. Runs each step, showing live progress
5. Reports back in the same window:

```
🔄 Running multi-agent workflow...

  ✅ Step 1 — Found "Q1 Budget 2026.xlsx" in Google Drive
  ✅ Step 2 — Downloaded file (1.2 MB)
  ✅ Step 3 — Sent email to cfo@company.com with attachment

✨ Done! Q1 Budget 2026.xlsx was downloaded from Drive and emailed to cfo@company.com.
```

The user never had to switch windows or do any manual steps.

---

## Full Technical Design

### Component Overview

```
Dashboard detects 2+ agents running
         │
         ▼
┌──────────────────────────┐
│  Multi-Agent Chat Window  │  ← New Streamlit page (app.py)
└──────────────────────────┘
         │
         ▼
┌──────────────────────┐
│  Multi-Agent Router   │  ← New component: detects which agents are needed
└──────────────────────┘
         │
         ▼
┌──────────────────────────┐
│   Master Orchestrator     │  ← New component: plans + runs the workflow
└──────────────────────────┘
         │              │
         ▼              ▼
  ┌──────────┐    ┌──────────┐
  │  Drive   │    │  Email   │  ← Existing orchestrators, called as tools
  │  Tools   │    │  Tools   │    Individual agent chats untouched
  └──────────┘    └──────────┘
```

---

### New Files to Create

```
src/
└── agent/
    ├── workflows/
    │   ├── __init__.py
    │   ├── router.py               ← Detects which agents a command needs
    │   ├── master_orchestrator.py  ← Plans and runs multi-step tasks
    │   ├── step_runner.py          ← Executes one step, passes result to next
    │   ├── file_bridge.py          ← Handles file passing between agents
    │   └── workflow_context.py     ← Holds state during a multi-step workflow
    └── ui/
        └── multi_agent/
            ├── __init__.py
            ├── app.py              ← New dedicated Streamlit chat page
            └── helpers.py          ← Detect running agents, button visibility
```

**Dashboard change (one small addition):**
`src/agent/ui/dashboard/app.py` gets a new button that only appears when 2+ agents are running:
```python
running = get_running_agents()
if len(running) >= 2:
    if st.button("⚡ Multi-Agent", type="primary"):
        launch_multi_agent_window()
```

**Existing Email and Drive agent files: zero changes.**

---

### Component Details

#### 1. `router.py` — Multi-Agent Intent Detector

**Job:** Look at the user's command and decide — is this a single-agent task or does it need multiple agents?

**How it works:**
- Uses keyword pattern matching as a fast first check
  - Drive keywords: `drive`, `file`, `download`, `folder`, `document`, `spreadsheet`
  - Email keywords: `email`, `send`, `mail`, `inbox`, `attach`
- If both sets appear in one command → multi-agent
- Falls back to LLM for ambiguous cases

**Key function:**
```python
def detect_workflow(command: str) -> WorkflowPlan | None:
    """
    Returns a WorkflowPlan if multiple agents are needed.
    Returns None if it's a single-agent command (handled normally).
    """
```

**Example detections:**
| Command                                                               | Result                      |
| --------------------------------------------------------------------- | --------------------------- |
| `List my unread emails`                                               | None — single agent (Email) |
| `Search for budget file in Drive`                                     | None — single agent (Drive) |
| `Download budget from Drive and email it to boss`                     | WorkflowPlan — multi-agent  |
| `Find the contract in Drive, summarize it, and send summary to Alice` | WorkflowPlan — multi-agent  |

---

#### 2. `master_orchestrator.py` — Planner and Runner

**Job:** Take a multi-agent command, break it into ordered steps, run each step, and pass results between them.

**Planning phase:**
- Sends command to LLM with this instruction:
  > "Break this task into ordered steps. For each step, say which agent handles it and what input it needs."
- LLM returns a structured plan

**Example plan for** `"Download Q1 Budget from Drive and email it to cfo@company.com"`:
```
Step 1: drive_agent
  action: search_files
  input: "Q1 Budget"
  output_key: file_id

Step 2: drive_agent
  action: download_file
  input: {file_id from Step 1}
  output_key: file_path

Step 3: email_agent
  action: send_email
  input: {
    to: "cfo@company.com",
    subject: "Q1 Budget",
    attachment: {file_path from Step 2}
  }
```

**Execution phase:**
- Runs steps one by one
- Each step's output is stored in `WorkflowContext`
- Next step reads what it needs from context
- If a step fails → stops and reports what went wrong clearly

---

#### 3. `workflow_context.py` — State During a Workflow

**Job:** Hold all the data produced during a workflow run so steps can share it.

```python
class WorkflowContext:
    def __init__(self):
        self.results = {}          # step outputs stored here
        self.temp_files = []       # temp files to clean up after
        self.agent_id = ""
        self.started_at = datetime.now()

    def set(self, key: str, value: any):
        self.results[key] = value

    def get(self, key: str) -> any:
        return self.results.get(key)

    def cleanup(self):
        # Delete temp files created during workflow
        for f in self.temp_files:
            Path(f).unlink(missing_ok=True)
```

---

#### 4. `file_bridge.py` — File Passing Between Agents

**Job:** When Drive Agent downloads a file, Email Agent needs to find it and attach it. This handles that transfer.

- Drive Agent saves file to a known temp location
- Registers it in file_bridge with a unique handle
- Email Agent asks file_bridge for the file by handle
- After email is sent, file_bridge cleans up the temp file

```
Drive downloads → /tmp/octamind_wf_abc123/Q1_Budget_2026.xlsx
                              │
                   file_bridge registers it
                              │
Email reads     → /tmp/octamind_wf_abc123/Q1_Budget_2026.xlsx
                              │
                   file_bridge deletes after send
```

---

#### 5. `step_runner.py` — Executes One Step

**Job:** Given a single step from the plan, run it against the right agent's tools and return the result.

- Maps step → correct orchestrator (drive or email)
- Calls the function
- Handles errors gracefully
- Returns result back to master orchestrator

---

### How Existing Agents Change

**Not at all.** This is a key benefit of the dedicated window approach.

- `email_agent/app.py` — untouched
- `drive_agent/app.py` — untouched
- All existing orchestrators — untouched
- All 325 tests — still pass

The multi-agent window is entirely separate. It imports and calls the existing orchestrators as a library — the same way we call them from their own chat pages today. No modification needed.

---

### Multi-Agent Chat Window — UI Design

The new `multi_agent/app.py` page looks and feels like the existing agent chat pages — same dark theme, same chat bubbles — but with a few additions:

**Header:**
```
⚡ Multi-Agent   •   Email Agent 🟢   Drive Agent 🟢
```
Shows which agents are currently active.

**Chat behavior:**
User types a command → system shows a live progress card as it runs each step:

```
🔄 Running workflow across 2 agents...

  ✅ Step 1  [Drive]  Found "Q1 Budget 2026.xlsx"
  ✅ Step 2  [Drive]  Downloaded file (1.2 MB)
  ✅ Step 3  [Email]  Sent to cfo@company.com with attachment

✨ Done! Q1 Budget 2026.xlsx was downloaded from Drive
   and emailed to cfo@company.com.
```

If a step fails:
```
🔄 Running workflow across 2 agents...

  ✅ Step 1  [Drive]  Found "Q1 Budget 2026.xlsx"
  ✅ Step 2  [Drive]  Downloaded file (18 MB)
  ❌ Step 3  [Email]  Failed — attachment too large for Gmail (limit: 25 MB)

💡 Suggestion: "Share the Drive link for Q1 Budget instead of attaching it"
```

**Sidebar:**
- Shows active agents with green dots
- Quick example multi-agent commands
- Full Usage Guide button (same pattern as Email/Drive agents)
- Workflow history (last N completed workflows)

---

## Example Workflows to Support (Phase 1)

These are the first workflows to build and test:

| User Command                                              | Steps                                                       |
| --------------------------------------------------------- | ----------------------------------------------------------- |
| Download `<file>` from Drive and email it to `<person>`   | Drive search → Drive download → Email send                  |
| Find `<file>` in Drive and share the link with `<person>` | Drive search → Email send with link                         |
| Email me everything in my `<folder>` folder               | Drive list → Drive download (loop) → Email with attachments |
| Search Drive for `<topic>` and send me a summary by email | Drive search → Email send with results list                 |

---

## Example Workflows for Future Phases

Once the base framework is stable, these can be added:

| Command                                                               | Agents Needed    |
| --------------------------------------------------------------------- | ---------------- |
| `Summarize the meeting notes from Drive and add to my calendar`       | Drive + Calendar |
| `Get all invoices from my email and save them to a Drive folder`      | Email + Drive    |
| `Find emails from Alice, download her attachments, organize in Drive` | Email + Drive    |
| `Send me a morning briefing with emails and Drive activity`           | Email + Drive    |

---

## Implementation Phases

### Phase 1 — Core Workflow Engine (2–3 days)
- [ ] Create `src/agent/workflows/` package
- [ ] Build `workflow_context.py`
- [ ] Build `file_bridge.py`
- [ ] Build `step_runner.py` — calling existing Drive + Email orchestrators
- [ ] Build `router.py` — keyword detection + LLM fallback
- [ ] Build `master_orchestrator.py` — LLM planning + step execution
- [ ] Support first workflow: Drive download → Email send

### Phase 2 — Multi-Agent Chat UI (1–2 days)
- [ ] Create `src/agent/ui/multi_agent/` package
- [ ] Build `helpers.py` — detect which agents are running
- [ ] Build `app.py` — full dark-theme chat page with live step progress
- [ ] Add `⚡ Multi-Agent` button to dashboard (shows only when 2+ agents running)
- [ ] Wire button to launch the multi-agent window
- [ ] Support all Phase 1 example workflows

### Phase 3 — Polish + Robustness (1–2 days)
- [ ] Better LLM prompt for more accurate step planning
- [ ] Show agent status badges in multi-agent window header
- [ ] Error messages with actionable suggestions
- [ ] Auto-start agents silently if not running when user types in multi-agent window
- [ ] Temp file cleanup even when workflow crashes (`finally` block)
- [ ] Timeout guard (max 60s per step)
- [ ] Write tests for router, orchestrator, and step runner

---

## Things to Be Careful About

| Risk                                                       | How to Handle                                                |
| ---------------------------------------------------------- | ------------------------------------------------------------ |
| LLM misidentifies a single-agent command as multi-agent    | Keyword check first, LLM only as fallback                    |
| Temp files left on disk if workflow crashes                | `finally` block always calls `context.cleanup()`             |
| File too large to email                                    | Check size before sending, suggest Drive link instead        |
| Step 2 depends on Step 1 which failed                      | Stop immediately, don't run remaining steps                  |
| Infinite loops in complex workflows                        | Hard limit of max 10 steps per workflow                      |
| User credential scope (Drive needs read, Email needs send) | Check scopes at workflow start, fail fast with clear message |

---

## Success Criteria

The feature is done when:

1. The dashboard shows a **⚡ Multi-Agent** button only when Email + Drive agents are both running
2. Clicking it opens a new dedicated chat window
3. The user types:
   > “Download the latest sales report from my Drive and email it to team@company.com”
4. The window shows live step progress and returns:
   > ✅ Downloaded `Sales_Report_Feb2026.xlsx` (1.2 MB) from Drive and sent to team@company.com
5. The Email Agent chat and Drive Agent chat are completely unchanged and still work independently
6. All 325 existing tests still pass
