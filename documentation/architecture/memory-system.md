# Cognitive Memory Architecture

**Complete Implementation Guide & Reference**

*Last Updated: February 25, 2026*

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Layers](#architecture-layers)
3. [Implementation Details](#implementation-details)
4. [Data Flow](#data-flow)
5. [Automatic Consolidation](#automatic-consolidation)
6. [State Persistence](#state-persistence)
7. [Usage Scenarios](#usage-scenarios)
8. [Code Reference](#code-reference)
9. [Testing](#testing)
10. [LLM Context Management](#llm-context-management)
11. [On-Demand Episodic Recall](#on-demand-episodic-recall)
12. [Recall System Improvements (Feb 2026)](#recall-system-improvements)

---

## Overview

The Cognitive Memory Architecture implements a **6-layer memory system** (7 for the multi-agent hub) inspired by human cognitive processes. This system enables agents to:

- ✅ Remember short-term interactions (Working Memory)
- ✅ Store long-term events with timestamps (Episodic Memory)
- ✅ Extract and maintain learned knowledge about the **user** (Semantic Memory)
- ✅ Maintain stable identity (Personality)
- ✅ Learn confirmed behavioural patterns after 3+ occurrences, including day-of-week and time-of-day habits (Habits)
- ✅ Develop a big-picture manager-level mental model of the user — synthesised from ALL memory layers (Consciousness)
- ✅ **Multi-agent only:** Synthesise a cross-domain user model from all sub-agents' consciousness layers (Collective Consciousness)

### Key Features

- **Automatic Consolidation**: `ConsolidationRunner` daemon thread starts with the app and runs every 24 h for **all** Personal Assistants — including idle/stopped ones
- **Pattern Extraction**: Automatically detects repeated behaviours
- **Habit Learning**: Requires 3+ confirmations. Detects day-of-week patterns (e.g. “deletes spam every Friday”) and time-of-day patterns (e.g. “sends emails at 09:00”)
- **90-Day Decay**: Old memories archived or deleted based on importance
- **State Persistence**: Consolidation timestamps survive agent restarts
- **LLM Integration**: Memory-aware responses
- **PA Hub Hard-Coded Personality**: `__multi_agent__` personality is prose-level, protective, always restored on init — immune to trait-slider edits

---

## Quick Reference — What Goes in Each File

> Plain-language summary. For full details see the layer sections below.

| File                 | What it stores                                                        | Written by                                                       | Grows how fast                  |                        Sent to LLM?                         |                                  Cleanup                                   |
| -------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------- | :---------------------------------------------------------: | :------------------------------------------------------------------------: |
| `working_memory.md`  | The last 10 things the agent did or was asked                         | Every interaction                                                | Fast — auto-trimmed to 10 items |                    ✅ Last 10 interactions                   |                           Auto-trimmed in-place                            |
| `episodic_memory.md` | Time-stamped events: what happened and why it matters                 | Every interaction (via `add_interaction`) + consolidation themes | Moderate                        | ❌ Not sent by default — loaded on-demand for recall queries | Items older than 90 days → `archive/` (Low → deleted, Medium → archived, High → kept) |
| `semantic_memory.md` | Learned facts about the user — preferences, recurring needs, background, values, people | Consolidation engine                            | Slow                            |                   ✅ Last 3 000 chars only                   |                     Never archived (caps protect LLM)                      |
| `personality.md`     | Who the agent is: tone, communication style, goals. **PA Hub: hard-coded protective persona** | Manual / agent setup. PA Hub: always restored on init | Barely at all |                   ✅ Full file (no cap)                      |                               Never changes                                |
| `habits.md`          | Confirmed user behavioural patterns (3+ occurrences). Captures day-of-week, time-of-day, and action-type patterns | Consolidation engine | Slow |                     ✅ Last 3 000 chars                      |                     Never archived (caps protect LLM)                      |
| `consciousness.md`   | Big-picture manager-level mental model of the user. Synthesised from ALL memory layers | Consolidation engine (every 2–4 weeks) | Very slow |                   ✅ Full file (no cap)                      |                               Never archived                               |
| `collective_consciousness.md` | **PA Hub only.** Cross-domain synthesis of every skill agent’s `consciousness.md` | Consolidation engine (each cycle for `__multi_agent__`) | Very slow | ✅ Full file (no cap) | Never archived |

### Rule of thumb

- **User sends a message** → `working_memory.md` gains one entry (oldest dropped if > 10).
- **App boots** → `ConsolidationRunner` daemon thread starts immediately and runs a full consolidation pass for all agents. Subsequent passes run every 24 hours — even for stopped/inactive agents.
- **Each consolidation cycle:** working memory patterns → `semantic_memory.md`; episodic themes → `semantic_memory.md`; day-of-week/time-of-day patterns → `habits.md`; consciousness update (if 2+ weeks); PA hub → `collective_consciousness.md`.
- **Event is 90 days old** → Low importance deleted, Medium moved to `archive/episodic_YYYY_MM.md`, High kept forever.
- **Every LLM call** → last 10 working memory interactions sent. `personality.md` and `consciousness.md` sent in full. `habits.md` and `semantic_memory.md` capped at 3 000 chars. `episodic_memory.md` excluded by default (on-demand recall only). Multi-agent additionally sends `collective_consciousness.md` in full.
- **User asks “do you remember X?”** → `recall_for_llm()` runs before the LLM call, searches episodic/working/semantic on demand, and injects only matching entries into the prompt for that single turn.

### What gets summarised vs archived

| Action             | What happens                                                                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Summarised**     | `working_memory.md` entries are distilled into `semantic_memory.md` and `episodic_memory.md` by the consolidation engine                          |
| **Archived**       | `episodic_memory.md` entries older than 90 days — Low → deleted, Medium → `archive/episodic_YYYY_MM.md`. ✅ File rewrite implemented. |
| **Trimmed**        | `working_memory.md` is trimmed in-place to the last 10 interactions                                                                               |
| **Capped for LLM** | `semantic_memory.md`, `habits.md`, `personality.md`, `consciousness.md` are tail-capped before being added to the LLM prompt                      |

---

## Architecture Layers

### Layer 1: Working Memory (Short-Term)

**Purpose**: Current context and recent interactions (RAM-like)

**Characteristics**:
- Limited capacity: Max 10 items
- Auto-trimmed: Oldest items removed automatically
- High-speed access: Loaded on every LLM request
- Ephemeral: Constantly updated

**Storage**: `memory/{agent_id}/working_memory.md`

**Structure**:
```markdown
# Working Memory

## Active Focus
- Processing user requests

## Current Questions
- (None)

## Current Context
- Active session in progress

---

## Interaction at 2026-02-20T00:15:30

**Timestamp:** 2026-02-20T00:15:30
**Command:** count emails today
**Action:** count_emails
**Status:** success
**Result:** 25 emails
**Metadata:** reasoning: User wants daily email count

---
```

**Implementation**: `agent_memory.py::add_interaction()`

---

### Layer 2: Episodic Memory (Events)

**Purpose**: Time-stamped events with importance scoring

**Characteristics**:
- Time-stamped: Every event has a date
- Importance-scored: High/Medium/Low
- Searchable: Keyword search via `search_episodic_memory()`
- Subject to decay: 90-day mechanism applies
- **Not in default LLM context**: loaded on-demand only (see §11)

> ⚠️ **Known limitation**: The `insight` field is currently hardcoded to `"User performed {action}"` for all auto-recorded events. Meaningful insights require either manual `add_episodic_event()` calls or LLM-generated insight strings. This limits the value of theme extraction during consolidation.

**Storage**: `memory/{agent_id}/episodic_memory.md`

**Structure**:
```markdown
# Episodic Memory

## 2026-02-20

**Event:** User checked daily email counts multiple times
**Insight:** User prefers staying on top of inbox volume
**Importance:** High
**Context:** Email management workflow

---

## 2026-02-19

**Event:** User deleted spam emails
**Insight:** Proactive email hygiene behavior
**Importance:** Medium
**Context:** Mailbox cleanup
```

**Implementation**: `agent_memory.py::add_episodic_event()`

---

### Layer 3: Semantic Memory (Knowledge)

**Purpose**: Distilled knowledge about the user (not raw logs)

**Characteristics**:
- Synthesized: Patterns extracted from working/episodic memory
- Slowly evolving: Only updates during consolidation
- High-level: User preferences, interests, patterns
- Long-term: No decay mechanism

**Storage**: `memory/{agent_id}/semantic_memory.md`

**Structure**:
```markdown
# Semantic Memory

## User Preferences
- Prefers daily email counts to stay organized
- Frequently checks "today" timeframe
- Values quick inbox summaries

## Usage Patterns
- Peak usage: Morning hours (7-10 AM)
- Frequent commands: count, list, delete
- Communication style: Direct and task-oriented

## Key Insights
- User manages high email volume (40+ daily)
- Proactive about spam/junk cleanup
- Prefers automation for repetitive tasks
```

**Implementation**: `agent_memory.py::update_semantic_memory()`  
**Auto-updated by**: `memory_consolidator.py::_extract_patterns_from_working_memory()`

---

### Layer 4: Personality (Stable Identity)

**Purpose**: Agent's behavioral traits and communication style

**Characteristics**:
- Stable: Rarely changes
- Defines agent behavior: How to interact
- User-specific: Can be different per user
- Manually defined: Not auto-learned

**Storage**: `memory/{agent_id}/personality.md`

**Structure**:
```markdown
# Personality Profile

## Core Traits
- **Tone:** Professional yet friendly
- **Style:** Clear, concise, helpful
- **Approach:** Proactive assistance

## Communication Style
- Use natural language
- Reference past interactions when relevant
- Acknowledge continuity in relationship
- Be memory-aware in responses

## Goals
- Help manage email efficiently
- Provide intelligent summaries
- Learn user preferences over time
```

**Implementation**: `agent_memory.py::update_personality()`

---

### Layer 5: Habits (Behavioral Learning)

**Purpose**: Learned patterns from repeated confirmations

**Characteristics**:
- **Requires 3+ confirmations**: Not based on single interactions
- Behavioral patterns: Communication, work, learning styles
- Automatically detected: By consolidation engine
- Stable once formed: Difficult to change

**Storage**: `memory/{agent_id}/habits.md`

**Structure**:
```markdown
# Habits & Patterns

## Communication Pattern - 2026-02-20
- Prefers imperative communication style (85% of interactions)
- Direct task requests without small talk
- Question-and-answer format for information needs

## Work Pattern - 2026-02-19
- Most active during morning hours (7-10 AM)
- Peak usage: Monday mornings (planning week)
- Regular check-ins: 3-4 times per day

## Learning Pattern - 2026-02-18
- Prefers simple queries over complex searches
- Task-oriented: Count/list operations (70% of tasks)
- Efficiency-focused: Quick results valued
```

**Implementation**: `agent_memory.py::add_habit()`  
**Auto-detected by**: `memory_consolidator.py::_detect_habits()`

---

### Layer 6: Consciousness (Manager’s Mental Model)

**Purpose**: Big-picture understanding of the user — synthesised from ALL memory layers

**Characteristics**:  
- Synthesised from working, episodic, semantic, and habits — not just semantic
- Infrequently updated: Every 2–4 weeks
- Covers 7 structured sections (who they are, what they care about, how they communicate, where they need help, trust baseline, trajectory, key insights)

**Storage**: `memory/{agent_id}/consciousness.md`

**Sections**:

| Section | What it captures |
|---------|------------------|
| Who Is This Person? | Professional identity, role, context |
| What Do They Care About Most? | Values, priorities, non-negotiables |
| Current Life / Work Chapter | Phase they’re in right now |
| How They Think & Communicate | Mental models, dominant interaction style |
| Where They Need the Most Help | Frequent friction points, top actions |
| Trust & Safety Profile | Normal patterns — baseline for anomaly detection |
| Strategic Trajectory | Where they seem to be heading |

**Implementation**: `agent_memory.py::update_consciousness()`  
**Auto-updated by**: `memory_consolidator.py::_update_consciousness_layer()`

---

### Layer 7: Collective Consciousness *(Personal Assistant Hub only)*

**Purpose**: Cross-domain synthesis of all sub-agents’ individual consciousness layers into a single unified picture of the user

**Characteristics**:  
- Only exists for `__multi_agent__` (`memory/__multi_agent__/collective_consciousness.md`)
- Updated every consolidation cycle (not just every 2–4 weeks)
- Aggregates non-placeholder bullets from each agent’s `consciousness.md`
- Builds a composite trust baseline from all agents’ safety sections

**Storage**: `memory/__multi_agent__/collective_consciousness.md`

**Sections**:

| Section | What it captures |
|---------|------------------|
| Agent-Specific Insights | Key bullets each agent has independently learned |
| Composite Trust Baseline | Normal patterns across all services — for anomaly detection |
| Cross-Domain Patterns | Behaviours that appear in multiple agents’ memory |
| Conflict / Inconsistency Log | Cases where two agents have contradictory models |

**Auto-updated by**: `memory_consolidator.py::_update_collective_consciousness()`

---

## Implementation Details

### File Structure

```
memory/
├── {agent_id}/
│   ├── working_memory.md          # Last 10 interactions
│   ├── episodic_memory.md         # Time-stamped events
│   ├── semantic_memory.md         # Learned facts about the user
│   ├── personality.md             # Agent identity
│   ├── habits.md                  # Confirmed user behavioural patterns (3+)
│   ├── consciousness.md           # Big-picture mental model of the user
│   ├── consolidation_state.json   # Persistence state
│   └── archive/                   # Old episodic memories
│       └── episodic_2025_*.md
└── __multi_agent__/             # Personal Assistant hub (created on first dashboard launch)
    ├── working_memory.md
    ├── episodic_memory.md
    ├── semantic_memory.md
    ├── personality.md             # Hard-coded protective personal-assistant persona
    ├── habits.md
    ├── consciousness.md
    ├── collective_consciousness.md # Cross-agent synthesis (unique to PA hub)
    └── archive/
```

### Core Classes

#### AgentMemory (`src/agent/memory/agent_memory.py`)

**Primary interface for memory operations**

```python
class AgentMemory:
    def __init__(self, agent_id: str, memory_base_dir: str = "memory")
    
    # Working Memory
    def add_interaction(command, action, result, metadata, importance)
    def get_recent_interactions(count=10) -> List[Dict]
    
    # Episodic Memory
    def add_episodic_event(event, insight, importance, context)
    def get_recent_events(count=10) -> List[Dict]
    def search_episodic_memory(query) -> List[Dict]
    
    # Semantic Memory
    def update_semantic_memory(section, content)
    def get_semantic_memory() -> str
    
    # Personality
    def get_personality() -> str
    def update_personality(trait, description)
    
    # Habits
    def get_habits() -> str
    def add_habit(habit_type, description)
    
    # Consciousness
    def get_consciousness() -> str
    def update_consciousness(section, content)
    
    # Consolidation
    def get_consolidator() -> MemoryConsolidator
    def run_consolidation()
    
    # LLM Integration
    def get_full_context_for_llm(include_episodic=False) -> str
    def recall_for_llm(query, max_episodic=5, max_working=3) -> str
    
    # Search
    def search_interactions(query) -> List[Dict]
    def search_episodic_memory(query) -> List[Dict]
    def remember(query) -> str
```

#### MemoryConsolidator (`src/agent/memory/memory_consolidator.py`)

**Automatic memory consolidation engine**

```python
class MemoryConsolidator:
    def __init__(self, agent_memory: AgentMemory)
    
    # Main Entry Point
    def consolidate()
    def should_consolidate(interaction_count: int) -> bool
    
    # Pattern Extraction
    def _extract_patterns_from_working_memory() -> Dict
    def _extract_themes_from_episodic() -> Dict
    def _update_semantic_with_patterns(patterns)
    def _update_semantic_with_themes(themes)
    
    # Habit Detection
    def _detect_habits() -> List[Dict]
    def _add_confirmed_habits(habits)
    
    # Decay Mechanism
    def _apply_decay_mechanism()
    
    # Consciousness Updates
    def _should_update_consciousness() -> bool
    def _update_consciousness_layer()
    
    # State Persistence
    def _load_state()
    def _save_state()
```

---

## Data Flow

### Complete Memory Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INTERACTION                        │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
    Email Action          Conversation
    ("count emails")      ("Hello!")
         │                       │
         ↓                       ↓
    Execute Command        LLM Response
         │                       │
         └───────────┬───────────┘
                     ↓
         ┌───────────────────────┐
         │ memory.add_interaction│
         │   command, action,    │
         │   result, metadata    │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ↓                       ↓
    Working Memory          Episodic Memory
    (Auto-trim to 10)       (Timestamped)
    working_memory.md       episodic_memory.md
         │                       │
         │   interaction_count += 1
         │                       │
         └───────────┬───────────┘
                     ↓
         ┌──────────────────────────┐
         │ Should Consolidate?      │
         │ - Count >= 20?           │
         │ - 24 hours passed?       │
         └───────┬──────────────────┘
                 │
         ┌───────┴────────┐
         │ YES           │ NO
         ↓               ↓
    CONSOLIDATION    Continue
         │
         ↓
┌────────────────────────────────────────────────────────────┐
│                 🧠 CONSOLIDATION ENGINE 🧠                  │
│                                                             │
│  1. Extract Patterns                                        │
│     ├─ Working Memory → Frequent commands                  │
│     ├─ Detect timeframe preferences                        │
│     └─ Identify action patterns                            │
│                                                             │
│  2. Extract Themes                                          │
│     ├─ Episodic Memory → Recurring events                  │
│     ├─ High-importance insights                            │
│     └─ User context patterns                               │
│                                                             │
│  3. Detect Habits (3+ confirmations)                       │
│     ├─ Communication patterns                              │
│     ├─ Work patterns (time of day)                         │
│     └─ Learning patterns (task complexity)                 │
│                                                             │
│  4. Apply 90-Day Decay                                       │
│     ├─ Low importance → Delete                             │
│     ├─ Medium importance → Archive                         │
│     └─ High importance → Keep                              │
│                                                             │
│  5. Update Consciousness (every 2-4 weeks)                 │
│     ├─ Synthesize user profile                             │
│     ├─ Extract core patterns                               │
│     └─ Strategic direction insights                        │
│                                                             │
└────────────┬───────────────────────────────────────────────┘
             │
             ↓
    ┌────────────────────┐
    │ Update Memory Files│
    ├────────────────────┤
    │ semantic_memory.md │ ← Patterns & themes
    │ habits.md          │ ← Confirmed habits (3+)
    │ consciousness.md   │ ← Meta-summary (periodic)
    └────────────────────┘
             │
             ↓
    ┌─────────────────────┐
    │ Save State to Disk  │
    │ consolidation_state │
    │      .json          │
    └─────────────────────┘
             │
             ↓
    interaction_count = 0 (reset)
    last_consolidation = NOW
```

### LLM Integration Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  LLM REQUEST INITIATED                      │
└────────────────────┬────────────────────────────────────────┘
                     ↓
         ┌───────────────────────┐
         │ Load Memory Context   │
         │ get_full_context_     │
         │        for_llm()      │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────────────────────────────┐
         │                                               │
         ↓                                               ↓
    Load ALL Layers                          Format as String
    ├─ Personality   (full file, no cap)         ┌──────────────┐
    ├─ Consciousness (full file, no cap)         │ # Agent      │
    ├─ Working Memory (last 10 items)            │ Memory       │
    ├─ Semantic Memory (last 3000 chars)         │ Context      │
    ├─ Habits        (last 3000 chars)           │              │
    └─ Episodic: NOT included by default      │ ## Person... │
       (use recall_for_llm() instead)         │ ## Consci... │
                                             │ ## Working..│
                                             │ ## Semant...│
                                             │ ## Habits...│
                                             │[+ Recall if │
                                             │ recall query]│
                                             └──────┬───────┘
                                                    │
                     ┌──────────────────────────────┘
                     ↓
         ┌───────────────────────┐
         │   Build System Prompt │
         │                       │
         │ You are {agent_name}  │
         │                       │
         │ Memory Context:       │
         │ {memory_context}      │
         │                       │
         │ Memory Guidelines:    │
         │ - 6 layers explained  │
         │ - Usage principles    │
         │ - Auto-management     │
         └───────────┬───────────┘
                     │
                     ↓
         ┌───────────────────────┐
         │  LLM API Call         │
         │  (GPT-4o-mini)        │
         │                       │
         │  system: prompt       │
         │  messages: history    │
         │  + user message       │
         └───────────┬───────────┘
                     │
                     ↓
         ┌───────────────────────┐
         │   LLM Response        │
         │   (Memory-Aware)      │
         │                       │
         │ "Based on your habit  │
         │  of checking morning  │
         │  emails, here are..." │
         └───────────────────────┘
```

---

## Automatic Consolidation

### Trigger Conditions

**1. Global Background Thread (Primary — added Feb 2026)**
- Implementation: `ConsolidationRunner` daemon thread (`src/agent/memory/consolidation_runner.py`)
- Starts: Automatically when the Agent Hub dashboard boots (`dashboard/app.py` at import time)
- First run: Immediately on startup
- Subsequent runs: Every 24 hours
- Scope: **All registered agents + `__multi_agent__`** — including stopped/inactive agents
- Survives dashboard reruns: Yes (daemon thread lives with the Streamlit process)
- Use case: Ensures memory improves continuously regardless of agent activity

**2. Counter-Based Trigger (Per-Agent, Legacy)**
- Triggers: Every 20 interactions within an active agent session
- Reset: After each consolidation
- Survives restarts: No (counter resets)
- Use case: Active sessions that need more frequent consolidation

**3. Manual Trigger**
- Triggers: `memory.run_consolidation()` called directly
- Use case: Testing, forced consolidation

### Consolidation Process

**Step 1: Pattern Extraction from Working Memory**

Analyzes last 50 interactions for:
- Frequent commands (3+ occurrences)
- Timeframe preferences (today, yesterday, week)
- Action preferences (count, list, delete patterns)
- Error patterns

**Output**: Updates `semantic_memory.md` → “Usage Patterns” section

**Step 2: Theme Extraction from Episodic Memory**

Analyzes events for:
- High-importance insights
- Recurring event types (2+ occurrences)
- Common contexts

**Output**: Updates `semantic_memory.md` → “Episodic Themes” section

**Step 3: Habit Detection (3+ Confirmations required)**

Analyzes 100 most recent interactions for:

- **Communication Pattern**
  - Question style: Inquisitive vs Direct vs Imperative
  - Requires: 7+ instances of same style
  
- **Work Pattern**
  - Time of day: Morning/Afternoon/Evening/Night
  - Requires: 5+ sessions in same time period
  
- **Learning Pattern**
  - Task complexity: Simple/Complex/Conversational
  - Requires: 5+ tasks of same type

- **Scheduled / Day-of-Week Patterns** *(added Feb 2026)*
  - Correlates day-of-week + action type (delete, send, schedule, OOO, archive, review)
  - Also correlates hour-of-day + action type
  - Requires: 3+ occurrences of the same (time, action) combination
  - Examples: “Tends to delete on Fridays (seen 4×)” · “Tends to send around 09:00 (seen 5×)”

**Output**: Adds to `habits.md` if threshold met

**Step 4: 90-Day Decay Mechanism**

For each episodic event older than 90 days:

| Importance | Action | Status |
| ---------- | ------ | ------ |
| Low        | Delete completely | ✅ Implemented — removed from episodic file |
| Medium     | Archive to `archive/episodic_YYYY_MM.md` | ✅ Implemented — file rewritten, archived to monthly files |
| High       | Keep in episodic memory | ✅ Always kept |

> The decay logic in `_apply_decay_mechanism()` correctly classifies events but the `episodic_memory.md` file is not actually rewritten — there is a `TODO` comment at the end of the method. The counts are logged only. This must be implemented before the file grows too large.

**Step 5: Consciousness Update (Every 2-4 Weeks)**

If 14+ days since last update:
- Synthesize user profile from semantic + habits
- Extract core patterns
- Update strategic direction insights

**Output**: Updates `consciousness.md`

### Code Flow

```python
# email_agent_ui.py - After every interaction

memory.add_interaction(command, action, result, metadata)
st.session_state.interaction_count += 1

consolidator = memory.get_consolidator()
if consolidator.should_consolidate(st.session_state.interaction_count):
    logger.info("Triggering consolidation")
    memory.run_consolidation()
    st.session_state.interaction_count = 0
    logger.info("Consolidation completed")
```

```python
# memory_consolidator.py - Consolidation logic

def consolidate(self):
    # Step 1
    patterns = self._extract_patterns_from_working_memory()
    if patterns:
        self._update_semantic_with_patterns(patterns)
    
    # Step 2
    themes = self._extract_themes_from_episodic()
    if themes:
        self._update_semantic_with_themes(themes)
    
    # Step 3
    new_habits = self._detect_habits()
    if new_habits:
        self._add_confirmed_habits(new_habits)
    
    # Step 4
    self._apply_decay_mechanism()
    
    # Step 5
    if self._should_update_consciousness():
        self._update_consciousness_layer()
    
    self.last_consolidation = datetime.now()
    self._save_state()  # Persist state
```

---

## State Persistence

### Problem Statement

**Without Persistence**:
```
Day 1: 15 interactions → No consolidation (need 20)
Agent STOPS
Day 2: Agent RESTARTS
       Counter = 0  ← LOST!
       last_consolidation = None  ← LOST!
       24-hour trigger won't work
Result: Need 20 NEW interactions to trigger
```

**With Persistence**:
```
Day 1: 15 interactions → No consolidation
       Consolidation last ran at 08:00 AM
       State saved to consolidation_state.json
Agent STOPS
Day 2: Agent RESTARTS (36 hours later at 08:00 PM)
       Loads state from disk
       last_consolidation = Day 1 08:00 AM
       Calculates: 36 hours passed
       ✅ Triggers consolidation immediately!
```

### Implementation

**State File**: `memory/{agent_id}/consolidation_state.json`

```json
{
  "last_consolidation": "2026-02-20T08:00:00.123456",
  "last_consciousness_update": "2026-02-15T14:30:00.987654"
}
```

**Load on Init**:
```python
def _load_state(self):
    if self.state_file.exists():
        with open(self.state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        if state.get('last_consolidation'):
            self.last_consolidation = datetime.fromisoformat(
                state['last_consolidation']
            )
```

**Save After Consolidation**:
```python
def _save_state(self):
    state = {
        'last_consolidation': self.last_consolidation.isoformat(),
        'last_consciousness_update': self.last_consciousness_update.isoformat()
    }
    with open(self.state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
```

**Startup Check** (`email_agent_ui.py`):
```python
if 'last_consolidation_check' not in st.session_state:
    st.session_state.last_consolidation_check = datetime.now()
    
    # Check if 24+ hours passed since last consolidation
    consolidator = memory.get_consolidator()
    if consolidator.last_consolidation:
        hours_since = (datetime.now() - consolidator.last_consolidation).total_seconds() / 3600
        if hours_since >= 24:
            logger.info(f"Triggering consolidation after restart ({hours_since:.1f} hours)")
            memory.run_consolidation()
```

---

## Usage Scenarios

### Scenario 1: Active Session with Many Interactions

```
08:00 AM - Agent starts
08:05 AM - User: "count emails today" (1)
08:10 AM - User: "list unread" (2)
08:15 AM - User: "delete junk" (3)
    ...
09:30 AM - User: 18th interaction
09:35 AM - User: 19th interaction
09:40 AM - User: 20th interaction
           ⚡ CONSOLIDATION TRIGGERS
           - Extract patterns (frequent commands)
           - Detect habits if 3+ confirmations
           - Update semantic memory
           - Save state to disk
           - Reset counter to 0
09:45 AM - User continues (counter starts from 0)
```

### Scenario 2: Low Activity + Overnight Stop

```
Day 1 - 08:00 AM:
    - Agent starts
    - User: 5 interactions
    - Last consolidation: None (first time)
    - Manually trigger consolidation to set baseline
    - State saved: last_consolidation = 08:00 AM
    
Day 1 - 10:00 PM:
    - Agent STOPS
    - Total interactions: 15 (below 20 threshold)
    
🌙 Overnight... (30 hours pass)

Day 2 - 02:00 PM:
    - Agent STARTS
    - Loads state: last_consolidation = Day 1 08:00 AM
    - Calculates: 30 hours passed
    - ⚡ TRIGGERS IMMEDIATELY (24+ hour rule)
    - Consolidation runs on startup
    - Updates state: last_consolidation = Day 2 02:00 PM
```

### Scenario 3: Habit Formation

```
Week 1:
    - User checks "count emails today" 2 times
    - Not a habit yet (need 3+)

Week 2:
    - User checks "count emails today" 5 more times
    - Total: 7 times
    - Consolidation runs:
      → Detects pattern: "count emails today" used 7x
      → Threshold met: 7 >= 3 ✓
      → Creates habit: "Frequent Commands: count emails today (7x)"
      → Saves to habits.md

Week 3 onwards:
    - LLM sees habit in memory context
    - LLM: "I notice you check your daily email count regularly.
           Would you like me to proactively report this each morning?"
```

### Scenario 4: Consciousness Evolution

```
Week 1-2:
    - User interactions accumulate
    - Semantic memory grows
    - Habits detected
    - Consciousness: Not updated yet

Week 3-4 (14+ days pass):
    - Consolidation checks: _should_update_consciousness()
    - Returns True (14+ days since last update)
    - Runs: _update_consciousness_layer()
      → Analyzes semantic memory
      → Analyzes habits
      → Synthesizes user profile
      → Updates consciousness.md:
        "User demonstrates systematic email management
         with growing automation preferences..."

Next day:
    - LLM loads consciousness context
    - LLM response includes meta-understanding:
      "Given your focus on efficiency and automation,
       I recommend setting up email filters..."
```

### Scenario 5: Memory Decay (90 Days)

> ⚠️ **Not yet fully implemented** — the decay *classification* runs but the file is not yet rewritten. Events accumulate until the TODO is resolved.

```
Day 1:
    - Event: "User deleted spam" (importance: Low)
    - Saved to episodic_memory.md

Day 91 (intended behaviour once TODO is resolved):
    - Consolidation runs
    - Checks event age: 91 days > 90 days
    - Importance: Low → DELETE from episodic_memory.md

High Importance events (always kept):
    - Event: "User set up critical email filter" (High)
    - Age: any → KEEP forever

Medium Importance events (90+ days):
    - Move to memory/{agent_id}/archive/episodic_YYYY_MM.md
```

---

## Code Reference

### Key Files

| File                                      | Purpose                                 | Notes |
| ----------------------------------------- | --------------------------------------- | ----- |
| `src/agent/memory/agent_memory.py`        | Core memory management class + `MULTI_AGENT_ID` constant | ~ 1140 lines |
| `src/agent/memory/memory_consolidator.py` | Consolidation engine: patterns, habits, consciousness, collective consciousness | ~830 lines |
| `src/agent/memory/consolidation_runner.py` | Global 24 h background thread — covers all agents | ~140 lines |
| `src/agent/memory/collective_memory.py`   | Episodic snapshot aggregator for Personal Assistant LLM context | ~140 lines |
| `src/agent/ui/dashboard/app.py`           | Dashboard entry — boots ConsolidationRunner + `__multi_agent__` memory on startup | |
| `src/agent/llm/llm_parser.py`             | LLM integration with memory context     | |

### Critical Functions

**Memory Operations** (`src/agent/memory/agent_memory.py`):
- `add_interaction()` — records to working + episodic memory on every turn
- `add_episodic_event()` — direct episodic write with custom insight
- `get_full_context_for_llm()` — assembles capped context for LLM (all normal turns)
- `recall_for_llm(query)` — on-demand episodic search for recall queries (see §11)
- `search_episodic_memory(query)` — keyword search across all episodic entries
- `remember(query)` — human-readable recall response (used by generic agent UI)

**Consolidation** (`src/agent/memory/memory_consolidator.py`):
- `consolidate()` — full consolidation cycle (6 steps; step 6 is PA hub only)
- `_extract_patterns_from_working_memory()` — working → semantic patterns
- `_extract_themes_from_episodic()` — episodic → semantic themes
- `_detect_habits()` — habit detection including day-of-week + time-of-day patterns (3+ threshold)
- `_apply_decay_mechanism()` — 90-day decay with file rewrite ✅
- `_update_consciousness_layer()` — reads ALL memory layers to write 7-section consciousness
- `_update_collective_consciousness()` — **PA hub only**; synthesises `collective_consciousness.md` from all skill agents

**Global Consolidation Runner** (`src/agent/memory/consolidation_runner.py`):
- `get_consolidation_runner()` — singleton accessor
- `ConsolidationRunner.start()` — idempotent; starts daemon thread
- `ConsolidationRunner._run_cycle()` — loops all agents, calls `MemoryConsolidator.consolidate()`

**State Persistence** (`src/agent/memory/memory_consolidator.py`):
- `_load_state()` — loads `consolidation_state.json` on init
- `_save_state()` — persists timestamps after each consolidation

**UI Integration**:
- `src/agent/ui/email_agent_ui.py::handle_conversation()` — gets full context + recall injection
- `src/agent/ui/generic_agent_ui.py::_handle_conversation()` — uses `memory.remember()` for recall

**LLM Integration** (`src/agent/llm/llm_parser.py`):
- `chat()` — injects `memory_context` as system prompt
- `orchestrate_mcp_tool()` — injects `memory_context` for tool routing decisions

---

## Testing

### Test Scripts

**1. Basic Consolidation Test**
```bash
python test_memory_consolidation.py
```
Tests:
- 25 interaction simulation
- Pattern extraction
- Habit detection
- Semantic memory updates
- Consolidation triggers

**2. Restart Persistence Test**
```bash
python test_restart_consolidation.py
```
Tests:
- State file creation
- State persistence across restarts
- 24-hour trigger after restart
- Counter trigger still works

### Manual Testing Checklist

**Working Memory**:
- [ ] Add interaction
- [ ] Verify appears in working_memory.md
- [ ] Add 11 interactions
- [ ] Verify oldest is removed (max 10)

**Episodic Memory**:
- [ ] Add episodic event
- [ ] Verify appears in episodic_memory.md with timestamp
- [ ] Verify importance level saved

**Consolidation - Counter Trigger**:
- [ ] Start fresh agent
- [ ] Perform 20 interactions
- [ ] Verify consolidation runs
- [ ] Check semantic_memory.md updated

**Consolidation - Time Trigger**:
- [ ] Run consolidation manually
- [ ] Check consolidation_state.json created
- [ ] Modify state file: set last_consolidation to 25 hours ago
- [ ] Restart agent
- [ ] Verify consolidation triggers on startup

---

## LLM Context Management

> This section answers three questions:
> 1. **What exactly is sent to the LLM as memory?**
> 2. **Is dumping all files a problem?**
> 3. **Do we need indexing?**

---

### What Gets Sent Today

Every LLM call goes through one of two paths:

#### Path A — Conversational (`llm.chat()`)

Called from `handle_conversation()` in `email_agent_ui.py` and `_handle_conversation()` in `generic_agent_ui.py`.

```
get_full_context_for_llm()
    ├─ personality.md          → full file (no cap)               ← uncapped ✅
    ├─ consciousness.md        → full file (no cap)               ← uncapped ✅
    ├─ working_memory.md       → last 10 interactions (~1 000 tokens)
    ├─ semantic_memory.md      → last 3 000 chars  (~750 tokens)  ← capped ✅
    ├─ habits.md               → last 3 000 chars  (~750 tokens)  ← capped ✅
    └─ episodic_memory.md      → NOT included (include_episodic=False by default)
```

This block is injected into the **system prompt** — the very first message in every API call.

#### Path B — Tool Routing (`llm.orchestrate_mcp_tool()`)

Called from `execute_with_llm_orchestration()` whenever the user issues an email action command.

```
get_full_context_for_llm()       ← same block as Path A
    → prepended to the USER message:
      "Memory Context:\n{memory_context}\n\nUser Query: {user_query}"
```

The full memory blob is sent here too, even though the LLM only needs to decide *which tool to call* — personality, consciousness, and habits are irrelevant for that decision.

---

### How Big Is the Context Right Now?

Measured on the existing `8aef0053` agent (Feb 2026):

| File                 | Size on disk | Sent to LLM? | How much?                     | Cap      |
| -------------------- | ------------ | ------------ | ----------------------------- | -------- |
| `personality.md`     | ~0.5 KB      | ✅            | Full file (no cap)            | —        |
| `consciousness.md`   | ~0.5 KB      | ✅            | Full file (no cap)            | —        |
| `working_memory.md`  | ~3.5 KB      | ✅            | Last 10 interactions (~1 KB)  | 10 items |
| `semantic_memory.md` | ~0.4 KB      | ✅            | Last 3 000 chars              | 3 000 ch |
| `habits.md`          | ~0.4 KB      | ✅            | Last 3 000 chars              | 3 000 ch |
| `episodic_memory.md` | ~2.4 KB      | ❌            | Not sent                      | —        |

**Current total context payload ≈ ~2 250 tokens max** — capped regardless of how large files grow.

A typical GPT-4o-mini system prompt + 10-message history + user message lands at **~1,500–2,000 tokens total**, well inside the 128K context window.

---

### Where the Problem Grows

The files that are always loaded in full — `semantic_memory.md` and `habits.md` — **grow unboundedly** with every consolidation run:

- Each consolidation adds new sections to `semantic_memory.md` (patterns, themes).
- Each confirmed habit adds a dated block to `habits.md`.
- There is **no size cap or truncation** applied before the content is handed to the LLM.

Projected growth (rough estimate):

| After    | Semantic memory | Habits | Estimated total context  |
| -------- | --------------- | ------ | ------------------------ |
| 1 month  | ~3 KB           | ~2 KB  | ~6 KB / ~1,500 tokens    |
| 6 months | ~20 KB          | ~10 KB | ~35 KB / ~8,750 tokens   |
| 2 years  | ~80 KB          | ~40 KB | ~130 KB / ~32,500 tokens |

GPT-4o-mini supports 128K tokens, so raw overflow is **not** the immediate concern.  
The real risks are:

1. **Token cost** — every message pays for the full memory payload.
2. **Latency** — larger prompts take longer to process.
3. **Attention dilution** — LLMs lose focus on recent/relevant content when the context has lots of old/stale information. This causes subtle hallucinations (fabricated "memories") and missed instructions buried deep in the prompt.
4. **Tool routing overhead** — `orchestrate_mcp_tool()` only needs 1–2 lines of user-preference context, not the entire memory blob.

---

### Current Problems (Ranked by Impact)

#### ~~Problem 1 — No size caps on semantic/habits files~~ ✅ FIXED

`get_full_context_for_llm()` now uses `_tail()` to cap each section before injection:

```python
# personality.md   → no cap (sent in full)
# consciousness.md → no cap (sent in full)
_LLM_SEMANTIC_CAP     = 3_000   # chars (~750 tokens)
_LLM_HABITS_CAP       = 3_000   # chars (~750 tokens)
_LLM_WORKING_MEM_CAP  = 10      # interactions
```

The `_tail()` helper keeps the **most recent** content (bottom of file, since new entries are appended) and prepends `...[earlier content trimmed]...` when truncation occurs. Files on disk are never modified — only the slice sent to the LLM is shortened.

---

#### Problem 2 — Full memory injected into tool routing (Medium impact, wastes tokens now)

`orchestrate_mcp_tool()` uses the same full context to make a simple decision like  
*"user said 'count emails today' → return `get_todays_messages`"*.

For tool routing the LLM needs at most:
- User's preferred result count (from semantic memory)
- Nothing else from personality, consciousness, or habits

**Fix needed**: A separate, slimmed `get_routing_context_for_llm()` function.

---

#### Problem 3 — No relevance filtering (Low impact now, high impact at scale)

The entire memory is concatenated unconditionally regardless of the current query.  
A user asking *"how many emails do I have today?"* receives the same memory payload as  
*"do you remember what I told you about my preferred work hours?"*

In the first case, personality, consciousness, and habits add noise.  
In the second case, episodic memory (which is not included by default) would be the most useful layer.

**Fix needed**: Query-aware context selection.

---

### Do We Need Indexing?

**Right now: No.** At current file sizes, loading full files is fast and cheap.

**In 6–12 months: Possibly.** Indexing becomes worth the complexity when:
- Any single memory file exceeds ~20 KB (≈5,000 tokens)
- You have many agents (each paying full context cost per message)
- Response quality drops due to attention dilution on stale content

The options in order of complexity:

#### Option A — Character cap (implement now, prevents future pain)

Add a `max_chars` parameter to `get_full_context_for_llm()`. Truncate each section independently, keeping the **most recent** content (bottom of file, since new entries are appended):

```python
def get_full_context_for_llm(self, include_episodic=False, max_chars_per_section=2000) -> str:
    semantic = self.get_semantic_memory()
    if len(semantic) > max_chars_per_section:
        semantic = "...(truncated)...\n" + semantic[-max_chars_per_section:]
    habits = self.get_habits()
    if len(habits) > max_chars_per_section:
        habits = "...(truncated)...\n" + habits[-max_chars_per_section:]
    ...
```

`max_chars=2000` per section ≈ 500 tokens each — keeps context comfortably under 3,000 tokens total.

---

#### Option B — Section-level extraction (medium complexity)

Parse the markdown headings in each file and only load sections that are relevant to the current query:

```python
def get_relevant_sections(file_content: str, query: str, top_n=3) -> str:
    # Split by ## headings
    # Score each section by keyword overlap with query
    # Return top N sections
```

This keeps context small without losing important information. No external libraries needed.

---

#### Option C — Vector embeddings (high complexity, not needed yet)

Embed each memory section as a vector using an embedding model (e.g. `text-embedding-3-small`). At query time, retrieve the top-k most similar sections.

**When to consider**: When Option B is insufficient — i.e., when files have hundreds of sections and keyword matching misses semantic relevance.

**Not recommended** until Option A fails — adds operational complexity (embedding storage, retrieval latency, cost) that is not justified at current scale.

---

### Done & Remaining

| Action                                                         | Status                                                     |
| -------------------------------------------------------------- | ---------------------------------------------------------- |
| Cap `semantic_memory.md` and `habits.md` before LLM injection  | ✅ Done — `_tail()` + per-section caps in `agent_memory.py` |
| Slim context variant for tool routing (`orchestrate_mcp_tool`) | ⬜ Still pending — would cut tool-routing token cost ~80%   |
| Query-aware context selection (Problem 3)                      | ⬜ Future work — not needed until files exceed 20 KB        |

---

### Context Monitoring

To observe real context sizes in production, add a debug log line in `get_full_context_for_llm()`:

```python
logger.debug(f"[Memory] Context size: {len(context)} chars / ~{len(context)//4} tokens")
```

And watch `email_agent.log` to catch growth before it becomes a problem.

---

### Summary Table

| Issue                               | Current state            | Impact               | Fix                                 |
| ----------------------------------- | ------------------------ | -------------------- | ----------------------------------- |
| `semantic_memory.md` loaded in full | Full file, unbounded     | High (future)        | Cap at 2,000 chars                  |
| `habits.md` loaded in full          | Full file, unbounded     | Medium (future)      | Cap at 2,000 chars                  |
| Full context in tool routing        | ~2KB (fine today)        | Medium (now)         | Use `get_routing_context_for_llm()` |
| No relevance filtering              | All layers always sent   | Low (now)            | Query-aware section selection       |
| Episodic not sent by default        | `include_episodic=False` | Intentional ✅        | Keep off by default                 |
| No vector indexing                  | Flat files               | None (current scale) | Revisit at >20KB per file           |

**Habit Detection**:
- [ ] Perform same action 7+ times
- [ ] Trigger consolidation
- [ ] Check habits.md for detected pattern

**LLM Memory Awareness**:
- [ ] Add interactions
- [ ] Trigger consolidation
- [ ] Ask conversational question
- [ ] Verify LLM references past interactions

---

## LLM Memory Guidelines

The LLM receives these instructions in its system prompt:

### Memory System Guidelines

**6 Layers Explained**:
1. **Working Memory** - Current context, last 10 interactions
2. **Episodic Memory** - Time-stamped events with importance levels
3. **Semantic Memory** - Distilled user knowledge and preferences
4. **Personality** - Your stable behavioral traits
5. **Habits** - Learned patterns (3+ confirmations required)
6. **Consciousness** - Meta-level understanding and goals

### Memory Usage Principles

- ✅ Draw from ALL relevant memory layers when responding
- ✅ Reference specific past interactions when they add value
- ✅ Adapt responses based on learned user preferences
- ✅ Connect current conversation to long-term patterns
- ✅ Be memory-aware: acknowledge continuity

### IMPORTANT - What LLMs CANNOT Do

- ❌ You CANNOT manually update memory files
- ❌ Don't say "I'll update my memory" or "I'm storing this"
- ✅ Memory consolidation happens AUTOMATICALLY in the background
- ✅ Your interactions are automatically recorded
- ✅ Patterns are automatically extracted after 20 interactions or 24 hours
- ✅ Habits are automatically detected after 3+ confirmations
- ✅ Old memories decay automatically after 90 days
- ✅ Your consciousness layer updates every 2-4 weeks

### What This Means for LLMs

- Focus on natural conversations - memory management is automatic
- Just BE yourself according to your personality - habits will be learned
- Reference memory naturally: "I remember when...", "Based on your preference for..."
- DO acknowledge patterns: "I've noticed you often ask about..."

---

## Architecture Decisions

### Why 6 Layers?

Based on cognitive science research:
- **Working Memory**: Matches human short-term memory capacity (7±2 items)
- **Episodic Memory**: Autobiographical memory system in humans
- **Semantic Memory**: Conceptual knowledge storage in human cognition
- **Personality**: Stable traits that guide behavior
- **Habits**: Learned behaviors that become automatic
- **Consciousness**: Meta-cognitive awareness and self-reflection

### Why Automatic Consolidation?

**Alternative 1**: Manual consolidation by LLM
- ❌ Unreliable: LLM might forget to trigger
- ❌ Token-expensive: Requires explicit instructions
- ❌ Inconsistent: Different prompts = different behavior

**Alternative 2**: User-triggered consolidation
- ❌ Poor UX: Users shouldn't think about memory management
- ❌ Forgotten: Users will forget to trigger

**Chosen**: Automatic background consolidation
- ✅ Reliable: Always runs at thresholds
- ✅ Transparent: Users don't need to know
- ✅ Consistent: Same logic every time
- ✅ Efficient: No LLM tokens wasted

### Why 3+ Confirmations for Habits?

- 1 confirmation: Could be accident or experiment
- 2 confirmations: Could be coincidence
- 3+ confirmations: Indicates real pattern

Statistical confidence increases with repetitions.

### Why 90-Day Decay?

Based on memory research:
- 30 days: Too short, recent memories still relevant
- 90 days: Balances retention vs. storage
- 180 days: Too long, stale data accumulates

Adjustable via `agent_memory.py::decay_days` property.

---

## Future Enhancements

### Planned Features

1. **LLM-Assisted Consolidation**
   - Use LLM to extract insights during consolidation
   - Better pattern recognition with natural language understanding
   
2. **Multi-Agent Memory Sharing**
   - Shared semantic memory across agents
   - Personal working/episodic memory per agent
   
3. **Memory Visualization**
   - Dashboard showing memory layers
   - Timeline view of episodic events
   - Pattern visualization
   
4. **Importance Scoring via LLM**
   - Auto-determine High/Medium/Low importance
   - Context-aware scoring
   
5. **Memory Search**
   - Natural language queries: "What did I do last Monday?"
   - Semantic search across all layers
   
6. **Memory Export/Import**
   - Backup memory to JSON
   - Transfer memory between systems
   
7. **Adaptive Thresholds**
   - Learn optimal consolidation frequency per user
   - Adjust habit confirmation threshold

---

## Troubleshooting

### Problem: Consolidation not triggering

**Check**:
1. Is `interaction_count` incrementing?
   - Look for: `st.session_state.interaction_count += 1`
2. Is consolidation check running?
   - Check logs: `logger.info("Triggering consolidation")`
3. Is state file created?
   - Check: `memory/{agent_id}/consolidation_state.json`

**Solution**: Enable debug logging in `email_agent_ui.py`

### Problem: State not persisting across restarts

**Check**:
1. Is state file present?
   - Path: `memory/{agent_id}/consolidation_state.json`
2. Is `_save_state()` being called?
   - Check logs: `logger.debug("Saved consolidation state")`
3. Is `_load_state()` being called on init?
   - Check logs: `logger.info("Loaded last consolidation")`

**Solution**: Verify file permissions, check JSON format

### Problem: Habits not being detected

**Check**:
1. Are there 100+ interactions?
   - Habit detection requires sufficient data
2. Are patterns repeated 3+ times?
   - Check working memory for repetitions
3. Is consolidation running?
   - Habits only detected during consolidation

**Solution**: Perform 20+ similar actions, trigger consolidation

### Problem: Memory context not loading in LLM

**Check**:
1. Is `get_full_context_for_llm()` being called?
   - Check in `handle_conversation()` and `execute_with_llm_orchestration()`
2. Are memory files populated?
   - Verify content in `memory/{agent_id}/*.md`
3. Is memory_context passed to LLM?
   - Check: `llm.chat(memory_context=memory_context)`

**Solution**: Enable logging in `llm_parser.py`, verify memory loading

---

## Performance Considerations

### Memory Size

- **Working Memory**: ~10 KB (10 interactions × 1 KB)
- **Episodic Memory**: ~100 KB (100 events × 1 KB)
- **Semantic Memory**: ~20 KB (accumulated knowledge)
- **Habits**: ~10 KB (learned patterns)
- **Personality**: ~5 KB (stable traits)
- **Consciousness**: ~10 KB (meta-summary)

**Total per agent**: ~155 KB

**For 100 agents**: ~15.5 MB

### Consolidation Performance

- **Time to consolidate**: ~1-2 seconds
- **Frequency**: Every 20 interactions or 24 hours
- **Impact**: Minimal (runs in background)

### LLM Token Usage

**Memory context size (maximum, all sections capped)**:
- Personality: variable (full file, typically ~100–500 tokens)
- Consciousness: variable (full file, typically ~100–400 tokens)
- Working Memory: ~1 000 tokens (last 10 interactions)
- Semantic Memory: ~750 tokens (3 000 char cap)
- Habits: ~750 tokens (3 000 char cap)
- On-demand recall (recall queries only): ~200–500 tokens extra

**Normal turn**: ~3 000–4 000 tokens typical (richer context than previous 2 250 cap)  
**Recall turn**: above + recalled episodic snippets (~3 500–4 500 tokens)

---

## On-Demand Episodic Recall

### Motivation

The standard `get_full_context_for_llm()` deliberately excludes the full episodic file to keep token usage bounded. But when a user asks *"do you remember when I asked about X?"* or *"what did you say about my work hours?"*, the most relevant memory is almost certainly in episodic history — not in the capped semantic/habits snippets.

This mirrors human recall: you don’t carry your entire life history in working memory, but when someone asks "do you remember that conversation?", you pause and search.

### How It Works

```
User message
    ↓
recall_for_llm(message) called
    ┣━ No recall signals detected? → return "" immediately (zero cost)
    ┗━ Recall signals found
           ┣━ Extract search terms (strip stop-words)
           ┣━ Keyword search: working_memory interactions
           ┣━ Keyword search: episodic_memory events
           ┗━ Section-match: semantic_memory
                   ↓
           Compact recall block assembled
                   ↓
memory_context = get_full_context_for_llm() + "\n\n" + recall_block
                   ↓
LLM called with augmented context (this turn only)
```

### Recall Signal Words

The following words/phrases in the user message trigger a recall search:

```
# Original signals:
remember, recall, did we, have we, last time, earlier, before,
previous, when did, what was, told you, mentioned, said,
talked about, discussed, do you know, you know that

# Added Feb 2026 — cover natural-language history queries:
did i, have i, ask you, asked you, any command, what did i,
do you remember, past week, this week, past month, this month,
ago, back, yesterday, recently, last few, history, previously,
any time, ever ask, ever told, commanded, instructed
```

If none of these appear, `recall_for_llm()` returns `""` immediately and adds zero overhead.

### Recall Stop Words

Before running the keyword search, temporal and filler words are stripped from the query so they don't poison the match:

```
past, week, month, day, days, ago, last, recently, back,
yesterday, today, now, perform, ask, asked, any, command,
commands, please, can, you, me, i, did, have, what, when,
how, ever, time, times, all, some, was, were, want, will
```

This means *"did I ask you to perform any commands past week?"* correctly extracts `[]` (empty keywords), which then triggers the temporal window fallback rather than a keyword-only search that would return nothing.

### Temporal Resolution

When the query contains a time expression, `recall_for_llm()` resolves it to a concrete date window before scanning episodic memory:

| Expression | Resolved to |
|---|---|
| `"yesterday"` | Single target date: yesterday |
| `"2 days ago"`, `"3 days ago"`, … | Single target date: N days back |
| `"past week"`, `"this week"` | Window: today − 7 days |
| `"last week"` | Window: today − 14 days to today − 7 days |
| `"past month"`, `"this month"` | Window: today − 30 days |
| `"last month"` | Window: today − 60 days to today − 30 days |

All episodic entries whose embedded ISO timestamp falls within the window are returned, regardless of keyword overlap.

### Output Format

```markdown
## On-Demand Memory Recall (retrieved for this query only)

### Recalled from Recent Interactions:
- [2026-02-20T09:15:00] count emails today → 25 emails
- [2026-02-19T08:30:00] list unread emails → 12 unread

### Recalled from Episodic Memory (past events):
- [2026-02-20] list: Can you count the total emails yesterday? | context: success (37 emails)
- [2026-02-19] conversation: Do you remember our past conversation?

### Recalled from Semantic Memory (learned knowledge):
User prefers daily email counts
- Peak usage: Morning hours
```

### Implementation

**Method**: `AgentMemory.recall_for_llm(query, max_episodic=5, max_working=3)`  
**File**: `src/agent/memory/agent_memory.py`

**Wired in**:
- `src/agent/ui/email_agent_ui.py::handle_conversation()` — appends recall block to context before `llm.chat()`
- `src/agent/ui/generic_agent_ui.py::_handle_conversation()` — uses `memory.remember()` for rule-based recall response (does not go through LLM)

### Why Not Vector Indexing?

| Scale                                                                              | Approach                                                                   |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Files < 5 KB (current)                                                             | Keyword search — <1 ms, no dependencies                                    |
| Files 5–20 KB                                                                      | Keyword search still adequate                                              |
| Files > 20 KB or semantic queries (*"when did I talk about something stressful?"*) | Vector embeddings (`text-embedding-3-small`) — adds cost, latency, storage |

At the current scale (a few hundred entries per agent), keyword search is the right choice. Vector indexing should only be evaluated when a single episodic file consistently exceeds 20 KB.

---

## Recall System Improvements

*Section added: February 22, 2026*

This section summarises the concrete fixes made to align the running implementation with the design spec above.

### Why These Fixes Were Needed

The memory system design was correct on paper but the implementation had several gaps:

1. LLM context was **too narrow** (5 interactions, truncated personality)
2. Episodic recall used **too few trigger phrases** — natural queries like "did I ask you?" were ignored
3. **Temporal noise words** like `past`, `week`, `ago` poisoned keyword searches, making them return nothing
4. **Episodic insights** were hardcoded placeholders, making search useless
5. Email commands were stored with **Medium** importance, risking decay

### Fix Summary

| # | Problem | Fix | File |
|---|---|---|---|
| 1 | Working memory sent 5 interactions | Changed to 10 | `agent_memory.py` |
| 2 | Personality capped at 1 500 chars | Removed cap — sent full | `agent_memory.py` |
| 3 | Consciousness capped at 1 000 chars | Removed cap — sent full | `agent_memory.py` |
| 4 | Habits capped at 1 500 chars | Raised to 3 000 chars | `agent_memory.py` |
| 5 | Only 16 recall signal phrases | Expanded to 38+ phrases | `agent_memory.py` |
| 6 | No temporal stop words | Added ~20 stop words | `agent_memory.py` |
| 7 | No temporal date resolution | Added window resolution | `agent_memory.py` |
| 8 | Episodic fallback gated on empty terms | Always fires if no events matched | `agent_memory.py` |
| 9 | Episodic insight hardcoded to `"User performed {action}"` | Dynamic meaningful string | `agent_memory.py` |
| 10 | Email commands stored as Medium importance | Changed to High | `agent_memory.py` |

### Key Code Locations

```python
# src/agent/memory/agent_memory.py

_RECALL_SIGNALS = frozenset({...})   # 38+ trigger phrases
_RECALL_STOP_WORDS = frozenset({...}) # temporal/filler noise words

class AgentMemory:
    def get_full_context_for_llm(self) -> str:
        # personality.md → full (no cap)
        # consciousness.md → full (no cap)
        # working_memory.md → last 10 interactions
        # habits.md → last 3 000 chars
        # semantic_memory.md → last 3 000 chars

    def recall_for_llm(self, query: str, ...) -> str:
        # 1. Check _RECALL_SIGNALS — bail early if no match
        # 2. Strip _RECALL_STOP_WORDS from query terms
        # 3. Resolve temporal expressions → target_dates or window
        # 4. Scan episodic entries — keyword + date window match
        # 5. Fallback: return last 5 episodic entries if nothing matched
        # 6. Scan working memory interactions — keyword match
        # 7. Scan semantic memory sections — keyword match
        # 8. Assemble and return recall block
```

---

## Conclusion

The Cognitive Memory Architecture provides agents with:

✅ **Human-like memory** - 6 layers mimicking cognitive processes  
✅ **Automatic learning** - Patterns extracted without manual intervention  
✅ **Persistent state** - Survives restarts and long gaps  
✅ **Memory-aware responses** - LLM draws from all relevant layers  
✅ **Bounded context** - Smart character caps prevent unbounded token growth  
✅ **On-demand recall** - Episodic memory searched when the user references the past  
✅ **Natural language recall** - 38+ signal phrases + temporal resolution ("past week", "2 days ago")  
✅ **Meaningful episodic insights** - Searchable descriptions instead of generic placeholders  
❌ **Decay file rewrite** - Not yet implemented (entries classified but file not updated)

---

**Document Version**: 1.2  
**Last Updated**: February 22, 2026  
**Authors**: AI Development Team  
**Status**: Production

