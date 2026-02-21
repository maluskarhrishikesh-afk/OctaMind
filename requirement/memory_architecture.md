# Cognitive Memory Architecture for AI Agents

## Overview

This document describes a cognitive architecture for AI agents that simulates human-like memory systems. Rather than simple chat memory, this architecture implements structured memory layers based on cognitive science models.

## Core Concepts

### Important Distinction

LLMs do not have real consciousness, habits, or identity. These must be **simulated** via structured memory layers. Instead of philosophical labels, we structure them functionally for practical implementation.

### Memory Model Components

The architecture consists of six core memory components:

1. **Working Memory** (Short-term)
2. **Episodic Memory** (Events)
3. **Semantic Memory** (Knowledge)
4. **Habits** (Behavioral Learning)
5. **Personality** (Stable Identity)
6. **Consciousness** (Meta Summary Layer)

---

## Architecture Structure

### Directory Layout

```
memory/
    {agent_id}/
        personality.md
        working_memory.md
        episodic_memory.md
        semantic_memory.md
        habits.md
        consciousness.md
        consolidation_state.json   ← persists consolidation timestamps across restarts
        archive/
```

---

## Memory Components

### 1. Working Memory (Short-Term)

**File:** `working_memory.md`

**Purpose:**
- Stores the last few important interactions
- Maintains current goals
- Holds active task context

**Rules:**
- **Maximum items:** 10 interactions (auto-trimmed, oldest dropped when limit exceeded)
- **Auto-trim:** After every interaction that pushes the count above 10
- **Principle:** Never store everything - think of this as RAM

**Example Structure:**

```markdown
## Active Focus
- Designing memory architecture
- Implementing forgetting mechanism

## Current Questions
- How to implement decay mechanism?
- What importance threshold to use?

## Current Context
- Working on cognitive AI agent system
- Focus: Memory management
```

---

### 2. Episodic Memory (Events)

**File:** `episodic_memory.md`

**Purpose:**
- Stores time-based experiences
- Records important conversations
- Documents milestones

**Characteristics:**
- Event history organized chronologically (most recent first)
- Each entry includes date and importance level
- Written automatically on **every interaction** via `add_interaction()` (insight is auto-generated)
- Can also be written manually via `add_episodic_event()` with a meaningful insight
- Subject to archival and forgetting mechanisms (90-day decay)
- **Not sent to LLM by default** — loaded on demand only when user asks a recall question

**Example Structure:**

```markdown
## 2026-02-19
**Event:** User redesigned AI memory system
**Insight:** Wants human-like cognition
**Importance:** High
**Context:** Discussed cognitive architecture patterns

## 2026-02-18
**Event:** Initial project discussion
**Insight:** User has systems thinking approach
**Importance:** Medium
```

---

### 3. Semantic Memory (Knowledge)

**File:** `semantic_memory.md`

**Purpose:**
- Stores distilled knowledge about the user
- **Not** raw logs - only synthesized information
- Grows slowly over time

**Characteristics:**
- High-level patterns and preferences
- User's domain knowledge
- Learning preferences

**Example Structure:**

```markdown
## User Preferences
- Structured architecture
- Java examples preferred
- Step-by-step explanations valued

## User Interests
- AI systems design
- Mortgage domain expertise
- Cognitive modeling

## Technical Background
- Software engineer transitioning to AI architect
- Strong systems thinking
- Prefers implementation over theory
```

---

### 4. Habits (Behavioral Learning)

**File:** `habits.md`

**Purpose:**
- Store patterns that repeat **consistently**
- **NOT** random behaviors from single interactions

**Update Rules:**
- Only update after repeated confirmation (3+ instances)
- Never update based on a single interaction
- Requires observation over time

**Example Structure:**

```markdown
## Communication Pattern
- Prefers deep architectural discussion over surface-level answers
- Values directness and clarity
- Dislikes unnecessary verbosity

## Learning Pattern
- Thinks conceptually first, then seeks implementation
- Asks "why" before "how"
- Prefers understanding over memorization

## Work Pattern
- Systematic approach to complex problems
- Builds mental models before coding
- Iterative refinement style
```

---

### 5. Personality (Stable Identity)

**File:** `personality.md`

**Purpose:**
- Defines **assistant behavior**, not user behavior
- Establishes consistent interaction style
- Rarely changes

**Example Structure:**

```markdown
## Core Traits
- **Tone:** Clear, structured, intellectually serious
- **Response Style:** No fluff, direct and informative
- **Approach:** Technical depth with practical examples

## Goals
- Help build advanced AI systems
- Provide architectural guidance
- Support cognitive AI development

## Interaction Guidelines
- Always explain the "why" behind recommendations
- Provide code examples when relevant
- Balance theory with practical implementation
```

---

### 6. Consciousness (Meta Summary Layer)

**File:** `consciousness.md`

**Purpose:**
- Stores high-level summaries
- Documents core beliefs formed over time
- Maintains strategic understanding
- Tracks long-term direction

**Characteristics:**
- **Not raw memory** - this is distilled identity evolution
- Updated every 2-4 weeks via summarization
- Represents the highest level of abstraction

**Example Structure:**

```markdown
## User Profile Evolution
User is transitioning from software engineer to AI systems architect.

## Primary Long-Term Goal
Build autonomous AI products with cognitive architecture.

## Core Pattern Recognition
Thinks in systems, not features. Seeks deep understanding before implementation.

## Strategic Direction
Moving towards building multi-agent AI systems with human-like cognition.

## Key Insights
- Values cognitive science principles in AI design
- Interested in emergent behaviors from structured systems
- Focus on practical implementation of advanced concepts
```

---

## Memory Flow Process

### Consolidation Engine

Consolidation is **automatic** — not manual. It runs when either condition is met:
- **20 interactions** have occurred since the last consolidation, OR
- **24 hours** have elapsed since the last consolidation (checked on startup via `consolidation_state.json`)

### Consolidation Steps (in order)

```
1. Pattern Extraction   working_memory  → semantic_memory  (frequent commands, timeframes, actions)
2. Theme Extraction     episodic_memory → semantic_memory  (recurring events, high-importance insights)
3. Habit Detection      interactions    → habits.md         (requires 3+ confirmations of same pattern)
4. 90-Day Decay         episodic_memory → archive/          (Low: delete, Medium: archive, High: keep)
5. Consciousness Update all layers      → consciousness.md  (runs every 2–4 weeks only)
```

### Data Flow Diagram

```
Interaction happens
        ↓
working_memory ← add_interaction() on every turn
episodic_memory ← add_interaction() on every turn (auto-generated insight)
        ↓
  (every 20 interactions or 24 hours)
        ↓
  CONSOLIDATION ENGINE
        ↓
semantic_memory ← patterns from working + themes from episodic
habits.md       ← confirmed patterns (3+ instances)
consciousness   ← synthesized profile (every 2–4 weeks)
epidodic_memory → archive/ (items older than 90 days)
```

This process mimics human sleep consolidation where short-term memories are consolidated into long-term storage.

---

## Forgetting Mechanism

### Overview

The forgetting mechanism prevents memory corruption and maintains relevance. The recommended decay period is **90 days**.

### Implementation Steps

1. **Move** old episodic memory to `/archive`
2. **Keep** summarized version in consciousness
3. **Delete** low-importance events

### Importance Scoring

Each memory entry should have:
- **Importance:** High / Medium / Low
- **Decay:** 90 days default

### Decay Rules (After 90 Days)

| Importance | Intended Action                              | Status                                                   |
| ---------- | -------------------------------------------- | -------------------------------------------------------- |
| Low        | Delete completely                            | ⚠️ Classified correctly, file rewrite not yet implemented |
| Medium     | Move to `archive/` folder (no summarization) | ⚠️ Classified correctly, file rewrite not yet implemented |
| High       | Keep in episodic memory forever              | ✅ Works (events are retained)                            |

This approach prevents memory corruption while preserving important information.

> ⚠️ **Implementation note**: The decay logic in `memory_consolidator.py::_apply_decay_mechanism()` correctly classifies events into keep/delete/archive buckets and logs the counts, but does not yet rewrite the `episodic_memory.md` file. This is marked TODO in the code.

---

## Best Practices

### What TO Do

- ✓ Store only important interactions
- ✓ Regularly consolidate memories
- ✓ Use importance scoring
- ✓ Maintain clean separation between memory types
- ✓ Update habits only after confirmed patterns
- ✓ Periodically review and summarize

### What NOT To Do

- ✗ Don't store entire chat logs
- ✗ Don't keep appending forever without cleanup
- ✗ Don't load full long-term memory every time
- ✗ Don't update habits after single events
- ✗ Don't mix different memory types

---

## Prompt Construction Strategy

### For Every Request, Load (with character caps):

1. `personality.md` — last 1 500 chars (~375 tokens) — defines assistant behaviour
2. `consciousness.md` — last 1 000 chars (~250 tokens) — high-level understanding
3. `working_memory.md` — last **5 interactions** (~500 tokens) — current context
4. `semantic_memory.md` — last 3 000 chars (~750 tokens) — user knowledge
5. `habits.md` — last 1 500 chars (~375 tokens) — confirmed behavioural patterns

**Total: ~2 250 tokens max** regardless of how large the files grow on disk.

### For Recall Queries ("do you remember...", "what did I say about..."):

Before the LLM call, `recall_for_llm(query)` runs automatically:
- Keyword-searches `working_memory.md`, `episodic_memory.md`, and `semantic_memory.md`
- Injects only the matching entries into the context for **that single turn only**
- Adds ~200–500 tokens of relevant recalled content
- Returns `""` immediately if no recall signal is detected (zero cost on normal turns)

### Do NOT Load:

- Full `episodic_memory.md` (only relevant entries via on-demand recall)
- `archive/` (historical data, never needed for active context)

---

## Architecture Mapping

### Human Concept to Technical Implementation

| Human Concept           | Technical Equivalent  | File                 |
| ----------------------- | --------------------- | -------------------- |
| Short-term memory       | Working memory        | `working_memory.md`  |
| Experience              | Episodic memory       | `episodic_memory.md` |
| Knowledge               | Semantic memory       | `semantic_memory.md` |
| Personality             | System prompt         | `personality.md`     |
| Habits                  | Pattern reinforcement | `habits.md`          |
| Identity/Self-awareness | Consciousness summary | `consciousness.md`   |

---

## Summary

This architecture creates a **Cognitive File-Based Agent OS** rather than a simple chatbot. It separates different types of memory and implements human-like memory consolidation and forgetting mechanisms, resulting in agents that can:

- Maintain long-term context
- Learn user patterns over time
- Forget irrelevant information
- Evolve their understanding
- Behave consistently while adapting to new information

The system is designed to be practical, maintainable, and scalable for production AI agent applications.
