# OctaMind — UI Reference

**Last updated:** 2026-02-21  
**Framework:** Streamlit (Python)  
**Theme:** Dark glassmorphism · Primary accent `#e91e8c` (pink) · Background gradient `#0f172a → #1a1a2e → #16213e`

---

## Architecture Overview

OctaMind uses **three separate Streamlit applications** that communicate only through process management and shared JSON files. They do NOT share URL routes — each is a distinct process.

```
┌─────────────────────────────────────────────┐
│  Agent Hub Dashboard  (port 8501, always on) │
│  agent_dashboard.py                          │
│  — Create, start, stop, configure agents     │
└──────────────────┬──────────────────────────┘
                   │  spawns sub-process per agent
        ┌──────────┴──────────────┐
        ▼                         ▼
┌───────────────────┐   ┌─────────────────────────┐
│ Gmail Agent UI    │   │ Generic Agent Chat UI    │
│ email_agent_ui.py │   │ generic_agent_ui.py      │
│ port: dynamic     │   │ port: dynamic            │
│ (Gmail agents)    │   │ (all other agent types)  │
└───────────────────┘   └─────────────────────────┘
```

Each agent window runs on a unique port assigned at start time and shuts down automatically when the browser closes (watchdog thread).

---

## Page 1 — Agent Hub Dashboard

**File:** `src/agent/ui/agent_dashboard.py`  
**Entry point:** `python start.py` or `streamlit run src/agent/ui/agent_dashboard.py`  
**Default URL:** `http://localhost:8501`  
**Page title:** `OctaMind — Agent Hub`

This is the main control center. It is always running while OctaMind is active.

### Layout

```
┌──────────────────┬─────────────────────────────────────────┐
│   SIDEBAR        │   MAIN AREA                              │
│                  │                                          │
│  📊 Overview     │  OctaMind hero header (logo + tagline)   │
│  • Total agents  │                                          │
│  • Running count │  ┌── Mode A: Agent List ─────────────┐  │
│                  │  │  Search bar + Type + Status filters │  │
│  ➕ Create Agent  │  │  2-column grid of agent cards       │  │
│  (button)        │  └─────────────────────────────────────┘  │
│                  │                                          │
│  🎯 Agent Types  │  ┌── Mode B: Create Agent Form ───────┐  │
│  (per-type count)│  │  (replaces list, see below)         │  │
│                  │  └─────────────────────────────────────┘  │
│  💡 tip caption  │                                          │
│                  │  ┌── Mode C: Configure Panel ─────────┐  │
│                  │  │  (shown above list when open)       │  │
│                  │  └─────────────────────────────────────┘  │
└──────────────────┴─────────────────────────────────────────┘
```

### Sidebar

| Element                | Description                                             |
| ---------------------- | ------------------------------------------------------- |
| **Total Agents**       | Count badge (pink) — agents in `agents.json`            |
| **Running**            | Count badge (green) — agents with live processes        |
| **➕ Create New Agent** | Primary button → switches main area to Create form      |
| **🎯 Agent Types list** | Shows each type with per-type agent count; updates live |
| Caption                | "Each agent runs in its own Streamlit window."          |

### Modes / Views

#### Mode A — Agent List (default)

Shown when no form/configure panel is open.

**Search & filters** (3-column row):
- Text search — matches agent name or type (case-insensitive)
- Type dropdown — "All" plus each of the 6 agent types
- Status dropdown — All / Running / Stopped

**Agent Card** (rendered by `show_agent_card()`):

Each card is a glassmorphism panel with:

| Section        | Content                                                |
| -------------- | ------------------------------------------------------ |
| Header row     | `{icon} {name}` + status badge (🟢 Running / ⚫ Stopped) |
| Body           | Type, Role description                                 |
| Footer         | Created date                                           |
| Running banner | Port number + **🚀 Open {Agent} Window** link button    |
| Button row     | ▶️ Start / ⏹️ Stop · ⚙️ Configure · 🗑️ Delete              |

- **Start** spawns the agent subprocess, assigns a free port, shows success toast.
- **Stop** terminates the subprocess.
- **Configure** toggles the Configure Panel (see Mode C). Label changes to "✖ Close Config" when open.
- **Delete** requires a two-step confirmation (first click shows warning, second click confirms). Stops agent first if running.

**Empty state:** When no agents exist, a welcome screen is shown with type cards and a "Create Your First Agent" CTA.  
**Filter mismatch:** When filters return zero results, a warning panel is shown.

---

#### Mode B — Create Agent Form

Triggered by "➕ Create New Agent" in sidebar or "Create Your First Agent" CTA. Replaces the agent list.

All fields are inside `st.form("create_agent_form")` which submits as one batch.

| Field                    | Widget                                           | Notes                                          |
| ------------------------ | ------------------------------------------------ | ---------------------------------------------- |
| **Agent Name**           | `st.text_input`                                  | Required                                       |
| **Agent Type**           | Visual type cards + `st.radio`                   | 6 options; radio text is pink (#e91e8c)        |
| **Role / Purpose**       | `st.text_area` (100px)                           | Required — describes what the agent does       |
| **🎭 Personality Traits** | Collapsible `st.expander` (collapsed by default) | 5 sliders (0–10); sensible defaults pre-filled |
| **⚙️ Advanced Config**    | Collapsible `st.expander` (collapsed by default) | Auto-run on startup, Max operations            |
| **Submit / Cancel**      | Two form buttons                                 | Cancel restores agent list view                |

**Agent Type cards:** Each type is displayed as a visual card with icon + name + description, then a horizontal radio group underneath lets the user pick. The selection drives both the visual highlight and the actual type stored.

**Personality Traits expander:**

| Slider        | Range | Default | Left → Right         |
| ------------- | ----- | ------- | -------------------- |
| Tone          | 0–10  | 3       | Formal → Casual      |
| Verbosity     | 0–10  | 5       | Brief → Detailed     |
| Humor         | 0–10  | 2       | Serious → Witty      |
| Empathy       | 0–10  | 6       | Neutral → Warm       |
| Proactiveness | 0–10  | 5       | Reactive → Proactive |

On submit, traits are passed to `AgentManager.create_agent()` and written to `memory/<agent_id>/personality.md`.

---

#### Mode C — Configure Panel

Shown inline above the agent list when ⚙️ Configure is clicked on a card. Only one agent can be in configure mode at a time (`st.session_state.configure_agent_id`).

Rendered by `show_configure_panel(agent)`:

```
⚙️ Configure — {Agent Name}
Adjust personality traits and set up recurring automations.

[🎭 Personality Traits]  [⚙️ Automations]
```

**Personality Traits tab:**
- 5 sliders pre-filled from `agent['config']['personality_traits']`
- Two-column layout
- "💾 Save Personality" form button → calls `AgentManager.update_personality_traits()` → rewrites `personality.md`

**Automations tab:**
- Only shows content for `gmail` agents; other types show a "coming soon" info box.
- Lists all 10 Gmail automations from `AUTOMATION_CATALOG`.
- Each automation entry shows:
  - Label + description in a styled container (green border if enabled, subtle if disabled)
  - `st.checkbox("Enable this automation")` — saves immediately on toggle via `update_automation_state()` + `st.rerun()`
  - Collapsible ⚙️ Settings expander (only visible when enabled AND automation has configurable params)
  - "💾 Save Settings" button per automation (saves param changes)

**Available Gmail automations:**

| Automation               | Description                                 | Interval |
| ------------------------ | ------------------------------------------- | -------- |
| Auto-Delete Spam         | Permanently trash SPAM messages             | 30 min   |
| Auto-Archive Newsletters | Move promotional emails out of inbox        | 60 min   |
| Daily Email Digest       | Summarise inbox and save to episodic memory | 24 hr    |
| Auto-Label VIP Contacts  | Star emails from frequent contacts          | 60 min   |
| Flag Old Unread Emails   | Add `needs-attention` label to old unread   | 120 min  |
| Weekly Email Report      | Generate productivity report                | 7 days   |
| Auto-Categorise Emails   | Apply smart labels to uncategorised emails  | 120 min  |
| Auto-Unsubscribe         | Detect and open unsubscribe links           | 24 hr    |
| Out-of-Office Auto-Reply | Send auto-replies until a set date          | 60 min   |
| Archive Old Read Emails  | Archive read emails older than N days       | 24 hr    |

---

## Page 2 — Gmail Agent Chat

**File:** `src/agent/ui/email_agent_ui.py`  
**Launched by:** Dashboard "▶️ Start Agent" for Gmail-type agents  
**URL:** `http://localhost:{dynamic_port}` (link shown on agent card)  
**Page title:** `{Agent Name} — OctaMind`

This is the LLM-orchestrated Gmail management interface. Users type natural language commands and the agent executes Gmail API operations.

### Layout

```
┌─────────────────────────┬─────────────────────────────────────┐
│   SIDEBAR               │  MAIN AREA                          │
│                         │                                      │
│  📖 Full Usage Guide    │  OctaMind hero header (logo + name) │
│                         │                                      │
│  ⚡ Quick Commands      │  Chat message history                │
│  (9 collapsible groups) │  • User messages (right-aligned)     │
│                         │  • Agent responses (left-aligned)    │
│  🟢 Ready               │                                      │
│                         │  💬 Chat input box                   │
│  📊 Inbox Statistics    │  (always at bottom)                  │
│  • Total / Unread       │                                      │
│  • Threads              │                                      │
│  • Unread %             │                                      │
│                         │                                      │
│  📜 Session History     │                                      │
│  (appears after first   │                                      │
│  message)               │                                      │
└─────────────────────────┴─────────────────────────────────────┘
```

### Sidebar Sections

| Section                | Description                                                                            |
| ---------------------- | -------------------------------------------------------------------------------------- |
| **📖 Full Usage Guide** | Link button to `documentation/EMAIL_AGENT_USAGE_GUIDE.md`                              |
| **⚡ Quick Commands**   | 9 collapsed expanders, each with 4–8 example commands                                  |
| **🟢 Ready**            | Live status indicator                                                                  |
| **📊 Inbox Statistics** | 2×2 grid: Total messages, Unread, Threads, Unread % (fetched from Gmail)               |
| **📜 Session History**  | Appears after first exchange; shows last N user↔agent pairs in reverse with timestamps |

### Quick Command Groups

| Group                    | Examples                                                      |
| ------------------------ | ------------------------------------------------------------- |
| 📥 Read & Search          | List emails, find by sender, today's emails, label search     |
| ✉️ Send & Draft           | Send email, create draft, list/send/delete drafts             |
| 🗑️ Delete                 | Delete by count, sender, or label                             |
| 🧠 Summarize & Tasks      | Summarize email, daily digest, extract tasks, saved tasks     |
| 💬 Reply & Smart Labels   | Suggest reply, quick reply, auto-label, urgent detection      |
| 📅 Calendar & Follow-ups  | Extract events, set follow-up, pending follow-ups, ICS export |
| ⏰ Scheduling             | Schedule email, view/reschedule/cancel scheduled emails       |
| 👥 Contacts & Newsletters | Frequent contacts, export contacts, newsletter detection      |
| 📊 Analytics & Reports    | Email stats, productivity insights, weekly report, patterns   |

### Chat Interface

- Messages displayed using `st.chat_message` (Streamlit native bubble UI)
- User input via `st.chat_input` at bottom of page
- Each submission → LLM parses intent → Gmail API executes → response shown
- Interactions saved to agent's episodic memory (if memory module available)
- Background: automation scheduler starts once per process for recurring tasks

---

## Page 3 — Generic Agent Chat

**File:** `src/agent/ui/generic_agent_ui.py`  
**Launched by:** Dashboard "▶️ Start Agent" for all non-Gmail agent types  
**URL:** `http://localhost:{dynamic_port}`  
**Page title:** `{Agent Name} — OctaMind`  
**Supported types:** `google_drive`, `slack`, `calendar`, `stock_market`, `custom`

A universal conversational UI for agents whose back-end integrations are not yet built. Agents can chat and their interactions are stored in memory.

### Layout

```
┌─────────────────────────┬─────────────────────────────────────┐
│   SIDEBAR               │  MAIN AREA                          │
│                         │                                      │
│  🤖 OctaMind logo       │  OctaMind header (logo + name)      │
│                         │  Agent ID caption                   │
│  🤖 Agent Info          │  Divider                            │
│  • Name, Type, ID       │                                      │
│                         │  💬 Chat with {Agent Name}          │
│  🧠 Agent Memory        │  • Message bubbles                  │
│  [6 tabs]               │  • Clear Chat button (top-right)    │
│  Personality · Habits   │  • Chat input box                   │
│  Working · Episodic     │                                      │
│  Semantic · Conscious.  │                                      │
│                         │                                      │
│  🛠️ Capabilities        │                                      │
│  (type-specific list)   │                                      │
│                         │                                      │
│  📜 Session History     │                                      │
│  (after first message)  │                                      │
└─────────────────────────┴─────────────────────────────────────┘
```

### Sidebar Sections

| Section                        | Description                                                   |
| ------------------------------ | ------------------------------------------------------------- |
| **OctaMind logo + Agent name** | Branding header                                               |
| **🤖 Agent Info**               | Name, Type, ID (raw agent_id)                                 |
| **🧠 Agent Memory**             | 6-tab viewer — reads live from `memory/<agent_id>/*.md` files |
| **🛠️ Capabilities**             | Per-type list of planned features; empty for `custom` agents  |
| **📜 Session History**          | Appears after first exchange; shows recent user↔agent pairs   |

### Memory Viewer Tabs

| Tab           | File read            |
| ------------- | -------------------- |
| Personality   | `personality.md`     |
| Habits        | `habits.md`          |
| Working       | `working_memory.md`  |
| Episodic      | `episodic_memory.md` |
| Semantic      | `semantic_memory.md` |
| Consciousness | `consciousness.md`   |

### Per-Type Capabilities

| Agent Type     | Capabilities shown                                         |
| -------------- | ---------------------------------------------------------- |
| 📁 Google Drive | List files, search, upload/download, share, delete         |
| 💬 Slack        | Send messages, list channels, manage notifications, search |
| 📅 Calendar     | Create events, view schedule, set reminders, reschedule    |
| 📈 Stock Market | Track prices, market trends, portfolio, news, price alerts |
| 🔧 Custom       | Adaptable, learns preferences, suggests automations        |

> **Note:** These agents respond via a simple LLM fallback (`_handle_conversation`) since full integrations are planned for future phases. The memory viewer and personality traits are fully functional.

---

## UI Design System

### Colours

| Token           | Value              | Used for                           |
| --------------- | ------------------ | ---------------------------------- |
| Primary pink    | `#e91e8c`          | Headings, buttons, borders, labels |
| Accent teal     | `#a8dadc`          | Secondary labels, sub-headings     |
| Background dark | `#0f172a`          | Page background start              |
| Background mid  | `#1a1a2e`          | Agent cards                        |
| Background end  | `#16213e`          | Page background end                |
| Status green    | `#28a745`          | Running badge, enabled automations |
| Status red      | `#ff6b6b`          | Stopped badge, errors              |
| Muted text      | `#888` / `#b0b0b0` | Descriptions, captions             |

### Typography

- **Page title:** 2.4–2.6 rem, weight 900, gradient fill (pink → teal)
- **Section heading:** 1.4–1.8 rem, weight 800, white or pink
- **Card labels:** 0.9–1 rem, weight 600, pink
- **Body / descriptions:** 0.85–0.95 rem, `#b0b0b0`
- **Captions:** 0.75–0.8 rem, `#888`

### Glassmorphism Cards (reusable pattern)

```css
background: linear-gradient(135deg, rgba(233,30,140,0.15) 0%, rgba(156,39,176,0.1) 100%);
border: 1px solid rgba(233,30,140,0.3);
border-radius: 16px;
backdrop-filter: blur(10px);
box-shadow: 0 8px 32px rgba(233,30,140,0.15);
padding: 24–32px;
```

### Common UI Patterns

| Pattern             | How implemented                                               |
| ------------------- | ------------------------------------------------------------- |
| Inline HTML styling | `st.markdown(..., unsafe_allow_html=True)`                    |
| Logo                | `st.cache_resource` base64 PNG, decoded once per process      |
| Form submission     | `st.form` + `st.form_submit_button` (avoids premature reruns) |
| Immediate toggles   | `st.checkbox` / `st.button` outside forms + `st.rerun()`      |
| Expanders           | `st.expander(label, expanded=False)` — collapsed by default   |
| 2-col layouts       | `st.columns([ratio, ratio])`                                  |
| Status badges       | Inline `<div>` with background-color and border-radius        |
| Page icon           | PIL Image of `octopus.png`, fallback to 🐙 emoji               |

---

## Session State Keys

### Agent Hub Dashboard

| Key                             | Type          | Purpose                                   |
| ------------------------------- | ------------- | ----------------------------------------- |
| `show_create_form`              | `bool`        | Whether the Create Agent form is visible  |
| `configure_agent_id`            | `str \| None` | ID of agent whose Configure panel is open |
| `delete_confirm_{agent_id}`     | `bool`        | Two-step delete confirmation state        |
| `cp_tone`, `cp_verbosity`, etc. | `int`         | Personality slider values in Create form  |

### Gmail Agent Chat

| Key        | Type   | Purpose                                            |
| ---------- | ------ | -------------------------------------------------- |
| `agent_id` | `str`  | Current agent's ID                                 |
| `messages` | `list` | Full chat message history                          |
| `history`  | `list` | Session history for sidebar (user+assistant pairs) |

### Generic Agent Chat

| Key             | Type   | Purpose                                      |
| --------------- | ------ | -------------------------------------------- |
| `chat_messages` | `list` | Full chat history including opening greeting |
| `history`       | `list` | Session history for sidebar                  |

---

## Source Files Quick Reference

| File                               | Lines | Purpose                                |
| ---------------------------------- | ----- | -------------------------------------- |
| `src/agent/ui/agent_dashboard.py`  | ~762  | Agent Hub — main control centre        |
| `src/agent/ui/email_agent_ui.py`   | ~1877 | Gmail agent chat + LLM orchestration   |
| `src/agent/ui/generic_agent_ui.py` | ~399  | Generic chat for non-Gmail agent types |
| `src/agent/assets/octopus.png`     | —     | Logo used across all UI pages          |

---

## Adding a New Page / Panel

1. **New agent type UI:** Copy `generic_agent_ui.py`, replace `_TYPE_META` with your type's metadata. Register in `AgentManager.AGENT_TYPES`. The process manager (`start_agent`) picks the launch file from `_AGENT_LAUNCHERS` in `process_manager.py`.

2. **New panel on agent card:** Add a new `st.session_state` key for open/close state, follow the `configure_agent_id` pattern — toggle in the card button, render the panel function above the agent list in `main()`.

3. **New sidebar section in email agent:** Add a new `st.divider()` + section block inside the `with st.sidebar:` block in `email_agent_ui.py::main()`.
