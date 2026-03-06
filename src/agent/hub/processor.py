"""
HubProcessor — pure-Python multi-agent brain.

No Streamlit. No HTTP. Just:

    result = HubProcessor().process(message, session_id, source)
    print(result.response)

Any delivery channel (Telegram poller, FastAPI endpoint, CLI …) calls this
and gets a plain-text / markdown response back.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("hub_processor")

# Structured logging helpers — correlation IDs thread through every skill/LLM call
try:
    from src.agent.logging.log_manager import (
        bind_correlation, new_correlation_id,
        bind_request, new_request_id,
    )
except Exception:  # graceful fallback so the hub never fails to import
    def bind_correlation(cid: str) -> str: return cid  # type: ignore[misc]
    def new_correlation_id() -> str: return "-"        # type: ignore[misc]
    def bind_request(rid: str) -> str: return rid       # type: ignore[misc]
    def new_request_id() -> str: return "-"            # type: ignore[misc]

# Structured session-state builder — same module used by PA app
try:
    from src.agent.context.conversation_state import build_structured_query as _build_sq
except Exception:
    def _build_sq(task: str, history: list) -> str: return task  # type: ignore[misc]

# ---------------------------------------------------------------------------
# In-memory per-session conversation history
# Key: session_id  →  list of {"role": "user"|"assistant", "content": str}
# ---------------------------------------------------------------------------
_SESSION_HISTORY: Dict[str, List[Dict[str, str]]] = {}
_MAX_HISTORY = 20          # messages kept per session
_MAX_HISTORY_FOR_LLM = 10  # messages sent to LLM each turn

# ---------------------------------------------------------------------------
# Cross-process conversation persistence
# Written by poller/API process, read by the Streamlit dashboard.
# ---------------------------------------------------------------------------
_CONV_PATH = Path(__file__).parent.parent.parent.parent / "data" / "hub_conversations.json"
_conv_lock = threading.Lock()


def _persist_conversation(session_id: str, source: str, history: List[Dict[str, str]]) -> None:
    """Write/update session history in hub_conversations.json."""
    try:
        with _conv_lock:
            data: Dict[str, Any] = {}
            if _CONV_PATH.exists():
                try:
                    data = json.loads(_CONV_PATH.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            sessions = data.setdefault("sessions", {})
            sessions[session_id] = {
                "source": source,
                "session_id": session_id,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "messages": history,
            }
            _CONV_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _CONV_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(_CONV_PATH)
    except Exception as exc:
        logger.debug("Could not persist conversation: %s", exc)


def _load_session_history() -> None:
    """Restore _SESSION_HISTORY from hub_conversations.json on startup.

    This ensures conversation context survives process restarts.  Only the
    last _MAX_HISTORY messages per session are loaded to keep memory bounded.
    Sessions older than 24 hours are skipped — they're stale context that
    would confuse rather than help the LLM.
    """
    if not _CONV_PATH.exists():
        return
    try:
        data = json.loads(_CONV_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load conversation history from disk: %s", exc)
        return

    sessions = data.get("sessions", {})
    cutoff = datetime.now(timezone.utc).timestamp() - 24 * 3600  # 24-hour window

    loaded = 0
    for session_id, session_data in sessions.items():
        try:
            last_updated = session_data.get("last_updated", "")
            if last_updated:
                # Parse ISO timestamp; skip stale sessions
                ts = datetime.fromisoformat(last_updated).timestamp()
                if ts < cutoff:
                    continue
            messages: List[Dict[str, str]] = session_data.get("messages", [])
            if messages:
                # Keep only the most recent _MAX_HISTORY turns
                _SESSION_HISTORY[session_id] = messages[-_MAX_HISTORY:]
                loaded += 1
        except Exception:
            pass  # corrupted session — skip silently

    if loaded:
        logger.info("Restored conversation history for %d session(s) from disk.", loaded)


# Restore history immediately when the module is imported
_load_session_history()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HubRequest:
    """Incoming message from any channel."""
    message: str
    session_id: str                  # unique per chat / user (e.g. "telegram_123456")
    source: str = "unknown"          # "telegram" | "whatsapp" | "api" | …
    agent_id: str = "_collective_memory_"
    agent_name: str = "Personal Assistant"


@dataclass
class HubResponse:
    """Response sent back to the channel."""
    response: str
    source: str = "hub"
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "success"          # "success" | "partial" | "error"
    elapsed: float = 0.0
    # Local file paths produced as side-effects (e.g. downloaded zip, exported PDF)
    file_artifacts: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scheduling follow-up enrichment (mirrors personal_assistant/app.py)
# ---------------------------------------------------------------------------
# When a user replies with a bare time string ("2 PM to 3 PM") after a
# scheduling suggestion, the keyword pre-filter in the router finds no agent
# keywords and silently treats it as conversational — the LLM says "I've
# scheduled it" but nothing is actually booked.  Enriching the command so it
# contains explicit scheduling verbs fixes routing for both Telegram and
# Dashboard channels.

_BARE_TIME_PATTERN = re.compile(
    r"""^\s*
    \d{1,2}(?::\d{2})?          # start hour (e.g. 2 or 10:30)
    \s*(?:am|pm|AM|PM)          # AM/PM
    (?:
        \s*(?:to|\-|\u2013|till|until)\s*   # optional range separator
        \d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)  # end hour
    )?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)

# Matches a scheduling verb at the start of a command ("schedule", "book", etc.)
_SCHEDULING_VERB_PATTERN = re.compile(
    r"\b(?:schedule|book|create|set up|add|plan)\b",
    re.IGNORECASE,
)

# Matches a time reference inside a command ("at 8 PM", "9:30 am", etc.)
_INLINE_TIME_PATTERN = re.compile(
    r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    re.IGNORECASE,
)

_SCHEDULING_CONTEXT_KEYWORDS = frozenset({
    "schedule", "meeting", "slot", "free", "available", "book",
    "calendar", "appointment", "block", "time", "best time",
})

# Temporal references to carry forward into the enriched scheduling command.
# We scan BOTH user and assistant messages so "tomorrow" spoken by either party
# is captured and injected into the new command.
_TEMPORAL_PATTERN = re.compile(
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
    re.IGNORECASE,
)


def _enrich_scheduling_followup(command: str, history: List[Dict[str, str]]) -> str:
    """Enrich a scheduling-related command with date context from recent history.

    Handles two cases:
    1. Bare time reply ("3 PM") after a scheduling conversation — inject the
       scheduling verb and any date extracted from history.
    2. Full scheduling command ("Schedule Gym at 8 PM") that contains a time
       but **no date** — inject the specific date from recent history so the
       agent doesn't default to today.

    This fixes the bug where "Schedule a meeting at 8 PM for Gym Session"
    issued after discussing March 12th gets booked on today's date instead.
    """
    stripped = command.strip()

    # Scan recent messages from BOTH roles to extract temporal/scheduling context
    recent_messages = history[-8:] if len(history) >= 8 else history
    full_recent = " ".join(m.get("content", "") for m in recent_messages)
    recent_lower = full_recent.lower()

    # ── Case 1: bare time reply (old behaviour) ────────────────────────────
    if _BARE_TIME_PATTERN.match(stripped):
        if not any(kw in recent_lower for kw in _SCHEDULING_CONTEXT_KEYWORDS):
            return command
        date_context = ""
        all_temporal = _TEMPORAL_PATTERN.findall(full_recent)
        if all_temporal:
            best_match = max(all_temporal, key=len)
            date_context = f" on {best_match}"
        return f"Schedule a calendar meeting / book the time slot for {command}{date_context}"

    # ── Case 2: full scheduling command with time but no explicit date ──────
    # Only applies when the command has a scheduling verb and an inline time
    # reference but no date of its own.
    if not _SCHEDULING_VERB_PATTERN.search(stripped):
        return command
    if not _INLINE_TIME_PATTERN.search(stripped):
        return command
    if _TEMPORAL_PATTERN.search(stripped):
        # Command already has its own date — no enrichment needed
        return command

    # Pull the most specific date from recent history (user + assistant messages)
    # Prefer ordinal+month forms (e.g. "12th March") over vague ones ("march")
    all_temporal = _TEMPORAL_PATTERN.findall(full_recent)
    if not all_temporal:
        return command  # no date in context either — leave as-is

    best_match = max(all_temporal, key=len)
    # Avoid injecting generic weekday/month-only tokens unless nothing better exists
    _GENERIC = {"monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday", "january", "february", "march",
                "april", "may", "june", "july", "august", "september",
                "october", "november", "december"}
    if best_match.lower() in _GENERIC and len(all_temporal) > 1:
        # Try to find a more specific match (ordinal+month or ISO date)
        specific = [t for t in all_temporal if t.lower() not in _GENERIC]
        if specific:
            best_match = max(specific, key=len)

    enriched = f"{stripped} on {best_match}"
    return enriched


# ---------------------------------------------------------------------------
# Session management helpers
# ---------------------------------------------------------------------------

def clear_session(session_id: str) -> None:
    """Wipe conversation history for a session (e.g. after a /reset command)."""
    _SESSION_HISTORY.pop(session_id, None)
    # Remove from persistent store too
    try:
        with _conv_lock:
            if _CONV_PATH.exists():
                data = json.loads(_CONV_PATH.read_text(encoding="utf-8"))
                data.get("sessions", {}).pop(session_id, None)
                tmp = _CONV_PATH.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                tmp.replace(_CONV_PATH)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Internal helpers (ported from personal_assistant/app.py, Streamlit-free)
# ---------------------------------------------------------------------------

def _render_step_result(step: dict) -> str:
    icon = "✅" if step.get("status") == "success" else "❌"
    agent = step.get("agent", "?")
    tool = step.get("tool", "?")
    line = f"{icon} **{agent.title()}** — `{tool}`"
    if step.get("status") != "success":
        # step["error"] is None for skipped/partial states — fall back to
        # the nested result message so users always see a meaningful reason.
        error_msg = (
            step.get("error")
            or (step.get("result") or {}).get("message")
            or "Unknown error"
        )
        line += f"\n   ⚠️ {error_msg}"
    return line


def _compose_final_response(run_result: dict, original_command: str) -> str:
    """Ask the LLM to turn raw step results into a friendly response."""
    from src.agent.llm.llm_parser import get_llm_client

    steps = run_result.get("steps", [])
    steps_payload = [
        {
            "agent": s.get("agent"),
            "task": s.get("instruction") or s.get("tool", "?"),
            "status": s.get("status"),
            "result": (
                s.get("result", {}).get("message")
                if isinstance(s.get("result"), dict)
                else s.get("result")
            ),
            "error": s.get("error"),
        }
        for s in steps
    ]

    prompt = f"""The user asked: "{original_command}"

A multi-agent workflow was executed. Here are the raw results from each step:

{json.dumps(steps_payload, indent=2, default=str)}

Compose a response following these rules:
- Friendly, conversational tone
- Use **bold** for important names and key values
- Use bullet points / numbered lists for multiple items
- Use relevant emojis (📁 files, ✉️ emails, ✅ success)
- Add a brief summary sentence at the start
- Do NOT expose raw field names, JSON keys, or technical IDs
- Do NOT mention tool names or agent internals"""

    llm = get_llm_client()
    try:
        r = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Compose clear, friendly markdown responses from raw tool results."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
            timeout=40,
        )
        return r.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Final response composition failed: %s", exc)
        return "✅ Workflow completed. " + (
            "Steps: " + ", ".join(s.get("tool", "?") for s in steps) if steps else "No steps recorded."
        )


def _render_workflow_output(run_result: dict, original_command: str = "") -> str:
    status = run_result.get("status", "error")

    # ReAct orchestrator already composed the final answer — use it directly
    if run_result.get("final_answer") and status in ("success", "partial"):
        return run_result["final_answer"]

    if status == "success":
        return _compose_final_response(run_result, original_command)

    steps = run_result.get("steps", [])
    parts: List[str] = []
    if status == "partial":
        parts.append("⚠️ **Workflow partially completed** — one or more steps failed.")
    else:
        parts.append("❌ **Workflow failed.**")
        if not steps:
            parts.append(
                "\n🤔 I wasn't sure what to do with that. "
                "Could you rephrase or give me more detail? "
                "For example: *'Find my payslip files and email them to me'* "
                "or *'Zip the Payslips folder and send it to my email'*."
            )

    for s in steps:
        parts.append(_render_step_result(s))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Workflow summary logging
# ---------------------------------------------------------------------------

_AGENT_ICONS: Dict[str, str] = {
    "email": "✉️",
    "files": "📁",
    "calendar": "📅",
    "telegram": "✈️",
    "whatsapp": "💬",
    "drive": "☁️",
    "linkedin": "💼",
    "stock": "📈",
    "browser": "🌐",
    "habit": "🎯",
    "chat": "🗣️",
}


def _log_workflow_summary(
    mode: str,
    agents_used: List[str],
    llm_calls: int,
    elapsed: float,
    status: str,
) -> None:
    """Emit a compact, human-friendly workflow summary to the hub_processor logger.

    Example output::

        ╔══════════════════════════════════════╗
        ║  🤖  WORKFLOW COMPLETE               ║
        ╠══════════════════════════════════════╣
        ║  Status: ✅ success    Time: 2.41 s  ║
        ║  Mode:   Skill DAG                   ║
        ╠══════════════════════════════════════╣
        ║  Agents: 📁 files                    ║
        ╠══════════════════════════════════════╣
        ║  LLM Calls: 2 total                  ║
        ╚══════════════════════════════════════╝
    """
    w = 44  # inner width (between ║ and ║)
    bar = "═" * w
    status_icon = "✅" if status in ("success", "partial") else "❌"
    agents_str = "  ".join(
        f"{_AGENT_ICONS.get(a, '🔧')} {a}" for a in agents_used
    ) or "—"

    lines = [
        f"╔{bar}╗",
        f"║  {'🤖  WORKFLOW COMPLETE':<{w - 2}}║",
        f"╠{bar}╣",
        f"║  Status: {status_icon} {status:<8}   Time: {elapsed:.2f} s{'':<{max(0, w - 36)}}║",
        f"║  Mode:   {mode:<{w - 10}}║",
        f"╠{bar}╣",
        f"║  Agents: {agents_str:<{w - 10}}║",
        f"╠{bar}╣",
        f"║  LLM Calls: {llm_calls} total{'':<{max(0, w - 18 - len(str(llm_calls)))}}║",
        f"╚{bar}╝",
    ]
    logger.info("\n".join(lines))


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

class HubProcessor:
    """
    Channel-agnostic message processor.

    Usage:
        proc = HubProcessor()
        resp = proc.process("Download Q3 report and email it to alice@example.com",
                            session_id="telegram_12345",
                            source="telegram")
        send_back(resp.response)
    """

    def process(
        self,
        message: str,
        session_id: str,
        source: str = "unknown",
        agent_id: str = "_collective_memory_",
        agent_name: str = "Personal Assistant",
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> HubResponse:
        """Process one message and return a response.

        Parameters
        ----------
        on_progress:
            Optional callback called with a brief status string at key
            processing milestones (routing, planning, executing…).  Used by
            Telegram auto-responder to edit a live "thinking" placeholder
            message in the chat.  Safe to leave as None.
        """
        t0 = time.perf_counter()
        req = HubRequest(
            message=message,
            session_id=session_id,
            source=source,
            agent_id=agent_id,
            agent_name=agent_name,
        )

        # Bind a fresh correlation ID for this turn — propagates into every
        # skill / LLM call so all related log lines share the same corr= value.
        _cid = bind_correlation(new_correlation_id())
        logger.info(
            "┌─ [Hub:%s] Turn START  corr=%s  session=%s  command=%.120s",
            source, _cid, session_id, message,
        )

        # Build conversation history for this session
        history = _SESSION_HISTORY.setdefault(session_id, [])

        try:
            response_text, actions, status, file_artifacts, search_paths = self._dispatch(
                req, history, on_progress=on_progress
            )
        except Exception as exc:
            logger.exception("[HubProcessor] Unhandled error: %s", exc)
            response_text = f"❌ An unexpected error occurred: {exc}"
            actions = []
            status = "error"
            file_artifacts = []
            search_paths = []

        # Update session history with timestamps
        _ts = datetime.now(timezone.utc).isoformat()
        _elapsed = round(time.perf_counter() - t0, 2)
        history.append({"role": "user", "content": message, "ts": _ts})
        _hist_entry: Dict[str, Any] = {
            "role": "assistant",
            "content": response_text,
            "ts": _ts,
            "elapsed": _elapsed,
        }
        if file_artifacts:
            _hist_entry["file_artifacts"] = file_artifacts
        if search_paths:
            _hist_entry["search_paths"] = search_paths
        history.append(_hist_entry)
        logger.info(
            "└─ [Hub:%s] Turn END  corr=%s  status=%s  elapsed=%.2fs",
            source, _cid, status, _elapsed,
        )
        # Trim to keep memory bounded
        if len(history) > _MAX_HISTORY:
            _SESSION_HISTORY[session_id] = history[-_MAX_HISTORY:]

        # Persist to disk — makes conversations visible on the dashboard
        _persist_conversation(session_id, source, _SESSION_HISTORY.get(session_id, history))

        # Persist interaction to agent memory
        try:
            from src.agent.memory.agent_memory import get_agent_memory
            mem = get_agent_memory(agent_id)
            mem.add_interaction(
                command=message,
                action="hub_dispatch",
                result={"status": status, "source": source},
                importance="Medium",
            )
        except Exception as mem_err:
            logger.debug("Memory record skipped: %s", mem_err)

        return HubResponse(
            response=response_text,
            source=source,
            actions_taken=actions,
            status=status,
            elapsed=round(time.perf_counter() - t0, 2),
            file_artifacts=file_artifacts,
        )

    # ------------------------------------------------------------------

    def _dispatch(
        self,
        req: HubRequest,
        history: List[Dict[str, str]],
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> tuple[str, list, str, list]:
        """
        Route the message:
          1. Neither agent → conversational LLM reply
          2. Single agent  → direct agent orchestrator
          3. Multi-agent   → workflow planner + runner

        Returns (response_text, actions, status, file_artifacts).
        """
        from src.agent.workflows import classify_and_route, run_workflow

        def _progress(msg: str) -> None:
            if on_progress:
                try:
                    on_progress(msg)
                except Exception:
                    pass

        # Enrich bare time-slot follow-ups so the router recognises them
        routing_message = _enrich_scheduling_followup(req.message, history)
        if routing_message != req.message:
            logger.info("│  [ENRICH] Scheduling follow-up enriched: %.120s", routing_message)

        # Build structured Session State — inject resolved entities
        # (ISO dates, 24h times, files, e-mails) so agents receive exact values.
        enriched_query = _build_sq(routing_message, history)
        try:
            _sq_marker = "## Session State"
            if _sq_marker in enriched_query:
                _state_json = enriched_query.split(_sq_marker, 1)[1].strip()
                logger.info("│  [SESSION STATE] %s", " ".join(_state_json.split()))
        except Exception:
            pass

        # ── Unified intent classification ─────────────────────────────────────
        # classify_and_route() handles all three message patterns in one LLM call:
        #   CHAT              → "Do you know about cricket?"
        #   CONTEXT_FOLLOWUP  → "Can you zip that and mail it to me?"  (after search)
        #   FRESH_TASK        → "Are there any payslip files on my computer?"
        try:
            from src.agent.manifest.context_manifest import read_context as _read_ctx
            _active_ctx = _read_ctx()
        except Exception:
            _active_ctx = None
        try:
            from src.agent.context.conversation_state import _default_tracker as _cst
            _session_state = _cst.build(history, routing_message)
        except Exception:
            _session_state = None

        t_dispatch = time.perf_counter()
        _progress("🔍 Analyzing your request…")
        intent = classify_and_route(routing_message, _active_ctx, _session_state)
        agents_needed = intent.agents if not intent.is_chat else None
        logger.info(
            "│  [INTENT]  category=%s  agents=%s  reason=%s  source=%s",
            intent.category, agents_needed or "conversational", intent.reason, req.source,
        )

        # ── Pronoun clarification guard ────────────────────────────────────
        # When classify_and_route returns a non-chat intent but can resolve no
        # agents (e.g. "Can you zip that?" with no context manifest live), and
        # the message contains a bare pronoun that clearly refers to a previous
        # result, return a helpful clarification instead of routing to nothing.
        if not intent.is_chat and not agents_needed:
            _pronoun_re = re.compile(
                r'\b(them|those|those files|those documents|it|that|the files|'
                r'the documents|the folder|they)\b',
                re.IGNORECASE,
            )
            if _pronoun_re.search(req.message):
                logger.info("│  [INTENT-CLARIFY] pronoun + no resolvable agents → clarification")
                return (
                    "🤔 I'm not sure what you're referring to — I don't have any files "
                    "from a recent search in this conversation.\n\n"
                    "Could you be more specific? For example:\n"
                    "- *'Search for my payslip files and email them to me'*\n"
                    "- *'Find the project report and send it to my email'*",
                    [], "success", [], [],
                )
            # No pronoun, no agents — treat as a general chat question
            agents_needed = None

        # ── 1. Conversational fallback ─────────────────────────────────────
        if agents_needed is None:
            _progress("💬 Thinking…")
            reply = self._chat_response(req, history)
            _log_workflow_summary("💬 Chat", [], 1, time.perf_counter() - t_dispatch, "success")
            return reply, [], "success", [], []

        # ── 2. Single-agent shortcut ───────────────────────────────────────
        if len(agents_needed) == 1:
            _progress(f"⚙️ Running {agents_needed[0].title()} skill…")
            # Pass the structurally-enriched query so the skill agent receives
            # resolved entities (ISO dates, 24h times …) from Session State.
            reply, acts, artifacts, s_paths = self._run_single_agent(agents_needed[0], req, query=enriched_query)
            _llm_calls = acts[0].get("llm_calls", 1) if acts else 1
            _log_workflow_summary(
                "⚙️ Skill DAG", agents_needed, _llm_calls,
                time.perf_counter() - t_dispatch, "success",
            )
            return reply, acts, "success", artifacts, s_paths

        # ── 3. Multi-agent workflow ────────────────────────────────────────
        _agents_str = " + ".join(a.title() for a in agents_needed)
        _progress(f"📋 Planning workflow: {_agents_str}…")
        # Pass the enriched query (with ## Session State block) so the DAG
        # planner can resolve context references like 'them' / 'those files'
        # from session state (last_found_folder, last_found_paths, etc.).
        run_result = run_workflow(enriched_query)
        response_text = _render_workflow_output(run_result, req.message)
        actions = [
            {"agent": s.get("agent"), "tool": s.get("tool"), "status": s.get("status")}
            for s in run_result.get("steps", [])
        ]
        # Gather file artifacts from step results
        # file_artifacts: explicitly delivered files (zip, report, deliver_file output) — sent to Telegram
        # search_paths:   individual search hits (for context/follow-up) — NOT auto-sent
        file_artifacts: List[str] = []
        search_paths: List[str] = []
        _seen_artifacts: set = set()
        for step in run_result.get("steps", []):
            res = step.get("result") or {}
            if isinstance(res, dict):
                # Primary file output (zip, report, etc.) — deliver to user
                for key in ("file_path", "local_path", "archive", "destination"):
                    fp = res.get(key)
                    if fp and isinstance(fp, str) and fp not in _seen_artifacts and Path(fp).exists():
                        file_artifacts.append(fp)
                        _seen_artifacts.add(fp)
                        break
                # Individual search results — context only, NOT for auto-delivery
                for r in res.get("results", []):
                    if isinstance(r, dict):
                        rp = r.get("path", "")
                        if rp and isinstance(rp, str) and rp not in _seen_artifacts:
                            search_paths.append(rp)
                            _seen_artifacts.add(rp)
        _total_llm = sum(s.get("llm_calls", 0) for s in run_result.get("steps", []))
        _log_workflow_summary(
            "📋 Multi-Agent DAG", agents_needed, _total_llm,
            time.perf_counter() - t_dispatch, run_result.get("status", "error"),
        )

        # ── Gap-5: clear context after a successful delivery ───────────────
        # When a multi-agent workflow delivers a file (zip → email, zip → Drive,
        # etc.) the search context is no longer needed.  Leaving it alive causes
        # the NEXT unrelated message to still see "awaiting: file_action" which
        # can confuse the router into thinking it's a follow-up.
        if file_artifacts:
            try:
                from src.agent.manifest.context_manifest import clear_context as _cc
                _cc()
                logger.info(
                    "[context-manifest] context cleared after multi-agent delivery  artifacts=%d",
                    len(file_artifacts),
                )
            except Exception:
                pass

        return response_text, actions, run_result.get("status", "error"), file_artifacts, search_paths

    # ------------------------------------------------------------------

    def _chat_response(self, req: HubRequest, history: List[Dict[str, str]]) -> str:
        """Conversational reply via LLM (no agent tools needed)."""
        try:
            from src.agent.llm.llm_parser import get_llm_client
            from src.agent.memory.agent_memory import get_agent_memory
            from src.agent.memory.collective_memory import get_collective_context

            memory_context = ""
            try:
                memory_context = get_collective_context()
            except Exception:
                pass

            try:
                own_memory = get_agent_memory(req.agent_id)
                recalled = own_memory.recall_for_llm(req.message)
                if recalled:
                    memory_context += f"\n\n{recalled}"
            except Exception:
                pass

            llm = get_llm_client()
            return llm.chat(
                user_message=req.message,
                agent_name=req.agent_name,
                agent_type="Personal Assistant",
                memory_context=memory_context,
                conversation_history=history[-_MAX_HISTORY_FOR_LLM:],
            )
        except Exception as exc:
            logger.warning("Conversational LLM fallback failed: %s", exc)
            return (
                "I'm your Personal Assistant — give me commands that span your "
                "Drive and Email agents, e.g. *'Download the Q3 report and email it to alice@example.com'*."
            )

    # ------------------------------------------------------------------

    def _run_single_agent(self, agent: str, req: HubRequest, query: Optional[str] = None) -> tuple[str, list, list]:
        """
        Route to a single agent using the registry — no hardcoded agent names.
        Falls back to a generic executor call if no dedicated response composer exists.

        query: if provided, use this instead of req.message for agent execution.
               Allows callers to pass an enriched/resolved command.

        Returns (reply_text, actions, file_artifacts).
        """
        try:
            from src.agent.workflows.agent_registry import get_executor
            from pathlib import Path as _P

            executor = get_executor(agent)
            if executor is None:
                return f"❌ Agent '{agent}' is registered but could not be loaded.", [], []

            effective_query = query if query is not None else req.message
            # ── Context Manifest injection ────────────────────────────────
            # Prepend any persisted cross-turn context (email listing, calendar
            # events, drive files, file search results) so the LLM never
            # re-asks for information already resolved in the previous turn.
            # Pass the current agent name so tool-specific instructions are
            # only injected when this IS the agent that wrote the context —
            # prevents cross-agent tool hallucination (e.g. Drive agent being
            # told to call collect_files_from_manifest).
            try:
                from src.agent.manifest.context_manifest import inject_context_into_query as _ctxinj  # noqa: PLC0415
                effective_query = _ctxinj(effective_query, current_agent=agent)
                _ctx_marker = "## Context from Previous Turn"
                if _ctx_marker in effective_query:
                    _ctx_block = effective_query.split(_ctx_marker, 1)[1].split("## Session State", 1)[0].strip()
                    logger.info("│  [CTX INJECT] agent=%s context_block=%.400s", agent, _ctx_block)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────
            # Pass an artifacts_out dict so sub-agents can surface file paths.
            # Seed with session context so agents can route background job
            # notifications back to the correct user/channel.
            artifacts_out: Dict[str, Any] = {
                "_session_id": req.session_id,
                "_pa_id": req.agent_id,
                "_source": req.source,
            }
            result = executor(effective_query, agent_id=None, artifacts_out=artifacts_out)
            action = result.get("action", "react_response")

            # Explicit deliveries only: file_path is set by deliver_file() — sent to Telegram/Dashboard
            file_artifacts: List[str] = []
            _seen_fa: set = set()
            fp = artifacts_out.get("file_path") or result.get("file_path")
            if fp and isinstance(fp, str) and _P(fp).exists() and fp not in _seen_fa:
                file_artifacts.append(fp)
                _seen_fa.add(fp)
            # Search results (found_paths) — for context / follow-up only, NOT auto-delivered
            search_paths: List[str] = [
                rp for rp in (artifacts_out.get("found_paths") or result.get("found_paths") or [])
                if rp and isinstance(rp, str)
            ]

            # ── Gap-2 safety net ───────────────────────────────────────────
            # If the agent returned search paths but forgot to call write_context(),
            # auto-write a minimal context entry so the NEXT turn can still do
            # "zip them" / "email those" without triggering a fresh search.
            if search_paths:
                try:
                    from src.agent.manifest.context_manifest import (
                        read_context as _rc,
                        write_context as _wc,
                    )
                    if _rc(agent=agent) is None:
                        _wc(
                            agent=agent,
                            topic="auto_search_result",
                            resolved_entities={
                                "last_found_paths": search_paths,
                                "last_found_folder": str(_P(search_paths[0]).parent),
                                "count": len(search_paths),
                            },
                            awaiting="file_action",
                        )
                        logger.info(
                            "[context-manifest] auto-wrote context for agent=%s with %d search paths",
                            agent, len(search_paths),
                        )
                except Exception as _awc_err:
                    logger.debug("[context-manifest] auto-write safety net skipped: %s", _awc_err)

            # ReAct / NL orchestrators return a ready-made message
            if action == "react_response" or "message" in result:
                _llm = result.get("llm_calls", 1)
                return (
                    result.get("message", str(result)),
                    [{"agent": agent, "action": action, "llm_calls": _llm}],
                    file_artifacts,
                    search_paths,
                )

            # Try to find a dedicated response composer for richer formatting
            # Pattern: src.agent.ui.<agent>_agent.app._compose_<agent>_response
            try:
                import importlib
                mod = importlib.import_module(f"src.agent.ui.{agent}_agent.app")
                compose_fn = getattr(mod, f"_compose_{agent}_response", None)
                if compose_fn:
                    reply = compose_fn(result, action, req.message)
                    _llm = result.get("llm_calls", 1)
                    return reply, [{"agent": agent, "action": action, "llm_calls": _llm}], file_artifacts, search_paths
            except Exception:
                pass

            # Last resort: stringify the result
            _llm = result.get("llm_calls", 1)
            return (
                str(result.get("message", result)),
                [{"agent": agent, "action": action, "llm_calls": _llm}],
                file_artifacts,
                search_paths,
            )

        except Exception as exc:
            logger.exception("Single-agent error (%s): %s", agent, exc)
            return f"❌ {agent.title()} agent error: {exc}", [{"agent": agent, "status": "error"}], [], []
