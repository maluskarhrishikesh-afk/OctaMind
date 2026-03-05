"""
Personal Assistant Chat UI — Streamlit page.

Handles cross-agent commands that involve both the Drive Agent and Email Agent.
Commands are analysed → plan is shown → steps execute sequentially with live
progress tracking → results summarised.

Accent: purple (#7c3aed / rgb 124,58,237)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.agent.ui.dashboard.styles import inject_agent_css
from src.agent.ui.personal_assistant.helpers import _logo_b64, _logo_icon, _logo_path, _logo_pinkraven, _start_browser_watchdog, get_running_agents
from src.agent.hub.pa_manager import load_assistants, create_assistant, delete_assistant
from src.agent.context.conversation_state import build_structured_query as _build_structured_query

# ── Logging ───────────────────────────────────────────────────────────────────
# Logging is initialised in main() once the PA name is known so the log file
# is named after the actual PA (e.g. logs/Alice.log).  The import is at
# module level so the logger object is available for module-level code.
from src.agent.logging.log_manager import (
    setup_pa_logging, bind_correlation, new_correlation_id,
    bind_request, new_request_id,
)
logger = logging.getLogger("personal_assistant")

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
))

import re as _re

# ── Lazy workflow imports ───────────────────────────────────────────


def _import_workflows():
    from src.agent.workflows import detect_agents_needed, run_workflow
    return detect_agents_needed, run_workflow


# ── Emotion detection ────────────────────────────────────────────────────────
# Zero extra LLM calls — pure regex keyword scan.
# Returns (label, guidance) on a match, None otherwise.
_EMOTION_RULES: list[tuple[str, str, str]] = [
    (
        r"\b(angry|furious|infuriating|outrage|outraged|ridiculous|useless|hate this|fed up|terrible|horrible|awful|disgusting)\b",
        "angry",
        "The user appears angry or frustrated. Start by warmly acknowledging their feelings — do NOT be dismissive or defensive. Then address their request calmly and helpfully.",
    ),
    (
        r"\b(frustrated|annoying|annoyed|irritated|not working|broken|waste|again|still doesn.{0,5}t|never works|always wrong|keep failing|keeps failing)\b",
        "frustrated",
        "The user seems frustrated. Acknowledge this gently first. Be concise and focus on solving the problem directly.",
    ),
    (
        r"\b(sad|depressed|upset|hopeless|worthless|miserable|lonely|overwhelmed|can.{0,5}t cope|crying|feeling low|feeling down)\b",
        "sad_low",
        "The user may be feeling low or overwhelmed. Lead with warmth and compassion. Offer encouragement before practical advice.",
    ),
    (
        r"\b(stressed|panic|panicking|urgent|emergency|asap|right now|immediately|deadline|in trouble|please help|help me now)\b",
        "stressed",
        "The user appears stressed or in an urgent situation. Be calm and decisive — prioritise the most important action first and give a direct answer.",
    ),
    (
        r"\b(should i quit|thinking of quitting|about to quit|want to quit|give up|give everything up|drop out|delete everything|delete all|leave everything|start over completely)\b",
        "major_decision",
        "The user may be considering a major or irreversible decision. Be thoughtful and non-judgmental. Gently acknowledge their situation, ask ONE clarifying question if helpful, and do NOT encourage hasty action.",
    ),
]

_EMOTION_EMPATHY_OPENERS: dict[str, str] = {
    "angry":         "I hear you — let's work through this together. ",
    "frustrated":    "I understand your frustration. ",
    "sad_low":       "I'm here for you. ",
    "stressed":      "No worries, I've got this. ",
    "major_decision": "That's a big decision — take a breath. ",
}


def _detect_emotion(message: str) -> tuple[str, str] | None:
    """
    Quick keyword-based emotion scan (zero LLM calls).
    Returns (label, empathy_guidance_for_llm) or None.
    Only the first matching rule fires (ordered by severity).
    """
    for pattern, label, guidance in _EMOTION_RULES:
        if _re.search(pattern, message, _re.IGNORECASE):
            return label, guidance
    return None


# ── Scheduling follow-up enrichment ─────────────────────────────────────────
# When a user replies with a bare time (e.g. "2 PM to 3 PM") after the
# scheduler agent has suggested slots, the router's keyword pre-filter
# finds no agent keywords and treats the message as conversational —
# leading the LLM to say "I've scheduled…" without actually booking anything.
# This helper detects that pattern and enriches the command so the router
# correctly routes it to the scheduler agent, which will create the event.

_BARE_TIME_PATTERN = _re.compile(
    r"""^\s*
    \d{1,2}(?::\d{2})?          # start hour (e.g. 2 or 10:30)
    \s*(?:am|pm|AM|PM)          # AM/PM
    (?:
        \s*(?:to|\-|–|till|until)\s*   # optional range separator
        \d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)  # end hour
    )?
    \s*$""",
    _re.VERBOSE | _re.IGNORECASE,
)

_SCHEDULING_CONTEXT_KEYWORDS = frozenset({
    "schedule", "meeting", "slot", "free", "available", "book",
    "calendar", "appointment", "block", "time", "best time",
})

# Detect scheduling verbs & nouns in the user's own command (for Case 3)
_CMD_SCHEDULING_VERB_RE = _re.compile(
    r"\b(schedule|book|set\s+up|add|create|plan)\b", _re.IGNORECASE
)
_CMD_SCHEDULING_NOUN_RE = _re.compile(
    r"\b(meeting|session|appointment|call|event|standup|sync|block)\b", _re.IGNORECASE
)
_CMD_TIME_RE = _re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", _re.IGNORECASE
)

# Temporal references to carry forward into the enriched scheduling command.
# Scans BOTH user and assistant messages so dates spoken by either party
# are captured and injected into the new command.
_TEMPORAL_PATTERN = _re.compile(
    r"\b("
    # Ordinal day + month with SPACE before ordinal suffix (e.g. "8 th March", "3 rd April")
    r"\d{1,2}\s+(?:st|nd|rd|th)\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*"
    # Ordinal day + month with NO space before suffix (e.g. "8th March", "3rd April")
    r"|\d{1,2}(?:st|nd|rd|th)\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*"
    # Bare day + month name (e.g. "8 March", "3 April")
    r"|\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"|tomorrow|today|tonight|yesterday"
    r"|next\s+\w+"
    r"|this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|weekend|morning|afternoon|evening)"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?"
    r")\b",
    _re.IGNORECASE,
)


# Detect when the assistant's last reply was soliciting the event title / details.
# Covers phrasings like "What event title shall I use?", "provide event details", etc.
_ASSISTANT_ASKING_TITLE_RE = _re.compile(
    r"(what.*event|event.*title|event.*name|name.*event|title.*event"
    r"|what would you like to (name|call)|title.*meeting|meeting.*title"
    r"|provide.*title|provide.*name|provide.*detail|what.*detail"
    r"|event/appointment title|appointment.*title|title.*appointment"
    r"|shall i use|what.*call (it|the)|title.*use\?)",
    _re.IGNORECASE,
)


def _enrich_scheduling_followup(command: str, history: list) -> str:
    """
    Enriches follow-up messages in a scheduling conversation so the router
    correctly dispatches them to the calendar agent instead of treating them
    as conversational noise.

    Handles three cases:
    1. Bare time reply — e.g. '2 PM to 3 PM' after the bot suggested slots.
    2. Event-title reply — e.g. 'Abs Gym' after the bot asked for a title.
    3. Scheduling command with time but no date — e.g. 'Schedule a meeting at
       8 PM for Gym Session' after the bot confirmed '12th March is free'.
       The date from history is injected so quick_add_event receives a fully-
       qualified expression and doesn't silently fall back to today's date.

    Temporal context (dates like '7th March', 'tomorrow') is extracted from
    recent history and injected into the enriched command so the calendar agent
    books on the right date.
    """
    stripped = command.strip()

    # ── Case 1: bare time reply ──────────────────────────────────────────────
    if _BARE_TIME_PATTERN.match(stripped):
        recent_messages = history[-6:] if len(history) >= 6 else history
        recent_text = " ".join(m.get("content", "") for m in recent_messages).lower()

        if any(kw in recent_text for kw in _SCHEDULING_CONTEXT_KEYWORDS):
            date_context = ""
            all_temporal = _TEMPORAL_PATTERN.findall(recent_text)
            if all_temporal:
                best_match = max(all_temporal, key=len)
                date_context = f" on {best_match}"
            return f"Schedule a calendar meeting / book the time slot for {stripped}{date_context}"

    # ── Case 2: event-title follow-up ───────────────────────────────────────
    # Trigger when: the phrase is short (≤8 words, ≤80 chars), is not itself
    # a question, the recent conversation is about scheduling, AND the last
    # assistant message was asking for a title / event details.
    if (
        len(stripped) <= 80
        and not stripped.endswith("?")
        and len(stripped.split()) <= 8
    ):
        recent_messages = history[-8:] if len(history) >= 8 else history
        recent_text_full = " ".join(m.get("content", "") for m in recent_messages)
        recent_text_lower = recent_text_full.lower()

        if any(kw in recent_text_lower for kw in _SCHEDULING_CONTEXT_KEYWORDS):
            last_assistant_msg = ""
            for m in reversed(recent_messages):
                if m.get("role") == "assistant":
                    last_assistant_msg = m.get("content", "")
                    break

            if last_assistant_msg and _ASSISTANT_ASKING_TITLE_RE.search(last_assistant_msg):
                # Extract date context from history
                date_context = ""
                all_temporal = _TEMPORAL_PATTERN.findall(recent_text_lower)
                if all_temporal:
                    best_match = max(all_temporal, key=len)
                    date_context = f" on {best_match}"
                # Extract time context from history (reuse for completeness)
                time_context = ""
                _time_m = _re.search(
                    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*(?:to\s*\d{1,2}(?::\d{2})?\s*(?:am|pm))?",
                    recent_text_lower, _re.IGNORECASE,
                )
                if _time_m:
                    time_context = f" at {_time_m.group()}"
                return (
                    f"Schedule a '{stripped}' event{date_context}{time_context}"
                    f" in my calendar"
                )

    # ── Case 3: scheduling command with time but no date ────────────────────
    # Trigger when: user issues a scheduling command that contains a time
    # (e.g. "at 8 PM") but no explicit date, while recent history mentions a
    # specific date (e.g. the assistant just said "12th March is free").
    # We inject the date directly into the command string so the calendar LLM
    # and quick_add_event always receive a fully-qualified date+time, eliminating
    # the risk of the event being booked on today's date by default.
    if (
        _CMD_SCHEDULING_VERB_RE.search(stripped)
        and _CMD_SCHEDULING_NOUN_RE.search(stripped)
        and _CMD_TIME_RE.search(stripped)
        and not _TEMPORAL_PATTERN.search(stripped)          # no date in the command itself
    ):
        recent_messages = history[-8:] if len(history) >= 8 else history
        _vague_re = _re.compile(
            r"^(today|tonight|yesterday|monday|tuesday|wednesday|"
            r"thursday|friday|saturday|sunday|march|april|may|"
            r"june|july|august|september|october|november|december|"
            r"january|february)$", _re.IGNORECASE
        )

        # Prefer dates from the most recent USER message (user intent is
        # authoritative). Old ASSISTANT confirmations can contain stale dates
        # (e.g. a prior booking on "11th March") that would otherwise win via
        # max(key=len) since they often include the year ("11th March 2026").
        best_date = None
        for msg in reversed(recent_messages):
            if msg.get("role") != "user":
                continue
            user_temporal = _TEMPORAL_PATTERN.findall(msg.get("content", "").lower())
            concrete = [t for t in user_temporal if not _vague_re.match(t.strip())]
            if concrete:
                best_date = max(concrete, key=len)  # longest within single message
                break

        # Fall back to all messages (both user and assistant) if no user date found
        if not best_date:
            recent_text_lower = " ".join(m.get("content", "") for m in recent_messages).lower()
            all_temporal = _TEMPORAL_PATTERN.findall(recent_text_lower)
            concrete_all = [t for t in all_temporal if not _vague_re.match(t.strip())]
            if concrete_all:
                best_date = max(concrete_all, key=len)

        if best_date:
            return f"{stripped} on {best_date}"

    return command


def _inject_conversation_context(command: str, history: list) -> str:
    """
    Enriches a skill-agent command with a structured JSON state block derived
    from the conversation history.

    Replaces the old free-text context prepend with a deterministic
    ``## Session State`` JSON section that the LLM can read unambiguously.
    Entities are RESOLVED before injection (e.g. "12th March" → "2026-03-12")
    so the skill agent receives exact values, not raw text.

    Example output (appended after the task):

        Schedule a meeting at 8 PM for Gym Session

        ## Session State (structured — prefer these resolved values over raw text)
        {
          "current_date": "2026-03-04",
          "timezone": "IST (UTC+05:30)",
          "active_date": "2026-03-12",
          "active_time_start": "20:00",
          "last_assistant_action": "Your calendar is completely free on 12th March …"
        }
    """
    if not history:
        return command  # No history — nothing to enrich

    enriched = _build_structured_query(command, history)

    # ── Log the resolved Session State for observability ─────────────────
    try:
        from src.agent.context.conversation_state import _default_tracker as _tracker
        import json as _json_log
        _state = _tracker.build(history, command)
        _state_str = _json_log.dumps(_state, ensure_ascii=False)
        logger.info("┤ [SESSION STATE] %s", _state_str)
    except Exception:
        pass

    return enriched


def _chat_response(message: str, agent_name: str, agent_id: str = None,
                   emotion_hint: str = "", history: list = None) -> str:
    """
    Handle conversational (non-workflow) messages via the LLM.
    Used when the command doesn't involve multiple agents.

    history: the PA-namespaced message list from session state so the LLM
    receives proper conversation context.  When omitted the last 10 messages
    from st.session_state are used as a safe fallback.
    """
    try:
        from src.agent.llm.llm_parser import get_llm_client
        from src.agent.memory.agent_memory import get_agent_memory
        from src.agent.memory.collective_memory import get_collective_context

        # Collective consciousness — pull memory from ALL registered agents
        memory_context = ""
        try:
            memory_context = get_collective_context()
        except Exception as mem_err:
            logger.debug("Collective memory load skipped: %s", mem_err)

        # Inject emotion guidance so the LLM responds with appropriate empathy
        if emotion_hint:
            memory_context = (
                f"[Emotional Context — respond with empathy first: {emotion_hint}]\n\n"
                + memory_context
            )

        # Layer on per-message recall from own memory
        if agent_id:
            try:
                own_memory = get_agent_memory(agent_id)
                recalled = own_memory.recall_for_llm(message)
                if recalled:
                    memory_context += f"\n\n{recalled}"
            except Exception as mem_err:
                logger.debug("Recall skipped: %s", mem_err)

        conversation_history = []
        # Use the caller-supplied history (PA-namespaced) for accurate context;
        # fall back to any chat_messages key as a last resort.
        _hist_source = history if history is not None else st.session_state.get("chat_messages", [])
        for m in _hist_source[-10:]:
            conversation_history.append(
                {"role": m["role"], "content": m["content"]})

        llm = get_llm_client()
        response = llm.chat(
            user_message=message,
            agent_name=agent_name,
            agent_type="Personal Assistant",
            memory_context=memory_context,
            conversation_history=conversation_history,
        )

        # Record interaction to memory
        if agent_id and response:
            try:
                memory = get_agent_memory(agent_id)
                memory.add_interaction(
                    command=message,
                    action="conversation",
                    result={"status": "success", "response": response[:200]},
                    importance="Medium",
                )
            except Exception as mem_err:
                logger.debug("Memory record skipped: %s", mem_err)

        return response
    except Exception as exc:
        logger.warning("LLM chat fallback failed: %s", exc)
        return (
            "I'm your Personal Assistant — I can run commands that combine both your "
            "Drive Agent and Email Agent. Try something like: "
            "*'Download the Q3 report and email it to alice@example.com'*."
        )


# ── Usage Guide dialog ───────────────────────────────────────────────────────
@st.dialog("📖 Personal Assistant Usage Guide", width="large")
def _show_multi_agent_guide() -> None:
    st.markdown("""
## ⚡ What can your Personal Assistant do?

Your Personal Assistant lets you give **combined Drive + Email commands** in a single
sentence. Octa Bot automatically plans which agents to use and in what order.

---

## 📁➡️✉️ Drive → Email workflows

| Command | What happens |
|---------|--------------|
| `Download the Q3 report and send it to alice@example.com` | Drive finds & downloads file, Email attaches & sends |
| `Find the invoice PDF and email it to bob@example.com` | Drive searches, Email sends with attachment |
| `Get the project proposal and draft an email to the team` | Drive retrieves file, Email creates draft |
| `Download the latest report and send a summary to manager@co.com` | Drive downloads, AI summarises, Email sends |

## ✉️➡️📁 Email → Drive workflows

| Command | What happens |
|---------|--------------|
| `Save the attachment from email <id> to my Drive` | Email downloads attachment, Drive uploads |
| `Upload the file from today's email to the Project folder` | Email gets attachment, Drive stores it |

## 🤝 Combined queries

| Command | What happens |
|---------|--------------|
| `Share the Q4 spreadsheet with everyone who emailed me today` | Drive finds file, Email finds senders, Drive shares |
| `Email me a storage report` | Drive generates report, Email sends it to you |

---

## 💡 Tips
- Be specific about **file names** and **email recipients** for best results.
- The planner shows each step as it executes — you can see what's happening in real time.
- If a step fails, the workflow stops and explains what went wrong.
- Personal Assistant commands work best when **both** agents are running (check the sidebar).
    """)


# ── Formatting helpers ───────────────────────────────────────────────────────

import json as _json


def _format_step_badge(agent: str) -> str:
    if agent == "drive":
        return "📁 Drive"
    elif agent == "email":
        return "✉️ Email"
    return f"🤖 {agent.title()}"


def _render_step_result(step_result: dict) -> str:
    """Build a compact status line shown during live workflow execution."""
    status_icon = "✅" if step_result["status"] == "success" else "❌"
    agent = step_result.get("agent", "?")
    tool = step_result.get("tool", "?")
    label = _format_step_badge(agent)
    line = f"{status_icon} **{label}** — `{tool}`"
    if step_result["status"] == "error":
        # step_result["error"] can be None — fall back to nested message.
        _err = (
            step_result.get("error")
            or (step_result.get("result") or {}).get("message")
            or "Unknown error"
        )
        line += f"\n   ⚠️ {_err}"
    return line


def _compose_final_response(run_result: dict, original_command: str) -> str:
    """
    Pass raw step results directly to the LLM and let it compose a friendly,
    conversational final response. No pre-processing — the LLM sees everything.
    """
    from src.agent.llm.llm_parser import get_llm_client

    steps = run_result.get("steps", [])

    steps_payload = [
        {
            "agent": sr.get("agent"),
            # Use the human-readable instruction/description for the compose LLM
            "task": sr.get("instruction") or sr.get("tool", "?"),
            "status": sr.get("status"),
            # Flatten nested result dicts (new NL runner returns {"message":..., "artifacts":...})
            "result": (
                sr.get("result", {}).get("message")
                if isinstance(sr.get("result"), dict)
                else sr.get("result")
            ),
            "error": sr.get("error"),
        }
        for sr in steps
    ]

    composition_prompt = f"""The user asked: "{original_command}"

A cross-agent workflow was executed. Here are the raw results from each step:

{_json.dumps(steps_payload, indent=2, default=str)}

Compose a response following these formatting rules:
- Write in a friendly, conversational tone like a helpful assistant
- Use **bold** for important names, counts, and key values
- Use bullet points or numbered lists to present multiple items
- Use tables (markdown) when comparing or listing structured data (e.g. files, emails)
- Use relevant emojis to make the response visually engaging (e.g. 📁 for files, ✉️ for emails, ✅ for success)
- Add a brief summary sentence at the start so the user knows what happened
- If there are many items, show the most important ones and mention the total count
- Do NOT show raw field names, JSON keys, or technical IDs unless they are needed for the user to act on them
- Do NOT mention tool names or agent internals"""

    llm = get_llm_client()
    try:
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Compose clear, friendly markdown responses from raw tool results."},
                {"role": "user", "content": composition_prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
            timeout=40,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Final response composition failed: %s", exc)
        return "✅ Workflow completed. " + ("Steps: " + ", ".join(s.get("tool", "?") for s in steps) if steps else "No steps recorded.")


def _render_workflow_output(run_result: dict, original_command: str = "") -> str:
    """Build the full assistant message for a completed workflow."""
    status = run_result.get("status", "error")
    plan = run_result.get("plan")
    steps = run_result.get("steps", [])
    elapsed = run_result.get("elapsed", 0)

    parts = []

    # ReAct mode: orchestrator already composed the final answer — use it directly
    # (avoids a second LLM call just for formatting)
    if run_result.get("final_answer") and status in ("success", "partial"):
        return run_result["final_answer"]

    if status == "success":
        return _compose_final_response(run_result, original_command)
    elif status == "partial":
        parts.append(
            "⚠️ **Workflow partially completed** — one or more steps failed.")
    else:
        parts.append("❌ **Workflow failed.**")

    if plan:
        parts.append(f"\n**Plan:** {plan.command}")

    parts.append(f"\n**Steps executed** ({len(steps)}) in {elapsed:.1f}s:\n")
    for r in steps:
        parts.append(_render_step_result(r))

    if status == "error" and not steps:
        parts.append(
            "\n🤔 I wasn't sure what to do with that. "
            "Could you rephrase or give me a bit more detail? "
            "For example: *'Find my payslip files and email them to me'* "
            "or *'Zip the Payslips folder and send it to my email'*."
        )

    return "\n".join(parts)


# ── Live Channels feed (auto-refreshing fragment) ───────────────────────────

_SOURCE_ICONS = {
    "telegram": "✈️",
    "whatsapp": "💬",
    "api": "🔌",
    "dashboard": "🖥️",
    "unknown": "📡",
}
_SOURCE_COLORS = {
    "telegram": "#229ED9",
    "whatsapp": "#25D366",
    "api": "#7c3aed",
    "dashboard": "#e91e8c",
    "unknown": "#888",
}
_CONV_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "hub_conversations.json"


import threading as _threading

_dashboard_chat_lock = _threading.Lock()


def _persist_dashboard_chat(pa_id: str, messages: list) -> None:
    """
    Write the current Dashboard chat session to hub_conversations.json so
    the consolidation engine can pick it up alongside Telegram / WhatsApp
    conversations.  Session key is ``dashboard_<pa_id>`` and source is
    ``"dashboard"``.
    """
    from datetime import timezone as _tz

    session_id = f"dashboard_{pa_id}"
    now_iso = datetime.now(_tz.utc).isoformat()
    history = [
        {"role": m["role"], "content": str(m["content"])[:500], "ts": now_iso}
        for m in messages
    ]
    try:
        with _dashboard_chat_lock:
            data: dict = {}
            if _CONV_PATH.exists():
                try:
                    data = _json.loads(_CONV_PATH.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    data = {}
            sessions = data.setdefault("sessions", {})
            sessions[session_id] = {
                "source": "dashboard",
                "session_id": session_id,
                "last_updated": now_iso,
                "messages": history,
            }
            _CONV_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _CONV_PATH.with_suffix(".tmp")
            tmp.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(_CONV_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Dashboard chat persist skipped: %s", exc)


# _inject_fixed_chat_bar removed — replaced by st.container(height=…) native Streamlit layout


def _status_card(phase: str, steps: list, state: str = "running") -> str:
    """Return a self-contained dark HTML progress card. state: running|complete|error"""
    _palette = {
        "running": {"bg": "rgba(124,58,237,0.12)", "border": "rgba(124,58,237,0.4)",
                    "label": "#c4b5fd", "icon": "⚙️"},
        "complete": {"bg": "rgba(34,197,94,0.12)",  "border": "rgba(34,197,94,0.4)",
                     "label": "#86efac",  "icon": "✅"},
        "error":    {"bg": "rgba(239,68,68,0.12)",   "border": "rgba(239,68,68,0.4)",
                     "label": "#fca5a5",  "icon": "❌"},
    }
    c = _palette.get(state, _palette["running"])
    dots = ""
    if state == "running":
        dots = ("<span style='display:inline-block;animation:spin 1s linear infinite;'"
                ">⏳</span> ")
    rows = "".join(
        f"<div style='color:#94a3b8;font-size:0.82rem;padding:2px 0 2px 18px;'>▸ {s}</div>"
        for s in steps
    )
    pulse = (
        "<style>@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}</style>"
        if state == "running" else ""
    )
    return (
        f"{pulse}"
        f"<div style='background:{c['bg']};border:1px solid {c['border']};"
        f"border-radius:12px;padding:12px 16px;margin:6px 0;'>"
        f"<div style='color:{c['label']};font-weight:700;font-size:0.93rem;'>"
        f"{dots}{phase}</div>"
        f"{rows}</div>"
    )


@st.fragment(run_every=5)
def _render_live_channels() -> None:
    """Auto-refreshing live feed of all external-channel conversations."""
    import json as _json
    from datetime import datetime as _dt

    try:
        if not _CONV_PATH.exists():
            st.info(
                "No external channel conversations yet. "
                "Messages sent via Telegram or other bots will appear here automatically."
            )
            return

        raw = _json.loads(_CONV_PATH.read_text(encoding="utf-8"))
        sessions = raw.get("sessions", {})

        if not sessions:
            st.info("No external channel conversations yet.")
            return

        # Sort newest-first
        sorted_sessions = sorted(
            sessions.values(),
            key=lambda s: s.get("last_updated", ""),
            reverse=True,
        )

        st.caption(f"🔄 Auto-refreshing every 5s &nbsp;·&nbsp; **{len(sorted_sessions)}** active session(s)")

        for idx, sess in enumerate(sorted_sessions):
            source = sess.get("source", "unknown")
            session_id = sess.get("session_id", "?")
            messages = sess.get("messages", [])
            last_updated = sess.get("last_updated", "")

            icon = _SOURCE_ICONS.get(source, "📡")
            color = _SOURCE_COLORS.get(source, "#888")

            try:
                time_str = _dt.fromisoformat(last_updated).strftime("%b %d %H:%M")
            except Exception:
                time_str = last_updated[:16]

            label = f"{icon} **{session_id}** &nbsp;`{source}`&nbsp;&nbsp; _{time_str}_"
            with st.expander(label, expanded=(idx == 0)):
                if not messages:
                    st.caption("No messages yet.")
                    continue

                # Group messages into (user, assistant) pairs so that when
                # we reverse for newest-first display, user always appears
                # before the assistant's reply within each pair.
                msg_list = messages[-12:]
                _pairs: list = []
                _i = 0
                while _i < len(msg_list):
                    if (
                        _i + 1 < len(msg_list)
                        and msg_list[_i].get("role") == "user"
                        and msg_list[_i + 1].get("role") == "assistant"
                    ):
                        _pairs.append([msg_list[_i], msg_list[_i + 1]])
                        _i += 2
                    else:
                        _pairs.append([msg_list[_i]])
                        _i += 1

                for _pair in reversed(_pairs):
                    for msg in _pair:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        ts = msg.get("ts", "")
                        elapsed = msg.get("elapsed")

                        try:
                            ts_str = _dt.fromisoformat(ts).strftime("%H:%M:%S")
                        except Exception:
                            ts_str = ""

                        ts_html = (
                            f"<span style='font-size:0.72rem;color:#9ca3af;white-space:nowrap;"
                            f"min-width:62px;padding-top:4px;display:inline-block;'>{ts_str}</span>"
                        )

                        if role == "user":
                            st.markdown(
                                f"<div style='display:flex;gap:8px;margin:6px 0;align-items:flex-start;'>"
                                f"{ts_html}"
                                f"<div style='background:#1e1e2e;border-left:3px solid {color};"
                                f"border-radius:0 8px 8px 0;padding:8px 12px;flex:1;font-size:0.86rem;"
                                f"color:#e2e8f0;line-height:1.5;'>{content}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            elapsed_badge = (
                                f" <span style='font-size:0.7rem;color:#a78bfa;'>({elapsed:.1f}s)</span>"
                                if elapsed else ""
                            )
                            st.markdown(
                                f"<div style='display:flex;gap:8px;margin:6px 0;align-items:flex-start;'>"
                                f"{ts_html}"
                                f"<div style='background:#2d1f4e;border-left:3px solid #8b5cf6;"
                                f"border-radius:0 8px 8px 0;padding:8px 12px;flex:1;font-size:0.86rem;"
                                f"color:#e2e8f0;line-height:1.5;'>"
                                f"{content}{elapsed_badge}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
    except Exception as exc:
        st.error(f"Could not load conversations: {exc}")


# ── Channel helpers ───────────────────────────────────────────────────────────

def _start_pa_channels(pa: dict) -> None:
    """Start every enabled channel assigned to this PA."""
    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        for ch_name in pa.get("channels", []):
            ch = CHANNEL_REGISTRY.get(ch_name)
            if ch and ch.enabled and not ch.is_running():
                try:
                    ch.start()
                except Exception as exc:
                    logger.warning("Could not start channel %s: %s", ch_name, exc)
    except Exception as exc:
        logger.warning("_start_pa_channels failed: %s", exc)


@st.dialog("\u2728 Create New Assistant", width="large")
def _create_pa_dialog() -> None:
    """Full-screen dialog for creating a Personal Assistant."""
    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
    except Exception as exc:
        st.error(f"Could not load registries: {exc}")
        return

    st.markdown(
        "<p style='color:#c4b5fd;margin-bottom:20px;'>Define the <b>name</b>, "
        "<b>skills</b> it can use, and <b>channels</b> it will listen on.</p>",
        unsafe_allow_html=True,
    )

    pa_name = st.text_input(
        "\U0001f4cb Assistant Name",
        placeholder="e.g. Aria, Jarvis, Max\u2026",
        help="Pick a name you\'d naturally use when talking to this assistant.",
    )

    st.markdown("---")
    st.markdown("**\U0001f6e0\ufe0f Skills** &nbsp;<span style='color:#94a3b8;font-size:0.85rem'>What can this assistant do?</span>", unsafe_allow_html=True)
    skill_opts = list(AGENT_REGISTRY.keys())
    selected_skills = st.multiselect(
        "Skills",
        options=skill_opts,
        default=skill_opts,
        format_func=lambda s: f"{s.title()} \u2014 {AGENT_REGISTRY[s]['description'][:60]}\u2026",
        label_visibility="collapsed",
    )
    if not selected_skills:
        st.warning("At least one skill is required.")

    st.markdown("---")
    st.markdown("**\U0001f4e1 Channels** &nbsp;<span style='color:#94a3b8;font-size:0.85rem'>How will users talk to this assistant?  Selected channels will start automatically.</span>", unsafe_allow_html=True)
    ch_opts = list(CHANNEL_REGISTRY.keys())
    selected_channels = st.multiselect(
        "Channels",
        options=ch_opts,
        default=[],
        format_func=lambda c: f"{CHANNEL_REGISTRY[c].icon} {CHANNEL_REGISTRY[c].display_name} \u2014 {CHANNEL_REGISTRY[c].description[:50]}\u2026",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.92rem;font-weight:700;color:#c4b5fd;margin-bottom:4px;'>✈️ Telegram Bot Token <span style='color:#f87171;'>*required</span></div>"
        "<div style='font-size:0.8rem;color:#64748b;margin-bottom:8px;'>Create a bot via <b>@BotFather</b> on Telegram and paste the token here.</div>",
        unsafe_allow_html=True,
    )
    tg_token_input = st.text_input(
        "Bot Token",
        placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        type="password",
        label_visibility="collapsed",
    )

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("\u2795 Create Assistant", type="primary", use_container_width=True):
            name = pa_name.strip()
            if not name:
                st.error("\u26a0\ufe0f Please enter a name for the assistant.")
            elif not selected_skills:
                st.error("\u26a0\ufe0f Select at least one skill.")
            elif not tg_token_input.strip():
                st.error("\u26a0\ufe0f A Telegram Bot Token is required. Get one from @BotFather on Telegram.")
            else:
                cfg = {"telegram": {"bot_token": tg_token_input.strip(), "auto_reply": True}}
                new_pa = create_assistant(name, selected_skills, selected_channels, config=cfg)
                # Auto-start the channels assigned to this PA
                _start_pa_channels(new_pa)
                # Auto-start the Telegram bot poller
                try:
                    from src.telegram.pa_poller_manager import start_pa_poller as _spp
                    _spp(new_pa["id"])
                except Exception as _tge:
                    st.warning(f"\u26a0\ufe0f Bot failed to start automatically: {_tge}")
                st.toast(f"✅ **{new_pa['name']}** created! Reload the page to see the new tab.", icon="✅")
                st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


# ── Per-PA chat panel ──────────────────────────────────────────────────────────

def _pa_k(pa_id: str, key: str) -> str:
    """Namespace a session_state key under a PA id."""
    return f"pa_{pa_id}_{key}"


# ── Google auth helpers ───────────────────────────────────────────────────────

def _is_gmail_ready() -> bool:
    """Check if a Gmail token exists on disk (fast, no API call)."""
    try:
        from src.email.gmail_service import is_gmail_authorized
        return is_gmail_authorized()
    except Exception:
        return False


def _reauth_gmail_ui(context: str = "", key_suffix: str = "") -> None:
    """
    Show a Gmail re-authorization panel in the chat.

    Displays the auth message (if any), a Re-authorize button that opens
    `setup_google_auth.py` in a new terminal, and a Retry hint.
    """
    import hashlib as _hl
    _btn_key = "reauth_btn_" + _hl.md5((context + key_suffix).encode()).hexdigest()[:8]

    if context:
        st.warning(context)
    else:
        st.warning(
            "🔑 **Gmail authorization required.**  \n"
            "Your Google token is missing or has expired."
        )

    if st.button("🔑 Re-authorize Gmail", key=_btn_key, type="primary"):
        try:
            from src.email.gmail_service import reset_gmail_client
            reset_gmail_client()  # clear cached client so next call retries
            project_root = Path(__file__).parent.parent.parent.parent.parent
            auth_script = project_root / "setup_google_auth.py"
            if sys.platform == "win32":
                subprocess.Popen(
                    [sys.executable, str(auth_script)],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen([sys.executable, str(auth_script)])
            st.success(
                "✅ **Authorization window opened.** \n\n"
                "Complete the Google sign-in in the new window, "
                "then come back and resend your message."
            )
        except Exception as exc:
            st.error(
                f"❌ Could not launch the auth script: {exc}  \n\n"
                f"Run manually: `python setup_google_auth.py`"
            )


# ── Channel status pills helper (used in tab-bar badge row) ──────────────────

def _build_channel_status_pills_html(pa: dict) -> str:
    """Return compact inline HTML pills for each channel assigned to *pa*.

    Used to render status badges alongside the tab bar so users can see
    channel health at a glance without opening the Live Channels tab.
    Returns an empty string when the channel registry is unavailable.
    """
    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        pa_channels = pa.get("channels", [])
        if not pa_channels:
            return ""
        ch_objects = [
            (ch_name, CHANNEL_REGISTRY[ch_name])
            for ch_name in pa_channels
            if ch_name in CHANNEL_REGISTRY
        ]
        if not ch_objects:
            return ""
        pills = ""
        for ch_name, ch in ch_objects:
            running = ch.is_running()
            dot_color = "#22c55e" if running else "#ef4444"
            status_label = "Running" if running else "Stopped"
            pills += (
                f"<span style='display:inline-flex;align-items:center;gap:4px;"
                f"background:#1a1a2e;border:1px solid {dot_color}44;"
                f"border-radius:20px;padding:2px 9px 2px 7px;font-size:0.74rem;'>"
                f"<span style='font-size:0.85rem'>{ch.icon}</span>"
                f"<span style='color:#e2e8f0;font-weight:600;font-size:0.73rem'>{ch.display_name}</span>"
                f"<span style='color:{dot_color};font-size:0.6rem;'>&#x25cf;&nbsp;{status_label}</span>"
                f"</span>"
            )
        return pills
    except Exception:
        return ""


def _render_pa_chat(pa: dict) -> None:
    """Render an independent chat panel for one Personal Assistant.

    Layout (ChatGPT-style, fully native Streamlit):
      ┌─────────────────────────────────────────┐
      │  scrollable message area (container)    │
      │  • all history messages                 │
      │  • live status placeholders when busy   │
      └─────────────────────────────────────────┘
      [ chat_input — always anchored below ]

    No JS injection needed.  st.container(height=…) gives a fixed-height
    scrollable viewport; st.chat_input() placed after it auto-anchors to the
    bottom of the page, always visible regardless of message count.
    """
    pa_id   = pa["id"]
    pa_name = pa["name"]
    pa_skills = set(pa.get("skills", []))

    mk = lambda key: _pa_k(pa_id, key)

    detect_agents_needed, run_workflow = _import_workflows()

    # ── Stopped-channel nudge (compact — status pills live above the tab bar) ─
    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        pa_channels = pa.get("channels", [])
        if pa_channels:
            ch_objects = [(c, CHANNEL_REGISTRY[c]) for c in pa_channels if c in CHANNEL_REGISTRY]
            any_stopped = any(not ch.is_running() for _, ch in ch_objects)
            if any_stopped:
                if st.button("▶️ Start Channels", key=f"start_ch_{pa_id}", type="primary"):
                    _start_pa_channels(pa)
                    st.rerun()
    except Exception as exc:
        logger.debug("Channel panel error: %s", exc)

    # ── Session state (per PA) ────────────────────────────────────────────────
    if mk("messages") not in st.session_state:
        st.session_state[mk("messages")] = [{
            "role": "assistant",
            "content": (
                f"👋 Hey! I'm **{pa_name}**, your personal AI assistant. "
                "I'm ready to work — just tell me what you need! ⚡\n\n"
                "💡 *Try something like: \"Check my emails\", \"What's on my calendar?\", "
                "or \"Organise my downloads folder\".*"
            ),
        }]
    if mk("processing") not in st.session_state:
        st.session_state[mk("processing")] = False
    if mk("command") not in st.session_state:
        st.session_state[mk("command")] = None
    if mk("count") not in st.session_state:
        st.session_state[mk("count")] = 0

    # ── Gmail first-time / expired token notice ───────────────────────────────
    # Shown persistently at the top of the chat whenever the email skill is
    # attached but no valid token exists — guides new users through setup.
    if "email" in pa_skills and not _is_gmail_ready():
        with st.container(border=True):
            st.markdown("##### 📧 Gmail Setup Required")
            _reauth_gmail_ui(
                "Gmail is not yet authorized for this assistant. "
                "Click below to open a browser sign-in window.",
                key_suffix=pa_id,
            )

    # ── Determine if a command is in-flight ───────────────────────────────────
    # Evaluated once here so the container and the processing block see the
    # same state within a single script run.
    _is_processing = (
        st.session_state[mk("processing")]
        and bool(st.session_state.get(mk("command")))
    )

    # ── Scrollable chat history area ──────────────────────────────────────────
    # Fixed-height container keeps the chat input permanently visible below.
    # All messages — including live status cards and the final reply — render
    # inside this scrollable box, so the input is never pushed off-screen.
    with st.container(height=560, border=False):
        for msg in st.session_state[mk("messages")]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Sentinel anchor — JS below scrollIntoViews this to auto-scroll bottom
        st.markdown(
            f'<div id="chat-bottom-{pa_id}"></div>',
            unsafe_allow_html=True,
        )

        # Pre-create the two live placeholders INSIDE the container (and inside
        # a chat_message bubble) so status cards and the reply appear in-line
        # with the conversation, not below the input bar.
        _card_ph = None
        _result_ph = None
        if _is_processing:
            with st.chat_message("assistant"):
                _card_ph = st.empty()   # status card (thinking/planning/executing/done)
                _result_ph = st.empty() # final reply text

    # ── Auto-scroll the chat container to the bottom (ChatGPT style) ─────────
    try:
        import streamlit.components.v1 as _components
        _components.html(
            f"""<script>
            (function() {{
                var anchor = window.parent.document.getElementById("chat-bottom-{pa_id}");
                if (anchor) {{
                    // scrollIntoView with block:"end" scrolls the overflow container, not page
                    anchor.scrollIntoView({{behavior: "instant", block: "end"}});
                }} else {{
                    // Fallback: scroll all overflow-auto containers to bottom
                    var scrollables = window.parent.document.querySelectorAll(
                        '[data-testid="stVerticalBlockBorderWrapper"] > div'
                    );
                    scrollables.forEach(function(el) {{
                        if (el.scrollHeight > el.clientHeight) {{
                            el.scrollTop = el.scrollHeight;
                        }}
                    }});
                }}
            }})();
            </script>""",
            height=0,
        )
    except Exception:
        pass  # Non-critical — auto-scroll is cosmetic only

    # ── Chat input — placed AFTER the container ───────────────────────────────
    # Streamlit positions chat_input at the bottom of the viewport when it is
    # not nested inside a scrollable container.  This gives a true fixed-bottom
    # input bar without any JS injection.
    user_input = st.chat_input(
        f"Ask {pa_name}…" if not st.session_state[mk("processing")] else "⏳ Processing…",
        key=f"chat_input_{pa_id}",
    )
    if user_input:
        if st.session_state[mk("processing")]:
            st.toast("⏳ Still thinking — please wait for the current response.", icon="⏳")
        else:
            st.session_state[mk("messages")].append({"role": "user", "content": user_input})
            st.session_state[mk("command")] = user_input
            st.session_state[mk("processing")] = True
            st.rerun()

    # ── Process pending command ───────────────────────────────────────────────
    if not _is_processing:
        return   # nothing to process — exit cleanly

    command = st.session_state[mk("command")]
    st.session_state[mk("command")] = None   # clear so it doesn't re-run on next rerun

    # ── Bind a fresh correlation ID to this turn so every log line for this
    # ── request — across all skills — shares the same corr= identifier.
    _cid = bind_correlation(new_correlation_id())
    _t_turn = time.perf_counter()
    logger.info(
        "┌─ [PA:%s] Turn START  corr=%s  command=%.120s",
        pa_name, _cid, command,
    )
    _emotion_result = _detect_emotion(command)
    _emotion_label  = _emotion_result[0] if _emotion_result else None
    _emotion_hint   = _emotion_result[1] if _emotion_result else ""
    _empathy_opener = _EMOTION_EMPATHY_OPENERS.get(_emotion_label or "", "")

    # Safety fallback: if placeholders weren't created (shouldn't happen)
    if _card_ph is None:
        _card_ph = st.empty()
    if _result_ph is None:
        _result_ph = st.empty()

    # Decide which skill(s) are needed.
    # Enrich bare time-slot replies (e.g. "2 PM to 3 PM") so the router
    # recognises them as scheduling tasks instead of casual conversation.
    _routing_command = _enrich_scheduling_followup(
        command, st.session_state.get(mk("messages"), [])
    )
    if _routing_command != command:
        logger.info("│  [ENRICH] Scheduling follow-up enriched: %.120s", _routing_command)
    agents_needed = detect_agents_needed(_routing_command)
    logger.info(
        "│  [ROUTE]  agents=%s  source=dashboard  pa=%s",
        agents_needed or "conversational", pa_name,
    )

    # Filter to only this PA's attached skills
    if agents_needed is not None and pa_skills:
        filtered = [a for a in agents_needed if a in pa_skills]
        if not filtered:
            _missing = [a for a in agents_needed if a not in pa_skills]
            _m_str = " and ".join(f"**{s.title()}**" for s in _missing)
            _sfx = "s" if len(_missing) > 1 else ""
            _verb = "are" if len(_missing) > 1 else "is"
            _no_skill_reply = (
                f"⚠️ This request needs the {_m_str} skill{_sfx}, "
                f"which {_verb} not enabled for **{pa_name}**.\n\n"
                f"Go to the **Configure** tab → **Skills** to enable it."
            )
            _result_ph.markdown(_no_skill_reply)
            st.session_state[mk("messages")].append({"role": "assistant", "content": _no_skill_reply})
            st.session_state[mk("processing")] = False
            st.rerun()
        agents_needed = filtered

    # ── Smart routing upgrade: "mail/send them" with multiple found files ─────
    # When the router picks only ["email"] but session state contains multiple
    # previously-found file paths, the user almost certainly wants zip-then-email
    # (not 3 separate emails).  Upgrade to ["files", "email"] so the DAG planner
    # handles the zip step automatically.
    # Also: if the command uses pronouns ("them", "those") but NO files exist in
    # context, show a clear clarification message instead of silently failing.
    if agents_needed == ["email"]:
        try:
            from src.agent.context.conversation_state import _default_tracker as _cst_tracker
            import re as _re_routing
            _cst_state = _cst_tracker.build(
                st.session_state.get(mk("messages"), []), command
            )
            _found_paths = _cst_state.get("last_found_paths", [])
            _found_folder = _cst_state.get("last_found_folder", "")
            if len(_found_paths) > 1:
                agents_needed = ["files", "email"]
                logger.info(
                    "│  [ROUTE-UPGRADE]  ['email'] → ['files','email']  "
                    "(%d files in context — will zip before emailing)",
                    len(_found_paths),
                )
            elif len(_found_paths) == 0 and not _found_folder:
                # No files in context — check if command uses a pronoun reference
                _pronoun_re = _re_routing.compile(
                    r'\b(them|those|those files|those documents|it|the files|'
                    r'the documents|the folder|they)\b',
                    _re_routing.IGNORECASE,
                )
                if _pronoun_re.search(command):
                    logger.info(
                        "│  [ROUTE-CLARIFY]  Pronoun reference + no file context → clarification"
                    )
                    _clarify_msg = (
                        "🤔 I'm not sure what to email — I don't have any files from a "
                        "recent search in this conversation.\n\n"
                        "Could you be more specific? For example:\n"
                        "- *'Search for my payslip files and email them to me'*\n"
                        "- *'Find the project report and send it to my email'*"
                    )
                    _result_ph.markdown(_clarify_msg)
                    st.session_state[mk("messages")].append({"role": "assistant", "content": _clarify_msg})
                    _persist_dashboard_chat(pa_id, st.session_state[mk("messages")])
                    st.session_state[mk("processing")] = False
                    st.rerun()
        except Exception:
            pass

    # ── Conversational (no skill needed) ─────────────────────────────────────
    if agents_needed is None:
        _card_ph.markdown(
            _status_card("🤔 Thinking…",
                         ["Reading your message…", "Reasoning & composing a reply…"]),
            unsafe_allow_html=True)
        _pa_history = st.session_state.get(mk("messages"), [])
        reply = _chat_response(command, pa_name, pa_id, emotion_hint=_emotion_hint, history=_pa_history)
        logger.info("└─ [PA:%s] Turn END (conversational)  elapsed=%.2fs", pa_name, time.perf_counter() - _t_turn)
        _card_ph.markdown(_status_card("✅ Done", [], "complete"), unsafe_allow_html=True)
        _result_ph.markdown(reply)
        st.session_state[mk("messages")].append({"role": "assistant", "content": reply})
        _persist_dashboard_chat(pa_id, st.session_state[mk("messages")])
        st.session_state[mk("processing")] = False
        st.rerun()

    # ── Single-skill shortcut ─────────────────────────────────────────────────
    if len(agents_needed) == 1:
        single_agent = agents_needed[0]
        _icons  = {"drive": "📁", "email": "✉️", "files": "🗂️", "calendar": "📅", "stock_market": "📈"}
        _labels = {"drive": "Drive", "email": "Email", "files": "Files", "calendar": "Calendar", "stock_market": "Stock Market"}
        icon  = _icons.get(single_agent, "🤖")
        label = _labels.get(single_agent, single_agent.replace("_", " ").title())
        _result_status = "success"

        _card_ph.markdown(
            _status_card("🤔 Analyzing your request…", ["Detecting required skill…"]),
            unsafe_allow_html=True)
        _card_ph.markdown(
            _status_card(f"⚙️ Routing to {icon} {label}…",
                         [f"Preparing {label} skill…", "Executing task…"]),
            unsafe_allow_html=True)
        try:
            from src.agent.workflows.agent_registry import get_executor
            executor = get_executor(single_agent)
            # Inject prior conversation context so the skill agent has follow-up awareness
            _ctx_command = _inject_conversation_context(
                _routing_command,
                st.session_state.get(mk("messages"), []),
            )
            result = executor(_ctx_command, agent_id=None) if executor else {"action": "error", "message": f"Skill '{single_agent}' not loaded."}
            _result_status = result.get("status", "success")
            action = result.get("action", "react_response")
            if action == "react_response" or "message" in result:
                reply = result.get("message", str(result))
            else:
                try:
                    import importlib
                    mod = importlib.import_module(f"src.agent.ui.{single_agent}_agent.app")
                    compose_fn = getattr(mod, f"_compose_{single_agent}_response", None)
                    reply = compose_fn(result, action, command) if compose_fn else str(result.get("message", result))
                except Exception:
                    reply = str(result.get("message", result))
            _card_ph.markdown(
                _status_card(f"✅ Done — {icon} {label}", [], "complete"),
                unsafe_allow_html=True)
        except Exception as exc:
            logger.exception("Single-skill shortcut error: %s", exc)
            reply = f"❌ Something went wrong: {exc}"
            _result_status = "error"
            _card_ph.markdown(
                _status_card("❌ Error", [str(exc)[:120]], "error"),
                unsafe_allow_html=True)

        logger.info(
            "└─ [PA:%s] Turn END (skill=%s)  status=%s  elapsed=%.2fs",
            pa_name, single_agent, _result_status, time.perf_counter() - _t_turn,
        )

        if _result_status == "auth_error":
            _result_ph.markdown(
                "🔑 **Gmail authorization required.** "
                "The re-authorization panel is shown at the top of this chat — please click it."
            )
            _save_msg = "🔑 Gmail authorization required — use the Re-authorize button at the top."
        else:
            # Prepend a brief empathy opener for emotional messages
            if _empathy_opener and not reply.startswith(("❌", "⚠️")):
                reply = _empathy_opener + reply
            _result_ph.markdown(reply)
            _save_msg = reply

            # ── File artifact download button ─────────────────────────────────
            # Executors that produce downloadable files return a "file_path" key.
            # Present a download button directly inside the chat for instant access.
            _artifact_path = (result or {}).get("file_path", "")
            if _artifact_path:
                try:
                    import mimetypes as _mimetypes
                    if os.path.isfile(_artifact_path):
                        _fname = os.path.basename(_artifact_path)
                        with open(_artifact_path, "rb") as _fh:
                            _fdata = _fh.read()
                        _mime, _ = _mimetypes.guess_type(_artifact_path)
                        _mime = _mime or "application/octet-stream"
                        st.download_button(
                            label=f"⬇️ Download {_fname}",
                            data=_fdata,
                            file_name=_fname,
                            mime=_mime,
                            key=f"dl_{pa_id}_{len(st.session_state[mk('messages')])}",
                        )
                        _save_msg += f"\n\n📎 File produced: `{_fname}`"
                except Exception as _dl_err:
                    logger.debug("Download button render error: %s", _dl_err)

        st.session_state[mk("messages")].append({"role": "assistant", "content": _save_msg})
        _persist_dashboard_chat(pa_id, st.session_state[mk("messages")])
        st.session_state[mk("processing")] = False
        st.rerun()

    # ── Multi-skill workflow ──────────────────────────────────────────────────
    _agent_display = {"drive": "📁 Drive", "email": "✉️ Email", "files": "🗂️ Files",
                      "calendar": "📅 Calendar", "stock_market": "📈 Stocks"}
    _agents_str = " + ".join(
        _agent_display.get(a, f"🤖 {a.replace('_',' ').title()}") for a in agents_needed
    )

    _card_ph.markdown(
        _status_card("🤔 Thinking…", ["Analyzing your request…", "Detecting required skills…"]),
        unsafe_allow_html=True)
    _card_ph.markdown(
        _status_card(f"📋 Planning workflow for: {_agents_str}",
                     ["Designing step-by-step execution plan…"]),
        unsafe_allow_html=True)
    _card_ph.markdown(
        _status_card("⚙️ Executing…", ["Running agents — this may take a moment…"]),
        unsafe_allow_html=True)

    try:
        # Enrich the command with structured Session State (last_found_paths,
        # last_found_folder, dates, etc.) so the DAG planner can resolve context
        # references like "them", "those files", "the folder" correctly.
        _enriched_for_workflow = _inject_conversation_context(
            command, st.session_state.get(mk("messages"), [])
        )
        run_result = run_workflow(_enriched_for_workflow)
        _total_steps = len(run_result.get("steps", []))
        _step_lines = []
        for _i, sr in enumerate(run_result.get("steps", []), 1):
            _s_icon  = "✅" if sr.get("status") == "success" else "❌"
            _s_badge = _format_step_badge(sr.get("agent", "?"))
            _s_tool  = sr.get("tool", "?")
            _step_lines.append(f"{_s_icon} Step {_i}/{_total_steps} — {_s_badge} › {_s_tool}")
        wf_status = run_result.get("status", "error")
        _elapsed  = run_result.get("elapsed", 0)
        _done_state = "complete" if wf_status == "success" else "error"
        _done_label = (
            f"✅ Done — {_total_steps} step(s) in {_elapsed:.1f}s"
            if wf_status == "success"
            else f"⚠️ Partial / Error — {_total_steps} step(s) in {_elapsed:.1f}s"
        )
        _card_ph.markdown(_status_card(_done_label, _step_lines, _done_state), unsafe_allow_html=True)
    except Exception as exc:
        logger.exception("Workflow execution error: %s", exc)
        run_result = {"status": "error", "steps": [], "elapsed": 0, "plan": None, "summary": str(exc)}
        _card_ph.markdown(_status_card("❌ Unexpected error", [str(exc)[:120]], "error"), unsafe_allow_html=True)

    final_text = _render_workflow_output(run_result, command)
    # Prepend empathy opener for emotional messages (multi-skill workflow)
    if _empathy_opener and not final_text.startswith(("❌", "⚠️")):
        final_text = _empathy_opener + final_text
    _result_ph.markdown(final_text)

    # ── File artifact download button (multi-skill) ───────────────────────────
    # Collect file_path values from each workflow step result.
    # DAG steps nest the path under result.artifacts.file_path, so we check
    # both the top-level key and the nested location.
    def _step_file_path(sr: dict) -> str:
        if sr.get("file_path"):
            return sr["file_path"]
        _res = sr.get("result") or {}
        if isinstance(_res, dict):
            if _res.get("file_path"):
                return _res["file_path"]
            _art = _res.get("artifacts") or {}
            if isinstance(_art, dict) and _art.get("file_path"):
                return _art["file_path"]
        return ""

    _wf_artifacts = [
        _fp for sr in run_result.get("steps", [])
        if (_fp := _step_file_path(sr))
    ]
    for _wf_fp in _wf_artifacts:
        try:
            import mimetypes as _mimetypes
            if os.path.isfile(_wf_fp):
                _wf_fname = os.path.basename(_wf_fp)
                with open(_wf_fp, "rb") as _wf_fh:
                    _wf_fdata = _wf_fh.read()
                _wf_mime, _ = _mimetypes.guess_type(_wf_fp)
                _wf_mime = _wf_mime or "application/octet-stream"
                st.download_button(
                    label=f"⬇️ Download {_wf_fname}",
                    data=_wf_fdata,
                    file_name=_wf_fname,
                    mime=_wf_mime,
                    key=f"wfdl_{pa_id}_{_wf_fname}_{len(st.session_state[mk('messages')])}",
                )
                final_text += f"\n\n📎 File produced: `{_wf_fname}`"
        except Exception as _wf_dl_err:
            logger.debug("Workflow download button error: %s", _wf_dl_err)

    # Record to PA-level memory (not skill-level)
    try:
        from src.agent.memory.agent_memory import get_agent_memory
        _mem = get_agent_memory(pa_id)
        _mem.add_interaction(
            command=command,
            action="multi_skill_workflow",
            result={
                "status": run_result.get("status", "error"),
                "agents": agents_needed,
                "steps": len(run_result.get("steps", [])),
            },
            importance="High",
        )
        st.session_state[mk("count")] += 1
    except Exception as _mem_err:
        logger.debug("PA workflow memory record skipped: %s", _mem_err)

    st.session_state[mk("messages")].append({"role": "assistant", "content": final_text})
    _persist_dashboard_chat(pa_id, st.session_state[mk("messages")])
    logger.info(
        "└─ [PA:%s] Turn END (workflow agents=%s)  status=%s  elapsed=%.2fs",
        pa_name, agents_needed, run_result.get("status", "error"),
        time.perf_counter() - _t_turn,
    )
    st.session_state[mk("processing")] = False
    st.rerun()


# ── PA Settings ───────────────────────────────────────────────────────────────

def _render_pa_settings() -> None:
    """PA Settings tab — create / manage Personal Assistants, Skills, Channels."""

    st.markdown("## ⚙️ Personal Assistant Settings")

    # ── Create New Assistant ──────────────────────────────────────────────────
    with st.expander("✨ Create New Assistant", expanded=False):
        try:
            from src.agent.workflows.agent_registry import AGENT_REGISTRY
            from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        except Exception as exc:
            st.error(f"Could not load registries: {exc}")
            return

        with st.form("create_pa_form", clear_on_submit=True):
            pa_name_input = st.text_input("Assistant Name", placeholder="e.g. Aria, Jarvis, Max…")
            skill_opts = list(AGENT_REGISTRY.keys())
            selected_skills = st.multiselect(
                "Attach Skills",
                options=skill_opts,
                default=skill_opts,
                format_func=lambda s: f"{s.title()} — {AGENT_REGISTRY[s]['description'][:60]}…",
            )
            channel_opts = list(CHANNEL_REGISTRY.keys())
            selected_channels = st.multiselect(
                "Attach Channels",
                options=channel_opts,
                default=channel_opts,
                format_func=lambda c: f"{CHANNEL_REGISTRY[c].icon} {CHANNEL_REGISTRY[c].display_name}",
            )
            tg_token_settings = st.text_input(
                "✈️ Telegram Bot Token *",
                placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                type="password",
                help="Required. Create a bot via @BotFather on Telegram.",
            )
            submitted = st.form_submit_button("➕ Create Assistant", type="primary")
            if submitted:
                name = pa_name_input.strip()
                if not name:
                    st.error("Please enter a name.")
                elif not selected_skills:
                    st.error("Attach at least one skill.")
                elif not tg_token_settings.strip():
                    st.error("⚠️ A Telegram Bot Token is required. Get one from @BotFather on Telegram.")
                else:
                    cfg = {"telegram": {"bot_token": tg_token_settings.strip(), "auto_reply": True}}
                    new_pa = create_assistant(name, selected_skills, selected_channels, config=cfg)
                    try:
                        from src.telegram.pa_poller_manager import start_pa_poller as _spp2
                        _spp2(new_pa["id"])
                    except Exception as _tge2:
                        st.warning(f"⚠️ Bot failed to start: {_tge2}")
                    st.toast(f"✅ Created **{new_pa['name']}**. Reload the page to see the new tab.", icon="✅")
                    st.rerun()

    st.divider()

    # ── Existing Assistants ───────────────────────────────────────────────────
    st.markdown("### 🤖 Your Personal Assistants")
    assistants = load_assistants()
    for pa in assistants:
        with st.container():
            col_info, col_del = st.columns([5, 1])
            with col_info:
                skill_badges = " ".join(
                    f"<span style='background:#4c1d95;color:#ddd8fe;padding:2px 8px;"
                    f"border-radius:10px;font-size:0.75rem;margin:2px'>{s.title()}</span>"
                    for s in pa.get("skills", [])
                )
                st.markdown(
                    f"<div style='padding:10px 0;border-bottom:1px solid #334155;'>"
                    f"<b style='color:#e2e8f0;font-size:1rem'>{pa['name']}</b>"
                    f"<span style='color:#64748b;font-size:0.78rem;margin-left:8px'>{pa['id']}</span>"
                    f"<div style='margin-top:6px'>{skill_badges}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col_del:
                if len(assistants) > 1:
                    if st.button("🗑️", key=f"del_{pa['id']}", help=f"Delete {pa['name']}"):
                        if delete_assistant(pa["id"]):
                            st.toast(f"🗑️ Deleted {pa['name']}. Reload to update tabs.", icon="🗑️")
                            st.rerun()
                        else:
                            st.error("Could not delete.")

    st.divider()

    # ── Skills ────────────────────────────────────────────────────────────────
    st.markdown("### 🛠️ Available Skills")
    st.caption("Skills are stateless executors — they have no memory. "
               "All context and history live in the Personal Assistant.")

    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        for skill_name, info in AGENT_REGISTRY.items():
            st.markdown(
                f"<div style='padding:6px 0;border-bottom:1px solid #1e293b;'>"
                f"<b style='color:#e2e8f0'>{skill_name.title()}</b>"
                f"<span style='color:#94a3b8;margin-left:12px;font-size:0.85rem'>"
                f"{info.get('description','')}</span></div>",
                unsafe_allow_html=True,
            )
    except Exception as exc:
        st.error(f"Could not load Skills registry: {exc}")

    st.divider()

    # ── Channels ──────────────────────────────────────────────────────────────
    st.markdown("### 📡 Channels")
    st.caption("Channels are communication interfaces. Each runs independently.")

    try:
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        for ch_name, ch in CHANNEL_REGISTRY.items():
            running = ch.is_running()
            badge = (
                "<span style='background:#16a34a;color:#fff;"
                "padding:2px 10px;border-radius:12px;font-size:0.78rem'>● Running</span>"
                if running else
                "<span style='background:#dc2626;color:#fff;"
                "padding:2px 10px;border-radius:12px;font-size:0.78rem'>● Stopped</span>"
            )
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:12px;"
                f"padding:8px 0;border-bottom:1px solid #334155;'>"
                f"<span style='font-size:1.4rem'>{ch.icon}</span>"
                f"<div style='flex:1'><b style='color:#e2e8f0'>{ch.display_name}</b>"
                f"<span style='color:#94a3b8;margin-left:10px;font-size:0.82rem'>{ch.description}</span>"
                f"</div>{badge}</div>",
                unsafe_allow_html=True,
            )
            try:
                s = ch.status()
                parts = []
                if s.port: parts.append(f"Port {s.port}")
                if s.pid:  parts.append(f"PID {s.pid}")
                if s.detail: parts.append(s.detail)
                if parts: st.caption("  " + " · ".join(parts))
            except Exception:
                pass
    except Exception as exc:
        st.error(f"Could not load Channel registry: {exc}")


def _render_pa_configure(pa: dict) -> None:
    """Configure tab for a single PA — edit skills and channels in place."""
    from src.agent.hub.pa_manager import update_assistant, load_assistants

    # Always reload the freshest version from disk
    fresh = next((a for a in load_assistants() if a["id"] == pa["id"]), pa)

    try:
        from src.agent.workflows.agent_registry import AGENT_REGISTRY
        from src.agent.hub.channel_registry import CHANNEL_REGISTRY
        skill_opts   = list(AGENT_REGISTRY.keys())
        channel_opts = list(CHANNEL_REGISTRY.keys())
    except Exception as exc:
        st.error(f"Could not load registries: {exc}")
        return

    st.markdown(
        f"<div style='font-size:1.2rem;font-weight:800;color:#a78bfa;margin-bottom:16px;'>"
        f"⚙️ Configure &nbsp; <span style='color:#c4b5fd'>{fresh['name']}</span></div>",
        unsafe_allow_html=True,
    )

    with st.form(f"configure_pa_{fresh['id']}"):
        new_name = st.text_input("Assistant Name", value=fresh["name"])

        new_skills = st.multiselect(
            "🛠️ Skills",
            options=skill_opts,
            default=[s for s in fresh.get("skills", []) if s in skill_opts],
            format_func=lambda s: f"{s.title()} — {AGENT_REGISTRY[s].get('description','')[:60]}",
            help="Skills are stateless executors. Memory lives at the PA level.",
        )

        new_channels = st.multiselect(
            "📡 Channels",
            options=channel_opts,
            default=[c for c in fresh.get("channels", []) if c in channel_opts],
            format_func=lambda c: f"{CHANNEL_REGISTRY[c].icon} {CHANNEL_REGISTRY[c].display_name}",
            help="Channels the assistant will listen on.",
        )

        # ── Telegram config (matches config/settings.json structure) ────────────
        st.markdown(
            "<div style='font-size:0.88rem;color:#c4b5fd;font-weight:600;margin:14px 0 4px'>"
            "✈️ Telegram Bot</div>"
            "<div style='font-size:0.8rem;color:#64748b;margin-bottom:6px;'>"
            "Create a bot via @BotFather on Telegram. Each assistant runs its own dedicated bot."
            "</div>",
            unsafe_allow_html=True,
        )
        _tg_cfg = (fresh.get("config") or {}).get("telegram", {})
        new_token = st.text_input(
            "Bot Token",
            value=_tg_cfg.get("bot_token", ""),
            placeholder="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            type="password",
        )
        new_auto_reply = st.checkbox(
            "Auto-reply enabled",
            value=_tg_cfg.get("auto_reply", True),
            help="Automatically reply to inbound Telegram messages using the AI.",
        )
        _default_persona = (
            f"You are {fresh['name']}, a friendly AI assistant built with Octa Bot. "
            "Keep replies concise (2-3 sentences max) and conversational."
        )
        new_persona = st.text_area(
            "Auto-reply Persona",
            value=_tg_cfg.get("auto_reply_persona", _default_persona),
            height=80,
            help="System prompt that shapes how your bot speaks in Telegram replies.",
        )

        saved = st.form_submit_button("💾 Save Changes", type="primary")
        if saved:
            if not new_name.strip():
                st.error("Name cannot be empty.")
            elif not new_skills:
                st.error("Attach at least one skill.")
            else:
                # Merge full Telegram config block (mirrors config/settings.json structure)
                cfg = dict(fresh.get("config") or {})
                tg_cfg = dict(cfg.get("telegram") or {})
                if new_token.strip():
                    tg_cfg["bot_token"] = new_token.strip()
                elif "bot_token" in tg_cfg:
                    del tg_cfg["bot_token"]
                tg_cfg["auto_reply"] = new_auto_reply
                tg_cfg["auto_reply_persona"] = new_persona.strip()
                if tg_cfg:
                    cfg["telegram"] = tg_cfg
                elif "telegram" in cfg:
                    del cfg["telegram"]
                update_assistant(
                    fresh["id"],
                    name=new_name.strip(),
                    skills=new_skills,
                    channels=new_channels,
                    config=cfg,
                )
                st.toast(f"✅ Configuration saved for **{new_name.strip()}**!", icon="✅")
                st.rerun()

    st.divider()

    # ── Read-only skill reference ─────────────────────────────────────────────
    st.markdown("**Available Skills**")
    for skill_name, info in AGENT_REGISTRY.items():
        active = skill_name in fresh.get("skills", [])
        dot = "<span style='color:#16a34a'>●</span>" if active else "<span style='color:#4b5563'>●</span>"
        st.markdown(
            f"<div style='padding:4px 0;border-bottom:1px solid #1e293b;font-size:0.88rem;'>"
            f"{dot} <b style='color:#e2e8f0'>{skill_name.title()}</b>"
            f"<span style='color:#94a3b8;margin-left:10px'>{info.get('description','')}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Channel status ────────────────────────────────────────────────────────
    st.markdown("**Channel Status**")

    # Telegram: show per-PA poller status and start/stop
    tg_token = (fresh.get("config") or {}).get("telegram", {}).get("bot_token", "").strip()
    try:
        from src.telegram.pa_poller_manager import get_pa_poller_status, start_pa_poller, stop_pa_poller
        tg_status = get_pa_poller_status(fresh["id"])
        tg_running = tg_status is not None
    except Exception:
        tg_running = False
        tg_status = None
    # ── Telegram row with inline Start / Stop button ─────────────────────────
    tg_badge = (
        "<span style='background:#16a34a;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Running</span>"
        if tg_running else
        "<span style='background:#4b5563;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Stopped</span>"
    )
    tg_info = (
        "Token configured" if tg_token
        else "⚠️ Enter a token above and click Save to enable"
    )
    tg_row_col, tg_btn_col = st.columns([3, 1])
    with tg_row_col:
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:8px 0;"
            f"border-bottom:1px solid #1e293b;'>"
            f"<span style='font-size:1.2rem'>✈️</span>"
            f"<div style='flex:1'><b style='color:#e2e8f0'>Telegram Bot</b>"
            f"<span style='color:#94a3b8;margin-left:8px;font-size:0.82rem'>{tg_info}</span>"
            f"</div>{tg_badge}</div>",
            unsafe_allow_html=True,
        )
    with tg_btn_col:
        if tg_token:
            if not tg_running:
                if st.button("▶️ Start", key=f"start_tg_{fresh['id']}", use_container_width=True, type="primary"):
                    try:
                        start_pa_poller(fresh["id"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
            else:
                if st.button("⏹️ Stop", key=f"stop_tg_{fresh['id']}", use_container_width=True):
                    try:
                        stop_pa_poller(fresh["id"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")

    # ── Other channels from registry (telegram excluded — handled above) ──────
    for ch_name, ch in CHANNEL_REGISTRY.items():
        if ch_name == "telegram":
            continue   # already rendered with Start/Stop controls above
        active = ch_name in fresh.get("channels", [])
        running = ch.is_running()
        state_badge = (
            "<span style='background:#16a34a;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Running</span>"
            if running else
            "<span style='background:#4b5563;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75rem'>● Stopped</span>"
        )
        assigned = "<span style='color:#a78bfa;font-size:0.75rem;margin-left:6px'>(assigned)</span>" if active else ""
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid #1e293b;'>"
            f"<span style='font-size:1.2rem'>{ch.icon}</span>"
            f"<div style='flex:1'><b style='color:#e2e8f0'>{ch.display_name}</b>{assigned}"
            f"<span style='color:#94a3b8;margin-left:8px;font-size:0.82rem'>{ch.description}</span></div>"
            f"{state_badge}</div>",
            unsafe_allow_html=True,
        )


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    logger.debug("=== MULTI-AGENT MAIN() CALLED ===")
    agent_id = os.getenv("AGENT_ID", "_collective_memory_")

    # ── Single-PA mode: launched by process_manager for a specific PA ─────────
    pa_id_filter = os.getenv("PA_ID", "").strip()
    all_assistants = load_assistants()
    single_pa = None
    if pa_id_filter:
        single_pa = next((a for a in all_assistants if a["id"] == pa_id_filter), None)
        if single_pa:
            agent_id = single_pa["id"]
            assistants = [single_pa]
        else:
            assistants = all_assistants
    else:
        assistants = all_assistants

    # ── Initialise unified logging for this PA process ────────────────────────
    # Done once per Streamlit worker (idempotent).  Log file: logs/<name>.log
    _pa_log_name = single_pa["name"] if single_pa else "personal_assistant"
    setup_pa_logging(_pa_log_name)
    bind_correlation(new_correlation_id())   # fresh correlation for this page load

    st.set_page_config(
        page_title=f"{single_pa['name']} — Octa Bot" if single_pa else "Personal Assistants — Octa Bot",
        page_icon=_logo_icon(),
        layout="wide",
    )

    _start_browser_watchdog(agent_id)
    inject_agent_css(accent_hex="#7c3aed", accent_rgb="124,58,237")

    # ── Single-PA mode: Chat + Live Channels + Configure tabs ─────────────────
    if single_pa:
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg, rgba(124,58,237,0.18) 0%, rgba(139,92,246,0.12) 100%);
                       border:1.5px solid rgba(124,58,237,0.5);padding:10px 16px;border-radius:12px;margin-top:-2.5rem;margin-bottom:6px;
                       backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 4px 16px rgba(124,58,237,0.12);">
              <div style="display:flex;align-items:center;gap:12px;">
                <img src="{_logo_b64()}" style="width:40px;height:40px;border-radius:10px;object-fit:cover;box-shadow:0 2px 8px rgba(124,58,237,0.35);">
                <div>
                  <div style="font-size:1.35rem;font-weight:900;line-height:1.1;background:linear-gradient(135deg,#8b5cf6 0%,#7c3aed 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
                    🤖 {single_pa['name']}
                  </div>
                  <div style="font-size:0.78rem;color:#c4b5fd;margin-top:2px;">
                    {len(single_pa.get('skills', []))} skills &nbsp;•&nbsp; {len(single_pa.get('channels', []))} channels
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Channel status pills — right-aligned beside the tab bar ──────────
        _status_col_l, _status_col_r = st.columns([3, 2])
        with _status_col_r:
            _ch_pills_html = _build_channel_status_pills_html(single_pa)
            if _ch_pills_html:
                st.markdown(
                    f"<div style='display:flex;justify-content:flex-end;align-items:center;"
                    f"gap:6px;padding:4px 0 2px;'>{_ch_pills_html}</div>",
                    unsafe_allow_html=True,
                )

        tab_chat, tab_live, tab_cfg = st.tabs(["💬 Chat", "📡 Live Channels", "⚙️ Configure"])
        with tab_chat:
            _render_pa_chat(single_pa)
        with tab_live:
            _render_live_channels()
        with tab_cfg:
            _render_pa_configure(single_pa)
        return

    # ── Header ────────────────────────────────────────────────────────────────
    pa_subtitle = " &nbsp;•&nbsp; ".join(pa["name"] for pa in assistants)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, rgba(124,58,237,0.18) 0%, rgba(139,92,246,0.12) 100%);
                   border:1.5px solid rgba(124,58,237,0.5);padding:24px;border-radius:16px;margin-bottom:24px;
                   backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px rgba(124,58,237,0.15);">
          <div style="display:flex;align-items:center;gap:18px;margin-bottom:16px;">
            <img src="{_logo_b64()}" style="width:72px;height:72px;border-radius:18px;object-fit:cover;box-shadow:0 4px 15px rgba(124,58,237,0.4);">
            <div style="flex:1;">
              <div style="font-size:2.4rem;font-weight:900;line-height:1.1;background:linear-gradient(135deg,#8b5cf6 0%,#7c3aed 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">Octa Bot</div>
              <div style="font-size:1.05rem;color:#c4b5fd;margin-top:6px;font-weight:600;">
                🤖 Personal Assistants &nbsp;•&nbsp; {pa_subtitle}
              </div>
            </div>
          </div>
          <div style="font-size:0.95rem;color:#c4b5fd;line-height:1.6;font-weight:500;padding-top:12px;border-top:1px solid rgba(124,58,237,0.3);">
            Each assistant has its own memory, skills, and channels. Select a tab to chat. ✨
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        # Prominent create button at the top
        if st.button("\u2795 New Assistant", use_container_width=True, type="primary"):
            _create_pa_dialog()

        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:12px 0 4px;font-weight:600;"
            "letter-spacing:0.06em;text-transform:uppercase;'>\U0001f916 Your Assistants</p>",
            unsafe_allow_html=True,
        )
        for pa in assistants:
            skill_count   = len(pa.get("skills", []))
            ch_count      = len(pa.get("channels", []))
            pa_channels   = pa.get("channels", [])
            try:
                from src.agent.hub.channel_registry import CHANNEL_REGISTRY
                ch_running = sum(
                    1 for c in pa_channels
                    if c in CHANNEL_REGISTRY and CHANNEL_REGISTRY[c].is_running()
                )
                ch_dot = (
                    "<span style='color:#16a34a'>&#x25cf;</span>"
                    if ch_running == ch_count and ch_count > 0
                    else ("<span style='color:#f59e0b'>&#x25cf;</span>" if ch_running > 0 else "<span style='color:#dc2626'>&#x25cf;</span>")
                )
            except Exception:
                ch_dot = ""
            st.markdown(
                f"<div style='font-size:0.82rem;color:#a8dadc;padding:4px 0;"
                f"border-bottom:1px solid rgba(124,58,237,0.15);'>"
                f"{ch_dot} <b>{pa['name']}</b>"
                f"<span style='color:#64748b;margin-left:6px'>{skill_count} skills "
                f"\u00b7 {ch_count} ch</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if st.button("\U0001f4d6 Usage Guide", use_container_width=True, type="secondary"):
            _show_multi_agent_guide()

        st.markdown("---")
        st.markdown(
            "<p style='font-size:0.78rem;color:#bbb;margin:8px 0 4px;font-weight:600;"
            "letter-spacing:0.06em;text-transform:uppercase;'>🟢 Active Agents</p>",
            unsafe_allow_html=True,
        )
        running = get_running_agents()
        agent_agents = [a for a in running if a.get("id") != "_collective_memory_"]
        if agent_agents:
            for a in agent_agents:
                atype = a.get("type") or a.get("agent_type", "agent")
                aname = a.get("name", atype.title())
                aurl = a.get("url", "")
                icon = "📁" if "drive" in atype.lower() else (
                    "✉️" if "email" in atype.lower() else "🤖")
                link = f'<a href="{aurl}" target="_blank" style="color:#c4b5fd;">{aname}</a>' if aurl else aname
                st.markdown(
                    f"<div style='font-size:0.82rem;color:#a8dadc;padding:3px 0;'>"
                    f"{icon} {link}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div style='font-size:0.8rem;color:#888;'>No agents detected</div>",
                unsafe_allow_html=True,
            )

    # ── Dynamic tabs: one per PA + Live Channels + PA Settings ───────────────
    pa_tab_labels = [f"🤖 {pa['name']}" for pa in assistants]
    all_tab_labels = pa_tab_labels + ["📡 Live Channels", "⚙️ PA Settings"]
    all_tabs = st.tabs(all_tab_labels)

    for i, pa in enumerate(assistants):
        with all_tabs[i]:
            _render_pa_chat(pa)

    with all_tabs[-2]:
        _render_live_channels()

    with all_tabs[-1]:
        _render_pa_settings()


if __name__ == "__main__":
    main()
