# LLM Call Analysis — How Many AI Calls Happen Per Query?

> **Purpose:** This document explains, in plain English, exactly how many LLM (AI model) calls happen for different types of user requests. Use this as a baseline when planning optimisations.

Last updated: 2026-02-27

---

## The Short Answer

| What you say | LLM calls (typical) | LLM calls (worst case) |
|---|:---:|:---:|
| Casual chat ("How are you?") | **2** | 2 |
| Single task ("Send an email to Alice") | **2–4** | 7 |
| Two-agent task ("Zip folder X and email me") | **5–8** | 25 |
| Three-agent task ("Download, zip, and email") | **7–12** | 31 |

---

## What is an "LLM Call"?

Every time the system asks the AI model a question and waits for an answer, that is **one LLM call**. Each call takes time (~1–5 seconds) and costs tokens.

Think of it like sending a text message to a very smart assistant. Each back-and-forth exchange is one call.

---

## The Two Loops Explained Simply

### Loop 1 — Per-Skill Loop (`run_skill_react`)

When one agent (e.g. the Email Agent) needs to do its job, it has a conversation with the AI:

```
Turn 1:  User: "Send email to bob@gmail.com"
         AI:   "I'll call send_email tool"
               → Tool runs → result comes back

Turn 2:  "Tool result: email sent"
         AI:   "OK, task is done. Final answer: ✅ Email sent."
```

This loop runs **up to 6 turns** per skill. Simple tasks finish in **1–2 turns**. Complex tasks (multiple tools needed) may take 3–6 turns.

**Each turn = 1 LLM call.**

---

### Loop 2 — Master Orchestrator Loop (`react_workflow`)

When the user's request needs **more than one agent** (e.g. Files agent + Email agent), a master loop coordinates them:

```
Turn 1:  User: "Zip my Documents folder and email me the zip"
         AI:   "I'll start by delegating to the Files agent"
               → Files agent runs its own 6-turn loop (Loop 1)
               → Files agent reports: "Done, zip is at C:\docs.zip"

Turn 2:  "Observation: zip created at C:\docs.zip"
         AI:   "Now I'll delegate to the Email agent"
               → Email agent runs its own 6-turn loop (Loop 1)
               → Email agent reports: "Email sent"

Turn 3:  "Observation: email sent"
         AI:   "Both done. Final answer: ✅ All complete."
```

This master loop runs **up to 12 turns**. Each delegation call triggers a full per-skill sub-loop.

**Each master turn = 1 LLM call. Each sub-agent turn = 1 more LLM call.**

---

## Detailed Breakdown by Query Type

### 1. Casual Chat
**Example:** "What's the weather like?" / "How are you?"

```
classify_intent()  → 1 call  (is this a command or chat?)
_chat_response()   → 1 call  (write the reply)
─────────────────────────────
Total: 2 calls
```

---

### 2. Single-Skill Command (via Personal Assistant)
**Example:** "Send an email to alice@example.com saying hello"

```
classify_intent()          → 1 call   (COMMAND detected)
run_skill_react()
  Turn 1: think + call tool → 1 call   (AI decides to call send_email)
  Tool: send_email runs     → 0 calls  (just code, no AI)
  Turn 2: confirm done      → 1 call   (AI writes final answer)
─────────────────────────────────────────
Typical total: 3 calls
Max total:     7 calls  (if 6 iterations needed)
```

---

### 3. Single-Skill Command (via Workflow Dashboard)
**Example:** "Download my latest invoice from Drive"

```
react_workflow() master loop
  Turn 1: AI decides to delegate to Drive agent  → 1 call
  run_skill_react() - Drive agent
    Turn 1: AI calls search_files tool            → 1 call
    Turn 2: AI calls download_file tool           → 1 call
    Turn 3: AI confirms done                      → 1 call
  Turn 2: Master AI sees result, calls final_answer → 1 call
─────────────────────────────────────────
Typical total: 5 calls
Max total:     13 calls (12 master + 6 sub-agent - 5 overlap minimum)
```

---

### 4. Two-Agent Command
**Example:** "Zip my Documents folder and email me the zip file"

```
react_workflow() master loop
  Turn 1: AI → delegate to Files agent           → 1 call
  ┌─ Files agent: run_skill_react()
  │  Turn 1: AI calls zip_folder tool            → 1 call
  │  Turn 2: AI confirms zip done                → 1 call
  └─ Returns: "zip at C:\Documents.zip"
  Turn 2: AI → delegate to Email agent           → 1 call
  ┌─ Email agent: run_skill_react()
  │  Turn 1: AI calls send_email_with_attachment → 1 call
  │  Turn 2: AI confirms email sent              → 1 call
  └─ Returns: "email sent"
  Turn 3: AI → final_answer                      → 1 call
─────────────────────────────────────────
Typical total: 7 calls
Max total:     25 calls (12 master + 6 files + 6 email + 1 classify)
```

---

### 5. Three-Agent Command
**Example:** "Download report.pdf from Drive, zip it with the Notes folder, then email me both"

```
react_workflow() master loop
  Turn 1: delegate to Drive agent                → 1 call
  ┌─ Drive agent: 1–3 turns                      → 1–3 calls
  Turn 2: delegate to Files agent                → 1 call
  ┌─ Files agent: 1–3 turns                      → 1–3 calls
  Turn 3: delegate to Email agent                → 1 call
  ┌─ Email agent: 1–3 turns                      → 1–3 calls
  Turn 4: final_answer                           → 1 call
─────────────────────────────────────────
Typical total: 9–13 calls
Max total:     31 calls (12 master + 6 + 6 + 6 + 1 classify)
```

---

## Where Each Loop Lives in Code

| What | File | Key function | Max iterations |
|------|------|------|:---:|
| Master multi-agent loop | `src/agent/workflows/master_orchestrator.py` | `react_workflow()` | 12 |
| Per-skill loop (all agents) | `src/agent/workflows/skill_react_engine.py` | `run_skill_react()` | 6 |
| Per-agent loop (legacy path) | `src/agent/ui/*/orchestrator.py` | `reason_and_act()` | 6 |
| Intent classification | `src/agent/workflows/router.py` | `detect_agents_needed()` | 1 (always) |
| Chat response | `src/agent/ui/personal_assistant/app.py` | `_chat_response()` | 1 (always) |

---

## Why So Many Calls?

The current design uses **Reason + Act (ReAct)** loops. This means the AI thinks step-by-step, one tool at a time. Each step needs a fresh LLM call to decide what to do next.

**Advantages:**
- Handles unexpected situations (tool fails → AI retries differently)
- Works for completely open-ended requests
- No upfront knowledge of what tools will be needed

**Disadvantages:**
- Many LLM calls = slow response times (10–30 seconds for complex queries)
- Each call costs tokens
- Predictable multi-step tasks (zip + email) don't need this flexibility

---

## Optimisation Opportunities

These are the main patterns where LLM calls can be reduced:

### Option A — Fast-Plan Path (Structured Execution)
For predictable request patterns (e.g. "zip folder X and email me"):
- Instead of letting the master loop figure it out turn-by-turn, make **1 LLM planning call** upfront
- Get back a complete JSON plan: `[zip_folder, send_email_with_attachment]`
- Execute the plan directly by calling service functions (no sub-agent loops)
- **Result:** 7 calls → 1 call for supported flows

### Option B — Tool Batching
Allow the per-skill ReAct loop to emit **multiple tool calls** in one turn instead of one.
- Currently: think → 1 tool → observe → think → 1 tool → ...
- Batched: think → [tool1, tool2, tool3] → observe all → final_answer
- **Result:** 3–6 calls per skill → 1–2 calls

### Option C — Cached Planning
For repeated requests (same user, same type of command), cache the step-plan and skip re-planning.
- **Result:** removes the master loop LLM cost on repeat queries

### Option D — Remove Classification Call
`detect_agents_needed()` uses 1 LLM call just to classify. A fast regex/keyword pre-filter could handle 80% of cases with 0 LLM calls.
- **Result:** saves 1 call on every request

---

## Summary for Planning

The biggest wins are:
1. **Fast-plan path** for zip/upload/email patterns → saves ~6 calls per request
2. **Tool batching** in per-skill loops → saves ~2–4 calls per skill used
3. **Keyword-first routing** before the LLM classifier → saves 1 call on every request

Current bottleneck: the master orchestrator's turn-by-turn delegation model calls the LLM every time it decides to hand off to a sub-agent, even when the sequence is completely predictable from the user's original request.
