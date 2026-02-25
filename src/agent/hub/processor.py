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
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hub_processor")

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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HubRequest:
    """Incoming message from any channel."""
    message: str
    session_id: str                  # unique per chat / user (e.g. "telegram_123456")
    source: str = "unknown"          # "telegram" | "whatsapp" | "api" | …
    agent_id: str = "__multi_agent__"
    agent_name: str = "Personal Assistant"


@dataclass
class HubResponse:
    """Response sent back to the channel."""
    response: str
    source: str = "hub"
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "success"          # "success" | "partial" | "error"
    elapsed: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers (ported from personal_assistant/app.py, Streamlit-free)
# ---------------------------------------------------------------------------

def _render_step_result(step: dict) -> str:
    icon = "✅" if step.get("status") == "success" else "❌"
    agent = step.get("agent", "?")
    tool = step.get("tool", "?")
    line = f"{icon} **{agent.title()}** — `{tool}`"
    if step.get("status") != "success":
        line += f"\n   ⚠️ {step.get('error', 'Unknown error')}"
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
            parts.append("\nCould not create a plan for this command. Try rephrasing it.")

    for s in steps:
        parts.append(_render_step_result(s))

    return "\n".join(parts)


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

    def process(self, message: str, session_id: str, source: str = "unknown",
                agent_id: str = "__multi_agent__",
                agent_name: str = "Personal Assistant") -> HubResponse:
        t0 = time.perf_counter()
        req = HubRequest(
            message=message,
            session_id=session_id,
            source=source,
            agent_id=agent_id,
            agent_name=agent_name,
        )

        # Build conversation history for this session
        history = _SESSION_HISTORY.setdefault(session_id, [])

        try:
            response_text, actions, status = self._dispatch(req, history)
        except Exception as exc:
            logger.exception("[HubProcessor] Unhandled error: %s", exc)
            response_text = f"❌ An unexpected error occurred: {exc}"
            actions = []
            status = "error"

        # Update session history with timestamps
        _ts = datetime.now(timezone.utc).isoformat()
        history.append({"role": "user", "content": message, "ts": _ts})
        history.append({
            "role": "assistant",
            "content": response_text,
            "ts": _ts,
            "elapsed": round(time.perf_counter() - t0, 2),
        })
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
        )

    # ------------------------------------------------------------------

    def _dispatch(
        self,
        req: HubRequest,
        history: List[Dict[str, str]],
    ) -> tuple[str, list, str]:
        """
        Route the message:
          1. Neither agent → conversational LLM reply
          2. Single agent  → direct agent orchestrator
          3. Multi-agent   → workflow planner + runner
        """
        from src.agent.workflows import detect_agents_needed, run_workflow

        agents_needed = detect_agents_needed(req.message)

        # ── 1. Conversational fallback ─────────────────────────────────────
        if agents_needed is None:
            reply = self._chat_response(req, history)
            return reply, [], "success"

        # ── 2. Single-agent shortcut ───────────────────────────────────────
        if len(agents_needed) == 1:
            reply, acts = self._run_single_agent(agents_needed[0], req)
            return reply, acts, "success"

        # ── 3. Multi-agent workflow ────────────────────────────────────────
        run_result = run_workflow(req.message)
        response_text = _render_workflow_output(run_result, req.message)
        actions = [
            {"agent": s.get("agent"), "tool": s.get("tool"), "status": s.get("status")}
            for s in run_result.get("steps", [])
        ]
        return response_text, actions, run_result.get("status", "error")

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

    def _run_single_agent(self, agent: str, req: HubRequest) -> tuple[str, list]:
        """
        Route to a single agent using the registry — no hardcoded agent names.
        Falls back to a generic executor call if no dedicated response composer exists.
        """
        try:
            from src.agent.workflows.agent_registry import get_executor

            executor = get_executor(agent)
            if executor is None:
                return f"❌ Agent '{agent}' is registered but could not be loaded.", []

            result = executor(req.message, agent_id=None)
            action = result.get("action", "react_response")

            # ReAct / NL orchestrators return a ready-made message
            if action == "react_response" or "message" in result:
                return result.get("message", str(result)), [{"agent": agent, "action": action}]

            # Try to find a dedicated response composer for richer formatting
            # Pattern: src.agent.ui.<agent>_agent.app._compose_<agent>_response
            try:
                import importlib
                mod = importlib.import_module(f"src.agent.ui.{agent}_agent.app")
                compose_fn = getattr(mod, f"_compose_{agent}_response", None)
                if compose_fn:
                    reply = compose_fn(result, action, req.message)
                    return reply, [{"agent": agent, "action": action}]
            except Exception:
                pass

            # Last resort: stringify the result
            return str(result.get("message", result)), [{"agent": agent, "action": action}]

        except Exception as exc:
            logger.exception("Single-agent error (%s): %s", agent, exc)
            return f"❌ {agent.title()} agent error: {exc}", [{"agent": agent, "status": "error"}]
